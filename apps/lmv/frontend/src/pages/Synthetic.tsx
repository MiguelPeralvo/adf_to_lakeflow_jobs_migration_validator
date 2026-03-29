import React, { useState, useEffect, useCallback, useRef } from "react";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";
import { setPendingValidation, setPendingBatchFolder } from "../store";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type Mode = "template" | "llm" | "custom";
interface TemplateInfo { key: string; label: string; icon: string; description: string }
interface TestDataItem { pipeline_name: string; source_files: Record<string, string>; seed_sql: string[]; expected_outputs: Record<string, string>; setup_instructions: string }
interface PipelineItem { name: string; adf_json: Record<string, unknown>; description: string; difficulty: string }
interface GenerateResult { count: number; pipelines: PipelineItem[]; output_path: string | null; test_data?: TestDataItem[]; fallback_note?: string }
interface PlanSpec { name: string; stress_area: string; activity_count: number }

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export function SyntheticPage() {
  /* ---- config ---- */
  const [mode, setMode] = useState<Mode>("llm");
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [count, setCount] = useState(10);
  const [maxActivities, setMaxActivities] = useState(20);
  const [difficulty, setDifficulty] = useState("medium");
  const [generateTestData, setGenerateTestData] = useState(false);

  /* ---- spec (natural language) ---- */
  const [spec, setSpec] = useState("");
  const [specLoading, setSpecLoading] = useState(false);

  /* ---- plan (structured, read-only) ---- */
  const [planSpecs, setPlanSpecs] = useState<PlanSpec[]>([]);

  /* ---- generation ---- */
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [resultTab, setResultTab] = useState<"pipelines" | "testdata">("pipelines");
  const [selectedPipeline, setSelectedPipeline] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* ---- progress ---- */
  const [progressCompleted, setProgressCompleted] = useState(0);
  const [progressTotal, setProgressTotal] = useState(0);
  const [progressFailed, setProgressFailed] = useState(0);
  const [lastPipelineName, setLastPipelineName] = useState<string | null>(null);
  const [pipelineErrors, setPipelineErrors] = useState<string[]>([]);
  const [phase, setPhase] = useState<"idle" | "planning" | "generating" | "done">("idle");

  /* ---- per-pipeline stage ---- */
  const [currentPipelineIdx, setCurrentPipelineIdx] = useState(-1);
  const [currentStage, setCurrentStage] = useState("");
  const [currentStagePct, setCurrentStagePct] = useState(0);
  const [currentAttempt, setCurrentAttempt] = useState(0);
  const [maxAttempts, setMaxAttempts] = useState(0);
  const [pipelineStatus, setPipelineStatus] = useState<Record<number, "ok" | "fail">>({});

  /* ---- load templates ---- */
  useEffect(() => { fetch("/api/synthetic/templates").then(r => r.json()).then(setTemplates).catch(() => {}); }, []);

  /* ---- resolve spec text from template + params ---- */
  const resolveSpecCounter = useRef(0);
  const resolveSpec = useCallback(async (preset: string | null) => {
    if (!preset || mode === "custom") return;
    const requestId = ++resolveSpecCounter.current;
    try {
      const res = await fetch("/api/synthetic/resolve-template", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset, count, max_activities: maxActivities, difficulty, generate_test_data: generateTestData }),
      });
      const data = await res.json();
      if (data.prompt && requestId === resolveSpecCounter.current) setSpec(data.prompt);
    } catch {}
  }, [mode, count, maxActivities, difficulty, generateTestData]);

  function selectPreset(key: string) {
    setSelectedPreset(key);
    resolveSpec(key);
  }

  /* Re-resolve when any param changes (if a preset is selected) */
  useEffect(() => { if (selectedPreset && mode !== "custom") resolveSpec(selectedPreset); }, [count, maxActivities, difficulty, generateTestData, selectedPreset, resolveSpec]);

  /* ---- Generate Spec via LLM (enriches spec from prompt) ---- */
  async function handleGenerateSpec() {
    setError(null); setSpecLoading(true);
    try {
      const body: Record<string, unknown> = { count, mode, difficulty, max_activities: maxActivities };
      if (selectedPreset) body.preset = selectedPreset;
      if (spec) body.custom_prompt = spec;
      const res = await fetch("/api/synthetic/spec", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `HTTP ${res.status}`); }
      const data = await res.json();
      /* Convert structured spec to readable natural-language summary */
      const lines = [`Generate ${data.count} ADF pipelines:\n`];
      for (const p of data.pipelines || []) {
        lines.push(`• ${p.name} — ${p.activity_count} activities, stress: ${p.stress_area}`);
        if (p.expression_complexity) lines[lines.length - 1] += `, complexity: ${p.expression_complexity}`;
      }
      setSpec(lines.join("\n"));
    } catch (err) { setError(err instanceof Error ? err.message : "Spec generation failed"); }
    finally { setSpecLoading(false); }
  }

  /* ---- Run generation (from spec or quickstart) ---- */
  async function runGeneration(specText?: string) {
    setError(null); setResult(null); setGenerating(true); setPlanSpecs([]);
    setProgressCompleted(0); setProgressTotal(0); setProgressFailed(0);
    setLastPipelineName(null); setPipelineErrors([]); setPhase("planning");
    setCurrentPipelineIdx(-1); setCurrentStage(""); setCurrentStagePct(0); setCurrentAttempt(0); setMaxAttempts(0); setPipelineStatus({});
    setResultTab("pipelines"); setSelectedPipeline(null);
    try {
      const body: Record<string, unknown> = { count, difficulty, max_activities: maxActivities, mode, generate_test_data: generateTestData };
      if (selectedPreset) body.preset = selectedPreset;
      const text = specText ?? spec;
      if (text) body.custom_prompt = text;
      const res = await fetch("/api/synthetic/generate?stream=true", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `HTTP ${res.status}`); }
      const reader = res.body!.getReader(); const decoder = new TextDecoder();
      let buffer = "", finalResult: GenerateResult | null = null, failed = 0;
      while (true) {
        const { done, value } = await reader.read(); if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n"); buffer = lines.pop()!;
        for (const line of lines) { if (!line.trim()) continue;
          try { const ev = JSON.parse(line);
            if (ev.type === "plan") { setPlanSpecs(ev.specs || []); setProgressTotal(ev.count); setPhase("generating"); }
            else if (ev.type === "stage") { setCurrentPipelineIdx(ev.pipeline_index); setCurrentStage(ev.stage); setCurrentStagePct(ev.pct ?? 0); setLastPipelineName(ev.pipeline_name); if (ev.attempt) { setCurrentAttempt(ev.attempt); setMaxAttempts(ev.max_attempts ?? 1); } }
            else if (ev.type === "progress") { setProgressCompleted(ev.completed); setProgressTotal(ev.total); setCurrentStage(""); setCurrentStagePct(0); if (ev.pipeline_name) setLastPipelineName(ev.pipeline_name); const idx = ev.completed - 1; setPipelineStatus(prev => ({ ...prev, [idx]: ev.ok ? "ok" : "fail" })); if (ev.ok === false) { failed++; setProgressFailed(failed); if (ev.error) setPipelineErrors(p => [...p, `Pipeline ${ev.completed}: ${ev.error}`]); } }
            else if (ev.type === "complete") { finalResult = ev.result; setResult(ev.result); }
          } catch {} }
      }
      if (!finalResult) throw new Error("Generation stream ended unexpectedly");
      setTimeout(() => document.getElementById("synthetic-results")?.scrollIntoView({ behavior: "smooth" }), 120);
    } catch (err) { setError(err instanceof Error ? err.message : "Generation failed"); }
    finally { setGenerating(false); setPhase("done"); }
  }

  function openInValidator(p: PipelineItem) {
    setPendingValidation({ pipeline_name: p.name, adf_json: p.adf_json, source: "synthetic" });
    window.location.hash = `#/validate?pipeline=${encodeURIComponent(p.name)}`;
  }

  // Overall %: during "generating" (LLM call), estimate 50% since we can't track it.
  // For other stages, use the actual pct.
  const pipelineFraction = currentStage === "generating" ? 0.5 : (currentStagePct / 100);
  const overallPct = progressTotal > 0
    ? ((progressCompleted + pipelineFraction) / progressTotal) * 100
    : 0;
  const hasSpec = spec.trim().length > 10;
  const busy = specLoading || generating;

  const STAGE_LABELS: Record<string, string> = {
    preparing: "Preparing prompt",
    generating: "Calling LLM",
    parsing: "Parsing response",
    validating: "Validating structure",
    building_snapshot: "Building snapshot",
    retry: "Retrying",
    complete: "Complete",
    failed: "Failed",
  };

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */
  return (
    <>
      <TopHeader title="Synthetic Generation" />
      <div className="pt-24 pb-16 px-10 max-w-7xl space-y-10"
           style={{ animation: "fade-in-up 0.4s ease both" }}>

        {/* ─── Header ─── */}
        <section className="flex justify-between items-end gap-8">
          <div>
            <h2 className="text-4xl font-bold font-headline text-on-surface tracking-tight">
              Synthetic Pipeline &amp; Data Generation
            </h2>
            <p className="text-slate-500 font-body mt-2 max-w-xl">
              Author a natural-language spec, let the agent build a validated plan, then generate calibrated ADF pipelines and test data.
            </p>
          </div>
          {/* Phase badges */}
          <div className="flex items-center gap-2 shrink-0">
            {(["spec", "plan", "generate"] as const).map((step, i) => {
              const done = step === "spec" ? hasSpec : step === "plan" ? planSpecs.length > 0 : !!result;
              const active = step === "spec" ? (!generating && !result) : step === "plan" ? phase === "planning" : phase === "generating";
              return (
                <React.Fragment key={step}>
                  {i > 0 && <div className={`w-6 h-px ${done ? "bg-tertiary/50" : "bg-outline-variant/20"}`} />}
                  <span className={`machined-chip px-2.5 py-1 rounded text-[9px] font-mono uppercase tracking-wider ${
                    done ? "border-tertiary text-tertiary" : active ? "border-primary text-primary" : "border-outline-variant/30 text-outline"
                  }`}>{step}</span>
                </React.Fragment>
              );
            })}
          </div>
        </section>

        {/* ─── Progress banner ─── */}
        {generating && (
          <div className="sticky top-16 z-30 rounded-xl overflow-hidden bg-surface-container border border-primary/20 shadow-xl shadow-blue-900/10"
               style={{ animation: "fade-in-up 0.25s ease both" }}>
            {/* Overall progress bar */}
            <div className="h-1.5 bg-surface-container-highest">
              <div className="h-full bg-primary transition-all duration-700 ease-out" style={{ width: `${overallPct}%` }} />
            </div>
            <div className="px-5 py-3 space-y-3">
              {phase === "planning" ? (
                <div className="flex items-center gap-3">
                  <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin shrink-0" />
                  <p className="text-sm font-mono text-on-surface">
                    <span className="text-primary font-semibold">Building plan</span> — agent is analyzing spec and designing pipelines...
                  </p>
                </div>
              ) : progressTotal > 0 ? (<>
                {/* Overall status line */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin shrink-0" />
                    <p className="text-sm font-mono text-on-surface">
                      Pipeline <span className="text-primary font-bold">{progressCompleted + 1}</span>
                      <span className="text-outline">/{progressTotal}</span>
                    </p>
                  </div>
                  <span className="text-xs font-mono text-outline">{Math.round(overallPct)}% overall</span>
                </div>

                {/* Current pipeline detail */}
                {currentStage && lastPipelineName && (
                  <div className="bg-surface-container-high/40 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-on-surface font-medium truncate">{lastPipelineName}</span>
                      <span className="text-[10px] font-mono text-outline">
                        {currentStage === "generating" ? "Waiting for LLM..." : `${currentStagePct}%`}
                      </span>
                    </div>
                    {/* Per-pipeline stage progress bar */}
                    <div className="h-1 bg-surface-container-highest rounded-full overflow-hidden">
                      {currentStage === "generating" ? (
                        /* Indeterminate shimmer while waiting for LLM */
                        <div className="h-full w-1/3 bg-primary-container rounded-full animate-[shimmer_1.5s_ease-in-out_infinite]"
                          style={{ animationName: "shimmer" }} />
                      ) : (
                        <div className="h-full bg-primary-container transition-all duration-300 ease-out rounded-full" style={{ width: `${currentStagePct}%` }} />
                      )}
                    </div>
                    {/* Stage indicators */}
                    <div className="flex items-center gap-1">
                      {(["preparing", "generating", "parsing", "validating", "building_snapshot"] as const).map((s) => {
                        const stageOrder = ["preparing", "generating", "parsing", "validating", "building_snapshot"];
                        const ci = stageOrder.indexOf(currentStage === "retry" ? "generating" : currentStage);
                        const si = stageOrder.indexOf(s);
                        const isDone = si < ci;
                        const isActive = si === ci;
                        return (
                          <React.Fragment key={s}>
                            {si > 0 && <div className={`flex-1 h-px ${isDone ? "bg-tertiary/40" : isActive ? "bg-primary/40" : "bg-outline-variant/15"}`} />}
                            <div className={`flex items-center gap-1 ${isDone ? "text-tertiary" : isActive ? "text-primary" : "text-outline/40"}`}>
                              {isDone
                                ? <span className="material-symbols-outlined text-[11px]" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                                : isActive
                                ? <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                                : <span className="inline-block w-1.5 h-1.5 rounded-full bg-outline-variant/30" />}
                              <span className="text-[9px] font-mono whitespace-nowrap">
                                {s === "generating" && isActive && currentStage === "retry"
                                  ? `Retry ${currentAttempt}/${maxAttempts}`
                                  : s === "generating" && isActive && maxAttempts > 1
                                  ? `LLM ${currentAttempt}/${maxAttempts}`
                                  : STAGE_LABELS[s] ?? s}
                              </span>
                            </div>
                          </React.Fragment>
                        );
                      })}
                    </div>
                  </div>
                )}

                {progressFailed > 0 && (
                  <details>
                    <summary className="text-[11px] font-mono text-amber-400 cursor-pointer">{progressFailed} failed — details</summary>
                    <div className="mt-1 max-h-20 overflow-auto pl-2 border-l border-amber-500/20">
                      {pipelineErrors.map((e, i) => <p key={i} className="text-[11px] font-mono text-amber-300/70">{e}</p>)}
                    </div>
                  </details>)}
              </>) : (
                <div className="flex items-center gap-3">
                  <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin shrink-0" />
                  <p className="text-sm font-mono text-on-surface">Initializing...</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ─── Done banner ─── */}
        {result && !generating && (
          <div className={`sticky top-16 z-30 rounded-xl overflow-hidden bg-surface-container shadow-xl ${progressFailed > 0 ? "border border-amber-500/20 shadow-amber-900/10" : "border border-tertiary/20 shadow-emerald-900/10"}`}
               style={{ animation: "fade-in-up 0.3s ease both" }}>
            <div className={`h-1 ${progressFailed > 0 ? "bg-amber-500" : "bg-tertiary"}`} />
            <div className="px-5 py-3 space-y-2">
              <div className="flex items-center gap-4">
                <span className={`material-symbols-outlined text-xl ${progressFailed > 0 ? "text-amber-400" : "text-tertiary"}`} style={{ fontVariationSettings: "'FILL' 1" }}>
                  {progressFailed > 0 ? "warning" : "check_circle"}
                </span>
                <div className="flex-1 flex items-center gap-6 flex-wrap">
                  <p className="text-sm font-mono text-on-surface">
                    <span className="text-tertiary font-bold">{result.count}</span> pipelines generated
                    {progressFailed > 0 && <span className="text-amber-400 ml-2">({progressFailed} failed)</span>}
                  </p>
                  {result.output_path && (
                    <div className="flex items-center gap-2 text-[11px] font-mono text-outline">
                      <span className="material-symbols-outlined text-sm">folder</span>
                      <span className="truncate max-w-xs" title={result.output_path}>{result.output_path}</span>
                      <button onClick={() => navigator.clipboard.writeText(result.output_path!)} className="text-primary hover:text-primary-container" title="Copy">
                        <span className="material-symbols-outlined text-sm">content_copy</span>
                      </button>
                    </div>)}
                </div>
              </div>
              {/* Show error details persistently after generation */}
              {pipelineErrors.length > 0 && (
                <details className="ml-9" open>
                  <summary className="text-[11px] font-mono text-amber-400 cursor-pointer hover:text-amber-300">
                    {pipelineErrors.length} generation error{pipelineErrors.length > 1 ? "s" : ""} — details
                  </summary>
                  <div className="mt-1.5 space-y-1 max-h-40 overflow-auto">
                    {pipelineErrors.map((e, i) => (
                      <p key={i} className="text-[11px] font-mono text-amber-300/80 pl-2 border-l-2 border-amber-500/20">{e}</p>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </div>
        )}

        {/* ─── Plan panel — visible during & after generation ─── */}
        {planSpecs.length > 0 && (
          <details className="rounded-xl bg-surface-container border border-outline-variant/10 overflow-hidden shadow-lg"
                   open={generating || (!!result && planSpecs.length <= 20)}
                   style={{ animation: "fade-in-up 0.3s ease both" }}>
            <summary className="px-5 py-3 cursor-pointer flex items-center gap-3 hover:bg-surface-container-high/30 transition-colors select-none">
              <span className={`material-symbols-outlined text-sm ${result && !generating ? "text-tertiary" : "text-primary"}`}>
                {result && !generating ? "task_alt" : "checklist"}
              </span>
              <span className="text-sm font-mono text-on-surface-variant flex-1">
                Agent Plan — <span className="text-on-surface font-semibold">{planSpecs.length}</span> pipelines
              </span>
              {generating && (
                <span className="machined-chip border-primary text-primary px-2 py-0.5 rounded text-[9px] font-mono">
                  {progressCompleted}/{progressTotal}
                </span>
              )}
              {result && !generating && (
                <span className="machined-chip border-tertiary text-tertiary px-2 py-0.5 rounded text-[9px] font-mono">
                  complete
                </span>
              )}
            </summary>
            <div className="border-t border-outline-variant/5">
              {planSpecs.length <= 12 ? (
                /* Table layout for manageable counts */
                <table className="w-full text-left">
                  <thead className="text-[9px] font-mono text-outline uppercase tracking-wider bg-surface-container-high/30">
                    <tr>
                      <th className="pl-5 pr-2 py-2 w-10"></th>
                      <th className="px-3 py-2">Pipeline Name</th>
                      <th className="px-3 py-2">Stress Area</th>
                      <th className="px-3 py-2 w-20 text-right pr-5">Activities</th>
                    </tr>
                  </thead>
                  <tbody>
                    {planSpecs.map((s, i) => {
                      const status = pipelineStatus[i];
                      const isDone = status === "ok";
                      const isFailed = status === "fail";
                      const isCurrent = progressCompleted === i && generating && !status;
                      return (
                        <tr key={i} className={`border-t border-outline-variant/5 transition-colors ${
                          isCurrent ? "bg-primary/5" : isFailed ? "bg-error/3" : isDone ? "" : "opacity-50"
                        }`}>
                          <td className="pl-5 pr-2 py-2 text-center">
                            {isDone
                              ? <span className="material-symbols-outlined text-tertiary text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                              : isFailed
                              ? <span className="material-symbols-outlined text-error text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>cancel</span>
                              : isCurrent
                              ? <div className="w-3.5 h-3.5 mx-auto border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                              : <span className="text-[10px] font-mono text-outline">{String(i + 1).padStart(2, "0")}</span>}
                          </td>
                          <td className={`px-3 py-2 text-xs font-mono ${isFailed ? "text-error/70 line-through" : "text-on-surface"}`}>{s.name}</td>
                          <td className="px-3 py-2 text-[11px] text-outline truncate max-w-xs">{s.stress_area}</td>
                          <td className="px-3 py-2 text-xs font-mono text-outline text-right pr-5">{s.activity_count}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                /* Compact grid for large counts (>12) */
                <div className="p-4 space-y-3">
                  {(() => {
                    const okCount = Object.values(pipelineStatus).filter(s => s === "ok").length;
                    const failCount = Object.values(pipelineStatus).filter(s => s === "fail").length;
                    const pendingCount = planSpecs.length - okCount - failCount - (generating ? 1 : 0);
                    return (
                      <div className="flex items-center gap-4 text-[10px] font-mono text-outline">
                        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-tertiary" /> Done ({okCount})</span>
                        {failCount > 0 && <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-error" /> Failed ({failCount})</span>}
                        {generating && <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse" /> In progress</span>}
                        {pendingCount > 0 && <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-outline-variant/40" /> Pending ({pendingCount})</span>}
                      </div>
                    );
                  })()}
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-1.5">
                    {planSpecs.map((s, i) => {
                      const status = pipelineStatus[i];
                      const isDone = status === "ok";
                      const isFailed = status === "fail";
                      const isCurrent = progressCompleted === i && generating && !status;
                      return (
                        <div key={i} className={`px-2.5 py-1.5 rounded-lg text-[10px] font-mono transition-all flex items-center gap-1.5 min-w-0 ${
                          isDone ? "bg-tertiary/10 text-tertiary border border-tertiary/15"
                            : isFailed ? "bg-error/10 text-error border border-error/15"
                            : isCurrent ? "bg-primary/10 text-primary border border-primary/20"
                            : "bg-surface-container-high/50 text-outline border border-transparent"
                        }`} title={`${s.name} — ${s.stress_area} (${s.activity_count} activities)${isFailed ? " — FAILED" : ""}`}>
                          {isDone && <span className="material-symbols-outlined text-[11px] shrink-0" style={{ fontVariationSettings: "'FILL' 1" }}>check</span>}
                          {isFailed && <span className="material-symbols-outlined text-[11px] shrink-0" style={{ fontVariationSettings: "'FILL' 1" }}>close</span>}
                          {isCurrent && <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse shrink-0" />}
                          {!isDone && !isFailed && !isCurrent && <span className="text-outline/40 shrink-0">{String(i + 1).padStart(2, "0")}</span>}
                          <span className={`truncate ${isFailed ? "line-through" : ""}`}>{s.name}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </details>
        )}

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* ─── Mode + Presets ─── */}
        <div className="space-y-5">
          <div className="flex items-center gap-5">
            <div className="inline-flex p-1 bg-surface-container-low rounded-lg">
              {([
                { id: "template" as Mode, label: "Template" },
                { id: "llm" as Mode, label: "LLM" },
                { id: "custom" as Mode, label: "Custom" },
              ]).map(m => (
                <button key={m.id}
                  onClick={() => { setMode(m.id); setSpec(""); setSelectedPreset(null); }}
                  className={`px-5 py-1.5 rounded-md text-sm font-medium transition-all ${
                    mode === m.id ? "bg-surface-container-highest text-primary" : "text-outline-variant hover:text-on-surface"
                  }`}>{m.label}</button>
              ))}
            </div>
            <span className="text-[10px] font-mono text-outline">
              {mode === "template" ? "Deterministic — fast, no LLM" : mode === "llm" ? "LLM-powered — preset + editable" : "Free-form — full control"}
            </span>
          </div>

          {mode !== "custom" && templates.length > 0 && (
            <div className="grid grid-cols-3 gap-3">
              {templates.map(t => (
                <button key={t.key} onClick={() => selectPreset(t.key)}
                  className={`p-4 rounded-xl text-left transition-all group ${
                    selectedPreset === t.key
                      ? "bg-surface-container-high border border-primary/30 shadow-lg shadow-blue-900/8"
                      : "bg-surface-container border border-transparent hover:bg-surface-container-high hover:border-outline-variant/10"
                  }`}>
                  <div className="flex items-start justify-between">
                    <span className="material-symbols-outlined text-primary text-lg">{t.icon}</span>
                    {selectedPreset === t.key && (
                      <span className="material-symbols-outlined text-primary text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>radio_button_checked</span>
                    )}
                  </div>
                  <h3 className="font-headline font-semibold text-on-surface text-sm mt-2 mb-0.5">{t.label}</h3>
                  <p className="text-[11px] text-outline leading-relaxed line-clamp-2">{t.description}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ═══════ Spec workspace ═══════ */}
        <div className="grid grid-cols-12 gap-6 items-start">

          {/* Left: Parameters (compact) */}
          <div className="col-span-3 space-y-4 sticky top-24">
            <div className="bg-surface-container rounded-xl border border-outline-variant/10 overflow-hidden">
              <div className="px-4 py-2.5 bg-surface-container-high/40 border-b border-outline-variant/5">
                <span className="font-mono text-[10px] text-slate-400 uppercase tracking-widest">Parameters</span>
              </div>
              <div className="p-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[9px] font-mono text-outline uppercase tracking-wider mb-1">Count</label>
                    <input type="number" value={count} onChange={e => setCount(Number(e.target.value))} min={1} max={500}
                      className="w-full bg-surface-container-lowest rounded-lg py-1.5 px-2.5 text-sm text-primary font-mono outline-none border-none focus:ring-1 focus:ring-primary" />
                  </div>
                  <div>
                    <label className="block text-[9px] font-mono text-outline uppercase tracking-wider mb-1">Activities</label>
                    <input type="number" value={maxActivities} onChange={e => setMaxActivities(Number(e.target.value))} min={1} max={100}
                      className="w-full bg-surface-container-lowest rounded-lg py-1.5 px-2.5 text-sm text-primary font-mono outline-none border-none focus:ring-1 focus:ring-primary" />
                  </div>
                </div>
                <div>
                  <label className="block text-[9px] font-mono text-outline uppercase tracking-wider mb-1">Difficulty</label>
                  <select value={difficulty} onChange={e => setDifficulty(e.target.value)}
                    className="w-full bg-surface-container-lowest rounded-lg py-1.5 px-2.5 text-sm text-on-surface outline-none border-none focus:ring-1 focus:ring-primary">
                    <option value="simple">Simple</option><option value="medium">Medium</option><option value="complex">Complex</option>
                  </select>
                </div>
                <div className="flex items-center justify-between">
                  <div><span className="text-[9px] font-mono text-outline uppercase tracking-wider">Test Data</span></div>
                  <button onClick={() => setGenerateTestData(!generateTestData)}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${generateTestData ? "bg-tertiary/60" : "bg-surface-container-highest"}`}>
                    <span className={`inline-block h-3 w-3 rounded-full bg-white transition-transform ${generateTestData ? "translate-x-5" : "translate-x-1"}`} />
                  </button>
                </div>
              </div>
            </div>

            {/* Quickstart button */}
            <button onClick={() => runGeneration(spec || undefined)} disabled={busy}
              className={`w-full py-2 rounded-lg text-xs font-mono transition-all flex items-center justify-center gap-2 ${
                busy ? "bg-surface-container-high text-slate-600 cursor-wait"
                     : "bg-surface-container text-outline hover:text-on-surface hover:bg-surface-container-high border border-outline-variant/10"
              }`}>
              <span className="material-symbols-outlined text-[16px]">bolt</span>
              Quickstart — skip spec
            </button>
          </div>

          {/* Right: Natural-language spec editor */}
          <div className="col-span-9">
            <div className="bg-[#060a13] rounded-xl overflow-hidden border border-outline-variant/10 shadow-2xl flex flex-col">
              {/* Chrome bar */}
              <div className="px-5 py-3 bg-surface-container/30 border-b border-outline-variant/5 flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <span className="material-symbols-outlined text-primary text-sm">description</span>
                  <span className="font-mono text-[10px] text-slate-400 uppercase tracking-widest">Generation Spec</span>
                  <span className="machined-chip border-tertiary text-tertiary px-2 py-0.5 rounded text-[9px] font-mono">natural language</span>
                </div>
                <div className="flex items-center gap-4">
                  {/* Generate Spec button (inline) */}
                  {mode !== "template" && (
                    <button onClick={handleGenerateSpec} disabled={busy}
                      className={`text-[10px] font-mono flex items-center gap-1 transition-all ${
                        busy ? "text-slate-600 cursor-wait" : "text-primary hover:text-primary-fixed"
                      }`}>
                      {specLoading
                        ? <div className="w-3 h-3 border border-primary/30 border-t-primary rounded-full animate-spin" />
                        : <span className="material-symbols-outlined text-[14px]">auto_fix_high</span>}
                      {specLoading ? "Generating..." : "Enrich with LLM"}
                    </button>
                  )}
                  <div className="flex gap-1.5">
                    <div className="w-2 h-2 rounded-full bg-red-500/20 border border-red-500/40" />
                    <div className="w-2 h-2 rounded-full bg-yellow-500/20 border border-yellow-500/40" />
                    <div className="w-2 h-2 rounded-full bg-green-500/20 border border-green-500/40" />
                  </div>
                </div>
              </div>

              {/* Spec textarea */}
              <div className="relative flex-1">
                {!hasSpec && !specLoading && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none gap-3 opacity-60">
                    <span className="material-symbols-outlined text-3xl text-slate-700">draft</span>
                    <p className="text-sm text-slate-600 font-body text-center leading-relaxed">
                      Select a preset to auto-populate,<br />or write your generation requirements
                    </p>
                  </div>
                )}
                <textarea value={spec} onChange={e => setSpec(e.target.value)} spellCheck={false}
                  placeholder="Describe the ADF pipelines you want to generate — activity types, expression patterns, complexity targets, naming conventions..."
                  className="w-full h-[340px] bg-transparent px-5 py-4 text-on-surface/90 font-body text-sm leading-relaxed resize-none outline-none placeholder:text-slate-700/60" />
              </div>

              {/* Footer with primary action */}
              <div className="px-5 py-3 border-t border-outline-variant/5 bg-surface-container/20 flex items-center justify-between">
                <span className="text-[10px] font-mono text-outline">
                  {hasSpec ? `${spec.split("\n").length} lines` : "empty"}
                </span>
                <button onClick={() => runGeneration()} disabled={busy || !hasSpec}
                  className={`px-8 py-2 rounded-lg font-bold text-sm flex items-center gap-2 transition-all ${
                    busy || !hasSpec
                      ? "bg-primary/15 text-slate-500 cursor-not-allowed"
                      : "bg-[#2d7ff9] text-white hover:bg-blue-600 shadow-lg shadow-blue-900/20"
                  }`}>
                  {generating
                    ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Generating...</>
                    : <><span className="material-symbols-outlined text-sm">rocket_launch</span> Generate Pipelines / Data</>}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ═══════ Results ═══════ */}
        {result && !generating && (
          <section id="synthetic-results" className="space-y-6" style={{ animation: "fade-in-up 0.35s ease both" }}>
            {result.fallback_note && (
              <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/30">
                <span className="material-symbols-outlined text-amber-500 text-lg mt-0.5 shrink-0">warning</span>
                <p className="text-sm text-amber-200 leading-relaxed">{result.fallback_note}</p>
              </div>)}

            {result.output_path && (
              <div className="flex items-center gap-4 p-4 rounded-xl bg-surface-container border border-outline-variant/10">
                <span className="material-symbols-outlined text-tertiary">save</span>
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] font-mono text-outline uppercase tracking-wider mb-0.5">Persisted to disk</p>
                  <p className="text-sm font-mono text-on-surface truncate" title={result.output_path}>{result.output_path}</p>
                </div>
                <button onClick={() => navigator.clipboard.writeText(result.output_path!)}
                  className="px-3 py-1.5 rounded-lg bg-surface-container-high text-xs font-mono text-primary hover:bg-surface-container-highest transition-colors flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm">content_copy</span> Copy
                </button>
                <button onClick={() => {
                  setPendingBatchFolder(result.output_path!);
                  window.location.hash = "#/batch";
                }}
                  className="px-4 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-mono font-bold hover:bg-primary/20 transition-colors flex items-center gap-1.5 border border-primary/20">
                  <span className="material-symbols-outlined text-sm">monitoring</span> Run Batch Validation
                </button>
                <button onClick={() => navigator.clipboard.writeText(
                  `curl -X POST http://localhost:8000/api/adf/upload -H 'Content-Type: application/json' -d '{"tenant_id":"...","client_id":"...","client_secret":"...","subscription_id":"...","resource_group":"...","factory_name":"...","folder_path":"${result.output_path}"}'`
                )} title="Copy upload command"
                  className="px-4 py-1.5 rounded-lg bg-surface-container-high text-outline text-xs font-mono hover:text-on-surface hover:bg-surface-container-highest transition-colors flex items-center gap-1.5 border border-outline-variant/10">
                  <span className="material-symbols-outlined text-sm">cloud_upload</span> Copy Upload to ADF Command
                </button>
              </div>)}

            <div className="flex gap-8 border-b border-outline-variant/20">
              <button onClick={() => setResultTab("pipelines")}
                className={`pb-3 text-sm font-semibold transition-colors ${resultTab === "pipelines" ? "text-primary border-b-2 border-primary" : "text-outline hover:text-on-surface"}`}>
                Pipelines ({result.count})
              </button>
              {result.test_data && result.test_data.length > 0 && (
                <button onClick={() => setResultTab("testdata")}
                  className={`pb-3 text-sm font-semibold transition-colors ${resultTab === "testdata" ? "text-primary border-b-2 border-primary" : "text-outline hover:text-on-surface"}`}>
                  Test Data ({result.test_data.length})
                </button>)}
            </div>

            {resultTab === "pipelines" && (
              <div className="bg-surface-container rounded-xl overflow-hidden border border-outline-variant/10 shadow-xl">
                <table className="w-full text-left">
                  <thead className="bg-surface-container-high text-[10px] font-mono text-outline uppercase tracking-wider">
                    <tr><th className="px-6 py-3 w-14">#</th><th className="px-6 py-3">Pipeline</th><th className="px-6 py-3 w-24">Difficulty</th><th className="px-6 py-3 w-36 text-right">Action</th></tr>
                  </thead>
                  <tbody>
                    {result.pipelines.map((pl, i) => {
                      const open = selectedPipeline === i;
                      return (
                        <React.Fragment key={i}>
                          <tr onClick={() => setSelectedPipeline(open ? null : i)}
                            className={`border-t border-outline-variant/10 cursor-pointer transition-colors ${open ? "bg-primary/5" : "hover:bg-surface-container-low/30"}`}>
                            <td className="px-6 py-2.5 text-[10px] font-mono text-outline">{String(i + 1).padStart(3, "0")}</td>
                            <td className="px-6 py-2.5">
                              <p className="text-sm font-mono text-on-surface">{pl.name}</p>
                              <p className="text-[11px] text-outline mt-0.5 truncate max-w-md">{pl.description}</p>
                            </td>
                            <td className="px-6 py-2.5">
                              <span className={`inline-block px-2 py-0.5 rounded text-[9px] font-mono font-bold uppercase ${
                                pl.difficulty === "simple" ? "bg-tertiary/10 text-tertiary" : pl.difficulty === "complex" || pl.difficulty === "llm" ? "bg-error/10 text-error" : "bg-primary/10 text-primary"
                              }`}>{pl.difficulty}</span>
                            </td>
                            <td className="px-6 py-2.5 text-right">
                              <button onClick={e => { e.stopPropagation(); openInValidator(pl); }}
                                className="inline-flex items-center gap-1 text-primary text-xs font-mono hover:underline">
                                Validate <span className="material-symbols-outlined text-sm">arrow_forward</span>
                              </button>
                            </td>
                          </tr>
                          {open && (
                            <tr><td colSpan={4} className="px-6 py-4 bg-base border-t border-outline-variant/10">
                              <pre className="font-mono text-xs text-primary/80 max-h-[280px] overflow-auto rounded-lg bg-[#060a13] p-4 border border-outline-variant/5">
                                {JSON.stringify(pl.adf_json, null, 2)}
                              </pre>
                            </td></tr>)}
                        </React.Fragment>);
                    })}
                  </tbody>
                </table>
              </div>)}

            {resultTab === "testdata" && result.test_data && (
              <div className="space-y-4">
                {result.test_data.map((td, i) => (
                  <div key={i} className="bg-surface-container rounded-xl overflow-hidden border border-outline-variant/10">
                    <div className="px-6 py-3 bg-surface-container-high/20 border-b border-outline-variant/10 flex items-center gap-3">
                      <span className="material-symbols-outlined text-primary text-sm">storage</span>
                      <span className="font-mono text-sm text-on-surface font-medium">{td.pipeline_name}</span>
                    </div>
                    {Object.entries(td.source_files).map(([path, content]) => (
                      <div key={path} className="px-6 py-3 border-b border-outline-variant/5">
                        <div className="flex items-center gap-2 mb-1.5"><span className="material-symbols-outlined text-tertiary text-sm">description</span><span className="text-xs font-mono text-on-surface">{path}</span></div>
                        <pre className="text-[11px] font-mono text-on-surface/60 max-h-[100px] overflow-auto bg-surface-container-lowest rounded-lg p-3">{content.slice(0, 500)}{content.length > 500 ? "\n..." : ""}</pre>
                      </div>))}
                    {td.seed_sql.length > 0 && (
                      <div className="px-6 py-3 border-b border-outline-variant/5">
                        <pre className="text-[11px] font-mono text-primary/70 max-h-[100px] overflow-auto bg-surface-container-lowest rounded-lg p-3">{td.seed_sql.join("\n")}</pre>
                      </div>)}
                    <div className="px-6 py-3"><p className="text-xs text-outline leading-relaxed whitespace-pre-line">{td.setup_instructions}</p></div>
                  </div>))}
              </div>)}
          </section>)}
      </div>
    </>
  );
}
