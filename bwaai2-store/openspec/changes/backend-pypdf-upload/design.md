# Design: Backend PyPDF Upload and Storage Service

## Context

The backend service is built using Python 3.12, FastAPI, and Redis 7. It implements the ingestion layer and query endpoints specified in `contracts/openapi.yaml`. In this multi-repo setup:
- `bwaai2-store` (the current repo) holds only OpenSpec specifications and OpenAPI contracts (`contracts/openapi.yaml`).
- `bwaai2-backend` (located at `../bwaai2-backend`) hosts all application code (`app/`), tests (`tests/`), Dockerfile, `docker-compose.yml`, and build tooling.

The API functions as an asynchronous producer: it accepts batch uploads, validates format and integrity, stores the raw files and metadata in Redis, enqueues discrete job descriptors into Redis Streams (`documents:jobs`), and immediately responds with HTTP 202 Accepted.

## Goals / Non-Goals

**Goals:**
- Implement all endpoints from `contracts/openapi.yaml` (`POST /documents`, `GET /documents`, `GET /documents/{document_id}`, `GET /documents/{document_id}/status`, `GET /health`) in `bwaai2-backend`.
- Streamed validation of uploaded files against size (25MB), batch count (10), MIME type, `%PDF-` magic bytes, non-zero length, and encryption.
- Robust Redis 7 data model using connection pooling initialized during FastAPI lifespan.
- Decoupled `Parser` abstraction with `PyPDFParser` executing off-thread via `asyncio.to_thread`.
- 100% contract compliance with `contracts/openapi.yaml`, verified by an automated OpenAPI parity test reading from `CONTRACT_PATH`.

**Non-Goals:**
- Running the Redis Streams consumer worker daemon in this change (workers will be implemented in a subsequent change).
- Multimodal LLM integration with Gemini or Mistral (requests specifying these parsers are validated but return `PARSER_UNAVAILABLE`).
- Long-term blob storage in S3/GCS.
- Modifying `contracts/openapi.yaml` or placing any backend code in `bwaai2-store`.

## Decisions

### 1. Multi-Repo Architecture & Contract Referencing
- **Decision**: Keep `bwaai2-store` strictly limited to OpenAPI contracts and OpenSpec changes. Place all application code, tests, and configuration directly in `../bwaai2-backend` with layout at root (`app/`, `tests/`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `Makefile`).
- **Rationale**: Clean separation of governance/contract source of truth from implementation codebases.
- **Contract Access**: The contract test in `bwaai2-backend` references the contract file via environment variable `CONTRACT_PATH` (defaulting to `../bwaai2-store/contracts/openapi.yaml`), preventing out-of-sync copies.

### 2. Redis Data Model
- **`doc:{id}` (Hash)**: Stores mutable metadata fields: `document_id`, `filename`, `parser`, `status`, `created_at`, `updated_at`, and `error` (JSON string when status is `failed`).
- **`doc:{id}:pages` (String / JSON)**: Stores extracted page records `[{"page_number": 1, "content": "...", "format": "text"}]` when status is `done`.
- **`doc:{id}:summary` (String)**: Stores the final consolidated summary (null in this change).
- **`doc:{id}:file` (Binary String with TTL)**: Holds the raw uploaded PDF bytes with a configurable expiration (`PDF_TTL_SECONDS`, default: 86,400 seconds / 24 hours).
- **`docs:index` (Sorted Set)**: Indexes all documents with `score = epoch_timestamp` and `member = document_id`. Enables cursor-based reverse-chronological pagination (`ZREVRANGEBYSCORE` / `ZREVRANGE`) without offset drift or table scans.

### 3. Why Parsing is Not in the Request Path
- PDF text extraction, OCR, and AI summarization are computationally intensive and non-deterministic in duration.
- Executing parsing synchronously within the upload request handler would cause HTTP gateway timeouts (typically 15–30s), tie up FastAPI worker concurrency, and make client uploads vulnerable to network drops.
- Offloading processing to Redis Streams (`documents:jobs`) ensures upload request latencies remain under 50ms regardless of PDF length or batch size.

### 4. Why Store PDF Bytes in Redis
- Storing temporary raw PDF bytes in Redis with an automated TTL eliminates external object storage dependencies (such as AWS S3 or MinIO) during early development and local development.
- Redis 7 handles binary strings up to 512MB effortlessly; storing 25MB PDFs in-memory provides sub-millisecond retrieval speeds for downstream worker processes.
- Redis Streams messages remain small and lightweight (passing only `{ "document_id": "...", "parser": "..." }`), preventing stream bloat while workers fetch raw bytes on-demand via `doc:{id}:file`.

### 5. Limits Chosen
- **Max File Size**: 25 MB (`26,214,400` bytes). Large enough to support complex corporate reports and publications, while bounding server memory consumption.
- **Max Batch Count**: 10 files per request. Prevents client abuse and excessive multipart buffer allocations in single HTTP transactions.
- **Query Pagination**: Default 20 items per page, maximum 100.
- **Polling Retry-After**: 3 seconds suggested backoff for client polling.

### 6. Pluggable Parser Interface & Off-Thread Execution
- A generic `Parser` abstract base class defines `async def parse(self, pdf_bytes: bytes) -> list[Page]`.
- `PyPDFParser` uses `pypdf.PdfReader` wrapped in `asyncio.to_thread`. Because PDF parsing in pure Python is CPU-bound, executing it in a thread pool prevents blocking the asyncio event loop.
- The upload handler validates the `parser` parameter. For `pypdf`, jobs are enqueued. For `gemini` and `mistral`, the API returns HTTP 500 with `PARSER_UNAVAILABLE` until their worker backends are implemented.

## Assumptions

1. **Router Mounting and Contract Path Parity**:
   - `contracts/openapi.yaml` defines server URL `/api/v1` with paths `/documents`, `/documents/{document_id}`, `/documents/{document_id}/status`, and `/health`.
   - FastAPI mounts routes at root `/` (matching the OpenAPI schema paths directly) and aliases them with prefix `/api/v1` (`include_in_schema=False`).
2. **Document Identifiers**:
   - Generated as `doc_<uuid4_hex>` (e.g., `doc_01j9a8b7c6d5e4f3a2b1c0d9e8`), fitting cleanly into standard URL path segments and Redis keys.
3. **Cursor Format**:
   - Opaque base64-encoded JSON payload containing `{"created_at": float_timestamp, "document_id": str}` for deterministic ordering.
4. **FastAPI Contract Exception Handling**:
   - Custom FastAPI exception handlers format all 4xx/5xx responses to match the contract's unified `Error` schema (`code`, `message`, `details`).

## Risks / Trade-offs

- **[Risk] High Redis memory consumption if many large files are uploaded simultaneously**  
  *Mitigation*: Configurable `PDF_TTL_SECONDS` expires files automatically. In production, Redis `maxmemory` and eviction policies prevent OOM crashes.
- **[Risk] Encrypted PDFs accepted before parsing**  
  *Mitigation*: Pre-flight inspection in the upload handler reads the PDF trailer using `PdfReader.is_encrypted` and rejects encrypted files immediately with `ENCRYPTED_PDF` (HTTP 400).
