import React, { useState } from "react";
import { api } from "../api";
import { TopHeader } from "../components/TopHeader";
import { ErrorBanner } from "../components/ErrorBanner";

interface JudgeResult { score: number; reasoning: string }

const QUICK_TESTS = [
  { id: "4012", label: "Substring", adf: "@substring(item().name, 0, 5)", python: "row['name'][:5]", expect: true },
  { id: "4028", label: "Math coercion", adf: "@add(variables('count'), 1)", python: 'count += "1"', expect: false },
  { id: "4035", label: "Case transform", adf: "@toLower(dataset().folder)", python: "path.lower()", expect: true },
  { id: "4049", label: "Equality check", adf: "@equals(parameters('env'), 'prod')", python: "env == 'prod'", expect: true },
  { id: "4063", label: "Concat + param", adf: "@concat(pipeline().parameters.prefix, '/', utcNow())", python: "f\"{prefix}/{datetime.utcnow()}\"", expect: true },
  { id: "4077", label: "Nested math", adf: "@add(mul(pipeline().parameters.count, 2), 1)", python: "int(dbutils.widgets.get('count')) * 2 + 1", expect: true },
];

function scoreColor(s: number): string {
  if (s >= 0.9) return "#27e199";
  if (s >= 0.7) return "#ffb547";
  return "#ff5c5c";
}

export function ExpressionPage() {
  const [adfExpr, setAdfExpr] = useState("");
  const [pythonCode, setPythonCode] = useState("");
  const [result, setResult] = useState<JudgeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleJudge() {
    if (!adfExpr.trim() || !pythonCode.trim()) return;
    setError(null); setResult(null); setLoading(true);
    try { setResult(await api.validateExpression(adfExpr.trim(), pythonCode.trim())); }
    catch (err) { setError(err instanceof Error ? err.message : "Judge failed"); }
    finally { setLoading(false); }
  }

  function loadQuickTest(t: typeof QUICK_TESTS[0]) {
    setAdfExpr(t.adf); setPythonCode(t.python); setResult(null); setError(null);
  }

  return (
    <>
      <TopHeader title="Expression Validator" />
      <div className="pt-24 pb-16 px-10 max-w-7xl space-y-8" style={{ animation: "fade-in-up 0.4s ease both" }}>

        {/* Header */}
        <section className="flex justify-between items-end">
          <div>
            <h2 className="text-4xl font-bold font-headline text-on-surface tracking-tight">Expression Validator</h2>
            <p className="text-slate-500 font-body mt-2">
              Verify semantic equivalence between ADF expressions and their Python translations using an LLM judge.
            </p>
          </div>
          <button onClick={handleJudge} disabled={loading || !adfExpr.trim() || !pythonCode.trim()}
            className={`px-6 py-2.5 rounded-lg font-bold text-sm flex items-center gap-2 transition-all ${
              loading ? "bg-primary/30 text-slate-500 cursor-wait"
                      : !adfExpr.trim() || !pythonCode.trim() ? "bg-surface-container-high text-slate-600 cursor-not-allowed"
                      : "bg-gradient-to-br from-primary to-primary-container text-on-primary-container hover:scale-[1.02] shadow-lg shadow-blue-900/20"
            }`}>
            {loading
              ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Judging...</>
              : <><span className="material-symbols-outlined text-sm">gavel</span> Judge Equivalence</>}
          </button>
        </section>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        {/* Split editors */}
        <div className="grid grid-cols-12 gap-6">
          {/* ADF panel */}
          <div className="col-span-6">
            <div className="bg-[#060a13] rounded-xl overflow-hidden border border-outline-variant/10 shadow-2xl flex flex-col h-[280px]">
              <div className="px-5 py-3 bg-surface-container/30 border-b border-outline-variant/5 flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-primary-container" />
                  <span className="font-mono text-[10px] text-slate-400 uppercase tracking-widest">ADF Expression</span>
                </div>
                <div className="flex gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-red-500/20 border border-red-500/40" />
                  <div className="w-2 h-2 rounded-full bg-yellow-500/20 border border-yellow-500/40" />
                  <div className="w-2 h-2 rounded-full bg-green-500/20 border border-green-500/40" />
                </div>
              </div>
              <textarea value={adfExpr} onChange={e => setAdfExpr(e.target.value)} spellCheck={false}
                placeholder="@concat(pipeline().parameters.prefix, utcNow())"
                className="flex-1 bg-transparent px-5 py-4 text-primary font-mono text-sm leading-relaxed resize-none outline-none placeholder:text-slate-700" />
            </div>
          </div>

          {/* Python panel */}
          <div className="col-span-6">
            <div className="bg-[#060a13] rounded-xl overflow-hidden border border-outline-variant/10 shadow-2xl flex flex-col h-[280px]">
              <div className="px-5 py-3 bg-surface-container/30 border-b border-outline-variant/5 flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-tertiary" />
                  <span className="font-mono text-[10px] text-slate-400 uppercase tracking-widest">Python Code</span>
                </div>
                <div className="flex gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-red-500/20 border border-red-500/40" />
                  <div className="w-2 h-2 rounded-full bg-yellow-500/20 border border-yellow-500/40" />
                  <div className="w-2 h-2 rounded-full bg-green-500/20 border border-green-500/40" />
                </div>
              </div>
              <textarea value={pythonCode} onChange={e => setPythonCode(e.target.value)} spellCheck={false}
                placeholder="f&quot;{dbutils.widgets.get('prefix')}/{datetime.utcnow()}&quot;"
                className="flex-1 bg-transparent px-5 py-4 text-tertiary font-mono text-sm leading-relaxed resize-none outline-none placeholder:text-slate-700" />
            </div>
          </div>
        </div>

        {/* Result */}
        {result && !loading && (
          <div className="grid grid-cols-12 gap-6" style={{ animation: "fade-in-up 0.3s ease both" }}>
            {/* Score gauge */}
            <div className="col-span-3 bg-surface-container rounded-xl p-6 flex flex-col items-center justify-center border border-outline-variant/10 relative overflow-hidden">
              <div className="absolute inset-0 blur-[80px] pointer-events-none" style={{ backgroundColor: `${scoreColor(result.score)}08` }} />
              <span className="text-[10px] font-mono text-outline uppercase tracking-widest mb-4">Confidence</span>
              <div className="relative w-28 h-28 flex items-center justify-center">
                <svg className="w-full h-full -rotate-90">
                  <circle className="text-surface-container-highest" cx="56" cy="56" r="50" fill="transparent" stroke="currentColor" strokeWidth={6} />
                  <circle cx="56" cy="56" r="50" fill="transparent" stroke={scoreColor(result.score)} strokeWidth={6} strokeLinecap="round"
                    strokeDasharray={314.2} strokeDashoffset={314.2 - result.score * 314.2}
                    style={{ transition: "stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)" }} />
                </svg>
                <span className="absolute text-3xl font-headline font-bold" style={{ color: scoreColor(result.score) }}>
                  {(result.score * 100).toFixed(0)}
                </span>
              </div>
              <span className={`mt-3 machined-chip px-2.5 py-0.5 rounded text-[9px] font-mono uppercase`}
                style={{ borderColor: scoreColor(result.score), color: scoreColor(result.score) }}>
                {result.score >= 0.9 ? "EQUIVALENT" : result.score >= 0.7 ? "PARTIAL MATCH" : "DIVERGENT"}
              </span>
            </div>

            {/* Reasoning */}
            <div className="col-span-9 glass-panel rounded-xl p-6 border border-outline-variant/10">
              <div className="flex items-center gap-2 mb-3">
                <span className="material-symbols-outlined text-primary text-sm">psychology</span>
                <span className="text-xs font-headline font-semibold text-primary uppercase tracking-wider">LLM Reasoning</span>
                <span className="machined-chip border-outline-variant/30 text-outline px-2 py-0.5 rounded text-[9px] font-mono ml-auto">FMAPI Judge</span>
              </div>
              <p className="text-on-surface/90 text-sm leading-relaxed font-body whitespace-pre-line">{result.reasoning}</p>
            </div>
          </div>
        )}

        {loading && (
          <div className="bg-surface-container rounded-xl p-8 flex flex-col items-center gap-4">
            <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-sm font-mono text-outline">LLM judge evaluating...</span>
          </div>
        )}

        {/* Quick-test library */}
        <section>
          <div className="flex items-center gap-3 mb-4">
            <span className="material-symbols-outlined text-primary text-sm">science</span>
            <h3 className="text-xs font-mono text-outline uppercase tracking-wider">Quick-Test Library</h3>
            <span className="text-[10px] text-outline">— click to load</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {QUICK_TESTS.map(t => (
              <button key={t.id} onClick={() => loadQuickTest(t)}
                className="p-4 rounded-xl bg-surface-container border border-transparent hover:border-outline-variant/20 hover:bg-surface-container-high transition-all text-left group">
                <div className="flex justify-between items-center mb-3">
                  <span className="text-xs font-headline font-semibold text-on-surface">{t.label}</span>
                  <span className={`material-symbols-outlined text-sm ${t.expect ? "text-tertiary" : "text-error"}`}
                    style={{ fontVariationSettings: "'FILL' 1" }}>
                    {t.expect ? "check_circle" : "cancel"}
                  </span>
                </div>
                <div className="space-y-1.5">
                  <p className="text-[10px] font-mono text-primary truncate">{t.adf}</p>
                  <p className="text-[10px] font-mono text-tertiary truncate">{t.python}</p>
                </div>
              </button>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
