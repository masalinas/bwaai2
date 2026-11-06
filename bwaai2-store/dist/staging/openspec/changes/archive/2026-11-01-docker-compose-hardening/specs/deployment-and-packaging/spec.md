# Spec: Deployment and Packaging

## Purpose

Defines requirements for the unified root Docker Compose deployment, container security hardening, multi-layout path resolution, and secret-safe zip archive packaging.

## ADDED Requirements

### Requirement: Single-Archive Delivery Packaging
The delivery packaging script `delivery/scripts/package.sh` SHALL assemble the entire project into a self-contained archive at `dist/bwaai-pdf-processor.zip` containing `docker-compose.yml`, `.env.example`, `README.md`, `Makefile`, `contracts/`, `openspec/`, `samples/`, `scripts/`, `backend/`, and `frontend/`, excluding all `.venv`, `node_modules`, `.git`, `.env`, and build caches.

#### Scenario: Secret and .env leakage rejection
- **WHEN** `package.sh` encounters a `.env` file or files containing private credentials in the staging directory
- **THEN** it immediately halts with a non-zero exit status and does not generate the zip archive

#### Scenario: Clean packaging success
- **WHEN** `package.sh` is executed on clean repositories
- **THEN** it outputs `dist/staging/` and `dist/bwaai-pdf-processor.zip` and prints archive size and file statistics

### Requirement: Root Docker Compose Orchestration
The root `docker-compose.yml` SHALL orchestrate `redis`, `api`, `worker`, and `frontend` on a single internal bridge network without external network dependencies, configuring `condition: service_healthy` across dependencies, reasonable resource bounds, and log rotation.

#### Scenario: Service health readiness ordering
- **WHEN** `docker compose up --build -d` is executed
- **THEN** `redis` becomes healthy before `api` and `worker` start, and `api` becomes healthy before `frontend` starts

#### Scenario: Dynamic worker scaling
- **WHEN** `docker compose up --scale worker=3 -d` is executed
- **THEN** 3 worker instances register unique consumer names on the consumer group without container name collisions or port conflicts

### Requirement: Redis Persistence and Eviction Safety
The Redis service SHALL run with `--appendonly yes` writing to a named Docker volume `redis_data` and `--maxmemory-policy noeviction`.

#### Scenario: Redis restart with queued jobs
- **WHEN** Redis restarts while jobs are in `documents:jobs`
- **THEN** queued jobs persist in AOF storage and are processed to completion after restart

### Requirement: Nginx Reverse Proxy Limits
The frontend Nginx container SHALL proxy `/api/` to the API service with `client_max_body_size` set to at least 300MB and proxy timeouts of at least 120 seconds, exposing a `/healthz` endpoint for container health probes.

#### Scenario: Batch upload of 10 files
- **WHEN** a client uploads a 10-file batch of PDF documents totaling over 100MB
- **THEN** Nginx does not reject the request with HTTP 413, proxying it to FastAPI for contract validation

### Requirement: Cross-Layout Contract Path Resolution
The backend contract parity test and the frontend API type generator SHALL resolve the contract path using the fallback sequence: `CONTRACT_PATH` env var -> `../contracts/openapi.yaml` (zip layout) -> `../bwaai2-store/contracts/openapi.yaml` (development layout).

#### Scenario: Execution inside zip layout
- **WHEN** tests or type generation run inside the extracted zip directory where `../contracts/openapi.yaml` exists
- **THEN** the contract resolves successfully without requiring `CONTRACT_PATH` to be set

### Requirement: Graceful Operation Without LLM API Keys
The stack SHALL start up and pass all health checks when `GEMINI_API_KEY` and `MISTRAL_API_KEY` are empty. PyPDF uploads SHALL parse successfully, while Gemini and Mistral requests SHALL return clear `PARSER_UNAVAILABLE` or `SUMMARY_FAILED` errors instead of crashing.

#### Scenario: PyPDF upload without API keys
- **WHEN** a document is uploaded with `parser=pypdf` on a stack with empty API keys
- **THEN** pages are parsed and stored in Redis, and summarization reports a configuration requirement error without crashing the worker
