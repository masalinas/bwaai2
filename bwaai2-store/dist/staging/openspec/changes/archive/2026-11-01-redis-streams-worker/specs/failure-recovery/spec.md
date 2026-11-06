# Spec Delta

## Purpose

Specifies failure classification, dead-letter queue routing, retry policies, and orphan job recovery using `XAUTOCLAIM` for the worker daemon.

## ADDED Requirements

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
The worker daemon SHALL periodically execute `XAUTOCLAIM` on `documents:jobs` to identify and reassign messages that have remained pending past `CLAIM_IDLE_MS` due to crashed or unresponsive worker instances.

#### Scenario: Crashed worker message claimed by live worker
- **WHEN** a message has been pending longer than CLAIM_IDLE_MS
- **THEN** a running worker claims the message via XAUTOCLAIM and processes it through the standard execution path
