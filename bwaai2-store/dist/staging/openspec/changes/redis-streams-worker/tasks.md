# Tasks

## 1. Planning and Store Verification

- [x] 1.1 [store] Verify OpenSpec proposal, design, and specs for `redis-streams-worker`, validated via `openspec validate redis-streams-worker --strict`.

## 2. Worker Core Architecture

- [x] 2.1 [backend] Extend `app/core/config.py` and `app/core/constants.py` with worker configurations (`WORKER_CONCURRENCY`, `MAX_ATTEMPTS`, `CLAIM_IDLE_MS`, `STREAM_DOCUMENTS_DEAD`, heartbeat keys).
- [x] 2.2 [backend] Implement consumer group initialization and consumer identity management in `app/worker/consumer.py`.
- [x] 2.3 [backend] Implement job processing pipeline with status transitions (`processing`, `done`, `failed`), PyPDF parser execution, and atomic results storage in `app/worker/processor.py`.

## 3. Resilience, Retries, and Recovery

- [x] 3.1 [backend] Implement permanent error DLQ dispatching to `documents:dead` and transient error retry logic with attempt tracking in `app/worker/processor.py`.
- [x] 3.2 [backend] Implement periodic `XAUTOCLAIM` background task for recovering stuck or abandoned jobs in `app/worker/autoclaim.py`.

## 4. Worker Process Assembly and Lifecycle

- [x] 4.1 [backend] Implement `app/worker/main.py` entrypoint with signal handling (`SIGTERM`/`SIGINT`), graceful drain, structured logging, and heartbeat reporting.
- [x] 4.2 [backend] Add `app/worker/__main__.py` to enable execution via `python -m app.worker`.

## 5. Infrastructure and Tooling

- [x] 5.1 [backend] Update `docker-compose.yml` to include the `worker` service with healthcheck and dependencies.
- [x] 5.2 [backend] Update `Makefile` with `worker` target and updated `up` target, and update `README.md` with worker scaling and end-to-end curl instructions.

## 6. Testing and Verification

- [x] 6.1 [backend] Implement comprehensive worker tests in `tests/test_worker.py` (happy path, corrupt/encrypted, transient retry, autoclaim recovery, idempotency, parallel consumers, unsupported parsers).
- [x] 6.2 [backend] Run full pytest suite and Ruff linter in `../bwaai2-backend`, verifying all tests pass and code is clean.
