export interface DimensionResult {
  score: number;
  passed: boolean;
  details: Record<string, unknown>;
}

export interface Scorecard {
  entity_id?: string;
  score: number;
  label: "HIGH_CONFIDENCE" | "REVIEW_RECOMMENDED" | "MANUAL_INTERVENTION";
  dimensions: Record<string, DimensionResult>;
}

export interface HarnessResult {
  entity_id?: string;
  pipeline_name: string;
  scorecard: Scorecard;
  iterations: number;
  fix_suggestions: Array<Record<string, unknown>>;
}

export interface ComparisonRow {
  activity_name: string;
  adf_output: string | null;
  databricks_output: string | null;
  match: boolean;
  diff: string | null;
}

export interface ParallelResult {
  entity_id?: string;
  pipeline_name: string;
  equivalence_score: number;
  comparisons: ComparisonRow[];
  scorecard: Scorecard;
}

export interface HistoryEntry {
  entity_id?: string;
  pipeline_name: string;
  timestamp: string;
  scorecard: Scorecard;
}

export interface ExpressionResult {
  entity_id?: string;
  score: number;
  reasoning: string;
  adf_expression: string;
  python_code: string;
}

/** Summary returned by GET /api/entities — metadata only, no full results. */
export interface EntitySummary {
  entity_id: string;
  type: string;
  timestamp: string;
  pipeline_name?: string;
  scorecard?: { score: number; label: string };
  // batch
  folder?: string;
  total?: number;
  mean_score?: number;
  // expression
  adf_expression?: string;
  score?: number;
  // synthetic
  output_path?: string;
  count?: number;
  mode?: string;
  // harness
  iterations?: number;
  // parallel
  equivalence_score?: number;
}
