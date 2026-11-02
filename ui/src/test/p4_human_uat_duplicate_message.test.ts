import { describe, expect, it } from "vitest";

import {
  ApiError,
  messageForDocumentInvalidReason,
  messageForUploadSizeReason,
  userFacingErrorMessage,
} from "../api/errors";
import { managedOperationFailureMessage } from "../features/operations/operationErrorMessages";
import { operation as makeOperation } from "./mockApi";

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
    const operation = makeOperation({
      operation_id: "op_duplicate",
      status: "failed",
      error: {
        code: "document_invalid",
        message: "Submitted document is invalid",
        retryable: false,
        details: { reason: "document_identity_conflict" },
      },
    });
    expect(managedOperationFailureMessage(operation)).toBe(
      "This document is already present in this workspace.",
    );
  });

  it("explains how to recover from an OCR-required source failure", () => {
    const expected =
      "This PDF contains no extractable text. OCR is not enabled in this installation. Convert the PDF to a searchable document using an OCR tool, then upload it again.";
    expect(messageForDocumentInvalidReason("ocr_required")).toBe(expected);
    const operation = makeOperation({
      operation_id: "op_ocr",
      status: "failed",
      error: {
        code: "document_invalid",
        message: "Submitted document is invalid",
        retryable: false,
        details: { reason: "ocr_required" },
      },
    });
    expect(managedOperationFailureMessage(operation)).toBe(expected);
  });

  it("maps per-file and aggregate upload-size rejections separately", () => {
    const perFile =
      "A file exceeds its per-file upload limit. Reduce it to the limit shown above. For PDFs, compress or optimize them, or split them into smaller PDFs while preserving searchable text when possible.";
    const aggregate =
      "This upload request exceeds the combined size limit. Upload fewer files at a time.";
    expect(messageForUploadSizeReason("source_file_too_large")).toBe(perFile);
    expect(messageForUploadSizeReason("request_too_large")).toBe(aggregate);

    expect(
      userFacingErrorMessage(
        new ApiError({
          kind: "api",
          code: "document_invalid",
          message: "Submitted document is invalid",
          details: { reason: "source_file_too_large" },
        }),
      ),
    ).toBe(perFile);
    expect(
      userFacingErrorMessage(
        new ApiError({
          kind: "api",
          code: "request_invalid",
          message: "Request is invalid",
          details: { reason: "request_too_large" },
        }),
      ),
    ).toBe(aggregate);

    const operation = makeOperation({
      operation_id: "op_upload_size",
      status: "failed",
      error: {
        code: "document_invalid",
        message: "Submitted document is invalid",
        retryable: false,
        details: { reason: "source_file_too_large" },
      },
    });
    expect(managedOperationFailureMessage(operation)).toBe(perFile);
  });
});
