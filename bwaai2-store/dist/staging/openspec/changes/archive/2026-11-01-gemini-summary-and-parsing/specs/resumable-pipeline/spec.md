# Spec Delta

## Purpose

Provides a multi-stage resumable worker execution pipeline that preserves extracted pages across summarization retries and failures.

## ADDED Requirements

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
