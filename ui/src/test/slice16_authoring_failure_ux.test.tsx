import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OperationProgress } from "../components/OperationProgress";
import type { Operation } from "../api/types";
import {
  messageForGoldSafeReason,
} from "../features/goldLab/errors/goldLabErrors";
import {
  goldBootstrapOperationFailureMessage,
  managedOperationFailureMessage,
} from "../features/operations/operationErrorMessages";

const EXACT = {
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
  bootstrap_internal_failure:
    "Baseline creation failed unexpectedly. No baseline was published.",
} as const;

describe("S16 closure authoring-failure UX copy", () => {
  it("messageForGoldSafeReason returns the five frozen operator strings", () => {
    for (const [reason, copy] of Object.entries(EXACT)) {
      if (reason === "bootstrap_internal_failure") continue;
      expect(messageForGoldSafeReason(reason)).toBe(copy);
    }
  });

  it("preserves existing bootstrap_internal_failure copy", () => {
    expect(messageForGoldSafeReason("bootstrap_internal_failure")).toBe(
      EXACT.bootstrap_internal_failure,
    );
  });

  it("gold bootstrap mapper returns exact auth/timeout/http/zero strings", () => {
    expect(
      goldBootstrapOperationFailureMessage({
        code: "gold_conflict",
        details: { reason: "authoring_authentication_failed" },
      }),
    ).toBe(EXACT.authoring_authentication_failed);
    expect(
      goldBootstrapOperationFailureMessage({
        code: "gold_conflict",
        details: { reason: "authoring_request_timeout" },
      }),
    ).toBe(EXACT.authoring_request_timeout);
    expect(
      goldBootstrapOperationFailureMessage({
        code: "gold_conflict",
        details: { reason: "authoring_http_error" },
      }),
    ).toBe(EXACT.authoring_http_error);
    expect(
      goldBootstrapOperationFailureMessage({
        code: "gold_conflict",
        details: { reason: "zero_usable_proposals" },
      }),
    ).toBe(EXACT.zero_usable_proposals);
  });

  it("renders unreachable copy and never zero_usable_proposals text", () => {
    const operation = {
      operation_id: "wop_unreachable",
      kind: "gold_lab_baseline_bootstrap",
      workspace_id: "ws_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      expected_revision: null,
      status: "failed",
      progress_stage: "proposing",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:01Z",
      result: null,
      error: {
        code: "gold_conflict",
        message: "SENTINEL_MUST_NOT_SURFACE",
        retryable: false,
        details: { reason: "authoring_endpoint_unreachable" },
      },
    } as Operation;

    expect(managedOperationFailureMessage(operation)).toBe(
      EXACT.authoring_endpoint_unreachable,
    );

    render(<OperationProgress phase="operation" operation={operation} />);
    expect(
      screen.getByRole("alert"),
    ).toHaveTextContent(EXACT.authoring_endpoint_unreachable);
    expect(screen.queryByText(/completed its calls/i)).toBeNull();
    expect(screen.queryByText("SENTINEL_MUST_NOT_SURFACE")).toBeNull();
  });
});
