import React, { useState } from "react";
import { api } from "../api";
import type { ParallelResult, ComparisonRow } from "../types";
import { TopHeader } from "../components/TopHeader";
import { ScorecardGauge } from "../components/ScorecardGauge";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";

export function ParallelPage() {
  const [pipelineName, setPipelineName] = useState("");
  const [paramsJson, setParamsJson] = useState('{ "env": "dev" }');
  const [result, setResult] = useState<ParallelResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    if (!pipelineName.trim()) return;
    setError(null); setResult(null); setLoading(true);
    try {
      const params = JSON.parse(paramsJson);
      setResult(await api.parallelRun(pipelineName.trim(), params));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parallel run failed");
    } finally { setLoading(false); }
  }

  const eqPct = result ? Math.round(result.equivalence_score * 100) : 0;
  const eqColor = eqPct >= 90 ? "#27e199" : eqPct >= 70 ? "#ffb547" : "#ff5c5c";

  return (
    <>
      <TopHeader title="Parallel Engine" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-7xl">
        <div>
          <h2 className="text-4xl font-extrabold text-slate-50 font-headline tracking-tight">Parallel Test</h2>
          <p className="text-slate-400 mt-2 text-lg">Simultaneously execute ADF and Databricks workflows to validate logic parity.</p>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        <section className="bg-surface-container rounded-xl p-8 shadow-2xl shadow-blue-900/5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
              <label className="block text-xs font-bold text-primary tracking-widest uppercase mb-3">Pipeline Name</label>
              <input
                value={pipelineName}
                onChange={(e) => setPipelineName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleRun()}
                placeholder="DW_Sales_Ingestion_Monthly"
                className="w-full bg-surface-container-lowest border-none rounded-lg p-4 text-slate-200 font-mono focus:ring-2 focus:ring-primary/20 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-primary tracking-widest uppercase mb-3">Parameters (JSON)</label>
              <textarea
                value={paramsJson}
                onChange={(e) => setParamsJson(e.target.value)}
                rows={1}
                className="w-full bg-surface-container-lowest border-none rounded-lg p-4 text-slate-200 font-mono focus:ring-2 focus:ring-primary/20 outline-none resize-none"
              />
            </div>
          </div>
          <div className="mt-8 flex justify-end">
            <button
              onClick={handleRun}
              disabled={loading || !pipelineName.trim()}
              className="bg-gradient-to-br from-primary to-primary-container text-on-primary-container px-8 py-3 rounded-lg font-bold text-sm tracking-wide shadow-lg shadow-primary/10 hover:scale-[1.02] active:scale-95 transition-all"
            >
              {loading ? "RUNNING..." : "RUN PARALLEL TEST"}
            </button>
          </div>
        </section>

        {loading && <div className="bg-surface-container rounded-xl p-8"><LoadingOverlay message="Executing on ADF + Databricks..." /></div>}

        {result && !loading && (
          <div className="flex flex-col lg:flex-row gap-8">
            {/* Left: gauges */}
            <aside className="w-full lg:w-[280px] flex flex-col gap-6">
              <div className="bg-surface-container-low rounded-xl p-6 flex flex-col items-center text-center">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">Logic Equivalence</span>
                <div className="relative w-32 h-32 flex items-center justify-center">
                  <svg className="w-full h-full -rotate-90">
                    <circle className="text-surface-container-highest" cx="64" cy="64" r="58" fill="transparent" stroke="currentColor" strokeWidth={8} />
                    <circle cx="64" cy="64" r="58" fill="transparent" stroke={eqColor} strokeWidth={8} strokeLinecap="round"
                      strokeDasharray={364.4} strokeDashoffset={364.4 - (eqPct / 100) * 364.4}
                      style={{ transition: "stroke-dashoffset 1s ease" }}
                    />
                  </svg>
                  <span className="absolute text-3xl font-black font-headline text-slate-50">{eqPct}%</span>
                </div>
                <div className="mt-4 machined-chip px-3 py-1 rounded text-[10px] font-mono" style={{ borderColor: eqColor, color: eqColor }}>
                  {eqPct >= 90 ? "NOMINAL PARITY" : eqPct >= 70 ? "PARTIAL PARITY" : "DIVERGENCE DETECTED"}
                </div>
              </div>
              <div className="bg-surface-container-low rounded-xl p-6">
                <ScorecardGauge scorecard={result.scorecard} size={120} />
              </div>
            </aside>

            {/* Right: comparison table */}
            <section className="flex-1 min-w-0">
              <div className="bg-surface-container rounded-xl overflow-hidden shadow-2xl">
                <div className="px-8 py-5 bg-surface-container-high/50 flex justify-between items-center">
                  <h3 className="text-sm font-bold font-headline text-slate-100 uppercase tracking-wider">
                    Activity Comparison Ledger
                  </h3>
                  <div className="machined-chip border-primary px-3 py-1 rounded text-[10px] font-mono text-primary">
                    {result.comparisons.length} activities
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="bg-surface-container-lowest/30">
                        {["Activity", "Match", "ADF Output", "Databricks Output", "Diff"].map((h) => (
                          <th key={h} className="px-6 py-3 text-[10px] font-mono text-slate-500 uppercase tracking-widest">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.comparisons.map((row, i) => (
                        <tr key={i} className="border-t border-white/5 hover:bg-surface-container-low/30 transition-colors">
                          <td className="px-6 py-3 text-sm font-mono text-slate-200 font-medium">{row.activity_name}</td>
                          <td className="px-6 py-3">
                            <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                              row.match ? "bg-[#27e199]/10 text-[#27e199]" : "bg-[#ff5c5c]/10 text-[#ff5c5c]"
                            }`}>
                              {row.match ? "\u2713" : "\u2717"}
                            </span>
                          </td>
                          <td className="px-6 py-3 text-xs font-mono text-slate-400 max-w-[180px] truncate" title={row.adf_output || ""}>
                            {row.adf_output || "\u2014"}
                          </td>
                          <td className="px-6 py-3 text-xs font-mono text-slate-400 max-w-[180px] truncate" title={row.databricks_output || ""}>
                            {row.databricks_output || "\u2014"}
                          </td>
                          <td className="px-6 py-3 text-xs font-mono text-[#ff5c5c]">{row.diff || "\u2014"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </>
  );
}
