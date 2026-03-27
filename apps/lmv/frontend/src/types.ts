export interface DimensionResult {
  score: number;
  passed: boolean;
  details: Record<string, unknown>;
}

export interface Scorecard {
  score: number;
  label: "HIGH_CONFIDENCE" | "REVIEW_RECOMMENDED" | "MANUAL_INTERVENTION";
  dimensions: Record<string, DimensionResult>;
}

export interface HarnessResult {
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
  pipeline_name: string;
  equivalence_score: number;
  comparisons: ComparisonRow[];
  scorecard: Scorecard;
}

export interface HistoryEntry {
  pipeline_name: string;
  timestamp: string;
  scorecard: Scorecard;
}
