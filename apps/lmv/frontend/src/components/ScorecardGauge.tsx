import React from "react";
import type { Scorecard } from "../types";

function scoreColor(score: number): string {
  if (score >= 90) return "#27e199";
  if (score >= 70) return "#ffb547";
  return "#ff5c5c";
}

function labelText(label: string): { text: string; color: string } {
  switch (label) {
    case "HIGH_CONFIDENCE":
      return { text: "OPTIMAL", color: "#27e199" };
    case "REVIEW_RECOMMENDED":
      return { text: "REVIEW NEEDED", color: "#ffb547" };
    default:
      return { text: "CRITICAL", color: "#ff5c5c" };
  }
}

export function ScorecardGauge({
  scorecard,
  size = 200,
}: {
  scorecard: Scorecard;
  size?: number;
}) {
  const pct = Math.max(0, Math.min(100, scorecard.score));
  const r = (size - 16) / 2;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (pct / 100) * circumference;
  const color = scoreColor(pct);
  const badge = labelText(scorecard.label);
  const cx = size / 2;

  return (
    <div className="flex flex-col items-center space-y-4">
      <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
        <svg className="w-full h-full transform -rotate-90">
          <circle
            className="text-surface-container-highest"
            cx={cx}
            cy={cx}
            r={r}
            fill="transparent"
            stroke="currentColor"
            strokeWidth={8}
          />
          <circle
            cx={cx}
            cy={cx}
            r={r}
            fill="transparent"
            stroke={color}
            strokeWidth={12}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{
              transition: "stroke-dashoffset 1.2s cubic-bezier(0.22, 1, 0.36, 1)",
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-6xl font-bold font-headline text-white">
            {Math.round(pct)}
          </span>
          <span className="font-mono text-xs text-slate-500 tracking-tighter">/ 100</span>
        </div>
      </div>
      <div
        className="machined-chip px-4 py-1.5 rounded-sm"
        style={{ borderColor: badge.color }}
      >
        <span
          className="font-mono text-[10px] font-bold uppercase tracking-widest"
          style={{ color: badge.color }}
        >
          {badge.text}
        </span>
      </div>
    </div>
  );
}

/** Small inline gauge for tables/lists */
export function MiniGauge({ value, size = 48 }: { value: number; size?: number }) {
  const r = (size - 8) / 2;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (value / 100) * circumference;
  const color = scoreColor(value);
  const cx = size / 2;

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg className="w-full h-full -rotate-90">
        <circle
          className="text-surface-container-highest"
          cx={cx} cy={cx} r={r} fill="transparent" stroke="currentColor" strokeWidth={3}
        />
        <circle
          cx={cx} cy={cx} r={r} fill="transparent" stroke={color}
          strokeWidth={3} strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset}
        />
      </svg>
      <span className="absolute text-xs font-bold font-mono" style={{ color }}>
        {Math.round(value)}
      </span>
    </div>
  );
}
