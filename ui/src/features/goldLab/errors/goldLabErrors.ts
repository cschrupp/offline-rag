import { isApiError } from "../../../api/errors";

const GOLD_LAB_MESSAGES: Record<string, string> = {
  request_invalid:
    "Check the form fields and try again. One or more values are not accepted.",
  not_found: "Gold Lab resource not found.",
  gold_project_unknown: "Gold project not found.",
  gold_campaign_unknown: "Gold campaign not found.",
  gold_task_unknown: "Gold task not found.",
  gold_baseline_unknown:
    "The selected baseline is no longer available for this project. Refresh and choose another eligible baseline.",
  gold_conflict:
    "This Gold Lab resource changed since you last loaded it. Refresh, then try again.",
  gold_state_unavailable:
    "Gold Lab state is temporarily unavailable. Reload the page. Do not continue with this action until state can be trusted.",
  gold_busy:
    "Gold Lab is busy. Retry the same commit when ready; do not change the answer yet.",
  idempotency_conflict:
    "This commit key is already bound to a different earlier attempt. Reload and reconcile state before correcting.",
  unexpected_response:
    "Received an unexpected Gold Lab response. Reload and try again.",
  internal_error: "Something went wrong in Gold Lab. Try again later.",
  network_error:
    "Could not reach OfflineRAG. Check that this installation is running and reachable.",
};

const MISSING_RESOURCE_MESSAGE = "Gold Lab resource not found.";

function isMissingResourceCode(code: string): boolean {
  return code === "not_found" || code.endsWith("_unknown");
}

/**
 * Gold Lab UI error text. Never surfaces raw backend exception / ApiError.message.
 */
export function goldLabErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    const mapped = GOLD_LAB_MESSAGES[error.code];
    if (mapped) return mapped;
    if (isMissingResourceCode(error.code)) {
      return MISSING_RESOURCE_MESSAGE;
    }
    return GOLD_LAB_MESSAGES.internal_error;
  }
  return GOLD_LAB_MESSAGES.internal_error;
}

export function isGoldStateUnavailable(error: unknown): boolean {
  return isApiError(error) && error.code === "gold_state_unavailable";
}

export function isAmbiguousTransportError(error: unknown): boolean {
  return isApiError(error) && error.code === "network_error";
}

export function isRetryableSameIntentError(error: unknown): boolean {
  return isApiError(error) && (error.code === "gold_busy" || error.retryable);
}

export function isIdempotencyConflict(error: unknown): boolean {
  return isApiError(error) && error.code === "idempotency_conflict";
}
