import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai.errors import APIError

from app.core.exceptions import ParserFailedError, SummaryFailedError, SummaryRateLimitedError
from app.models.documents import ContentFormat, DocumentPage
from app.services.gemini import GeminiService
from app.services.parsers.gemini_parser import GeminiParser
from app.services.summarizer import DocumentSummarizer
from tests.conftest import create_sample_pdf


def make_mock_gemini_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


@pytest.mark.asyncio
async def test_gemini_parser_happy_path() -> None:
    pdf_bytes = create_sample_pdf(num_pages=2)
    mock_service = MagicMock(spec=GeminiService)

    structured_json = json.dumps(
        {
            "pages": [
                {"page_number": 1, "markdown": "# Fiscal Performance\n\nRevenue grew 18%."},
                {"page_number": 2, "markdown": "## Balance Sheet\n\nCash reserves strong."},
            ]
        }
    )
    mock_service.generate_content = AsyncMock(
        return_value=make_mock_gemini_response(structured_json)
    )

    parser = GeminiParser(gemini_service=mock_service)
    pages = await parser.parse(pdf_bytes)

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[0].format == ContentFormat.markdown
    assert "Revenue grew 18%" in pages[0].content
    assert pages[1].page_number == 2
    assert "Balance Sheet" in pages[1].content


@pytest.mark.asyncio
async def test_gemini_parser_page_mismatch_retry_then_succeed() -> None:
    pdf_bytes = create_sample_pdf(num_pages=2)
    mock_service = MagicMock(spec=GeminiService)

    # Attempt 1: only 1 page (mismatch)
    bad_json = json.dumps({"pages": [{"page_number": 1, "markdown": "Page 1 only"}]})
    # Attempt 2: 2 pages (match)
    good_json = json.dumps(
        {
            "pages": [
                {"page_number": 1, "markdown": "Page 1 recovered"},
                {"page_number": 2, "markdown": "Page 2 recovered"},
            ]
        }
    )
    mock_service.generate_content = AsyncMock(
        side_effect=[
            make_mock_gemini_response(bad_json),
            make_mock_gemini_response(good_json),
        ]
    )

    parser = GeminiParser(gemini_service=mock_service)
    pages = await parser.parse(pdf_bytes)

    assert len(pages) == 2
    assert mock_service.generate_content.call_count == 2
    assert pages[1].page_number == 2


@pytest.mark.asyncio
async def test_gemini_parser_persistent_mismatch_fails() -> None:
    pdf_bytes = create_sample_pdf(num_pages=3)
    mock_service = MagicMock(spec=GeminiService)

    mismatch_json = json.dumps({"pages": [{"page_number": 1, "markdown": "Only one page"}]})
    mock_service.generate_content = AsyncMock(return_value=make_mock_gemini_response(mismatch_json))

    parser = GeminiParser(gemini_service=mock_service)
    with pytest.raises(ParserFailedError) as exc_info:
        await parser.parse(pdf_bytes)

    assert exc_info.value.code == "PARSER_FAILED"
    assert mock_service.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_summarizer_single_pass_happy_path() -> None:
    mock_service = MagicMock(spec=GeminiService)
    mock_service.generate_content = AsyncMock(
        return_value=make_mock_gemini_response(
            "The document highlights robust annual profitability."
        )
    )

    pages = [
        DocumentPage(page_number=1, content="Sales increased by 20%.", format=ContentFormat.text),
        DocumentPage(
            page_number=2, content="Operating expenses remained flat.", format=ContentFormat.text
        ),
    ]

    summarizer = DocumentSummarizer(gemini_service=mock_service)
    summary = await summarizer.summarize_document(pages)

    assert summary == "The document highlights robust annual profitability."
    assert mock_service.generate_content.call_count == 1


@pytest.mark.asyncio
async def test_summarizer_empty_extracted_text_fails() -> None:
    pages = [
        DocumentPage(page_number=1, content="   \n   ", format=ContentFormat.text),
        DocumentPage(page_number=2, content="", format=ContentFormat.text),
    ]

    summarizer = DocumentSummarizer()
    with pytest.raises(SummaryFailedError) as exc_info:
        await summarizer.summarize_document(pages)

    assert exc_info.value.code == "SUMMARY_FAILED"
    assert "gemini" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_summarizer_map_reduce_for_large_document() -> None:
    mock_service = MagicMock(spec=GeminiService)
    # Return chunk summaries then final summary
    mock_service.generate_content = AsyncMock(
        side_effect=[
            make_mock_gemini_response("Intermediate summary 1."),
            make_mock_gemini_response("Intermediate summary 2."),
            make_mock_gemini_response("Final consolidated executive summary."),
        ]
    )

    # Generate pages exceeding 100,000 characters
    long_content = "Important financial text data and metrics. " * 1500  # ~64,000 chars
    pages = [
        DocumentPage(page_number=1, content=long_content, format=ContentFormat.text),
        DocumentPage(page_number=2, content=long_content, format=ContentFormat.text),
    ]

    summarizer = DocumentSummarizer(gemini_service=mock_service)
    summary = await summarizer.summarize_document(pages)

    assert summary == "Final consolidated executive summary."
    assert mock_service.generate_content.call_count == 3


@pytest.mark.asyncio
async def test_gemini_service_rate_limit_retry_and_exhaustion() -> None:
    gemini_service = GeminiService(concurrency=2)
    mock_client = MagicMock()

    api_429 = APIError(429, {"error": {"message": "Quota exceeded (RESOURCE_EXHAUSTED)"}})
    mock_client.aio.models.generate_content = AsyncMock(side_effect=api_429)
    gemini_service._client = mock_client

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(SummaryRateLimitedError) as exc_info:
            await gemini_service.generate_content(contents="test prompt", max_retries=3)

    assert exc_info.value.code == "SUMMARY_RATE_LIMITED"
    assert mock_client.aio.models.generate_content.call_count == 3


@pytest.mark.asyncio
async def test_gemini_missing_api_key() -> None:
    # Real GeminiService with empty API key
    gemini_service = GeminiService(api_key="")

    # 1. GeminiParser raises ParserUnavailableError
    parser = GeminiParser(gemini_service=gemini_service)
    pdf_bytes = create_sample_pdf(1)
    with pytest.raises(Exception) as exc_p:
        await parser.parse(pdf_bytes)
    assert exc_p.value.code == "PARSER_UNAVAILABLE"
    assert "GEMINI_API_KEY is not set" in exc_p.value.message

    # 2. DocumentSummarizer raises SummaryFailedError
    summarizer = DocumentSummarizer(gemini_service=gemini_service)
    pages = [DocumentPage(page_number=1, content="Some text", format=ContentFormat.text)]
    with pytest.raises(SummaryFailedError) as exc_s:
        await summarizer.summarize_document(pages)
    assert exc_s.value.code == "SUMMARY_FAILED"
    assert "GEMINI_API_KEY is not set" in exc_s.value.message
