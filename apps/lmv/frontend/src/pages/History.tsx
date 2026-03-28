import React, { useState } from "react";
import { api } from "../api";
import type { HistoryEntry } from "../types";
import { TopHeader } from "../components/TopHeader";
import { DimensionBreakdown } from "../components/DimensionBreakdown";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";

function scoreColor(s: number): string {
  if (s >= 90) return "#27e199";
  if (s >= 70) return "#adc6ff";
  return "#ffb4ab";
}

function statusLabel(label: string): string {
  switch (label) {
    case "HIGH_CONFIDENCE": return "OPTIMIZED";
    case "REVIEW_RECOMMENDED": return "MARGINAL_DIFF";
    default: return "CRITICAL_FAILURE";
  }
}

export function HistoryPage() {
  const [pipelineName, setPipelineName] = useState("");
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function handleSearch() {
    if (!pipelineName.trim()) return;
    setError(null); setEntries([]); setExpandedIdx(null); setLoading(true); setSearched(true);
    try {
      setEntries(await api.history(pipelineName.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    } finally { setLoading(false); }
  }

  return (
    <>
      <TopHeader title="Migration History" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-6xl">
        {/* Search & Filter Card */}
        <section className="mb-10">
          <div className="bg-surface-container rounded-xl p-6 shadow-2xl shadow-blue-900/5">
            <div className="flex flex-col md:flex-row gap-4 items-end">
              <div className="flex-1 space-y-2">
                <label className="text-[11px] font-bold text-slate-500 uppercase tracking-widest px-1 font-body">Search Pipeline Identity</label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 material-symbols-outlined text-slate-500 text-lg">search</span>
                  <input
                    value={pipelineName}
                    onChange={(e) => setPipelineName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                    placeholder="Enter pipeline name, ID, or cluster..."
                    className="w-full bg-surface-container-lowest border-none rounded-lg py-3 pl-12 pr-4 text-sm text-on-surface placeholder:text-slate-600 focus:ring-1 focus:ring-primary/30 transition-all font-body outline-none"
                  />
                </div>
              </div>
              <button
                onClick={handleSearch}
                disabled={loading || !pipelineName.trim()}
                className="bg-gradient-to-br from-primary to-primary-container text-on-primary-container font-bold px-8 py-3 rounded-lg text-sm hover:opacity-90 transition-all active:scale-95 shadow-lg shadow-primary/10 h-[46px]"
              >
                Search Logs
              </button>
            </div>
          </div>
        </section>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
        {loading && <div className="bg-surface-container rounded-xl p-8"><LoadingOverlay message="Loading history..." /></div>}

        {!loading && searched && entries.length === 0 && !error && (
          <div className="bg-surface-container rounded-xl p-12 text-center">
            <span className="material-symbols-outlined text-4xl text-slate-700 mb-4 block">history</span>
            <p className="text-xs font-mono text-slate-600">No history found for &quot;{pipelineName}&quot;</p>
          </div>
        )}

        {entries.length > 0 && (
          <section className="space-y-4">
            <h2 className="text-xs font-bold text-slate-500 uppercase tracking-[0.2em] mb-6 flex items-center gap-3">
              <span className="w-8 h-px bg-slate-800" />
              Execution Logs
            </h2>

            {entries.map((entry, i) => {
              const color = scoreColor(entry.scorecard.score);
              const isOpen = expandedIdx === i;
              const ts = new Date(entry.timestamp).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
              const status = statusLabel(entry.scorecard.label);
              const borderColor = entry.scorecard.score >= 90 ? "border-tertiary" : entry.scorecard.score >= 70 ? "border-primary" : "border-error";

              return (
                <div key={i} className={`group ${borderColor} border-l-2`}>
                  <div className={`${isOpen ? "bg-surface-container" : "bg-surface-container-low"} rounded-r-xl overflow-hidden`}>
                    {/* Entry Header */}
                    <div
                      onClick={() => setExpandedIdx(isOpen ? null : i)}
                      className="p-5 flex items-center justify-between cursor-pointer hover:bg-surface-container transition-colors"
                    >
                      <div className="flex items-center gap-6">
                        {/* Score Box */}
                        <div className="flex flex-col items-center justify-center w-14 h-14 bg-surface-container-lowest rounded-lg">
                          <span className="font-mono text-xl font-bold leading-none" style={{ color }}>
                            {Math.round(entry.scorecard.score)}
                          </span>
                          <span className="text-[9px] text-slate-500 font-mono uppercase mt-1">Score</span>
                        </div>
                        <div>
                          <h3 className="font-headline font-bold text-slate-100">{entry.pipeline_name}</h3>
                          <div className="flex items-center gap-3 mt-1">
                            <span
                              className="machined-chip text-[10px] px-2 py-0.5 font-mono rounded-sm"
                              style={{ borderColor: color, color }}
                            >
                              {status}
                            </span>
                            <span className="text-slate-500 text-[11px] font-mono">{ts}</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-8">
                        {/* Dimension Summary (desktop only) */}
                        <div className="hidden lg:flex gap-10 text-right">
                          {Object.entries(entry.scorecard.dimensions).slice(0, 2).map(([name, dim]) => {
                            const dimPct = Math.round(dim.score * 100);
                            const dimColor = dim.passed ? (dim.score >= 0.9 ? "text-tertiary" : "text-on-surface") : "text-error";
                            return (
                              <div key={name}>
                                <p className="text-[10px] text-slate-500 uppercase font-body">{name.replace(/_/g, ' ')}</p>
                                <p className={`text-sm font-mono ${dimColor}`}>{dimPct}%</p>
                              </div>
                            );
                          })}
                        </div>
                        <span className="material-symbols-outlined text-slate-500 group-hover:text-primary transition-colors"
                          style={{ transform: isOpen ? "rotate(180deg)" : "rotate(0)", transition: "transform 0.2s" }}
                        >
                          expand_more
                        </span>
                      </div>
                    </div>

                    {/* Expanded Details */}
                    {isOpen && (
                      <div className="p-6 bg-surface-container-lowest/50 border-t border-white/5 space-y-6">
                        {/* Dimension mini-cards */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                          {Object.entries(entry.scorecard.dimensions).slice(0, 3).map(([name, dim]) => {
                            const pct = Math.round(dim.score * 100);
                            const cardBorderColor = dim.passed ? "border-tertiary/50" : "border-error/50";
                            const iconColor = dim.passed ? "text-tertiary" : "text-error";
                            const iconName = dim.passed ? "check_circle" : "error";
                            return (
                              <div key={name} className={`bg-surface-container p-4 rounded-lg border-l-2 ${cardBorderColor}`}>
                                <div className="flex justify-between items-start mb-4">
                                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter font-body">
                                    {name.replace(/_/g, ' ')}
                                  </span>
                                  <span className={`material-symbols-outlined ${iconColor} text-lg`}>{iconName}</span>
                                </div>
                                <div className="flex justify-between items-end">
                                  <span className="text-2xl font-mono text-slate-100">{pct}<span className="text-xs text-slate-500">%</span></span>
                                  <span className={`text-[11px] font-mono ${dim.passed ? "text-tertiary" : "text-error"}`}>
                                    {dim.passed ? "Nominal" : "Variance Detected"}
                                  </span>
                                </div>
                                <div className="mt-4 h-1.5 w-full bg-surface-container-high rounded-full overflow-hidden">
                                  <div
                                    className={`h-full rounded-full ${dim.passed ? "bg-tertiary" : "bg-error"}`}
                                    style={{ width: `${pct}%` }}
                                  />
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        <div className="flex justify-end gap-3 pt-4">
                          <button className="text-[11px] font-bold text-slate-400 uppercase border border-outline-variant/30 px-4 py-2 rounded hover:bg-surface-container-high transition-colors">
                            Download JSON Trace
                          </button>
                          <button className="text-[11px] font-bold text-on-primary-container bg-primary-container px-4 py-2 rounded hover:opacity-90 transition-all">
                            Re-run Validation
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </section>
        )}
      </div>
    </>
  );
}
