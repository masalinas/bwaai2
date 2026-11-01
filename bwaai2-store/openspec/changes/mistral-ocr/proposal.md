# Proposal: Mistral OCR Document Parser Integration

## Why

With PyPDF plain text extraction and Gemini multimodal parsing operational, users require high-accuracy document OCR capabilities. Mistral OCR provides state-of-the-art document understanding, layout preservation, and Markdown transcription for complex, scanned, or multi-column PDFs. Integrating Mistral OCR completes the parser lineup specified in the OpenAPI contract.

## What Changes

This change specifies and implements the Mistral OCR parser in `bwaai2-backend` and activates the option in `bwaai2-frontend`:

### Store (`bwaai2-store`)
- Authored OpenSpec proposal, design, specifications, and tasks under `openspec/changes/mistral-ocr/`.
- The OpenAPI contract (`contracts/openapi.yaml`) remains unmodified as `mistral` is already included in `ParserType`.

### Backend (`bwaai2-backend`)
- **Mistral OCR Parser (`MistralParser`)**:
  - Implements `BaseParser` interface (`async def parse(self, pdf_bytes: bytes) -> list[DocumentPage]`).
  - Utilizes the official `mistralai` Python SDK (`client.ocr.process_async`) with model `mistral-ocr-latest`.
  - Dual-mode payload strategy:
    - Files $\le$ 10 MB: Sent as inline base64 data URI (`data:application/pdf;base64,...`).
    - Files > 10 MB: Uploaded via Mistral Files API (`upload_async`), processed via signed URL (`get_signed_url_async`), and cleaned up immediately in a `finally` block (`delete_async`).
  - Extracts Markdown pages (`page_number = index + 1`, `content = markdown`, `format = "markdown"`).
  - Verifies extracted page count against PyPDF ground truth; retries once on mismatch, failing with `PARSER_FAILED` if the discrepancy persists.
- **Error Classification & Resilience**:
  - Concurrency limited via `asyncio.Semaphore` (`MISTRAL_CONCURRENCY=2`) and request timeout (`MISTRAL_TIMEOUT_SECONDS=60`).
  - HTTP 429 (rate limits) and 5xx/timeouts are classified as transient, redelivered with exponential backoff up to `MAX_ATTEMPTS`.
  - HTTP 4xx (invalid document, unsupported encoding) is permanent, failing immediately with `PARSER_FAILED` and dead-lettering without retries.
  - Missing API key: If `MISTRAL_API_KEY` is empty, `PARSER_UNAVAILABLE` is raised with an explanatory message, allowing the API and other parsers to function without crashing.
- **Worker & Factory Registration**:
  - `JobProcessor` registers `MistralParser`. `mistral` jobs are processed through the standard resumable pipeline (`queued -> processing -> summarizing -> done`).
- **Configuration & Infrastructure**:
  - Environment variables `MISTRAL_API_KEY`, `MISTRAL_OCR_MODEL`, `MISTRAL_CONCURRENCY`, `MISTRAL_TIMEOUT_SECONDS` added to `Settings`, `.env.example`, and `docker-compose.yml`.
  - `README.md` updated with key acquisition guide, configuration, and cURL walkthrough.

### Frontend (`bwaai2-frontend`)
- Enables Mistral option in `src/config/parsers.ts` by setting `DISABLED_PARSERS = []`.
- Updates parser selector unit tests to verify Mistral selection.

### In Scope
- `MistralParser` service and client integration in `bwaai2-backend`.
- Unit and integration tests mocking Mistral API.
- Enabling Mistral in `bwaai2-frontend`.

### Out of Scope
- OpenAPI contract modifications.
- Image extraction (`include_image_base64=false`).
- Bounding box structural annotations.

## Capabilities

### New Capabilities
- `mistral-parser`: Mistral OCR integration supporting inline base64 and Files API execution with PyPDF page count verification.

### Modified Capabilities
None.

## Impact
- **Contracts**: Unchanged.
- **Backend**: Adds `mistralai` dependency to `pyproject.toml`; adds `MistralParser` to parser factory and worker.
- **Frontend**: Enables `mistral` in parser options.
