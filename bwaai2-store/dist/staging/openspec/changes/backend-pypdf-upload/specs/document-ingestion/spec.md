# Spec Delta

## Purpose

Enables multi-file PDF ingestion at `POST /documents`, validating MIME types, magic bytes, file sizes, and encryption, persisting files and metadata in Redis, and queuing jobs on Redis Streams.

## ADDED Requirements

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
