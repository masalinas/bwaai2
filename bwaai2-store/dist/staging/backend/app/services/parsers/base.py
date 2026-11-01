from abc import ABC, abstractmethod

from app.models.documents import DocumentPage


class BaseParser(ABC):
    """Abstract interface for PDF parsers."""

    @abstractmethod
    async def parse(self, pdf_bytes: bytes) -> list[DocumentPage]:
        """Asynchronously extract structured pages from raw PDF binary bytes."""
        raise NotImplementedError
