# Proposal: Gemini Summary and Parsing Integration

## Why

Currently, the asynchronous worker processes documents with PyPDF text extraction but lacks intelligent multimodal markdown parsing and document summarization. Integrating Gemini enables high-fidelity PDF-to-Markdown parsing via multimodal LLM inference and produces consolidated, multilingual summaries across all parsed documents. Furthermore, refining the document lifecycle with a `summarizing` state allows clients to access extracted pages early while summarization progresses.

## What Changes

This change updates the OpenAPI contract in `bwaai2-store` and implements the Gemini client, parser, summarizer, and multi-stage resumable worker pipeline in `bwaai2-backend`:

### Contract Updates (`bwaai2-store/contracts/openapi.yaml`)
- **Document Status Lifecycle**: Added `summarizing` to the enum (`queued -> processing -> summarizing -> done | failed`).
- **Early Page Exposure**: `GET /documents/{document_id}` returns the `pages` array as soon as parsing completes (states `summarizing`, `done`, or `failed` after parsing succeeded), while `summary` is populated upon transition to `done`.
- **Error Codes**: Added `SUMMARY_FAILED` to `ErrorCode` enum alongside existing `SUMMARY_RATE_LIMITED`.
- **Examples**: Added `summarizingDocument` and `failedAfterParsing` realistic examples.

### Backend Implementation (`bwaai2-backend`)
- **Gemini Client Service (`app/services/gemini.py`)**:
  - Official `google-genai` async client wrapper.
  - Environment configuration (`GEMINI_MODEL`, `GEMINI_API_KEY`, `GEMINI_CONCURRENCY`).
  - Error classification (429/quota -> `SUMMARY_RATE_LIMITED` transient; 5xx -> transient; 4xx/prompt blocked -> permanent `SUMMARY_FAILED`).
  - Concurrency limiting via `asyncio.Semaphore` (default 2) and exponential backoff with jitter.
- **Gemini Parser (`GeminiParser`)**:
  - Implements `Parser` interface, sending PDF bytes to Gemini (inline if <= 10MB, Files API if > 10MB) with structured JSON schema output `pages: [{page_number, markdown}]`.
  - Verifies page count against PyPDF; retries once on mismatch before failing with `PARSER_FAILED`.
  - Registered in parser factory/worker (`gemini` jobs are processed; `mistral` remains `PARSER_UNAVAILABLE`).
- **Document Summarizer (`app/services/summarizer.py`)**:
  - Single summary per document from extracted pages.
  - Context budget check (`SUMMARY_MAX_INPUT_CHARS`): single call if within budget, map-reduce if exceeded.
  - Generates concise summary in the document's language.
  - Empty text rejection: fails with `SUMMARY_FAILED` if extracted text is empty.
- **Resumable Worker Pipeline (`app/worker/processor.py`)**:
  - Staged execution: `queued -> processing` (parse & store pages) -> `summarizing` (atomic transition) -> `done` (store summary & finished timestamp) -> `XACK`.
  - Summary failures preserve stored pages. Retries resume directly at the summary stage without re-parsing.
  - Dead-letter queue dispatching on exhausted attempts or permanent failure.

### In Scope
- OpenAPI 3.1 contract adjustments in `bwaai2-store`.
- Gemini client wrapper, parser, and summarizer in `bwaai2-backend`.
- Resumable pipeline updates in the background worker daemon.
- Unit and integration tests with mocked Gemini client.

### Out of Scope
- Mistral parser implementation (`mistral` continues returning `PARSER_UNAVAILABLE`).
- Frontend React UI changes.

## Capabilities

### New Capabilities
- `gemini-parser`: Multimodal Gemini PDF-to-Markdown parser producing per-page structured JSON with page-count verification against PyPDF.
- `document-summarizer`: Gemini summarizer service with context budget chunking, map-reduce, and language preservation.
- `resumable-pipeline`: Multi-stage worker execution pipeline (`queued -> processing -> summarizing -> done | failed`) preserving pages upon summarization failure.

### Modified Capabilities
None.

## Impact
- **Contracts**: [contracts/openapi.yaml](file:///Users/miguel/git/bwaai2/bwaai2-store/contracts/openapi.yaml) updated with `summarizing` status and `SUMMARY_FAILED` code.
- **Dependencies**: Adds `google-genai` to `bwaai2-backend`.
- **Infrastructure**: Exposes `GEMINI_API_KEY` and worker concurrency settings in Docker Compose.
