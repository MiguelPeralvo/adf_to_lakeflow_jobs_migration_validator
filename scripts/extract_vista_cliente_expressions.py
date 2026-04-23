#!/usr/bin/env python3
"""Extract IfCondition expressions from the Vista Cliente ADF corpus and emit
a stratified golden-set JSON plus a full category histogram.

Usage:
    python scripts/extract_vista_cliente_expressions.py \
        --corpus ~/Downloads/DataFactory/pipeline \
        --out golden_sets/vista_cliente_expressions.json \
        --hist dev/findings/vista-cliente-category-histogram-2026-04-23.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
from pathlib import Path

# 9 VC buckets -> canonical categories (keep X-6 reporting stable)
VC_TO_CANONICAL = {
    "compound_and": "logical",
    "compound_or": "logical",
    "nested_predicate": "logical",
    "equals_binary": "logical",
    "contains_intersection_empty": "collection",
    "concat_string": "string",
    "variables_ref": "nested",
    "bare_activity_output": "nested",
    "pipeline_param_ref": "nested",
}

# --- classification helpers -------------------------------------------------

def _classify(expr: str, depth: int) -> str:
    e = expr or ""
    low = e.lower()
    has_and = "@and(" in low
    has_or = "@or(" in low
    has_equals = "@equals(" in low
    has_contains = "@contains(" in low or "@intersection(" in low or "@empty(" in low
    has_concat = "@concat(" in low or "touppers(" in low or "toupper(" in low or "replace(" in low
    has_vars = "variables(" in low
    has_pipeline_param = "pipeline().parameters." in low
    bare_expr = e.strip().startswith("@{") is False and not e.strip().startswith("@")
    # priority: compound > nested > equals > contains > concat > variable > param > bare
    if has_and and (has_or or has_equals or has_contains):
        return "nested_predicate"
    if has_and:
        return "compound_and"
    if has_or:
        return "compound_or"
    if depth >= 2:
        return "nested_predicate"
    if has_equals:
        return "equals_binary"
    if has_contains:
        return "contains_intersection_empty"
    if has_concat:
        return "concat_string"
    if has_vars:
        return "variables_ref"
    if has_pipeline_param:
        return "pipeline_param_ref"
    if bare_expr:
        return "bare_activity_output"
    # fallback
    return "bare_activity_output"


# --- recursive walk ---------------------------------------------------------

def _walk_activities(activities, pipeline_name: str, out: list, depth: int = 0, parent: str = ""):
    if not isinstance(activities, list):
        return
    for act in activities:
        if not isinstance(act, dict):
            continue
        act_type = act.get("type", "")
        act_name = act.get("name", "")
        path = f"{parent}/{act_name}" if parent else act_name
        if act_type == "IfCondition":
            tp = act.get("typeProperties") or {}
            expr_obj = tp.get("expression") or {}
            expr_val = expr_obj.get("value") if isinstance(expr_obj, dict) else expr_obj
            if expr_val:
                vc_cat = _classify(expr_val, depth)
                out.append({
                    "pipeline": pipeline_name,
                    "activity_name": path,
                    "depth": depth,
                    "raw_expression": expr_val,
                    "vc_category": vc_cat,
                })
            # recurse
            _walk_activities(tp.get("ifTrueActivities") or [], pipeline_name, out, depth + 1, path)
            _walk_activities(tp.get("ifFalseActivities") or [], pipeline_name, out, depth + 1, path)
        # also traverse ForEach / Switch / Until children
        tp = act.get("typeProperties") or {}
        for child_key in ("activities", "ifTrueActivities", "ifFalseActivities", "defaultActivities"):
            # Skip ifTrueActivities/ifFalseActivities for IfCondition (already handled above at depth + 1)
            if act_type == "IfCondition" and child_key in ("ifTrueActivities", "ifFalseActivities"):
                continue
            if child_key in tp:
                _walk_activities(tp.get(child_key) or [], pipeline_name, out, depth, path)
        for case in tp.get("cases") or []:
            if isinstance(case, dict):
                _walk_activities(case.get("activities") or [], pipeline_name, out, depth, path)


def _extract_all(corpus_dir: Path) -> list[dict]:
    records: list[dict] = []
    for fp in sorted(corpus_dir.glob("*.json")):
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        props = d.get("properties") or {}
        activities = props.get("activities") or d.get("activities") or []
        _walk_activities(activities, fp.stem, records)
    return records


# --- sampling ---------------------------------------------------------------

def _stratified_sample(records: list[dict], seed: int = 42, total_target: int = 200,
                       floor: int = 12) -> list[dict]:
    from collections import defaultdict
    buckets: dict[str, list] = defaultdict(list)
    for r in records:
        buckets[r["vc_category"]].append(r)

    rng = random.Random(seed)
    for vals in buckets.values():
        rng.shuffle(vals)

    # First: take floor from each bucket (or all if smaller)
    out = []
    for vc_cat, vals in buckets.items():
        take = min(floor, len(vals))
        out.extend(vals[:take])

    # If under target, fill proportionally from remaining
    remaining = {k: v[min(floor, len(v)):] for k, v in buckets.items()}
    while len(out) < total_target:
        added = 0
        # proportional top-up by bucket size
        for vc_cat, vals in sorted(remaining.items(), key=lambda kv: -len(kv[1])):
            if len(out) >= total_target:
                break
            if vals:
                out.append(vals.pop(0))
                added += 1
        if added == 0:
            break  # exhausted
    return out


# --- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hist", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--total", type=int, default=200)
    ap.add_argument("--floor", type=int, default=12)
    args = ap.parse_args()

    corpus = Path(os.path.expanduser(args.corpus))
    records = _extract_all(corpus)
    from collections import Counter
    hist = Counter(r["vc_category"] for r in records)
    total_raw = len(records)

    hist_payload = {
        "corpus_dir": str(corpus),
        "total_if_condition_expressions": total_raw,
        "per_vc_category": dict(hist),
        "per_canonical_category": dict(Counter(VC_TO_CANONICAL[r["vc_category"]] for r in records)),
        "pipelines_seen": len({r["pipeline"] for r in records}),
    }
    Path(args.hist).parent.mkdir(parents=True, exist_ok=True)
    Path(args.hist).write_text(json.dumps(hist_payload, indent=2))

    # Filter out empty expressions
    records = [r for r in records if r["raw_expression"] and str(r["raw_expression"]).strip()]

    sample = _stratified_sample(records, seed=args.seed, total_target=args.total, floor=args.floor)

    expressions = []
    for r in sample:
        vc_cat = r["vc_category"]
        expressions.append({
            "adf_expression": r["raw_expression"],
            "category": VC_TO_CANONICAL[vc_cat],
            "vc_category": vc_cat,
            "expected_python": None,
            "source": {
                "pipeline": r["pipeline"],
                "activity_name": r["activity_name"],
                "depth": r["depth"],
            },
        })

    out_payload = {
        "count": len(expressions),
        "origin": "vista_cliente_if_condition_sweep_2026_04_23",
        "corpus": str(corpus),
        "sampling": {
            "seed": args.seed,
            "floor_per_vc_category": args.floor,
            "total_target": args.total,
            "strategy": "stratified_by_vc_category_with_floor_then_proportional_fill",
        },
        "vc_to_canonical_mapping": VC_TO_CANONICAL,
        "expressions": expressions,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out_payload, indent=2))

    print(f"wrote {args.out} (count={len(expressions)})")
    print(f"wrote {args.hist} (raw_total={total_raw})")
    print(f"per-vc_category histogram: {dict(hist)}")


if __name__ == "__main__":
    main()
