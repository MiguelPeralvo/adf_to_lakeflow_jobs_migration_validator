import React from "react";

type Comparison = {
  row_id: string;
  activity_name: string;
  match: boolean;
  diff: string | null;
};

type ParallelComparisonTableProps = {
  rows: Comparison[];
};

export function ParallelComparisonTable({ rows }: ParallelComparisonTableProps) {
  return (
    <table>
      <thead>
        <tr>
          <th>Activity</th>
          <th>Match</th>
          <th>Diff</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.row_id}>
            <td>{row.activity_name}</td>
            <td>{String(row.match)}</td>
            <td>{row.diff ?? ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
