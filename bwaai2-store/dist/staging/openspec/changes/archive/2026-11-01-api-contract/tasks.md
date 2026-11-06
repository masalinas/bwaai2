# Tasks

## 1. OpenAPI Specification Contract Drafting

- [x] 1.1 Create `contracts/openapi.yaml` with OpenAPI 3.1.0 root structure, metadata, server URLs, and tags (`documents`, `system`), verified by validating file existence and YAML parsing.
- [x] 1.2 Define reusable components in `components/schemas` including `ErrorCode`, `Error`, `ParserType`, `DocumentStatus`, `ContentFormat`, `DocumentUploadItem`, `DocumentListItem`, `DocumentListResponse`, `DocumentPage`, `DocumentDetailResponse`, `DocumentStatusResponse`, and `HealthResponse`, verified by schema syntax checks.
- [x] 1.3 Define reusable responses in `components/responses` for all error codes (400, 404, 413, 415, 422, 429, 500) and standard parameter/header definitions (e.g., `Retry-After`), verified by schema reference resolution.
- [x] 1.4 Implement the endpoints in `paths`: `POST /documents`, `GET /documents`, `GET /documents/{document_id}`, `GET /documents/{document_id}/status`, and `GET /health` with complete operationIds, summaries, tags, realistic request/response examples, limits, and status codes (202, 200, 400, 404, 413, 415, 422, 429, 500), verified by inspection of path definitions.

## 2. Validation and Linting

- [x] 2.1 Validate the OpenSpec change artifacts using `openspec validate api-contract --strict`, verifying zero errors or warnings reported.
- [x] 2.2 Lint `contracts/openapi.yaml` using Redocly CLI (`npx -y @redocly/cli lint contracts/openapi.yaml`), verifying zero errors and zero warnings.
- [x] 2.3 Verify YAML parsing and OpenAPI 3.1 structural integrity via CLI tooling, verifying clean validation.

## 3. Review and Verification

- [x] 3.1 Review contract alignment against all user prompt requirements (flow, status lifecycle, reusable schemas, operation IDs, limits, examples), verified against the requirement checklist.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Generate TypeScript client types for the frontend from `contracts/openapi.yaml`.
- Wire FastAPI backend schemas and route stubs to validate against `contracts/openapi.yaml`.
