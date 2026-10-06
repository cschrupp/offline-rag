import type { ErrorEnvelope } from "./types";

export type ApiErrorKind = "api" | "network" | "unexpected";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly code: string;
  readonly retryable: boolean;
  readonly status: number | null;
  readonly details: Record<string, unknown> | null;
  readonly traceId: string | null;

  constructor(params: {
    kind: ApiErrorKind;
    code: string;
    message: string;
    retryable?: boolean;
    status?: number | null;
    details?: Record<string, unknown> | null;
    traceId?: string | null;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.kind = params.kind;
    this.code = params.code;
    this.retryable = params.retryable ?? false;
    this.status = params.status ?? null;
    this.details = params.details ?? null;
    this.traceId = params.traceId ?? null;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function parseErrorEnvelope(
  payload: unknown,
  status: number,
): ApiError | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const body = payload as Partial<ErrorEnvelope>;
  if (!body.error || typeof body.error.code !== "string") {
    return null;
  }
  return new ApiError({
    kind: "api",
    code: body.error.code,
    message:
      typeof body.error.message === "string" && body.error.message.trim()
        ? body.error.message
        : "Request failed",
    retryable: Boolean(body.retryable),
    status,
    details:
      body.details && typeof body.details === "object"
        ? (body.details as Record<string, unknown>)
        : null,
    traceId: typeof body.trace_id === "string" ? body.trace_id : null,
  });
}

export function userFacingErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    switch (error.code) {
      case "workspace_conflict":
        return "This workspace changed since you last loaded it. Review the updated state, then submit again.";
      case "service_overloaded":
        return "System is busy. No work was queued.";
      case "idempotency_conflict":
        return "This request conflicts with a different earlier action using the same idempotency key.";
      case "workspace_state_unavailable":
        return "Workspace state is temporarily unavailable. Reload the page or recover the service, then try again.";
      case "workspace_unknown":
        return "Workspace not found.";
      case "source_unknown":
        return "Source not found in this workspace.";
      case "operation_unknown":
        return "Managed operation not found.";
      case "network_error":
        return "Could not reach OfflineRAG. Check that this installation is running and reachable.";
      default:
        return error.message;
    }
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return "Something went wrong.";
}
