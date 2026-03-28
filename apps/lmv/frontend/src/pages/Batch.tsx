import React, { useState } from "react";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingOverlay } from "../components/LoadingOverlay";

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
  if (s >= 70) return "#adc6ff";
  return "#ffb4ab";
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

  // Compute distribution bands from cases
  function getDistribution(report: BatchReport) {
    const high = report.cases.filter(c => c.score >= 90).length;
    const mid = report.cases.filter(c => c.score >= 70 && c.score < 90).length;
    const low = report.cases.filter(c => c.score < 70).length;
    return { high, mid, low };
  }

  return (
    <>
      <TopHeader title="Regression Analysis" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-7xl">
        {/* Page Header */}
        <div className="flex justify-between items-end">
          <div>
            <h2 className="text-3xl font-headline font-bold text-on-surface tracking-tight">
              Batch Regression Analysis
            </h2>
            <p className="text-outline mt-1 font-body">
              Global cross-validation of migration endpoints against golden datasets.
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
            {/* Summary Banner (Metric Cards) */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {/* Total Pipelines */}
              <div className="bg-surface-container p-6 rounded-xl relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                  <span className="material-symbols-outlined text-6xl">account_tree</span>
                </div>
                <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">Total Pipelines</p>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-4xl font-headline font-bold text-on-surface tracking-tight">
                    {report.total}
                  </span>
                </div>
              </div>

              {/* Mean CCS with Radial Gauge */}
              <div className="bg-surface-container p-6 rounded-xl flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">Mean CCS</p>
                  <span className="text-4xl font-headline font-bold text-on-surface tracking-tight">
                    {Math.round(report.mean_score)}%
                  </span>
                </div>
                <div className="relative w-16 h-16">
                  <svg className="w-full h-full transform -rotate-90">
                    <circle className="text-surface-container-highest" cx="32" cy="32" r="28" fill="transparent" stroke="currentColor" strokeWidth={4} />
                    <circle
                      cx="32" cy="32" r="28" fill="transparent"
                      stroke="#adc6ff" strokeWidth={4}
                      strokeDasharray={175.9}
                      strokeDashoffset={175.9 - (report.mean_score / 100) * 175.9}
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="material-symbols-outlined text-primary text-xl">speed</span>
                  </div>
                </div>
              </div>

              {/* Min CCS */}
              <div className="bg-surface-container p-6 rounded-xl border-l-4 border-error/50">
                <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">Min CCS</p>
                <div className="mt-2">
                  <span className="text-4xl font-headline font-bold tracking-tight" style={{ color: scoreColor(report.min_score) }}>
                    {Math.round(report.min_score)}
                  </span>
                  {report.cases.length > 0 && (
                    <p className="text-xs text-slate-500 mt-1 font-mono">
                      ID: {report.cases.reduce((min, c) => c.score < min.score ? c : min, report.cases[0]).pipeline_name.substring(0, 16)}
                    </p>
                  )}
                </div>
              </div>

              {/* Regression Count */}
              <div className="bg-surface-container p-6 rounded-xl">
                <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">Regressions</p>
                <div className="mt-2 flex items-center gap-3">
                  <span className="text-4xl font-headline font-bold text-on-surface tracking-tight">
                    {report.below_threshold}
                  </span>
                  {report.below_threshold > 0 && (
                    <div className="px-2 py-1 bg-error-container/30 text-error rounded text-[10px] font-bold border border-error/20 uppercase tracking-tighter">
                      Critical
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Data Integrity Distribution */}
            {report.cases.length > 0 && (() => {
              const dist = getDistribution(report);
              const total = report.cases.length;
              return (
                <div className="bg-surface-container rounded-xl p-8">
                  <div className="flex justify-between items-center mb-8">
                    <div>
                      <h3 className="text-lg font-headline font-semibold text-on-surface">Data Integrity Distribution</h3>
                      <p className="text-sm text-slate-500">Cluster density across Consensus Confidence Score (CCS) bands.</p>
                    </div>
                    <div className="flex gap-4">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-tertiary" />
                        <span className="text-xs text-slate-500 font-mono">High (90-100)</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-primary" />
                        <span className="text-xs text-slate-500 font-mono">Stable (70-89)</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-error" />
                        <span className="text-xs text-slate-500 font-mono">Alert (&lt; 70)</span>
                      </div>
                    </div>
                  </div>
                  <div className="space-y-6">
                    {/* High Band */}
                    <div className="space-y-2">
                      <div className="flex justify-between items-end text-xs font-mono text-slate-500">
                        <span>SCORE: 90-100</span>
                        <span className="text-tertiary font-bold">{dist.high} PIPELINES</span>
                      </div>
                      <div className="h-10 bg-surface-container-lowest rounded overflow-hidden">
                        <div
                          className="h-full bg-tertiary/80 transition-all duration-1000"
                          style={{ width: `${total ? (dist.high / total) * 100 : 0}%`, boxShadow: "0 0 15px rgba(39,225,153,0.2)" }}
                        />
                      </div>
                    </div>
                    {/* Mid Band */}
                    <div className="space-y-2">
                      <div className="flex justify-between items-end text-xs font-mono text-slate-500">
                        <span>SCORE: 70-89</span>
                        <span className="text-primary font-bold">{dist.mid} PIPELINES</span>
                      </div>
                      <div className="h-10 bg-surface-container-lowest rounded overflow-hidden">
                        <div
                          className="h-full bg-primary/80 transition-all duration-1000"
                          style={{ width: `${total ? (dist.mid / total) * 100 : 0}%`, boxShadow: "0 0 15px rgba(173,198,255,0.2)" }}
                        />
                      </div>
                    </div>
                    {/* Low Band */}
                    <div className="space-y-2">
                      <div className="flex justify-between items-end text-xs font-mono text-slate-500">
                        <span>SCORE: &lt; 70</span>
                        <span className="text-error font-bold">{dist.low} PIPELINES</span>
                      </div>
                      <div className="h-10 bg-surface-container-lowest rounded overflow-hidden">
                        <div
                          className="h-full bg-error/80 transition-all duration-1000"
                          style={{ width: `${total ? (dist.low / total) * 100 : 0}%`, boxShadow: "0 0 15px rgba(255,180,171,0.2)" }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Golden Set Validation Records Table */}
            <div className="bg-surface-container rounded-xl overflow-hidden flex flex-col">
              <div className="p-6 border-b border-outline-variant/15 flex justify-between items-center bg-surface-container-high/30">
                <h3 className="text-lg font-headline font-semibold text-on-surface">Golden Set Validation Records</h3>
                <div className="flex gap-2">
                  <button className="bg-surface-container-lowest border border-outline-variant/30 text-xs px-3 py-1.5 rounded-lg hover:bg-surface-bright transition-colors flex items-center gap-2">
                    <span className="material-symbols-outlined text-sm">filter_list</span> Filter
                  </button>
                  <button className="bg-surface-container-lowest border border-outline-variant/30 text-xs px-3 py-1.5 rounded-lg hover:bg-surface-bright transition-colors flex items-center gap-2">
                    <span className="material-symbols-outlined text-sm">download</span> Export
                  </button>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="text-xs uppercase tracking-widest text-slate-500 font-mono bg-surface-container-low/50">
                      <th className="px-6 py-4 font-medium">Pipeline Name</th>
                      <th className="px-6 py-4 font-medium text-right">Current CCS</th>
                      <th className="px-6 py-4 font-medium text-right">Threshold</th>
                      <th className="px-6 py-4 font-medium text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/5">
                    {report.cases.map((c, i) => {
                      const color = scoreColor(c.score);
                      return (
                        <tr key={i} className="group hover:bg-surface-container-low transition-colors">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <span className="material-symbols-outlined text-slate-500 group-hover:text-primary transition-colors">database</span>
                              <span className="text-sm font-medium text-on-surface">{c.pipeline_name}</span>
                            </div>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <span className="font-mono font-bold" style={{ color }}>{Math.round(c.score)}</span>
                          </td>
                          <td className="px-6 py-4 text-right text-slate-500">
                            <span className="font-mono">{threshold}</span>
                          </td>
                          <td className="px-6 py-4 text-center">
                            {c.ccs_below_threshold ? (
                              <span className="machined-chip border-error/50 text-error px-3 py-1 text-[10px] font-bold uppercase tracking-widest rounded-r">REGRESSED</span>
                            ) : (
                              <span className="machined-chip border-tertiary/50 text-tertiary px-3 py-1 text-[10px] font-bold uppercase tracking-widest rounded-r">PASS</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="p-4 bg-surface-container-lowest/50 border-t border-outline-variant/10 flex justify-between items-center text-xs text-slate-500">
                <span className="font-mono">Showing {report.cases.length} of {report.total} validation instances</span>
                <div className="flex items-center gap-4">
                  <button className="hover:text-primary transition-colors">
                    <span className="material-symbols-outlined text-sm">chevron_left</span> Previous
                  </button>
                  <span className="text-on-surface font-bold">1 / {Math.ceil(report.total / 5)}</span>
                  <button className="hover:text-primary transition-colors">
                    Next <span className="material-symbols-outlined text-sm">chevron_right</span>
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
