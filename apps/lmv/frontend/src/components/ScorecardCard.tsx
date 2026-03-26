import React from "react";

type ScorecardCardProps = {
  score: number;
  label: string;
};

export function ScorecardCard({ score, label }: ScorecardCardProps) {
  return (
    <section>
      <h2>Conversion Confidence Score</h2>
      <p>{score.toFixed(2)}</p>
      <p>{label}</p>
    </section>
  );
}
