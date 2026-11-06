# Spec: Mistral OCR Document Parser

## Purpose

Enables document OCR extraction using the Mistral OCR API (`mistral-ocr-latest`), supporting inline base64 payloads and Files API signed URLs, with PyPDF page count validation.

## ADDED Requirements

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

### Requirement: Page Count Validation and Retry
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
