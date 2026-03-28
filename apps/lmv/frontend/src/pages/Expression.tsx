import React, { useState } from "react";
import { api } from "../api";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingOverlay } from "../components/LoadingOverlay";

interface JudgeResult {
  score: number;
  reasoning: string;
}

const QUICK_TESTS = [
  { id: "4012", adf: "@substring(item().name, 0, 5)", python: "row['name'][:5]", pass: true },
  { id: "4028", adf: "@add(variables('count'), 1)", python: 'count += "1"', pass: false },
  { id: "4035", adf: "@toLower(dataset().folder)", python: "path.lower()", pass: true },
  { id: "4049", adf: "@equals(parameters('env'), 'prod')", python: "env == 'prod'", pass: true },
];

export function ExpressionPage() {
  const [adfExpr, setAdfExpr] = useState("");
  const [pythonCode, setPythonCode] = useState("");
  const [result, setResult] = useState<JudgeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleJudge() {
    if (!adfExpr.trim() || !pythonCode.trim()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const res = await api.validateExpression(adfExpr.trim(), pythonCode.trim());
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Judge failed");
    } finally {
      setLoading(false);
    }
  }

  function loadQuickTest(idx: number) {
    const t = QUICK_TESTS[idx];
    setAdfExpr(t.adf);
    setPythonCode(t.python);
    setResult(null);
    setError(null);
  }

  const scoreColor = result
    ? result.score >= 0.9
      ? "#27e199"
      : result.score >= 0.7
      ? "#ffb547"
      : "#ff5c5c"
    : "#adc6ff";

  return (
    <>
      <TopHeader title="Expression Engine" />
      <div className="pt-24 pb-12 px-10 space-y-8 max-w-7xl w-full">
        {/* Page Header */}
        <div className="flex justify-between items-end">
          <div>
            <h2 className="text-3xl font-bold font-headline text-primary">
              Expression Validator
            </h2>
            <p className="text-slate-400 mt-1 font-body">
              Cross-compile and verify legacy ADF logic against modern Python counterparts.
            </p>
          </div>
          <div className="machined-chip border-tertiary px-4 py-2 rounded-sm">
            <span className="text-[10px] font-mono text-tertiary block uppercase tracking-tighter">Status</span>
            <span className="text-sm font-mono text-on-surface">Engine Ready</span>
          </div>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Split-panel editor */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* ADF Side */}
          <div className="bg-surface-container rounded-xl overflow-hidden shadow-2xl flex flex-col h-[320px]">
            <div className="px-4 py-3 bg-surface-container-high flex justify-between items-center">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-primary-container" />
                <span className="text-xs font-mono text-slate-300 uppercase tracking-widest">ADF Expression</span>
              </div>
              <span className="material-symbols-outlined text-slate-500 text-sm">integration_instructions</span>
            </div>
            <textarea
              value={adfExpr}
              onChange={(e) => setAdfExpr(e.target.value)}
              className="flex-1 bg-surface-container-lowest p-6 text-[13px] font-mono text-primary border-none resize-none leading-relaxed placeholder:text-slate-700 outline-none focus:ring-0"
              placeholder="@concat(pipeline().parameters.prefix, utcNow())"
            />
          </div>

          {/* Python Side */}
          <div className="bg-surface-container rounded-xl overflow-hidden shadow-2xl flex flex-col h-[320px]">
            <div className="px-4 py-3 bg-surface-container-high flex justify-between items-center">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-tertiary" />
                <span className="text-xs font-mono text-slate-300 uppercase tracking-widest">Python Code</span>
              </div>
              <span className="material-symbols-outlined text-slate-500 text-sm">terminal</span>
            </div>
            <textarea
              value={pythonCode}
              onChange={(e) => setPythonCode(e.target.value)}
              className="flex-1 bg-surface-container-lowest p-6 text-[13px] font-mono text-tertiary border-none resize-none leading-relaxed placeholder:text-slate-700 outline-none focus:ring-0"
              placeholder="str(dbutils.widgets.get('prefix')) + str(datetime.now())"
            />
          </div>

          {/* Action Button */}
          <div className="lg:col-span-2">
            <button
              onClick={handleJudge}
              disabled={loading || !adfExpr.trim() || !pythonCode.trim()}
              className={`w-full py-5 rounded-xl font-headline font-semibold text-lg flex items-center justify-center gap-3 transition-all shadow-lg shadow-primary-container/10 ${
                loading
                  ? "bg-primary/30 text-slate-400 cursor-wait"
                  : "bg-gradient-to-r from-primary to-primary-container text-on-primary-fixed hover:brightness-110"
              }`}
            >
              <span className="material-symbols-outlined">gavel</span>
              {loading ? "Judging..." : "Judge Equivalence"}
            </button>
          </div>
        </section>

        {/* Results */}
        {loading && (
          <section className="bg-surface-container-low rounded-xl p-8">
            <LoadingOverlay message="LLM judge is evaluating..." />
          </section>
        )}

        {result && !loading && (
          <section className="bg-surface-container-low rounded-xl p-8 relative overflow-hidden">
            {/* Background Accent */}
            <div className="absolute -right-20 -top-20 w-64 h-64 blur-[100px] rounded-full" style={{ backgroundColor: `${scoreColor}0D` }} />
            <div className="flex flex-col md:flex-row items-center gap-10 relative z-10">
              {/* Score Gauge */}
              <div className="flex flex-col items-center justify-center">
                <div className="relative w-32 h-32 flex items-center justify-center">
                  <svg className="w-full h-full transform -rotate-90">
                    <circle className="text-surface-container-highest" cx="64" cy="64" r="58" fill="transparent" stroke="currentColor" strokeWidth={8} />
                    <circle cx="64" cy="64" r="58" fill="transparent" stroke={scoreColor} strokeWidth={8} strokeLinecap="round"
                      strokeDasharray={364.4} strokeDashoffset={364.4 - result.score * 364.4}
                      style={{ transition: "stroke-dashoffset 1s ease" }}
                    />
                  </svg>
                  <span className="absolute text-4xl font-headline font-bold" style={{ color: scoreColor }}>
                    {result.score.toFixed(2)}
                  </span>
                </div>
                <span className="text-[10px] font-mono text-slate-500 mt-3 uppercase tracking-widest">Confidence Index</span>
              </div>

              {/* LLM Reasoning (glass-panel) */}
              <div className="flex-1 glass-panel p-6 rounded-2xl border border-outline-variant/10">
                <div className="flex items-center gap-2 mb-3">
                  <span className="material-symbols-outlined text-primary text-sm">psychology</span>
                  <span className="text-xs font-headline font-semibold text-primary uppercase tracking-wider">LLM Reasoning</span>
                </div>
                <p className="text-on-surface text-sm leading-relaxed font-body">{result.reasoning}</p>
              </div>

              {/* Model Badge Card */}
              <div className="self-end md:self-auto">
                <div className="bg-surface-container-highest/60 border border-outline-variant/20 px-4 py-3 rounded-xl flex items-center gap-3">
                  <div className="w-8 h-8 rounded bg-on-primary flex items-center justify-center">
                    <span className="material-symbols-outlined text-primary-fixed text-lg">token</span>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 font-mono uppercase leading-none">Validator Model</p>
                    <p className="text-sm font-headline font-semibold text-on-surface">FMAPI Judge</p>
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Quick-Test Library */}
        <section className="space-y-6">
          <h3 className="text-[11px] font-headline font-bold text-slate-500 uppercase tracking-[0.2em]">Quick-Test Library</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {QUICK_TESTS.map((t, i) => (
              <button
                key={i}
                onClick={() => loadQuickTest(i)}
                className="bg-surface-container border border-transparent hover:border-outline-variant/30 hover:bg-surface-container-high transition-all p-5 rounded-xl text-left group"
              >
                <div className="flex justify-between items-start mb-4">
                  <span
                    className={`material-symbols-outlined text-xl ${t.pass ? "text-tertiary" : "text-error"}`}
                  >
                    {t.pass ? "check_circle" : "cancel"}
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">ID: {t.id}</span>
                </div>
                <div className="space-y-3">
                  <div className="bg-surface-container-lowest p-2 rounded">
                    <p className="text-[10px] text-slate-500 mb-1">ADF</p>
                    <p className="text-xs font-mono text-primary truncate">{t.adf}</p>
                  </div>
                  <div className="bg-surface-container-lowest p-2 rounded">
                    <p className="text-[10px] text-slate-500 mb-1">Python</p>
                    <p className="text-xs font-mono text-tertiary truncate">{t.python}</p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
