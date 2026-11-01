# Tasks

## 1. Contract and Store Specification

- [x] 1.1 [store] Update `contracts/openapi.yaml` with `summarizing` status, `SUMMARY_FAILED` error code, and updated endpoint descriptions/examples, verified by Redocly linter.
- [x] 1.2 [store] Verify OpenSpec proposal, design, and specs for `gemini-summary-and-parsing`, validated via `openspec validate gemini-summary-and-parsing --strict`.

## 2. Backend Models, Config, and Dependencies

- [x] 2.1 [backend] Add `google-genai` dependency to `pyproject.toml` and update virtual environment.
- [x] 2.2 [backend] Update `app/core/config.py` with Gemini configuration (`GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_CONCURRENCY`, `GEMINI_TIMEOUT_SECONDS`, `SUMMARY_MAX_INPUT_CHARS`) and `.env.example`.
- [x] 2.3 [backend] Update `app/models/errors.py` and `app/models/documents.py` to add `summarizing` status and `SUMMARY_FAILED` error code.

## 3. Gemini Services (Client, Parser, Summarizer)

- [x] 3.1 [backend] Implement Gemini async client wrapper in `app/services/gemini.py` with concurrency semaphore, error classification, and retry backoff.
- [x] 3.2 [backend] Implement `GeminiParser` in `app/services/parsers/gemini_parser.py` with structured output, inline vs. files upload, and PyPDF page-count verification.
- [x] 3.3 [backend] Implement `DocumentSummarizer` in `app/services/summarizer.py` supporting single-pass, map-reduce chunking, language preservation, and empty text rejection.

## 4. Resumable Worker Pipeline and API Updates

- [x] 4.1 [backend] Update `app/worker/processor.py` to implement the two-stage resumable pipeline (`processing` -> `summarizing` -> `done`), preserving pages upon summarization failure.
- [x] 4.2 [backend] Update `app/api/documents.py` and `app/services/storage.py` to return `summarizing` status and expose pages as soon as they exist.
- [x] 4.3 [backend] Update `docker-compose.yml` to pass Gemini configuration to the `worker` service.

## 5. Testing and Documentation

- [x] 5.1 [backend] Implement tests in `tests/test_gemini.py` covering parser happy path/retry mismatch, summarization single-pass/map-reduce, rate limiting, and empty text rejection.
- [x] 5.2 [backend] Update `tests/test_worker.py` to test the resumable multi-stage pipeline, page retention on failure, and redelivery resumption.
- [x] 5.3 [backend] Verify contract parity test `tests/test_contract.py` passes against the updated `contracts/openapi.yaml`.
- [x] 5.4 [backend] Run full pytest suite and Ruff linter, and update `README.md` with Gemini environment variables and cURL walkthrough.
