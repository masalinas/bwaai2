from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.core import constants
from tests.conftest import create_sample_pdf


@pytest.mark.asyncio
async def test_status_unknown_id(client: AsyncClient) -> None:
    response = await client.get("/documents/doc_does_not_exist/status")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "DOCUMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_status_polling_queued(client: AsyncClient) -> None:
    pdf_bytes = create_sample_pdf(1)
    files = [("files", ("invoice.pdf", pdf_bytes, "application/pdf"))]
    post_resp = await client.post("/documents", files=files)
    doc_id = post_resp.json()[0]["document_id"]

    response = await client.get(f"/documents/{doc_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == doc_id
    assert data["status"] == "queued"
    assert "Retry-After" in response.headers
    assert response.headers["Retry-After"] == "3"


@pytest.mark.asyncio
async def test_status_polling_done(client: AsyncClient, fake_redis) -> None:
    pdf_bytes = create_sample_pdf(1)
    files = [("files", ("invoice.pdf", pdf_bytes, "application/pdf"))]
    post_resp = await client.post("/documents", files=files)
    doc_id = post_resp.json()[0]["document_id"]

    # Manually transition to done in redis
    now_iso = datetime.now(UTC).isoformat()
    await fake_redis.hset(constants.doc_key(doc_id), b"status", b"done")
    await fake_redis.hset(constants.doc_key(doc_id), b"updated_at", now_iso.encode("utf-8"))

    response = await client.get(f"/documents/{doc_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    # Retry-After header should not be present when job is done
    assert "Retry-After" not in response.headers
