export const ACTIVE_OPERATIONS_KEY = "offline-rag.active-operations.v1";

export type ActiveOperationRef = {
  operation_id: string;
  workspace_id: string;
  kind: string;
  label?: string;
};

function isActiveOperationRef(value: unknown): value is ActiveOperationRef {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.operation_id === "string" &&
    typeof item.workspace_id === "string" &&
    typeof item.kind === "string" &&
    (item.label === undefined || typeof item.label === "string")
  );
}

export function loadActiveOperations(): ActiveOperationRef[] {
  try {
    const raw = localStorage.getItem(ACTIVE_OPERATIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isActiveOperationRef);
  } catch {
    return [];
  }
}

export function saveActiveOperations(items: ActiveOperationRef[]): void {
  localStorage.setItem(ACTIVE_OPERATIONS_KEY, JSON.stringify(items));
}

export function rememberActiveOperation(ref: ActiveOperationRef): void {
  const current = loadActiveOperations().filter(
    (item) => item.operation_id !== ref.operation_id,
  );
  current.push(ref);
  saveActiveOperations(current);
}

export function forgetActiveOperation(operationId: string): void {
  saveActiveOperations(
    loadActiveOperations().filter((item) => item.operation_id !== operationId),
  );
}

export function isTerminalOperationStatus(status: string): boolean {
  return status === "succeeded" || status === "failed" || status === "interrupted";
}
