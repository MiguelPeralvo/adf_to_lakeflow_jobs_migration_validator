# Architectural & Design Decisions

This document records the key decisions made during LMV development, their
rationale, and their trade-offs.

---

## ADR-001: Tool-Agnostic Contract (ConversionSnapshot)

**Decision:** All evaluation dimensions operate on `ConversionSnapshot`, a
frozen dataclass with no imports from wkmigrate or any other migration tool.

**Context:** wkmigrate is the primary migration tool today, but the validator
should work with any tool that produces Databricks artifacts from ADF.

**Rationale:**
- Single adapter boundary (`wkmigrate_adapter.py`) isolates all wkmigrate types
- Adding a new tool adapter (e.g., for a custom converter) requires one file
- Dimensions never need to change when wkmigrate's internal API changes
- Frozen dataclasses prevent accidental mutation during evaluation

**Trade-off:** The adapter must manually extract fields, which can drift if
wkmigrate adds new artifact types. Mitigated by adapter-specific tests.

---

## ADR-002: Single-Process Multi-Surface Architecture

**Decision:** One FastAPI process serves REST API, MCP SSE, and static
frontend. No microservices, no message queues.

**Context:** LMV runs as a Databricks App (single container) and also
locally for development. Adding infrastructure complexity would slow both.

**Rationale:**
- Databricks Apps expect a single command/port
- All surfaces share the same providers (judge, harness, converter)
- No inter-service latency or state synchronization
- Frontend served as static files from the same process

**Trade-off:** CPU-heavy LLM calls block the event loop for other requests.
Mitigated by FastAPI's thread pool for sync endpoints and NDJSON streaming
for long-running operations.

---

## ADR-003: Environment-Based Dependency Injection

**Decision:** Providers are built from environment variables at startup.
Missing providers cause graceful degradation, not crashes.

**Context:** Different deployments have different credentials available.
Local dev may have no Azure credentials. Databricks Apps have workspace tokens.

**Rationale:**
- `/api/status` reports which capabilities are active
- Endpoints needing unavailable providers return 503
- No configuration files to manage across environments
- `.env` file loaded for local dev, ignored in production

**Trade-off:** No compile-time validation of provider configuration.
Mitigated by startup logging and the status endpoint.

---

## ADR-004: NDJSON Streaming for Long Operations

**Decision:** Synthetic generation and batch validation stream progress
as newline-delimited JSON over HTTP POST responses.

**Context:** Generating 50 LLM-backed pipelines takes minutes. Batch
validation of 100+ pipelines needs real-time progress.

**Alternatives considered:**
- **WebSocket:** More complex, requires client-side reconnection logic
- **SSE (Server-Sent Events):** GET-only, awkward for POST payloads
- **Polling:** Extra endpoints, state management, timing issues

**Rationale:**
- Works with standard `fetch()` + `ReadableStream` in browsers
- POST body carries the full request; response streams events
- Each line is self-contained JSON — easy to parse incrementally
- FastAPI `StreamingResponse` with sync generators works naturally

**Trade-off:** Browser `fetch()` doesn't support automatic reconnection
like SSE. Acceptable because these are one-shot operations, not persistent
subscriptions.

---

## ADR-005: Plan-Then-Execute for LLM Generation

**Decision:** Synthetic pipeline generation uses a two-phase flow:
(1) LLM produces a structured plan, (2) each pipeline generated per plan spec.

**Context:** Users write a natural-language spec. Direct single-shot
generation produced inconsistent counts and unfocused stress areas.

**Rationale:**
- Plan gives the user visibility into what will be generated
- Each pipeline gets a focused prompt with its specific name and stress area
- Failed pipelines don't affect others (isolated retries)
- Per-pipeline staged progress (preparing → LLM → parsing → validating)
- Plan can be user-edited (spec → plan is a controllable step)

**Trade-off:** Extra LLM call for the planning phase (16K tokens).
Justified by dramatically better generation quality and user control.

---

## ADR-006: json_repair for LLM JSON Output

**Decision:** Use the `json_repair` library as fallback when `json.loads`
fails on LLM-generated pipeline JSON.

**Context:** LLM (Opus 4.6) generates complex ADF pipelines with SQL
expressions containing single-quote patterns (`''''`) that produce
structurally broken JSON (~50% failure rate without repair).

**Alternatives considered:**
- **Custom regex repair:** Handled simple cases but couldn't fix structural
  issues (prematurely closed string boundaries)
- **Structured outputs / tool use:** Would constrain the LLM's ability to
  generate realistic complex expressions
- **Retry until valid:** Wasteful — same prompt often produces same error

**Rationale:**
- `json_repair` handles the specific SQL-quote-in-JSON pattern reliably
- Falls back gracefully — `json.loads` tried first (fast path)
- No constraints on what the LLM can generate

**Trade-off:** Adds a dependency. The repair might silently alter JSON
structure in unexpected ways. Mitigated by `_is_adf_pipeline()` validation
after repair.

---

## ADR-007: Hot-Swappable wkmigrate

**Decision:** wkmigrate can be switched to a different GitHub repo + branch
at runtime without server restart.

**Context:** Users test their wkmigrate changes by validating against
synthetic pipelines. Restarting the server loses in-memory state and
interrupts workflows.

**Implementation:**
1. `POST /api/config/wkmigrate/apply` clones/fetches the repo
2. `pip install -e` (editable, no-deps) from the clone
3. `importlib.reload()` on all `wkmigrate.*` modules
4. `_build_convert_fn()` called again to pick up new code
5. Mutable `convert_holder` dict swaps the function pointer

**Trade-off:** Module reloading is inherently fragile — class instances
created before the reload retain old method implementations. Acceptable
because validation creates fresh objects per request. The convert_fn is
stateless.

---

## ADR-008: SQLite History with JSON Fallback

**Decision:** Activity log persisted to SQLite with WAL mode. Falls back
to JSON file if sqlite3 is unavailable.

**Context:** In-memory history was lost on every server restart. Users
need to see past validations and synthetic runs.

**Rationale:**
- SQLite is in the Python standard library — no extra dependency
- WAL mode allows concurrent reads during writes
- Indexed on type and timestamp for fast queries
- JSON fallback ensures the feature works everywhere (even restricted envs)
- Single file — easy to back up or mount as a volume

**Trade-off:** SQLite doesn't scale to multiple server instances. For
multi-instance deployments, replace with PostgreSQL or a shared store.

---

## ADR-009: Stitch M3 Dark Design System

**Decision:** Frontend uses a custom Tailwind v4 theme based on Google's
Material 3 dark palette, branded as "Stitch."

**Context:** The UI needs a distinctive, production-grade aesthetic that
works well for data engineering tools — high information density, dark
background for long sessions, clear visual hierarchy.

**Key tokens:**
- Base: `#060a13` (near-black void)
- Primary: `#adc6ff` (blue)
- Tertiary: `#27e199` (green — success, completion)
- Error: `#ffb4ab` (red — failures, warnings)
- Fonts: Outfit (headlines), DM Sans (body), IBM Plex Mono (code)

**Patterns:**
- Editor chrome with traffic-light dots (mimics code editor)
- `machined-chip` — left-bordered status badges
- `glass-panel` — blurred transparent overlays
- Collapsible `<details>` for progressive disclosure

---

## ADR-010: Agent-Powered Batch Analysis

**Decision:** Batch validation optionally runs LLM analysis on each
failing pipeline, diagnosing why dimensions failed and suggesting fixes.

**Context:** Programmatic scores tell you WHAT failed but not WHY.
Users need actionable guidance to fix wkmigrate or their ADF pipelines.

**Implementation:**
- `agent_analysis: true` flag on the folder validation request
- For each failing pipeline, sends the source ADF activities + converted
  tasks + dimension details to `provider.complete()` (free-text response)
- Streams `analysis_start` and `analysis` events for real-time UI updates
- Results stored on each case as `agent_analysis[]`

**Trade-off:** One LLM call per failing dimension per failing pipeline.
For a batch of 100 pipelines with 3 failing dimensions each, that's
up to 300 LLM calls. The toggle is off by default.
