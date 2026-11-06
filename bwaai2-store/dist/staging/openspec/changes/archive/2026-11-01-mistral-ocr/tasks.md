# Tasks

## 1. Store Specification

- [x] 1.1 [store] Author OpenSpec change `mistral-ocr` (`proposal.md`, `design.md`, `specs/`, `tasks.md`).
- [x] 1.2 [store] Verify OpenSpec validity with `openspec validate mistral-ocr --strict`.

## 2. Backend Dependencies and Configuration

- [x] 2.1 [backend] Add `mistralai>=1.5.0` to `pyproject.toml` dependencies and install in `.venv`.
- [x] 2.2 [backend] Update `app/core/config.py` and `.env.example` with `MISTRAL_API_KEY`, `MISTRAL_OCR_MODEL`, `MISTRAL_CONCURRENCY`, `MISTRAL_TIMEOUT_SECONDS`.
- [x] 2.3 [backend] Define `ParserTransientError` and `ParserRateLimitedError` in `app/core/exceptions.py`.

## 3. Mistral Parser Service

- [x] 3.1 [backend] Implement `MistralParser` in `app/services/parsers/mistral_parser.py` using official async SDK (`client.ocr.process_async`), base64 inline threshold (10 MB), and Files API fallback (`upload_async`, `get_signed_url_async`, `delete_async`).
- [x] 3.2 [backend] Implement PyPDF ground-truth page count comparison and single-attempt retry on count mismatch in `MistralParser`.
- [x] 3.3 [backend] Implement concurrency semaphore, request timeout, and error classification (429/5xx transient, 4xx permanent `PARSER_FAILED`, missing key `PARSER_UNAVAILABLE`).
- [x] 3.4 [backend] Update `app/services/parsers/llm_parsers.py` to re-export `MistralParser`.

## 4. Worker and Router Integration

- [x] 4.1 [backend] Update `app/worker/processor.py` to register `MistralParser` in `JobProcessor` and handle `ParserUnavailableError` and `ParserTransientError`.
- [x] 4.2 [backend] Update `app/api/documents.py` to accept `mistral` if `MISTRAL_API_KEY` is configured, or return `PARSER_UNAVAILABLE` with clear message if missing.
- [x] 4.3 [backend] Pass Mistral environment variables to `worker` service in `docker-compose.yml`.

## 5. Frontend Activation

- [x] 5.1 [frontend] Enable Mistral option in `src/config/parsers.ts` by setting `DISABLED_PARSERS = []`.
- [x] 5.2 [frontend] Update tests in `bwaai2-frontend/tests/upload.test.tsx` and verify frontend test suite passes.

## 6. Testing and Documentation

- [x] 6.1 [backend] Implement unit tests in `tests/test_mistral.py` covering inline base64, Files API path, page count retry and failure, 429 rate limit retry, 4xx permanent failure, and missing key.
- [x] 6.2 [backend] Update `tests/test_worker.py` to test end-to-end processing of `mistral` documents through `processing -> summarizing -> done`.
- [x] 6.3 [backend] Run full pytest suite and Ruff linter in `bwaai2-backend`.
- [x] 6.4 [backend] Update `README.md` in `bwaai2-backend` with Mistral API key setup, environment variables, and cURL walkthrough.
