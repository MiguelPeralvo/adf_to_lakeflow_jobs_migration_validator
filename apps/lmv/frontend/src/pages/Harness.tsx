import React, { useState } from "react";
import { api } from "../api";
import type { HarnessResult } from "../types";
import { Card, SectionTitle } from "../components/Card";
import { ScorecardGauge } from "../components/ScorecardGauge";
import { DimensionBreakdown } from "../components/DimensionBreakdown";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";

export function HarnessPage() {
  const [pipelineName, setPipelineName] = useState("");
  const [result, setResult] = useState<HarnessResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    if (!pipelineName.trim()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const res = await api.harnessRun(pipelineName.trim());
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Harness run failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ animation: "fadeInUp 0.4s ease" }}>
      <SectionTitle>Harness Run</SectionTitle>
      <p style={{ color: "var(--text-secondary)", marginBottom: 20, fontSize: 13, maxWidth: 600 }}>
        End-to-end: fetch ADF pipeline, translate with wkmigrate, validate, and optionally suggest fixes.
      </p>

      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
          <div style={{ flex: 1 }}>
            <label
              style={{
                display: "block",
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                marginBottom: 6,
              }}
            >
              Pipeline Name
            </label>
            <input
              value={pipelineName}
              onChange={(e) => setPipelineName(e.target.value)}
              placeholder="e.g., etl_daily_ingestion"
              onKeyDown={(e) => e.key === "Enter" && handleRun()}
              style={{
                width: "100%",
                padding: "10px 14px",
                background: "var(--bg-base)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                fontFamily: "var(--font-mono)",
                fontSize: 13,
                outline: "none",
                transition: "border-color var(--transition)",
              }}
              onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
              onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
            />
          </div>
          <button
            onClick={handleRun}
            disabled={loading || !pipelineName.trim()}
            style={{
              padding: "10px 28px",
              background: loading ? "var(--accent-dim)" : "var(--accent)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--radius)",
              fontFamily: "var(--font-display)",
              fontWeight: 600,
              fontSize: 13,
              cursor: loading ? "wait" : "pointer",
              opacity: loading || !pipelineName.trim() ? 0.5 : 1,
              transition: "all var(--transition)",
              whiteSpace: "nowrap",
            }}
          >
            {loading ? "Running..." : "Run Harness"}
          </button>
        </div>
      </Card>

      {loading && (
        <Card>
          <LoadingOverlay message="Running harness \u2014 this may take a minute..." />
        </Card>
      )}

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {result && !loading && (
        <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 20, animation: "fadeInUp 0.4s ease" }}>
          <Card style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 20 }}>
            <ScorecardGauge scorecard={result.scorecard} />
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)", textAlign: "center" }}>
              <div>Pipeline: <span style={{ color: "var(--text-primary)" }}>{result.pipeline_name}</span></div>
              <div>Iterations: <span style={{ color: "var(--text-primary)" }}>{result.iterations}</span></div>
            </div>
          </Card>

          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <Card>
              <DimensionBreakdown dimensions={result.scorecard.dimensions} />
            </Card>

            {result.fix_suggestions.length > 0 && (
              <Card>
                <h3
                  style={{
                    fontFamily: "var(--font-display)",
                    fontSize: 14,
                    fontWeight: 600,
                    color: "var(--amber)",
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    marginBottom: 12,
                  }}
                >
                  Fix Suggestions
                </h3>
                {result.fix_suggestions.map((s, i) => (
                  <div
                    key={i}
                    style={{
                      padding: "10px 14px",
                      background: "var(--bg-base)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius)",
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      color: "var(--text-secondary)",
                      marginBottom: 8,
                      lineHeight: 1.6,
                    }}
                  >
                    {JSON.stringify(s, null, 2)}
                  </div>
                ))}
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
