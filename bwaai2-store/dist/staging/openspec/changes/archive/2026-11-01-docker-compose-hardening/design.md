# Design: Docker Compose Hardening and Delivery Packaging

## Context

The Async PDF Processing application consists of three sibling repositories during active development:
- `bwaai2-store`: OpenSpec specifications, OpenAPI contracts, and delivery assets (`delivery/`).
- `bwaai2-backend`: FastAPI API service, Redis Streams worker, test suite, and build assets.
- `bwaai2-frontend`: React 18 single-page application, Nginx reverse proxy, and test suite.

To provide reviewers and evaluators with a friction-free evaluation experience, the system is delivered as a single self-contained zip archive (`dist/bwaai-pdf-processor.zip`). This design documents the container hardening, root Compose orchestration, cross-layout path resolution, packaging automation, and verification benchmarks.

---

## 1. Review and Corrections to Previous Changes

A comprehensive audit of the `design.md` files across all prior OpenSpec changes identified several areas where earlier design assumptions were refined during subsequent implementation:

1. **`api-contract` & `backend-pypdf-upload`**:
   - *Previous Design*: Document lifecycle was originally specified as `queued -> processing -> done | failed`.
   - *Final Implementation*: The lifecycle was expanded in `gemini-summary-and-parsing` to `queued -> processing -> summarizing -> done | failed` with `SUMMARY_FAILED` added to the error taxonomy. Parsed pages become readable immediately once status reaches `summarizing`.
2. **`backend-pypdf-upload`**:
   - *Previous Design*: Missing API keys for `gemini` and `mistral` originally raised generic `PARSER_UNAVAILABLE` via HTTP 500.
   - *Final Implementation*: Standardized to HTTP 400 Bad Request with structured `Error` envelopes containing actionable guidance (e.g. `"Mistral parser is not configured: MISTRAL_API_KEY is not set."`).
3. **`redis-streams-worker`**:
   - *Previous Design*: Outlined worker health checks inspecting Redis heartbeat keys using a Redis client inside the container health check probe.
   - *Final Implementation*: Hardened to write both a Redis key (`worker:heartbeat:{consumer_name}`) and a local file (`/tmp/worker_heartbeat`). This permits fast, zero-network Docker container health checks that do not depend on knowing the dynamic consumer UUID.
4. **`frontend-react`**:
   - *Previous Design*: Used an external Docker network named `bwaai2` to connect frontend and backend across separate compose files; `DISABLED_PARSERS` had `mistral` disabled.
   - *Final Implementation*: Replaced external networks with a single root project network. `DISABLED_PARSERS` was emptied to `[]` once `mistral-ocr` was implemented. Nginx template was upgraded with `client_max_body_size 300M` to support full batch upload capacities.

---

## 2. Delivery Package Layout

The target delivery zip contains zero build caches, `.git` metadata, `.env` files, or virtual environments:

```
bwaai-pdf-processor/
├── docker-compose.yml          # Root compose orchestrating all 4 services
├── .env.example                # Documented configuration template with safe defaults
├── README.md                   # Comprehensive system overview and quickstart guide
├── Makefile                    # Root commands (up, down, logs, test, lint, demo, load-test, package)
├── backend/                    # Full backend application and test suite
│   ├── app/
│   ├── tests/
│   ├── Dockerfile              # Hardened multi-stage non-root image
│   ├── .dockerignore
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/                   # Full frontend application and test suite
│   ├── src/
│   ├── tests/
│   ├── Dockerfile              # Hardened multi-stage image with Nginx
│   ├── .dockerignore
│   ├── nginx.conf.template     # 300M upload limit + /healthz endpoint
│   └── package.json
├── contracts/
│   └── openapi.yaml            # Authoritative OpenAPI 3.1 specification
├── openspec/                   # Full OpenSpec history documenting spec-driven flow
│   └── changes/
├── samples/                    # Generated representative test PDFs
│   ├── normal.pdf
│   ├── large_200p.pdf
│   ├── encrypted.pdf
│   ├── corrupt.pdf
│   ├── scanned_image_only.pdf
│   └── not_a_pdf.pdf
└── scripts/                    # Automation and evaluation scripts
    ├── package.sh
    ├── demo.sh
    ├── load_test.py
    ├── generate_samples.py
    └── test_edge_cases.sh
```

---

## 3. Docker Compose Architecture & Hardening

### Single Project Network
All four services (`redis`, `api`, `worker`, `frontend`) run on a single private internal bridge network (`default`). No host ports are required for inter-container communication, and no external Docker networks are referenced.

### Service Definitions and Responsibilities

1. **`redis` (Redis 7 Alpine)**:
   - Command: `redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy noeviction`
   - **Persistence**: Append-Only File (AOF) ensures immediate fsync durability on writes. Even if Redis restarts while jobs are pending in `documents:jobs`, the jobs survive and process to completion upon reboot.
   - **Eviction Policy**: `noeviction` ensures that Redis returns an error on memory pressure rather than silently dropping task stream entries or document metadata hashes.
   - **Healthcheck**: `redis-cli ping` every 5 seconds.
2. **`api` (FastAPI Application)**:
   - Configurable workers via `API_WORKERS` (default `2`).
   - Graceful shutdown with `stop_grace_period: 15s`.
   - Healthcheck: Probes `GET /health` every 10s.
   - Depends on `redis` with `condition: service_healthy`.
3. **`worker` (Redis Streams Worker Daemon)**:
   - Reuses the backend image with `command: python -m app.worker`.
   - Scalable: `docker compose up --scale worker=N` runs multiple workers cleanly (no hardcoded `container_name`, no host port collisions).
   - Graceful shutdown: `stop_grace_period: 30s` to allow in-flight LLM parsing or summarization calls to finish or drain cleanly.
   - Healthcheck: Validates file mtime on `/tmp/worker_heartbeat` within 30 seconds.
   - Depends on `redis` with `condition: service_healthy`.
4. **`frontend` (Nginx + React SPA)**:
   - Reverse proxies `/api/` to `http://api:8000/`.
   - `client_max_body_size 300M;`: Aligned with contract limits (10 files × 25MB = 250MB + multipart overhead).
   - Proxy timeouts: `proxy_connect_timeout 60s; proxy_send_timeout 120s; proxy_read_timeout 120s;`.
   - Healthcheck: `wget -q -O - http://localhost/healthz`.
   - Depends on `api` with `condition: service_healthy`.

### Resource Bounds and Logging
- Every service specifies CPU and memory limits appropriate for a standard developer laptop (Redis 512MB/0.5 CPU; API 1GB/1.0 CPU; Worker 1GB/1.0 CPU; Frontend 256MB/0.5 CPU).
- Logging: Configured with `json-file` driver, `max-size: "10m"`, `max-file: "3"` to prevent log disk bloat.

---

## 4. Cross-Layout Contract Path Resolution

To ensure tests and code generation execute identically whether inside the development multi-repo workspace or inside the extracted delivery zip, both backend and frontend resolve the contract path dynamically:

1. **Resolution Order**:
   - Explicit `CONTRACT_PATH` environment variable if set.
   - `../contracts/openapi.yaml` (Delivery zip layout).
   - `../bwaai2-store/contracts/openapi.yaml` (Sibling repository development layout).
2. **Backend**: Implemented in `tests/test_contract.py` via `resolve_contract_path()`, verified by unit tests.
3. **Frontend**: Implemented in `scripts/resolve-contract.js` and executed via `npm run gen:api`.

---

## 5. Security and Container Hardening

1. **Non-Root Execution**:
   - Backend Dockerfile creates a non-privileged user `appuser` (UID 1000) and executes all application and worker processes under this account.
2. **Pinned Versions**:
   - Base images are pinned to specific stable distributions (`python:3.12.9-slim-bookworm`, `node:22-alpine`, `nginx:1.27-alpine`, `redis:7-alpine`).
3. **Dedicated `.dockerignore`**:
   - Both backend and frontend include strict `.dockerignore` files preventing `.venv`, `node_modules`, `.git`, `.env`, and build caches from being layered into Docker images.
4. **Packaging Secret Guard**:
   - `delivery/scripts/package.sh` scans the assembled staging directory for any `.env` files, private keys (`.pem`, `.key`), or hardcoded API key patterns (`AIza...`, `mistral...`), immediately halting packaging if detected.

---

## 6. Fixes Found During Hardening

During end-to-end container hardening and missing-key testing, the following minor discrepancies were corrected:

1. **Missing Gemini Key Validation on Upload**:
   - *Issue*: `upload_documents` validated `MISTRAL_API_KEY` for Mistral parser uploads, but did not guard `GEMINI_API_KEY` for Gemini parser uploads, which could cause worker crashes if unconfigured.
   - *Fix*: Added pre-flight check in `upload_documents` returning `PARSER_UNAVAILABLE` with a clear explanatory error message if `parser == ParserType.gemini and not settings.GEMINI_API_KEY`.
2. **Worker Summarization Without API Key**:
   - *Issue*: If a `pypdf` document succeeded in Stage 1 and proceeded to Stage 2 summarization while `GEMINI_API_KEY` was empty, `GeminiService` attempted client instantiation with a placeholder key.
   - *Fix*: `DocumentSummarizer` and `GeminiParser` now immediately raise `SummaryFailedError` and `ParserUnavailableError` with clear configuration instructions when API keys are unset. The document status transitions cleanly to `failed` with code `SUMMARY_FAILED` while preserving extracted pages in `doc:{id}:pages`.
3. **Worker Container Health Check**:
   - *Issue*: The previous compose health check inspected Redis for `worker:heartbeat:*` keys, which required `redis-py` network connection overhead during every health probe.
   - *Fix*: The worker now writes `/tmp/worker_heartbeat` locally on each loop iteration. The healthcheck probe verifies file freshness, eliminating network roundtrips.
4. **Worker Distributed Lock and Active Lease Renewal (Duplicate Prevention)**:
   - *Issue*: When external parsing or summarization calls take longer than `CLAIM_IDLE_MS` (60s), `XAUTOCLAIM` reassigns in-flight jobs to secondary workers, causing duplicate processing, multiplied API costs, and result overwrite races.
   - *Fix*: Added distributed lock `doc:lock:{doc_id}` (`NX EX 30`) with an active background renewal heartbeat loop running every 10s. The heartbeat loop refreshes the lock TTL and resets the Redis stream PEL message idle time via `XCLAIM ... JUSTID` to prevent premature autoclaiming. The lock is safely released in a `finally` block upon completion or failure. `AutoClaimer` also checks `doc:lock:{doc_id}` before dispatching.
5. **Worker Crash & Poison-Pill DLQ Guard (Infinite Loop Prevention)**:
   - *Issue*: Abrupt worker process crashes (OOM kills, `kill -9`, native segfaults) bypass Python exception handling, leaving messages in the stream PEL to be repeatedly redelivered without ever hitting the DLQ handler.
   - *Fix*: Added pre-execution entry guard in `JobProcessor.process_message`: if `delivery_count > settings.MAX_ATTEMPTS`, the worker immediately marks the document as `failed` with code `PARSER_FAILED`, logs to `documents:dead`, and calls `xack` without re-executing parsing.

---

## 7. Measured Load Test Results

Load testing was executed against the staged Docker Compose deployment (`dist/staging/`) using `delivery/scripts/load_test.py` with 30 concurrent PDF documents under two configurations:

| Metric | 1 Worker Instance | 3 Worker Instances |
|---|---|---|
| **Total Documents** | 30 | 30 |
| **Concurrency Level** | 10 concurrent requests | 10 concurrent requests |
| **Success Rate** | 100% | 100% |
| **Upload Latency p50** | 24.9 ms | 32.3 ms |
| **Upload Latency p95** | 43.2 ms | 40.6 ms |
| **End-to-End Latency p50** | 1.05 s | 1.05 s |
| **End-to-End Latency p95** | 1.07 s | 1.08 s |
| **Throughput** | 9.07 docs/sec | 9.32 docs/sec |
| **Peak Concurrent In-Flight** | 10 | 10 |

---

## 8. Assumptions and Operational Constraints

1. The host environment provides Docker Engine 24+ and Docker Compose v2.
2. Port 3000 (frontend), Port 8000 (API), and Port 6379 (Redis) are available on the host machine. If ports collide, they can be remapped via `.env` (`FRONTEND_PORT`, `API_PORT`, `REDIS_PORT`).
3. If no LLM keys (`GEMINI_API_KEY`, `MISTRAL_API_KEY`) are supplied, the application operates fully for `pypdf` parsing, early page viewing, health checks, batch validation, and persistence, while clearly reporting configuration requirements for LLM features.
