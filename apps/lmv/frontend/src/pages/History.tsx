import React, { useState } from "react";
import { api } from "../api";
import type { HistoryEntry, Scorecard } from "../types";
import { Card, SectionTitle } from "../components/Card";
import { DimensionBreakdown } from "../components/DimensionBreakdown";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";

function scoreBadge(score: number) {
  const color = score >= 90 ? "var(--green)" : score >= 70 ? "var(--amber)" : "var(--red)";
  const bg = score >= 90 ? "var(--green-dim)" : score >= 70 ? "var(--amber-dim)" : "var(--red-dim)";
  return { color, bg };
}

function TimelineEntry({ entry, onExpand, expanded }: { entry: HistoryEntry; onExpand: () => void; expanded: boolean }) {
  const { color, bg } = scoreBadge(entry.scorecard.score);
  const ts = new Date(entry.timestamp);
  const timeStr = ts.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        background: expanded ? "var(--bg-elevated)" : "var(--bg-surface)",
        overflow: "hidden",
        transition: "all var(--transition)",
      }}
    >
      <div
        onClick={onExpand}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "14px 18px",
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: 22,
            color,
            minWidth: 50,
            textAlign: "right",
          }}
        >
          {Math.round(entry.scorecard.score)}
        </span>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            fontWeight: 500,
            padding: "3px 10px",
            borderRadius: 12,
            background: bg,
            color,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
          }}
        >
          {entry.scorecard.label.replace(/_/g, " ")}
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)" }}>
          {timeStr}
        </span>
        <span
          style={{
            fontSize: 10,
            color: "var(--text-muted)",
            transform: expanded ? "rotate(180deg)" : "rotate(0)",
            transition: "transform var(--transition)",
          }}
        >
          {"\u25BC"}
        </span>
      </div>

      {expanded && (
        <div style={{ padding: "0 18px 18px", animation: "fadeInUp 0.3s ease" }}>
          <DimensionBreakdown dimensions={entry.scorecard.dimensions} />
        </div>
      )}
    </div>
  );
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
    setError(null);
    setEntries([]);
    setExpandedIdx(null);
    setLoading(true);
    setSearched(true);
    try {
      const res = await api.history(pipelineName.trim());
      setEntries(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ animation: "fadeInUp 0.4s ease" }}>
      <SectionTitle>Scorecard History</SectionTitle>

      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 12 }}>
          <input
            value={pipelineName}
            onChange={(e) => setPipelineName(e.target.value)}
            placeholder="Pipeline name to search..."
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            style={{
              flex: 1,
              padding: "10px 14px",
              background: "var(--bg-base)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              fontFamily: "var(--font-mono)",
              fontSize: 13,
              outline: "none",
            }}
          />
          <button
            onClick={handleSearch}
            disabled={loading || !pipelineName.trim()}
            style={{
              padding: "10px 24px",
              background: "var(--accent)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--radius)",
              fontFamily: "var(--font-display)",
              fontWeight: 600,
              fontSize: 13,
              cursor: "pointer",
              opacity: loading || !pipelineName.trim() ? 0.5 : 1,
            }}
          >
            Search
          </button>
        </div>
      </Card>

      {loading && <Card><LoadingOverlay message="Loading history..." /></Card>}
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {!loading && searched && entries.length === 0 && !error && (
        <Card>
          <div style={{ textAlign: "center", color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 12, padding: 24 }}>
            No history found for "{pipelineName}"
          </div>
        </Card>
      )}

      {entries.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {entries.map((entry, i) => (
            <TimelineEntry
              key={i}
              entry={entry}
              expanded={expandedIdx === i}
              onExpand={() => setExpandedIdx(expandedIdx === i ? null : i)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
