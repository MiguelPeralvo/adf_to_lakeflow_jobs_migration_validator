# Provisioning & Deployment Guide

## Deployment Modes

LMV can be deployed in five configurations depending on your needs:

| Mode | What you get | Requirements |
|------|-------------|-------------|
| **Library** | `evaluate()` in your Python code | `pip install lakeflow-migration-validator` |
| **API** | REST endpoints at `/api/*` | + `pip install .[api]` + uvicorn |
| **MCP** | Tool server for Claude/agents at `/mcp` | + `pip install .[mcp]` |
| **Full App** | UI + API + MCP in one process | + frontend build + all extras |
| **Databricks App** | Managed deployment on Databricks | + `app.yaml` + workspace |

---

## 1. Library Mode

Minimal — embed validation in your pipeline or CI:

```bash
pip install lakeflow-migration-validator
```

```python
from lakeflow_migration_validator import evaluate, evaluate_from_wkmigrate

# If you have a ConversionSnapshot:
scorecard = evaluate(snapshot)
print(f"CCS: {scorecard.score}, label: {scorecard.label}")

# If you have wkmigrate output:
scorecard = evaluate_from_wkmigrate(adf_json, prepared_workflow)
assert scorecard.score >= 90, f"CCS {scorecard.score} below threshold"
```

### CI Gate Example

```yaml
# .github/workflows/ci.yml
- name: Score gate
  run: |
    python -c "
    from lakeflow_migration_validator import evaluate_batch
    from lakeflow_migration_validator.golden_set import load_pipeline_golden_set
    suite = load_pipeline_golden_set('golden_sets/pipelines.json')
    report = evaluate_batch(suite, my_converter, threshold=90.0)
    assert report.below_threshold == 0, f'{report.below_threshold} pipelines below 90'
    "
```

---

## 2. API Mode

REST API for programmatic access:

```bash
pip install "lakeflow-migration-validator[api]"
```

```python
# my_server.py
from lakeflow_migration_validator.api import create_app

app = create_app(
    convert_fn=my_convert_function,      # (dict) -> ConversionSnapshot
    judge_provider=my_fmapi_provider,    # Optional: for LLM features
)

# Run: uvicorn my_server:app --port 8000
```

### Environment Variables

```bash
# Required for LLM features (expression validation, agent analysis, synthetic)
DATABRICKS_HOST=https://your-workspace.azuredatabricks.net
DATABRICKS_TOKEN=dapi...

# Optional for harness/parallel testing
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
AZURE_SUBSCRIPTION_ID=...
AZURE_RESOURCE_GROUP=...
AZURE_FACTORY_NAME=...
```

### Test the API

```bash
# Health
curl http://localhost:8000/healthz

# Capabilities
curl http://localhost:8000/api/status

# Validate a pipeline
curl -X POST http://localhost:8000/api/validate \
  -H 'Content-Type: application/json' \
  -d '{"adf_json": {"name": "test", "properties": {"activities": [...]}}}'

# Batch validate a folder
curl -X POST "http://localhost:8000/api/validate/folder?stream=true" \
  -H 'Content-Type: application/json' \
  -d '{"folder_path": "/path/to/adf_pipelines", "threshold": 90}'
```

---

## 3. MCP Mode

Expose validation as tools for Claude, Cursor, or any MCP client:

```bash
pip install "lakeflow-migration-validator[mcp]"
```

```python
from lakeflow_migration_validator.mcp_server import create_mcp_server

mcp = create_mcp_server(
    convert_fn=my_converter,
    judge_provider=my_judge,
)

# Mount on any ASGI app:
app.mount("/mcp", mcp.sse_app())

# Or run standalone:
mcp.run()  # stdio transport
```

### MCP Client Configuration

```json
{
  "mcpServers": {
    "lmv": {
      "url": "http://localhost:8000/mcp",
      "transport": "sse"
    }
  }
}
```

Tools available to the LLM:
- `validate_pipeline` — score an ADF pipeline
- `validate_expression` — check expression equivalence
- `suggest_fix` — get fix suggestions for failing dimensions
- `run_parallel_test` — compare ADF vs Databricks outputs

---

## 4. Full App (UI + API + MCP)

The default — serves everything from one process:

```bash
# Install all extras
pip install "lakeflow-migration-validator[api,mcp,cli,llm]"

# Build frontend
cd apps/lmv/frontend && npm ci && npm run build && cd -

# Run
uvicorn apps.lmv.backend.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 for the UI.

### Docker

```dockerfile
FROM python:3.12-slim

# System deps for git (needed for wkmigrate hot-swap)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Node for frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --with api,mcp,llm --no-root

COPY src/ src/
COPY apps/ apps/
COPY golden_sets/ golden_sets/

# Build frontend
RUN cd apps/lmv/frontend && npm ci && npm run build

# Install the package
RUN poetry install --with api,mcp,llm

EXPOSE 8000
ENV PYTHONPATH=/app/src

CMD ["uvicorn", "apps.lmv.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t lmv .
docker run -p 8000:8000 \
  -e DATABRICKS_HOST=https://your-workspace.azuredatabricks.net \
  -e DATABRICKS_TOKEN=dapi... \
  lmv
```

### docker-compose

```yaml
version: "3.8"
services:
  lmv:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABRICKS_HOST: ${DATABRICKS_HOST}
      DATABRICKS_TOKEN: ${DATABRICKS_TOKEN}
    volumes:
      - lmv-history:/tmp  # persist SQLite history
      - lmv-cache:/tmp/lmv_wkmigrate_cache  # persist git clones

volumes:
  lmv-history:
  lmv-cache:
```

---

## 5. Databricks Apps

Deploy as a managed Databricks App:

```yaml
# apps/lmv/app.yaml
name: lakeflow-migration-validator
description: "ADF-to-Databricks conversion validation"
command: "uvicorn apps.lmv.backend.main:app --host 0.0.0.0 --port 8000"
env:
  - name: DATABRICKS_HOST
    description: Workspace URL
  - name: DATABRICKS_TOKEN
    description: PAT or OAuth token
    valueFrom: secret
```

```bash
# Deploy
databricks apps deploy apps/lmv/

# The app gets a URL like:
# https://your-workspace.azuredatabricks.net/apps/lakeflow-migration-validator
```

---

## Provisioning Checklist

### Minimum (Programmatic Validation Only)

- [ ] Python 3.12+
- [ ] `pip install lakeflow-migration-validator`
- [ ] wkmigrate installed (for real translation)

### Standard (API + UI)

- [ ] All of the above
- [ ] `pip install .[api]`
- [ ] Node.js 20+ (for frontend build)
- [ ] `DATABRICKS_HOST` + `DATABRICKS_TOKEN` env vars
- [ ] Port 8000 accessible

### Full (All Features)

- [ ] All of the above
- [ ] `pip install .[api,mcp,cli,llm]`
- [ ] `git` installed (for wkmigrate hot-swap)
- [ ] Azure credentials (for harness/parallel testing)
- [ ] `json-repair` package (for LLM JSON fixing)
- [ ] Databricks serving endpoints enabled (for FMAPI models)

### Model Requirements

| Model | Purpose | FMAPI Endpoint |
|-------|---------|---------------|
| `databricks-claude-opus-4-6` | Plan generation, agent analysis, synthetic pipelines | `/serving-endpoints/databricks-claude-opus-4-6/invocations` |
| `databricks-chatgpt-5-4` | Expression validation, judge scoring | `/serving-endpoints/databricks-chatgpt-5-4/invocations` |

---

## Storage

| What | Where | Persistence |
|------|-------|-------------|
| Activity history | `{tempdir}/lmv_history.db` (SQLite WAL) | Survives restarts |
| Synthetic runs | `{tempdir}/lmv_synthetic/{timestamp}/` | Until temp cleanup |
| wkmigrate clones | `{tempdir}/lmv_wkmigrate_cache/` | Cached across swaps |

For production, mount persistent volumes for these paths.

---

## Monitoring

### Health Check

```bash
curl http://localhost:8000/healthz
# {"status": "ok"}
```

### Capability Check

```bash
curl http://localhost:8000/api/status
# {"validator": true, "judge": true, "harness": false, "parallel": false}
```

### Logs

Uvicorn logs all requests. Set `--log-level debug` for verbose output.
The FMAPI provider logs retries and failures at WARNING level.

---

## Upgrading wkmigrate

### Via UI (No Restart)

1. Batch Validation → wkmigrate config panel
2. Select repo + branch
3. Click "Apply & Reload"

### Via API (No Restart)

```bash
curl -X POST http://localhost:8000/api/config/wkmigrate/apply \
  -H 'Content-Type: application/json' \
  -d '{"repo_url": "https://github.com/MiguelPeralvo/wkmigrate", "branch": "alpha"}'
```

### Via pip (Requires Restart)

```bash
pip install -e "git+https://github.com/MiguelPeralvo/wkmigrate@alpha#egg=wkmigrate"
# Restart the server
```
