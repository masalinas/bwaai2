# Spec Delta

## MODIFIED Requirements

### Requirement: Recovery of Stuck Messages via Autoclaim
The worker daemon SHALL periodically execute `XAUTOCLAIM` on `documents:jobs` to identify and reassign messages that have remained pending past `CLAIM_IDLE_MS` due to crashed or unresponsive worker instances, while skipping any message whose processing lock is currently held by an active worker.

#### Scenario: Crashed worker message claimed by live worker
- **WHEN** a message has been pending longer than CLAIM_IDLE_MS and no active lock is held
- **THEN** a running worker claims the message via XAUTOCLAIM and processes it through the standard execution path

#### Scenario: Active in-flight message skipped during autoclaim
- **WHEN** a message has been pending longer than CLAIM_IDLE_MS but its document lock is actively held by a processing worker
- **THEN** autoclaim skips reclaiming or dispatching the message, leaving it with the active worker

## ADDED Requirements

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
