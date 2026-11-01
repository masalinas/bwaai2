# Async PDF Processor Frontend

A modern React 18 + TypeScript single-page application for asynchronous PDF document parsing, real-time lifecycle tracking, per-page content inspection (Markdown / plain text), and Gemini executive summaries.

---

## Features

- **Strict OpenAPI Contract Typing**: Consumes types generated directly from `contracts/openapi.yaml` via `openapi-typescript` (`src/api/schema.d.ts`).
- **Drag-and-Drop Ingestion**: Upload 1 to 10 PDF documents with client-side validation against contract limits (PDF MIME type, 25 MB max file size, 10 files max).
- **Extensible Parser Selection**: Supports `pypdf`, `gemini`, and `mistral`. Disabling/enabling options is controlled by a single constant (`DISABLED_PARSERS`). Gracefully handles `PARSER_UNAVAILABLE` errors without application disruption.
- **TanStack Query Polling**: Polls non-terminal documents (`queued`, `processing`, `summarizing`) at ~2s intervals, pausing when tab is hidden, honoring `Retry-After` header hints, and halting on terminal states (`done`, `failed`).
- **Rich Document Viewer**:
  - Pages are visible as soon as parsing completes (during `summarizing` or `done`).
  - GitHub-flavored Markdown rendering for Gemini-extracted pages and summaries; preformatted monospace for PyPDF plain text.
  - Page navigator with previous/next controls.
  - Preserves parsed pages even if summarization fails (`SUMMARY_FAILED`).
- **Export Capabilities**: One-click summary copy to clipboard and full markdown document download (`.md`).
- **CORS-Free Proxy Architecture**: Vite reverse proxy in development and Nginx reverse proxy in production container.

---

## Prerequisites

- **Node.js**: v18.0.0 or later (v22 recommended)
- **npm**: v9.0.0 or later
- **Docker & Docker Compose** (optional, for containerized execution)

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | Base path for frontend API requests |
| `VITE_DEV_PROXY_TARGET` | `http://localhost:8000` | Target URL for Vite dev server reverse proxy |
| `BACKEND_URL` | `http://api:8000` | Target URL for Nginx production reverse proxy in Docker |
| `CONTRACT_PATH` | `../bwaai2-store/contracts/openapi.yaml` | Path to authoritative contract for `npm run gen:api` |

---

## Available Scripts

```bash
# Start local development server with HMR and proxy at http://localhost:3000
npm run dev

# Run TypeScript typecheck and build optimized production bundle
npm run build

# Preview production build locally
npm run preview

# Run automated test suite with Vitest and MSW
npm run test

# Run ESLint linter
npm run lint

# Format code with Prettier
npm run format

# Check formatting without writing
npm run format:check

# Regenerate TypeScript definitions from OpenAPI contract
npm run gen:api
```

---

## Running the Full Stack

### Option A: Local Development (Vite + FastAPI + Redis)

1. **Start Redis and Backend API**:
   In `../bwaai2-backend`:
   ```bash
   # In terminal 1 (start Redis)
   docker run -d -p 6379:6379 --name local-redis redis:7-alpine

   # In terminal 2 (start API)
   uv run uvicorn app.main:app --reload --port 8000

   # In terminal 3 (start worker)
   uv run python -m app.worker
   ```

2. **Start Frontend Dev Server**:
   In `bwaai2-frontend`:
   ```bash
   npm install
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) in your browser. All requests to `/api/*` are automatically proxied to `http://localhost:8000/*`.

---

### Option B: Containerized Execution with Docker Compose

1. **Create shared Docker network**:
   ```bash
   docker network create bwaai2
   ```

2. **Start Backend & Redis**:
   In `../bwaai2-backend`:
   ```bash
   docker compose up -d
   # Connect the backend container to the shared network:
   docker network connect bwaai2 pdf_api
   ```

3. **Start Frontend Container**:
   In `bwaai2-frontend`:
   ```bash
   docker compose up --build -d
   ```
   Access the web application at [http://localhost:3000](http://localhost:3000). Nginx proxies all `/api/` traffic directly to `http://api:8000/`.

---

## End-to-End Walkthrough with Sample PDF

1. **Create a minimal test PDF**:
   ```bash
   python3 -c "from pypdf import PdfWriter; w = PdfWriter(); w.add_blank_page(200, 200); w.write('sample_doc.pdf')"
   ```
2. **Open Frontend**:
   Navigate to [http://localhost:3000](http://localhost:3000).
3. **Upload Document**:
   Drag and drop `sample_doc.pdf` into the upload zone (or click "Choose files"), leave parser as `PyPDF` (or select `Gemini 2.5 Flash`), and click **Upload & Process (1)**.
4. **Observe Real-Time Lifecycle**:
   - The document immediately appears at the top of the list in **Queued** state.
   - TanStack Query automatically polls the status: badge transitions to **Processing** -> **Summarizing** -> **Done**.
5. **Inspect Results**:
   - In **Summarizing** state, extracted pages become readable immediately with a placeholder for the summary.
   - In **Done** state, the Gemini executive summary appears at the top.
   - Click **Copy** to copy the summary to clipboard, or click **Download .md** to download the consolidated markdown export.
