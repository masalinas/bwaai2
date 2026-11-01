from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from httpx2 import Response as Httpx2Response
from mistralai.client.errors import SDKError

from app.core.config import settings
from app.core.exceptions import (
    ParserFailedError,
    ParserRateLimitedError,
    ParserTransientError,
    ParserUnavailableError,
)
from app.models.documents import ContentFormat
from app.services.parsers.mistral_parser import MistralParser
from tests.conftest import create_sample_pdf


class MockOCRPage:
    def __init__(self, index: int, markdown: str) -> None:
        self.index = index
        self.markdown = markdown


class MockOCRResponse:
    def __init__(self, pages: list[MockOCRPage]) -> None:
        self.pages = pages


@pytest.mark.asyncio
async def test_mistral_parser_happy_path_inline() -> None:
    pdf_bytes = create_sample_pdf(num_pages=2)
    mock_client = MagicMock()

    mock_response = MockOCRResponse(
        pages=[
            MockOCRPage(index=0, markdown="# Page 1 Markdown Content"),
            MockOCRPage(index=1, markdown="# Page 2 Markdown Content"),
        ]
    )
    mock_client.ocr.process_async = AsyncMock(return_value=mock_response)

    parser = MistralParser(api_key="mock_mistral_key", client=mock_client)
    pages = await parser.parse(pdf_bytes)

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[0].format == ContentFormat.markdown
    assert pages[0].content == "# Page 1 Markdown Content"
    assert pages[1].page_number == 2
    assert pages[1].format == ContentFormat.markdown
    assert pages[1].content == "# Page 2 Markdown Content"

    # Verify inline base64 document format
    mock_client.ocr.process_async.assert_called_once()
    call_kwargs = mock_client.ocr.process_async.call_args.kwargs
    assert call_kwargs["model"] == settings.MISTRAL_OCR_MODEL
    assert call_kwargs["include_image_base64"] is False
    doc_arg = call_kwargs["document"]
    assert doc_arg["type"] == "document_url"
    assert doc_arg["document_url"].startswith("data:application/pdf;base64,")


@pytest.mark.asyncio
async def test_mistral_parser_files_api_for_large_pdf() -> None:
    pdf_bytes = create_sample_pdf(num_pages=1)
    mock_client = MagicMock()

    mock_client.files.upload_async = AsyncMock(return_value=MagicMock(id="file_mistral_999"))
    mock_client.files.get_signed_url_async = AsyncMock(
        return_value=MagicMock(url="https://api.mistral.ai/files/file_mistral_999/signed")
    )
    mock_response = MockOCRResponse(pages=[MockOCRPage(index=0, markdown="# Large Document")])
    mock_client.ocr.process_async = AsyncMock(return_value=mock_response)
    mock_client.files.delete_async = AsyncMock(return_value=None)

    # Set threshold to 10 bytes so sample PDF exceeds it
    parser = MistralParser(
        api_key="mock_mistral_key",
        inline_threshold_bytes=10,
        client=mock_client,
    )
    pages = await parser.parse(pdf_bytes)

    assert len(pages) == 1
    assert pages[0].content == "# Large Document"

    mock_client.files.upload_async.assert_called_once()
    mock_client.files.get_signed_url_async.assert_called_once_with(file_id="file_mistral_999")
    mock_client.ocr.process_async.assert_called_once()
    ocr_call = mock_client.ocr.process_async.call_args.kwargs
    assert (
        ocr_call["document"]["document_url"]
        == "https://api.mistral.ai/files/file_mistral_999/signed"
    )
    mock_client.files.delete_async.assert_called_once_with(file_id="file_mistral_999")


@pytest.mark.asyncio
async def test_mistral_parser_page_count_mismatch_retry_then_succeed() -> None:
    pdf_bytes = create_sample_pdf(num_pages=2)
    mock_client = MagicMock()

    mismatched_response = MockOCRResponse(pages=[MockOCRPage(index=0, markdown="# Page 1")])
    matching_response = MockOCRResponse(
        pages=[
            MockOCRPage(index=0, markdown="# Page 1"),
            MockOCRPage(index=1, markdown="# Page 2"),
        ]
    )

    mock_client.ocr.process_async = AsyncMock(side_effect=[mismatched_response, matching_response])

    parser = MistralParser(api_key="mock_mistral_key", client=mock_client)
    pages = await parser.parse(pdf_bytes)

    assert len(pages) == 2
    assert mock_client.ocr.process_async.call_count == 2


@pytest.mark.asyncio
async def test_mistral_parser_persistent_mismatch_fails() -> None:
    pdf_bytes = create_sample_pdf(num_pages=3)
    mock_client = MagicMock()

    mismatched_response = MockOCRResponse(pages=[MockOCRPage(index=0, markdown="# Page 1")])
    mock_client.ocr.process_async = AsyncMock(return_value=mismatched_response)

    parser = MistralParser(api_key="mock_mistral_key", client=mock_client)

    with pytest.raises(ParserFailedError) as exc_info:
        await parser.parse(pdf_bytes)

    assert exc_info.value.code == "PARSER_FAILED"
    assert "source PDF contains 3 pages" in exc_info.value.message
    assert mock_client.ocr.process_async.call_count == 2


@pytest.mark.asyncio
async def test_mistral_parser_rate_limit_429() -> None:
    pdf_bytes = create_sample_pdf(num_pages=1)
    mock_client = MagicMock()

    raw_resp = Httpx2Response(status_code=429)
    err = SDKError("Rate limit exceeded", raw_response=raw_resp, body="Quota reached")
    mock_client.ocr.process_async = AsyncMock(side_effect=err)

    parser = MistralParser(api_key="mock_mistral_key", client=mock_client)

    with pytest.raises(ParserRateLimitedError) as exc_info:
        await parser.parse(pdf_bytes)

    assert exc_info.value.code == "PARSER_FAILED"
    assert "rate limit exceeded" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_mistral_parser_permanent_4xx() -> None:
    pdf_bytes = create_sample_pdf(num_pages=1)
    mock_client = MagicMock()

    raw_resp = Httpx2Response(status_code=422)
    err = SDKError("Unprocessable entity", raw_response=raw_resp, body="Invalid encoding")
    mock_client.ocr.process_async = AsyncMock(side_effect=err)

    parser = MistralParser(api_key="mock_mistral_key", client=mock_client)

    with pytest.raises(ParserFailedError) as exc_info:
        await parser.parse(pdf_bytes)

    assert exc_info.value.code == "PARSER_FAILED"
    assert "rejected document (422)" in exc_info.value.message


@pytest.mark.asyncio
async def test_mistral_parser_timeout_transient() -> None:
    pdf_bytes = create_sample_pdf(num_pages=1)
    mock_client = MagicMock()
    mock_client.ocr.process_async = AsyncMock(side_effect=TimeoutError("Request timed out"))

    parser = MistralParser(api_key="mock_mistral_key", client=mock_client)

    with pytest.raises(ParserTransientError) as exc_info:
        await parser.parse(pdf_bytes)

    assert "timed out" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_mistral_parser_missing_api_key() -> None:
    pdf_bytes = create_sample_pdf(num_pages=1)
    parser = MistralParser(api_key="")

    with pytest.raises(ParserUnavailableError) as exc_info:
        await parser.parse(pdf_bytes)

    assert exc_info.value.code == "PARSER_UNAVAILABLE"
    assert "MISTRAL_API_KEY is not set" in exc_info.value.message


@pytest.mark.asyncio
async def test_mistral_upload_missing_key_vs_present(client: AsyncClient) -> None:
    pdf_bytes = create_sample_pdf(1)
    files = [("files", ("test.pdf", pdf_bytes, "application/pdf"))]

    # 1. When MISTRAL_API_KEY is empty -> 500 PARSER_UNAVAILABLE
    with patch.object(settings, "MISTRAL_API_KEY", ""):
        resp_missing = await client.post("/documents", files=files, data={"parser": "mistral"})
        assert resp_missing.status_code == 500
        assert resp_missing.json()["code"] == "PARSER_UNAVAILABLE"
        assert "not configured" in resp_missing.json()["message"].lower()

    # 2. When MISTRAL_API_KEY is set -> 202 Accepted
    with patch.object(settings, "MISTRAL_API_KEY", "mistral-valid-key"):
        resp_present = await client.post("/documents", files=files, data={"parser": "mistral"})
        assert resp_present.status_code == 202
        assert resp_present.json()[0]["status"] == "queued"
