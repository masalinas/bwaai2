# Spec Delta

## Purpose

Defines asynchronous consumer group message ingestion from Redis Streams, status lifecycle management, PyPDF parsing, and at-least-once delivery semantics.

## ADDED Requirements

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
