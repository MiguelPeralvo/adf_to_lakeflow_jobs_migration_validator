import React, { useState } from "react";
import { api } from "../api";
import type { HarnessResult, DimensionResult } from "../types";
import { TopHeader } from "../components/TopHeader";
import { ScorecardGauge } from "../components/ScorecardGauge";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";

const DIM_ICONS: Record<string, string> = {
  activity_coverage: "analytics",
  expression_coverage: "function",
  dependency_preservation: "link",
  notebook_validity: "code",
  parameter_completeness: "tune",
  secret_completeness: "security",
  not_translatable_ratio: "translate",
  semantic_equivalence: "psychology",
  runtime_success: "database",
  parallel_equivalence: "compare_arrows",
};

const DIM_LABELS: Record<string, string> = {
  activity_coverage: "Activity Coverage",
  expression_coverage: "Expression Coverage",
  dependency_preservation: "Dependency Preservation",
  notebook_validity: "Notebook Validity",
  parameter_completeness: "Parameter Completeness",
  secret_completeness: "Secret Completeness",
  not_translatable_ratio: "Translatable Ratio",
  semantic_equivalence: "Semantic Equivalence",
  runtime_success: "Runtime Success",
  parallel_equivalence: "Parallel Equivalence",
};

function dimDelta(score: number): { text: string; color: string } {
  if (score >= 0.95) return { text: "STABLE", color: "text-slate-500" };
  if (score >= 0.9) return { text: `+${((score - 0.9) * 100).toFixed(1)}%`, color: "text-tertiary" };
  if (score >= 0.7) return { text: `${(score * 100).toFixed(1)}%`, color: "text-primary" };
  return { text: `${(score * 100).toFixed(1)}%`, color: "text-error" };
}

export function HarnessPage() {
  const [pipelineName, setPipelineName] = useState("");
  const [result, setResult] = useState<HarnessResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    if (!pipelineName.trim()) return;
    setError(null); setResult(null); setLoading(true);
    try {
      setResult(await api.harnessRun(pipelineName.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Harness failed");
    } finally { setLoading(false); }
  }

  return (
    <>
      <TopHeader title="Harness Engine" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-7xl">
        <header className="mb-2">
          <h2 className="text-[20px] font-semibold font-headline text-slate-50">Harness Run</h2>
          <p className="text-sm text-slate-400 font-body mt-1">Execute automated stress tests and logical integrity benchmarks on your migration pipelines.</p>
        </header>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Input Card */}
        <section className="mb-10">
          <div className="p-6 rounded-xl bg-surface-container border border-white/5 flex flex-col md:flex-row items-end gap-6 shadow-sm">
            <div className="flex-1 w-full">
              <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 font-mono">Pipeline Name</label>
              <div className="relative group">
                <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-primary/60 text-lg">account_tree</span>
                <input
                  value={pipelineName}
                  onChange={(e) => setPipelineName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleRun()}
                  placeholder="PROD_USER_DATA_MIGRATION_V4"
                  className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 pl-12 pr-4 text-slate-100 font-mono text-sm focus:border-primary focus:ring-4 focus:ring-primary/10 outline-none transition-all"
                />
              </div>
            </div>
            <button
              onClick={handleRun}
              disabled={loading || !pipelineName.trim()}
              className={`h-[46px] px-8 rounded-lg font-bold text-sm flex items-center gap-2 transition-all shadow-lg ${
                loading || !pipelineName.trim()
                  ? "bg-primary/30 text-slate-500 cursor-wait"
                  : "bg-gradient-to-br from-primary to-primary-container text-on-primary-container hover:scale-[1.02] active:scale-95 shadow-primary/20"
              }`}
            >
              <span className="material-symbols-outlined text-lg">play_arrow</span>
              {loading ? "Running..." : "Run Harness"}
            </button>
          </div>
        </section>

        {loading && <div className="bg-surface-container rounded-xl p-8"><LoadingOverlay message="Running harness -- this may take a minute..." /></div>}

        {result && !loading && (
          <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-8 items-start">
            {/* Left Column: Scorecard */}
            <aside className="space-y-6">
              <div className="p-6 rounded-xl bg-surface-container-high border border-white/5 shadow-xl">
                <div className="flex flex-col items-center text-center">
                  <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mb-6 font-mono">Performance Index</h3>
                  <ScorecardGauge scorecard={result.scorecard} size={144} />
                  <div className="w-full space-y-4 pt-4 mt-4 border-t border-white/5">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-slate-500">Pipeline</span>
                      <span className="font-mono text-slate-200">{result.pipeline_name}</span>
                    </div>
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-slate-500">Iterations</span>
                      <span className="font-mono text-slate-200">{result.iterations.toLocaleString()}</span>
                    </div>
                  </div>
                </div>
              </div>
              {/* Integrity Status */}
              <div className="p-5 rounded-xl bg-surface-container-low border border-white/5">
                <h4 className="text-[11px] font-bold text-slate-400 uppercase mb-4">Integrity Status</h4>
                <div className="space-y-3">
                  {Object.entries(result.scorecard.dimensions).slice(0, 3).map(([name, dim]) => (
                    <div key={name} className="flex items-center gap-3">
                      <div className={`w-1.5 h-1.5 rounded-full ${dim.passed ? "bg-tertiary" : "bg-primary-container"}`} />
                      <span className="text-xs text-slate-300">{DIM_LABELS[name] || name}</span>
                    </div>
                  ))}
                </div>
              </div>
            </aside>

            {/* Right Column: Bento Dimension Cards + Fix Suggestions */}
            <section className="space-y-8">
              {/* Dimension Breakdown (Bento Style) */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {Object.entries(result.scorecard.dimensions)
                  .sort(([, a], [, b]) => b.score - a.score)
                  .slice(0, 6)
                  .map(([name, dim]) => {
                    const pct = Math.round(dim.score * 100);
                    const delta = dimDelta(dim.score);
                    const iconColor = dim.passed
                      ? dim.score >= 0.95 ? "text-tertiary" : "text-primary"
                      : "text-error";
                    return (
                      <div key={name} className="p-6 rounded-xl bg-surface-container border border-white/5 hover:bg-surface-container-high transition-colors">
                        <div className="flex justify-between items-start mb-4">
                          <span className={`material-symbols-outlined ${iconColor}`}>
                            {DIM_ICONS[name] || "analytics"}
                          </span>
                          <span className={`text-xs font-mono ${delta.color}`}>{delta.text}</span>
                        </div>
                        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">
                          {DIM_LABELS[name] || name}
                        </p>
                        <p className="text-2xl font-black font-headline text-slate-50">{pct}%</p>
                      </div>
                    );
                  })}
              </div>

              {/* Fix Suggestions */}
              {result.fix_suggestions.length > 0 && (
                <div className="p-8 rounded-xl bg-surface-container-low border border-white/5 relative overflow-hidden shadow-2xl">
                  <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full blur-[80px] -mr-32 -mt-32" />
                  <div className="flex items-center gap-3 mb-8">
                    <span className="material-symbols-outlined text-primary text-2xl">auto_awesome</span>
                    <div>
                      <h3 className="text-lg font-bold font-headline text-slate-50">Automated Fix Suggestions</h3>
                      <p className="text-xs text-slate-500">The LMV engine has identified {result.fix_suggestions.length} potential optimizations.</p>
                    </div>
                  </div>
                  <div className="space-y-6">
                    {result.fix_suggestions.map((s, i) => (
                      <div key={i} className="p-5 rounded-lg bg-surface-container border-l-4 border-primary/40">
                        <div className="flex justify-between items-center mb-4">
                          <span className="text-xs font-bold text-primary flex items-center gap-2">
                            <span className="material-symbols-outlined text-sm">lightbulb</span>
                            Optimization #{i + 1}
                          </span>
                          <span className="text-[10px] font-mono text-slate-500 uppercase">Priority: {i === 0 ? "High" : "Medium"}</span>
                        </div>
                        <pre className="bg-surface-container-lowest rounded-md p-4 font-mono text-[11px] leading-6 text-slate-400 border border-white/5 overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(s, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                  <div className="mt-8 flex justify-end gap-3">
                    <button className="px-5 py-2 rounded-md border border-outline-variant/20 text-xs font-bold text-slate-300 hover:bg-white/5 transition-all">Export Logs</button>
                    <button className="px-5 py-2 rounded-md bg-white text-[#060a13] text-xs font-bold hover:bg-slate-200 transition-all">Apply All Fixes</button>
                  </div>
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </>
  );
}
