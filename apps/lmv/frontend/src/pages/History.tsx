import React, { useState } from "react";
import { api } from "../api";
import type { HistoryEntry } from "../types";
import { TopHeader } from "../components/TopHeader";
import { DimensionBreakdown } from "../components/DimensionBreakdown";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";

function scoreColor(s: number): string {
  if (s >= 90) return "#27e199";
  if (s >= 70) return "#ffb547";
  return "#ff5c5c";
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
      <TopHeader title="Audit Log" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-7xl">
        <div>
          <h2 className="text-3xl font-bold font-headline text-on-surface tracking-tight">Scorecard History</h2>
          <p className="text-slate-400 mt-1">Track conversion quality over time. Search by pipeline name.</p>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        <div className="bg-surface-container rounded-xl p-6 border border-white/5 flex gap-4">
          <div className="relative flex-1">
            <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-slate-500 text-lg">search</span>
            <input
              value={pipelineName}
              onChange={(e) => setPipelineName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Search pipeline name..."
              className="w-full bg-surface-container-lowest border-none rounded-lg py-3 pl-12 pr-4 text-sm font-mono text-slate-200 placeholder:text-slate-600 outline-none focus:ring-1 focus:ring-primary/40 transition-all"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={loading || !pipelineName.trim()}
            className="px-6 py-3 rounded-lg bg-accent text-white font-bold text-sm hover:bg-blue-600 transition-all"
          >
            Search
          </button>
        </div>

        {loading && <div className="bg-surface-container rounded-xl p-8"><LoadingOverlay message="Loading history..." /></div>}

        {!loading && searched && entries.length === 0 && !error && (
          <div className="bg-surface-container rounded-xl p-12 text-center">
            <span className="material-symbols-outlined text-4xl text-slate-700 mb-4 block">history</span>
            <p className="text-xs font-mono text-slate-600">No history found for "{pipelineName}"</p>
          </div>
        )}

        {entries.length > 0 && (
          <div className="space-y-3">
            {entries.map((entry, i) => {
              const color = scoreColor(entry.scorecard.score);
              const isOpen = expandedIdx === i;
              const ts = new Date(entry.timestamp).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

              return (
                <div key={i} className={`rounded-xl border border-white/5 overflow-hidden transition-all ${isOpen ? "bg-surface-container-high" : "bg-surface-container"}`}>
                  <div
                    onClick={() => setExpandedIdx(isOpen ? null : i)}
                    className="flex items-center gap-6 px-6 py-4 cursor-pointer hover:bg-surface-container-high/50 transition-colors"
                  >
                    <span className="text-2xl font-bold font-headline min-w-[50px] text-right" style={{ color }}>
                      {Math.round(entry.scorecard.score)}
                    </span>
                    <span
                      className="text-[10px] font-mono font-bold uppercase tracking-widest px-3 py-1 rounded"
                      style={{ color, backgroundColor: `${color}15`, border: `1px solid ${color}30` }}
                    >
                      {entry.scorecard.label.replace(/_/g, " ")}
                    </span>
                    <span className="flex-1" />
                    <span className="text-xs font-mono text-slate-500">{ts}</span>
                    <span
                      className="material-symbols-outlined text-slate-600 text-sm transition-transform"
                      style={{ transform: isOpen ? "rotate(180deg)" : "rotate(0)" }}
                    >
                      expand_more
                    </span>
                  </div>
                  {isOpen && (
                    <div className="px-6 pb-6">
                      <DimensionBreakdown dimensions={entry.scorecard.dimensions} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
