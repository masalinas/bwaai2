# Design: Redis Streams Asynchronous Worker

## Context

The system processes PDF uploads asynchronously. The HTTP ingestion API receives documents, validates them, writes raw files and initial metadata to Redis 7, and pushes tasks onto Redis Stream `documents:jobs`. 

This design establishes the architecture for the background worker daemon running in `bwaai2-backend`. The worker joins consumer group `documents:workers`, reads jobs, executes CPU-bound PyPDF parsing off-thread, persists structured page outputs, handles retries, and recycles orphan jobs.

## Goals / Non-Goals

**Goals:**
- Provide a resilient, horizontally scalable worker process (`python -m app.worker`) capable of running in multiple parallel container instances (`docker compose up --scale worker=3`).
- Implement at-least-once delivery: acknowledge (`XACK`) messages only after successful persistence of results.
- Implement idempotent execution: gracefully handle duplicate message delivery without duplicate work.
- Provide automatic recovery of abandoned tasks from crashed workers using `XAUTOCLAIM`.
- Route permanently failed or exhausted jobs to a dead-letter stream (`documents:dead`).
- Provide clean graceful shutdown on `SIGTERM` / `SIGINT` with task draining.

**Non-Goals:**
- Integrating Gemini or Mistral parser backends (jobs with these parsers are marked `failed` with `PARSER_UNAVAILABLE` and acknowledged).
- Generating Gemini document summaries (summary remains null).
- Modifying `contracts/openapi.yaml` or placing application code in `bwaai2-store`.

## Decisions

### 1. Delivery Semantics & Idempotency
- **At-Least-Once Delivery**: The worker calls `XREADGROUP` without automatic acknowledgement (`noack=False`). The `XACK` command is issued strictly after:
  - Structured pages are successfully written to `doc:{id}:pages` and document status is updated to `done`, OR
  - An unrecoverable failure is recorded in `doc:{id}` and routed to `documents:dead`.
- **Idempotency Guard**: Before parsing, the worker checks `doc:{id}` status. If the status is already `done`, the message is acknowledged immediately without re-parsing.

### 2. Failure Classification & Retry Policy
- **Permanent Errors**:
  - `EncryptedPDFError` -> error code `ENCRYPTED_PDF`.
  - Missing raw PDF file bytes (`doc:{id}:file` expired) -> error code `DOCUMENT_NOT_FOUND`.
  - Corrupted, malformed, or unparseable PDF -> error code `PARSER_FAILED`.
  - Unsupported parsers (`gemini`, `mistral`) -> error code `PARSER_UNAVAILABLE`.
  - *Action*: Record failure in `doc:{id}`, push to Dead-Letter Queue (`documents:dead`), and `XACK` original message immediately.
- **Transient Errors**:
  - Redis connection drop, socket timeout, temporary I/O blips.
  - *Action*: Do not acknowledge. The message remains in the Pending Entries List (PEL). The worker tracks attempts (using Redis delivery count or message attempt metadata). If `attempts >= MAX_ATTEMPTS` (default: 3), the worker transitions the document to `failed`, routes to DLQ, and acknowledges the message.

### 3. Dead-Letter Queue (DLQ) Format
Messages failing permanently or exceeding `MAX_ATTEMPTS` are published to `documents:dead` with fields:
```json
{
  "document_id": "doc_01j9a8b7...",
  "parser": "pypdf",
  "original_msg_id": "1730332800000-0",
  "error_code": "PARSER_FAILED",
  "error_message": "Failed to parse PDF document: ...",
  "attempts": "3",
  "failed_at": "2026-10-30T22:00:00Z"
}
```

### 4. Orphan Message Recovery via XAUTOCLAIM
- If a worker container crashes while processing a job, the message remains in the Pending Entries List (PEL).
- Every worker instance runs a periodic background loop executing `XAUTOCLAIM` every `AUTOCLAIM_INTERVAL_SECONDS` (default: 10s) with `min_idle_time = CLAIM_IDLE_MS` (default: 60,000ms).
- Claimed messages are seamlessly handed off to the standard processing pipeline.

### 5. Unique Consumer Identity & Horizontal Scaling
- Consumer names are generated dynamically on startup:
  `f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"`
- This ensures distinct consumers when running multiple replicas under Docker Compose (`docker compose up --scale worker=3`) or Kubernetes pods.

### 6. Graceful Shutdown & Drain
- On `SIGTERM` / `SIGINT`, the worker enters stopping mode:
  - Halts new `XREADGROUP` poll requests.
  - Cancels the background autoclaim and heartbeat tasks.
  - Waits up to `SHUTDOWN_TIMEOUT_SECONDS` (default: 15s) for currently executing parser tasks to complete and acknowledge.
  - Closes the Redis connection pool and exits cleanly.

### 7. Heartbeat & Healthchecks
- Every worker instance writes a heartbeat key `worker:heartbeat:{consumer_name}` with TTL of 30 seconds every 10 seconds.
- Docker Compose healthcheck probes worker liveness by executing a python one-liner checking heartbeat key presence.

## Configuration Table

| Environment Variable | Type | Default | Description |
|---|---|---|---|
| `REDIS_URL` | string | `redis://localhost:6379/0` | Redis connection URL |
| `WORKER_CONCURRENCY` | integer | `5` | Maximum concurrent jobs processed per worker instance |
| `WORKER_BLOCK_MS` | integer | `2000` | Block timeout for XREADGROUP in milliseconds |
| `WORKER_BATCH_SIZE` | integer | `10` | Max messages fetched per XREADGROUP batch |
| `MAX_ATTEMPTS` | integer | `3` | Maximum retry attempts for transient errors before DLQ |
| `CLAIM_IDLE_MS` | integer | `60000` | Minimum idle time (ms) before pending message is claimed |
| `CLAIM_BATCH_SIZE` | integer | `10` | Maximum messages claimed per XAUTOCLAIM cycle |
| `AUTOCLAIM_INTERVAL_SECONDS` | integer | `10` | Interval between autoclaim sweeps |
| `HEARTBEAT_INTERVAL_SECONDS` | integer | `10` | Frequency of heartbeat renewal in Redis |
| `SHUTDOWN_TIMEOUT_SECONDS` | integer | `15` | Maximum drain window for in-flight tasks on shutdown |

## Risks / Trade-offs

- **[Risk] Worker crash during PyPDF parsing leaves job in processing state**  
  *Mitigation*: `XAUTOCLAIM` reclaims the job after `CLAIM_IDLE_MS` and re-runs it or fails it if attempts are exhausted.
- **[Risk] Poison pill / corrupted PDF repeatedly crashing workers**  
  *Mitigation*: Pre-flight validation in API catches corrupt headers. Parser crashes are caught as permanent errors, updated to `failed`, and pushed to DLQ.
- **[Risk] High CPU consumption from concurrent PyPDF threads**  
  *Mitigation*: `WORKER_CONCURRENCY` bounds simultaneous thread executions per container.
