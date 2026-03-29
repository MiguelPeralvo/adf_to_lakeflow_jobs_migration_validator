import React, { useState, useEffect } from "react";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";
import { setPendingBatchFolder, navigateToEntity, TYPE_TO_PAGE } from "../store";

interface ActivityEntry {
  type: "validation" | "batch_validation" | "synthetic_generation" | "expression" | "harness" | "parallel";
  timestamp: string;
  entity_id?: string;
  // validation
  pipeline_name?: string;
  scorecard?: { score: number; label: string; dimensions: Record<string, { score: number; passed: boolean }> };
  // batch_validation
  folder?: string;
  total?: number;
  mean_score?: number;
  below_threshold?: number;
  threshold?: number;
  // synthetic_generation
  output_path?: string;
  count?: number;
  mode?: string;
  // expression
  adf_expression?: string;
  python_code?: string;
  score?: number;
  // harness
  iterations?: number;
  // parallel
  equivalence_score?: number;
}

interface SyntheticRun {
  path: string;
  name: string;
  pipeline_count: number;
  subfolder_count: number;
  has_suite: boolean;
}

function scoreColor(s: number): string {
  if (s >= 90) return "#27e199";
  if (s >= 70) return "#adc6ff";
  return "#ffb4ab";
}

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function HistoryPage({ entityId: _entityId }: { entityId?: string | null }) {
  const [activityLog, setActivityLog] = useState<ActivityEntry[]>([]);
  const [syntheticRuns, setSyntheticRuns] = useState<SyntheticRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [tab, setTab] = useState<"activity" | "synthetic_runs">("activity");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch("/api/history").then(r => r.json()).catch(() => []),
      fetch("/api/synthetic/runs").then(r => r.json()).catch(() => []),
    ]).then(([log, runs]) => {
      setActivityLog(log);
      setSyntheticRuns(runs);
    }).finally(() => setLoading(false));
  }, []);

  const typeIcon: Record<string, string> = {
    validation: "rule",
    batch_validation: "monitoring",
    synthetic_generation: "science",
    expression: "gavel",
    harness: "settings_input_component",
    parallel: "account_tree",
  };
  const typeLabel: Record<string, string> = {
    validation: "Validation",
    batch_validation: "Batch Validation",
    synthetic_generation: "Synthetic Generation",
    expression: "Expression",
    harness: "E2E Harness",
    parallel: "Parallel Test",
  };
  const typeColor: Record<string, string> = {
    validation: "text-primary",
    batch_validation: "text-on-surface",
    synthetic_generation: "text-tertiary",
    expression: "text-[#ffb547]",
    harness: "text-primary",
    parallel: "text-primary",
  };

  function viewEntity(entry: ActivityEntry) {
    if (!entry.entity_id) return;
    const page = TYPE_TO_PAGE[entry.type];
    if (page) navigateToEntity(page, entry.entity_id);
  }

  return (
    <>
      <TopHeader title="History" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-6xl">
        <section>
          <h2 className="text-4xl font-bold font-headline text-on-surface tracking-tight">Activity History</h2>
          <p className="text-slate-500 font-body mt-2">
            Timeline of validations, batch runs, and synthetic generation sessions. Click any entry to view full results.
          </p>
        </section>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Tab bar */}
        <div className="flex gap-8 border-b border-outline-variant/20">
          <button onClick={() => setTab("activity")}
            className={`pb-3 text-sm font-semibold transition-colors ${tab === "activity" ? "text-primary border-b-2 border-primary" : "text-outline hover:text-on-surface"}`}>
            Activity Log ({activityLog.length})
          </button>
          <button onClick={() => setTab("synthetic_runs")}
            className={`pb-3 text-sm font-semibold transition-colors ${tab === "synthetic_runs" ? "text-primary border-b-2 border-primary" : "text-outline hover:text-on-surface"}`}>
            Synthetic Runs ({syntheticRuns.length})
          </button>
        </div>

        {loading && (
          <div className="bg-surface-container rounded-xl p-12 flex flex-col items-center gap-4">
            <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-sm font-mono text-outline">Loading history...</span>
          </div>
        )}

        {/* Activity Log tab */}
        {!loading && tab === "activity" && (
          activityLog.length === 0 ? (
            <div className="bg-surface-container rounded-xl p-12 text-center">
              <span className="material-symbols-outlined text-4xl text-slate-700 mb-4 block">history</span>
              <p className="text-sm font-mono text-slate-600">No activity yet. Run a validation or generate synthetic pipelines to see history.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {activityLog.map((entry, i) => {
                const isOpen = expandedIdx === i;
                const icon = typeIcon[entry.type] || "help";
                const label = typeLabel[entry.type] || entry.type;
                const color = typeColor[entry.type] || "text-outline";
                const hasEntity = !!entry.entity_id;

                return (
                  <div key={i} className="bg-surface-container rounded-xl border border-outline-variant/10 overflow-hidden">
                    <div onClick={() => setExpandedIdx(isOpen ? null : i)}
                      className="px-5 py-3 flex items-center gap-4 cursor-pointer hover:bg-surface-container-high/30 transition-colors">
                      <span className={`material-symbols-outlined text-lg ${color}`}>{icon}</span>

                      <div className="flex-1 min-w-0">
                        {entry.type === "validation" && (
                          <p className="text-sm text-on-surface">
                            <span className="font-mono font-medium">{entry.pipeline_name}</span>
                            {entry.scorecard && (
                              <span className="ml-2 font-mono font-bold" style={{ color: scoreColor(entry.scorecard.score) }}>
                                {Math.round(entry.scorecard.score)}%
                              </span>
                            )}
                          </p>
                        )}
                        {entry.type === "batch_validation" && (
                          <p className="text-sm text-on-surface">
                            <span className="font-medium">{entry.total} pipelines</span>
                            <span className="text-outline mx-2">—</span>
                            <span className="font-mono" style={{ color: scoreColor(entry.mean_score || 0) }}>mean {Math.round(entry.mean_score || 0)}%</span>
                            {(entry.below_threshold ?? 0) > 0 && (
                              <span className="text-error ml-2">({entry.below_threshold} below {entry.threshold})</span>
                            )}
                          </p>
                        )}
                        {entry.type === "synthetic_generation" && (
                          <p className="text-sm text-on-surface">
                            <span className="font-medium">{entry.count} pipelines</span>
                            <span className="text-outline mx-2">—</span>
                            <span className="text-outline">{entry.mode} mode</span>
                          </p>
                        )}
                        {entry.type === "expression" && (
                          <p className="text-sm text-on-surface">
                            <span className="font-mono font-medium truncate">{entry.adf_expression?.slice(0, 50)}</span>
                            {entry.score != null && (
                              <span className="ml-2 font-mono font-bold" style={{ color: scoreColor(entry.score * 100) }}>
                                {Math.round(entry.score * 100)}%
                              </span>
                            )}
                          </p>
                        )}
                        {entry.type === "harness" && (
                          <p className="text-sm text-on-surface">
                            <span className="font-mono font-medium">{entry.pipeline_name}</span>
                            <span className="text-outline ml-2">— {entry.iterations} iterations</span>
                          </p>
                        )}
                        {entry.type === "parallel" && (
                          <p className="text-sm text-on-surface">
                            <span className="font-mono font-medium">{entry.pipeline_name}</span>
                            {entry.equivalence_score != null && (
                              <span className="ml-2 font-mono font-bold" style={{ color: scoreColor(entry.equivalence_score * 100) }}>
                                {Math.round(entry.equivalence_score * 100)}% equiv
                              </span>
                            )}
                          </p>
                        )}
                      </div>

                      {hasEntity && (
                        <button onClick={(e) => { e.stopPropagation(); viewEntity(entry); }}
                          className="px-3 py-1 rounded-lg bg-primary/10 text-primary text-[10px] font-mono font-bold hover:bg-primary/20 border border-primary/20 flex items-center gap-1 shrink-0">
                          <span className="material-symbols-outlined text-[12px]">open_in_new</span>
                          View
                        </button>
                      )}

                      <span className="machined-chip px-2 py-0.5 rounded text-[9px] font-mono border-outline-variant/30 text-outline">{label}</span>
                      <span className="text-[10px] font-mono text-outline w-16 text-right shrink-0">{relativeTime(entry.timestamp)}</span>
                      <span className={`material-symbols-outlined text-sm text-outline transition-transform ${isOpen ? "rotate-180" : ""}`}>expand_more</span>
                    </div>

                    {isOpen && (
                      <div className="px-5 pb-4 pt-1 border-t border-outline-variant/5 space-y-3">
                        <div className="flex items-center gap-3">
                          <span className="text-[10px] font-mono text-outline">
                            {new Date(entry.timestamp).toLocaleString()}
                          </span>
                          {entry.entity_id && (
                            <span className="text-[9px] font-mono text-outline/50">
                              ID: {entry.entity_id.slice(0, 8)}
                            </span>
                          )}
                        </div>

                        {entry.type === "validation" && entry.scorecard && (
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                            {Object.entries(entry.scorecard.dimensions).map(([dim, d]) => (
                              <div key={dim} className={`rounded-lg p-2.5 border ${d.passed ? "border-outline-variant/10 bg-surface-container-high/30" : "border-error/20 bg-error/5"}`}>
                                <p className="text-[9px] font-mono text-outline uppercase truncate">{dim.replace(/_/g, " ")}</p>
                                <p className={`text-sm font-mono font-bold ${d.passed ? "text-tertiary" : "text-error"}`}>{(d.score * 100).toFixed(0)}%</p>
                              </div>
                            ))}
                          </div>
                        )}

                        {entry.type === "batch_validation" && entry.folder && (
                          <div className="flex items-center gap-3">
                            <span className="material-symbols-outlined text-sm text-outline">folder</span>
                            <span className="text-xs font-mono text-on-surface truncate">{entry.folder}</span>
                            <button onClick={(e) => { e.stopPropagation(); setPendingBatchFolder(entry.folder!); window.location.hash = "#/batch"; }}
                              className="ml-auto px-3 py-1 rounded-lg bg-primary/10 text-primary text-[10px] font-mono font-bold hover:bg-primary/20 border border-primary/20">
                              Re-run
                            </button>
                          </div>
                        )}

                        {entry.type === "synthetic_generation" && entry.output_path && (
                          <div className="flex items-center gap-3">
                            <span className="material-symbols-outlined text-sm text-outline">folder</span>
                            <span className="text-xs font-mono text-on-surface truncate">{entry.output_path}</span>
                            <button onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(entry.output_path!); }}
                              className="ml-auto px-3 py-1 rounded-lg bg-surface-container-high text-[10px] font-mono text-primary hover:bg-surface-container-highest border border-outline-variant/10">
                              Copy path
                            </button>
                            <button onClick={(e) => { e.stopPropagation(); setPendingBatchFolder(entry.output_path!); window.location.hash = "#/batch"; }}
                              className="px-3 py-1 rounded-lg bg-primary/10 text-primary text-[10px] font-mono font-bold hover:bg-primary/20 border border-primary/20">
                              Validate
                            </button>
                          </div>
                        )}

                        {/* View full results button for all types */}
                        {hasEntity && (
                          <button onClick={() => viewEntity(entry)}
                            className="text-xs font-mono text-primary hover:text-primary-fixed flex items-center gap-1.5">
                            <span className="material-symbols-outlined text-sm">arrow_forward</span>
                            View full results
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )
        )}

        {/* Synthetic Runs tab */}
        {!loading && tab === "synthetic_runs" && (
          syntheticRuns.length === 0 ? (
            <div className="bg-surface-container rounded-xl p-12 text-center">
              <span className="material-symbols-outlined text-4xl text-slate-700 mb-4 block">science</span>
              <p className="text-sm font-mono text-slate-600">No synthetic runs found. Generate pipelines from the Synthetic page.</p>
            </div>
          ) : (
            <div className="bg-surface-container rounded-xl overflow-hidden border border-outline-variant/10">
              <table className="w-full text-left">
                <thead className="bg-surface-container-high text-[9px] font-mono text-outline uppercase tracking-wider">
                  <tr>
                    <th className="px-6 py-3">Run</th>
                    <th className="px-6 py-3 text-right">Pipelines</th>
                    <th className="px-6 py-3 text-right">Subfolders</th>
                    <th className="px-6 py-3 text-center">Suite</th>
                    <th className="px-6 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {syntheticRuns.map((run, i) => (
                    <tr key={i} className="border-t border-outline-variant/5 hover:bg-surface-container-low/30 transition-colors">
                      <td className="px-6 py-3">
                        <p className="text-sm font-mono text-on-surface">{run.name}</p>
                        <p className="text-[10px] font-mono text-outline truncate max-w-md">{run.path}</p>
                      </td>
                      <td className="px-6 py-3 text-right text-sm font-mono text-on-surface">{run.pipeline_count}</td>
                      <td className="px-6 py-3 text-right text-sm font-mono text-outline">{run.subfolder_count}</td>
                      <td className="px-6 py-3 text-center">
                        {run.has_suite ? (
                          <span className="material-symbols-outlined text-tertiary text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                        ) : (
                          <span className="material-symbols-outlined text-outline text-sm">remove</span>
                        )}
                      </td>
                      <td className="px-6 py-3 text-right">
                        <div className="flex items-center gap-2 justify-end">
                          <button onClick={() => navigator.clipboard.writeText(run.path)}
                            className="text-[10px] font-mono text-outline hover:text-on-surface">
                            <span className="material-symbols-outlined text-sm">content_copy</span>
                          </button>
                          <button onClick={() => { setPendingBatchFolder(run.path); window.location.hash = "#/batch"; }}
                            className="px-3 py-1 rounded-lg bg-primary/10 text-primary text-[10px] font-mono font-bold hover:bg-primary/20 border border-primary/20">
                            Validate
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>
    </>
  );
}
