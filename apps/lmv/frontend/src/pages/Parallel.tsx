import React from "react";

import { ParallelComparisonTable } from "../components/ParallelComparisonTable";

const demoRows = [
  { activity_name: "task_a", match: true, diff: null },
  { activity_name: "task_b", match: false, diff: "normalized outputs differ" },
];

export function ParallelPage() {
  return (
    <main>
      <h1>Parallel Run</h1>
      <p>POST /api/parallel/run</p>
      <ParallelComparisonTable rows={demoRows} />
    </main>
  );
}
