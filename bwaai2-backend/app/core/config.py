from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Async PDF Processing API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    PDF_TTL_SECONDS: int = 86400  # 24 hours

    # Validation Limits
    MAX_FILE_SIZE_BYTES: int = 26_214_400  # 25 MB
    MAX_FILES_PER_REQUEST: int = 10
    DEFAULT_PAGE_LIMIT: int = 20
    MAX_PAGE_LIMIT: int = 100
    RETRY_AFTER_SECONDS: int = 3

    # Worker Configuration
    WORKER_CONCURRENCY: int = 5
    WORKER_BLOCK_MS: int = 2000
    WORKER_BATCH_SIZE: int = 10
    MAX_ATTEMPTS: int = 3
    CLAIM_IDLE_MS: int = 60000
    CLAIM_BATCH_SIZE: int = 10
    AUTOCLAIM_INTERVAL_SECONDS: int = 10
    HEARTBEAT_INTERVAL_SECONDS: int = 10
    SHUTDOWN_TIMEOUT_SECONDS: int = 15

    # Gemini & Summarization Configuration
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_CONCURRENCY: int = 2
    GEMINI_TIMEOUT_SECONDS: int = 60
    SUMMARY_MAX_INPUT_CHARS: int = 100_000

    # Mistral OCR Configuration
    MISTRAL_API_KEY: str = ""
    MISTRAL_OCR_MODEL: str = "mistral-ocr-latest"
    MISTRAL_CONCURRENCY: int = 2
    MISTRAL_TIMEOUT_SECONDS: int = 60
    MISTRAL_INLINE_THRESHOLD_BYTES: int = 10 * 1024 * 1024  # 10 MB

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
