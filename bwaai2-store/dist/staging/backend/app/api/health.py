from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.core.config import settings
from app.models.errors import Error
from app.models.health import HealthResponse
from app.services.storage import StorageService, get_redis_client

router = APIRouter(tags=["system"])


def get_storage_service(redis: Redis = Depends(get_redis_client)) -> StorageService:
    return StorageService(redis=redis)


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="getHealth",
    summary="Service health and dependency diagnostic check",
    description="Verifies operational health of the service and downstream Redis connectivity.",
    responses={
        400: {"model": Error, "description": "Bad Request"},
        422: {"model": Error, "description": "Unprocessable Entity"},
        429: {"model": Error, "description": "Too Many Requests"},
        500: {"model": Error, "description": "Internal Server Error"},
    },
)
async def get_health(storage: StorageService = Depends(get_storage_service)) -> HealthResponse:
    redis_ok = await storage.ping()
    redis_status = "healthy" if redis_ok else "unreachable"
    overall_status = "ok" if redis_ok else "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.APP_VERSION,
        timestamp=datetime.now(UTC),
        dependencies={"redis": redis_status},
    )
