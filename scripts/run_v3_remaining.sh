#!/bin/bash
# Run remaining 4 contexts with v3 calibration (variables + div rules)
set -e
source .env
export DATABRICKS_HOST DATABRICKS_TOKEN

echo "=== lookup_query v3 ==="
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context lookup_query \
  --model databricks-claude-sonnet-4-6 \
  --output golden_sets/semantic_eval_post_w25/lookup_query_v3.json

echo "=== copy_query v3 ==="
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context copy_query \
  --model databricks-claude-sonnet-4-6 \
  --output golden_sets/semantic_eval_post_w25/copy_query_v3.json

echo "=== if_condition v3 ==="
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context if_condition \
  --model databricks-claude-sonnet-4-6 \
  --output golden_sets/semantic_eval_post_w25/if_condition_v3.json

echo "=== web_body v3 ==="
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context web_body \
  --model databricks-claude-sonnet-4-6 \
  --output golden_sets/semantic_eval_post_w25/web_body_v3.json

echo "All v3 contexts complete!"
