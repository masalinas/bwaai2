# pdf-processor Specification

## Purpose
Comprehensive specification for the asynchronous PDF processing system (BWAAI2), covering OpenAPI 3.1 contract definitions, FastAPI document ingestion and cursor-paginated queries, Redis Streams worker queue orchestration, multi-engine parsers (PyPDF, Google Gemini 3.8 Flash, Mistral OCR), resumable two-stage pipelines, dead-letter failure recovery, React single-page frontend application, and containerized Docker Compose packaging.

## Requirements

### Requirement: Single-Archive Delivery Packaging
The delivery packaging script `delivery/scripts/package.sh` SHALL assemble the entire project into a self-contained archive at `dist/bwaai-pdf-processor.zip` containing `docker-compose.yml`, `.env.example`, `README.md`, `Makefile`, `contracts/`, `openspec/`, `samples/`, `scripts/`, `backend/`, and `frontend/`, excluding all `.venv`, `node_modules`, `.git`, `.env`, and build caches.

#### Scenario: Secret and .env leakage rejection
- **WHEN** `package.sh` encounters a `.env` file or files containing private credentials in the staging directory
- **THEN** it immediately halts with a non-zero exit status and does not generate the zip archive

#### Scenario: Clean packaging success
- **WHEN** `package.sh` is executed on clean repositories
- **THEN** it outputs `dist/staging/` and `dist/bwaai-pdf-processor.zip` and prints archive size and file statistics

### Requirement: Root Docker Compose Orchestration
The root `docker-compose.yml` SHALL orchestrate `redis`, `api`, `worker`, and `frontend` on a single internal bridge network without external network dependencies, configuring `condition: service_healthy` across dependencies, reasonable resource bounds, and log rotation.

#### Scenario: Service health readiness ordering
- **WHEN** `docker compose up --build -d` is executed
- **THEN** `redis` becomes healthy before `api` and `worker` start, and `api` becomes healthy before `frontend` starts

#### Scenario: Dynamic worker scaling
- **WHEN** `docker compose up --scale worker=3 -d` is executed
- **THEN** 3 worker instances register unique consumer names on the consumer group without container name collisions or port conflicts

### Requirement: Redis Persistence and Eviction Safety
The Redis service SHALL run with `--appendonly yes` writing to a named Docker volume `redis_data` and `--maxmemory-policy noeviction`.

#### Scenario: Redis restart with queued jobs
- **WHEN** Redis restarts while jobs are in `documents:jobs`
- **THEN** queued jobs persist in AOF storage and are processed to completion after restart

### Requirement: Nginx Reverse Proxy Limits
The frontend Nginx container SHALL proxy `/api/` to the API service with `client_max_body_size` set to at least 300MB and proxy timeouts of at least 120 seconds, exposing a `/healthz` endpoint for container health probes.

#### Scenario: Batch upload of 10 files
- **WHEN** a client uploads a 10-file batch of PDF documents totaling over 100MB
- **THEN** Nginx does not reject the request with HTTP 413, proxying it to FastAPI for contract validation

### Requirement: Cross-Layout Contract Path Resolution
The backend contract parity test and the frontend API type generator SHALL resolve the contract path using the fallback sequence: `CONTRACT_PATH` env var -> `../contracts/openapi.yaml` (zip layout) -> `../bwaai2-store/contracts/openapi.yaml` (development layout).

#### Scenario: Execution inside zip layout
- **WHEN** tests or type generation run inside the extracted zip directory where `../contracts/openapi.yaml` exists
- **THEN** the contract resolves successfully without requiring `CONTRACT_PATH` to be set

### Requirement: Graceful Operation Without LLM API Keys
The stack SHALL start up and pass all health checks when `GEMINI_API_KEY` and `MISTRAL_API_KEY` are empty. PyPDF uploads SHALL parse successfully, while Gemini and Mistral requests SHALL return clear `PARSER_UNAVAILABLE` or `SUMMARY_FAILED` errors instead of crashing.

#### Scenario: PyPDF upload without API keys
- **WHEN** a document is uploaded with `parser=pypdf` on a stack with empty API keys
- **THEN** pages are parsed and stored in Redis, and summarization reports a configuration requirement error without crashing the worker

### Requirement: Service Health Inspection
The API SHALL provide a health check endpoint at `GET /health` under the system tag, returning the operational status of the service and its dependencies, current application version, and the server timestamp.

#### Scenario: Service is fully operational
- **WHEN** a client or orchestrator issues a `GET /health` request while all subsystems are functioning
- **THEN** the server returns HTTP 200 OK with status "ok", application version, and ISO-8601 timestamp

#### Scenario: Service encounters internal failure
- **WHEN** an unrecoverable failure occurs within the health inspection check
- **THEN** the server returns HTTP 500 Internal Server Error conforming to the standard Error response schema

### Requirement: Service and Dependency Health Inspection
The API SHALL expose `GET /health` under the system tag, executing a Redis ping check and returning the operational health status, version string, and ISO-8601 timestamp.

#### Scenario: All systems operational
- **WHEN** a client issues `GET /health` and Redis responds successfully to ping
- **THEN** the server returns HTTP 200 with status "ok", version "1.0.0", and dependency redis marked "healthy"

#### Scenario: Redis connection failure
- **WHEN** Redis is unreachable or fails to respond to ping
- **THEN** the server reports degraded status or returns HTTP 500 conforming to the unified Error schema

### Requirement: Batch Document Submission
The API SHALL accept batch uploads of 1 to 10 PDF documents via multipart/form-data at `POST /documents`, validate file types and payload sizes, enqueue independent worker jobs, and immediately return HTTP 202 Accepted with a list of generated document identifiers and initial queued statuses.

#### Scenario: Successful batch upload
- **WHEN** a client submits a valid multipart/form-data request with two PDF files and parser set to "pypdf"
- **THEN** the server returns HTTP 202 Accepted with a JSON array containing two document records having unique IDs, filenames, and status "queued"

#### Scenario: Invalid file media type rejected
- **WHEN** a client uploads a file with a non-PDF MIME type such as "image/png"
- **THEN** the server rejects the request with HTTP 415 Unsupported Media Type and error code "INVALID_FILE_TYPE"

#### Scenario: File exceeds maximum allowed size
- **WHEN** a client uploads a PDF exceeding the configured limit of 25 megabytes
- **THEN** the server returns HTTP 413 Payload Too Large with error code "FILE_TOO_LARGE"

#### Scenario: Batch exceeds maximum file count
- **WHEN** a client uploads more than 10 PDF files in a single request
- **THEN** the server returns HTTP 413 Payload Too Large with error code "TOO_MANY_FILES"

#### Scenario: Zero byte empty file submitted
- **WHEN** a client uploads a file with 0 bytes
- **THEN** the server returns HTTP 400 Bad Request with error code "EMPTY_FILE"

### Requirement: Paginated Document Listing
The API SHALL allow clients to list previously submitted documents via `GET /documents`, returning document identifiers, original filenames, chosen parsers, current statuses, and creation/update timestamps, ordered chronologically with cursor-based pagination.

#### Scenario: First page list query
- **WHEN** a client issues a `GET /documents` request with limit 10 and no cursor
- **THEN** the server returns HTTP 200 OK with up to 10 document items, a pagination cursor for subsequent items, and has_more indicator

#### Scenario: Subsequent page query with cursor
- **WHEN** a client issues a `GET /documents` request supplying a valid next_cursor token
- **THEN** the server returns HTTP 200 OK with the next batch of document items starting immediately after the cursor

#### Scenario: Invalid cursor parameter provided
- **WHEN** a client issues a `GET /documents` request with an unparseable or expired cursor string
- **THEN** the server returns HTTP 400 Bad Request with error code "DOCUMENT_NOT_FOUND" or a validation error

### Requirement: Complete Document Result Retrieval
The API SHALL provide full document details at `GET /documents/{document_id}`, returning processing metadata, and upon completion ("done"), an array of page objects with extracted content and format ("text" or "markdown"), plus a unified Gemini summary. If failed, it MUST return error diagnostics.

#### Scenario: Successful retrieval of completed document
- **WHEN** a client requests a document whose processing status is "done"
- **THEN** the server returns HTTP 200 OK containing document metadata, an ordered pages array with page numbers and text/markdown content, and the Gemini summary string

#### Scenario: Retrieval of failed document
- **WHEN** a client requests a document whose processing status is "failed"
- **THEN** the server returns HTTP 200 OK containing the failure status and an error object detailing the failure code and message

#### Scenario: Requesting non-existent document ID
- **WHEN** a client requests a document ID that does not exist in the system
- **THEN** the server returns HTTP 404 Not Found with error code "DOCUMENT_NOT_FOUND"

### Requirement: Document Processing Status Polling
The API SHALL expose a lightweight status endpoint at `GET /documents/{document_id}/status` returning only the current lifecycle status, timestamps, and optional error information, supporting an HTTP `Retry-After` header when processing is incomplete.

#### Scenario: Polling document in queued or processing state
- **WHEN** a client requests status for a document that is currently "queued" or "processing"
- **THEN** the server returns HTTP 200 OK with current status and an optional `Retry-After` response header recommending the polling backoff duration

#### Scenario: Polling document in terminal done state
- **WHEN** a client requests status for a document that has completed processing
- **THEN** the server returns HTTP 200 OK with status "done" and no Retry-After header

#### Scenario: Polling non-existent document ID
- **WHEN** a client requests status for a document ID that does not exist
- **THEN** the server returns HTTP 404 Not Found with error code "DOCUMENT_NOT_FOUND"

### Requirement: Standardized Error Representation
Every client and server error response (HTTP 4xx and 5xx) returned by the API SHALL adhere to a unified error schema containing a machine-readable error code enum, a descriptive human-readable message, and optional structured error details.

#### Scenario: Validation failure adheres to error schema
- **WHEN** a client submits a malformed parameter or payload
- **THEN** the server responds with HTTP 422 Unprocessable Entity containing "code", "message", and "details"

#### Scenario: Parser worker unavailability
- **WHEN** an external parser service or backend worker cluster is unavailable
- **THEN** the server responds with HTTP 500 Internal Server Error containing error code "PARSER_UNAVAILABLE"

### Requirement: Multipart PDF Batch Upload
The API SHALL accept multipart/form-data requests at `POST /documents` containing 1 to 10 files and an optional parser parameter, returning HTTP 202 Accepted with a list of enqueued document descriptors upon successful validation.

#### Scenario: Valid single PDF upload
- **WHEN** a client posts a valid unencrypted PDF file with parser default "pypdf"
- **THEN** the server returns HTTP 202 with an array containing one document descriptor with status "queued"

#### Scenario: Valid multi-file PDF upload
- **WHEN** a client posts three valid PDF files in a single multipart request
- **THEN** the server enqueues three separate jobs and returns HTTP 202 with three document descriptors

### Requirement: File Validation and Constraint Enforcement
The API SHALL validate each uploaded file's content type (`application/pdf`), header magic bytes (`%PDF-`), non-zero length, maximum size (25MB), and unencrypted status, rejecting non-conforming uploads with standardized error responses.

#### Scenario: Rejection of non-PDF MIME type
- **WHEN** a client uploads a file with media type "image/png"
- **THEN** the server returns HTTP 415 Unsupported Media Type with code "INVALID_FILE_TYPE"

#### Scenario: Rejection of spoofed PDF extension
- **WHEN** a client uploads a text file renamed to ".pdf" lacking `%PDF-` magic bytes
- **THEN** the server returns HTTP 415 Unsupported Media Type with code "INVALID_FILE_TYPE"

#### Scenario: Rejection of empty file
- **WHEN** a client uploads a file of 0 bytes
- **THEN** the server returns HTTP 400 Bad Request with code "EMPTY_FILE"

#### Scenario: Rejection of oversized file
- **WHEN** a client uploads a PDF exceeding 25 megabytes
- **THEN** the server returns HTTP 413 Payload Too Large with code "FILE_TOO_LARGE"

#### Scenario: Rejection of excessive file count
- **WHEN** a client uploads more than 10 files in a single request
- **THEN** the server returns HTTP 413 Payload Too Large with code "TOO_MANY_FILES"

#### Scenario: Rejection of encrypted PDF
- **WHEN** a client uploads a password-protected PDF document
- **THEN** the server returns HTTP 400 Bad Request with code "ENCRYPTED_PDF"

### Requirement: Parser Availability Check
The API SHALL accept parser parameters "pypdf", "gemini", and "mistral", but return HTTP 500 with code "PARSER_UNAVAILABLE" for unimplemented parsers ("gemini" and "mistral").

#### Scenario: PyPDF parser accepted
- **WHEN** a client specifies parser "pypdf" for a valid PDF upload
- **THEN** the server accepts the upload with HTTP 202

#### Scenario: Gemini parser reported unavailable
- **WHEN** a client specifies parser "gemini"
- **THEN** the server returns HTTP 500 with code "PARSER_UNAVAILABLE"

#### Scenario: Mistral parser reported unavailable
- **WHEN** a client specifies parser "mistral"
- **THEN** the server returns HTTP 500 with code "PARSER_UNAVAILABLE"

### Requirement: Redis Persistence and Stream Publishing
Upon successful validation, the API SHALL persist the raw PDF bytes with a configurable TTL, save document metadata in a Redis hash, index the creation timestamp in a sorted set, and append an execution task to the `documents:jobs` Redis Stream.

#### Scenario: Document storage and queue dispatch
- **WHEN** a valid PDF upload is accepted
- **THEN** a Redis hash `doc:{id}` is created with status "queued", the PDF bytes are saved at `doc:{id}:file`, and a message containing document_id and parser is published to `documents:jobs`

### Requirement: Document Collection Query with Cursor Pagination
The API SHALL expose `GET /documents` to retrieve a list of uploaded documents ordered by creation time in descending order, supporting `limit` and an opaque `cursor` parameter.

#### Scenario: Query first page of documents
- **WHEN** a client calls `GET /documents` with limit 20 and no cursor
- **THEN** the server returns up to 20 documents, a next_cursor token, and has_more boolean

#### Scenario: Query subsequent page with cursor
- **WHEN** a client calls `GET /documents` passing a valid cursor from a previous page
- **THEN** the server returns items immediately following the cursor position

### Requirement: Full Document Result Retrieval
The API SHALL expose `GET /documents/{document_id}` returning document metadata, status, parsed pages when available, summary if present, or error details when processing failed.

#### Scenario: Retrieve document in queued state
- **WHEN** a client requests a document whose status is "queued"
- **THEN** the server returns HTTP 200 with status "queued", null pages, and null summary

#### Scenario: Retrieve non-existent document
- **WHEN** a client requests an ID that does not exist in Redis
- **THEN** the server returns HTTP 404 Not Found with code "DOCUMENT_NOT_FOUND"

### Requirement: Document Query Status Polling
The API SHALL expose `GET /documents/{document_id}/status` returning only status, timestamps, and optional error info, providing an HTTP `Retry-After: 3` header when the document is incomplete.

#### Scenario: Polling status for in-flight job
- **WHEN** a client polls a document whose status is "queued" or "processing"
- **THEN** the server returns HTTP 200 with the status and a `Retry-After: 3` header

#### Scenario: Polling status for non-existent document
- **WHEN** a client polls an unknown document ID
- **THEN** the server returns HTTP 404 Not Found with code "DOCUMENT_NOT_FOUND"

### Requirement: Pluggable Parser Interface
The backend SHALL implement a unified `Parser` interface with an asynchronous `parse(pdf_bytes: bytes) -> list[Page]` method, allowing multiple parser engines to be substituted transparently.

#### Scenario: Interface contract adherence
- **WHEN** a parser implementation executes its parse method
- **THEN** it returns a list of Page objects with 1-indexed page_number, content string, and format indicator

### Requirement: PyPDF Text Extraction Off Event Loop
The `PyPDFParser` service SHALL execute PDF reading and page text extraction off the main asyncio event loop using `asyncio.to_thread`, detecting encrypted PDFs and emitting structured page results with `format: "text"`.

#### Scenario: Successful multi-page text parsing
- **WHEN** valid PDF bytes are provided to `PyPDFParser.parse()`
- **THEN** it returns Page objects for each page with extracted text and format "text"

#### Scenario: Encrypted PDF encountered during parsing
- **WHEN** password-protected PDF bytes are passed to `PyPDFParser.parse()`
- **THEN** it raises an `EncryptedPDFError` indicating password protection

### Requirement: Structured Multimodal Gemini Parsing
The `GeminiParser` SHALL send PDF binary bytes to Gemini using structured output schemas returning a list of page objects with 1-indexed `page_number`, markdown `content`, and format set to `markdown`.

#### Scenario: Successful Gemini Markdown parsing
- **WHEN** valid PDF bytes are processed by GeminiParser
- **THEN** it returns structured DocumentPage objects containing page numbers and markdown formatting

### Requirement: Gemini Page Count Validation and Retry
The parser SHALL compare the number of pages returned by Gemini against the ground-truth page count obtained via PyPDF. If the count differs, it MUST retry the extraction once; if the mismatch persists, it SHALL raise `ParserFailedError`.

#### Scenario: Page count matches on first attempt
- **WHEN** Gemini returns the exact number of pages detected by PyPDF
- **THEN** the parsed pages are accepted without retry

#### Scenario: Page count mismatch retried and resolved
- **WHEN** Gemini initially returns fewer pages than PyPDF detects, but matches on the second attempt
- **THEN** the second result is accepted

#### Scenario: Persistent page count mismatch
- **WHEN** Gemini returns mismatched page counts on both attempts
- **THEN** the parser raises `ParserFailedError` with error code "PARSER_FAILED"

### Requirement: Structured Mistral OCR Parsing
The `MistralParser` SHALL submit PDF documents to Mistral OCR using `client.ocr.process_async` and return ordered `DocumentPage` objects with 1-indexed `page_number`, markdown `content`, and format set to `markdown`.

#### Scenario: Successful Mistral Markdown parsing
- **WHEN** valid PDF bytes are processed by MistralParser
- **THEN** it returns structured DocumentPage objects containing page numbers and markdown formatting

### Requirement: Inline vs Files API Ingestion Threshold
For PDF payloads $\le$ 10 MB, the parser SHALL format the document as an inline base64 data URI (`data:application/pdf;base64,...`). For payloads > 10 MB, the parser SHALL upload the file via Mistral Files API, process the signed URL, and delete the uploaded file in a `finally` block.

#### Scenario: Small PDF uses inline base64
- **WHEN** a PDF smaller than 10 MB is processed
- **THEN** the parser transmits the document inline without calling the Files API

#### Scenario: Large PDF uses Files API
- **WHEN** a PDF exceeding 10 MB is processed
- **THEN** the parser uploads the file to the Files API, retrieves a signed URL, performs OCR, and cleans up the uploaded file

### Requirement: Mistral Page Count Validation and Retry
The parser SHALL compare the number of extracted pages against the ground truth page count from PyPDF. If the counts differ, it MUST retry once. If the mismatch persists, it SHALL raise `ParserFailedError`.

#### Scenario: Page count matches
- **WHEN** Mistral returns the exact number of pages detected by PyPDF
- **THEN** the parsed pages are accepted without retry

#### Scenario: Page count mismatch retried and failed
- **WHEN** Mistral returns fewer pages than PyPDF detects on both attempts
- **THEN** the parser raises `ParserFailedError` with error code "PARSER_FAILED"

### Requirement: Error Classification and Rate Limiting
The parser SHALL limit concurrent requests with an `asyncio.Semaphore` (`MISTRAL_CONCURRENCY`, default 2). HTTP 429 and 5xx/timeouts SHALL be treated as transient errors triggering redelivery. HTTP 4xx SHALL be treated as permanent errors raising `ParserFailedError`.

#### Scenario: Rate limit HTTP 429 triggers retry
- **WHEN** Mistral returns HTTP 429
- **THEN** the error is classified as transient and left for worker backoff redelivery

#### Scenario: Permanent HTTP 4xx fails immediately
- **WHEN** Mistral returns HTTP 400 or 422
- **THEN** the parser raises `ParserFailedError` and routes to the dead-letter queue without retry

### Requirement: Missing API Key Configuration
If `MISTRAL_API_KEY` is empty, the parser SHALL report `PARSER_UNAVAILABLE` with an explanatory message indicating that the parser is not configured, without preventing other parsers or the API from operating.

#### Scenario: Upload when API key is missing
- **WHEN** a user uploads a document with parser `mistral` but `MISTRAL_API_KEY` is not set
- **THEN** the request fails with error code `PARSER_UNAVAILABLE` and a configuration message

### Requirement: Consumer Group Ingestion
The worker daemon SHALL join the consumer group `documents:workers` on stream `documents:jobs`, utilizing a unique consumer identifier, and continuously consume pending and new jobs using `XREADGROUP` throttled by a concurrency semaphore.

#### Scenario: Consumer group initialization
- **WHEN** the worker daemon starts up
- **THEN** it idempotently creates consumer group "documents:workers" on stream "documents:jobs" with the stream created if missing

#### Scenario: Throttled concurrent reading
- **WHEN** multiple messages arrive on "documents:jobs"
- **THEN** the worker processes no more than the configured WORKER_CONCURRENCY tasks simultaneously

### Requirement: Document Status Lifecycle Transitions
The worker daemon SHALL atomically set the document status to `processing` with a started timestamp prior to parsing, and upon successful extraction, write page results to `doc:{id}:pages` and mark status `done` with a finished timestamp before acknowledging the message with `XACK`.

#### Scenario: Successful document parsing and state transition
- **WHEN** a worker receives a valid job for an enqueued PDF
- **THEN** it sets status "processing", extracts page text, writes page results, sets status "done", and calls XACK on the message

#### Scenario: Idempotent processing of already completed job
- **WHEN** a message is received for a document whose status is already "done"
- **THEN** the worker immediately acknowledges the message with XACK without re-running parsing

### Requirement: Unsupported Parser Rejection
When a worker encounters a job specifying an unimplemented parser such as `gemini` or `mistral`, it SHALL immediately set the document status to `failed` with error code `PARSER_UNAVAILABLE`, record error diagnostics, and acknowledge the message with `XACK`.

#### Scenario: Gemini parser job received
- **WHEN** a worker reads a job message with parser set to "gemini"
- **THEN** it updates the document status to "failed" with code "PARSER_UNAVAILABLE" and acknowledges the message without retrying

### Requirement: Resumable Staged Processing
The worker daemon SHALL execute document processing in two discrete, resumable stages: parsing followed by summarization, atomically transitioning the status to `summarizing` once pages are written.

#### Scenario: Full successful pipeline execution
- **WHEN** an enqueued document is processed
- **THEN** it transitions from "queued" to "processing", persists pages, transitions to "summarizing", persists summary, transitions to "done", and acknowledges the message

#### Scenario: Resumption of redelivered summarizing document
- **WHEN** a document already in the "summarizing" state is picked up by a worker
- **THEN** the worker skips the parsing phase and proceeds directly to summarization using existing pages

### Requirement: Page Retention on Summarization Failure
If summarization fails due to a rate limit or unrecoverable error, the worker SHALL record the failure on the document while preserving the extracted page records in Redis.

#### Scenario: Summarization rate limit exhausted
- **WHEN** summarization fails repeatedly with rate limits exceeding MAX_ATTEMPTS
- **THEN** status is set to "failed" with code "SUMMARY_RATE_LIMITED", extracted pages remain accessible via GET /documents/{id}, and the job is sent to "documents:dead"

### Requirement: Permanent Failure and Dead-Letter Routing
The worker daemon SHALL treat encrypted, corrupted, expired, or non-existent PDF files as permanent failures, updating the document status to `failed` with contract-defined error codes, routing the message to dead-letter stream `documents:dead`, and acknowledging the original message with `XACK`.

#### Scenario: Corrupted or unparseable PDF encountered
- **WHEN** PyPDF parser fails with an unrecoverable parsing error
- **THEN** document status is set to "failed" with code "PARSER_FAILED", an entry is added to "documents:dead", and the message is acknowledged

#### Scenario: Expired or missing PDF file
- **WHEN** the raw PDF bytes are absent from Redis when worker processing begins
- **THEN** document status is set to "failed" with code "DOCUMENT_NOT_FOUND", the failure is logged to "documents:dead", and the message is acknowledged

### Requirement: Transient Failure Retry and Backoff
When encountering transient infrastructure errors (such as Redis disconnects or timeouts), the worker daemon SHALL leave the message unacknowledged up to `MAX_ATTEMPTS` to allow redelivery, routing to `documents:dead` only after exceeding the maximum attempt count.

#### Scenario: Transient error retried up to limit
- **WHEN** processing fails due to a temporary Redis connection error and attempt count is below MAX_ATTEMPTS
- **THEN** the message is left unacknowledged to permit redelivery

#### Scenario: Maximum retry attempts exceeded
- **WHEN** a message fails processing repeatedly exceeding MAX_ATTEMPTS
- **THEN** the document status is set to "failed", the event is written to "documents:dead", and the message is acknowledged

### Requirement: Recovery of Stuck Messages via Autoclaim
The worker daemon SHALL periodically execute `XAUTOCLAIM` on `documents:jobs` to identify and reassign messages that have remained pending past `CLAIM_IDLE_MS` due to crashed or unresponsive worker instances, while skipping any message whose processing lock is currently held by an active worker.

#### Scenario: Crashed worker message claimed by live worker
- **WHEN** a message has been pending longer than CLAIM_IDLE_MS and no active lock is held
- **THEN** a running worker claims the message via XAUTOCLAIM and processes it through the standard execution path

#### Scenario: Active in-flight message skipped during autoclaim
- **WHEN** a message has been pending longer than CLAIM_IDLE_MS but its document lock is actively held by a processing worker
- **THEN** autoclaim skips reclaiming or dispatching the message, leaving it with the active worker

### Requirement: Consolidated Document Summarization
The summarizer service SHALL generate exactly one concise summary for a document using its extracted pages, preserving the primary language of the document.

#### Scenario: Single-pass summarization within context budget
- **WHEN** the combined text of all document pages is within the configured character budget
- **THEN** a single Gemini summarization request is made and the generated summary is returned

#### Scenario: Map-reduce summarization for large documents
- **WHEN** the combined text of all document pages exceeds the configured character budget
- **THEN** pages are summarized in chunks, and a final summary is generated from the intermediate summaries

### Requirement: Empty Extracted Text Rejection
When document pages contain no extractable text content (such as purely scanned PDFs parsed with PyPDF), the summarizer SHALL raise `SummaryFailedError` with a message advising the client to utilize the `gemini` multimodal parser.

#### Scenario: Empty text content detected
- **WHEN** all page contents in a document consist solely of whitespace
- **THEN** the summarizer raises an error with code "SUMMARY_FAILED" and suggestion to use parser "gemini"

### Requirement: Drag-and-Drop and File Picker Upload
The UI SHALL provide an upload zone supporting drag-and-drop and standard file picker input for 1 to 10 files.

#### Scenario: User drops valid PDF files
- **WHEN** the user drops one or more valid PDF files (`.pdf` extension, MIME type `application/pdf`)
- **THEN** the files are added to the pending upload queue and displayed with name and file size

### Requirement: Client-Side Validation
The UI SHALL validate files before submission against contract constraints:
1. File type MUST be `application/pdf`.
2. File size MUST NOT exceed 25 MB (26,214,400 bytes).
3. Batch count MUST NOT exceed 10 files.

#### Scenario: Non-PDF file rejected
- **WHEN** the user attempts to upload a non-PDF file (e.g. `report.docx` or `image.png`)
- **THEN** the UI rejects the file and displays an error message indicating that only PDF files are supported

#### Scenario: File exceeding maximum size rejected
- **WHEN** the user attempts to upload a PDF file exceeding 25 MB
- **THEN** the UI rejects the file and displays an error message showing the 25 MB limit

#### Scenario: More than 10 files rejected
- **WHEN** the user attempts to upload more than 10 files simultaneously
- **THEN** the UI warns the user and restricts the batch to a maximum of 10 files

### Requirement: Parser Selection
The UI SHALL offer a parser selector containing the options defined in the contract (`pypdf`, `gemini`, `mistral`), defaulting to `pypdf`. Parsers designated in `DISABLED_PARSERS` SHALL be visually disabled with an explanatory tooltip or badge.

#### Scenario: Default parser selection
- **WHEN** the user views the upload interface
- **THEN** `pypdf` is selected by default

#### Scenario: Disabled parser cannot be submitted
- **WHEN** a parser is listed in `DISABLED_PARSERS` (such as `mistral`)
- **THEN** the option cannot be selected or submitted

### Requirement: Submission and Optimistic List Addition
Upon clicking Submit, the UI SHALL issue `POST /documents` with `multipart/form-data` containing `files[]` and `parser`. On a `202 Accepted` response, the returned items SHALL be added immediately to the document list in `queued` status.

#### Scenario: Successful upload batch submission
- **WHEN** the user submits 2 valid PDF files
- **THEN** the API returns 202 with 2 document records, which immediately appear in the document list as "Queued"

#### Scenario: Graceful handling of PARSER_UNAVAILABLE
- **WHEN** the upload request fails due to `PARSER_UNAVAILABLE`
- **THEN** the UI displays the server error message and remains fully usable without crashing

### Requirement: Document Listing and Ordering
The UI SHALL query `GET /documents` to display the history of uploaded documents, ordered with the newest documents first. Each item SHALL display its filename, parser badge, status badge, and creation timestamp.

#### Scenario: Displaying document list
- **WHEN** the document list loads
- **THEN** it renders all documents with their filename, parser tag, status badge, and formatted timestamp

### Requirement: Pagination (Load More)
The UI SHALL support cursor-based pagination matching the contract (`cursor` and `has_more` fields). If `has_more` is true, a "Load More" button SHALL be rendered.

#### Scenario: Loading additional documents
- **WHEN** the user clicks "Load More"
- **THEN** the UI requests the next page using the `cursor` parameter and appends the new items to the list

### Requirement: Status Lifecycle Badges
The UI SHALL display distinct, accessible visual badges for each status:
- `queued`: Amber badge
- `processing`: Blue badge with activity indicator
- `summarizing`: Purple badge with pulse indicator
- `done`: Emerald badge with checkmark icon
- `failed`: Rose/Crimson badge with alert icon

#### Scenario: Visual status differentiation
- **WHEN** a document transitions from `processing` to `summarizing` to `done`
- **THEN** the badge color, icon, and text update accordingly with an `aria-live` announcement

### Requirement: TanStack Query Polling
For each document with a non-terminal status (`queued`, `processing`, `summarizing`), the UI SHALL poll `GET /documents/{document_id}/status` periodically:
1. Default interval is 2,000 milliseconds.
2. If the API response includes a `Retry-After` header, that duration SHALL be used for the next poll.
3. Polling SHALL stop immediately when status reaches `done` or `failed`.
4. Polling SHALL pause when the browser tab is hidden.

#### Scenario: Transition through status lifecycle
- **WHEN** a newly uploaded document is polled
- **THEN** status updates from `queued` to `processing` to `summarizing` and finally stops at `done`

#### Scenario: Polling halts on terminal state
- **WHEN** a document status becomes `done` or `failed`
- **THEN** polling for that document ceases

### Requirement: Document Selection and Detail Fetching
When a user selects a document from the list, the UI SHALL fetch `GET /documents/{document_id}` and render its details.

#### Scenario: User selects a completed document
- **WHEN** the user selects a document with status `done`
- **THEN** the viewer loads the executive summary and parsed pages

### Requirement: Early Page Display During Summarization
When a document has status `summarizing`, the UI SHALL display the extracted pages immediately, alongside a placeholder indicating that the summary is being generated.

#### Scenario: Viewing document in summarizing status
- **WHEN** the user inspects a document currently in `summarizing` status
- **THEN** the viewer renders the extracted pages and displays a loading card for the pending summary

### Requirement: Content Rendering (Markdown vs Text)
The UI SHALL render each page according to its `format` property:
- If format is `markdown`, content SHALL be rendered via `react-markdown` with GFM support.
- If format is `text`, content SHALL be rendered in a preformatted monospace block preserving whitespace.

#### Scenario: Gemini markdown page rendering
- **WHEN** viewing a page produced by Gemini (`format: markdown`)
- **THEN** headings, tables, bold text, and lists are formatted as HTML

#### Scenario: PyPDF plain text page rendering
- **WHEN** viewing a page produced by PyPDF (`format: text`)
- **THEN** plain text is rendered preserving line breaks and spacing

### Requirement: Page Navigation
When a document contains multiple pages, the UI SHALL provide page navigation controls (previous page, next page, and current page / total pages indicator).

#### Scenario: Navigating between pages
- **WHEN** the user clicks "Next Page"
- **THEN** the viewer switches from page 1 to page 2

### Requirement: Error Display with Page Retention
When a document has status `failed`, the UI SHALL render an error message containing the `code` and `message`. If `pages` are present in the response (e.g., failure occurred during summarization), the pages SHALL remain viewable.

#### Scenario: Failed summarization keeps pages
- **WHEN** a document failed with code `SUMMARY_FAILED` after parsing completed
- **THEN** the error is prominently displayed, and the extracted pages are still readable

### Requirement: Copy and Export Actions
The UI SHALL provide action buttons:
1. **Copy Summary**: Copies the executive summary text to the clipboard with visual confirmation.
2. **Download Markdown**: Generates and downloads a `.md` file containing the summary and all pages.

#### Scenario: Copy summary to clipboard
- **WHEN** the user clicks "Copy Summary"
- **THEN** the text is copied to clipboard and a brief confirmation state is shown

#### Scenario: Download full markdown
- **WHEN** the user clicks "Download Markdown"
- **THEN** the browser downloads `{document_id}_{filename}.md` containing the summary and all pages

### Requirement: Active Processing Distributed Lease and Renewal
The worker daemon SHALL acquire a distributed lock with TTL before processing any document job, refresh the lock and stream message idle time periodically while execution is in progress, and release the lock upon job completion or termination.

#### Scenario: Distributed lock prevents concurrent duplicate processing
- **WHEN** a worker attempts to process a document whose lock is currently held by another worker
- **THEN** the worker aborts execution immediately without re-invoking document parsers or summarizers

#### Scenario: Active heartbeat keeps lock and message lease alive
- **WHEN** a document processing or summarization task executes for longer than CLAIM_IDLE_MS
- **THEN** background renewal refreshes the lock and resets PEL idle time, preventing premature autoclaim or duplicate execution

### Requirement: Poison Pill and Crashed Worker DLQ Guard
Before beginning document execution, the worker daemon SHALL inspect the delivery count of the message. If the delivery count exceeds MAX_ATTEMPTS due to repeated worker crashes or fatal terminations, the daemon SHALL immediately transition the document to failed, publish to the dead-letter queue, and acknowledge the message.

#### Scenario: Poison pill document causes repeated worker crashes
- **WHEN** a message is redelivered with delivery count exceeding MAX_ATTEMPTS after successive worker crashes
- **THEN** the worker transitions document status to "failed" with code "PARSER_FAILED", writes the event to "documents:dead", and acknowledges the message via XACK without re-executing parsing
