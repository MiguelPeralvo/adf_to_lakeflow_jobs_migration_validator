import React, { useState } from "react";
import type { DimensionResult } from "../types";

const LABELS: Record<string, string> = {
  activity_coverage: "Activity Coverage",
  expression_coverage: "Expression Coverage",
  dependency_preservation: "Dependency Preservation",
  notebook_validity: "Notebook Validity",
  parameter_completeness: "Parameter Completeness",
  secret_completeness: "Secret Completeness",
  not_translatable_ratio: "Translatable Ratio",
  semantic_equivalence: "Semantic Equivalence",
  runtime_success: "Runtime Success",
  parallel_equivalence: "Parallel Equivalence",
};

function barColor(score: number, passed: boolean): string {
  if (!passed) return "var(--red)";
  if (score >= 0.9) return "var(--green)";
  if (score >= 0.7) return "var(--amber)";
  return "var(--red)";
}

function DetailBlock({ details }: { details: Record<string, unknown> }) {
  const entries = Object.entries(details).filter(
    ([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0)
  );
  if (entries.length === 0) return <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>No details</span>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {entries.map(([key, value]) => (
        <div key={key} style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-muted)",
              minWidth: 140,
              flexShrink: 0,
            }}
          >
            {key}
          </span>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              color: "var(--text-secondary)",
              wordBreak: "break-all",
            }}
          >
            {typeof value === "object" ? JSON.stringify(value, null, 0) : String(value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function DimensionRow({
  name,
  result,
  delay,
}: {
  name: string;
  result: DimensionResult;
  delay: number;
}) {
  const [open, setOpen] = useState(false);
  const pct = Math.round(result.score * 100);
  const color = barColor(result.score, result.passed);

  return (
    <div
      style={{
        animation: `slideIn 0.4s ease ${delay}ms both`,
        borderBottom: "1px solid var(--border)",
        padding: "14px 0",
      }}
    >
      <div
        onClick={() => setOpen(!open)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        <span
          style={{
            width: 18,
            height: 18,
            borderRadius: "50%",
            background: result.passed ? "var(--green-dim)" : "var(--red-dim)",
            border: `1.5px solid ${result.passed ? "var(--green)" : "var(--red)"}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 10,
            flexShrink: 0,
          }}
        >
          {result.passed ? "\u2713" : "\u2717"}
        </span>

        <span
          style={{
            fontFamily: "var(--font-body)",
            fontWeight: 500,
            fontSize: 13,
            color: "var(--text-primary)",
            width: 180,
            flexShrink: 0,
          }}
        >
          {LABELS[name] || name}
        </span>

        <div
          style={{
            flex: 1,
            height: 6,
            background: "var(--border)",
            borderRadius: 3,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${pct}%`,
              background: color,
              borderRadius: 3,
              animation: `barGrow 0.8s cubic-bezier(0.22, 1, 0.36, 1) ${delay + 100}ms both`,
              boxShadow: `0 0 8px ${color}44`,
            }}
          />
        </div>

        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 13,
            fontWeight: 600,
            color,
            width: 45,
            textAlign: "right",
            flexShrink: 0,
          }}
        >
          {pct}%
        </span>

        <span
          style={{
            fontSize: 10,
            color: "var(--text-muted)",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform var(--transition)",
            flexShrink: 0,
          }}
        >
          \u25BC
        </span>
      </div>

      {open && (
        <div
          style={{
            marginTop: 10,
            marginLeft: 32,
            padding: "12px 16px",
            background: "var(--bg-base)",
            borderRadius: "var(--radius)",
            border: "1px solid var(--border)",
          }}
        >
          <DetailBlock details={result.details} />
        </div>
      )}
    </div>
  );
}

export function DimensionBreakdown({
  dimensions,
}: {
  dimensions: Record<string, DimensionResult>;
}) {
  const sorted = Object.entries(dimensions).sort(([, a], [, b]) => a.score - b.score);

  return (
    <div>
      <h3
        style={{
          fontFamily: "var(--font-display)",
          fontSize: 14,
          fontWeight: 600,
          color: "var(--text-secondary)",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          marginBottom: 8,
        }}
      >
        Dimension Breakdown
      </h3>
      {sorted.map(([name, result], i) => (
        <DimensionRow key={name} name={name} result={result} delay={i * 60} />
      ))}
    </div>
  );
}
