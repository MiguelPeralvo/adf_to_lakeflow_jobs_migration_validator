import React, { useState } from "react";
import { api } from "../api";
import type { Scorecard } from "../types";
import { Card, SectionTitle } from "../components/Card";
import { ScorecardGauge } from "../components/ScorecardGauge";
import { DimensionBreakdown } from "../components/DimensionBreakdown";
import { LoadingOverlay } from "../components/LoadingOverlay";
import { ErrorBanner } from "../components/ErrorBanner";

const PLACEHOLDER = `{
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
}`;

export function ValidatePage() {
  const [json, setJson] = useState(PLACEHOLDER);
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleValidate() {
    setError(null);
    setScorecard(null);
    setLoading(true);
    try {
      const parsed = JSON.parse(json);
      const result = await api.validate({ adf_json: parsed });
      setScorecard(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ animation: "fadeInUp 0.4s ease" }}>
      <SectionTitle>Validate Conversion</SectionTitle>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>
        <Card>
          <label
            style={{
              display: "block",
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              marginBottom: 8,
            }}
          >
            ADF Pipeline JSON
          </label>
          <textarea
            value={json}
            onChange={(e) => setJson(e.target.value)}
            spellCheck={false}
            style={{
              width: "100%",
              height: 300,
              background: "var(--bg-base)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              padding: 14,
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              lineHeight: 1.7,
              color: "var(--text-primary)",
              resize: "vertical",
              outline: "none",
              transition: "border-color var(--transition)",
            }}
            onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
            onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
          />
          <button
            onClick={handleValidate}
            disabled={loading}
            style={{
              marginTop: 14,
              padding: "10px 28px",
              background: loading ? "var(--accent-dim)" : "var(--accent)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--radius)",
              fontFamily: "var(--font-display)",
              fontWeight: 600,
              fontSize: 13,
              cursor: loading ? "wait" : "pointer",
              letterSpacing: "0.02em",
              transition: "all var(--transition)",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "Validating..." : "Validate"}
          </button>
        </Card>

        <Card style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
          {loading && <LoadingOverlay message="Evaluating pipeline..." />}
          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
          {scorecard && !loading && <ScorecardGauge scorecard={scorecard} />}
          {!scorecard && !loading && !error && (
            <div style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 12, textAlign: "center" }}>
              Paste ADF JSON and click Validate
              <br />
              to see the Conversion Confidence Score
            </div>
          )}
        </Card>
      </div>

      {scorecard && !loading && (
        <Card style={{ animation: "fadeInUp 0.5s ease 0.2s both" }}>
          <DimensionBreakdown dimensions={scorecard.dimensions} />
        </Card>
      )}
    </div>
  );
}
