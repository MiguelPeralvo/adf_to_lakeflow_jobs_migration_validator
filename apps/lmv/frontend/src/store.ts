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

/** Cross-page: pass a folder path to the Batch Validation page. */
let _pendingBatchFolder: string | null = null;

export function setPendingBatchFolder(path: string): void {
  _pendingBatchFolder = path;
}

export function consumePendingBatchFolder(): string | null {
  const p = _pendingBatchFolder;
  _pendingBatchFolder = null;
  return p;
}

/** Navigate to an entity detail view by page + entity ID. */
export function navigateToEntity(page: string, entityId: string): void {
  window.location.hash = `#/${page}/${entityId}`;
}

/** Map backend event types to frontend page names. */
export const TYPE_TO_PAGE: Record<string, string> = {
  validation: "validate",
  expression: "expression",
  harness: "harness",
  parallel: "parallel",
  batch_validation: "batch",
  synthetic_generation: "synthetic",
};
