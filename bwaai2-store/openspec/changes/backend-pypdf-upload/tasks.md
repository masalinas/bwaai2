# Tasks

## 1. Specification and Project Setup

- [x] 1.1 [store] Verify OpenSpec proposal, design, and specs for `backend-pypdf-upload`, validated via `openspec validate backend-pypdf-upload --strict`.
- [x] 1.2 [backend] Initialize project structure in `../bwaai2-backend` with `pyproject.toml`, dependencies (`fastapi`, `uvicorn`, `redis`, `pypdf`, `pydantic`, `pydantic-settings`, `python-multipart`, `pytest`, `pytest-asyncio`, `httpx`, `fakeredis`, `ruff`, `pyyaml`), and `uv venv`.

## 2. Core Models and Configuration

- [x] 2.1 [backend] Implement `app/core/config.py`, `app/core/constants.py` (stream names, groups, Redis keys), and `app/core/exceptions.py` (domain errors).
- [x] 2.2 [backend] Implement Pydantic models matching `contracts/openapi.yaml` in `app/models/errors.py`, `app/models/documents.py`, and `app/models/health.py`.

## 3. Storage, Queue, and Parser Services

- [x] 3.1 [backend] Implement async Redis storage client in `app/services/storage.py` handling `doc:{id}` hashes, `docs:index` sorted sets, and raw bytes with TTL.
- [x] 3.2 [backend] Implement Redis Streams producer in `app/services/queue.py` publishing jobs to `documents:jobs`.
- [x] 3.3 [backend] Implement `Parser` interface in `app/services/parsers/base.py` and `PyPDFParser` in `app/services/parsers/pypdf_parser.py` with `asyncio.to_thread` execution.

## 4. API Endpoints and Application Assembly

- [x] 4.1 [backend] Implement `app/api/documents.py` router handling `POST /documents`, `GET /documents`, `GET /documents/{document_id}`, and `GET /documents/{document_id}/status`.
- [x] 4.2 [backend] Implement `app/api/health.py` router checking Redis connectivity.
- [x] 4.3 [backend] Assemble `app/main.py` with lifespan connection pool management, unified error handlers, and route mounting.

## 5. Infrastructure and Tooling

- [x] 5.1 [backend] Create `Dockerfile` and `docker-compose.yml` for API and Redis 7 with healthchecks and environment variables.
- [x] 5.2 [backend] Create `Makefile` with `up`, `test`, `lint` targets and configure Ruff in `pyproject.toml`.

## 6. Testing and Contract Verification

- [x] 6.1 [backend] Implement unit tests for `PyPDFParser` in `tests/test_pypdf_parser.py`.
- [x] 6.2 [backend] Implement endpoint integration tests in `tests/test_documents.py`, `tests/test_status.py`, `tests/test_health.py`, and `tests/test_concurrency.py`.
- [x] 6.3 [backend] Implement OpenAPI contract comparison test in `tests/test_contract.py` verifying paths, methods, status codes, and schemas against `../bwaai2-store/contracts/openapi.yaml`.
- [x] 6.4 [backend] Run full pytest suite and Ruff linter in `../bwaai2-backend`, verifying all tests pass and code is clean.
