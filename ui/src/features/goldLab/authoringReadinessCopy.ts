/**
 * Product-language mapping for Gold Lab authoring readiness reason codes.
 * API may expose bounded codes; ordinary UI must not render raw identifiers.
 */

const AUTHORING_REASON_MESSAGES: Record<string, string> = {
  disabled: "Gold Lab authoring is disabled.",
  model_unset: "No authoring model is configured.",
  model_not_approved: "The selected model is not approved.",
  endpoint_not_configured: "No authoring server is configured.",
  endpoint_not_approved: "The authoring server is not approved.",
  network_policy_violation:
    "The authoring server is outside the permitted network boundary.",
  public_address_not_allowed:
    "The authoring server is outside the permitted network boundary.",
  unsupported_provider: "Gold Lab authoring is not ready.",
  unsupported_adapter: "Gold Lab authoring is not ready.",
  unsupported_contract: "Gold Lab authoring is not ready.",
};

const GENERIC_NOT_READY = "Gold Lab authoring is not ready.";

export function authoringReadinessStatusText(params: {
  ready: boolean;
  reasonCodes?: string[] | null;
}): string {
  if (params.ready) {
    return "Gold Lab authoring is ready.";
  }
  const codes = (params.reasonCodes ?? []).filter(
    (code): code is string => typeof code === "string" && code.trim().length > 0,
  );
  if (codes.length === 0) {
    return GENERIC_NOT_READY;
  }
  const mapped = codes
    .map((code) => AUTHORING_REASON_MESSAGES[code])
    .filter((text): text is string => Boolean(text));
  if (mapped.length === 0) {
    return GENERIC_NOT_READY;
  }
  // Preserve order; de-duplicate identical product sentences.
  const unique: string[] = [];
  for (const text of mapped) {
    if (!unique.includes(text)) unique.push(text);
  }
  return unique.join(" ");
}
