# Proposal: Redis Streams Asynchronous Worker

## Why

While `backend-pypdf-upload` implemented the HTTP ingestion layer that validates files and enqueues tasks to Redis Streams, documents currently remain in the `queued` state indefinitely. A dedicated, resilient asynchronous background worker daemon is required to consume jobs from `documents:jobs`, execute CPU-offloaded PyPDF extraction, handle transient and permanent failures, recover abandoned tasks via `XAUTOCLAIM`, and store final page results and lifecycle statuses in Redis 7.

## What Changes

This change implements the background processing layer within `bwaai2-backend` while keeping specifications in `bwaai2-store`:

- **Worker Daemon Entrypoint (`app/worker/main.py`)**:
  - Standalone executable process (`python -m app.worker`) designed to run independently from the FastAPI API.
  - Multi-instance horizontal scaling (`docker compose up --scale worker=3`) with unique consumer identification (`hostname + pid + uuid`).
- **Consumer Group Management**:
  - Idempotent stream consumer group initialization (`XGROUP CREATE ... MKSTREAM`).
  - Batch message consumption via `XREADGROUP` throttled by `asyncio.Semaphore` (`WORKER_CONCURRENCY`).
- **Job Execution Pipeline**:
  - Atomically transitions document status to `processing` (`started_at`), extracts page text via `PyPDFParser`, writes `doc:{id}:pages`, and marks status `done` (`finished_at`).
  - At-least-once processing semantics: `XACK` is performed strictly after results are persisted.
  - Idempotent execution: already-completed jobs are acknowledged without redundant processing.
  - Non-implemented parsers (`gemini`, `mistral`) are marked `failed` with contract code `PARSER_UNAVAILABLE` and acknowledged.
- **Resilience, Retries & Dead-Letter Queue (DLQ)**:
  - Error classification: permanent (encryption, corruption) vs. transient (network, Redis timeout).
  - Transient retry policy up to `MAX_ATTEMPTS` using redelivery tracking.
  - Unrecoverable messages routed to dead-letter stream `documents:dead` prior to `XACK`.
  - Periodic orphan job recovery using `XAUTOCLAIM` with `CLAIM_IDLE_MS`.
- **Graceful Shutdown & Observability**:
  - Signal handling (`SIGTERM`, `SIGINT`) allowing in-flight jobs to drain before termination.
  - Structured logging tagging `document_id`, `consumer_name`, and `attempt`.
  - Periodic heartbeat key in Redis for container liveness healthchecks.
- **Containerization & Tooling**:
  - Dedicated `worker` service in `docker-compose.yml`.
  - Updated `Makefile` with `worker` command and expanded `up` target.
  - Full end-to-end integration and concurrency test suite with `fakeredis`.

### In Scope
- Worker process, consumer group loop, and error handling in `bwaai2-backend`.
- Redis Streams producer/consumer integration (`documents:jobs`, `documents:dead`).
- Autoclaim stuck job recovery and dead-letter queue.
- Docker compose worker service and end-to-end verification tests.

### Out of Scope
- Gemini and Mistral multimodal parser integration (marked `failed` with `PARSER_UNAVAILABLE`).
- Gemini summarization execution (summary remains null).
- Frontend UI components.

## Capabilities

### New Capabilities
- `stream-consumer`: Asynchronous Redis Streams consumer group processing, PyPDF parsing off-thread, status transitions, and at-least-once delivery with `XACK`.
- `failure-recovery`: Dead-letter queue dispatching, transient retry backoff, and stuck message recovery via `XAUTOCLAIM`.

### Modified Capabilities
None.

## Impact
- **bwaai2-store**: OpenSpec change tracking; no application code is added to the store.
- **bwaai2-backend**: Adds `app/worker/`, updates `docker-compose.yml`, `Makefile`, and `README.md`.
- **System Architecture**: Enables the asynchronous PDF processing lifecycle to complete end-to-end (`queued` -> `processing` -> `done` or `failed`).
