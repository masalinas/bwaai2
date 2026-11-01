import io
from collections.abc import AsyncGenerator

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from pypdf import PdfWriter

from app.main import app
from app.services.storage import get_redis_client


def create_sample_pdf(num_pages: int = 1) -> bytes:
    """Generate minimal valid PDF bytes."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def create_sample_encrypted_pdf(password: str = "secret123") -> bytes:
    """Generate minimal encrypted PDF bytes."""
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=False)


@pytest.fixture
async def client(fake_redis: fakeredis.aioredis.FakeRedis) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
