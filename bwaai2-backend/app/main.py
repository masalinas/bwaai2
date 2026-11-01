from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.core.config import settings
from app.core.exceptions import AppException, ErrorCode
from app.core.logging import logger, setup_logging
from app.models.errors import Error
from app.services.storage import close_redis_pool, get_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging(debug=settings.DEBUG)
    logger.info("Initializing %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # Pre-warm Redis connection
    try:
        client = get_redis_client()
        await client.ping()
        logger.info("Connected to Redis successfully at %s", settings.REDIS_URL)
    except Exception as ex:
        logger.warning("Could not ping Redis on startup: %s", ex)

    yield

    # Clean shutdown
    await close_redis_pool()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="Async PDF Processing API",
    version=settings.APP_VERSION,
    description="Authoritative FastAPI implementation for Async PDF Processing API.",
    lifespan=lifespan,
    servers=[
        {"url": "/api/v1", "description": "Relative API path for local and gateway routing"},
        {
            "url": "https://api.pdfprocessor.internal/v1",
            "description": "Internal production gateway",
        },
    ],
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers mapping domain and runtime errors to contract Error schema
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=Error(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        ).model_dump(exclude_none=True),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {"msg": "Validation error"}
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=Error(
            code=ErrorCode.INVALID_FILE_TYPE,
            message=f"Validation failed: {first_error.get('msg', 'Invalid input')}",
            details=exc.errors(),
        ).model_dump(exclude_none=True),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled server exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=Error(
            code=ErrorCode.PARSER_FAILED,
            message="An unexpected server error occurred.",
            details={"error": str(exc)} if settings.DEBUG else None,
        ).model_dump(exclude_none=True),
    )


# Assemble routers: primary routes at root (matching OpenAPI schema paths)
# and alias under /api/v1
api_router = APIRouter()
api_router.include_router(documents_router)
api_router.include_router(health_router)

app.include_router(api_router)
app.include_router(api_router, prefix="/api/v1", include_in_schema=False)
