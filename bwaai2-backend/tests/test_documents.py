from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.core import constants
from app.core.config import settings
from tests.conftest import create_sample_encrypted_pdf, create_sample_pdf


@pytest.mark.asyncio
async def test_upload_single_pdf_happy_path(client: AsyncClient, fake_redis) -> None:
    pdf_bytes = create_sample_pdf(num_pages=2)
    files = [("files", ("test1.pdf", pdf_bytes, "application/pdf"))]

    response = await client.post("/documents", files=files, data={"parser": "pypdf"})

    assert response.status_code == 202
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    item = data[0]
    assert item["filename"] == "test1.pdf"
    assert item["status"] == "queued"
    assert item["document_id"].startswith("doc_")

    # Verify Redis Stream job was published
    jobs = await fake_redis.xrange(constants.STREAM_DOCUMENTS_JOBS)
    assert len(jobs) == 1
    _, fields = jobs[0]
    assert fields[b"document_id"] == item["document_id"].encode("utf-8")
    assert fields[b"parser"] == b"pypdf"


@pytest.mark.asyncio
async def test_upload_multiple_pdfs(client: AsyncClient, fake_redis) -> None:
    pdf1 = create_sample_pdf(num_pages=1)
    pdf2 = create_sample_pdf(num_pages=3)
    files = [
        ("files", ("report.pdf", pdf1, "application/pdf")),
        ("files", ("summary.pdf", pdf2, "application/pdf")),
    ]

    response = await client.post("/documents", files=files, data={"parser": "pypdf"})

    assert response.status_code == 202
    data = response.json()
    assert len(data) == 2
    assert data[0]["filename"] == "report.pdf"
    assert data[1]["filename"] == "summary.pdf"


@pytest.mark.asyncio
async def test_upload_invalid_mime_type(client: AsyncClient) -> None:
    files = [("files", ("image.png", b"fake-png-data", "image/png"))]

    response = await client.post("/documents", files=files)

    assert response.status_code == 415
    data = response.json()
    assert data["code"] == "INVALID_FILE_TYPE"
    assert "image/png" in data["message"]


@pytest.mark.asyncio
async def test_upload_spoofed_pdf_magic_bytes(client: AsyncClient) -> None:
    # Has .pdf extension and application/pdf header, but content does not start with %PDF-
    files = [("files", ("fake.pdf", b"NOT_A_PDF_FILE_HEADER", "application/pdf"))]

    response = await client.post("/documents", files=files)

    assert response.status_code == 415
    data = response.json()
    assert data["code"] == "INVALID_FILE_TYPE"


@pytest.mark.asyncio
async def test_upload_empty_file(client: AsyncClient) -> None:
    files = [("files", ("empty.pdf", b"", "application/pdf"))]

    response = await client.post("/documents", files=files)

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "EMPTY_FILE"


@pytest.mark.asyncio
async def test_upload_too_many_files(client: AsyncClient) -> None:
    pdf_bytes = create_sample_pdf(1)
    files = [("files", (f"doc_{i}.pdf", pdf_bytes, "application/pdf")) for i in range(12)]

    response = await client.post("/documents", files=files)

    assert response.status_code == 413
    data = response.json()
    assert data["code"] == "TOO_MANY_FILES"


@pytest.mark.asyncio
async def test_upload_encrypted_pdf(client: AsyncClient) -> None:
    encrypted_bytes = create_sample_encrypted_pdf("pass123")
    files = [("files", ("locked.pdf", encrypted_bytes, "application/pdf"))]

    response = await client.post("/documents", files=files)

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "ENCRYPTED_PDF"


@pytest.mark.asyncio
async def test_upload_parser_selection(client: AsyncClient) -> None:
    pdf_bytes = create_sample_pdf(1)

    # 1. Gemini parser is now supported and accepted by upload
    files_gemini = [("files", ("doc_gemini.pdf", pdf_bytes, "application/pdf"))]
    res_gemini = await client.post("/documents", files=files_gemini, data={"parser": "gemini"})
    assert res_gemini.status_code == 202
    assert res_gemini.json()[0]["status"] == "queued"

    # 2. Mistral parser when MISTRAL_API_KEY is not configured
    files_mistral = [("files", ("doc_mistral.pdf", pdf_bytes, "application/pdf"))]
    with patch.object(settings, "MISTRAL_API_KEY", ""):
        res_mistral_unconfigured = await client.post(
            "/documents", files=files_mistral, data={"parser": "mistral"}
        )
        assert res_mistral_unconfigured.status_code == 500
        assert res_mistral_unconfigured.json()["code"] == "PARSER_UNAVAILABLE"

    # 3. Mistral parser when MISTRAL_API_KEY is configured
    with patch.object(settings, "MISTRAL_API_KEY", "mock-key"):
        res_mistral_configured = await client.post(
            "/documents", files=files_mistral, data={"parser": "mistral"}
        )
        assert res_mistral_configured.status_code == 202
        assert res_mistral_configured.json()[0]["status"] == "queued"


@pytest.mark.asyncio
async def test_get_document_details(client: AsyncClient) -> None:
    # 1. Non-existent document
    response = await client.get("/documents/doc_nonexistent999")
    assert response.status_code == 404
    assert response.json()["code"] == "DOCUMENT_NOT_FOUND"

    # 2. Upload and retrieve
    pdf_bytes = create_sample_pdf(1)
    files = [("files", ("contract.pdf", pdf_bytes, "application/pdf"))]
    post_resp = await client.post("/documents", files=files)
    doc_id = post_resp.json()[0]["document_id"]

    get_resp = await client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 200
    doc_detail = get_resp.json()
    assert doc_detail["document_id"] == doc_id
    assert doc_detail["filename"] == "contract.pdf"
    assert doc_detail["status"] == "queued"
    assert doc_detail["pages"] is None
    assert doc_detail["summary"] is None


@pytest.mark.asyncio
async def test_list_documents_pagination(client: AsyncClient) -> None:
    pdf_bytes = create_sample_pdf(1)

    # Upload 5 documents
    for i in range(5):
        files = [("files", (f"file_{i}.pdf", pdf_bytes, "application/pdf"))]
        await client.post("/documents", files=files)

    # Query with limit 2
    r1 = await client.get("/documents?limit=2")
    assert r1.status_code == 200
    p1 = r1.json()
    assert len(p1["items"]) == 2
    assert p1["has_more"] is True
    assert p1["next_cursor"] is not None

    # Query next page
    cursor = p1["next_cursor"]
    r2 = await client.get(f"/documents?limit=2&cursor={cursor}")
    assert r2.status_code == 200
    p2 = r2.json()
    assert len(p2["items"]) == 2

    # Query remaining
    cursor2 = p2["next_cursor"]
    r3 = await client.get(f"/documents?limit=2&cursor={cursor2}")
    assert r3.status_code == 200
    p3 = r3.json()
    assert len(p3["items"]) == 1
    assert p3["has_more"] is False
    assert p3["next_cursor"] is None
