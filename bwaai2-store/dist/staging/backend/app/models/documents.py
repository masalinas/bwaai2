from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.errors import Error


class ParserType(StrEnum):
    pypdf = "pypdf"
    gemini = "gemini"
    mistral = "mistral"


class DocumentStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    summarizing = "summarizing"
    done = "done"
    failed = "failed"


class ContentFormat(StrEnum):
    text = "text"
    markdown = "markdown"


class DocumentUploadItem(BaseModel):
    document_id: str = Field(..., description="Unique document identifier.")
    filename: str = Field(..., description="Original file name provided during upload.")
    status: DocumentStatus = Field(..., description="Processing lifecycle status.")


class DocumentListItem(BaseModel):
    document_id: str = Field(..., description="Unique document identifier.")
    filename: str = Field(..., description="Original filename.")
    parser: ParserType = Field(..., description="Chosen parser type.")
    status: DocumentStatus = Field(..., description="Current processing status.")
    created_at: datetime = Field(
        ..., description="Timestamp when the document was received and enqueued."
    )
    updated_at: datetime = Field(..., description="Timestamp of the latest update.")


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem] = Field(
        default_factory=list, description="Array of document summary items."
    )
    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for the next page, or null if on the last page."
    )
    has_more: bool = Field(
        ..., description="Flag indicating whether additional items are available."
    )


class DocumentPage(BaseModel):
    page_number: int = Field(..., ge=1, description="1-indexed page sequence number.")
    content: str = Field(..., description="Extracted content for this page.")
    format: ContentFormat = Field(..., description="Format indicator (text or markdown).")


class DocumentDetailResponse(BaseModel):
    document_id: str = Field(..., description="Unique document identifier.")
    filename: str = Field(..., description="Original filename.")
    parser: ParserType = Field(..., description="Chosen parser type.")
    status: DocumentStatus = Field(..., description="Current processing status.")
    created_at: datetime = Field(..., description="Timestamp when the document was received.")
    updated_at: datetime = Field(..., description="Timestamp of the latest status transition.")
    pages: list[DocumentPage] | None = Field(
        default=None, description="Extracted page contents when done, or null."
    )
    summary: str | None = Field(
        default=None, description="Consolidated document summary when done, or null."
    )
    error: Error | None = Field(default=None, description="Error details if processing failed.")


class DocumentStatusResponse(BaseModel):
    document_id: str = Field(..., description="Unique document identifier.")
    status: DocumentStatus = Field(..., description="Current processing status.")
    created_at: datetime = Field(..., description="Timestamp when the document was received.")
    updated_at: datetime = Field(..., description="Timestamp of the latest status transition.")
    error: Error | None = Field(default=None, description="Error details if the status is failed.")
