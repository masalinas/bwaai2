# Design: Gemini Summary and Parsing Integration

## Context

The system previously accepted uploads and used PyPDF for plain-text extraction without summarization or multimodal parsing. This design introduces Gemini multimodal parsing (PDF-to-Markdown) and automated document summarization across all parsers, while adding a `summarizing` status lifecycle stage that lets clients access parsed pages immediately.

## Goals / Non-Goals

**Goals:**
- Update OpenAPI 3.1 contract in `bwaai2-store/contracts/openapi.yaml` with `summarizing` status, `SUMMARY_FAILED` error code, and updated descriptions/examples.
- Implement Gemini client service using official `google-genai` SDK with concurrency throttling, exponential backoff, and free-tier quota protection.
- Implement `GeminiParser` with structured JSON schema output and ground-truth page count verification against PyPDF.
- Implement `DocumentSummarizer` with context-budget map-reduce chunking, language preservation, and scanned PDF detection.
- Upgrade the worker processing pipeline to be staged and resumable, preserving extracted pages upon summarization failure.

**Non-Goals:**
- Implementing the Mistral parser (`mistral` continues returning `PARSER_UNAVAILABLE`).
- Frontend UI modifications.
- Live API calls during automated tests (all Gemini interactions are mocked).

## Decisions

### 1. Document Lifecycle & Resumable Staged Processing
- **Lifecycle**: `queued -> processing -> summarizing -> done | failed`.
- **Resumable Stages**:
  1. *Stage 1 (Parse)*: Worker checks if `doc:{id}:pages` already exists. If missing, runs parser and saves page results.
  2. *State Transition*: Worker atomically sets `status = summarizing` in `doc:{id}` hash.
  3. *Stage 2 (Summarize)*: Loads pages, calls `DocumentSummarizer`, writes summary to `doc:{id}:summary`, and marks `status = done`.
  4. *Acknowledge*: Calls `XACK` on `documents:jobs` only after both stages succeed.
- **Resumption**: If a worker crashes or is throttled during Stage 2, the redelivered job observes that pages are already in Redis and skips Stage 1 completely, avoiding redundant LLM or CPU parsing.

### 2. Failure Semantics & Page Retention
- If summarization fails permanently (e.g. prompt blocked, empty scanned text) or exhausts `MAX_ATTEMPTS` (rate limiting), the document is marked `failed` with code `SUMMARY_FAILED` or `SUMMARY_RATE_LIMITED`.
- **Page Preservation**: `doc:{id}:pages` is never deleted. The API endpoint `GET /documents/{document_id}` serves the extracted pages whenever status is `summarizing`, `done`, or `failed` (if parsing succeeded).

### 3. Inline Data vs. Files API Threshold
- **Threshold**: 10 MB (`10,485,760` bytes).
- Documents $\le$ 10 MB are sent directly as base64 inline bytes within the multimodal request (`types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")`), eliminating additional network roundtrips.
- Documents > 10 MB are uploaded via the Gemini Files API (`client.files.upload`), referenced in the generation prompt, and deleted after parsing.

### 4. Summarization Chunking & Language Preservation
- **Budget**: `SUMMARY_MAX_INPUT_CHARS` (default: 100,000 characters, ~25,000 tokens).
- **Single Pass**: If total document text is within budget, a single Gemini call produces the summary.
- **Map-Reduce**: If total text exceeds budget:
  - Text is split into chunks of ~50,000 characters.
  - Each chunk is summarized individually.
  - Intermediate summaries are concatenated and summarized into the final output.
- **Language**: The summarization prompt instructs Gemini in English to produce the summary strictly in the primary language of the source document.
- **Scanned PDF Rejection**: If all pages have empty text (common when PyPDF attempts to parse an image-only scanned document), the summarizer raises `SummaryFailedError` with the message: *"Document contains no extractable text. Please re-upload using the 'gemini' multimodal parser."*

### 5. Gemini Rate Limiting & Concurrency Control
- Free-tier Gemini limits (typically 15 RPM for flash models) require strict client-side pacing.
- A global `asyncio.Semaphore(GEMINI_CONCURRENCY)` (default: 2) bounds simultaneous outbound calls.
- Calls encountering HTTP 429 or `ResourceExhausted` errors execute exponential backoff with randomized jitter and honor `Retry-After` headers when provided.

## Configuration Table

| Environment Variable | Type | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | string | `""` | Google Gemini API key |
| `GEMINI_MODEL` | string | `gemini-2.5-flash` | Gemini model identifier for parsing and summarization |
| `GEMINI_CONCURRENCY` | integer | `2` | Max concurrent Gemini requests per worker instance |
| `GEMINI_TIMEOUT_SECONDS` | integer | `60` | Request timeout for individual Gemini API calls |
| `SUMMARY_MAX_INPUT_CHARS` | integer | `100000` | Character threshold for triggering map-reduce summarization |

## Risks / Trade-offs

- **[Risk] Gemini rate limits (429) during batch summarization**  
  *Mitigation*: Concurrency semaphore (default 2), exponential backoff, and redelivery through Redis Streams with pages already saved.
- **[Risk] Gemini multimodal parser page count hallucination**  
  *Mitigation*: The parser compares extracted page count against PyPDF's ground-truth page count. It retries once on mismatch; if the count still disagrees, it aborts with `PARSER_FAILED`.
- **[Risk] API Key exposure in logs**  
  *Mitigation*: Keys are loaded strictly from environment variables and never logged.
