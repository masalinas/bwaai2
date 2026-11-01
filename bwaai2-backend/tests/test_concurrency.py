import asyncio

import pytest
from httpx import AsyncClient

from tests.conftest import create_sample_pdf


@pytest.mark.asyncio
async def test_concurrent_uploads(client: AsyncClient) -> None:
    pdf_bytes = create_sample_pdf(1)

    async def upload_single(idx: int):
        files = [("files", (f"concurrent_{idx}.pdf", pdf_bytes, "application/pdf"))]
        return await client.post("/documents", files=files, data={"parser": "pypdf"})

    # Fire 10 concurrent requests
    responses = await asyncio.gather(*(upload_single(i) for i in range(10)))

    doc_ids = set()
    for resp in responses:
        assert resp.status_code == 202
        data = resp.json()
        assert len(data) == 1
        doc_ids.add(data[0]["document_id"])

    # Verify all 10 document IDs are strictly unique
    assert len(doc_ids) == 10
