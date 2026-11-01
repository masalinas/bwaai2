.PHONY: up down test lint format worker

up:
	docker compose up --build

down:
	docker compose down

worker:
	uv run python -m app.worker

test:
	uv run pytest -v

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .
