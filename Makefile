.PHONY: app app-build test test-all frontend-build frontend-dev

# Run the app locally (single process: UI + API + MCP)
app:
	./apps/lmv/run-local.sh

# Build the frontend for production (checked into dist/ for Databricks Apps)
frontend-build:
	cd apps/lmv/frontend && npm install --silent && npx vite build

# Run the frontend dev server with hot reload (proxies /api to backend)
frontend-dev:
	cd apps/lmv/frontend && npx vite --port 5173

# Run unit tests (no wkmigrate or external deps needed)
test:
	PYTHONPATH=src poetry run python -m pytest tests/unit/ -q --ignore=tests/unit/validation/test_wkmigrate_adapter.py --ignore=tests/unit/validation/test_cli.py

# Run all tests (requires wkmigrate + typer installed)
test-all:
	PYTHONPATH=src poetry run python -m pytest tests/ -q
