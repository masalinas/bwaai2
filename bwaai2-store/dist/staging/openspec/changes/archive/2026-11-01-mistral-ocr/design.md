# Design: Mistral OCR Document Parser Integration

## Overview

The Mistral OCR integration introduces `MistralParser` as the third parsing engine for the asynchronous PDF processor. Mistral OCR processes complex layout documents and produces high-quality Markdown. It runs seamlessly within the existing two-stage worker architecture (`processing` -> `summarizing` -> `done`).

---

## 1. Verified Official Mistral API & SDK Details

Prior to implementation, the official Mistral OCR documentation and installed Python package were verified:

- **SDK Package**: `mistralai>=1.5.0` (tested and verified with `mistralai==3.6.0`).
- **Client Instantiation**:
  ```python
  from mistralai.client import Mistral # or from mistralai import Mistral
  client = Mistral(api_key=settings.MISTRAL_API_KEY)
  ```
- **Primary Async Method**: `client.ocr.process_async(model=..., document=..., include_image_base64=False)`
- **Default Model**: `mistral-ocr-latest`.
- **Response Structure**:
  - `response.pages` is a list of page objects (`OCRPageObject`).
  - Each item contains `markdown: str` (the page text formatted as Markdown) and `index: int` (0-indexed page index).
- **Files API Async Methods**:
  - `client.files.upload_async(file={"file_name": ..., "content": ...}, purpose="ocr")`
  - `client.files.get_signed_url_async(file_id=...)`
  - `client.files.delete_async(file_id=...)`
- **Exception Hierarchy**:
  - `mistralai.client.errors.SDKError` with `status_code: int`, `message: str`, and `body: str`.

---

## 2. Ingestion & Payload Strategy (Inline vs. Files API)

Mistral OCR supports both inline data URIs and signed URLs:

- **Threshold**: **10 MB** (10,485,760 bytes, defined by `MISTRAL_INLINE_THRESHOLD_BYTES = 10 * 1024 * 1024`).
- **Inline Payload ($\le$ 10 MB)**:
  Binary PDF bytes are base64-encoded and transmitted as a data URI:
  ```python
  encoded_data = base64.b64encode(pdf_bytes).decode("utf-8")
  document = {
      "type": "document_url",
      "document_url": f"data:application/pdf;base64,{encoded_data}",
  }
  ```
  This eliminates intermediate file upload latency for typical documents.
- **Files API Payload (> 10 MB up to 25 MB)**:
  Larger PDFs are uploaded asynchronously using Mistral's file management endpoints:
  ```python
  uploaded = await client.files.upload_async(
      file={"file_name": "document.pdf", "content": pdf_bytes},
      purpose="ocr",
  )
  try:
      signed_url = await client.files.get_signed_url_async(file_id=uploaded.id)
      document = {
          "type": "document_url",
          "document_url": signed_url.url,
      }
      response = await client.ocr.process_async(...)
  finally:
      await client.files.delete_async(file_id=uploaded.id)
  ```
  The `try ... finally` block guarantees that uploaded files are immediately cleaned up after OCR processing completes or fails.
- **Image Option**: `include_image_base64=False` is set to avoid downloading heavy embedded image payloads, reducing network overhead and memory footprint.

---

## 3. Page Count Verification and Retry Policy

To guard against OCR page omission:

1. **Ground Truth Detection**:
   PyPDF inspects the raw PDF bytes off-thread to obtain the true page count:
   ```python
   def _get_page_count(pdf_bytes: bytes) -> int:
       reader = PdfReader(io.BytesIO(pdf_bytes))
       return len(reader.pages)
   ```
2. **Comparison**:
   The number of pages in `ocr_response.pages` must strictly equal `expected_count`.
3. **One-Attempt Retry**:
   If the counts mismatch on the first attempt, `MistralParser` logs a warning and retries the OCR call once.
4. **Mismatch Failure**:
   If the second attempt also returns a mismatched page count, `ParserFailedError` is raised with code `PARSER_FAILED`, routing the job to the dead-letter queue.

---

## 4. Concurrency, Rate Limiting, and Error Classification

To prevent overwhelming the Mistral API and handle rate limits reliably:

- **Concurrency Limiting**:
  All Mistral OCR network requests are guarded by an `asyncio.Semaphore(settings.MISTRAL_CONCURRENCY)` (default `2`).
- **Request Timeout**:
  Enforced via `asyncio.wait_for` using `settings.MISTRAL_TIMEOUT_SECONDS` (default `60`).
- **Error Classification**:
  - **Transient Errors**:
    - HTTP 429 (`RESOURCE_EXHAUSTED` / rate limit / quota exceeded).
    - HTTP 5xx (internal server errors).
    - Network connection errors, socket drops, and request timeouts.
    - Behavior: Raises `ParserRateLimitedError` or `ParserTransientError`. The worker catches these, logs a warning, and leaves the message unacknowledged in Redis Streams for exponential backoff redelivery up to `MAX_ATTEMPTS`.
  - **Permanent Errors**:
    - HTTP 4xx (e.g. 400 Bad Request, 422 Unprocessable Document, invalid format).
    - Behavior: Raises `ParserFailedError`. The worker marks the document `failed` with code `PARSER_FAILED`, routes it to `documents:dead`, and acknowledges the message immediately.

---

## 5. Missing Key Behavior

If `MISTRAL_API_KEY` is not provided (empty string):
- The API and worker start normally without crashing.
- PyPDF and Gemini parsing continue to work without disruption.
- If a document is submitted with `parser=mistral`:
  - `POST /documents` raises HTTP 500 with `PARSER_UNAVAILABLE` and message: `"Mistral parser is not configured: MISTRAL_API_KEY is not set."`
  - If a job is already queued in Redis Streams, `MistralParser.parse(...)` raises `ParserUnavailableError`, which transitions the document to `failed` (`PARSER_UNAVAILABLE`) and acknowledges the job.

---

## 6. Frontend Activation

In `bwaai2-frontend/src/config/parsers.ts`:
- The constant `DISABLED_PARSERS` is updated from `['mistral']` to `[]`.
- The frontend parser selector now allows users to choose `Mistral OCR`.
- The corresponding unit test in `tests/upload.test.tsx` is updated to reflect that Mistral is selectable.

---

## 7. Assumptions

1. The Mistral OCR API does not require pre-processing or page rasterization on the client; binary PDF upload is standard.
2. The maximum file size accepted by our application is 25 MB (per OpenAPI contract), which is well within Mistral's 50 MB / 512 MB file limits.
3. Extracted markdown pages from Mistral are passed directly to `DocumentSummarizer`, which preserves the document's language and follows the existing multi-stage pipeline.
