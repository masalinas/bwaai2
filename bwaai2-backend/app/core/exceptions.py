from enum import StrEnum
from typing import Any


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


class AppException(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class InvalidFileTypeError(AppException):
    def __init__(
        self,
        message: str = "Invalid file type. Only application/pdf is accepted.",
        details: Any = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.INVALID_FILE_TYPE,
            message=message,
            status_code=415,
            details=details,
        )


class FileTooLargeError(AppException):
    def __init__(
        self, message: str = "File exceeds maximum allowable size of 25MB.", details: Any = None
    ) -> None:
        super().__init__(
            code=ErrorCode.FILE_TOO_LARGE,
            message=message,
            status_code=413,
            details=details,
        )


class TooManyFilesError(AppException):
    def __init__(
        self,
        message: str = "Too many files. Maximum allowed per request is 10.",
        details: Any = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.TOO_MANY_FILES,
            message=message,
            status_code=413,
            details=details,
        )


class EmptyFileError(AppException):
    def __init__(
        self, message: str = "Uploaded file is empty (0 bytes).", details: Any = None
    ) -> None:
        super().__init__(
            code=ErrorCode.EMPTY_FILE,
            message=message,
            status_code=400,
            details=details,
        )


class EncryptedPDFError(AppException):
    def __init__(
        self,
        message: str = "The submitted PDF document is password-protected and cannot be read.",
        details: Any = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.ENCRYPTED_PDF,
            message=message,
            status_code=400,
            details=details,
        )


class DocumentNotFoundError(AppException):
    def __init__(self, message: str = "Document not found.", details: Any = None) -> None:
        super().__init__(
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message=message,
            status_code=404,
            details=details,
        )


class ParserUnavailableError(AppException):
    def __init__(
        self,
        message: str = "The requested parser service is temporarily unavailable.",
        details: Any = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.PARSER_UNAVAILABLE,
            message=message,
            status_code=500,
            details=details,
        )


class ParserFailedError(AppException):
    def __init__(
        self,
        message: str = "A fatal error occurred while executing the PDF parsing pipeline.",
        details: Any = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.PARSER_FAILED,
            message=message,
            status_code=500,
            details=details,
        )


class ParserRateLimitedError(AppException):
    def __init__(
        self, message: str = "Parser rate limit temporarily exceeded.", details: Any = None
    ) -> None:
        super().__init__(
            code=ErrorCode.PARSER_FAILED,
            message=message,
            status_code=429,
            details=details,
        )


class ParserTransientError(AppException):
    def __init__(
        self,
        message: str = "Parser service encountered a transient network or server error.",
        details: Any = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.PARSER_FAILED,
            message=message,
            status_code=503,
            details=details,
        )


class SummaryRateLimitedError(AppException):
    def __init__(
        self, message: str = "Summarization capacity temporarily exceeded.", details: Any = None
    ) -> None:
        super().__init__(
            code=ErrorCode.SUMMARY_RATE_LIMITED,
            message=message,
            status_code=429,
            details=details,
        )


class SummaryFailedError(AppException):
    def __init__(
        self, message: str = "Failed to generate document summary.", details: Any = None
    ) -> None:
        super().__init__(
            code=ErrorCode.SUMMARY_FAILED,
            message=message,
            status_code=500,
            details=details,
        )
