import React from "react";
import type { Scorecard } from "../types";

const SIZE = 200;
const STROKE = 14;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function scoreColor(score: number): string {
  if (score >= 90) return "var(--green)";
  if (score >= 70) return "var(--amber)";
  return "var(--red)";
}

function labelBadge(label: string): { text: string; bg: string; fg: string } {
  switch (label) {
    case "HIGH_CONFIDENCE":
      return { text: "High Confidence", bg: "var(--green-dim)", fg: "var(--green)" };
    case "REVIEW_RECOMMENDED":
      return { text: "Review Recommended", bg: "var(--amber-dim)", fg: "var(--amber)" };
    default:
      return { text: "Manual Intervention", bg: "var(--red-dim)", fg: "var(--red)" };
  }
}

export function ScorecardGauge({ scorecard }: { scorecard: Scorecard }) {
  const pct = Math.max(0, Math.min(100, scorecard.score));
  const offset = CIRCUMFERENCE - (pct / 100) * CIRCUMFERENCE;
  const color = scoreColor(pct);
  const badge = labelBadge(scorecard.label);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
      <svg
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ transform: "rotate(-90deg)", filter: `drop-shadow(0 0 18px ${color}33)` }}
      >
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="var(--border)"
          strokeWidth={STROKE}
        />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          style={{
            // @ts-expect-error CSS custom properties for animation
            "--circumference": CIRCUMFERENCE,
            "--dash-offset": offset,
            animation: "gaugeReveal 1.2s cubic-bezier(0.22, 1, 0.36, 1) forwards",
          }}
        />
        <text
          x={SIZE / 2}
          y={SIZE / 2}
          textAnchor="middle"
          dominantBaseline="central"
          style={{
            transform: "rotate(90deg)",
            transformOrigin: "center",
            fontFamily: "var(--font-display)",
            fontSize: 48,
            fontWeight: 700,
            fill: "var(--text-primary)",
          }}
        >
          {Math.round(pct)}
        </text>
      </svg>

      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          fontWeight: 500,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          padding: "5px 14px",
          borderRadius: 20,
          background: badge.bg,
          color: badge.fg,
          border: `1px solid ${badge.fg}22`,
        }}
      >
        {badge.text}
      </span>
    </div>
  );
}
