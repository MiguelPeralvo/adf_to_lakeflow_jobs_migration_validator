import React, { useState } from "react";
import { api } from "../api";
import type { HarnessResult } from "../types";
import { TopHeader } from "../components/TopHeader";
import { ScorecardGauge } from "../components/ScorecardGauge";
import { ErrorBanner } from "../components/ErrorBanner";

const DIM_META: Record<string, { label: string; icon: string }> = {
  activity_coverage:       { label: "Activity Coverage",       icon: "widgets" },
  expression_coverage:     { label: "Expression Coverage",     icon: "function" },
  dependency_preservation: { label: "Dependency Preservation", icon: "account_tree" },
  notebook_validity:       { label: "Notebook Validity",       icon: "code" },
  parameter_completeness:  { label: "Parameter Completeness",  icon: "tune" },
  secret_completeness:     { label: "Secret Completeness",     icon: "key" },
  not_translatable_ratio:  { label: "Translatable Ratio",      icon: "warning" },
  control_flow_fidelity:   { label: "Control Flow Fidelity",   icon: "alt_route" },
  semantic_equivalence:    { label: "Semantic Equivalence",     icon: "psychology" },
  runtime_success:         { label: "Runtime Success",          icon: "play_circle" },
  parallel_equivalence:    { label: "Parallel Equivalence",     icon: "compare_arrows" },
};

export function HarnessPage() {
  const [pipelineName, setPipelineName] = useState("");
  const [result, setResult] = useState<HarnessResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    if (!pipelineName.trim()) return;
    setError(null); setResult(null); setLoading(true);
    try { setResult(await api.harnessRun(pipelineName.trim())); }
    catch (err) { setError(err instanceof Error ? err.message : "Harness failed"); }
    finally { setLoading(false); }
  }

  const dims = result ? Object.entries(result.scorecard.dimensions) : [];
  const failingDims = dims.filter(([, d]) => !d.passed);

  return (
    <>
      <TopHeader title="E2E Harness" />
      <div className="pt-24 pb-16 px-10 max-w-7xl space-y-8" style={{ animation: "fade-in-up 0.4s ease both" }}>

        {/* Header */}
        <section className="flex justify-between items-end">
          <div>
            <h2 className="text-4xl font-bold font-headline text-on-surface tracking-tight">End-to-End Harness</h2>
            <p className="text-slate-500 font-body mt-2">
              Execute automated stress tests and logical integrity benchmarks on migrated pipelines.
            </p>
          </div>
          {result && (
            <div className="flex items-center gap-3 shrink-0">
              <span className="machined-chip border-primary text-primary px-3 py-1 rounded text-[10px] font-mono">
                {result.iterations} iteration{result.iterations !== 1 ? "s" : ""}
              </span>
              <span className={`machined-chip px-3 py-1 rounded text-[10px] font-mono ${
                result.scorecard.score >= 90 ? "border-tertiary text-tertiary" : result.scorecard.score >= 70 ? "border-primary text-primary" : "border-error text-error"
              }`}>
                CCS {Math.round(result.scorecard.score)}
              </span>
            </div>
          )}
        </section>

        {/* Input */}
        <div className="bg-surface-container rounded-xl border border-outline-variant/10 overflow-hidden">
          <div className="px-5 py-3 bg-surface-container-high/40 border-b border-outline-variant/5 flex justify-between items-center">
            <span className="font-mono text-[10px] text-slate-400 uppercase tracking-widest">Pipeline Target</span>
          </div>
          <div className="p-5 flex gap-4 items-end">
            <div className="flex-1 relative">
              <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-primary/50 text-lg">account_tree</span>
              <input value={pipelineName} onChange={e => setPipelineName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleRun()}
                placeholder="Enter pipeline name..."
                className="w-full bg-surface-container-lowest border-none rounded-lg py-3 pl-12 pr-4 text-on-surface font-mono text-sm outline-none focus:ring-1 focus:ring-primary" />
            </div>
            <button onClick={handleRun} disabled={loading || !pipelineName.trim()}
              className={`px-6 py-3 rounded-lg font-bold text-sm flex items-center gap-2 transition-all ${
                loading ? "bg-primary/30 text-slate-500 cursor-wait"
                        : "bg-gradient-to-br from-primary to-primary-container text-on-primary-container hover:scale-[1.02] shadow-lg shadow-blue-900/20"
              }`}>
              <span className="material-symbols-outlined text-sm">play_arrow</span>
              {loading ? "Running..." : "Run Harness"}
            </button>
          </div>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {loading && (
          <div className="bg-surface-container rounded-xl p-12 flex flex-col items-center gap-4">
            <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-sm font-mono text-outline">Running harness — this may take a minute...</span>
          </div>
        )}

        {result && !loading && (
          <div className="grid grid-cols-12 gap-6 items-start" style={{ animation: "fade-in-up 0.3s ease both" }}>
            {/* Left: Scorecard */}
            <div className="col-span-3 space-y-5 sticky top-24">
              <div className="bg-surface-container rounded-xl p-6 border border-outline-variant/10 flex flex-col items-center relative overflow-hidden">
                <div className="absolute inset-0 blur-[80px] pointer-events-none"
                  style={{ backgroundColor: result.scorecard.score >= 90 ? "rgba(39,225,153,0.04)" : result.scorecard.score >= 70 ? "rgba(255,181,71,0.04)" : "rgba(255,92,92,0.04)" }} />
                <span className="text-[10px] font-mono text-outline uppercase tracking-widest mb-4">Composite Score</span>
                <ScorecardGauge scorecard={result.scorecard} size={140} />
                <div className="w-full mt-5 pt-4 border-t border-outline-variant/10 space-y-2.5">
                  <div className="flex justify-between text-xs">
                    <span className="text-outline">Pipeline</span>
                    <span className="font-mono text-on-surface truncate ml-2 max-w-[120px]">{result.pipeline_name}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-outline">Iterations</span>
                    <span className="font-mono text-on-surface">{result.iterations}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-outline">Failing</span>
                    <span className={`font-mono ${failingDims.length > 0 ? "text-error" : "text-tertiary"}`}>{failingDims.length} dimensions</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right: Dimensions + Fix Suggestions */}
            <div className="col-span-9 space-y-6">
              {/* Dimension grid — all dimensions */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {dims.sort(([, a], [, b]) => a.score - b.score).map(([name, dim]) => {
                  const meta = DIM_META[name] || { label: name, icon: "help" };
                  const pct = Math.round(dim.score * 100);
                  return (
                    <div key={name} className={`p-4 rounded-xl border transition-colors ${
                      dim.passed ? "bg-surface-container border-outline-variant/10" : "bg-error/5 border-error/20"
                    }`}>
                      <div className="flex items-center justify-between mb-2">
                        <span className={`material-symbols-outlined text-sm ${dim.passed ? "text-outline" : "text-error"}`}>{meta.icon}</span>
                        <span className={`text-lg font-headline font-bold ${dim.passed ? "text-on-surface" : "text-error"}`}>{pct}%</span>
                      </div>
                      <p className="text-[9px] font-mono text-outline uppercase truncate">{meta.label}</p>
                      <div className="mt-2 h-1 bg-surface-container-highest rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${dim.passed ? "bg-tertiary" : "bg-error"}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Fix Suggestions */}
              {result.fix_suggestions.length > 0 && (
                <div className="bg-surface-container rounded-xl border border-outline-variant/10 overflow-hidden">
                  <div className="px-5 py-3 bg-surface-container-high/40 border-b border-outline-variant/5 flex items-center gap-3">
                    <span className="material-symbols-outlined text-primary text-sm">auto_awesome</span>
                    <span className="text-sm font-headline font-semibold text-on-surface">Fix Suggestions</span>
                    <span className="machined-chip border-primary text-primary px-2 py-0.5 rounded text-[9px] font-mono ml-auto">
                      {result.fix_suggestions.length} suggestion{result.fix_suggestions.length > 1 ? "s" : ""}
                    </span>
                  </div>
                  <div className="divide-y divide-outline-variant/5">
                    {result.fix_suggestions.map((s: Record<string, unknown>, i: number) => (
                      <details key={i} className="group" open={i === 0}>
                        <summary className="px-5 py-3 cursor-pointer hover:bg-surface-container-high/30 transition-colors flex items-center gap-3">
                          <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                            i === 0 ? "bg-error/10 text-error border border-error/20" : "bg-primary/10 text-primary border border-primary/20"
                          }`}>{i + 1}</span>
                          <span className="text-sm font-mono text-on-surface flex-1">
                            {String(s.dimension || s.dimension_name || `Suggestion ${i + 1}`).replace(/_/g, " ")}
                          </span>
                          <span className="text-[10px] font-mono text-outline">Priority {i === 0 ? "HIGH" : i === 1 ? "MED" : "LOW"}</span>
                          <span className="material-symbols-outlined text-sm text-outline group-open:rotate-180 transition-transform">expand_more</span>
                        </summary>
                        <div className="px-5 pb-4 pt-1 space-y-3">
                          {typeof s.diagnosis === "string" && s.diagnosis && (
                            <div className="pl-8">
                              <p className="text-[9px] font-mono text-outline uppercase mb-1">Diagnosis</p>
                              <p className="text-xs text-on-surface/80 leading-relaxed">{s.diagnosis}</p>
                            </div>
                          )}
                          {typeof s.suggestion === "string" && s.suggestion && (
                            <div className="pl-8">
                              <p className="text-[9px] font-mono text-outline uppercase mb-1">Suggested Fix</p>
                              <p className="text-xs text-tertiary/90 leading-relaxed">{s.suggestion}</p>
                            </div>
                          )}
                          {!s.diagnosis && !s.suggestion && (
                            <pre className="pl-8 text-[11px] font-mono text-on-surface/60 bg-surface-container-lowest rounded-lg p-3 overflow-auto max-h-40">
                              {JSON.stringify(s, null, 2)}
                            </pre>
                          )}
                        </div>
                      </details>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
