from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    EMPTY_FILE = "EMPTY_FILE"
    TOO_MANY_FILES = "TOO_MANY_FILES"
    PARSER_UNAVAILABLE = "PARSER_UNAVAILABLE"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    PARSER_FAILED = "PARSER_FAILED"
    SUMMARY_RATE_LIMITED = "SUMMARY_RATE_LIMITED"
    SUMMARY_FAILED = "SUMMARY_FAILED"


class Error(BaseModel):
    code: ErrorCode = Field(
        ..., description="Machine-readable error code identifying the failure condition."
    )
    message: str = Field(..., description="Human-readable error description.")
    details: Any = Field(default=None, description="Optional contextual or validation metadata.")
