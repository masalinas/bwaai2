# Spec Delta

## Purpose

Provides asynchronous PDF document submission, per-file processing lifecycle management, paginated listing, status polling, and structured content and summary retrieval.

## ADDED Requirements

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

### Requirement: Lightweight Status Polling
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
