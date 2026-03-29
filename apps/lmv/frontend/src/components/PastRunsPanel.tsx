import React, { useState, useEffect } from "react";
import { api } from "../api";
import type { EntitySummary } from "../types";

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function scoreColor(s: number): string {
  if (s >= 90) return "#27e199";
  if (s >= 70) return "#adc6ff";
  return "#ffb4ab";
}

interface Props {
  /** Backend event type to filter by (e.g., "validation", "expression"). */
  type: string;
  /** Called when a past run is selected. */
  onSelect: (entityId: string) => void;
  /** Currently viewed entity ID (highlighted in the list). */
  currentEntityId?: string | null;
}

export function PastRunsPanel({ type, onSelect, currentEntityId }: Props) {
  const [entities, setEntities] = useState<EntitySummary[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.listEntities(type, 15)
      .then(setEntities)
      .catch(() => setEntities([]))
      .finally(() => setLoading(false));
  }, [type]);

  if (entities.length === 0 && !loading) return null;

  function label(e: EntitySummary): string {
    if (e.pipeline_name) return e.pipeline_name;
    if (e.adf_expression) return e.adf_expression.slice(0, 40);
    if (e.folder) return e.folder.split("/").pop() || e.folder;
    if (e.output_path) return e.output_path.split("/").pop() || e.output_path;
    return e.entity_id.slice(0, 8);
  }

  function scoreBadge(e: EntitySummary): React.ReactNode {
    const s = e.scorecard?.score ?? e.score ?? e.mean_score ?? e.equivalence_score;
    if (s == null) return null;
    const pct = s > 1 ? s : s * 100;
    return (
      <span className="font-mono text-[10px] font-bold" style={{ color: scoreColor(pct) }}>
        {Math.round(pct)}%
      </span>
    );
  }

  return (
    <div className="bg-surface-container rounded-xl border border-outline-variant/10 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-4 py-2.5 flex items-center gap-2 text-left hover:bg-surface-container-high/30 transition-colors select-none"
      >
        <span className="material-symbols-outlined text-primary text-sm">history</span>
        <span className="text-[10px] font-mono text-outline uppercase tracking-widest flex-1">
          Past Runs ({entities.length})
        </span>
        <span className={`material-symbols-outlined text-sm text-outline transition-transform ${open ? "rotate-180" : ""}`}>
          expand_more
        </span>
      </button>
      {open && (
        <div className="border-t border-outline-variant/5 max-h-[260px] overflow-y-auto">
          {loading ? (
            <div className="p-4 flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
              <span className="text-[10px] font-mono text-outline">Loading...</span>
            </div>
          ) : (
            entities.map((e) => {
              const isCurrent = e.entity_id === currentEntityId;
              return (
                <button
                  key={e.entity_id}
                  onClick={() => onSelect(e.entity_id)}
                  className={`w-full px-4 py-2 flex items-center gap-3 text-left transition-colors ${
                    isCurrent
                      ? "bg-primary/10 border-l-2 border-primary"
                      : "hover:bg-surface-container-high/30 border-l-2 border-transparent"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <p className={`text-xs font-mono truncate ${isCurrent ? "text-primary" : "text-on-surface"}`}>
                      {label(e)}
                    </p>
                    <p className="text-[9px] font-mono text-outline">{relativeTime(e.timestamp)}</p>
                  </div>
                  {scoreBadge(e)}
                  <span className="text-[8px] font-mono text-outline/50 w-14 text-right truncate">
                    {e.entity_id.slice(0, 8)}
                  </span>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
