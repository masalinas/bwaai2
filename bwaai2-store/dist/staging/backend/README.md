# Async PDF Processor Backend

FastAPI backend and asynchronous Redis Streams worker for PDF document ingestion, PyPDF text extraction, Gemini multimodal PDF parsing (markdown), Mistral OCR extraction (markdown), executive AI summarization, and lifecycle tracking.

## Architecture

- **API Service**: FastAPI application accepting batch uploads (`POST /documents`), validating files, saving binaries with TTL, enqueuing tasks to Redis Streams (`documents:jobs`), and providing query/status endpoints.
- **Worker Daemon**: Asynchronous consumer group daemon (`documents:workers`) reading from `documents:jobs`, processing documents across a two-stage resumable pipeline:
  1. **Stage 1 (Parsing)**: Extracts text using PyPDF (`pypdf`, plain text), Gemini 3.8 Flash (`gemini`, structured markdown), or Mistral OCR (`mistral`, structured markdown via OCR). Stores pages in Redis.
  2. **Stage 2 (Summarization)**: Generates an executive summary using Gemini with single-pass or map-reduce chunking, preserving the document's language.
- **Redis 7**: Shared in-memory data store for metadata hashes (`doc:{id}`), page results (`doc:{id}:pages`), summary text (`doc:{id}:summary`), binary files (`doc:{id}:file`), index sorted sets (`docs:index`), and task streams (`documents:jobs`, `documents:dead`).

---

## Configuration & Environment Variables

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Connection string for Redis 7 |
| `GEMINI_API_KEY` | `""` | Google AI Studio Gemini API Key |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model name for multimodal parsing and summarization |
| `GEMINI_CONCURRENCY` | `2` | Max concurrent Gemini API requests (protects 15 RPM free tier) |
| `GEMINI_TIMEOUT_SECONDS`| `60` | Request timeout for Gemini API calls |
| `MISTRAL_API_KEY` | `""` | Mistral AI API Key for OCR document processing |
| `MISTRAL_OCR_MODEL` | `mistral-ocr-latest` | Mistral OCR model name |
| `MISTRAL_CONCURRENCY` | `2` | Max concurrent Mistral API requests |
| `MISTRAL_TIMEOUT_SECONDS`| `60` | Request timeout for Mistral OCR API calls |
| `MISTRAL_INLINE_THRESHOLD_BYTES`| `10485760` (10MB) | File size threshold for base64 inline vs Files API upload |
| `SUMMARY_MAX_INPUT_CHARS`| `100000` | Character threshold before switching from single-pass to map-reduce |
| `MAX_FILE_SIZE_BYTES` | `26214400` (25MB) | Maximum file size per uploaded PDF |
| `MAX_FILES_PER_REQUEST`| `10` | Maximum number of files accepted in a batch upload |
| `MAX_ATTEMPTS` | `3` | Maximum retry attempts before routing to Dead Letter Queue (`documents:dead`) |
| `RETRY_BACKOFF_BASE_SECONDS` | `2` | Base exponential backoff multiplier for retries |

### Getting API Keys

#### Google Gemini API Key
1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Sign in with your Google account and click **Create API Key**.
3. Copy your key and add it to your `.env` file:
   ```bash
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

#### Mistral AI API Key
1. Visit [Mistral AI Console](https://console.mistral.ai/).
2. Sign in or register and navigate to **API Keys**.
3. Click **Create new key**, copy it, and add it to your `.env` file:
   ```bash
   MISTRAL_API_KEY=your_mistral_api_key_here
   ```

---

## Running the Services

### 1. Docker Compose (API + Redis + Worker)

Create your `.env` file (copying `.env.example` and providing `GEMINI_API_KEY`):
```bash
cp .env.example .env
# Edit .env with your GEMINI_API_KEY
```

Start all services:
```bash
make up
# or: docker compose up --build
```

### 2. Scaling Workers

Scale the worker daemon to multiple parallel instances:
```bash
docker compose up --scale worker=3
```
Each worker automatically registers with a unique consumer identifier (`hostname-pid-uuid`) on the `documents:workers` consumer group, enabling distributed, parallel job execution without conflicts.

### 3. Running Locally with UV

Start Redis:
```bash
docker run -d -p 6379:6379 --name local-redis redis:7-alpine
```

Run the API:
```bash
uv run uvicorn app.main:app --reload --port 8000
```

Run the Worker in a separate terminal:
```bash
make worker
# or: uv run python -m app.worker
```

Run Tests & Linter:
```bash
make test
make lint
```

---

## Document Lifecycle & Status Transitions

```
[Upload] -> queued -> processing -> summarizing -> done
                           |             |
                           v             v
                         failed        failed (pages preserved)
```

- `queued`: File uploaded, stored in Redis, and job enqueued in Redis Stream.
- `processing`: Worker has claimed the job and is parsing pages (`pypdf`, `gemini`, or `mistral`).
- `summarizing`: Pages have been parsed and stored in Redis. Worker is generating the executive summary with Gemini.
- `done`: Parsing and summarization complete.
- `failed`: Job encountered an unrecoverable error. If failure occurred during summarization (`SUMMARY_FAILED` or `SUMMARY_RATE_LIMITED`), parsed pages remain accessible in `GET /documents/{id}`!

---

## End-to-End Walkthrough with cURL

### 1. Upload Document with Mistral OCR Parser

```bash
curl -X POST http://localhost:8000/documents \
  -F "files=@financial_statement.pdf;type=application/pdf" \
  -F "parser=mistral"
```

Response (202 Accepted):
```json
[
  {
    "document_id": "doc_01j9a8b7c6d5e4f3a2b1c0d9e8",
    "filename": "financial_statement.pdf",
    "status": "queued"
  }
]
```

*(Alternatively, use `-F "parser=gemini"` or `-F "parser=pypdf"`)*

### 2. Poll Status Endpoint

```bash
curl -i http://localhost:8000/documents/doc_01j9a8b7c6d5e4f3a2b1c0d9e8/status
```

Response while in `summarizing` stage (pages are already extracted):
```http
HTTP/1.1 200 OK
Retry-After: 3
Content-Type: application/json

{
  "document_id": "doc_01j9a8b7c6d5e4f3a2b1c0d9e8",
  "status": "summarizing",
  "created_at": "2026-10-31T00:00:00Z",
  "updated_at": "2026-10-31T00:00:03Z",
  "error": null
}
```

### 3. Fetch Document While Summarizing (Early Page Availability)

```bash
curl http://localhost:8000/documents/doc_01j9a8b7c6d5e4f3a2b1c0d9e8
```

Response:
```json
{
  "document_id": "doc_01j9a8b7c6d5e4f3a2b1c0d9e8",
  "filename": "annual_report.pdf",
  "parser": "gemini",
  "status": "summarizing",
  "created_at": "2026-10-31T00:00:00Z",
  "updated_at": "2026-10-31T00:00:03Z",
  "pages": [
    {
      "page_number": 1,
      "content": "# Fiscal Year 2026 Report\n\nRevenue grew by 24% year-over-year...",
      "format": "markdown"
    }
  ],
  "summary": null,
  "error": null
}
```

### 4. Fetch Completed Document Details

```bash
curl http://localhost:8000/documents/doc_01j9a8b7c6d5e4f3a2b1c0d9e8
```

Response:
```json
{
  "document_id": "doc_01j9a8b7c6d5e4f3a2b1c0d9e8",
  "filename": "annual_report.pdf",
  "parser": "gemini",
  "status": "done",
  "created_at": "2026-10-31T00:00:00Z",
  "updated_at": "2026-10-31T00:00:06Z",
  "pages": [
    {
      "page_number": 1,
      "content": "# Fiscal Year 2026 Report\n\nRevenue grew by 24% year-over-year...",
      "format": "markdown"
    }
  ],
  "summary": "This report highlights a 24% YoY revenue growth in FY2026, driven primarily by enterprise expansion.",
  "error": null
}
```
