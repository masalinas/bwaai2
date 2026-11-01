# Proposal: Docker Compose Hardening and Delivery Packaging

## Why

Reviewers and production evaluators receive the system as a single zip archive. They must be able to unzip it, copy `.env.example` to `.env`, optionally provide Gemini and Mistral API keys, execute `docker compose up --build`, and immediately use the full stack without extra manual steps, external network configurations, or reliance on sibling repository paths.

This change delivers a production-hardened, self-contained multi-container deployment, idempotent packaging automation, end-to-end edge case verification, and clear performance benchmarks measured directly against the staged artifact.

## What Changes

### Store (`bwaai2-store`)
- **OpenSpec Change (`docker-compose-hardening`)**: Authored proposal, design, specifications, and tasks.
- **Delivery Assets (`delivery/`)**:
  - `docker-compose.yml`: Root Compose specification orchestrating `redis`, `api`, `worker`, and `frontend` on a single internal bridge network with health checks, resource limits, log rotation, and dynamic worker scaling.
  - `.env.example`: Unified, documented environment variables with safe defaults (`GEMINI_API_KEY=""`, `MISTRAL_API_KEY=""`).
  - `README.md`: Comprehensive root guide featuring system architecture, Mermaid diagrams, quickstart, endpoints, worker scaling, load-test measurements, and operational assumptions.
  - `Makefile`: Convenient automation commands (`up`, `down`, `logs`, `test`, `lint`, `demo`, `load-test`, `package`, `check`).
  - `scripts/`:
    - `package.sh`: Idempotent POSIX packaging script building `dist/staging/` and `dist/bwaai-pdf-processor.zip` with strict secret/`.env` leakage detection.
    - `generate_samples.py`: Generates representative test PDFs (`normal`, `large_200p`, `encrypted`, `corrupt`, `scanned_image_only`, `not_a_pdf`).
    - `demo.sh`: Interactive demonstration script running an upload through polling to terminal state.
    - `load_test.py`: Asynchronous load testing script measuring latency percentiles, error rates, and peak concurrency.
    - `test_edge_cases.sh`: Automated verification script executing sample failure modes against the staged stack.
  - `samples/`: Pre-generated test PDF files.

### Backend (`bwaai2-backend`)
- **Contract Path Resolution**: Contract parity tests resolve `CONTRACT_PATH` in order: environment variable, `../contracts/openapi.yaml` (zip layout), `../bwaai2-store/contracts/openapi.yaml` (development layout).
- **Worker Heartbeat**: Worker maintains `/tmp/worker_heartbeat` for fast container health checks in addition to Redis heartbeat keys.
- **Graceful Unconfigured Key Handling**: When `GEMINI_API_KEY` or `MISTRAL_API_KEY` are not set, upload validation and worker execution return clear `PARSER_UNAVAILABLE` or `SUMMARY_FAILED` domain errors without crashing.
- **Container Hardening**: Dockerfile updated with multi-stage non-root user (`appuser`, UID 1000), pinned Python 3.12 version, and dedicated `.dockerignore`.

### Frontend (`bwaai2-frontend`)
- **Contract Path Resolution**: `npm run gen:api` utilizes `scripts/resolve-contract.js` to resolve `CONTRACT_PATH` across zip and dev layouts.
- **Nginx Hardening**: `nginx.conf.template` configured with `client_max_body_size 300M;`, extended upload proxy timeouts (120s), and a dedicated `/healthz` endpoint.
- **Container Hardening**: Dockerfile pinned to stable Alpine versions with dedicated `.dockerignore`. Removed external network requirement.

## Capabilities

### New Capabilities
- `deployment-and-packaging`: Root Docker Compose orchestration, container hardening, automated secret-safe archive packaging, and verification tools.

### Modified Capabilities
None.

## Impact
- **Contracts**: Unchanged.
- **Backend**: Container security hardening, path resolution flexibility, graceful missing-key resilience.
- **Frontend**: Nginx proxy limits aligned with batch upload contract, path resolution flexibility.
- **Reviewer Experience**: One zip file with zero extra setup.
