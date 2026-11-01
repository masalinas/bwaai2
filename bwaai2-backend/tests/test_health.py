from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data
    assert data["dependencies"]["redis"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_redis_down(client: AsyncClient) -> None:
    with patch("app.services.storage.StorageService.ping", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = False
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["dependencies"]["redis"] == "unreachable"
