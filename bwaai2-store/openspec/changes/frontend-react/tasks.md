# Tasks

## 1. Store Specification

- [x] 1.1 [store] Author OpenSpec change `frontend-react` (`proposal.md`, `design.md`, `specs/`, `tasks.md`).
- [x] 1.2 [store] Verify OpenSpec validity with `openspec validate frontend-react --strict`.

## 2. Frontend Project Setup & Typed Client

- [x] 2.1 [frontend] Initialize Vite + React 18 + TypeScript project structure with Tailwind CSS, Lucide icons, ESLint, and Prettier in `bwaai2-frontend`.
- [x] 2.2 [frontend] Implement `npm run gen:api` script using `openapi-typescript` targeting `contracts/openapi.yaml` and commit `src/api/schema.d.ts`.
- [x] 2.3 [frontend] Create typed API client in `src/api/client.ts` with custom `ApiError` class consuming contract schemas without manual duplication.
- [x] 2.4 [frontend] Define parser configuration and extensibility in `src/config/parsers.ts` (`AVAILABLE_PARSERS`, `DISABLED_PARSERS = ['mistral']`).

## 3. UI Components

- [x] 3.1 [frontend] Implement `UploadArea` component with drag-and-drop, file picker, parser selector, client validation (type, 25MB max size, 10 files max), and upload mutation.
- [x] 3.2 [frontend] Implement `DocumentList` component displaying filename, parser, status badge, timestamps, and cursor pagination ("Load More").
- [x] 3.3 [frontend] Implement `StatusBadge` component supporting all statuses (`queued`, `processing`, `summarizing`, `done`, `failed`) with accessible aria indicators.
- [x] 3.4 [frontend] Implement `DocumentViewer` component rendering executive summary, markdown/text page views, page navigation, error card with page retention, and copy/download export buttons.

## 4. TanStack Query & Polling Lifecycle

- [x] 4.1 [frontend] Configure `QueryClient` with intelligent retries, caching, and tab-visibility awareness.
- [x] 4.2 [frontend] Implement `useDocumentStatus` hook polling `GET /documents/{id}/status` every ~2s, honoring `Retry-After`, and stopping on terminal states (`done`, `failed`).
- [x] 4.3 [frontend] Implement `useDocumentDetail` hook fetching full details and synchronizing when status transitions to `summarizing` or `done`.

## 5. Automated Testing (Vitest + RTL + MSW)

- [x] 5.1 [frontend] Set up Vitest, jsdom, and MSW handlers typed from contract schemas.
- [x] 5.2 [frontend] Test upload happy path and status polling lifecycle (`queued -> processing -> summarizing -> done`).
- [x] 5.3 [frontend] Test client-side validation errors (non-PDF, oversized file, batch limit).
- [x] 5.4 [frontend] Test graceful handling of `PARSER_UNAVAILABLE` on upload.
- [x] 5.5 [frontend] Test `failed` document error display and page retention when summarization fails.
- [x] 5.6 [frontend] Test pagination ("Load More") and polling termination on terminal states.

## 6. Docker, Proxy & Documentation

- [x] 6.1 [frontend] Configure Vite dev server reverse proxy for `/api/` targeting local backend.
- [x] 6.2 [frontend] Create multi-stage `Dockerfile` and Nginx reverse proxy configuration (`nginx.conf`).
- [x] 6.3 [frontend] Create `docker-compose.yml` configured to connect to backend network.
- [x] 6.4 [frontend] Author `README.md` in `bwaai2-frontend` with prerequisites, scripts, full stack run instructions, and manual E2E walkthrough.
- [x] 6.5 [frontend] Run full verification: typecheck, lint, build, and test suite.
