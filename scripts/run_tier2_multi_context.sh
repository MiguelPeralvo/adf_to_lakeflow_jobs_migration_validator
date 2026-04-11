#!/usr/bin/env bash
# Tier 2: run semantic-eval on the 6 remaining activity contexts.
# set_variable is already measured by Tier 1 — skip it here.
#
# Output: one JSON per context in golden_sets/semantic_eval_by_context/
# Also writes a summary table to stdout at the end.

set -euo pipefail

cd "$(dirname "$0")/.."
source .env
export DATABRICKS_HOST DATABRICKS_TOKEN

OUT_DIR=golden_sets/semantic_eval_by_context
mkdir -p "$OUT_DIR"

CORPUS=golden_sets/expression_loop_post_w16.json
MODEL=databricks-claude-sonnet-4-6

CONTEXTS=(notebook_base_param if_condition for_each web_body lookup_query copy_query)

echo "=== Tier 2: 6-context semantic-eval sweep ==="
echo "Corpus: $CORPUS"
echo "Model:  $MODEL"
echo ""

for ctx in "${CONTEXTS[@]}"; do
  echo ""
  echo "--- Running context: $ctx ---"
  # Each context = ~200 LLM calls. Run sequentially to avoid rate limits.
  poetry run lmv semantic-eval \
    --golden-set "$CORPUS" \
    --context "$ctx" \
    --model "$MODEL" \
    --output "$OUT_DIR/${ctx}.json" 2>&1 | tail -20
done

echo ""
echo "=== Tier 2 complete. Aggregating results ==="

python3 <<'PYEOF'
import json
import glob
import os

results = {}
for f in sorted(glob.glob("golden_sets/semantic_eval_by_context/*.json")):
    ctx = os.path.basename(f).replace(".json", "")
    with open(f) as fp:
        data = json.load(fp)
    results[ctx] = {
        "overall": data.get("overall_mean_score", 0.0),
        "by_category": data.get("by_category", {}),
        "low_scoring_count": data.get("low_scoring_count", 0),
        "total_evaluated": data.get("total_evaluated", 0),
    }

# Add Tier 1 result (set_variable) if present
t1_file = "golden_sets/semantic_eval_post_w17_w18.json"
if os.path.exists(t1_file):
    with open(t1_file) as fp:
        data = json.load(fp)
    results["set_variable"] = {
        "overall": data.get("overall_mean_score", 0.0),
        "by_category": data.get("by_category", {}),
        "low_scoring_count": data.get("low_scoring_count", 0),
        "total_evaluated": data.get("total_evaluated", 0),
    }

# Write summary
summary = {
    "tier": "Tier 2: 7-context semantic-eval summary",
    "results": results,
    "by_context_overall": {k: v["overall"] for k, v in results.items()},
}
with open("golden_sets/semantic_eval_all_contexts_summary.json", "w") as fp:
    json.dump(summary, fp, indent=2, sort_keys=True)

print("\n=== 7-context summary ===")
print(f"{'Context':<25s}  {'Overall':>8s}  {'Low':>6s}  {'Total':>6s}")
print("-" * 50)
for ctx in ["set_variable", "notebook_base_param", "if_condition", "for_each",
            "web_body", "lookup_query", "copy_query"]:
    if ctx in results:
        r = results[ctx]
        print(f"{ctx:<25s}  {r['overall']:>8.3f}  {r['low_scoring_count']:>6d}  {r['total_evaluated']:>6d}")
    else:
        print(f"{ctx:<25s}  {'MISSING':>8s}")

overall_mean = sum(v["overall"] for v in results.values()) / max(len(results), 1)
print(f"{'MEAN':<25s}  {overall_mean:>8.3f}")
PYEOF

echo ""
echo "=== Tier 2 summary written to golden_sets/semantic_eval_all_contexts_summary.json ==="
