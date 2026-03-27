import React, { useState } from "react";
import { api } from "../api";
import type { ParallelResult, ComparisonRow } from "../types";
import { Card, SectionTitle } from "../components/Card";
import { ScorecardGauge } from "../components/ScorecardGauge";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";

function EquivalenceGauge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 90 ? "var(--green)" : pct >= 70 ? "var(--amber)" : "var(--red)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: "50%",
          border: `3px solid ${color}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: 18,
          color,
          boxShadow: `0 0 16px ${color}33`,
        }}
      >
        {pct}
      </div>
      <div>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 14 }}>Equivalence</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)" }}>ADF vs Databricks</div>
      </div>
    </div>
  );
}

function ComparisonTable({ rows }: { rows: ComparisonRow[] }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontFamily: "var(--font-mono)",
          fontSize: 12,
        }}
      >
        <thead>
          <tr>
            {["Activity", "Match", "ADF Output", "Databricks Output", "Diff"].map((h) => (
              <th
                key={h}
                style={{
                  textAlign: "left",
                  padding: "10px 14px",
                  borderBottom: "2px solid var(--border-bright)",
                  color: "var(--text-muted)",
                  fontWeight: 500,
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              style={{
                borderBottom: "1px solid var(--border)",
                animation: `slideIn 0.3s ease ${i * 40}ms both`,
              }}
            >
              <td style={{ padding: "10px 14px", color: "var(--text-primary)", fontWeight: 500 }}>
                {row.activity_name}
              </td>
              <td style={{ padding: "10px 14px" }}>
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 24,
                    height: 24,
                    borderRadius: "50%",
                    background: row.match ? "var(--green-dim)" : "var(--red-dim)",
                    color: row.match ? "var(--green)" : "var(--red)",
                    fontSize: 12,
                    fontWeight: 700,
                  }}
                >
                  {row.match ? "\u2713" : "\u2717"}
                </span>
              </td>
              <td
                style={{
                  padding: "10px 14px",
                  color: "var(--text-secondary)",
                  maxWidth: 200,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={row.adf_output || ""}
              >
                {row.adf_output || "\u2014"}
              </td>
              <td
                style={{
                  padding: "10px 14px",
                  color: "var(--text-secondary)",
                  maxWidth: 200,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={row.databricks_output || ""}
              >
                {row.databricks_output || "\u2014"}
              </td>
              <td
                style={{
                  padding: "10px 14px",
                  color: row.diff ? "var(--red)" : "var(--text-muted)",
                  fontStyle: row.diff ? "normal" : "italic",
                }}
              >
                {row.diff || "\u2014"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ParallelPage() {
  const [pipelineName, setPipelineName] = useState("");
  const [paramsJson, setParamsJson] = useState("{}");
  const [result, setResult] = useState<ParallelResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    if (!pipelineName.trim()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const params = JSON.parse(paramsJson);
      const res = await api.parallelRun(pipelineName.trim(), params);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parallel run failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ animation: "fadeInUp 0.4s ease" }}>
      <SectionTitle>Parallel Test</SectionTitle>
      <p style={{ color: "var(--text-secondary)", marginBottom: 20, fontSize: 13, maxWidth: 600 }}>
        Run the ADF pipeline and converted Lakeflow Job side-by-side, compare outputs per activity.
      </p>

      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 14 }}>
          <div>
            <label style={{ display: "block", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
              Pipeline Name
            </label>
            <input
              value={pipelineName}
              onChange={(e) => setPipelineName(e.target.value)}
              placeholder="e.g., etl_daily_ingestion"
              style={{
                width: "100%",
                padding: "10px 14px",
                background: "var(--bg-base)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                fontFamily: "var(--font-mono)",
                fontSize: 13,
                outline: "none",
              }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
              Parameters (JSON)
            </label>
            <input
              value={paramsJson}
              onChange={(e) => setParamsJson(e.target.value)}
              placeholder='{"env": "dev"}'
              style={{
                width: "100%",
                padding: "10px 14px",
                background: "var(--bg-base)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                fontFamily: "var(--font-mono)",
                fontSize: 13,
                outline: "none",
              }}
            />
          </div>
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
          }}
        >
          {loading ? "Running..." : "Run Parallel Test"}
        </button>
      </Card>

      {loading && <Card><LoadingOverlay message="Executing on ADF + Databricks..." /></Card>}
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {result && !loading && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20, animation: "fadeInUp 0.4s ease" }}>
          <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 20 }}>
            <Card style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 20 }}>
              <EquivalenceGauge score={result.equivalence_score} />
              <ScorecardGauge scorecard={result.scorecard} />
            </Card>
            <Card>
              <ComparisonTable rows={result.comparisons} />
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
