import React, { useState, useEffect } from "react";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingOverlay } from "../components/LoadingOverlay";

type Mode = "template" | "llm" | "custom";

interface TemplateInfo {
  key: string;
  label: string;
  icon: string;
  description: string;
}

interface TestDataItem {
  pipeline_name: string;
  source_files: Record<string, string>;
  seed_sql: string[];
  expected_outputs: Record<string, string>;
  setup_instructions: string;
}

interface GenerateResult {
  count: number;
  pipelines: string[];
  output_path: string | null;
  test_data?: TestDataItem[];
}

export function SyntheticPage() {
  const [mode, setMode] = useState<Mode>("template");
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [count, setCount] = useState(50);
  const [maxActivities, setMaxActivities] = useState(20);
  const [difficulty, setDifficulty] = useState("medium");
  const [complexity, setComplexity] = useState("mixed");
  const [generateTestData, setGenerateTestData] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [resultTab, setResultTab] = useState<"pipelines" | "testdata">("pipelines");
  const [selectedPipeline, setSelectedPipeline] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load templates on mount
  useEffect(() => {
    fetch("/api/synthetic/templates")
      .then((r) => r.json())
      .then(setTemplates)
      .catch(() => {});
  }, []);

  // When a preset is selected, resolve the prompt
  async function selectPreset(key: string) {
    setSelectedPreset(key);
    if (mode === "template") return; // template mode doesn't use prompt
    try {
      const res = await fetch("/api/synthetic/resolve-template", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset: key, count, max_activities: maxActivities }),
      });
      const data = await res.json();
      setPrompt(data.prompt || "");
    } catch {}
  }

  async function handleGenerate() {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const body: Record<string, unknown> = {
        count,
        difficulty,
        max_activities: maxActivities,
        mode,
        generate_test_data: generateTestData,
      };
      if (mode === "llm" && selectedPreset) body.preset = selectedPreset;
      if (mode === "custom" || (mode === "llm" && prompt)) body.custom_prompt = prompt;

      const res = await fetch("/api/synthetic/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      setResult(await res.json());
      setResultTab("pipelines");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <TopHeader title="Synthetic Engine" />
      <div className="pt-24 pb-12 px-10 space-y-10 max-w-7xl">
        {/* Header */}
        <section>
          <h2 className="text-3xl font-bold font-headline text-on-surface">Synthetic Pipeline Generator</h2>
          <p className="text-on-surface-variant mt-2 max-w-2xl">
            Initialize automated test suites with precisely calibrated complexity metrics to stress-test your migration logic.
          </p>
        </section>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Mode Selector */}
        <section className="flex justify-center">
          <div className="inline-flex p-1 bg-surface-container-low rounded-lg">
            {([
              { id: "template" as Mode, label: "Template (deterministic)" },
              { id: "llm" as Mode, label: "LLM (preset+editable)" },
              { id: "custom" as Mode, label: "Custom (free-form)" },
            ]).map((m) => (
              <button
                key={m.id}
                onClick={() => { setMode(m.id); setPrompt(""); setSelectedPreset(null); }}
                className={`px-6 py-2 rounded-md font-medium text-sm transition-all ${
                  mode === m.id
                    ? "bg-surface-container-highest text-primary"
                    : "text-outline-variant hover:text-on-surface"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </section>

        {/* Preset Template Grid (visible in template + llm modes) */}
        {mode !== "custom" && (
          <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {templates.map((t) => (
              <div
                key={t.key}
                onClick={() => selectPreset(t.key)}
                className={`p-6 bg-surface-container rounded-xl hover:bg-surface-container-high transition-all cursor-pointer group ${
                  selectedPreset === t.key ? "border-b-2 border-primary" : ""
                }`}
              >
                <span className="material-symbols-outlined text-primary mb-4 block">{t.icon}</span>
                <h3 className="font-headline font-semibold text-on-surface mb-2">{t.label}</h3>
                <p className="text-sm text-outline leading-relaxed">{t.description}</p>
              </div>
            ))}
          </section>
        )}

        {/* Prompt Editor (visible in llm + custom modes) */}
        {mode !== "template" && (
          <section className="space-y-4">
            <div className="flex justify-between items-center">
              <div className="machined-chip px-4 py-1.5 rounded text-[10px] font-mono text-primary border-primary flex gap-4">
                <span>MODE: {mode.toUpperCase()}</span>
                {selectedPreset && (
                  <>
                    <span className="opacity-30">|</span>
                    <span>TEMPLATE: {selectedPreset.toUpperCase()}</span>
                  </>
                )}
              </div>
            </div>
            <div className="relative bg-[#060a13] rounded-xl overflow-hidden border border-outline-variant/20">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                spellCheck={false}
                placeholder={mode === "custom" ? "Write your custom generation prompt here..." : "Select a preset template above, or edit this prompt directly..."}
                className="w-full h-[300px] bg-transparent px-6 py-4 text-on-surface font-mono text-xs leading-relaxed border-none resize-none outline-none focus:ring-1 focus:ring-primary placeholder:text-slate-700"
              />
            </div>
          </section>
        )}

        {/* Configuration Row */}
        <section className="flex flex-wrap items-end gap-6 p-6 bg-surface-container rounded-xl">
          <div className="space-y-2">
            <label className="block text-[10px] font-mono text-outline uppercase tracking-wider">Count</label>
            <input
              type="number"
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              min={1}
              max={500}
              className="w-24 bg-surface-container-lowest border-none rounded-lg py-2 px-3 text-sm text-primary font-mono outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="space-y-2">
            <label className="block text-[10px] font-mono text-outline uppercase tracking-wider">Max Activities</label>
            <input
              type="number"
              value={maxActivities}
              onChange={(e) => setMaxActivities(Number(e.target.value))}
              min={1}
              max={100}
              className="w-32 bg-surface-container-lowest border-none rounded-lg py-2 px-3 text-sm text-primary font-mono outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="space-y-2">
            <label className="block text-[10px] font-mono text-outline uppercase tracking-wider">Difficulty</label>
            <select
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value)}
              className="w-40 bg-surface-container-lowest border-none rounded-lg py-2 px-3 text-sm text-on-surface outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="simple">Simple</option>
              <option value="medium">Medium</option>
              <option value="complex">Complex</option>
            </select>
          </div>
          <div className="space-y-2">
            <label className="block text-[10px] font-mono text-outline uppercase tracking-wider">Expression Complexity</label>
            <select
              value={complexity}
              onChange={(e) => setComplexity(e.target.value)}
              className="w-48 bg-surface-container-lowest border-none rounded-lg py-2 px-3 text-sm text-on-surface outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="simple">Simple</option>
              <option value="nested">Nested</option>
              <option value="mixed">Mixed</option>
            </select>
          </div>
          <div className="flex-1 flex items-center justify-end gap-8">
            {/* Test data toggle */}
            <div className="flex items-center gap-3">
              <div className="text-right">
                <span className="block text-xs font-semibold text-on-surface">Generate parallel test data</span>
                <span className="block text-[10px] text-outline">CSV & SQL seed scripts</span>
              </div>
              <button
                onClick={() => setGenerateTestData(!generateTestData)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  generateTestData ? "bg-primary-container" : "bg-surface-container-highest"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
                    generateTestData ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
            </div>
            <button
              onClick={handleGenerate}
              disabled={loading}
              className={`px-8 py-3 rounded-lg font-bold text-sm shadow-lg transition-all ${
                loading
                  ? "bg-primary/30 text-slate-400 cursor-wait"
                  : "bg-gradient-to-br from-primary to-primary-container text-on-primary-container hover:scale-[0.98] shadow-primary/10"
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

        {/* Results */}
        {result && !loading && (
          <section className="space-y-6">
            {/* Tab bar */}
            <div className="flex gap-8 border-b border-outline-variant/20">
              <button
                onClick={() => setResultTab("pipelines")}
                className={`pb-4 text-sm font-semibold transition-colors ${
                  resultTab === "pipelines"
                    ? "text-primary border-b-2 border-primary"
                    : "text-outline hover:text-on-surface"
                }`}
              >
                Generated Pipelines ({result.count})
              </button>
              {result.test_data && result.test_data.length > 0 && (
                <button
                  onClick={() => setResultTab("testdata")}
                  className={`pb-4 text-sm font-semibold transition-colors ${
                    resultTab === "testdata"
                      ? "text-primary border-b-2 border-primary"
                      : "text-outline hover:text-on-surface"
                  }`}
                >
                  Test Data ({result.test_data.length} pipelines)
                </button>
              )}
            </div>

            {/* Pipelines tab */}
            {resultTab === "pipelines" && (
              <div className="bg-surface-container rounded-xl overflow-hidden">
                <table className="w-full text-left">
                  <thead className="bg-surface-container-high text-[10px] font-mono text-outline uppercase tracking-wider">
                    <tr>
                      <th className="px-6 py-4">#</th>
                      <th className="px-6 py-4">Pipeline Name</th>
                      <th className="px-6 py-4 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.pipelines.map((name, i) => {
                      const isOpen = selectedPipeline === i;
                      return (
                        <React.Fragment key={i}>
                          <tr
                            onClick={() => setSelectedPipeline(isOpen ? null : i)}
                            className={`border-t border-outline-variant/10 cursor-pointer transition-colors ${
                              isOpen ? "bg-primary/5" : "hover:bg-surface-container-low/30"
                            }`}
                          >
                            <td className="px-6 py-3 text-[10px] font-mono text-outline">{String(i + 1).padStart(3, "0")}</td>
                            <td className="px-6 py-3 text-sm font-mono text-on-surface">{name}</td>
                            <td className="px-6 py-3 text-right">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  window.location.hash = "#/validate";
                                }}
                                className="text-primary text-xs font-mono hover:underline"
                              >
                                Open in Validator
                              </button>
                            </td>
                          </tr>
                          {isOpen && (
                            <tr>
                              <td colSpan={3} className="px-6 py-4 bg-base border-t border-outline-variant/10">
                                <pre className="font-mono text-xs text-primary/80 max-h-[200px] overflow-auto">
                                  {JSON.stringify({ name, index: i, difficulty, complexity }, null, 2)}
                                </pre>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Test Data tab */}
            {resultTab === "testdata" && result.test_data && (
              <div className="space-y-6">
                {result.test_data.map((td, i) => (
                  <div key={i} className="bg-surface-container rounded-xl overflow-hidden border border-outline-variant/10">
                    <div className="px-6 py-4 bg-surface-container-high/20 border-b border-outline-variant/10 flex justify-between items-center">
                      <div className="flex items-center gap-3">
                        <span className="material-symbols-outlined text-primary text-sm">storage</span>
                        <span className="font-mono text-sm text-on-surface font-medium">{td.pipeline_name}</span>
                      </div>
                      <div className="flex gap-3">
                        {Object.keys(td.source_files).length > 0 && (
                          <span className="machined-chip border-tertiary text-tertiary px-3 py-1 rounded text-[10px] font-mono">
                            {Object.keys(td.source_files).length} CSV files
                          </span>
                        )}
                        {td.seed_sql.length > 0 && (
                          <span className="machined-chip border-primary text-primary px-3 py-1 rounded text-[10px] font-mono">
                            {td.seed_sql.length} SQL statements
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Source files */}
                    {Object.entries(td.source_files).map(([path, content]) => (
                      <div key={path} className="px-6 py-3 border-b border-outline-variant/5">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="material-symbols-outlined text-tertiary text-sm">description</span>
                          <span className="text-xs font-mono text-on-surface">{path}</span>
                        </div>
                        <pre className="text-[11px] font-mono text-on-surface/60 max-h-[120px] overflow-auto bg-surface-container-lowest rounded-lg p-3">
                          {content.slice(0, 500)}{content.length > 500 ? "\n..." : ""}
                        </pre>
                      </div>
                    ))}

                    {/* SQL scripts */}
                    {td.seed_sql.length > 0 && (
                      <div className="px-6 py-3 border-b border-outline-variant/5">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="material-symbols-outlined text-primary text-sm">database</span>
                          <span className="text-xs font-mono text-on-surface">SQL Seed Scripts</span>
                        </div>
                        <pre className="text-[11px] font-mono text-primary/70 max-h-[120px] overflow-auto bg-surface-container-lowest rounded-lg p-3">
                          {td.seed_sql.join("\n")}
                        </pre>
                      </div>
                    )}

                    {/* Setup instructions */}
                    <div className="px-6 py-3">
                      <p className="text-xs text-outline leading-relaxed whitespace-pre-line">{td.setup_instructions}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </>
  );
}
