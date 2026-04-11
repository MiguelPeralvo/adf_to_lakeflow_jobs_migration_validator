#!/usr/bin/env bash
# Tier 6-PRE: sequential synthetic pipeline generation (not parallel to avoid FMAPI quota contention).
# Produces ~350 pipelines across 7 presets → merged into golden_sets/big_pipeline_corpus.json

set -uo pipefail

cd "$(dirname "$0")/.."
source .env
export DATABRICKS_HOST DATABRICKS_TOKEN

mkdir -p golden_sets/gen
mkdir -p /tmp/autonomous_gen_logs

# Smaller count per preset (25 × 7 = 175 pipelines) for faster first pass,
# can be re-run for a second batch if needed. Sequential to avoid rate limits.
COUNT=25
PRESETS=(complex_expressions math_on_params deep_nesting activity_mix \
         full_coverage pipeline_invocation unsupported_types)

for preset in "${PRESETS[@]}"; do
  START=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] Generating $COUNT pipelines for preset: $preset ==="
  OUT_DIR="golden_sets/gen/${preset}"
  rm -rf "$OUT_DIR"
  mkdir -p "$OUT_DIR"

  poetry run lmv synthetic \
    --count "$COUNT" --mode llm --preset "$preset" \
    --output "$OUT_DIR" \
    > "/tmp/autonomous_gen_logs/${preset}.log" 2>&1

  EXIT=$?
  END=$(date +%s)
  ELAPSED=$((END - START))
  if [ $EXIT -eq 0 ]; then
    if [ -f "$OUT_DIR/suite.json" ]; then
      count=$(python3 -c "import json; print(len(json.load(open('$OUT_DIR/suite.json')).get('pipelines', [])))" 2>/dev/null || echo "?")
      echo "  ✓ $preset done in ${ELAPSED}s — suite has $count pipelines"
    else
      echo "  ⚠ $preset exited 0 but no suite.json at $OUT_DIR"
    fi
  else
    echo "  ✗ $preset FAILED (exit $EXIT, ${ELAPSED}s) — see /tmp/autonomous_gen_logs/${preset}.log"
    tail -5 "/tmp/autonomous_gen_logs/${preset}.log" 2>&1 | sed 's/^/    /'
  fi
done

echo ""
echo "=== Merging all generated suites ==="
python3 <<'PYEOF'
import json
import glob
import os
from pathlib import Path

all_pipelines = []
for suite_path in sorted(glob.glob("golden_sets/gen/*/suite.json")):
    try:
        with open(suite_path) as f:
            data = json.load(f)
        pipes = data.get("pipelines", [])
        preset = Path(suite_path).parent.name
        # Tag each pipeline with its source preset for traceability
        for p in pipes:
            p["_source_preset"] = preset
        all_pipelines.extend(pipes)
        print(f"  {preset}: {len(pipes)} pipelines")
    except Exception as e:
        print(f"  ERROR loading {suite_path}: {e}")

merged = {"pipelines": all_pipelines, "count": len(all_pipelines)}
out = "golden_sets/big_pipeline_corpus.json"
with open(out, "w") as f:
    json.dump(merged, f, indent=2, default=str)
print(f"\nMerged {len(all_pipelines)} pipelines into {out}")
PYEOF

echo "=== Tier 6-PRE complete ==="
