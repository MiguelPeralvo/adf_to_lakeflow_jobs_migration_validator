import React from "react";

import { ScorecardCard } from "../components/ScorecardCard";

export function ValidatePage() {
  return (
    <main>
      <h1>Validate Conversion</h1>
      <ScorecardCard score={0} label="REVIEW_RECOMMENDED" />
    </main>
  );
}
