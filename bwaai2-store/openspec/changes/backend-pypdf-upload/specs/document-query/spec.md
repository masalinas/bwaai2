# Spec Delta

## Purpose

Provides paginated document collection queries, detailed document result retrieval, and lightweight polling for the FastAPI backend.

## ADDED Requirements

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

### Requirement: Lightweight Status Polling
The API SHALL expose `GET /documents/{document_id}/status` returning only status, timestamps, and optional error info, providing an HTTP `Retry-After: 3` header when the document is incomplete.

#### Scenario: Polling status for in-flight job
- **WHEN** a client polls a document whose status is "queued" or "processing"
- **THEN** the server returns HTTP 200 with the status and a `Retry-After: 3` header

#### Scenario: Polling status for non-existent document
- **WHEN** a client polls an unknown document ID
- **THEN** the server returns HTTP 404 Not Found with code "DOCUMENT_NOT_FOUND"
