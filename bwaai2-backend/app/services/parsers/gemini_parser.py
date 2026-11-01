import asyncio
import io
import json

from google.genai import types
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app.core.exceptions import EncryptedPDFError, ParserFailedError, ParserUnavailableError
from app.core.logging import logger
from app.models.documents import ContentFormat, DocumentPage
from app.services.gemini import GeminiService
from app.services.parsers.base import BaseParser

INLINE_DATA_THRESHOLD_BYTES = 10 * 1024 * 1024  # 10 MB


class GeminiPageItem(BaseModel):
    page_number: int = Field(..., description="1-indexed sequence number of the page.")
    markdown: str = Field(..., description="High-fidelity markdown extracted from this page.")


class GeminiPagesPayload(BaseModel):
    pages: list[GeminiPageItem] = Field(..., description="List of all extracted pages.")


def _get_page_count_and_verify(pdf_bytes: bytes) -> int:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if reader.is_encrypted:
        raise EncryptedPDFError(
            message="The submitted PDF document is password-protected and cannot be read.",
            details={"encrypted": True},
        )
    return len(reader.pages)


class GeminiParser(BaseParser):
    def __init__(self, gemini_service: GeminiService | None = None) -> None:
        self.gemini_service = gemini_service or GeminiService()

    async def parse(self, pdf_bytes: bytes) -> list[DocumentPage]:
        if type(self.gemini_service) is GeminiService and not self.gemini_service.api_key:
            raise ParserUnavailableError(
                message="Gemini parser is not configured: GEMINI_API_KEY is not set.",
                details={"service": "gemini_parser"},
            )

        # 1. Establish ground-truth page count via PyPDF
        expected_page_count = await asyncio.to_thread(_get_page_count_and_verify, pdf_bytes)

        prompt = (
            f"You are an expert document parser. Carefully extract all content from this {expected_page_count}-page PDF. "
            f"For each page from 1 to {expected_page_count}, convert all text, headings, tables, and lists into clean, "
            f"structured Markdown. Return structured JSON matching the provided schema with exactly {expected_page_count} pages."
        )

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiPagesPayload,
            temperature=0.1,
        )

        # 2. Prepare payload (inline vs. Files API)
        is_inline = len(pdf_bytes) <= INLINE_DATA_THRESHOLD_BYTES
        uploaded_file = None

        try:
            if is_inline:
                part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
                contents = [part, prompt]
            else:
                logger.info(
                    "PDF size %d bytes > 10MB threshold; uploading via Files API", len(pdf_bytes)
                )
                uploaded_file = await self.gemini_service.upload_file(
                    pdf_bytes, mime_type="application/pdf"
                )
                contents = [uploaded_file, prompt]

            # 3. First parsing attempt
            pages_payload = await self._call_and_parse(contents, config)

            # 4. Verify page count; retry once if mismatch
            if len(pages_payload.pages) != expected_page_count:
                logger.warning(
                    "Page count mismatch on attempt 1: expected %d, got %d. Retrying once...",
                    expected_page_count,
                    len(pages_payload.pages),
                )
                retry_prompt = (
                    f"Warning: previous attempt returned {len(pages_payload.pages)} pages instead of {expected_page_count}. "
                    f"Please re-extract and ensure exactly {expected_page_count} pages are present in the 'pages' array."
                )
                retry_contents = [contents[0], retry_prompt]
                pages_payload = await self._call_and_parse(retry_contents, config)

                if len(pages_payload.pages) != expected_page_count:
                    raise ParserFailedError(
                        message=f"Gemini parsed {len(pages_payload.pages)} pages, but document has {expected_page_count} pages.",
                        details={
                            "expected_pages": expected_page_count,
                            "received_pages": len(pages_payload.pages),
                        },
                    )

            # 5. Map to DocumentPage instances
            return [
                DocumentPage(
                    page_number=p.page_number,
                    content=p.markdown,
                    format=ContentFormat.markdown,
                )
                for p in sorted(pages_payload.pages, key=lambda x: x.page_number)
            ]

        finally:
            if uploaded_file is not None and hasattr(uploaded_file, "name"):
                await self.gemini_service.delete_file(uploaded_file.name)

    async def _call_and_parse(
        self, contents: list, config: types.GenerateContentConfig
    ) -> GeminiPagesPayload:
        response = await self.gemini_service.generate_content(contents=contents, config=config)
        text = response.text or ""
        try:
            data = json.loads(text)
            return GeminiPagesPayload.model_validate(data)
        except Exception as ex:
            logger.error(
                "Failed to parse Gemini structured JSON output: %s (raw: %s)", ex, text[:200]
            )
            raise ParserFailedError(
                message=f"Invalid structured JSON response from Gemini: {str(ex)}",
                details={"raw_response": text[:500]},
            ) from ex
