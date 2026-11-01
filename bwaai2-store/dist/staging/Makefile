.PHONY: help up down logs restart ps test lint check demo load-test package

help:
	@echo "Available commands:"
	@echo "  make up          - Build and start all services in background (docker compose)"
	@echo "  make down        - Stop all services and remove volumes"
	@echo "  make logs        - Follow logs across all containers"
	@echo "  make restart     - Restart the container stack"
	@echo "  make ps          - Display container health and status"
	@echo "  make test        - Run test suites in backend and frontend"
	@echo "  make lint        - Run linters and formatting checks"
	@echo "  make check       - Run tests, linters, and contract verification in one go"
	@echo "  make demo        - Run end-to-end interactive upload demo against running stack"
	@echo "  make load-test   - Run asynchronous load test against running stack"
	@echo "  make package     - Package the full system into dist/bwaai-pdf-processor.zip"

up:
	docker compose up --build -d

down:
	docker compose down -v

logs:
	docker compose logs -f

restart:
	docker compose restart

ps:
	docker compose ps

test:
	@echo "==> Running Backend Tests..."
	cd backend && uv run pytest -v
	@echo "==> Running Frontend Tests..."
	cd frontend && npm run test

lint:
	@echo "==> Linting Backend..."
	cd backend && uv run ruff check . && uv run ruff format --check .
	@echo "==> Linting Frontend..."
	cd frontend && npm run lint

check: lint test
	@echo "==> Verifying OpenAPI Contract Parity..."
	cd backend && uv run pytest tests/test_contract.py -v
	@echo "==> All checks passed successfully!"

demo:
	bash scripts/demo.sh

load-test:
	python3 scripts/load_test.py --concurrency 10 --total 30

package:
	bash scripts/package.sh
