# Tasks

## 1. Store Specification & Delivery Structure

- [x] 1.1 [store] Author OpenSpec change `docker-compose-hardening` (`proposal.md`, `design.md`, `specs/`, `tasks.md`).
- [x] 1.2 [store] Verify OpenSpec validity with `openspec validate docker-compose-hardening --strict`.

## 2. Backend Hardening

- [x] 2.1 [backend] Update contract path resolution in `tests/test_contract.py` to resolve `CONTRACT_PATH`, `../contracts/openapi.yaml`, `../bwaai2-store/contracts/openapi.yaml`, and add unit test `test_contract_path_resolution`.
- [x] 2.2 [backend] Update `app/worker/main.py` heartbeat loop to maintain `/tmp/worker_heartbeat` for container health checks.
- [x] 2.3 [backend] Add clear missing-key handling in `app/api/documents.py` (Gemini), `app/services/parsers/gemini_parser.py`, and `app/services/summarizer.py`.
- [x] 2.4 [backend] Harden `Dockerfile` with pinned base image, non-root user `appuser`, and create `.dockerignore`.
- [x] 2.5 [backend] Verify backend test suite and linter (`pytest`, `ruff check`, `ruff format`).

## 3. Frontend Hardening

- [x] 3.1 [frontend] Create `scripts/resolve-contract.js`, update `package.json` `gen:api`, and add unit test in `tests/contract_path.test.ts`.
- [x] 3.2 [frontend] Update `nginx.conf.template` with `client_max_body_size 300M;`, timeouts, and `/healthz` endpoint.
- [x] 3.3 [frontend] Harden `Dockerfile` with pinned versions and create `.dockerignore`. Remove external network in `docker-compose.yml`.
- [x] 3.4 [frontend] Verify frontend test suite, linter, and build (`npm run test`, `npm run lint`, `npm run build`).

## 4. Delivery Assets Creation

- [x] 4.1 [store] Create `delivery/docker-compose.yml` with Redis AOF, health checks, resource limits, log rotation, and dynamic worker scaling.
- [x] 4.2 [store] Create `delivery/.env.example` documenting all configuration variables with safe defaults.
- [x] 4.3 [store] Create `delivery/Makefile` with targets (`up`, `down`, `logs`, `test`, `lint`, `demo`, `load-test`, `package`, `check`).
- [x] 4.4 [store] Create `delivery/scripts/generate_samples.py` and generate sample PDFs in `delivery/samples/` (`normal.pdf`, `large_200p.pdf`, `encrypted.pdf`, `corrupt.pdf`, `scanned_image_only.pdf`, `not_a_pdf.pdf`).
- [x] 4.5 [store] Create `delivery/scripts/package.sh` with idempotent staging, secret detection, and zip generation.
- [x] 4.6 [store] Create `delivery/scripts/demo.sh`, `delivery/scripts/load_test.py`, and `delivery/scripts/test_edge_cases.sh`.

## 5. Verification from Staged Copy

- [ ] 5.1 [store] Execute `delivery/scripts/package.sh` to assemble `dist/staging/` and `dist/bwaai-pdf-processor.zip`.
- [ ] 5.2 [store] Run `docker compose up --build -d` inside `dist/staging/` and wait for all services to become healthy.
- [ ] 5.3 [store] Run `test_edge_cases.sh` against the staged stack (status codes, upload limits, corrupted files, missing keys).
- [ ] 5.4 [store] Run `demo.sh` against the staged stack.
- [ ] 5.5 [store] Run `load_test.py` with 1 worker instance, record metrics.
- [ ] 5.6 [store] Scale workers to 3 instances (`docker compose up --scale worker=3 -d`) and run `load_test.py`, record metrics.
- [ ] 5.7 [store] Test Redis restart durability and worker kill XAUTOCLAIM recovery.
- [ ] 5.8 [store] Tear down staged deployment with `docker compose down -v`.

## 6. Documentation and Review

- [ ] 6.1 [store] Create `delivery/README.md` with system overview, Mermaid diagram, quick start, endpoints, scaling, measured load-test figures, and operational decisions.
- [ ] 6.2 [store] Update `design.md` with measured load test metrics and review notes.
- [ ] 6.3 [store] Ensure backend and frontend READMEs are consistent with the root README.
- [ ] 6.4 [store] Re-run `package.sh` to update `dist/bwaai-pdf-processor.zip` with final documentation.
