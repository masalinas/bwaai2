import asyncio
import base64
import io
from typing import Any

from pypdf import PdfReader

from app.core.config import settings
from app.core.exceptions import (
    ParserFailedError,
    ParserRateLimitedError,
    ParserTransientError,
    ParserUnavailableError,
)
from app.core.logging import logger
from app.models.documents import ContentFormat, DocumentPage
from app.services.parsers.base import BaseParser

try:
    from mistralai import Mistral
except ImportError:
    try:
        from mistralai.client import Mistral
    except ImportError:
        Mistral = None  # type: ignore[assignment, misc]


class MistralParser(BaseParser):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        concurrency: int | None = None,
        timeout_seconds: int | None = None,
        inline_threshold_bytes: int | None = None,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.MISTRAL_API_KEY
        self.model = model or settings.MISTRAL_OCR_MODEL
        self.timeout_seconds = timeout_seconds or settings.MISTRAL_TIMEOUT_SECONDS
        self.inline_threshold_bytes = (
            inline_threshold_bytes or settings.MISTRAL_INLINE_THRESHOLD_BYTES
        )
        self.semaphore = asyncio.Semaphore(concurrency or settings.MISTRAL_CONCURRENCY)
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise ParserUnavailableError(
                message="Mistral parser is not configured: MISTRAL_API_KEY is not set.",
                details={"service": "mistral_parser"},
            )
        if Mistral is None:
            raise ParserUnavailableError(
                message="mistralai SDK is not installed.",
                details={"service": "mistral_parser"},
            )
        self._client = Mistral(api_key=self.api_key)
        return self._client

    @staticmethod
    def _get_pdf_page_count(pdf_bytes: bytes) -> int:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return len(reader.pages)

    async def parse(self, pdf_bytes: bytes) -> list[DocumentPage]:
        client = self._get_client()

        # 1. Establish ground truth page count via PyPDF
        try:
            expected_pages = await asyncio.to_thread(self._get_pdf_page_count, pdf_bytes)
        except Exception as ex:
            raise ParserFailedError(
                message=f"Failed to inspect PDF structure: {str(ex)}",
                details={"reason": "corrupt_pdf"},
            ) from ex

        # 2. Execute with 1-attempt retry on page count mismatch
        pages = await self._call_ocr_with_retry_on_mismatch(client, pdf_bytes, expected_pages)
        return pages

    async def _call_ocr_with_retry_on_mismatch(
        self, client: Any, pdf_bytes: bytes, expected_pages: int
    ) -> list[DocumentPage]:
        # Attempt 1
        pages = await self._execute_ocr_call(client, pdf_bytes)
        if len(pages) == expected_pages:
            return pages

        logger.warning(
            "Mistral OCR page count mismatch on attempt 1 (extracted: %d, expected: %d). Retrying once...",
            len(pages),
            expected_pages,
        )

        # Attempt 2
        pages = await self._execute_ocr_call(client, pdf_bytes)
        if len(pages) == expected_pages:
            logger.info("Mistral OCR retry succeeded with matching page count: %d", len(pages))
            return pages

        logger.error(
            "Mistral OCR persistent page count mismatch (extracted: %d, expected: %d)",
            len(pages),
            expected_pages,
        )
        raise ParserFailedError(
            message=f"Mistral OCR extracted {len(pages)} pages, but source PDF contains {expected_pages} pages.",
            details={"expected_pages": expected_pages, "extracted_pages": len(pages)},
        )

    async def _execute_ocr_call(self, client: Any, pdf_bytes: bytes) -> list[DocumentPage]:
        async with self.semaphore:
            try:
                if len(pdf_bytes) <= self.inline_threshold_bytes:
                    return await self._parse_inline(client, pdf_bytes)
                else:
                    return await self._parse_via_files_api(client, pdf_bytes)
            except (ParserFailedError, ParserRateLimitedError, ParserTransientError):
                raise
            except Exception as ex:
                self._classify_and_raise_error(ex)

    async def _parse_inline(self, client: Any, pdf_bytes: bytes) -> list[DocumentPage]:
        encoded = base64.b64encode(pdf_bytes).decode("utf-8")
        document = {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{encoded}",
        }

        async with asyncio.timeout(self.timeout_seconds):
            response = await client.ocr.process_async(
                model=self.model,
                document=document,
                include_image_base64=False,
            )

        return self._map_ocr_response(response)

    async def _parse_via_files_api(self, client: Any, pdf_bytes: bytes) -> list[DocumentPage]:
        logger.info(
            "PDF size (%d bytes) exceeds inline threshold (%d bytes); utilizing Mistral Files API",
            len(pdf_bytes),
            self.inline_threshold_bytes,
        )

        file_payload = {
            "file_name": "document.pdf",
            "content": pdf_bytes,
        }

        uploaded_file = await client.files.upload_async(file=file_payload, purpose="ocr")
        file_id = getattr(uploaded_file, "id", None) or uploaded_file.get("id")

        try:
            signed_url_resp = await client.files.get_signed_url_async(file_id=file_id)
            doc_url = getattr(signed_url_resp, "url", None) or signed_url_resp.get("url")

            document = {
                "type": "document_url",
                "document_url": doc_url,
            }

            async with asyncio.timeout(self.timeout_seconds):
                response = await client.ocr.process_async(
                    model=self.model,
                    document=document,
                    include_image_base64=False,
                )

            return self._map_ocr_response(response)

        finally:
            if file_id:
                try:
                    await client.files.delete_async(file_id=file_id)
                except Exception as ex:
                    logger.warning("Failed to delete temporary Mistral file %s: %s", file_id, ex)

    @staticmethod
    def _map_ocr_response(response: Any) -> list[DocumentPage]:
        pages_raw = getattr(response, "pages", None) or []
        parsed_pages: list[DocumentPage] = []

        for idx, page in enumerate(pages_raw):
            page_index = getattr(page, "index", None)
            page_num = (page_index + 1) if page_index is not None else (idx + 1)
            markdown_content = getattr(page, "markdown", "") or ""

            parsed_pages.append(
                DocumentPage(
                    page_number=page_num,
                    content=markdown_content,
                    format=ContentFormat.markdown,
                )
            )

        # Ensure ordered by page number
        parsed_pages.sort(key=lambda p: p.page_number)
        return parsed_pages

    def _classify_and_raise_error(self, ex: Exception) -> None:
        status_code = getattr(ex, "status_code", None)
        body = getattr(ex, "body", None)
        msg = getattr(ex, "message", None) or str(ex)

        if status_code == 429:
            logger.warning("Mistral OCR rate limit exceeded (HTTP 429): %s", body or msg)
            raise ParserRateLimitedError(
                message=f"Mistral OCR rate limit exceeded: {body or msg}",
                details={"status_code": 429, "body": body},
            ) from ex

        if status_code is not None and 500 <= status_code < 600:
            logger.warning("Mistral OCR server error (HTTP %d): %s", status_code, body or msg)
            raise ParserTransientError(
                message=f"Mistral OCR temporary server error ({status_code}): {body or msg}",
                details={"status_code": status_code, "body": body},
            ) from ex

        if status_code is not None and 400 <= status_code < 500:
            logger.error("Mistral OCR client error (HTTP %d): %s", status_code, body or msg)
            raise ParserFailedError(
                message=f"Mistral OCR rejected document ({status_code}): {body or msg}",
                details={"status_code": status_code, "body": body},
            ) from ex

        if isinstance(ex, TimeoutError):
            logger.warning("Mistral OCR request timed out after %ds", self.timeout_seconds)
            raise ParserTransientError(
                message=f"Mistral OCR request timed out after {self.timeout_seconds} seconds.",
                details={"timeout_seconds": self.timeout_seconds},
            ) from ex

        if isinstance(ex, ConnectionError):
            logger.warning("Mistral OCR network connection error: %s", ex)
            raise ParserTransientError(
                message=f"Mistral OCR connection error: {str(ex)}",
            ) from ex

        # Unexpected fatal error
        logger.error("Unexpected error in Mistral parser: %s", ex, exc_info=True)
        raise ParserFailedError(
            message=f"Mistral OCR failed with unexpected error: {str(ex)}",
        ) from ex
