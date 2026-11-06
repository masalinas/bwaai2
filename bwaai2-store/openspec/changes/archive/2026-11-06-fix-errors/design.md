# Design: Distributed Worker Resilience (Lease Renewal and Crash DLQ Guard)

## Context

In Redis Streams worker architectures, tasks are acknowledged (`XACK`) strictly upon pipeline completion. If processing takes longer than `CLAIM_IDLE_MS` (60s), background autoclaimers identify the message as abandoned and reassign it to other workers, causing redundant parsing runs. Furthermore, if a worker process crashes abruptly (e.g. OOM, `kill -9`, segmentation fault) without throwing a Python catchable exception, the message remains unacknowledged and is retried indefinitely on subsequent autoclaims, because the existing DLQ routing logic only executes within `except Exception` blocks.

## Goals / Non-Goals

**Goals:**
- Provide mutual exclusion per document across worker instances using distributed Redis locks (`doc:lock:{doc_id}`).
- Maintain an active heartbeat during execution that extends the distributed lock TTL and resets the Redis stream PEL message idle time via `XCLAIM ... JUSTID`.
- Guarantee that `AutoClaimer` does not reassign or dispatch messages whose document lock is actively held.
- Implement a pre-execution entry guard on `delivery_count > settings.MAX_ATTEMPTS` to route repeated crash failures directly to the DLQ (`documents:dead`), transition status to `failed`, and call `XACK`.

**Non-Goals:**
- Redesigning the stream consumer topology or introducing heavy external orchestrators (Celery, Temporal).
- Modifying the REST API or database schema.

## Decisions

### 1. Distributed Locking with Safe Key Lifecycle
- **Key naming**: `doc:lock:{doc_id}` (`constants.doc_lock_key(doc_id)`).
- **Acquisition**: `SET doc:lock:{doc_id} {consumer_name} NX EX 30`. If false, another worker is actively processing; current worker logs a warning and aborts without duplicate execution.
- **Heartbeat & PEL reset**: While task is running, a background asyncio loop executes every 10 seconds:
  1. Checks if `doc:lock:{doc_id}` still belongs to `consumer_name`, refreshing TTL with `EXPIRE doc:lock:{doc_id} 30`.
  2. Executes `XCLAIM documents:jobs documents:workers {consumer_name} 0 {msg_id} JUSTID` to reset PEL idle time without incrementing delivery counts.
- **Safe Release**: In a `finally` block, verify `GET doc:lock:{doc_id} == consumer_name` and delete the key so locks are never inadvertently released if another worker claimed it after unexpected expiration.
- *Alternatives considered*: Redlock algorithm. Overkill for single Redis instance deployments; standard `SET NX EX` with TTL and heartbeat provides exact required safety.

### 2. AutoClaimer Pre-Dispatch Filtering
- In `AutoClaimer.sweep_once()`, inspect each claimed message for its `document_id`.
- If `EXISTS doc:lock:{doc_id}` is true, skip dispatching the job to the local processor.
- *Alternatives considered*: Let `process_message` alone reject it. Pre-filtering in `AutoClaimer` saves concurrency semaphore slots and prevents unnecessary Redis metadata lookups.

### 3. Pre-Execution Crash and DLQ Guard
- At the top of `JobProcessor.process_message`, after document metadata retrieval:
  ```python
  if delivery_count > settings.MAX_ATTEMPTS:
      await self._handle_permanent_error(
          doc_id=doc_id,
          parser=parser_name,
          msg_id=msg_id,
          code=ErrorCode.PARSER_FAILED,
          message=f"Job crashed or failed to complete after {delivery_count - 1} attempts.",
          consumer_name=consumer_name,
          attempts=delivery_count,
      )
      return
  ```
- *Alternatives considered*: Checking only in `AutoClaimer`. Placing the check in `process_message` guarantees protection regardless of entry point (normal consumer dispatch, autoclaim, or test runners).

## Risks / Trade-offs

- [Risk] Worker crash leaves lock key active for 30 seconds before expiring.
  → Mitigation: TTL is 30 seconds, which is strictly less than `CLAIM_IDLE_MS` (60s). By the time another worker's `AutoClaimer` sweeps for the abandoned job, the lock key has already naturally expired.
- [Risk] Background heartbeat task continues running if an unhandled exception occurs in `process_message`.
  → Mitigation: Heartbeat task cancellation and lock cleanup are wrapped in a strict `try...finally` block enclosing all pipeline processing stages.
