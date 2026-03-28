import React, { useState } from "react";
import type { DimensionResult } from "../types";

const LABELS: Record<string, { label: string; icon: string }> = {
  activity_coverage: { label: "Activity Coverage", icon: "check_circle" },
  expression_coverage: { label: "Expression Coverage", icon: "function" },
  dependency_preservation: { label: "Dependency Preservation", icon: "link" },
  notebook_validity: { label: "Notebook Validity", icon: "code" },
  parameter_completeness: { label: "Parameter Completeness", icon: "tune" },
  secret_completeness: { label: "Secret Completeness", icon: "lock" },
  not_translatable_ratio: { label: "Translatable Ratio", icon: "translate" },
  semantic_equivalence: { label: "Semantic Equivalence", icon: "psychology" },
  runtime_success: { label: "Runtime Success", icon: "play_arrow" },
  parallel_equivalence: { label: "Parallel Equivalence", icon: "compare_arrows" },
};

function dimColor(score: number, passed: boolean): string {
  if (!passed) return "#ff5c5c";
  if (score >= 0.9) return "#27e199";
  if (score >= 0.7) return "#ffb547";
  return "#ff5c5c";
}

function DetailPanel({ name, details }: { name: string; details: Record<string, unknown> }) {
  const d = details;

  // Render actionable details based on dimension type
  if (name === "activity_coverage" && Array.isArray(d.placeholders) && d.placeholders.length > 0) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-slate-400">
          {String(d.covered ?? 0)} of {String(d.total ?? 0)} activities translated
        </p>
        <p className="text-[10px] font-mono text-red-400 uppercase tracking-wider">Placeholder activities:</p>
        {(d.placeholders as string[]).map((p) => (
          <div key={p} className="flex items-center gap-2 text-xs font-mono text-red-300 bg-red-500/5 px-3 py-1.5 rounded">
            <span className="material-symbols-outlined text-red-400 text-sm">warning</span>
            {p}
          </div>
        ))}
      </div>
    );
  }

  if (name === "notebook_validity" && Array.isArray(d.errors) && d.errors.length > 0) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-slate-400">{String(d.valid ?? 0)} of {String(d.total ?? 0)} notebooks valid</p>
        <p className="text-[10px] font-mono text-red-400 uppercase tracking-wider">Syntax errors:</p>
        {(d.errors as Array<{ file_path: string; error: string }>).map((e, i) => (
          <div key={i} className="bg-red-500/5 px-3 py-2 rounded space-y-0.5">
            <p className="text-xs font-mono text-slate-300">{e.file_path}</p>
            <p className="text-[11px] font-mono text-red-300">{e.error}</p>
          </div>
        ))}
      </div>
    );
  }

  if (name === "parameter_completeness" && Array.isArray(d.missing) && d.missing.length > 0) {
    return (
      <div className="space-y-2">
        <p className="text-[10px] font-mono text-amber-400 uppercase tracking-wider">Missing parameters:</p>
        <div className="flex flex-wrap gap-2">
          {(d.missing as string[]).map((p) => (
            <span key={p} className="px-2 py-1 bg-amber-500/10 border border-amber-500/20 rounded text-xs font-mono text-amber-300">
              {p}
            </span>
          ))}
        </div>
      </div>
    );
  }

  if (name === "secret_completeness" && Array.isArray(d.missing) && d.missing.length > 0) {
    return (
      <div className="space-y-2">
        <p className="text-[10px] font-mono text-amber-400 uppercase tracking-wider">Missing secrets:</p>
        {(d.missing as string[]).map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-xs font-mono text-amber-300 bg-amber-500/5 px-3 py-1.5 rounded">
            <span className="material-symbols-outlined text-amber-400 text-sm">vpn_key</span>
            {s}
          </div>
        ))}
      </div>
    );
  }

  // Generic fallback: render key-value pairs
  const entries = Object.entries(d).filter(
    ([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0)
  );
  if (entries.length === 0) return <p className="text-xs text-slate-600 italic">No additional details</p>;

  return (
    <div className="space-y-1.5">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-3 text-xs">
          <span className="font-mono text-slate-500 min-w-[140px] shrink-0">{key}</span>
          <span className="font-mono text-slate-300 break-all">
            {typeof value === "object" ? JSON.stringify(value) : String(value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function DimensionBreakdown({ dimensions }: { dimensions: Record<string, DimensionResult> }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const sorted = Object.entries(dimensions).sort(([, a], [, b]) => a.score - b.score);

  return (
    <div className="bg-surface-container rounded-xl overflow-hidden border border-white/5 shadow-xl">
      <div className="px-8 py-5 border-b border-white/5 bg-surface-container-high/20 flex justify-between items-center">
        <h3 className="font-headline text-lg text-on-surface font-semibold">Dimension Breakdown</h3>
        <div className="flex items-center gap-4 text-[10px] font-mono uppercase tracking-widest text-slate-500">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#27e199]" /> Pass
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#ff5c5c]" /> Fail
          </div>
        </div>
      </div>
      <div className="p-8 space-y-2">
        {sorted.map(([name, result]) => {
          const color = dimColor(result.score, result.passed);
          const pct = Math.round(result.score * 100);
          const meta = LABELS[name] || { label: name, icon: "help" };
          const isOpen = expanded === name;

          return (
            <div key={name}>
              <div
                onClick={() => setExpanded(isOpen ? null : name)}
                className="flex items-center gap-6 p-2 -m-2 rounded-lg hover:bg-surface-container-low/50 transition-colors cursor-pointer group"
              >
                <div className="w-6 flex items-center justify-center">
                  <span
                    className="material-symbols-outlined text-xl"
                    style={{ color, fontVariationSettings: "'FILL' 1" }}
                  >
                    {result.passed ? "check_circle" : "cancel"}
                  </span>
                </div>
                <div className="w-[180px] text-slate-300 text-sm font-medium">{meta.label}</div>
                <div className="flex-1 h-1.5 bg-surface-container-highest rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-1000"
                    style={{ width: `${pct}%`, backgroundColor: color }}
                  />
                </div>
                <div className="w-16 text-right font-mono text-sm font-semibold" style={{ color }}>
                  {pct}%
                </div>
                <span
                  className="material-symbols-outlined text-slate-600 text-sm transition-transform"
                  style={{ transform: isOpen ? "rotate(180deg)" : "rotate(0)" }}
                >
                  expand_more
                </span>
              </div>
              {isOpen && (
                <div className="ml-12 mt-2 mb-4 p-4 bg-base rounded-lg border border-white/5 animate-[fade-in-up_0.2s_ease]">
                  <DetailPanel name={name} details={result.details} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
