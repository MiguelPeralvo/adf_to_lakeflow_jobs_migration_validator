#!/usr/bin/env python3
"""Aggregate Step-7 sweep results into an X-series KPI table.

Reads the VC and CRP0001 sweep JSONs produced by `lmv sweep-activity-contexts`
and emits a Markdown table with X-1 / X-6 numbers per corpus + per category.

Usage:
    python scripts/compute_step7_kpis.py
"""
from __future__ import annotations

import json
from pathlib import Path

RESULTS_DIR = Path("dev/results/step-7-vista-cliente")

VC_IF = RESULTS_DIR / "sweep-if-condition-2026-04-23.json"
VC_ALL = RESULTS_DIR / "sweep-all-contexts-2026-04-23.json"
CRP_IF = RESULTS_DIR / "crp0001-baseline-replay-2026-04-23.json"


def _coverage(cell: dict) -> float:
    total = cell.get("total", 0)
    resolved = cell.get("resolved", 0)
    return resolved / total if total else 0.0


def _per_category(sweep: dict, context: str = "if_condition") -> dict:
    out: dict[str, dict] = {}
    for key, cell in sweep.get("by_cell", {}).items():
        cat, ctx = key.split(",", 1)
        if ctx != context:
            continue
        out[cat] = cell
    return out


def main():
    vc_if = json.loads(VC_IF.read_text())
    vc_all = json.loads(VC_ALL.read_text())
    crp_if = json.loads(CRP_IF.read_text())

    # X-1: overall resolution ratio for if_condition
    vc_context = vc_if["by_context"]["if_condition"]
    crp_context = crp_if["by_context"]["if_condition"]

    vc_x1 = _coverage(vc_context)
    crp_x1 = _coverage(crp_context)
    baseline_x1 = 0.8317  # from wkmigrate-issue-27-meta-kpis.md

    # X-6: per-canonical-category resolution
    vc_cat = _per_category(vc_if)
    crp_cat = _per_category(crp_if)

    # Secondary: VC all-contexts
    vc_all_ctx = vc_all.get("by_context", {})

    out = []
    out.append("# Step 7 — Vista Cliente Sweep KPI Table\n")
    out.append("Generated: 2026-04-23  |  wkmigrate SHA: cfb49e6\n\n")
    out.append("## X-1 Expression Coverage (if_condition)\n")
    out.append("| Corpus | Resolved | Total | Coverage | Baseline | Delta | Within +/-5% |\n")
    out.append("|---|---|---|---|---|---|---|\n")
    delta_crp = crp_x1 - baseline_x1
    delta_vc = vc_x1 - baseline_x1
    out.append("| CRP0001 baseline (pinned) | — | — | 0.8317 | 0.8317 | 0.0000 | yes |\n")
    gate_crp = "yes" if abs(delta_crp) <= 0.05 else "NO (hard-gate flag)"
    out.append(f"| CRP0001 replay @ cfb49e6 | {crp_context['resolved']} | {crp_context['total']} | {crp_x1:.4f} | 0.8317 | {delta_crp:+.4f} | {gate_crp} |\n")
    gate_vc = "yes" if abs(delta_vc) <= 0.05 else "NO (expected: different corpus)"
    out.append(f"| Vista Cliente @ cfb49e6 | {vc_context['resolved']} | {vc_context['total']} | {vc_x1:.4f} | 0.8317 | {delta_vc:+.4f} | {gate_vc} |\n\n")

    out.append("## X-6 Per-canonical-category Coverage (if_condition, target >=0.70)\n")
    out.append("| Category | CRP0001 resolved/total | CRP0001 cov | VC resolved/total | VC cov | Delta | VC Pass |\n")
    out.append("|---|---|---|---|---|---|---|\n")
    all_cats = sorted(set(vc_cat.keys()) | set(crp_cat.keys()))
    per_cat_table = []
    for cat in all_cats:
        cc = crp_cat.get(cat)
        vc = vc_cat.get(cat)
        ccov = _coverage(cc) if cc else None
        vcov = _coverage(vc) if vc else None
        crp_s = f"{cc['resolved']}/{cc['total']}" if cc else "—"
        vc_s = f"{vc['resolved']}/{vc['total']}" if vc else "—"
        crp_c = f"{ccov:.4f}" if ccov is not None else "—"
        vc_c = f"{vcov:.4f}" if vcov is not None else "—"
        if ccov is not None and vcov is not None:
            dl = vcov - ccov
            dl_s = f"{dl:+.4f}"
        else:
            dl_s = "—"
        vc_pass = "yes" if (vcov is not None and vcov >= 0.70) else ("—" if vcov is None else "NO")
        out.append(f"| {cat} | {crp_s} | {crp_c} | {vc_s} | {vc_c} | {dl_s} | {vc_pass} |\n")
        per_cat_table.append({"cat": cat, "crp_cov": ccov, "vc_cov": vcov})
    out.append("\n")

    out.append("## X-2 Semantic Equivalence (if_condition)\n")
    out.append("| Corpus | Status |\n|---|---|\n")
    out.append("| CRP0001 | BLOCKED — DATABRICKS_HOST unset; judge-dependent |\n")
    out.append("| Vista Cliente | BLOCKED — DATABRICKS_HOST unset + `expected_python` null (VC lacks oracle) |\n\n")

    out.append("## Secondary: VC all-contexts resolution\n")
    out.append("| Context | Resolved | Total | Coverage | not_translatable |\n")
    out.append("|---|---|---|---|---|\n")
    for ctx, cell in sorted(vc_all_ctx.items()):
        cov = _coverage(cell)
        out.append(f"| {ctx} | {cell.get('resolved',0)} | {cell.get('total',0)} | {cov:.4f} | {cell.get('not_translatable_count',0)} |\n")

    print("".join(out))

    # also dump a JSON summary
    summary_path = RESULTS_DIR / "step7-kpi-summary-2026-04-23.json"
    summary_path.write_text(json.dumps({
        "wkmigrate_sha": "cfb49e6",
        "baseline_x1": baseline_x1,
        "crp0001_replay_x1": crp_x1,
        "vista_cliente_x1": vc_x1,
        "delta_crp_vs_baseline": delta_crp,
        "delta_vc_vs_baseline": delta_vc,
        "crp_within_5pct": abs(delta_crp) <= 0.05,
        "x6_per_category": {cat: {"crp_cov": c.get("crp_cov"), "vc_cov": c.get("vc_cov")} for cat, c in zip([x["cat"] for x in per_cat_table], per_cat_table)},
        "vc_all_contexts": {ctx: _coverage(cell) for ctx, cell in vc_all_ctx.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
