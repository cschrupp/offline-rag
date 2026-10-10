import { isApiError, userFacingErrorMessage } from "../../../api/errors";

const GOLD_LAB_MESSAGES: Record<string, string> = {
  request_invalid:
    "Check the form fields and try again. One or more values are not accepted.",
  gold_project_unknown: "Gold project not found.",
  gold_campaign_unknown: "Gold campaign not found.",
  gold_baseline_unknown:
    "The selected baseline is no longer available for this project. Refresh and choose another eligible baseline.",
  gold_conflict:
    "This Gold Lab resource changed since you last loaded it. Refresh, then try again.",
  gold_state_unavailable:
    "Gold Lab state is temporarily unavailable. Reload the page. Do not continue with this action until state can be trusted.",
  unexpected_response:
    "Received an unexpected Gold Lab response. Reload and try again.",
  internal_error: "Something went wrong in Gold Lab. Try again later.",
  network_error:
    "Could not reach OfflineRAG. Check that this installation is running and reachable.",
};

export function goldLabErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    const mapped = GOLD_LAB_MESSAGES[error.code];
    if (mapped) return mapped;
    if (error.code === "network_error") {
      return GOLD_LAB_MESSAGES.network_error;
    }
  }
  const fallback = userFacingErrorMessage(error);
  if (fallback && fallback !== "Something went wrong.") {
    return fallback;
  }
  return GOLD_LAB_MESSAGES.internal_error;
}

export function isGoldStateUnavailable(error: unknown): boolean {
  return isApiError(error) && error.code === "gold_state_unavailable";
}
