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
  const [runId, setRunId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    if (!pipelineName.trim()) return;
    setError(null); setResult(null); setRunId(""); setLoading(true);
    try {
      const params = JSON.parse(paramsJson);
      const newResult = await api.parallelRun(pipelineName.trim(), params);
      setResult(newResult);
      setRunId(`${Math.floor(Math.random() * 900 + 100)}-AX`);
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
        {/* Page Header */}
        <div className="mb-10">
          <h2 className="text-4xl font-extrabold text-slate-50 font-headline tracking-tight">Parallel Test</h2>
          <p className="text-slate-400 mt-2 text-lg">Simultaneously execute legacy ADF and target Databricks workflows to validate logic parity.</p>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Input Card */}
        <section className="bg-surface-container rounded-xl p-8 shadow-2xl shadow-blue-900/5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
              <label className="block text-xs font-bold text-primary tracking-widest uppercase mb-3 font-body">Pipeline Name</label>
              <input
                value={pipelineName}
                onChange={(e) => setPipelineName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleRun()}
                placeholder="DW_Sales_Ingestion_Monthly"
                className="w-full bg-surface-container-lowest border-none rounded-lg p-4 text-slate-200 font-mono focus:ring-2 focus:ring-primary/20 outline-none transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-primary tracking-widest uppercase mb-3 font-body">Parameters (JSON)</label>
              <textarea
                value={paramsJson}
                onChange={(e) => setParamsJson(e.target.value)}
                rows={1}
                className="w-full bg-surface-container-lowest border-none rounded-lg p-4 text-slate-200 font-mono focus:ring-2 focus:ring-primary/20 outline-none resize-none transition-all"
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
            {/* Left Column: Gauges */}
            <aside className="w-full lg:w-[280px] flex flex-col gap-6">
              {/* Equivalence Gauge */}
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

              {/* CCS Scorecard */}
              <div className="bg-surface-container-low rounded-xl p-6">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-6 block">CCS Scorecard</span>
                <div className="space-y-5">
                  {Object.entries(result.scorecard.dimensions).slice(0, 3).map(([name, dim]) => {
                    const pct = Math.round(dim.score * 100);
                    const barColor = dim.passed ? "bg-tertiary" : "bg-primary";
                    return (
                      <div key={name}>
                        <div className="flex justify-between items-end">
                          <span className="text-xs text-slate-400 font-body">{name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                          <span className="text-xs font-mono text-slate-50">{pct}%</span>
                        </div>
                        <div className="mt-1 h-1.5 w-full bg-surface-container-highest rounded-full overflow-hidden">
                          <div className={`h-full ${barColor}`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </aside>

            {/* Right Column: Comparison Table */}
            <section className="flex-1 min-w-0">
              <div className="bg-surface-container rounded-xl overflow-hidden shadow-2xl">
                {/* Table Header with machined-chip badges */}
                <div className="px-8 py-5 bg-surface-container-high/50 flex justify-between items-center">
                  <h3 className="text-sm font-bold font-headline text-slate-100 uppercase tracking-wider">
                    Activity Comparison Ledger
                  </h3>
                  <div className="flex gap-2">
                    <div className="machined-chip border-primary px-3 py-1 rounded text-[10px] font-mono text-primary">
                      RUN_ID: {runId}
                    </div>
                    <div className="machined-chip border-slate-500 px-3 py-1 rounded text-[10px] font-mono text-slate-400">
                      {result.comparisons.length} activities
                    </div>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-surface-container-lowest/30">
                        <th className="px-8 py-4 text-[10px] font-bold text-slate-500 uppercase tracking-widest border-b border-white/5">Activity</th>
                        <th className="px-4 py-4 text-[10px] font-bold text-slate-500 uppercase tracking-widest border-b border-white/5 text-center">Match</th>
                        <th className="px-6 py-4 text-[10px] font-bold text-slate-500 uppercase tracking-widest border-b border-white/5">ADF Output (Legacy)</th>
                        <th className="px-6 py-4 text-[10px] font-bold text-slate-500 uppercase tracking-widest border-b border-white/5">Databricks Output</th>
                        <th className="px-8 py-4 text-[10px] font-bold text-slate-500 uppercase tracking-widest border-b border-white/5 text-right">Diff</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 font-mono text-xs">
                      {result.comparisons.map((row, i) => (
                        <tr
                          key={i}
                          className={`hover:bg-white/5 transition-colors group ${!row.match ? "bg-error/5" : ""}`}
                        >
                          <td className="px-8 py-6 font-semibold text-slate-200">{row.activity_name}</td>
                          <td className="px-4 py-6 text-center">
                            <span
                              className={`material-symbols-outlined ${row.match ? "text-tertiary" : "text-error"}`}
                              style={{ fontVariationSettings: "'FILL' 1" }}
                            >
                              {row.match ? "check_circle" : "error"}
                            </span>
                          </td>
                          <td className="px-6 py-6 text-slate-400">{row.adf_output || "\u2014"}</td>
                          <td className={`px-6 py-6 ${!row.match ? "text-error font-bold" : "text-slate-400"}`}>
                            {row.databricks_output || "\u2014"}
                          </td>
                          <td className={`px-8 py-6 text-right ${!row.match ? "text-error font-bold" : "text-slate-500"}`}>
                            {row.diff || "0.00%"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {/* Table Footer */}
                <div className="p-6 bg-surface-container-lowest/50 border-t border-white/5 flex justify-between items-center">
                  <p className="text-[10px] text-slate-500 font-body italic">
                    {result.comparisons.filter(r => !r.match).length > 0
                      ? `Note: ${result.comparisons.filter(r => !r.match).length} mismatch(es) detected in comparison.`
                      : "All activities match between ADF and Databricks outputs."}
                  </p>
                  <button className="text-primary text-[10px] font-bold uppercase tracking-widest hover:underline transition-all">
                    Download Full Trace
                  </button>
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </>
  );
}
