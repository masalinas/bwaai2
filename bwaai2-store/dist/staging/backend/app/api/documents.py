import asyncio
import io
import uuid

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile, status
from pypdf import PdfReader
from redis.asyncio import Redis

from app.core import constants
from app.core.config import settings
from app.core.exceptions import (
    EmptyFileError,
    EncryptedPDFError,
    FileTooLargeError,
    InvalidFileTypeError,
    ParserUnavailableError,
    TooManyFilesError,
)
from app.core.logging import logger
from app.models.documents import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentStatusResponse,
    DocumentUploadItem,
    ParserType,
)
from app.models.errors import Error
from app.services.queue import QueueProducer
from app.services.storage import StorageService, get_redis_client

router = APIRouter(tags=["documents"])

COMMON_RESPONSES = {
    400: {"model": Error, "description": "Bad Request"},
    404: {"model": Error, "description": "Not Found"},
    413: {"model": Error, "description": "Payload Too Large"},
    415: {"model": Error, "description": "Unsupported Media Type"},
    422: {"model": Error, "description": "Unprocessable Entity"},
    429: {"model": Error, "description": "Too Many Requests"},
    500: {"model": Error, "description": "Internal Server Error"},
}


def get_storage_service(redis: Redis = Depends(get_redis_client)) -> StorageService:
    return StorageService(redis=redis)


def get_queue_producer(redis: Redis = Depends(get_redis_client)) -> QueueProducer:
    return QueueProducer(redis=redis)


def _is_pdf_encrypted(data: bytes) -> bool:
    try:
        reader = PdfReader(io.BytesIO(data))
        return bool(reader.is_encrypted)
    except Exception:
        # If reader fails before check, let parser handle or assume not encrypted
        return False


@router.post(
    "/documents",
    response_model=list[DocumentUploadItem],
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="uploadDocuments",
    summary="Upload and enqueue PDF documents for asynchronous processing",
    description="Accepts 1 to 10 PDF files via multipart/form-data with parser selection, returning 202 Accepted.",
    responses=COMMON_RESPONSES,
)
async def upload_documents(
    files: list[UploadFile] = File(
        ..., description="One or more PDF documents to parse and summarize."
    ),
    parser: ParserType = Form(default=ParserType.pypdf, description="Parser engine selection."),
    storage: StorageService = Depends(get_storage_service),
    queue: QueueProducer = Depends(get_queue_producer),
) -> list[DocumentUploadItem]:
    # 1. Validate file count
    if not files:
        raise EmptyFileError(message="No files provided in request.")

    if len(files) > settings.MAX_FILES_PER_REQUEST:
        raise TooManyFilesError(
            message=f"Request contains {len(files)} files; maximum batch size is {settings.MAX_FILES_PER_REQUEST} files.",
            details={"file_count": len(files), "max_allowed_files": settings.MAX_FILES_PER_REQUEST},
        )

    # 2. Check parser availability
    if parser == ParserType.mistral and not settings.MISTRAL_API_KEY:
        raise ParserUnavailableError(
            message="Mistral parser is not configured: MISTRAL_API_KEY is not set.",
            details={"service": "mistral_parser"},
        )

    # 3. Stream and validate each file
    validated_files: list[tuple[str, str, bytes]] = []
    chunk_size = 64 * 1024  # 64 KB chunks

    for file in files:
        filename = file.filename or "unnamed.pdf"

        # Content-type check
        if file.content_type != constants.ALLOWED_MIME_TYPE:
            raise InvalidFileTypeError(
                message=f"File '{filename}' has invalid content type '{file.content_type}'. Only '{constants.ALLOWED_MIME_TYPE}' is accepted.",
                details={
                    "filename": filename,
                    "received_content_type": file.content_type,
                    "expected_content_type": constants.ALLOWED_MIME_TYPE,
                },
            )

        # Streamed read with max size check
        chunks: list[bytes] = []
        total_size = 0

        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > settings.MAX_FILE_SIZE_BYTES:
                raise FileTooLargeError(
                    message=f"File '{filename}' exceeds maximum allowable size of 25MB.",
                    details={
                        "filename": filename,
                        "file_size_bytes": total_size,
                        "max_allowed_bytes": settings.MAX_FILE_SIZE_BYTES,
                    },
                )
            chunks.append(chunk)

        data = b"".join(chunks)

        # Empty file check
        if len(data) == 0:
            raise EmptyFileError(
                message=f"Uploaded file '{filename}' contains 0 bytes.",
                details={"filename": filename},
            )

        # Magic bytes check
        if not data.startswith(constants.PDF_MAGIC_BYTES):
            raise InvalidFileTypeError(
                message=f"File '{filename}' is not a valid PDF document (missing %PDF- signature).",
                details={"filename": filename},
            )

        # Encryption pre-flight check
        is_encrypted = await asyncio.to_thread(_is_pdf_encrypted, data)
        if is_encrypted:
            raise EncryptedPDFError(
                message=f"The submitted PDF document '{filename}' is password-protected and cannot be read.",
                details={"filename": filename},
            )

        doc_id = f"doc_{uuid.uuid4().hex[:26]}"
        validated_files.append((doc_id, filename, data))

    # 4. Persist and enqueue all validated files
    results: list[DocumentUploadItem] = []
    for doc_id, filename, data in validated_files:
        await storage.save_document(
            document_id=doc_id,
            filename=filename,
            parser=parser,
            pdf_bytes=data,
        )
        await queue.enqueue_document_job(document_id=doc_id, parser=parser)
        results.append(
            DocumentUploadItem(
                document_id=doc_id,
                filename=filename,
                status=DocumentUploadItem.model_fields[
                    "status"
                ].annotation.queued,  # DocumentStatus.queued
            )
        )

    logger.info("Accepted batch of %d documents with parser %s", len(results), parser.value)
    return results


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    operation_id="listDocuments",
    summary="List documents with pagination and status",
    description="Retrieves a paginated list of uploaded documents sorted chronologically.",
    responses=COMMON_RESPONSES,
)
async def list_documents(
    limit: int = Query(
        default=20, ge=1, le=100, description="Number of document records to return per page."
    ),
    cursor: str | None = Query(default=None, description="Opaque pagination cursor token."),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentListResponse:
    items, next_cursor, has_more = await storage.list_documents(limit=limit, cursor=cursor)
    return DocumentListResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetailResponse,
    operation_id="getDocument",
    summary="Retrieve full document details, parsed pages, and summary",
    description="Retrieves detailed information for a specific document, including pages and summary when available.",
    responses=COMMON_RESPONSES,
)
async def get_document(
    document_id: str = Path(..., description="Unique document identifier."),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentDetailResponse:
    return await storage.get_document_detail(document_id)


@router.get(
    "/documents/{document_id}/status",
    response_model=DocumentStatusResponse,
    operation_id="getDocumentStatus",
    summary="Lightweight status check for document progress polling",
    description="Lightweight endpoint designed for frequent client polling with Retry-After header.",
    responses=COMMON_RESPONSES,
)
async def get_document_status(
    response: Response,
    document_id: str = Path(..., description="Unique document identifier."),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentStatusResponse:
    status_resp = await storage.get_document_status(document_id)
    if status_resp.status in (
        status_resp.status.queued,
        status_resp.status.processing,
        status_resp.status.summarizing,
    ):
        response.headers[constants.RETRY_AFTER_HEADER] = str(settings.RETRY_AFTER_SECONDS)
    return status_resp
