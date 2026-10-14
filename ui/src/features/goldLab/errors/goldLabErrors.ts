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
    "Could not reach Seneca. Check that this installation is running and reachable.",
};

/** Bounded safe-reason vocabulary shared by sync API errors and operation cards. */
const SAFE_REASON_MESSAGES: Record<string, string> = {
  authoring_not_ready:
    "Gold Lab authoring is not ready. Configure it in Settings and restart if required.",
  authoring_endpoint_unauthorized:
    "The configured Gold Lab authoring server is not authorized by the active network policy.",
  project_archived: "Archived projects cannot accept this Gold Lab action.",
  project_status_invalid:
    "This Gold project is not in a state that allows the requested action.",
  proposal_count_exceeds_eligible_population:
    "The requested proposal count is larger than the eligible workspace population. Reduce the proposal count and try again.",
  authoring_authentication_failed:
    "The configured Gold Lab authoring server rejected authentication or authorization. Check the authoring API key and Settings, then try again.",
  authoring_request_timeout:
    "The Gold Lab authoring server did not respond in time. Confirm the server is running and reachable, then try again.",
  authoring_endpoint_unreachable:
    "Seneca could not reach the configured Gold Lab authoring server. Confirm the endpoint in Settings and that the server is running, then try again.",
  authoring_http_error:
    "The configured Gold Lab authoring endpoint returned a response Seneca could not accept. Check authoring Settings and server logs, then try again.",
  zero_usable_proposals:
    "Gold Lab authoring completed its calls but did not produce usable candidate questions from this workspace publication.",
  zero_reviewable_cases:
    "Candidate questions were produced, but no reviewable evidence cases could be assembled from this workspace publication.",
  pooling_artifact_unavailable:
    "Gold Lab could not prepare the retrieval artifacts required to assemble evidence for this baseline. No baseline was published.",
  prelabel_stage_cannot_start:
    "Advisory prelabeling could not start for this baseline attempt.",
  publication_drift_before_commit:
    "The workspace publication changed while the baseline was being created. Refresh and try again.",
  project_drift_before_commit:
    "The Gold project changed while the baseline was being created. Refresh and try again.",
  staged_run_invalid:
    "Gold Lab could not verify the staged baseline state. Reload before continuing.",
  historical_identity_failure:
    "Gold Lab could not verify historical evidence identity for this baseline. Reload before continuing.",
  canonical_destination_conflict:
    "Gold Lab detected a baseline-state conflict and did not overwrite existing canonical state.",
  bootstrap_internal_failure:
    "Baseline creation failed unexpectedly. No baseline was published.",
};

const MISSING_RESOURCE_MESSAGE = "Gold Lab resource not found.";

function isMissingResourceCode(code: string): boolean {
  return code === "not_found" || code.endsWith("_unknown");
}

function safeReasonFromError(error: unknown): string | null {
  if (!isApiError(error) || !error.details || typeof error.details !== "object") {
    return null;
  }
  const reason = error.details.reason;
  return typeof reason === "string" && reason.trim() ? reason.trim() : null;
}

/** Pure mapper for accepted Gold safe-reason codes. Unknown → null. */
export function messageForGoldSafeReason(reason: string): string | null {
  const key = reason.trim();
  if (!key) return null;
  return SAFE_REASON_MESSAGES[key] ?? null;
}

/**
 * Gold Lab UI error text. Never surfaces raw backend exception / ApiError.message.
 */
export function goldLabErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    const reason = safeReasonFromError(error);
    if (reason) {
      const mapped = messageForGoldSafeReason(reason);
      if (mapped) return mapped;
    }
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
