# Proposal: OpenAPI 3.1 Contract for Async PDF Processing

## Why

The PDF processing system requires asynchronous document parsing and LLM summarization across distributed backend workers (Python 3.12 / FastAPI / Redis Streams) and a React frontend. Establishing a formal OpenAPI 3.1 contract provides a strict single source of truth to generate frontend TypeScript types, validate backend API schema conformance, and eliminate contract drift before writing application code.

## What Changes

This change defines the complete HTTP API interface for asynchronous PDF ingestion, status polling, paginated listing, result retrieval, and health monitoring.

### In Scope
- OpenAPI 3.1.0 contract definition at `contracts/openapi.yaml`.
- Detailed operation definitions for:
  - `POST /documents`: Batch multipart/form-data PDF upload with parser selection (`pypdf`, `gemini`, `mistral`), returning HTTP 202 Accepted.
  - `GET /documents`: Paginated list of uploaded documents with processing status, parser selection, and timestamps.
  - `GET /documents/{document_id}`: Full document payload including per-page parsed content (`text` or `markdown`), consolidated Gemini summary, or error diagnostics.
  - `GET /documents/{document_id}/status`: Lightweight status polling endpoint with optional `Retry-After` header.
  - `GET /health`: System liveness and dependency status endpoint.
- Reusable component schemas (`Error`, `ErrorCode`, `DocumentStatus`, `ParserType`, `ContentFormat`, `DocumentUploadItem`, `DocumentListItem`, `DocumentPage`, etc.) with comprehensive response mappings.
- Reusable HTTP error responses (400, 404, 413, 415, 422, 429, 500) bound to the unified `Error` schema.
- Explicit specification of request constraints (e.g., maximum 10 files per request, 25MB per file) using `x-` vendor extensions.
- OpenSpec requirements and scenarios for all endpoints.

### Out of Scope
- Backend FastAPI route implementation, models, and worker scripts.
- Redis 7 Streams message broker consumers, queue workers, and storage layers.
- Frontend React components, API hooks, and TypeScript code generation pipelines.
- Docker, docker-compose, and CI/CD deployment configuration.
- Automated integration or unit tests for runtime services.

## Capabilities

### New Capabilities
- `document-processing`: Asynchronous PDF document ingestion, status tracking, paginated listing, and parsed/summarized content retrieval.
- `system-health`: Operational readiness and liveness health check endpoint for the service.

### Modified Capabilities
None. This is a greenfield API contract definition.

## Impact
- **Contracts**: Establishes `contracts/openapi.yaml` as the authoritative interface definition.
- **Frontend**: Enables code generation tools (such as `openapi-typescript` or `orval`) to generate type-safe React client queries.
- **Backend**: Serves as the validation baseline for FastAPI route implementations and schema tests.
- **Dependencies**: No external runtime dependencies introduced; linting tools (`@redocly/cli`, `@stoplight/spectral-cli`) are used exclusively for contract verification.
