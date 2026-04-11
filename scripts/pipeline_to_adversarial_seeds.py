#!/usr/bin/env python3
"""Convert low-scoring pipelines from batch eval into adversarial generation seeds.

Usage:
    python3 scripts/pipeline_to_adversarial_seeds.py \
        --batch-results golden_sets/batch_results_post_w18.json \
        --output golden_sets/adversarial_seeds_round1.json \
        --top-failures 20

Reads `lmv batch` output, picks the N lowest-scoring pipelines, analyzes what
dimensions they failed, and emits a prompt suitable for feeding back into
`lmv synthetic --mode llm --prompt ...` for another adversarial round.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-results", required=True,
                        help="Path to lmv batch output JSON")
    parser.add_argument("--output", required=True, help="Output JSON with adversarial seed prompt")
    parser.add_argument("--top-failures", type=int, default=20,
                        help="How many lowest-scoring pipelines to analyze")
    args = parser.parse_args()

    with open(args.batch_results) as fp:
        batch = json.load(fp)

    # Structure varies — adapt to both BatchResult and cases-style output
    cases = batch.get("cases") or batch.get("results") or batch.get("pipelines") or []
    if not cases:
        print("No cases found in batch results. Keys:", list(batch.keys()))
        return 2

    # Sort by score ascending, take the worst
    def get_score(c: dict) -> float:
        return c.get("ccs_score") or c.get("mean_score") or c.get("score") or 0.0

    sorted_cases = sorted(cases, key=get_score)
    worst = sorted_cases[: args.top_failures]

    if not worst:
        print("No failing cases to analyze.")
        return 0

    # Count which dimensions failed most often
    dimension_fail_counts: Counter[str] = Counter()
    sample_failures: list[dict] = []

    for case in worst:
        pipeline_name = case.get("pipeline_name") or case.get("name") or "unknown"
        score = get_score(case)
        dims = case.get("dimensions") or case.get("dimension_scores") or {}
        for dim_name, dim_val in dims.items():
            if isinstance(dim_val, dict):
                dim_score = dim_val.get("score", 1.0)
            else:
                dim_score = dim_val
            if dim_score < 0.7:
                dimension_fail_counts[dim_name] += 1
        if len(sample_failures) < 5:
            sample_failures.append({
                "pipeline_name": pipeline_name,
                "score": score,
                "weakest_dimensions": [d for d, v in (case.get("dimensions") or {}).items()
                                        if (v if isinstance(v, (int, float)) else v.get("score", 1.0)) < 0.7],
            })

    top_failed_dims = dimension_fail_counts.most_common(5)

    # Build the adversarial prompt
    prompt_lines = [
        f"Generate {args.top_failures * 3} ADF pipelines that specifically stress the following converter weaknesses identified by a previous batch evaluation round:",
        "",
    ]
    for dim, count in top_failed_dims:
        prompt_lines.append(f"- **{dim}**: {count}/{args.top_failures} failing pipelines scored below 0.7 on this dimension")

    prompt_lines.append("")
    prompt_lines.append("Each generated pipeline should:")
    prompt_lines.append("- Use realistic naming (etl_*, extract_*, transform_*, load_*)")
    prompt_lines.append("- Include 4-8 activities with dependency chains")
    prompt_lines.append("- Mix supported and unsupported activity types")
    prompt_lines.append("- Use pipeline parameters of various types (String, Int, Float, Bool)")
    prompt_lines.append("- Use expressions 2+ levels deep where relevant")
    prompt_lines.append("- Include at least one activity referencing upstream activity output")

    # Sample specific failure patterns from the worst cases
    if sample_failures:
        prompt_lines.append("")
        prompt_lines.append("Specific weak patterns to target (from the worst 5 pipelines of the previous round):")
        for s in sample_failures:
            weak = ", ".join(s["weakest_dimensions"]) or "mixed"
            prompt_lines.append(f"- {s['pipeline_name']}: weakest dimensions = {weak}")

    prompt_lines.append("")
    prompt_lines.append("Output ONLY valid ADF pipeline JSON, one pipeline per emit.")

    seed = {
        "top_failures": args.top_failures,
        "total_worst_analyzed": len(worst),
        "dimension_failure_counts": dict(top_failed_dims),
        "sample_failures": sample_failures,
        "prompt": "\n".join(prompt_lines),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(seed, indent=2), encoding="utf-8")

    print(f"Analyzed {len(worst)} worst pipelines.")
    print(f"Top failed dimensions: {top_failed_dims}")
    print(f"Adversarial seed prompt written to {out} ({len(seed['prompt'])} chars).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
