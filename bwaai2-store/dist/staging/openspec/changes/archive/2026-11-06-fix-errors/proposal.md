# Proposal: Fix Distributed Worker Resilience (Lease Renewal and Crash DLQ Guard)

## Why

Under real distributed runtime conditions, Redis Streams workers suffer from two architectural resilience flaws:
1. Long-running parsing or summarization calls (e.g. AI API latency exceeding `CLAIM_IDLE_MS`) cause `XAUTOCLAIM` to reassign in-flight jobs to secondary workers, resulting in duplicate processing, multiplied API costs, and result overwrite races.
2. Abrupt worker crashes (e.g., OOM kills, `kill -9`, or fatal C/Rust binding segfaults) never trigger Python `try...except` blocks, bypassing the DLQ handler and causing poison-pill documents to retry indefinitely in an infinite crash loop without ever transitioning to `failed`.

## What Changes

- **Distributed Lease and Active Heartbeat Renewal**:
  - Worker acquires a distributed lock `doc:lock:{doc_id}` (`NX EX 30`) prior to job processing.
  - While processing is in-flight, a background renewal task periodically refreshes the lock TTL (every 10 seconds) and resets the message's idle time in the stream PEL via `XCLAIM ... JUSTID` to prevent premature autoclaiming.
  - The lock is safely released in a `finally` block upon completion or failure.
  - `AutoClaimer` and `JobProcessor` skip processing any job whose document lock is currently held by an active worker.
- **Pre-execution Crash and DLQ Guard**:
  - Adds an entry guard check at the top of `process_message`: if `delivery_count > settings.MAX_ATTEMPTS`, the job is treated as having exhausted its retry budget due to crashes.
  - The job is immediately transitioned to `failed` with code `PARSER_FAILED`, published to the dead-letter stream `documents:dead`, and acknowledged via `XACK` without re-executing parsing or summarization.
- **Verification and Test Coverage**:
  - Adds integration tests verifying that active long-running jobs are not duplicated by autoclaimers or concurrent workers.
  - Adds tests for successive worker crash cycles proving that poison pills are routed to the DLQ and acknowledged after `MAX_ATTEMPTS`.

## Capabilities

### Modified Capabilities
- `pdf-processor`: Adds distributed lease locking, active heartbeat renewal, and pre-execution delivery count guards for crashed worker DLQ routing.

## Impact

- **Affected Services**: `bwaai2-backend` (`app/worker/processor.py`, `app/worker/autoclaim.py`, `app/core/constants.py`).
- **Dependencies & Schemas**: Uses existing Redis primitives (`SET NX EX`, `EXPIRE`, `DELETE`, `XCLAIM JUSTID`). No API contract changes; completely backward-compatible.
