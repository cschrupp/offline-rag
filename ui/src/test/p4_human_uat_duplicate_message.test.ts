import { describe, expect, it } from "vitest";

import {
  ApiError,
  messageForDocumentInvalidReason,
  userFacingErrorMessage,
} from "../api/errors";
import { managedOperationFailureMessage } from "../features/operations/operationErrorMessages";
import type { Operation } from "../api/types";

describe("P4 human-UAT duplicate document messaging", () => {
  it("maps document_identity_conflict on API errors", () => {
    expect(messageForDocumentInvalidReason("document_identity_conflict")).toBe(
      "This document is already present in this workspace.",
    );
    const err = new ApiError({
      kind: "api",
      code: "document_invalid",
      message: "Submitted document is invalid",
      details: { reason: "document_identity_conflict" },
    });
    expect(userFacingErrorMessage(err)).toBe(
      "This document is already present in this workspace.",
    );
  });

  it("keeps generic invalid copy for non-duplicate reasons", () => {
    const err = new ApiError({
      kind: "api",
      code: "document_invalid",
      message: "Submitted document is invalid",
      details: { reason: "document_unparseable" },
    });
    expect(userFacingErrorMessage(err)).toBe("Submitted document is invalid");
  });

  it("maps document_identity_conflict on managed operations", () => {
    const operation = {
      kind: "source_add",
      status: "failed",
      error: {
        code: "document_invalid",
        message: "Submitted document is invalid",
        details: { reason: "document_identity_conflict" },
      },
    } as Operation;
    expect(managedOperationFailureMessage(operation)).toBe(
      "This document is already present in this workspace.",
    );
  });

  it("explains how to recover from an OCR-required source failure", () => {
    const expected =
      "This PDF contains no extractable text. OCR is not enabled in this installation. Convert the PDF to a searchable document using an OCR tool, then upload it again.";
    expect(messageForDocumentInvalidReason("ocr_required")).toBe(expected);
    const operation = {
      kind: "source_add",
      status: "failed",
      error: {
        code: "document_invalid",
        message: "Submitted document is invalid",
        details: { reason: "ocr_required" },
      },
    } as Operation;
    expect(managedOperationFailureMessage(operation)).toBe(expected);
  });
});
