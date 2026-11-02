# Design: React Frontend Integration

## Overview

The React frontend for the Async PDF Processing application provides a lightweight, responsive, and robust single-page interface to upload PDFs, monitor asynchronous processing status in real time, view extracted pages with rendered Markdown or plain text, and read executive summaries.

---

## 1. Stack Choices and Rationale

| Layer | Choice | Rationale |
|---|---|---|
| **Build Tool & Framework** | Vite + React 18 + TypeScript (strict) | Vite provides sub-second HMR and optimal production bundling. Strict TypeScript ensures contract compliance without runtime regressions. |
| **Server State & Polling** | TanStack Query (`@tanstack/react-query` v5) | Solves server-state synchronization, cache deduplication, pagination, and polling (`refetchInterval`) natively without custom hand-rolled timer loops. Automatically handles tab visibility pausing and error backoff. |
| **Styling** | Tailwind CSS v3 | Utility-first CSS provides deterministic styling, minimal CSS bundle footprint, responsive layouts, and eliminates CSS-in-JS runtime overhead. |
| **Markdown Rendering** | `react-markdown` + `remark-gfm` | Renders GitHub-flavored Markdown for Gemini-parsed pages and executive summaries safely without `dangerouslySetInnerHTML`. |
| **Icons** | `lucide-react` | Tree-shakeable SVG icons for copy, download, file status badges, spinners, and upload indicators. |
| **Testing** | Vitest + React Testing Library + MSW | Vitest shares Vite's config for instant unit execution. MSW intercepts network requests using contract-typed handlers without hitting live backends. |
| **Package Manager** | npm | Standard, zero-install-overhead package manager ensuring cross-platform reproducibility. |

---

## 2. Typed API Client Generation

The frontend treats `contracts/openapi.yaml` as the authoritative single source of truth:

1. **Generation Command**:
   `npm run gen:api` executes:
   ```bash
   openapi-typescript ${CONTRACT_PATH:-../bwaai2-store/contracts/openapi.yaml} -o src/api/schema.d.ts
   ```
   The generated `src/api/schema.d.ts` is committed to source control so `bwaai2-frontend` can build and pass type checks independently.
2. **Type Extraction**:
   Type aliases are derived directly from the generated schema in `src/api/types.ts`:
   ```ts
   import type { components, operations, paths } from './schema';
   export type DocumentStatus = components['schemas']['DocumentStatus'];
   export type ParserType = components['schemas']['ParserType'];
   export type DocumentUploadItem = components['schemas']['DocumentUploadItem'];
   export type DocumentDetailResponse = components['schemas']['DocumentDetailResponse'];
   export type DocumentStatusResponse = components['schemas']['DocumentStatusResponse'];
   export type DocumentListResponse = components['schemas']['DocumentListResponse'];
   export type DocumentPage = components['schemas']['DocumentPage'];
   export type ApiErrorSchema = components['schemas']['Error'];
   export type ErrorCode = components['schemas']['ErrorCode'];
   ```
   No duplicate hand-written models exist.
3. **Thin Typed Client (`src/api/client.ts`)**:
   A wrapper around `fetch` provides typed helper functions:
   - `uploadDocuments(files: File[], parser: ParserType): Promise<DocumentUploadItem[]>`
   - `listDocuments(limit?: number, cursor?: string | null): Promise<DocumentListResponse>`
   - `getDocumentDetail(documentId: string): Promise<DocumentDetailResponse>`
   - `getDocumentStatus(documentId: string): Promise<{ data: DocumentStatusResponse; retryAfter?: number }>`
   - `getHealth(): Promise<components['schemas']['HealthResponse']>`
4. **Error Handling (`ApiError`)**:
   When the API returns a non-2xx status code, the response body is parsed against the contract's `Error` schema:
   ```ts
   export class ApiError extends Error {
     constructor(
       public readonly status: number,
       public readonly code: ErrorCode | string,
       message: string,
       public readonly details?: unknown
     ) {
       super(message);
       this.name = 'ApiError';
     }
   }
   ```

---

## 3. Polling Strategy

Instead of error-prone manual `setInterval` or `setTimeout` chains, status polling is orchestrated through TanStack Query:

1. **Trigger Condition**:
   Documents in non-terminal states (`queued`, `processing`, `summarizing`) are polled for status updates.
2. **Polling Frequency & Retry-After**:
   Default polling interval is 2,000ms (`POLL_INTERVAL_MS = 2000`). If the backend returns a `Retry-After` header (e.g., 3s), the query adjusts its next interval accordingly:
   ```ts
   refetchInterval: (query) => {
     const status = query.state.data?.data.status;
     if (status === 'done' || status === 'failed') {
       return false; // Stop polling on terminal states
     }
     const retryAfter = query.state.data?.retryAfter;
     return retryAfter ? retryAfter * 1000 : POLL_INTERVAL_MS;
   }
   ```
3. **Tab Visibility**:
   TanStack Query automatically pauses background polling when the browser tab is hidden or minimized (`refetchIntervalInBackground: false`), preserving network bandwidth and battery.
4. **Transient Error Resilience**:
   Query retry backoff (`retry: 3`, exponential backoff) allows polling to survive brief network dropouts without halting UI tracking.
5. **Cache Invalidation & Result Synchronization**:
   When status transitions to `summarizing` or `done`, the document detail query for `GET /documents/{id}` is automatically refetched to display freshly available pages or summaries.

---

## 4. Handling Document Status Lifecycle

The UI tracks the 5 documented statuses (`queued`, `processing`, `summarizing`, `done`, `failed`):

```
[Upload] -> queued -> processing -> summarizing -> done
                           |             |
                           v             v
                         failed        failed (pages preserved)
```

1. **`queued`**:
   - Status badge: Yellow/Amber outline ("Queued").
   - Action: Polling active. Viewer shows waiting placeholder.
2. **`processing`**:
   - Status badge: Blue animated spinner ("Parsing PDF...").
   - Action: Polling active. Page extraction in progress.
3. **`summarizing`**:
   - Status badge: Purple pulse ("Summarizing...").
   - Action: Polling active.
   - Result Viewer: **Pages are immediately rendered!** The user can read and navigate extracted pages right away. An animated placeholder card is displayed at the top for the summary: *"Generating executive summary with Gemini..."*.
4. **`done`**:
   - Status badge: Emerald green checkmark ("Completed").
   - Action: Polling terminates. Executive summary is rendered above pages. Full markdown export and summary copy are enabled.
5. **`failed`**:
   - Status badge: Crimson red alert ("Failed").
   - Action: Polling terminates.
   - Result Viewer: Shows error card with error `code` and friendly `message`. If failure occurred during summarization (`SUMMARY_FAILED` or `SUMMARY_RATE_LIMITED`), **previously parsed pages are retained and visible**.

---

## 5. Reverse Proxy Architecture vs. CORS

To avoid browser CORS blocks and eliminate the need for cross-origin credentials configuration:

1. **Development Environment (Vite Proxy)**:
   In `vite.config.ts`:
   ```ts
   server: {
     proxy: {
       '/api': {
         target: process.env.VITE_DEV_PROXY_TARGET || 'http://localhost:8000',
         changeOrigin: true,
         rewrite: (path) => path.replace(/^\/api/, ''),
       },
     },
   }
   ```
   Browser requests to `/api/documents` are proxied to `http://localhost:8000/documents`.
2. **Production Environment (Nginx Reverse Proxy)**:
   A lightweight Nginx Alpine container acts as both SPA static host and API gateway:
   ```nginx
   server {
       listen 80;
       server_name _;

       location / {
           root /usr/share/nginx/html;
           try_files $uri $uri/ /index.html;
       }

       location /api/ {
           proxy_pass http://${BACKEND_HOST}:${BACKEND_PORT}/;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```
   All requests flow same-origin from the browser's perspective.

---

## 6. Configurable Parser Options (Mistral Extensibility)

Parser selection is driven by configuration constants in `src/config/parsers.ts`:

```ts
export const AVAILABLE_PARSERS: { id: ParserType; name: string; description: string }[] = [
  { id: 'pypdf', name: 'PyPDF', description: 'Fast plain-text extraction' },
  { id: 'gemini', name: 'Gemini 3.8 Flash', description: 'Multimodal markdown extraction' },
  { id: 'mistral', name: 'Mistral OCR', description: 'Document OCR (Coming soon)' },
];

export const DISABLED_PARSERS: ParserType[] = ['mistral'];
```

- When Mistral parser is implemented on the backend in the future, enabling it on the frontend requires removing `'mistral'` from `DISABLED_PARSERS`.
- If an unavailable parser is selected (e.g. by setting `DISABLED_PARSERS = []` or testing direct requests), the backend returns 500 with `PARSER_UNAVAILABLE`. The frontend gracefully captures this error, displays the message on the affected document, and leaves the rest of the application completely usable.

---

## 7. Assumptions, Backend Issues, and Contract Issues

### Assumptions
1. Single-page UI with side-by-side or stacked split layout: left column for Upload Area & Document List; right column for Document Result Viewer. On smaller screens, stacks responsively.
2. The user can switch between pages using previous/next buttons or a page dropdown selector.
3. Full markdown download produces a `.md` file named `{document_id}_{filename}.md` containing the executive summary header followed by each page's content.

### Contract Issues
- The contract specifies `POST /documents` returning `202 Accepted` with an array of `DocumentUploadItem`. However, if an invalid file type or oversized file is included in a batch, the backend returns a 4xx error for the whole request. The frontend provides proactive client-side validation to catch invalid files, oversized files (>25MB), or batches exceeding 10 files *before* network submission.

### Backend Issues
- Backend CORS middleware is configured for wildcard origins, but in containerized environments browser access to container hostnames can fail without host port mapping. The frontend solves this by configuring an Nginx proxy in Docker and a Vite proxy in dev mode so the frontend always communicates same-origin via `/api/`.
