import React, { useState } from "react";
import { api } from "../api";
import type { HarnessResult } from "../types";
import { TopHeader } from "../components/TopHeader";
import { ScorecardGauge } from "../components/ScorecardGauge";
import { DimensionBreakdown } from "../components/DimensionBreakdown";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";

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
        <div>
          <h2 className="text-3xl font-bold font-headline text-on-surface tracking-tight">Harness Run</h2>
          <p className="text-slate-400 mt-1">Execute end-to-end: fetch ADF → translate → validate → suggest fixes.</p>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        <section className="bg-surface-container rounded-xl p-6 border border-white/5 flex flex-col md:flex-row items-end gap-6 shadow-sm">
          <div className="flex-1 w-full">
            <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 font-mono">Pipeline Name</label>
            <div className="relative">
              <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-primary/60 text-lg">account_tree</span>
              <input
                value={pipelineName}
                onChange={(e) => setPipelineName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleRun()}
                placeholder="PROD_USER_DATA_MIGRATION_V4"
                className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 pl-12 pr-4 text-slate-100 font-mono text-sm focus:border-primary outline-none transition-all"
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
        </section>

        {loading && <div className="bg-surface-container rounded-xl p-8"><LoadingOverlay message="Running harness — this may take a minute..." /></div>}

        {result && !loading && (
          <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-8 items-start">
            <aside className="space-y-6">
              <div className="p-6 rounded-xl bg-surface-container-high border border-white/5 shadow-xl flex flex-col items-center">
                <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mb-6 font-mono">Performance Index</h3>
                <ScorecardGauge scorecard={result.scorecard} size={144} />
                <div className="w-full space-y-3 pt-4 mt-4 border-t border-white/5 text-xs">
                  <div className="flex justify-between"><span className="text-slate-500">Pipeline</span><span className="font-mono text-slate-200">{result.pipeline_name}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">Iterations</span><span className="font-mono text-slate-200">{result.iterations}</span></div>
                </div>
              </div>
            </aside>

            <section className="space-y-8">
              <DimensionBreakdown dimensions={result.scorecard.dimensions} />

              {result.fix_suggestions.length > 0 && (
                <div className="bg-surface-container rounded-xl p-6 border border-white/5">
                  <h3 className="text-sm font-headline font-semibold text-[#ffb547] uppercase tracking-wider mb-4">
                    <span className="material-symbols-outlined text-sm mr-2 align-middle">lightbulb</span>
                    Fix Suggestions ({result.fix_suggestions.length})
                  </h3>
                  <div className="space-y-3">
                    {result.fix_suggestions.map((s, i) => (
                      <pre key={i} className="p-4 bg-base rounded-lg border border-white/5 font-mono text-xs text-slate-300 overflow-x-auto whitespace-pre-wrap">
                        {JSON.stringify(s, null, 2)}
                      </pre>
                    ))}
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
