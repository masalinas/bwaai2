# Proposal: React Frontend Integration

## Why

With the backend API, Redis Streams worker, and Gemini multimodal parsing and summarization pipelines fully implemented and verified, users require an accessible, reliable, single-page web interface to upload PDF documents, track background parsing and summarization in real time, and inspect extracted page content and executive summaries.

## What Changes

This change specifies and implements the React + TypeScript frontend application in `bwaai2-frontend`:

### Store (`bwaai2-store`)
- Specifications, architectural design, component behaviors, and implementation tasks stored under `openspec/changes/frontend-react/`.
- The authoritative contract at `contracts/openapi.yaml` remains strictly unmodified as the single source of truth.

### Frontend (`bwaai2-frontend`)
- **Technology Stack**: Vite + React 18 + TypeScript (strict mode), TanStack Query for caching and polling, `react-markdown` + `remark-gfm` for Markdown rendering, Tailwind CSS for lightweight responsive design, and npm.
- **Typed API Client**:
  - `npm run gen:api` executes `openapi-typescript` against `contracts/openapi.yaml` to generate `src/api/schema.d.ts`.
  - Type-safe fetch client wrapper in `src/api/client.ts` consuming the generated types directly with no duplicated manual interfaces.
  - Contract error schema parsing into a structured `ApiError` class.
- **Single-Page Application UI**:
  - **Upload Area**: Drag-and-drop and file picker supporting 1..10 PDFs, client-side validation for MIME type (`application/pdf`), maximum file size (25MB), and maximum file count (10).
  - **Parser Selector**: Supports `pypdf`, `gemini`, and `mistral` from contract enum. Default `pypdf`. Disabling options is driven by a single configuration constant (`DISABLED_PARSERS`). Handles `PARSER_UNAVAILABLE` gracefully.
  - **Documents List**: Chronological order (newest first), displaying status badges (`queued`, `processing`, `summarizing`, `done`, `failed`), timestamps, and pagination ("Load more").
  - **Smart Polling**: Polls `GET /documents/{id}/status` using TanStack Query `refetchInterval` (~2s, honoring `Retry-After` if present), automatically stopping on terminal states (`done`, `failed`) and pausing when the browser tab is hidden.
  - **Document Detail Viewer**: Renders executive summary and page contents (Markdown rendered for `gemini`, preformatted text for `pypdf`) with page navigator. While `summarizing`, shows available pages and a summary placeholder. When `failed`, retains pages if parsed and displays error details.
  - **Export Utilities**: One-click summary copy to clipboard and full markdown export download (`.md`).
- **Testing**:
  - Vitest + React Testing Library + Mock Service Worker (MSW) mocking contract-typed API responses.
  - Test suites covering upload happy path, validation errors, polling transitions (`queued -> processing -> summarizing -> done`), `PARSER_UNAVAILABLE` resilience, `failed` state page retention, and pagination.
- **Deployment & Docker**:
  - Multi-stage Dockerfile (Node build -> Nginx Alpine static server).
  - Nginx configuration serving the SPA with history fallback and reverse proxying `/api/` to backend to avoid CORS restrictions.
  - `docker-compose.yml` configured to connect to the backend container network.
  - Vite dev server reverse proxy for local development.

### In Scope
- Frontend application layout, typed API layer, UI components, polling lifecycle, export tools, unit/integration tests, Dockerfile, docker-compose, and documentation in `bwaai2-frontend`.
- OpenSpec proposal, design, specifications, and tasks in `bwaai2-store`.

### Out of Scope
- Backend modifications (`bwaai2-backend` is read-only).
- Contract modifications (`contracts/openapi.yaml` is immutable).
- User authentication and multi-tenant authorization.
- Multi-page client-side router (kept strictly single-page).
- Global external state managers (TanStack Query + React local state are sufficient).

## Capabilities

### New Capabilities
- `document-upload`: Drag-and-drop file upload with client validation and parser configuration.
- `document-polling-and-listing`: Paginated document history and automated background polling using TanStack Query.
- `document-viewer`: Markdown/text page presentation, page navigation, summary display, copy to clipboard, and Markdown file download.

### Modified Capabilities
None.

## Impact
- **Contracts**: Unchanged.
- **Backend**: Unchanged.
- **Frontend**: Full standalone React SPA created in `bwaai2-frontend`.
