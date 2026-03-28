import React, { useState } from "react";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingOverlay } from "../components/LoadingOverlay";

interface GenerateResult {
  count: number;
  pipelines: string[];
  output_path: string | null;
}

function difficultyStyle(d: string): { bg: string; border: string; text: string } {
  switch (d) {
    case "complex": return { bg: "bg-error/10", border: "border-error", text: "text-error" };
    case "medium": return { bg: "bg-primary/10", border: "border-primary", text: "text-primary" };
    default: return { bg: "bg-tertiary/10", border: "border-tertiary", text: "text-tertiary" };
  }
}

export function SyntheticPage() {
  const [count, setCount] = useState(50);
  const [difficulty, setDifficulty] = useState("medium");
  const [complexity, setComplexity] = useState("mixed");
  const [maxActivities, setMaxActivities] = useState(20);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [selectedPipeline, setSelectedPipeline] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const res = await fetch("/api/synthetic/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          count,
          difficulty,
          expression_complexity: complexity,
          max_activities: maxActivities,
          mode: "template",
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      setResult(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <TopHeader title="Synthetic Engine" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-7xl">
        {/* Page Header */}
        <section>
          <h2 className="text-3xl font-bold font-headline text-on-surface mb-2">
            Synthetic Pipeline Generator
          </h2>
          <p className="text-on-surface-variant max-w-2xl font-body">
            Initialize automated test suites with precisely calibrated complexity metrics.
            Generated assets are compatible with Lakeflow version 2.4 and higher.
          </p>
        </section>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Configuration Panel (Bento-style Grid) */}
        <section className="bg-surface-container rounded-xl p-8 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {/* Column Left */}
            <div className="space-y-6">
              <div className="space-y-2">
                <label className="text-xs font-headline font-bold text-primary uppercase tracking-widest">Pipeline Count</label>
                <div className="bg-surface-container-lowest p-4 rounded-lg flex items-center justify-between">
                  <span className="font-mono text-xl text-primary">{count}</span>
                  <div className="flex flex-col gap-1">
                    <button
                      onClick={() => setCount(c => Math.min(500, c + 10))}
                      className="material-symbols-outlined text-slate-500 hover:text-primary transition-colors text-sm"
                    >expand_less</button>
                    <button
                      onClick={() => setCount(c => Math.max(1, c - 10))}
                      className="material-symbols-outlined text-slate-500 hover:text-primary transition-colors text-sm"
                    >expand_more</button>
                  </div>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-headline font-bold text-primary uppercase tracking-widest">Difficulty Profile</label>
                <select
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value)}
                  className="w-full bg-surface-container-lowest border-none text-on-surface rounded-lg py-4 px-4 focus:ring-1 focus:ring-primary font-body"
                >
                  <option value="simple">simple</option>
                  <option value="medium">medium</option>
                  <option value="complex">complex</option>
                </select>
              </div>
            </div>
            {/* Column Right */}
            <div className="space-y-6">
              <div className="space-y-2">
                <label className="text-xs font-headline font-bold text-primary uppercase tracking-widest">Expression Complexity</label>
                <select
                  value={complexity}
                  onChange={(e) => setComplexity(e.target.value)}
                  className="w-full bg-surface-container-lowest border-none text-on-surface rounded-lg py-4 px-4 focus:ring-1 focus:ring-primary font-body"
                >
                  <option value="simple">simple</option>
                  <option value="nested">nested</option>
                  <option value="mixed">mixed</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-headline font-bold text-primary uppercase tracking-widest">Max Activities</label>
                <input
                  type="number"
                  value={maxActivities}
                  onChange={(e) => setMaxActivities(Number(e.target.value))}
                  className="w-full bg-surface-container-lowest border-none text-on-surface rounded-lg py-4 px-4 focus:ring-1 focus:ring-primary font-mono text-lg"
                />
              </div>
            </div>
          </div>
          <div className="mt-8">
            <button
              onClick={handleGenerate}
              disabled={loading}
              className={`w-full md:w-auto px-12 py-4 rounded-lg font-bold font-headline uppercase tracking-widest transition-all active:scale-95 ${
                loading
                  ? "bg-primary/30 text-slate-400 cursor-wait"
                  : "bg-gradient-to-br from-primary to-primary-container text-on-primary hover:shadow-xl hover:shadow-primary/20 shadow-lg shadow-primary/10"
              }`}
            >
              {loading ? "Generating..." : "Generate Suite"}
            </button>
          </div>
        </section>

        {loading && (
          <div className="bg-surface-container rounded-xl p-8">
            <LoadingOverlay message="Generating synthetic pipelines..." />
          </div>
        )}

        {result && !loading && (
          <>
            {/* Results Summary */}
            <section className="space-y-6">
              <div className="flex justify-between items-end">
                <div className="flex items-center gap-6">
                  <div className="bg-surface-container-high px-4 py-2 rounded-lg border-l-4 border-tertiary">
                    <p className="text-[10px] text-slate-500 font-headline uppercase font-bold">Total Generated</p>
                    <p className="font-mono text-xl text-tertiary">{result.count}</p>
                  </div>
                  {result.output_path && (
                    <div className="bg-surface-container-high px-4 py-2 rounded-lg">
                      <p className="text-[10px] text-slate-500 font-headline uppercase font-bold">Output Path</p>
                      <p className="font-mono text-sm text-slate-300">{result.output_path}</p>
                    </div>
                  )}
                </div>
                <button className="text-primary text-sm font-body flex items-center gap-2 hover:underline">
                  <span className="material-symbols-outlined text-sm">download</span> Export All
                </button>
              </div>

              {/* Preview Table */}
              <div className="bg-surface-container rounded-xl overflow-hidden">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-surface-container-high border-b border-outline-variant/10">
                      <th className="px-6 py-4 text-xs font-headline font-bold text-slate-400 uppercase tracking-widest">Pipeline Name</th>
                      <th className="px-6 py-4 text-xs font-headline font-bold text-slate-400 uppercase tracking-widest text-right">Index</th>
                      <th className="px-6 py-4 text-xs font-headline font-bold text-slate-400 uppercase tracking-widest">Difficulty</th>
                      <th className="px-6 py-4 text-xs font-headline font-bold text-slate-400 uppercase tracking-widest">Complexity</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/5">
                    {result.pipelines.slice(0, 10).map((name, i) => {
                      const ds = difficultyStyle(difficulty);
                      return (
                        <tr
                          key={i}
                          onClick={() => setSelectedPipeline(selectedPipeline === i ? null : i)}
                          className="hover:bg-surface-container-low transition-colors cursor-pointer group"
                        >
                          <td className="px-6 py-5">
                            <div className="flex items-center gap-3">
                              <span className="material-symbols-outlined text-slate-500 text-sm group-hover:text-primary">data_object</span>
                              <span className="font-mono text-sm text-on-surface">{name}</span>
                            </div>
                          </td>
                          <td className="px-6 py-5 text-right font-mono text-slate-400">{String(i + 1).padStart(2, "0")}</td>
                          <td className="px-6 py-5">
                            <div className={`inline-flex items-center px-2 py-0.5 rounded ${ds.bg} border-l-2 ${ds.border}`}>
                              <span className={`font-mono text-[10px] ${ds.text} uppercase`}>{difficulty}</span>
                            </div>
                          </td>
                          <td className="px-6 py-5 text-xs text-slate-400 font-body capitalize">{complexity}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Conversion Feasibility Analytics */}
            <section className="bg-surface-container-low p-8 rounded-xl space-y-8 border border-outline-variant/5">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div>
                  <h3 className="text-xl font-headline font-bold text-on-surface">Conversion Feasibility Analytics</h3>
                  <p className="text-sm text-slate-500 font-body">Preview how the generated suite maps to target architecture.</p>
                </div>
                <button className="px-8 py-3 rounded-lg border border-primary/20 bg-primary/5 text-primary font-bold font-headline uppercase tracking-wider hover:bg-primary/10 transition-colors flex items-center gap-3">
                  <span className="material-symbols-outlined">analytics</span>
                  Run Converter + Score
                </button>
              </div>
              {/* CCS Distribution Chart */}
              <div className="bg-surface-container-lowest p-6 rounded-lg space-y-4">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-xs font-bold text-slate-400 font-headline uppercase tracking-widest">Capability Coverage Score (CCS)</span>
                  <span className="text-xl font-mono text-primary">--</span>
                </div>
                <div className="h-4 w-full bg-surface-container-high rounded-full overflow-hidden flex">
                  <div className="h-full bg-tertiary" style={{ width: "45%" }} />
                  <div className="h-full bg-primary" style={{ width: "30%" }} />
                  <div className="h-full bg-secondary-container" style={{ width: "9%" }} />
                  <div className="h-full bg-error" style={{ width: "16%" }} />
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-2">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-tertiary" />
                    <span className="text-[10px] text-slate-400 font-mono">Native Support (45%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-primary" />
                    <span className="text-[10px] text-slate-400 font-mono">Refactor Required (30%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-secondary-container" />
                    <span className="text-[10px] text-slate-400 font-mono">UDF Emulated (9%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-error" />
                    <span className="text-[10px] text-slate-400 font-mono">Unsupported (16%)</span>
                  </div>
                </div>
              </div>
            </section>
          </>
        )}
      </div>
    </>
  );
}
