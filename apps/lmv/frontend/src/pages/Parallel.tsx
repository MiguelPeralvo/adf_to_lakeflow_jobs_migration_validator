import React, { useState, useEffect } from "react";
import { api } from "../api";
import type { ParallelResult, ComparisonRow } from "../types";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";
import { PastRunsPanel } from "../components/PastRunsPanel";

function eqColor(pct: number): string {
  if (pct >= 90) return "#27e199";
  if (pct >= 70) return "#ffb547";
  return "#ff5c5c";
}

export function ParallelPage({ entityId }: { entityId?: string | null }) {
  const [pipelineName, setPipelineName] = useState("");
  const [paramsJson, setParamsJson] = useState('{ "env": "dev" }');
  const [result, setResult] = useState<ParallelResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentEntityId, setCurrentEntityId] = useState<string | null>(entityId ?? null);

  // Load entity from URL
  useEffect(() => {
    if (!entityId) return;
    setLoading(true);
    api.getEntity(entityId)
      .then((data) => {
        const results = (data.results as Record<string, unknown>) || data;
        setResult(results as unknown as ParallelResult);
        setPipelineName((results.pipeline_name as string) || (data.pipeline_name as string) || "");
        setCurrentEntityId(entityId);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load entity"))
      .finally(() => setLoading(false));
  }, [entityId]);

  async function handleRun() {
    if (!pipelineName.trim()) return;
    setError(null); setResult(null); setLoading(true);
    try {
      const params = JSON.parse(paramsJson);
      const res = await api.parallelRun(pipelineName.trim(), params);
      setResult(res);
      if (res.entity_id) {
        setCurrentEntityId(res.entity_id);
        window.history.replaceState(null, "", `#/parallel/${res.entity_id}`);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Parallel run failed"); }
    finally { setLoading(false); }
  }

  function handlePastRunSelect(eid: string) {
    window.location.hash = `#/parallel/${eid}`;
  }

  const eqPct = result ? Math.round(result.equivalence_score * 100) : 0;
  const matchCount = result ? result.comparisons.filter(r => r.match).length : 0;
  const mismatchCount = result ? result.comparisons.filter(r => !r.match).length : 0;

  return (
    <>
      <TopHeader title="Parallel Testing" />
      <div className="pt-24 pb-16 px-10 max-w-7xl space-y-8" style={{ animation: "fade-in-up 0.4s ease both" }}>

        {/* Header */}
        <section className="flex justify-between items-end">
          <div>
            <h2 className="text-4xl font-bold font-headline text-on-surface tracking-tight">Parallel Testing</h2>
            <p className="text-slate-500 font-body mt-2">
              Execute ADF and Databricks workflows simultaneously with the same parameters, then compare outputs activity-by-activity.
            </p>
          </div>
          {result && (
            <div className="flex items-center gap-2 shrink-0">
              <span className="machined-chip px-2.5 py-1 rounded text-[9px] font-mono"
                style={{ borderColor: eqColor(eqPct), color: eqColor(eqPct) }}>
                {eqPct >= 90 ? "PARITY" : eqPct >= 70 ? "PARTIAL" : "DIVERGENT"}
              </span>
              <span className="machined-chip border-outline-variant/30 text-outline px-2.5 py-1 rounded text-[9px] font-mono">
                {result.comparisons.length} activities
              </span>
            </div>
          )}
        </section>

        {/* Past runs panel */}
        <PastRunsPanel type="parallel" onSelect={handlePastRunSelect} currentEntityId={currentEntityId} />

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Input: pipeline name + parameters */}
        <div className="grid grid-cols-12 gap-6">
          {/* Pipeline name */}
          <div className="col-span-5">
            <div className="bg-surface-container rounded-xl border border-outline-variant/10 overflow-hidden">
              <div className="px-5 py-2.5 bg-surface-container-high/40 border-b border-outline-variant/5">
                <span className="font-mono text-[10px] text-slate-400 uppercase tracking-widest">Pipeline Name</span>
              </div>
              <div className="p-4">
                <input value={pipelineName} onChange={e => setPipelineName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleRun()}
                  placeholder="DW_Sales_Ingestion_Monthly"
                  className="w-full bg-surface-container-lowest border-none rounded-lg py-2.5 px-4 text-on-surface font-mono text-sm outline-none focus:ring-1 focus:ring-primary" />
              </div>
            </div>
          </div>

          {/* Parameters */}
          <div className="col-span-5">
            <div className="bg-[#060a13] rounded-xl border border-outline-variant/10 overflow-hidden">
              <div className="px-5 py-2.5 bg-surface-container/30 border-b border-outline-variant/5 flex justify-between items-center">
                <span className="font-mono text-[10px] text-slate-400 uppercase tracking-widest">Parameters (JSON)</span>
                <div className="flex gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-red-500/20 border border-red-500/40" />
                  <div className="w-2 h-2 rounded-full bg-yellow-500/20 border border-yellow-500/40" />
                  <div className="w-2 h-2 rounded-full bg-green-500/20 border border-green-500/40" />
                </div>
              </div>
              <textarea value={paramsJson} onChange={e => setParamsJson(e.target.value)} spellCheck={false} rows={2}
                className="w-full bg-transparent px-5 py-3 text-primary font-mono text-xs leading-relaxed resize-none outline-none placeholder:text-slate-700" />
            </div>
          </div>

          {/* Run button */}
          <div className="col-span-2 flex items-end">
            <button onClick={handleRun} disabled={loading || !pipelineName.trim()}
              className={`w-full py-[52px] rounded-xl font-bold text-sm flex flex-col items-center justify-center gap-1 transition-all ${
                loading ? "bg-primary/30 text-slate-500 cursor-wait"
                        : "bg-gradient-to-br from-primary to-primary-container text-on-primary-container hover:scale-[0.98] shadow-lg shadow-blue-900/20"
              }`}>
              <span className="material-symbols-outlined text-lg">compare_arrows</span>
              <span className="text-xs">{loading ? "Running..." : "Run Test"}</span>
            </button>
          </div>
        </div>

        {loading && (
          <div className="bg-surface-container rounded-xl p-12 flex flex-col items-center gap-4">
            <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-sm font-mono text-outline">Executing on ADF + Databricks...</span>
          </div>
        )}

        {result && !loading && (
          <div className="space-y-6" style={{ animation: "fade-in-up 0.3s ease both" }}>
            {/* Summary row: equivalence + CCS dimensions */}
            <div className="grid grid-cols-12 gap-5">
              {/* Equivalence gauge */}
              <div className="col-span-3 bg-surface-container rounded-xl p-5 border border-outline-variant/10 flex flex-col items-center relative overflow-hidden">
                <div className="absolute inset-0 blur-[80px] pointer-events-none" style={{ backgroundColor: `${eqColor(eqPct)}06` }} />
                <span className="text-[9px] font-mono text-outline uppercase tracking-widest mb-3">Logic Equivalence</span>
                <div className="relative w-24 h-24 flex items-center justify-center">
                  <svg className="w-full h-full -rotate-90">
                    <circle className="text-surface-container-highest" cx="48" cy="48" r="42" fill="transparent" stroke="currentColor" strokeWidth={5} />
                    <circle cx="48" cy="48" r="42" fill="transparent" stroke={eqColor(eqPct)} strokeWidth={5} strokeLinecap="round"
                      strokeDasharray={263.9} strokeDashoffset={263.9 - (eqPct / 100) * 263.9}
                      style={{ transition: "stroke-dashoffset 1s ease" }} />
                  </svg>
                  <span className="absolute text-2xl font-headline font-bold text-on-surface">{eqPct}%</span>
                </div>
                <div className="flex gap-4 mt-3 text-[10px] font-mono">
                  <span className="text-tertiary">{matchCount} match</span>
                  {mismatchCount > 0 && <span className="text-error">{mismatchCount} diff</span>}
                </div>
              </div>

              {/* CCS dimensions */}
              {Object.entries(result.scorecard.dimensions).slice(0, 6).map(([name, dim]) => {
                const pct = Math.round(dim.score * 100);
                return (
                  <div key={name} className={`col-span-1-half bg-surface-container rounded-xl p-3 border ${dim.passed ? "border-outline-variant/10" : "border-error/20"}`}
                    style={{ gridColumn: "span 1.5" /* fallback below */ }}>
                    <p className="text-[8px] font-mono text-outline uppercase truncate mb-1">{name.replace(/_/g, " ")}</p>
                    <p className={`text-lg font-headline font-bold ${dim.passed ? "text-on-surface" : "text-error"}`}>{pct}%</p>
                    <div className="mt-1.5 h-0.5 bg-surface-container-highest rounded-full overflow-hidden">
                      <div className={`h-full ${dim.passed ? "bg-tertiary" : "bg-error"}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Comparison table */}
            <div className="bg-surface-container rounded-xl overflow-hidden border border-outline-variant/10 shadow-xl">
              <div className="px-5 py-3 bg-surface-container-high/30 border-b border-outline-variant/5 flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <span className="material-symbols-outlined text-primary text-sm">compare_arrows</span>
                  <span className="text-sm font-headline font-semibold text-on-surface">Activity Comparison</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="machined-chip border-outline-variant/30 text-outline px-2 py-0.5 rounded text-[9px] font-mono">
                    {result.comparisons.length} activities
                  </span>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead className="text-[9px] font-mono text-outline uppercase tracking-wider bg-surface-container-low/30">
                    <tr>
                      <th className="px-5 py-3 w-10"></th>
                      <th className="px-3 py-3">Activity</th>
                      <th className="px-3 py-3">ADF Output</th>
                      <th className="px-3 py-3">Databricks Output</th>
                      <th className="px-3 py-3 text-right w-20">Diff</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/5">
                    {result.comparisons.map((row: ComparisonRow, i: number) => (
                      <tr key={i} className={`transition-colors ${!row.match ? "bg-error/4 hover:bg-error/8" : "hover:bg-surface-container-low/30"}`}>
                        <td className="px-5 py-3 text-center">
                          <span className={`material-symbols-outlined text-sm ${row.match ? "text-tertiary" : "text-error"}`}
                            style={{ fontVariationSettings: "'FILL' 1" }}>
                            {row.match ? "check_circle" : "cancel"}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-xs font-mono text-on-surface font-medium">{row.activity_name}</td>
                        <td className="px-3 py-3 text-xs font-mono text-outline">{row.adf_output || "\u2014"}</td>
                        <td className={`px-3 py-3 text-xs font-mono ${!row.match ? "text-error font-semibold" : "text-outline"}`}>
                          {row.databricks_output || "\u2014"}
                        </td>
                        <td className={`px-3 py-3 text-xs font-mono text-right ${!row.match ? "text-error" : "text-outline"}`}>
                          {row.diff || "\u2014"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="px-5 py-3 bg-surface-container-lowest/30 border-t border-outline-variant/5 flex justify-between items-center">
                <p className="text-[10px] text-outline font-body">
                  {mismatchCount > 0
                    ? <><span className="text-error font-semibold">{mismatchCount}</span> mismatch{mismatchCount > 1 ? "es" : ""} detected</>
                    : <span className="text-tertiary">All activities match</span>}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
