import React, { useState } from "react";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingOverlay } from "../components/LoadingOverlay";

interface GenerateResult {
  count: number;
  pipelines: string[];
  output_path: string | null;
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
        <div>
          <h2 className="text-3xl font-bold font-headline text-on-surface tracking-tight">
            Synthetic Pipeline Generator
          </h2>
          <p className="text-slate-400 mt-1">
            Generate parameterized ADF pipelines with known-correct outputs for stress testing.
          </p>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Config panel */}
        <div className="bg-surface-container rounded-xl p-8 border border-white/5 shadow-xl">
          <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-6 font-mono">
            Generation Parameters
          </h3>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
            <div>
              <label className="block text-xs font-bold text-primary tracking-widest uppercase mb-2 font-mono">
                Count
              </label>
              <input
                type="number"
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                min={1}
                max={500}
                className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 px-4 text-slate-100 font-mono text-sm outline-none focus:border-primary transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-primary tracking-widest uppercase mb-2 font-mono">
                Difficulty
              </label>
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
                className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 px-4 text-slate-100 font-mono text-sm outline-none focus:border-primary transition-all"
              >
                <option value="simple">Simple</option>
                <option value="medium">Medium</option>
                <option value="complex">Complex</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-bold text-primary tracking-widest uppercase mb-2 font-mono">
                Expression Complexity
              </label>
              <select
                value={complexity}
                onChange={(e) => setComplexity(e.target.value)}
                className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 px-4 text-slate-100 font-mono text-sm outline-none focus:border-primary transition-all"
              >
                <option value="simple">Simple</option>
                <option value="nested">Nested</option>
                <option value="mixed">Mixed</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-bold text-primary tracking-widest uppercase mb-2 font-mono">
                Max Activities
              </label>
              <input
                type="number"
                value={maxActivities}
                onChange={(e) => setMaxActivities(Number(e.target.value))}
                min={1}
                max={100}
                className="w-full bg-surface-container-lowest border border-outline-variant/15 rounded-lg py-3 px-4 text-slate-100 font-mono text-sm outline-none focus:border-primary transition-all"
              />
            </div>
          </div>
          <div className="mt-8 flex justify-end">
            <button
              onClick={handleGenerate}
              disabled={loading}
              className={`px-8 py-3 rounded-lg font-bold text-sm tracking-wide flex items-center gap-2 transition-all shadow-lg ${
                loading
                  ? "bg-primary/30 text-slate-400 cursor-wait"
                  : "bg-gradient-to-br from-primary to-primary-container text-on-primary-container hover:scale-[1.02] active:scale-95 shadow-primary/10"
              }`}
            >
              <span className="material-symbols-outlined">science</span>
              {loading ? "Generating..." : "Generate Suite"}
            </button>
          </div>
        </div>

        {loading && (
          <div className="bg-surface-container rounded-xl p-8">
            <LoadingOverlay message="Generating synthetic pipelines..." />
          </div>
        )}

        {result && !loading && (
          <>
            {/* Summary */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="bg-surface-container p-6 rounded-xl">
                <p className="text-sm text-slate-500 uppercase tracking-wider">Generated</p>
                <span className="text-4xl font-headline font-bold text-on-surface mt-2 block">
                  {result.count}
                </span>
                <span className="text-xs font-mono text-[#27e199]">pipelines</span>
              </div>
              <div className="bg-surface-container p-6 rounded-xl">
                <p className="text-sm text-slate-500 uppercase tracking-wider">Difficulty</p>
                <span className="text-2xl font-headline font-bold text-on-surface mt-2 block capitalize">
                  {difficulty}
                </span>
              </div>
              <div className="bg-surface-container p-6 rounded-xl">
                <p className="text-sm text-slate-500 uppercase tracking-wider">Complexity</p>
                <span className="text-2xl font-headline font-bold text-on-surface mt-2 block capitalize">
                  {complexity}
                </span>
              </div>
            </div>

            {/* Pipeline list */}
            <div className="bg-surface-container rounded-xl overflow-hidden border border-white/5">
              <div className="px-8 py-5 bg-surface-container-high/20 border-b border-white/5 flex justify-between items-center">
                <h3 className="text-sm font-headline font-semibold text-slate-100 uppercase tracking-wider">
                  Generated Pipelines
                </h3>
                <span className="text-xs font-mono text-slate-500">{result.pipelines.length} items</span>
              </div>
              <div className="max-h-[400px] overflow-y-auto">
                {result.pipelines.map((name, i) => {
                  const isSelected = selectedPipeline === i;
                  return (
                    <div key={i}>
                      <div
                        onClick={() => setSelectedPipeline(isSelected ? null : i)}
                        className={`flex items-center gap-4 px-8 py-3 border-b border-white/5 cursor-pointer transition-colors ${
                          isSelected ? "bg-primary/10 border-l-2 border-l-primary" : "hover:bg-surface-container-low/30"
                        }`}
                      >
                        <span className="text-[10px] font-mono text-slate-600 w-8">{String(i + 1).padStart(3, "0")}</span>
                        <span className="material-symbols-outlined text-primary text-sm">account_tree</span>
                        <span className="text-sm font-mono text-slate-200 flex-1">{name}</span>
                        <span className="material-symbols-outlined text-slate-600 text-sm transition-transform" style={{ transform: isSelected ? "rotate(180deg)" : "rotate(0)" }}>
                          expand_more
                        </span>
                      </div>
                      {isSelected && (
                        <div className="px-8 py-4 bg-base border-b border-white/5 animate-[fade-in-up_0.2s_ease]">
                          <div className="flex items-center justify-between mb-3">
                            <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Pipeline Definition</span>
                            <button
                              onClick={() => {
                                window.location.hash = "#/validate";
                                // Store in sessionStorage so Validate page can pick it up
                                sessionStorage.setItem("lmv_prefill_json", JSON.stringify({ name }, null, 2));
                              }}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent/10 text-accent text-xs font-mono font-medium hover:bg-accent/20 transition-colors"
                            >
                              <span className="material-symbols-outlined text-sm">open_in_new</span>
                              Open in Validator
                            </button>
                          </div>
                          <pre className="p-4 bg-surface-container-lowest rounded-lg font-mono text-xs text-primary/80 overflow-x-auto max-h-[200px]">
                            {JSON.stringify({ name, type: "synthetic", difficulty, expression_complexity: complexity, index: i }, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
