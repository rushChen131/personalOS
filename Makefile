SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend

.PHONY: help install backend-install frontend-install backend-run frontend-run \
        dev-up dev-down migrate lint test smoke typecheck check-migrations ci clean

help:
	@echo "PersonalOS — available targets"
	@echo "  make install           Install backend + frontend dependencies"
	@echo "  make backend-run       Run FastAPI (SQLite, mock LLM) on :8000"
	@echo "  make frontend-run      Run Next.js dev server on :3000"
	@echo "  make dev-up            docker compose up -d (PG/Redis/MinIO stack)"
	@echo "  make dev-down          docker compose down"
	@echo "  make migrate           alembic upgrade head"
	@echo "  make lint              ruff check + next lint"
	@echo "  make test              backend unit tests"
	@echo "  make smoke             full endpoint smoke test (in-process)"
	@echo "  make typecheck         tsc --noEmit"
	@echo "  make check-migrations  alembic check (model vs migration drift)"
	@echo "  make ci                Run every CI gate locally"

install: backend-install frontend-install

backend-install:
	cd $(BACKEND) && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt || \
		(cd $(BACKEND) && python -m venv .venv && .venv/bin/pip install -r requirements.txt)

frontend-install:
	cd $(FRONTEND) && npm install --no-audit --no-fund

# Local path: SQLite + mock LLM, no external services required.
backend-run:
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000 || \
		(cd $(BACKEND) && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000)

frontend-run:
	cd $(FRONTEND) && npm run dev

dev-up:
	docker compose up -d --build

dev-down:
	docker compose down

migrate:
	cd $(BACKEND) && .venv/Scripts/python -m alembic upgrade head

lint:
	cd $(BACKEND) && .venv/Scripts/python -m ruff check app tests
	cd $(FRONTEND) && npm run lint

test:
	cd $(BACKEND) && .venv/Scripts/python -m unittest discover -s tests -t . -p "test_*.py"

# Exercises the full HTTP surface against a throwaway SQLite DB (no server needed).
smoke:
	cd $(BACKEND) && .venv/Scripts/python scripts/smoke_test.py

typecheck:
	cd $(FRONTEND) && npm run typecheck

# Fails if a model change was not accompanied by an Alembic revision.
check-migrations:
	cd $(BACKEND) && .venv/Scripts/python -m alembic upgrade head && \
		.venv/Scripts/python -m alembic check

# Mirrors .github/workflows/ci.yml so the same gates run before pushing.
ci: lint test smoke check-migrations typecheck
	cd $(FRONTEND) && npm run build

clean:
	rm -rf $(FRONTEND)/.next $(FRONTEND)/node_modules
	find $(BACKEND) -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
