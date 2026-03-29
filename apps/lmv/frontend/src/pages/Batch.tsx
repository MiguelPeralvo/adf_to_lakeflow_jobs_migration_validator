import React, { useState, useEffect } from "react";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";
import { consumePendingBatchFolder } from "../store";

interface DimResult { score: number; passed: boolean; details?: Record<string, unknown> }
interface AgentDiagnosis { dimension: string; score: number; diagnosis: string }
interface CaseResult {
  pipeline_name: string;
  file?: string;
  score: number;
  label: string;
  ccs_below_threshold: boolean;
  dimensions?: Record<string, DimResult>;
  agent_analysis?: AgentDiagnosis[];
}
interface BatchReport {
  total: number;
  threshold: number;
  mean_score: number;
  min_score: number;
  max_score: number;
  below_threshold: number;
  cases: CaseResult[];
}

type SourceMode = "folder" | "golden_set";

function scoreColor(s: number): string {
  if (s >= 90) return "#27e199";
  if (s >= 70) return "#adc6ff";
  return "#ffb4ab";
}

const DIM_LABELS: Record<string, { label: string; icon: string }> = {
  activity_coverage:       { label: "Activity Coverage",      icon: "widgets" },
  expression_coverage:     { label: "Expression Coverage",    icon: "function" },
  dependency_preservation: { label: "Dependency Preservation",icon: "account_tree" },
  notebook_validity:       { label: "Notebook Validity",      icon: "code" },
  parameter_completeness:  { label: "Parameter Completeness", icon: "tune" },
  secret_completeness:     { label: "Secret Completeness",    icon: "key" },
  not_translatable_ratio:  { label: "Translatable Ratio",     icon: "warning" },
  control_flow_fidelity:   { label: "Control Flow Fidelity",  icon: "alt_route" },
};

export function BatchPage() {
  const [sourceMode, setSourceMode] = useState<SourceMode>("folder");
  const [folderPath, setFolderPath] = useState("");
  const [goldenSetPath, setGoldenSetPath] = useState("golden_sets/pipelines.json");
  const [globPattern, setGlobPattern] = useState("*.json");
  const [threshold, setThreshold] = useState(90);
  const [report, setReport] = useState<BatchReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  // Streaming progress
  const [progressCompleted, setProgressCompleted] = useState(0);
  const [progressTotal, setProgressTotal] = useState(0);
  const [lastPipeline, setLastPipeline] = useState<string | null>(null);
  const [lastScore, setLastScore] = useState<number | null>(null);
  const [agentAnalysis, setAgentAnalysis] = useState(false);
  const [analyzingPipeline, setAnalyzingPipeline] = useState<string | null>(null);
  const [analyzingDimension, setAnalyzingDimension] = useState<string | null>(null);
  const [liveAnalyses, setLiveAnalyses] = useState<Record<string, AgentDiagnosis[]>>({});

  // wkmigrate config
  const [repos, setRepos] = useState<Array<{ url: string; default_branch: string }>>([]);
  const [activeRepo, setActiveRepo] = useState("");
  const [activeBranch, setActiveBranch] = useState("");
  const [branches, setBranches] = useState<Array<{ name: string; sha: string }>>([]);
  const [branchesLoading, setBranchesLoading] = useState(false);
  const [showConfig, setShowConfig] = useState(false);

  // Past synthetic runs
  const [syntheticRuns, setSyntheticRuns] = useState<Array<{ path: string; name: string; pipeline_count: number }>>([]);

  // Load config + runs + check pending folder
  useEffect(() => {
    fetch("/api/config/wkmigrate").then(r => r.json()).then(cfg => {
      setRepos(cfg.repos || []);
      setActiveRepo(cfg.active_repo || "");
      setActiveBranch(cfg.active_branch || "");
    }).catch(() => {});
    fetch("/api/synthetic/runs").then(r => r.json()).then(setSyntheticRuns).catch(() => {});
    const pending = consumePendingBatchFolder();
    if (pending) {
      setFolderPath(pending);
      setSourceMode("folder");
    }
  }, []);

  // Fetch branches when repo changes
  useEffect(() => {
    if (!activeRepo) return;
    setBranchesLoading(true);
    fetch(`/api/config/wkmigrate/branches?repo_url=${encodeURIComponent(activeRepo)}`)
      .then(r => r.json()).then(setBranches).catch(() => setBranches([]))
      .finally(() => setBranchesLoading(false));
  }, [activeRepo]);

  function saveConfig() {
    fetch("/api/config/wkmigrate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active_repo: activeRepo, active_branch: activeBranch }),
    }).catch(() => {});
  }

  async function handleRun() {
    setError(null); setReport(null); setLoading(true);
    setProgressCompleted(0); setProgressTotal(0); setLastPipeline(null); setLastScore(null);
    setExpandedRow(null); setAnalyzingPipeline(null); setAnalyzingDimension(null); setLiveAnalyses({});
    try {
      if (sourceMode === "folder") {
        if (!folderPath.trim()) throw new Error("Enter a folder path");
        const res = await fetch("/api/validate/folder?stream=true", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ folder_path: folderPath, threshold, glob_pattern: globPattern, agent_analysis: agentAnalysis }),
        });
        if (!res.ok) { const err = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(err.detail || `HTTP ${res.status}`); }
        const reader = res.body!.getReader(); const decoder = new TextDecoder();
        let buffer = "", finalReport: BatchReport | null = null;
        while (true) {
          const { done, value } = await reader.read(); if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n"); buffer = lines.pop()!;
          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const ev = JSON.parse(line);
              if (ev.type === "progress") { setProgressCompleted(ev.completed); setProgressTotal(ev.total); setLastPipeline(ev.pipeline_name); setLastScore(ev.score); setAnalyzingPipeline(null); setAnalyzingDimension(null); }
              else if (ev.type === "analysis_start") { setAnalyzingPipeline(ev.pipeline_name); setAnalyzingDimension(null); }
              else if (ev.type === "analysis") { setAnalyzingDimension(ev.dimension); setLiveAnalyses(prev => ({ ...prev, [ev.pipeline_name]: [...(prev[ev.pipeline_name] || []), { dimension: ev.dimension, score: ev.score, diagnosis: ev.diagnosis }] })); }
              else if (ev.type === "complete") { finalReport = ev.result; setAnalyzingPipeline(null); }
            } catch {}
          }
        }
        if (finalReport) setReport(finalReport); else throw new Error("Stream ended without results");
      } else {
        const res = await fetch("/api/validate/batch", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pipelines_path: goldenSetPath, threshold }),
        });
        if (!res.ok) { const err = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(err.detail || `HTTP ${res.status}`); }
        setReport(await res.json());
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Batch validation failed"); }
    finally { setLoading(false); }
  }

  const pct = progressTotal > 0 ? (progressCompleted / progressTotal) * 100 : 0;

  return (
    <>
      <TopHeader title="Batch Validation" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-7xl">
        {/* Header */}
        <div className="flex justify-between items-end">
          <div>
            <h2 className="text-4xl font-headline font-bold text-on-surface tracking-tight">
              Batch Validation &amp; Regression
            </h2>
            <p className="text-slate-500 font-body mt-2 max-w-xl">
              Validate all ADF pipelines in a folder through wkmigrate translation. Each pipeline is translated to Databricks and scored across 8 quality dimensions.
            </p>
          </div>
          <button onClick={handleRun} disabled={loading}
            className="bg-gradient-to-br from-primary to-primary-container hover:opacity-90 active:scale-[0.98] transition-all text-on-primary-container px-6 py-2.5 rounded-lg font-headline font-bold flex items-center gap-2 shadow-lg shadow-primary/10">
            <span className="material-symbols-outlined text-sm">play_arrow</span>
            {loading ? "Validating..." : "Run Batch Validation"}
          </button>
        </div>

        {/* Source config */}
        <div className="bg-surface-container rounded-xl border border-outline-variant/10 overflow-hidden">
          <div className="flex border-b border-outline-variant/10">
            <button onClick={() => setSourceMode("folder")}
              className={`flex-1 px-6 py-3 text-sm font-medium transition-colors ${sourceMode === "folder" ? "text-primary border-b-2 border-primary bg-surface-container-high/30" : "text-outline hover:text-on-surface"}`}>
              <span className="material-symbols-outlined text-sm align-middle mr-1.5">folder_open</span>
              ADF Pipeline Folder
            </button>
            <button onClick={() => setSourceMode("golden_set")}
              className={`flex-1 px-6 py-3 text-sm font-medium transition-colors ${sourceMode === "golden_set" ? "text-primary border-b-2 border-primary bg-surface-container-high/30" : "text-outline hover:text-on-surface"}`}>
              <span className="material-symbols-outlined text-sm align-middle mr-1.5">verified</span>
              Golden Set JSON
            </button>
          </div>
          <div className="p-6 flex gap-6 items-end">
            {sourceMode === "folder" ? (<>
              <div className="flex-1">
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 font-mono">Folder Path</label>
                <input value={folderPath} onChange={(e) => setFolderPath(e.target.value)} placeholder="/path/to/adf_pipelines/"
                  className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 px-4 text-slate-100 font-mono text-sm outline-none focus:border-primary transition-all" />
              </div>
              <div className="w-36">
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 font-mono">Pattern</label>
                <input value={globPattern} onChange={(e) => setGlobPattern(e.target.value)}
                  className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 px-4 text-slate-100 font-mono text-sm outline-none focus:border-primary transition-all" />
              </div>
            </>) : (
              <div className="flex-1">
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 font-mono">Golden Set Path</label>
                <input value={goldenSetPath} onChange={(e) => setGoldenSetPath(e.target.value)}
                  className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 px-4 text-slate-100 font-mono text-sm outline-none focus:border-primary transition-all" />
              </div>
            )}
            <div className="w-28">
              <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 font-mono">Threshold</label>
              <input type="number" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))}
                className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 px-4 text-slate-100 font-mono text-sm outline-none focus:border-primary transition-all" />
            </div>
            <div className="flex items-center gap-3 pb-1">
              <div className="text-right">
                <span className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest font-mono">Agent Analysis</span>
                <span className="block text-[9px] text-outline">LLM diagnoses failures</span>
              </div>
              <button onClick={() => setAgentAnalysis(!agentAnalysis)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${agentAnalysis ? "bg-primary-container" : "bg-surface-container-highest"}`}>
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${agentAnalysis ? "translate-x-6" : "translate-x-1"}`} />
              </button>
            </div>
          </div>
        </div>

        {/* Past synthetic runs — quick pick */}
        {sourceMode === "folder" && syntheticRuns.length > 0 && (
          <div className="bg-surface-container rounded-xl border border-outline-variant/10 overflow-hidden">
            <details>
              <summary className="px-5 py-3 cursor-pointer text-sm font-mono text-on-surface-variant hover:text-on-surface flex items-center gap-2 select-none">
                <span className="material-symbols-outlined text-primary text-sm">history</span>
                Recent Synthetic Runs ({syntheticRuns.length}) — click to pick
              </summary>
              <div className="px-5 pb-3 flex flex-wrap gap-2">
                {syntheticRuns.slice(0, 10).map(run => (
                  <button key={run.path} onClick={() => setFolderPath(run.path)}
                    className={`px-3 py-1.5 rounded-lg text-[10px] font-mono transition-all flex items-center gap-1.5 ${
                      folderPath === run.path
                        ? "bg-primary/10 text-primary border border-primary/20"
                        : "bg-surface-container-high text-outline hover:text-on-surface border border-transparent"
                    }`}>
                    <span className="material-symbols-outlined text-[12px]">folder</span>
                    {run.name}
                    <span className="text-outline/50">({run.pipeline_count})</span>
                  </button>
                ))}
              </div>
            </details>
          </div>
        )}

        {/* wkmigrate config */}
        <div className="bg-surface-container rounded-xl border border-outline-variant/10 overflow-hidden">
          <button onClick={() => setShowConfig(!showConfig)}
            className="w-full px-5 py-3 text-left text-sm font-mono text-on-surface-variant hover:text-on-surface flex items-center justify-between select-none">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-sm">settings</span>
              <span>wkmigrate: <span className="text-on-surface">{activeRepo.split("/").pop()}</span> @ <span className="text-primary">{activeBranch}</span></span>
            </div>
            <span className={`material-symbols-outlined text-sm transition-transform ${showConfig ? "rotate-180" : ""}`}>expand_more</span>
          </button>
          {showConfig && (
            <div className="px-5 pb-4 pt-1 border-t border-outline-variant/5 space-y-3">
              <div>
                <label className="block text-[9px] font-mono text-outline uppercase tracking-wider mb-1">Repository</label>
                <select value={activeRepo} onChange={e => { setActiveRepo(e.target.value); const r = repos.find(r => r.url === e.target.value); if (r) setActiveBranch(r.default_branch); }}
                  className="w-full bg-surface-container-lowest rounded-lg py-2 px-3 text-sm text-on-surface font-mono outline-none border-none focus:ring-1 focus:ring-primary">
                  {repos.map(r => <option key={r.url} value={r.url}>{r.url.replace("https://github.com/", "")}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[9px] font-mono text-outline uppercase tracking-wider mb-1">
                  Branch {branchesLoading && <span className="text-primary">(loading...)</span>}
                </label>
                <select value={activeBranch} onChange={e => setActiveBranch(e.target.value)}
                  className="w-full bg-surface-container-lowest rounded-lg py-2 px-3 text-sm text-on-surface font-mono outline-none border-none focus:ring-1 focus:ring-primary">
                  {branches.map(b => (
                    <option key={b.name} value={b.name}>{b.name} ({b.sha})</option>
                  ))}
                  {branches.length === 0 && <option value={activeBranch}>{activeBranch}</option>}
                </select>
              </div>
              <div className="flex items-center justify-between pt-1">
                <p className="text-[10px] text-outline">Changing repo/branch requires server restart to take effect.</p>
                <button onClick={saveConfig}
                  className="px-3 py-1 rounded-lg bg-primary/10 text-primary text-xs font-mono font-bold hover:bg-primary/20 transition-colors border border-primary/20">
                  Save Config
                </button>
              </div>
            </div>
          )}
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Progress */}
        {loading && progressTotal > 0 && (
          <div className="rounded-xl overflow-hidden bg-surface-container border border-primary/20">
            <div className="h-1.5 bg-surface-container-highest">
              <div className="h-full bg-primary transition-all duration-500 ease-out" style={{ width: `${pct}%` }} />
            </div>
            <div className="px-5 py-3 flex items-center gap-4">
              <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-mono text-on-surface">
                  {analyzingPipeline ? (
                    <><span className="text-primary font-semibold">Analyzing</span> {analyzingPipeline}{analyzingDimension && <span className="text-outline"> — {analyzingDimension}</span>}</>
                  ) : (
                    <>Validating <span className="text-primary font-bold">{progressCompleted}</span><span className="text-outline">/{progressTotal}</span>
                    {lastPipeline && <span className="text-outline ml-2">— <span className="text-on-surface-variant">{lastPipeline}</span></span>}
                    {lastScore != null && <span className="ml-2 font-bold" style={{ color: scoreColor(lastScore) }}>{Math.round(lastScore)}%</span>}</>
                  )}
                </p>
              </div>
              <span className="text-xs font-mono text-outline">{Math.round(pct)}%</span>
            </div>
          </div>
        )}
        {loading && progressTotal === 0 && (
          <div className="bg-surface-container rounded-xl p-8 flex flex-col items-center gap-4">
            <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-sm font-mono text-outline">Loading pipelines...</span>
          </div>
        )}

        {/* Report */}
        {report && !loading && (<>
          {/* Summary cards */}
          <div className="grid grid-cols-4 gap-5">
            {[
              { label: "Pipelines", value: report.total, icon: "account_tree" },
              { label: "Mean CCS", value: `${Math.round(report.mean_score)}%`, icon: "speed", color: scoreColor(report.mean_score) },
              { label: "Min CCS", value: Math.round(report.min_score), icon: "trending_down", color: scoreColor(report.min_score) },
              { label: "Below Threshold", value: report.below_threshold, icon: "error", color: report.below_threshold > 0 ? "#ffb4ab" : "#27e199" },
            ].map((card, i) => (
              <div key={i} className="bg-surface-container p-5 rounded-xl border border-outline-variant/10">
                <div className="flex items-center gap-2 mb-2">
                  <span className="material-symbols-outlined text-outline text-sm">{card.icon}</span>
                  <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">{card.label}</span>
                </div>
                <span className="text-3xl font-headline font-bold tracking-tight" style={{ color: card.color ?? "var(--color-on-surface)" }}>
                  {card.value}
                </span>
              </div>
            ))}
          </div>

          {/* Distribution */}
          {report.cases.length > 1 && (() => {
            const bands = [
              { label: "High Confidence (90-100)", color: "tertiary", count: report.cases.filter(c => c.score >= 90).length },
              { label: "Review Recommended (70-89)", color: "primary", count: report.cases.filter(c => c.score >= 70 && c.score < 90).length },
              { label: "Manual Intervention (< 70)", color: "error", count: report.cases.filter(c => c.score < 70).length },
            ];
            return (
              <div className="bg-surface-container rounded-xl p-6 border border-outline-variant/10">
                <h3 className="text-sm font-headline font-semibold text-on-surface mb-4">Score Distribution</h3>
                <div className="flex gap-1 h-8 rounded-lg overflow-hidden">
                  {bands.map(b => b.count > 0 && (
                    <div key={b.label} className={`bg-${b.color}/70 flex items-center justify-center transition-all`}
                      style={{ width: `${(b.count / report.cases.length) * 100}%` }}
                      title={`${b.label}: ${b.count}`}>
                      <span className="text-[10px] font-mono font-bold text-white/90">{b.count}</span>
                    </div>
                  ))}
                </div>
                <div className="flex gap-6 mt-3">
                  {bands.map(b => (
                    <div key={b.label} className="flex items-center gap-1.5">
                      <div className={`w-2 h-2 rounded-full bg-${b.color}`} />
                      <span className="text-[10px] font-mono text-outline">{b.label}: {b.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Results table with expandable dimensions */}
          <div className="bg-surface-container rounded-xl overflow-hidden border border-outline-variant/10">
            <div className="px-6 py-4 border-b border-outline-variant/10 bg-surface-container-high/30 flex justify-between items-center">
              <h3 className="text-sm font-headline font-semibold text-on-surface">Pipeline Results</h3>
              <span className="text-[10px] font-mono text-outline">{report.cases.length} pipelines — click to expand</span>
            </div>
            <table className="w-full text-left">
              <thead className="text-[9px] font-mono text-outline uppercase tracking-wider bg-surface-container-low/30">
                <tr>
                  <th className="px-6 py-3 w-10"></th>
                  <th className="px-3 py-3">Pipeline</th>
                  {sourceMode === "folder" && <th className="px-3 py-3">File</th>}
                  <th className="px-3 py-3 text-right w-20">CCS</th>
                  <th className="px-3 py-3 text-center w-28">Status</th>
                </tr>
              </thead>
              <tbody>
                {report.cases.map((c, i) => {
                  const isOpen = expandedRow === i;
                  const dims = c.dimensions || {};
                  const failedDims = Object.entries(dims).filter(([, d]) => !d.passed);
                  return (
                    <React.Fragment key={i}>
                      <tr onClick={() => setExpandedRow(isOpen ? null : i)}
                        className={`border-t border-outline-variant/5 cursor-pointer transition-colors ${isOpen ? "bg-primary/5" : "hover:bg-surface-container-low/30"}`}>
                        <td className="px-6 py-3 text-center">
                          <span className={`material-symbols-outlined text-sm transition-transform ${isOpen ? "rotate-90" : ""}`}>chevron_right</span>
                        </td>
                        <td className="px-3 py-3">
                          <p className="text-sm font-mono text-on-surface">{c.pipeline_name}</p>
                          {failedDims.length > 0 && !isOpen && (
                            <p className="text-[10px] text-error/70 mt-0.5">
                              {failedDims.length} dimension{failedDims.length > 1 ? "s" : ""} failing
                            </p>
                          )}
                        </td>
                        {sourceMode === "folder" && (
                          <td className="px-3 py-3 text-xs font-mono text-outline truncate max-w-[180px]" title={c.file}>{c.file?.split("/").pop()}</td>
                        )}
                        <td className="px-3 py-3 text-right">
                          <span className="font-mono font-bold text-lg" style={{ color: scoreColor(c.score) }}>{Math.round(c.score)}</span>
                        </td>
                        <td className="px-3 py-3 text-center">
                          {c.label === "ERROR" ? (
                            <span className="machined-chip border-amber-500/50 text-amber-400 px-2 py-0.5 text-[9px] font-bold uppercase rounded-r">ERROR</span>
                          ) : c.ccs_below_threshold ? (
                            <span className="machined-chip border-error/50 text-error px-2 py-0.5 text-[9px] font-bold uppercase rounded-r">BELOW {threshold}</span>
                          ) : (
                            <span className="machined-chip border-tertiary/50 text-tertiary px-2 py-0.5 text-[9px] font-bold uppercase rounded-r">PASS</span>
                          )}
                        </td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={sourceMode === "folder" ? 5 : 4} className="px-6 py-4 bg-base border-t border-outline-variant/5">
                            {Object.keys(dims).length > 0 ? (
                              <div className="grid grid-cols-2 gap-3">
                                {Object.entries(dims).map(([key, dim]) => {
                                  const info = DIM_LABELS[key] || { label: key, icon: "help" };
                                  const details = dim.details || {};
                                  return (
                                    <div key={key} className={`rounded-lg p-3 border ${dim.passed ? "bg-surface-container border-outline-variant/10" : "bg-error/5 border-error/20"}`}>
                                      <div className="flex items-center justify-between mb-2">
                                        <div className="flex items-center gap-2">
                                          <span className={`material-symbols-outlined text-sm ${dim.passed ? "text-tertiary" : "text-error"}`}>{info.icon}</span>
                                          <span className="text-xs font-medium text-on-surface">{info.label}</span>
                                        </div>
                                        <div className="flex items-center gap-2">
                                          <span className={`text-sm font-mono font-bold ${dim.passed ? "text-tertiary" : "text-error"}`}>
                                            {(dim.score * 100).toFixed(0)}%
                                          </span>
                                          <span className={`material-symbols-outlined text-sm ${dim.passed ? "text-tertiary" : "text-error"}`}
                                            style={{ fontVariationSettings: "'FILL' 1" }}>
                                            {dim.passed ? "check_circle" : "cancel"}
                                          </span>
                                        </div>
                                      </div>
                                      {/* Dimension-specific details */}
                                      {!dim.passed && (
                                        <div className="text-[10px] font-mono text-on-surface/60 space-y-0.5 mt-1 pl-6">
                                          {details.total != null && details.preserved != null && (
                                            <p>Preserved: {String(details.preserved)}/{String(details.total)}</p>
                                          )}
                                          {details.total != null && details.covered != null && (
                                            <p>Covered: {String(details.covered)}/{String(details.total)}</p>
                                          )}
                                          {Array.isArray(details.placeholders) && details.placeholders.length > 0 && (
                                            <p>Placeholders: {(details.placeholders as string[]).join(", ")}</p>
                                          )}
                                          {Array.isArray(details.missing) && details.missing.length > 0 && (
                                            <p>Missing: {(details.missing as string[]).join(", ")}</p>
                                          )}
                                          {Array.isArray(details.errors) && details.errors.length > 0 && (
                                            <p>Errors: {(details.errors as string[]).slice(0, 3).join("; ")}</p>
                                          )}
                                          {Array.isArray(details.unsupported) && details.unsupported.length > 0 && (
                                            <p>Unsupported: {(details.unsupported as string[]).join(", ")}</p>
                                          )}
                                          {details.defined != null && Array.isArray(details.missing) && (
                                            <p>Defined: {Array.isArray(details.defined) ? (details.defined as string[]).join(", ") || "none" : String(details.defined)}</p>
                                          )}
                                        </div>
                                      )}
                                      {dim.passed && (
                                        <div className="text-[10px] font-mono text-outline pl-6">
                                          {details.total != null ? `${String(details.total)} checked — all OK` : "Passed"}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <p className="text-sm text-outline font-mono">No dimension details available for this pipeline.</p>
                            )}
                            {/* Agent analysis */}
                            {(() => {
                              const analyses = c.agent_analysis || liveAnalyses[c.pipeline_name];
                              if (!analyses || analyses.length === 0) return null;
                              return (
                                <div className="mt-4 space-y-3">
                                  <div className="flex items-center gap-2">
                                    <span className="material-symbols-outlined text-primary text-sm">psychology</span>
                                    <h4 className="text-xs font-headline font-semibold text-on-surface uppercase tracking-wider">Agent Diagnosis</h4>
                                  </div>
                                  {analyses.map((a: AgentDiagnosis, ai: number) => (
                                    <div key={ai} className="rounded-lg border border-primary/15 bg-primary/3 p-3">
                                      <div className="flex items-center gap-2 mb-2">
                                        <span className="material-symbols-outlined text-error text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>cancel</span>
                                        <span className="text-xs font-mono font-bold text-on-surface">
                                          {(DIM_LABELS[a.dimension] || { label: a.dimension }).label}
                                        </span>
                                        <span className="text-xs font-mono text-error">{(a.score * 100).toFixed(0)}%</span>
                                      </div>
                                      <p className="text-xs text-on-surface/80 leading-relaxed whitespace-pre-line pl-6">
                                        {a.diagnosis || "Analysis pending..."}
                                      </p>
                                    </div>
                                  ))}
                                </div>
                              );
                            })()}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>)}
      </div>
    </>
  );
}
