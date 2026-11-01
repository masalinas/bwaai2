import asyncio
import io

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError

from app.core.exceptions import EncryptedPDFError, InvalidFileTypeError, ParserFailedError
from app.core.logging import logger
from app.models.documents import ContentFormat, DocumentPage
from app.services.parsers.base import BaseParser


class PyPDFParser(BaseParser):
    """Parser implementation using PyPDF executing in a background thread."""

    async def parse(self, pdf_bytes: bytes) -> list[DocumentPage]:
        """Asynchronously parses PDF bytes using asyncio.to_thread to prevent event loop blocking."""
        return await asyncio.to_thread(self._sync_parse, pdf_bytes)

    def _sync_parse(self, pdf_bytes: bytes) -> list[DocumentPage]:
        try:
            stream = io.BytesIO(pdf_bytes)
            reader = PdfReader(stream)

            # Check if PDF is encrypted or password-protected
            if reader.is_encrypted:
                logger.warning("Attempted to parse encrypted PDF")
                raise EncryptedPDFError(
                    message="The submitted PDF document is password-protected and cannot be read.",
                    details={"encrypted": True},
                )

            pages: list[DocumentPage] = []
            for idx, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ""
                except FileNotDecryptedError as err:
                    raise EncryptedPDFError(
                        message="The submitted PDF document requires a password to decrypt.",
                        details={"page_number": idx + 1},
                    ) from err
                except Exception as ex:
                    logger.warning("Error extracting text from page %d: %s", idx + 1, ex)
                    text = ""

                pages.append(
                    DocumentPage(
                        page_number=idx + 1,
                        content=text,
                        format=ContentFormat.text,
                    )
                )

            return pages

        except (EncryptedPDFError, InvalidFileTypeError):
            raise
        except Exception as ex:
            logger.error("PyPDF parsing failed: %s", ex, exc_info=True)
            raise ParserFailedError(
                message=f"Failed to parse PDF document: {str(ex)}",
                details={"error": str(ex)},
            ) from ex
