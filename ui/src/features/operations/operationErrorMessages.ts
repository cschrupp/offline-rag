import type { Operation } from "../../api/types";
import { messageForDocumentInvalidReason } from "../../api/errors";
import { messageForGoldSafeReason } from "../goldLab/errors/goldLabErrors";

const GOLD_BOOTSTRAP_CODE_FALLBACKS: Record<string, string> = {
  gold_conflict:
    "Gold Lab could not complete baseline creation because its state conflicted with the requested operation.",
  gold_state_unavailable:
    "Gold Lab state could not be verified. Reload before continuing.",
  workspace_conflict:
    "The workspace changed while baseline creation was running. Refresh before trying again.",
  internal_error:
    "Baseline creation failed unexpectedly. No baseline was published.",
};

const GENERIC_GOLD_BOOTSTRAP_FAILURE =
  "Gold Lab could not complete baseline creation. No baseline was published.";

export function isCudaMemoryExhaustedFailure(operation: Operation): boolean {
  const reason = operation.error?.details?.reason;
  return typeof reason === "string" && reason === "cuda_memory_exhausted";
}

/**
 * Product-facing failure copy for a durable managed operation card.
 * Gold baseline bootstrap never surfaces raw codes, reason identifiers, or
 * arbitrary backend messages when a bounded mapping exists.
 */
export function managedOperationFailureMessage(operation: Operation): string {
  const error = operation.error;
  if (!error) {
    return "Operation failed.";
  }

  if (String(operation.kind) === "gold_lab_baseline_bootstrap") {
    return goldBootstrapOperationFailureMessage(error);
  }

  if (isCudaMemoryExhaustedFailure(operation)) {
    return "GPU memory was exhausted while building semantic search.";
  }

  const code = String(error.code ?? "")
    .trim()
    .toLowerCase();
  if (code === "document_invalid") {
    const mapped = messageForDocumentInvalidReason(error.details?.reason);
    if (mapped) {
      return mapped;
    }
  }

  const message = typeof error.message === "string" ? error.message.trim() : "";
  return message || "Operation failed.";
}

export function goldBootstrapOperationFailureMessage(error: {
  code: string;
  message?: string;
  details?: Record<string, unknown> | null;
}): string {
  const reasonRaw = error.details?.reason;
  const reason =
    typeof reasonRaw === "string" && reasonRaw.trim() ? reasonRaw.trim() : null;
  if (reason) {
    const mapped = messageForGoldSafeReason(reason);
    if (mapped) return mapped;
    // Unknown reason identifiers must not be echoed.
  }

  const code = String(error.code ?? "")
    .trim()
    .toLowerCase();
  if (code && GOLD_BOOTSTRAP_CODE_FALLBACKS[code]) {
    return GOLD_BOOTSTRAP_CODE_FALLBACKS[code];
  }
  return GENERIC_GOLD_BOOTSTRAP_FAILURE;
}
