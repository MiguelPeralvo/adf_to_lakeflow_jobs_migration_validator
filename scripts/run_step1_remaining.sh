#!/bin/bash
# Run remaining Step 1 contexts sequentially with updated calibration + deduped corpus
set -e
source .env
export DATABRICKS_HOST DATABRICKS_TOKEN

echo "=== lookup_query ==="
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context lookup_query \
  --model databricks-claude-sonnet-4-6 \
  --output golden_sets/semantic_eval_post_w25/lookup_query.json

echo "=== copy_query ==="
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context copy_query \
  --model databricks-claude-sonnet-4-6 \
  --output golden_sets/semantic_eval_post_w25/copy_query.json

echo "=== if_condition ==="
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context if_condition \
  --model databricks-claude-sonnet-4-6 \
  --output golden_sets/semantic_eval_post_w25/if_condition.json

echo "=== set_variable (re-run with updated calibration) ==="
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context set_variable \
  --model databricks-claude-sonnet-4-6 \
  --output golden_sets/semantic_eval_post_w25/set_variable_v2.json

echo "=== web_body ==="
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context web_body \
  --model databricks-claude-sonnet-4-6 \
  --output golden_sets/semantic_eval_post_w25/web_body.json

echo "All contexts complete!"
