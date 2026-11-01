# Proposal: Backend PyPDF Upload and Storage Service

## Why

With the `api-contract` OpenAPI 3.1 specification established, the system requires the backend implementation. Operating in a multi-repo architecture where specs reside in `bwaai2-store` and implementation lives in `bwaai2-backend`, this change delivers the core FastAPI service, Redis 7 persistence, asynchronous Streams job producer, and a pluggable `Parser` abstraction with CPU-offloaded PyPDF extraction.

## What Changes

This change implements the backend API under `bwaai2-backend` adhering strictly to `contracts/openapi.yaml` without modifying the contract:

- **Multi-Repo Architecture**:
  - `bwaai2-store` maintains specifications and OpenAPI contract only.
  - `bwaai2-backend` hosts all application code (`app/`), tests (`tests/`), Dockerfile, `docker-compose.yml`, and `Makefile`.
- **FastAPI Endpoints**:
  - `POST /documents`: Batch multipart PDF upload validation, Redis metadata and binary storage, Redis Streams job publishing, and immediate `202 Accepted` response.
  - `GET /documents`: Paginated document listing via Redis sorted sets with cursor pagination (`limit`, `cursor`).
  - `GET /documents/{document_id}`: Document detail retrieval including parsed pages, summary, or error diagnostics.
  - `GET /documents/{document_id}/status`: Polling endpoint with HTTP `Retry-After: 3` header.
  - `GET /health`: Health check probing Redis connectivity.
- **Upload Validation & Error Handling**:
  - Validation of content-type (`application/pdf`), header magic bytes (`%PDF-`), non-zero file length, maximum file size (25MB), batch count (10), and encryption detection.
  - Unified `Error` response mapping domain exceptions to contract error codes (`INVALID_FILE_TYPE`, `FILE_TOO_LARGE`, `ENCRYPTED_PDF`, `EMPTY_FILE`, `TOO_MANY_FILES`, `PARSER_UNAVAILABLE`, `DOCUMENT_NOT_FOUND`).
- **Redis 7 Storage & Queue**:
  - Async `redis.asyncio` connection pool created in FastAPI lifespan.
  - Hash storage for `doc:{id}`, sorted set `docs:index`, raw PDF binary key `doc:{id}:file` with configurable TTL, and stream publishing to `documents:jobs`.
- **PyPDF Parser Engine**:
  - `Parser` interface with `PyPDFParser` executing off-thread via `asyncio.to_thread`.
  - Parsers `gemini` and `mistral` are recognized by validation but return `PARSER_UNAVAILABLE`.
- **Containerization & Tooling**:
  - `Dockerfile` and `docker-compose.yml` with `api` and `redis` services.
  - `Makefile` with `up`, `test`, and `lint` targets, and Ruff linting rules.
- **Testing**:
  - Async test suite using `pytest`, `httpx`, and `fakeredis`.
  - Contract check comparing FastAPI's generated OpenAPI against `contracts/openapi.yaml`.

### In Scope
- FastAPI application and endpoints matching `contracts/openapi.yaml`.
- Redis storage service and Redis Streams producer.
- `Parser` abstraction and `PyPDFParser` service with unit tests.
- Backend test suite, Dockerfile, and docker-compose setup in `bwaai2-backend`.

### Out of Scope
- Redis Streams background consumer/worker daemon.
- External Gemini and Mistral multimodal API integrations.
- Gemini document summarization execution (summary remains null).
- React frontend implementation.

## Capabilities

### New Capabilities
- `document-ingestion`: Multipart PDF upload validation (type, magic bytes, size, encryption), document metadata creation, Redis storage, and Redis Streams queueing (`POST /documents`).
- `document-query`: Document collection listing with cursor pagination (`GET /documents`), detailed document result retrieval (`GET /documents/{document_id}`), and lightweight polling (`GET /documents/{document_id}/status`).
- `pdf-parser-service`: PyPDF-based parser engine adhering to the `Parser` interface, operating off the event loop via `asyncio.to_thread`.
- `health-monitoring`: Service health and dependency diagnostic endpoint (`GET /health`).

### Modified Capabilities
None.

## Impact
- **bwaai2-store**: OpenSpec change tracking and contract compliance verification; no application code is added to the store.
- **bwaai2-backend**: Receives all backend service code, models, tests, Dockerfiles, and automation scripts.
