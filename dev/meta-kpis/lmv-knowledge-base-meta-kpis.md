# K-Series: Knowledge Base Meta-KPIs

These measure the health, coverage, and usefulness of the LLM knowledge base wiki at `knowledge/`. Loaded by `/lmv-autodev` for every session (knowledge base is always relevant).

> Reference loaded by `/lmv-autodev` Phase 0.5 (Knowledge Base Consultation).

## Coverage KPIs (soft gates, 10% tolerance)

| ID | Meta-KPI | Target | Measurement | Predicts |
|----|----------|--------|-------------|----------|
| **K-1** | Wiki page count | ≥ 7 (one per INDEX entry) | `ls knowledge/*.md \| wc -l` | Structural completeness |
| **K-2** | Failure mode coverage | 100% of issue-map signatures documented in failure-modes.md | `grep -c "###" knowledge/failure-modes.md` vs `jq '.failure_signatures \| length' dev/wkmigrate-issue-map.json` | Whether new failures get documented |
| **K-3** | Expression function coverage | ≥ 30 ADF functions documented in adf-expressions.md | `grep -c "^\| \`" knowledge/adf-expressions.md` | Whether the reference is usable for generation/judging |
| **K-4** | Learnings log freshness | At least 1 entry within last 7 days | `head -50 knowledge/learnings.md` and check most recent date | Whether sessions update the wiki |

## Quality KPIs (informational, no gate)

| ID | Meta-KPI | Target | Measurement | Predicts |
|----|----------|--------|-------------|----------|
| **K-5** | "Last updated" freshness | All pages updated within 14 days | grep "Last updated:" across all pages | Whether knowledge drifts from reality |
| **K-6** | Cross-reference integrity | All links in INDEX.md resolve to existing files | `grep -oP '\[.*?\]\((.*?)\)' knowledge/INDEX.md` then check existence | Structural health |
| **K-7** | Actionable insights per learning | ≥ 1 "Actionable for next session" per entry in learnings.md | count entries with that heading | Whether learnings are prescriptive, not just descriptive |

## Usage KPIs (tracked per session)

| ID | Meta-KPI | Target | Measurement | Predicts |
|----|----------|--------|-------------|----------|
| **K-8** | Pages consulted per session | ≥ 2 pages read in Phase 0.5 | Count Read tool calls targeting `knowledge/` in session | Whether agents actually use the wiki |
| **K-9** | Pages updated per session | ≥ 1 page updated in Phase 5.5 | Count Write/Edit tool calls targeting `knowledge/` in session | Whether sessions contribute back |
| **K-10** | Knowledge-informed decisions | ≥ 1 decision in the session explicitly references wiki content | Subjective review in session ledger | Whether the wiki influences behavior |

## Relationship to Other Series

- **K-2 ↔ A-3:** If A-3 (cluster attribution rate) drops, it means new failure modes exist that aren't in the issue map AND aren't in failure-modes.md. Both need updating.
- **K-4 ↔ K-9:** K-4 measures freshness passively; K-9 measures whether each session contributes. They're complementary.
- **K-8 ↔ all LR/X/A series:** The knowledge base is only valuable if it's consulted. K-8 is the leading indicator that the skill's Phase 0.5 is working.

## Notes

- The knowledge base follows Karpathy's LLM wiki pattern: structured markdown that LLMs can read before acting and update after learning.
- Unlike `dev/` files (which track operational state), `knowledge/` files capture **conceptual understanding** — rules, patterns, gotchas, and reasoning.
- The wiki should never duplicate code or git history. It captures the *why* and *how to think about* things, not the *what*.
