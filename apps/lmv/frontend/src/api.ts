import type { Scorecard, HarnessResult, ParallelResult, HistoryEntry } from "./types";

const BASE = "/api";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  validate(payload: { adf_json?: object; adf_yaml?: string; snapshot?: object; pipeline_name?: string }): Promise<Scorecard> {
    return post("/validate", payload);
  },
  validateExpression(adf_expression: string, python_code: string) {
    return post<{ score: number; reasoning: string }>("/validate/expression", { adf_expression, python_code });
  },
  harnessRun(pipeline_name: string): Promise<HarnessResult> {
    return post("/harness/run", { pipeline_name });
  },
  parallelRun(pipeline_name: string, parameters: Record<string, string> = {}): Promise<ParallelResult> {
    return post("/parallel/run", { pipeline_name, parameters });
  },
  history(pipeline_name: string): Promise<HistoryEntry[]> {
    return get(`/history/${encodeURIComponent(pipeline_name)}`);
  },
};
