# Lakeflow Migration Validator — Architecture & Design

## Overview

The Lakeflow Migration Validator (LMV) scores the quality of ADF-to-Databricks
Lakeflow Jobs conversions across 11 dimensions, producing a composite
**Conversion Confidence Score (CCS)** from 0–100.

It exposes four surfaces from a single Python process:

```
┌──────────────────────────────────────────────────┐
│                  FastAPI Process                  │
│                                                  │
│  /api/*    REST API (validation, synthetic, …)   │
│  /mcp      MCP SSE transport (agentic tools)     │
│  /         React SPA (Stitch M3 Dark UI)         │
│  CLI       lmv validate|batch|harness|…          │
└──────────────────────────────────────────────────┘
        │              │              │
   Databricks     wkmigrate      LLM Judge
    FMAPI        (hot-swap)     (Opus 4.6)
```

---

## System Architecture

### Layer Model

```
┌─────────────────────────────────────────────────────┐
│  Presentation        UI / CLI / MCP / REST API      │
├─────────────────────────────────────────────────────┤
│  Orchestration       Harness, FixLoop, Synthetic    │
├─────────────────────────────────────────────────────┤
│  Evaluation          11 Dimensions → Scorecard      │
├─────────────────────────────────────────────────────┤
│  Contract            ConversionSnapshot (agnostic)  │
├─────────────────────────────────────────────────────┤
│  Adapters            wkmigrate_adapter (boundary)   │
├─────────────────────────────────────────────────────┤
│  Providers           FMAPI, DatabricksRunner, ADF   │
└─────────────────────────────────────────────────────┘
```

### Data Flow

```
ADF Pipeline JSON
  → wkmigrate translate_pipeline() → Pipeline IR
  → wkmigrate prepare_workflow()   → PreparedWorkflow
  → from_wkmigrate()               → ConversionSnapshot
  → evaluate()                     → Scorecard { score, label, dimensions }
```

---

## Core Design Decisions

### 1. Tool-Agnostic Contract

All evaluation operates on `ConversionSnapshot` — a frozen dataclass with no
wkmigrate imports. Only `adapters/wkmigrate_adapter.py` touches wkmigrate types.

**Why:** Enables adding adapters for other migration tools (Stitch, Fivetran,
custom) without changing any dimension or scoring logic.

```python
@dataclass(frozen=True, slots=True)
class ConversionSnapshot:
    tasks: tuple[TaskSnapshot, ...]        # Translated Databricks tasks
    notebooks: tuple[NotebookSnapshot, ...]  # Generated notebook code
    secrets: tuple[SecretRef, ...]
    parameters: tuple[str, ...]
    dependencies: tuple[DependencyRef, ...]
    not_translatable: tuple[dict, ...]
    resolved_expressions: tuple[ExpressionPair, ...]
    source_pipeline: dict                  # Original ADF JSON
    total_source_dependencies: int
```

### 2. Dimension Protocol

Three implementation tiers with a single protocol:

| Tier | Type | Needs | Examples |
|------|------|-------|---------|
| 1 | `ProgrammaticCheck` | Nothing | activity_coverage, notebook_validity |
| 2 | `LLMJudge` | FMAPI | semantic_equivalence |
| 3 | `ExecutionDimension` | Databricks | runtime_success, parallel_equivalence |

```python
class Dimension(Protocol):
    name: str
    threshold: float
    def evaluate(self, input: Any, output: Any) -> DimensionResult: ...
```

### 3. Weighted CCS Formula

```
CCS = (Σ dimension_score × weight) / (Σ active_weights) × 100
```

Default weights (sum to 1.0 for active dimensions):

| Dimension | Weight | Threshold |
|-----------|--------|-----------|
| activity_coverage | 0.25 | 0.9 |
| expression_coverage | 0.20 | 0.8 |
| dependency_preservation | 0.15 | 0.9 |
| notebook_validity | 0.15 | 1.0 |
| parameter_completeness | 0.10 | 1.0 |
| secret_completeness | 0.10 | 1.0 |
| not_translatable_ratio | 0.05 | 0.8 |
| control_flow_fidelity | 0.00 | 0.8 |

Labels: **90–100** HIGH_CONFIDENCE, **70–89** REVIEW_RECOMMENDED, **<70** MANUAL_INTERVENTION

### 4. Graceful Degradation

The app starts with whatever providers are available:

```python
judge = _build_judge_provider()      # None if no DATABRICKS_HOST
harness = _build_harness_runner()    # None if no AZURE_* creds
convert = _build_convert_fn()        # passthrough if no wkmigrate
```

`/api/status` reports capabilities. Endpoints that need unavailable providers
return `503 Service Unavailable`.

### 5. Hot-Swappable wkmigrate

The `convert_fn` is wrapped in a mutable proxy:

```python
convert_holder = {"fn": _build_convert_fn()}

def convert_proxy(payload):
    return convert_holder["fn"](payload)
```

`POST /api/config/wkmigrate/apply` clones a repo, `pip install -e`, reloads
70+ modules via `importlib.reload`, and rebuilds `convert_fn` — all at runtime.

### 6. Synthetic Plan-Then-Execute

LLM-powered generation uses a two-phase architecture:

1. **Plan**: LLM analyzes natural-language spec → produces `GenerationPlan`
   with per-pipeline `PipelineSpec` (name, stress area, activity types)
2. **Execute**: Each pipeline generated independently with per-pipeline
   staged progress (preparing → calling_llm → parsing → validating → snapshot)

JSON repair via `json_repair` library handles malformed LLM output (unescaped
SQL quotes in ADF expressions).

### 7. Streaming NDJSON

Long-running operations (synthetic generation, batch validation) stream
progress via NDJSON over HTTP:

```
{"type": "plan", "count": 10, "specs": [...]}
{"type": "stage", "pipeline_index": 0, "stage": "generating", "pct": 10}
{"type": "progress", "completed": 1, "total": 10, "ok": true}
...
{"type": "complete", "result": {...}}
```

Frontend reads via `response.body.getReader()` with `TextDecoder`.

### 8. Persistent History (SQLite)

Activity log stored in SQLite (`{tempdir}/lmv_history.db`) with WAL mode.
Falls back to JSON file if sqlite3 unavailable. Stores validations, batch
runs, and synthetic generations. Survives server restarts.

---

## API Surface

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Health check |
| GET | `/api/status` | Capability report |
| POST | `/api/validate` | Validate one pipeline (ADF JSON, YAML, or snapshot) |
| POST | `/api/validate/expression` | LLM-judge expression equivalence |
| POST | `/api/validate/batch` | Validate golden set JSON |
| POST | `/api/validate/folder` | Scan folder of ADF JSONs (streaming) |
| GET | `/api/history` | Unified activity log |
| GET | `/api/history/{name}` | Per-pipeline validation history |
| POST | `/api/harness/run` | End-to-end harness with fix loop |
| POST | `/api/parallel/run` | ADF vs Databricks parallel test |
| GET | `/api/synthetic/templates` | List preset templates |
| POST | `/api/synthetic/resolve-template` | Resolve template to spec text |
| POST | `/api/synthetic/spec` | Generate structured spec |
| POST | `/api/synthetic/generate` | Generate pipelines (streaming) |
| GET | `/api/synthetic/runs` | List past generation directories |
| GET | `/api/config/wkmigrate` | Current repo/branch config |
| POST | `/api/config/wkmigrate` | Update config |
| POST | `/api/config/wkmigrate/apply` | Hot-swap wkmigrate at runtime |
| GET | `/api/config/wkmigrate/branches` | GitHub branch listing |

### MCP Tools

Exposed via SSE transport at `/mcp`:

- `validate_pipeline(adf_json)` → scorecard
- `validate_expression(adf_expression, python_code)` → score + reasoning
- `suggest_fix(context)` → suggestion
- `run_parallel_test(pipeline_name, parameters, snapshot)` → comparison

### CLI Commands

```bash
lmv validate <pipeline.json>
lmv batch <golden_set.json> --threshold 90
lmv harness <pipeline_name>
lmv synthetic --count 50 --difficulty complex
lmv parallel <pipeline_name>
lmv history <pipeline_name>
```

---

## Frontend Architecture

### Stack

- **React 18.3** + TypeScript 5.6
- **Tailwind CSS 4.2** with custom Stitch M3 Dark theme
- **Vite 6.0** for build + dev server
- **No state library** — React hooks + module-level store

### Pages

| Page | Route | Purpose |
|------|-------|---------|
| Validate | `#/validate` | Single pipeline → wkmigrate → score |
| Expression | `#/expression` | ADF expression ↔ Python equivalence |
| E2E Harness | `#/harness` | Full orchestration with fix loop |
| Parallel Testing | `#/parallel` | ADF vs Databricks output comparison |
| Batch Validation | `#/batch` | Folder scanning + agent analysis |
| Synthetic | `#/synthetic` | Spec → plan → pipeline generation |
| History | `#/history` | Activity timeline + synthetic runs |

### Design System (Stitch M3 Dark)

- **Fonts**: Outfit (headlines), DM Sans (body), IBM Plex Mono (code)
- **Colors**: base `#060a13`, surfaces `#0f131d`→`#30353f`, primary `#adc6ff`, tertiary `#27e199`, error `#ffb4ab`
- **Utilities**: `.glass-panel`, `.machined-chip`
- **Pattern**: Editor chrome with traffic-light dots, collapsible panels, NDJSON streaming progress

### Cross-Page Navigation

Module-level store (`store.ts`) passes data between pages:

```typescript
setPendingValidation({pipeline_name, adf_json, source: "synthetic"})
window.location.hash = "#/validate?pipeline=name"
// Validate page: consumePendingValidation() → auto-validate
```

---

## Deployment

### Databricks Apps

```yaml
# apps/lmv/app.yaml
command: "uvicorn apps.lmv.backend.main:app --host 0.0.0.0 --port 8000"
```

Required env vars:
- `DATABRICKS_HOST` — workspace URL (for FMAPI judge)
- `DATABRICKS_TOKEN` — PAT or OAuth

Optional (for harness/parallel):
- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`
- `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_FACTORY_NAME`

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --with api
COPY src/ src/
COPY apps/ apps/
# Pre-build frontend
COPY apps/lmv/frontend/dist/ apps/lmv/frontend/dist/
EXPOSE 8000
CMD ["uvicorn", "apps.lmv.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Local Development

```bash
# Backend
cp .env.example .env  # Set DATABRICKS_HOST + DATABRICKS_TOKEN
source .venv/bin/activate
uvicorn apps.lmv.backend.main:app --reload --port 8000

# Frontend (separate terminal, proxies to :8000)
cd apps/lmv/frontend && npm run dev

# Or production mode (backend serves built frontend)
cd apps/lmv/frontend && npm run build
uvicorn apps.lmv.backend.main:app --port 8000
```

### API-Only (No UI)

```python
from lakeflow_migration_validator.api import create_app
app = create_app(convert_fn=my_converter, judge_provider=my_judge)
# Run with uvicorn or any ASGI server
```

### MCP-Only (For Claude/Agents)

```python
from lakeflow_migration_validator.mcp_server import create_mcp_server
mcp = create_mcp_server(convert_fn=my_converter, judge_provider=my_judge)
# Mount mcp.sse_app() on any ASGI framework
```

### Library-Only (No Server)

```python
from lakeflow_migration_validator import evaluate, evaluate_from_wkmigrate

# Direct evaluation
scorecard = evaluate(snapshot)

# From wkmigrate
scorecard = evaluate_from_wkmigrate(adf_json, prepared_workflow)
```

---

## Testing Strategy

### Test Pyramid

```
Unit (277 tests)          — dimensions, scoring, serialization, API
Integration (CI-gated)    — live Azure + Databricks endpoints
Frontend (tsc + vite)     — type checking + build validation
```

### Running Tests

```bash
# Unit tests (no external dependencies)
pytest tests/unit/ -v

# Integration tests (requires Azure credentials)
pytest tests/integration/ -m "integration and not databricks"

# Databricks tests (requires workspace)
pytest tests/integration/ -m "databricks"

# Frontend
cd apps/lmv/frontend && npx tsc --noEmit && npm run build
```

### Golden Sets

Pre-generated test data in `golden_sets/`:
- `expressions.json` — 200 ADF → Python expression pairs
- `pipelines.json` — 60 synthetic pipelines with expected snapshots
- `regression_pipelines.json` — baseline for CCS regression detection

---

## Security Considerations

- **Credentials**: env vars only, never in code. `.env` is gitignored.
- **FMAPI tokens**: Bearer auth via `DATABRICKS_TOKEN`
- **Folder validation**: accepts local paths — restrict in production
  (e.g., allowlist directories or use a sandbox)
- **Error messages**: internal exceptions are logged server-side,
  generic messages returned to clients
- **Dependencies**: `litellm` pinned to exclude compromised versions
  (`!=1.82.7,!=1.82.8`)
