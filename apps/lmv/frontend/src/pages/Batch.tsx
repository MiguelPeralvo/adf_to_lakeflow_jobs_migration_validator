import React, { useState } from "react";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { MiniGauge } from "../components/ScorecardGauge";

interface BatchReport {
  total: number;
  threshold: number;
  mean_score: number;
  min_score: number;
  max_score: number;
  below_threshold: number;
  expression_mismatch_cases: number;
  ccs_distribution: Record<string, number>;
  cases: Array<{
    pipeline_name: string;
    score: number;
    label: string;
    ccs_below_threshold: boolean;
  }>;
}

function scoreColor(s: number): string {
  if (s >= 90) return "#27e199";
  if (s >= 70) return "#ffb547";
  return "#ff5c5c";
}

export function BatchPage() {
  const [goldenSetPath, setGoldenSetPath] = useState("golden_sets/pipelines.json");
  const [threshold, setThreshold] = useState(90);
  const [report, setReport] = useState<BatchReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setError(null);
    setReport(null);
    setLoading(true);
    try {
      const res = await fetch("/api/validate/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pipelines_path: goldenSetPath, threshold }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      setReport(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch validation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <TopHeader title="Regression Analysis" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-7xl">
        <div className="flex justify-between items-end">
          <div>
            <h2 className="text-3xl font-bold font-headline text-on-surface tracking-tight">
              Batch Regression Analysis
            </h2>
            <p className="text-slate-500 mt-1">
              Cross-validate migration pipelines against golden datasets.
            </p>
          </div>
          <button
            onClick={handleRun}
            disabled={loading}
            className="bg-gradient-to-br from-primary to-primary-container hover:opacity-90 active:scale-[0.98] transition-all text-on-primary-container px-6 py-2.5 rounded-lg font-headline font-bold flex items-center gap-2 shadow-lg shadow-primary/10"
          >
            <span className="material-symbols-outlined">play_arrow</span>
            {loading ? "Running..." : "Run Batch Validation"}
          </button>
        </div>

        {/* Config */}
        <div className="bg-surface-container rounded-xl p-6 border border-white/5 flex gap-6 items-end">
          <div className="flex-1">
            <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 font-mono">Golden Set Path</label>
            <input
              value={goldenSetPath}
              onChange={(e) => setGoldenSetPath(e.target.value)}
              className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 px-4 text-slate-100 font-mono text-sm outline-none focus:border-primary transition-all"
            />
          </div>
          <div className="w-32">
            <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 font-mono">Threshold</label>
            <input
              type="number"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 px-4 text-slate-100 font-mono text-sm outline-none focus:border-primary transition-all"
            />
          </div>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
        {loading && <div className="bg-surface-container rounded-xl p-8"><LoadingOverlay message="Scoring pipelines..." /></div>}

        {report && !loading && (
          <>
            {/* Metric cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-surface-container p-6 rounded-xl relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                  <span className="material-symbols-outlined text-6xl">account_tree</span>
                </div>
                <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">Total Pipelines</p>
                <span className="text-4xl font-headline font-bold text-on-surface tracking-tight mt-2 block">
                  {report.total}
                </span>
              </div>

              <div className="bg-surface-container p-6 rounded-xl flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">Mean CCS</p>
                  <span className="text-4xl font-headline font-bold text-on-surface tracking-tight">
                    {Math.round(report.mean_score)}
                  </span>
                </div>
                <MiniGauge value={report.mean_score} />
              </div>

              <div className="bg-surface-container p-6 rounded-xl border-l-4 border-[#ff5c5c]/50">
                <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">Min CCS</p>
                <span className="text-4xl font-headline font-bold tracking-tight mt-2 block" style={{ color: scoreColor(report.min_score) }}>
                  {Math.round(report.min_score)}
                </span>
              </div>

              <div className="bg-surface-container p-6 rounded-xl">
                <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">Regressions</p>
                <div className="mt-2 flex items-center gap-3">
                  <span className="text-4xl font-headline font-bold text-on-surface tracking-tight">
                    {report.below_threshold}
                  </span>
                  {report.below_threshold > 0 && (
                    <div className="px-2 py-1 bg-[#93000a]/30 text-[#ff5c5c] rounded text-[10px] font-bold border border-[#ff5c5c]/20 uppercase tracking-tighter">
                      Critical
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* CCS distribution */}
            {report.ccs_distribution && (
              <div className="bg-surface-container rounded-xl p-6 border border-white/5">
                <h3 className="text-sm font-headline font-semibold text-slate-300 uppercase tracking-wider mb-4">
                  CCS Distribution
                </h3>
                <div className="grid grid-cols-5 gap-3 text-center">
                  {[
                    { label: "P10", key: "p10" },
                    { label: "P25", key: "p25" },
                    { label: "Median", key: "median" },
                    { label: "P75", key: "p75" },
                    { label: "P90", key: "p90" },
                  ].map(({ label, key }) => {
                    const val = report.ccs_distribution[key] ?? 0;
                    return (
                      <div key={key} className="bg-surface-container-low rounded-lg p-3">
                        <p className="text-[10px] font-mono text-slate-500 uppercase">{label}</p>
                        <p className="text-xl font-headline font-bold mt-1" style={{ color: scoreColor(val) }}>
                          {Math.round(val)}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Pipeline table */}
            <div className="bg-surface-container rounded-xl overflow-hidden border border-white/5 shadow-xl">
              <div className="px-8 py-5 bg-surface-container-high/20 border-b border-white/5">
                <h3 className="text-sm font-headline font-semibold text-slate-100 uppercase tracking-wider">
                  Pipeline Results ({report.cases.length})
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-surface-container-lowest/30">
                      <th className="px-6 py-3 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Pipeline</th>
                      <th className="px-6 py-3 text-[10px] font-mono text-slate-500 uppercase tracking-widest">CCS</th>
                      <th className="px-6 py-3 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.cases.map((c, i) => (
                      <tr key={i} className="border-t border-white/5 hover:bg-surface-container-low/30 transition-colors">
                        <td className="px-6 py-3 text-sm font-mono text-slate-200">{c.pipeline_name}</td>
                        <td className="px-6 py-3">
                          <span className="text-sm font-mono font-bold" style={{ color: scoreColor(c.score) }}>
                            {Math.round(c.score)}
                          </span>
                        </td>
                        <td className="px-6 py-3">
                          {c.ccs_below_threshold ? (
                            <span className="px-2 py-1 bg-[#93000a]/30 text-[#ff5c5c] rounded text-[10px] font-bold border border-[#ff5c5c]/20 uppercase">
                              Regressed
                            </span>
                          ) : (
                            <span className="px-2 py-1 bg-[#27e199]/10 text-[#27e199] rounded text-[10px] font-bold border border-[#27e199]/20 uppercase">
                              Pass
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
