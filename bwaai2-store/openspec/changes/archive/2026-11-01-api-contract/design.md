# Design: OpenAPI 3.1 Contract for Async PDF Processing

## Context

The system processes PDF documents asynchronously using a backend stack composed of Python 3.12, FastAPI, and Redis 7 (leveraging Redis Streams as the durable task queue), paired with a React frontend. PDF parsing is compute-intensive and can involve external multimodal LLM inference (Gemini, Mistral) followed by a final Gemini summarization step. 

The OpenAPI 3.1 specification serves as the formal contract between frontend and backend teams. The frontend generates TypeScript types directly from the schema, while the backend validates its runtime FastAPI models against it.

## Goals / Non-Goals

**Goals:**
- Provide a clear, robust OpenAPI 3.1.0 contract specifying all request structures, response formats, HTTP status codes, headers, and error models.
- Support batch uploads (1..N files) with parser selection (`pypdf`, `gemini`, `mistral`).
- Support asynchronous job tracking through a dedicated polling endpoint with `Retry-After` backoff hints.
- Define a single unified `Error` schema used across all 4xx and 5xx responses with well-defined error codes.
- Ensure 100% compliance with OpenAPI 3.1 standards and zero linting warnings across Redocly and Spectral.

**Non-Goals:**
- Implementing application code, database migrations, or worker daemons.
- Configuring Redis consumer groups or Stream acknowledgment policies.
- Defining real-time bidirectional streaming protocols (e.g., WebSockets, SSE).
- Implementing authentication or authorization flows (to be added in a future security change).

## Decisions

### 1. Polling vs. Server-Sent Events (SSE) / WebSockets
- **Decision**: Use HTTP polling with a dedicated lightweight status endpoint (`GET /documents/{document_id}/status`) augmented by the HTTP `Retry-After` header, rather than persistent SSE or WebSocket connections.
- **Rationale**:
  - SSE and WebSockets require stateful connection persistence across ingress proxies, load balancers, and serverless/container scaling layers, leading to socket exhaustion and reconnection complexity.
  - In a PDF processing pipeline where jobs typically take between 2 and 30 seconds, short-interval HTTP polling (every 2–5 seconds) is lightweight, highly reliable, trivially retryable by React query hooks (`useQuery` with `refetchInterval`), and cacheable.
  - Avoids complexity in the React client and simplifies backend horizontal scaling.
- **Alternatives Considered**:
  - *Server-Sent Events (SSE)*: Cleaner event push, but complicates edge load balancing, proxy buffering, and reconnection state management.
  - *WebSockets*: Overkill for a unidirectional notification flow where the client only needs to know when a background job has transitioned to `done` or `failed`.

### 2. Immediate HTTP 202 Accepted for Ingestion
- **Decision**: Return HTTP 202 Accepted immediately upon receiving and validating the upload request at `POST /documents`.
- **Rationale**:
  - Uploading and parsing multiple PDF files via OCR or multimodal LLMs cannot be completed within standard HTTP request timeout windows (typically 15–30 seconds for gateways).
  - Returning 202 Accepted with a list of generated document IDs allows the client to immediately track the progress of each document without keeping an open multipart request.
- **Alternatives Considered**:
  - *Synchronous 200 OK*: Guarantees HTTP gateway timeouts on multi-page or batch PDF submissions.

### 3. Per-File Jobs in Queue
- **Decision**: Decompose multi-file batch uploads into discrete, independent worker jobs (one per file) in Redis Streams, returning individual `document_id` records in the 202 response.
- **Rationale**:
  - Isolation of failure: If one PDF in a batch is encrypted, corrupted, or triggers rate limits, the other documents can still succeed independently.
  - Parallel processing: Independent worker nodes can process separate files from the same upload concurrently.
  - Granular progress: The client UI can display per-file progress bars and results rather than waiting for the slowest file in a batch.
- **Alternatives Considered**:
  - *Single composite batch job*: A single failure would fail the entire batch or require complex partial-batch state machines.

### 4. Dedicated Lightweight Status Polling Endpoint
- **Decision**: Expose `GET /documents/{document_id}/status` separately from `GET /documents/{document_id}`.
- **Rationale**:
  - Extracted PDF content (pages array) and summaries can be several megabytes in size for large documents. Repeatedly transferring full document contents during polling wastes client and server bandwidth and increases serialization latency.
  - The status endpoint transfers only a few dozen bytes (`document_id`, `status`, timestamps, and optional error info) and supplies an HTTP `Retry-After` header to guide client backoff.
  - Once the status reaches `done`, the client makes a single fetch to `GET /documents/{document_id}` for the full payload.
- **Alternatives Considered**:
  - *Polling the full GET /documents/{document_id}*: High network overhead and redundant serialization on every poll interval.

### 5. Unified Error Schema Across All 4xx and 5xx Responses
- **Decision**: Standardize all error responses to a single reusable schema `Error` containing `code` (an enum of 9 specific error codes), `message` (human-readable string), and optional `details` (structured contextual metadata).
- **Rationale**:
  - Frontend error-handling utilities and React UI banners can rely on a consistent response envelope rather than custom shapes per endpoint.
  - The enum `ErrorCode` (`INVALID_FILE_TYPE`, `FILE_TOO_LARGE`, `ENCRYPTED_PDF`, `EMPTY_FILE`, `TOO_MANY_FILES`, `PARSER_UNAVAILABLE`, `DOCUMENT_NOT_FOUND`, `PARSER_FAILED`, `SUMMARY_RATE_LIMITED`) maps directly to domain errors across both API gateway and async worker stages.
- **Alternatives Considered**:
  - *FastAPI default validation errors (`{ "detail": [...] }`)*: Inconsistent with business domain errors and awkward for client discrimination without bespoke type guards.

## Assumptions

1. **Form-Data Parameter Naming**:
   - The multipart form property is named `files` (typed as `array` of binary items in OpenAPI 3.1). In the client documentation and form submissions, this corresponds to appending multiple files under the key `files` (or `files[]` depending on client library serialization).
2. **Batch Upload Limits**:
   - Maximum files per request: 10 files (annotated via `x-max-files-per-request: 10`).
   - Maximum file size per PDF: 25 MB (26,214,400 bytes, annotated via `x-max-file-size-bytes: 26214400`).
   - Allowed MIME type: strictly `application/pdf`.
3. **Parser-Specific Output Formatting**:
   - `pypdf`: Produces plain text per page (`format: "text"`).
   - `gemini`: Produces Markdown per page (`format: "markdown"`).
   - `mistral`: Produces Markdown per page (`format: "markdown"`).
4. **Summarization Granularity**:
   - Regardless of the parser selected, exactly one consolidated summary is generated per document using the Gemini model across all extracted pages.
5. **Pagination**:
   - `GET /documents` uses cursor-based pagination with `limit` (default: 20, minimum: 1, maximum: 100) and an opaque `cursor` query parameter. The response provides `next_cursor` (null if no further records) and `has_more` boolean.
6. **Polling Backoff**:
   - The default recommended poll interval is 3 seconds, returned via the standard HTTP `Retry-After: 3` header on `GET /documents/{document_id}/status` when status is `queued` or `processing`.
7. **HTTP Status Codes Coverage**:
   - Every operation specifies its applicable success code (200 or 202) and standard client/server error codes:
     - 400 Bad Request: Malformed inputs, empty file uploads, corrupted parameters.
     - 404 Not Found: Resource not found for document lookups.
     - 413 Payload Too Large: Upload exceeding file size or file count limits.
     - 415 Unsupported Media Type: Non-PDF files submitted.
     - 422 Unprocessable Entity: Schema validation failure.
     - 429 Too Many Requests: Rate limiting (e.g. client throttling or downstream LLM rate limiting).
     - 500 Internal Server Error: Worker unavailability or unexpected server errors.

## Risks / Trade-offs

- **[Risk] High polling traffic under heavy concurrent user load**  
  *Mitigation*: The lightweight `/status` endpoint minimizes response payloads, and the `Retry-After` header enables exponential backoff in client polling logic.
- **[Risk] External LLM API rate limits (`SUMMARY_RATE_LIMITED`) during summarization**  
  *Mitigation*: Document state is marked as `failed` with code `SUMMARY_RATE_LIMITED` and detailed retry hints, or queued for worker-level exponential backoff retry.
- **[Risk] Huge multi-hundred-page PDFs causing memory spikes on result retrieval**  
  *Mitigation*: Maximum upload file size is capped at 25MB. Page contents are extracted per-page to allow future per-page streaming or pagination if needed.
