# Tasks

## 1. Constants and Locking Primitives

- [x] 1.1 Add `doc_lock_key` helper in `app/core/constants.py` and verify imports and unit tests pass.
- [x] 1.2 Implement distributed lock acquisition, background lease renewal heartbeat loop, and safe release in `app/worker/processor.py` and verify syntax and unit tests.

## 2. Crash Protection and DLQ Guard

- [x] 2.1 Add pre-execution `delivery_count > settings.MAX_ATTEMPTS` guard in `app/worker/processor.py` to route crashed jobs directly to DLQ and verify via tests.
- [x] 2.2 Add active lock check in `app/worker/autoclaim.py` to skip in-flight jobs and verify via tests.

## 3. Test Coverage and Verification

- [x] 3.1 Implement unit and integration tests in `tests/test_worker.py` simulating 3 successive worker crashes and verifying the 4th attempt routes to DLQ and acks without re-parsing.
- [x] 3.2 Implement integration test in `tests/test_worker.py` simulating slow external parsing exceeding `CLAIM_IDLE_MS` with lease renewal and verify that a secondary worker skips duplicate execution.
- [x] 3.3 Run full backend test suite with `uv run --extra dev pytest` and verify all tests pass.
