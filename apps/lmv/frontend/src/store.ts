/** Cross-page shared state for the LMV app. */

export interface PendingValidation {
  pipeline_name: string;
  adf_json: Record<string, unknown>;
  source: "synthetic";
}

let _pending: PendingValidation | null = null;

export function setPendingValidation(data: PendingValidation): void {
  _pending = data;
}

export function consumePendingValidation(): PendingValidation | null {
  const data = _pending;
  _pending = null;
  return data;
}
