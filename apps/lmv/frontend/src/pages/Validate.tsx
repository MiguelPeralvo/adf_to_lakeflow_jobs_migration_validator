import React, { useState } from "react";
import { api } from "../api";
import type { Scorecard } from "../types";
import { TopHeader } from "../components/TopHeader";
import { ScorecardGauge } from "../components/ScorecardGauge";
import { DimensionBreakdown } from "../components/DimensionBreakdown";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";

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

export function ValidatePage() {
  const [mode, setMode] = useState<InputMode>("adf_json");
  const [input, setInput] = useState(PLACEHOLDERS.adf_json);
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <TopHeader title="Validation Workspace" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-7xl">
        {/* Page header */}
        <div className="flex justify-between items-end">
          <div>
            <h2 className="text-3xl font-bold font-headline text-on-surface tracking-tight">
              System Validation
            </h2>
            <p className="text-slate-500 mt-2">
              Score your ADF-to-Lakeflow conversion across 7 quality dimensions.
              Use <strong className="text-slate-300">Snapshot</strong> mode for the most accurate results.
            </p>
          </div>
          {/* Mode selector chips */}
          <div className="flex gap-2">
            {(Object.keys(MODE_INFO) as InputMode[]).map((m) => {
              const info = MODE_INFO[m];
              const active = mode === m;
              return (
                <button
                  key={m}
                  onClick={() => handleModeChange(m)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-mono font-medium transition-all ${
                    active
                      ? "bg-surface-container-high border border-primary/30 text-primary"
                      : "bg-surface-container border border-white/5 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${info.dot}`} />
                  {info.label}
                </button>
              );
            })}
          </div>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Editor + Gauge grid */}
        <div className="grid grid-cols-12 gap-6">
          {/* Code editor card */}
          <div className="col-span-8 bg-[#060a13] rounded-xl overflow-hidden border border-white/5 shadow-2xl flex flex-col h-[460px]">
            <div className="px-6 py-3 bg-surface-container/30 border-b border-white/5 flex justify-between items-center">
              <div className="flex items-center gap-3">
                <span className="material-symbols-outlined text-primary text-sm">code</span>
                <span className="font-mono text-[10px] text-slate-400 uppercase tracking-widest">
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
              className="flex-1 p-6 font-mono text-sm leading-relaxed text-primary/80 bg-transparent resize-none outline-none placeholder:text-slate-700"
              placeholder={PLACEHOLDERS[mode]}
            />
            <div className="p-4 border-t border-white/5 bg-surface-container/20 flex justify-end">
              <button
                onClick={handleValidate}
                disabled={loading}
                className={`px-8 py-2.5 rounded-lg font-bold text-sm flex items-center gap-2 transition-all ${
                  loading
                    ? "bg-primary/30 text-slate-400 cursor-wait"
                    : "bg-[#2d7ff9] text-white hover:bg-blue-600 hover:scale-[1.02] shadow-lg shadow-blue-900/20"
                }`}
              >
                <span className="material-symbols-outlined text-sm">play_arrow</span>
                {loading ? "Validating..." : "Validate"}
              </button>
            </div>
          </div>

          {/* Scorecard gauge */}
          <div className="col-span-4 bg-surface-container rounded-xl p-8 flex flex-col items-center justify-center border border-white/5 shadow-xl relative overflow-hidden">
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
            {loading && <LoadingOverlay message="Evaluating..." />}
            {scorecard && !loading && <ScorecardGauge scorecard={scorecard} />}
            {!scorecard && !loading && (
              <div className="text-center">
                <span className="material-symbols-outlined text-4xl text-slate-700 mb-4 block">speed</span>
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
