import asyncio
import io
import random
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.core.config import settings
from app.core.exceptions import SummaryFailedError, SummaryRateLimitedError
from app.core.logging import logger


class GeminiService:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        concurrency: int | None = None,
        client: genai.Client | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self.concurrency = concurrency or settings.GEMINI_CONCURRENCY
        self.semaphore = asyncio.Semaphore(self.concurrency)
        self._client = client

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            # Instantiate with API key or default environment
            self._client = genai.Client(api_key=self.api_key or "DUMMY_KEY_FOR_MOCK")
        return self._client

    async def generate_content(
        self,
        contents: Any,
        config: types.GenerateContentConfig | None = None,
        model: str | None = None,
        max_retries: int = 3,
    ) -> types.GenerateContentResponse:
        target_model = model or self.model

        for attempt in range(1, max_retries + 1):
            async with self.semaphore:
                try:
                    logger.debug(
                        "Dispatching request to Gemini (%s, attempt %d)", target_model, attempt
                    )
                    response = await asyncio.wait_for(
                        self.client.aio.models.generate_content(
                            model=target_model,
                            contents=contents,
                            config=config,
                        ),
                        timeout=settings.GEMINI_TIMEOUT_SECONDS,
                    )
                    return response

                except APIError as ex:
                    # 429 / Quota exhausted -> rate limit
                    is_rate_limit = ex.code == 429 or "RESOURCE_EXHAUSTED" in str(ex)
                    is_transient = ex.code in (500, 502, 503, 504) or is_rate_limit

                    if is_rate_limit:
                        logger.warning(
                            "Gemini 429 Rate Limit (attempt %d/%d): %s", attempt, max_retries, ex
                        )
                        if attempt == max_retries:
                            raise SummaryRateLimitedError(
                                message="Gemini rate limit exceeded after maximum retries.",
                                details={"code": ex.code, "message": str(ex)},
                            ) from ex
                        # Exponential backoff with jitter
                        delay = min(30.0, (2**attempt) + random.uniform(0.5, 1.5))
                        await asyncio.sleep(delay)
                        continue

                    elif is_transient:
                        logger.warning(
                            "Gemini transient API error %d (attempt %d/%d): %s",
                            ex.code,
                            attempt,
                            max_retries,
                            ex,
                        )
                        if attempt == max_retries:
                            raise SummaryFailedError(
                                message=f"Gemini transient failure persisted: {str(ex)}",
                                details={"code": ex.code},
                            ) from ex
                        await asyncio.sleep(1.0 * attempt)
                        continue

                    else:
                        # Permanent client error (400, 403, prompt blocked, etc.)
                        logger.error("Gemini permanent API error %d: %s", ex.code, ex)
                        raise SummaryFailedError(
                            message=f"Gemini request failed: {str(ex)}",
                            details={"code": ex.code, "error": str(ex)},
                        ) from ex

                except TimeoutError as ex:
                    logger.warning("Gemini request timed out (attempt %d/%d)", attempt, max_retries)
                    if attempt == max_retries:
                        raise SummaryFailedError(
                            message="Gemini request timed out after maximum retries.",
                            details={"timeout_seconds": settings.GEMINI_TIMEOUT_SECONDS},
                        ) from ex
                    await asyncio.sleep(1.0 * attempt)
                    continue

                except Exception as ex:
                    # Non-API exceptions (e.g. rate limit custom)
                    if isinstance(ex, (SummaryRateLimitedError, SummaryFailedError)):
                        raise
                    logger.error(
                        "Unexpected error communicating with Gemini: %s", ex, exc_info=True
                    )
                    if attempt == max_retries:
                        raise SummaryFailedError(
                            message=f"Unexpected error communicating with Gemini: {str(ex)}"
                        ) from ex
                    await asyncio.sleep(1.0 * attempt)
                    continue

        raise SummaryFailedError(
            message="Gemini generation failed after exhausting all retry attempts."
        )

    async def upload_file(self, file_bytes: bytes, mime_type: str = "application/pdf") -> Any:
        """Uploads large files via Files API."""
        stream = io.BytesIO(file_bytes)
        return await self.client.aio.files.upload(file=stream, mime_type=mime_type)

    async def delete_file(self, file_name: str) -> None:
        """Cleans up uploaded file from Files API."""
        try:
            await self.client.aio.files.delete(name=file_name)
        except Exception as ex:
            logger.warning("Failed to delete remote file %s: %s", file_name, ex)
