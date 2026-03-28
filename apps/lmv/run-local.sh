#!/bin/bash
# Run the LMV app locally — serves frontend + API + MCP from one process.
#
# Usage:
#   ./apps/lmv/run-local.sh                    # validate-only (no providers)
#   DATABRICKS_HOST=https://... ./apps/lmv/run-local.sh  # with LLM judge
#
# The app is accessible at http://localhost:8000
#   /          → React UI
#   /api/*     → REST API
#   /mcp       → MCP SSE transport (if mcp extra installed)
#   /healthz   → health check

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Build frontend if dist/ is missing or stale
FRONTEND_DIR="$SCRIPT_DIR/frontend"
DIST_DIR="$FRONTEND_DIR/dist"
if [ ! -f "$DIST_DIR/index.html" ]; then
    echo "Building frontend..."
    (cd "$FRONTEND_DIR" && npm install --silent && npx vite build)
fi

# Start the backend (serves API + frontend static files)
echo "Starting LMV at http://localhost:8000"
echo "  /          → UI"
echo "  /api/*     → REST API"
echo "  /mcp       → MCP (if installed)"
echo ""

cd "$REPO_ROOT"
PYTHONPATH=src exec uvicorn apps.lmv.backend.main:app \
    --host 0.0.0.0 \
    --port "${LMV_PORT:-8000}" \
    --reload \
    --reload-dir src \
    --reload-dir apps
