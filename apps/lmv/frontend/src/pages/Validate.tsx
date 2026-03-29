import React, { useState, useEffect } from "react";
import { api } from "../api";
import { consumePendingValidation } from "../store";
import type { Scorecard } from "../types";
import { TopHeader } from "../components/TopHeader";
import { ScorecardGauge } from "../components/ScorecardGauge";
import { DimensionBreakdown } from "../components/DimensionBreakdown";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";
import { PastRunsPanel } from "../components/PastRunsPanel";

type InputMode = "adf_json" | "adf_yaml" | "snapshot";

const PLACEHOLDERS: Record<InputMode, string> = {
  adf_json: `{
  "name": "my_adf_pipeline",
  "properties": {
    "activities": [
      {
        "name": "extract_data",
        "type": "DatabricksNotebook",
        "notebook_path": "/notebooks/extract"
      }
    ]
  }
}`,
  adf_yaml: `name: my_adf_pipeline
properties:
  activities:
    - name: extract_data
      type: DatabricksNotebook
      notebook_path: /notebooks/extract`,
  snapshot: `{
  "tasks": [{"task_key": "extract", "is_placeholder": false}],
  "notebooks": [{"file_path": "/nb/extract.py", "content": "x = 1"}],
  "secrets": [],
  "parameters": ["env"],
  "dependencies": [],
  "not_translatable": [],
  "resolved_expressions": [],
  "total_source_dependencies": 0
}`,
};

const MODE_INFO: Record<InputMode, { label: string; dot: string; hint: string }> = {
  adf_json: { label: "JSON", dot: "bg-primary-container", hint: "Raw ADF pipeline definition" },
  adf_yaml: { label: "YAML", dot: "bg-[#ffb547]", hint: "ADF pipeline as YAML" },
  snapshot: { label: "Snapshot", dot: "bg-[#27e199]", hint: "Pre-converted from wkmigrate — most accurate" },
};

export function ValidatePage({ entityId }: { entityId?: string | null }) {
  const [mode, setMode] = useState<InputMode>("adf_json");
  const [input, setInput] = useState(PLACEHOLDERS.adf_json);
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourcePipeline, setSourcePipeline] = useState<string | null>(null);
  const [currentEntityId, setCurrentEntityId] = useState<string | null>(entityId ?? null);

  // Load entity from URL
  useEffect(() => {
    if (entityId) {
      setLoading(true);
      api.getEntity(entityId)
        .then((data) => {
          const results = (data.results as Record<string, unknown>) || data;
          setScorecard(results as unknown as Scorecard);
          setSourcePipeline((data.pipeline_name as string) || null);
          setCurrentEntityId(entityId);
        })
        .catch((err) => setError(err instanceof Error ? err.message : "Failed to load entity"))
        .finally(() => setLoading(false));
      return;
    }
    // Auto-load pipeline from Synthetic page navigation
    const pending = consumePendingValidation();
    if (pending) {
      setMode("adf_json");
      setInput(JSON.stringify(pending.adf_json, null, 2));
      setSourcePipeline(pending.pipeline_name);
      setLoading(true);
      api.validate({ adf_json: pending.adf_json as object, pipeline_name: pending.pipeline_name })
        .then((result) => {
          setScorecard(result);
          if (result.entity_id) {
            setCurrentEntityId(result.entity_id);
            window.history.replaceState(null, "", `#/validate/${result.entity_id}`);
          }
        })
        .catch((err: unknown) => setError(err instanceof Error ? err.message : "Validation failed"))
        .finally(() => setLoading(false));
    }
  }, [entityId]);

  function handleModeChange(m: InputMode) {
    setMode(m);
    setInput(PLACEHOLDERS[m]);
    setScorecard(null);
    setError(null);
  }

  async function handleValidate() {
    setError(null);
    setScorecard(null);
    setLoading(true);
    try {
      let payload: Record<string, unknown>;
      if (mode === "adf_yaml") {
        payload = { adf_yaml: input };
      } else {
        const parsed = JSON.parse(input);
        payload = mode === "snapshot" ? { snapshot: parsed } : { adf_json: parsed };
      }
      const result = await api.validate(payload);
      setScorecard(result);
      if (result.entity_id) {
        setCurrentEntityId(result.entity_id);
        window.history.replaceState(null, "", `#/validate/${result.entity_id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setLoading(false);
    }
  }

  function handlePastRunSelect(eid: string) {
    window.location.hash = `#/validate/${eid}`;
  }

  return (
    <>
      <TopHeader title="Validation Workspace" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-7xl">
        {/* Page header */}
        <section className="flex justify-between items-end">
          <div>
            <h2 className="text-4xl font-bold font-headline text-on-surface tracking-tight">
              System Validation
            </h2>
            <p className="text-slate-500 font-body mt-2">
              Precision telemetry for Lakeflow migration integrity and structural parity.
            </p>
          </div>
          <div className="flex gap-3">
            {(Object.keys(MODE_INFO) as InputMode[]).map((m) => {
              const info = MODE_INFO[m];
              const active = mode === m;
              return (
                <button
                  key={m}
                  onClick={() => handleModeChange(m)}
                  className={`flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-body font-medium border transition-colors ${
                    active
                      ? "bg-surface-container-high border-primary/30 text-primary"
                      : "bg-surface-container border-outline-variant/10 text-slate-300 hover:bg-surface-container-high"
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${info.dot}`} />
                  {info.label}
                </button>
              );
            })}
            <button
              onClick={handleValidate}
              disabled={loading}
              className="px-5 py-2 rounded-lg bg-gradient-to-br from-primary to-primary-container text-on-primary-container font-bold font-body text-sm shadow-lg shadow-blue-900/20 hover:scale-[1.02] transition-transform"
            >
              Validate
            </button>
          </div>
        </section>

        {/* Past runs panel */}
        <PastRunsPanel type="validation" onSelect={handlePastRunSelect} currentEntityId={currentEntityId} />

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Source banner when navigating from Synthetic */}
        {sourcePipeline && (
          <div className="flex items-center gap-3 px-5 py-3 rounded-xl bg-primary/5 border border-primary/20">
            <span className="material-symbols-outlined text-primary text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>science</span>
            <div>
              <span className="text-[10px] font-mono text-outline uppercase tracking-wider">From Synthetic Engine</span>
              <p className="text-sm font-mono text-on-surface font-medium">{sourcePipeline}</p>
            </div>
            {currentEntityId && (
              <span className="ml-auto machined-chip border-outline-variant/30 text-outline px-2 py-0.5 rounded text-[9px] font-mono">
                {currentEntityId.slice(0, 8)}
              </span>
            )}
          </div>
        )}

        {/* Editor + Gauge grid */}
        <div className="grid grid-cols-12 gap-6">
          {/* JSON Editor Card */}
          <div className="col-span-8 bg-[#060a13] rounded-xl overflow-hidden border border-outline-variant/10 shadow-2xl flex flex-col h-[500px]">
            <div className="px-6 py-4 bg-surface-container/30 border-b border-outline-variant/5 flex justify-between items-center">
              <div className="flex items-center gap-3">
                <span className="material-symbols-outlined text-primary text-sm">code</span>
                <span className="font-mono text-xs text-slate-400 uppercase tracking-widest">
                  {MODE_INFO[mode].hint}
                </span>
              </div>
              <div className="flex gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500/20 border border-red-500/40" />
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/20 border border-yellow-500/40" />
                <div className="w-2.5 h-2.5 rounded-full bg-green-500/20 border border-green-500/40" />
              </div>
            </div>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              spellCheck={false}
              className="flex-1 p-6 font-mono text-sm leading-relaxed text-primary-fixed-dim/80 bg-transparent resize-none outline-none placeholder:text-slate-700"
              placeholder={PLACEHOLDERS[mode]}
            />
            <div className="p-4 border-t border-outline-variant/5 bg-surface-container/20 flex justify-end">
              <button
                onClick={handleValidate}
                disabled={loading}
                className={`px-8 py-2 rounded-lg font-bold font-body text-sm flex items-center gap-2 transition-all ${
                  loading
                    ? "bg-primary/30 text-slate-400 cursor-wait"
                    : "bg-[#2d7ff9] text-white hover:bg-blue-600 shadow-lg shadow-blue-900/20"
                }`}
              >
                <span className="material-symbols-outlined text-sm">play_arrow</span>
                {loading ? "Validating..." : "Validate"}
              </button>
            </div>
          </div>

          {/* Scorecard Gauge Card */}
          <div className="col-span-4 bg-surface-container rounded-xl p-8 flex flex-col items-center justify-center space-y-6 border border-outline-variant/10 shadow-xl relative overflow-hidden">
            {/* Subtle Glow Background */}
            {scorecard && (
              <div
                className="absolute inset-0 blur-[100px] pointer-events-none"
                style={{
                  backgroundColor:
                    scorecard.score >= 90
                      ? "rgba(39,225,153,0.05)"
                      : scorecard.score >= 70
                      ? "rgba(255,181,71,0.05)"
                      : "rgba(255,92,92,0.05)",
                }}
              />
            )}
            <h3 className="font-headline text-lg text-slate-300">Composite Score</h3>
            {loading && <LoadingOverlay message="Evaluating..." />}
            {scorecard && !loading && <ScorecardGauge scorecard={scorecard} />}
            {scorecard && !loading && (
              <p className="text-center text-sm text-slate-400 font-body">
                {scorecard.score >= 90
                  ? "All dimensions within optimal range."
                  : scorecard.score >= 70
                  ? "Review recommended for underperforming dimensions."
                  : <>Validation score requires <span className="text-red-400 font-mono">manual intervention</span>.</>}
              </p>
            )}
            {!scorecard && !loading && (
              <div className="text-center space-y-4">
                <span className="material-symbols-outlined text-4xl text-slate-700 block">speed</span>
                <p className="text-xs font-mono text-slate-600 leading-relaxed">
                  Paste a pipeline definition
                  <br />
                  and run validation
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Dimension breakdown */}
        {scorecard && !loading && (
          <DimensionBreakdown dimensions={scorecard.dimensions} />
        )}
      </div>
    </>
  );
}
