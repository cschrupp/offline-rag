import { describe, expect, it } from "vitest";

import { ApiError, userFacingErrorMessage } from "../api/errors";
import { managedOperationFailureMessage } from "../features/operations/operationErrorMessages";
import { operation } from "./mockApi";

describe("ingestion resource errors", () => {
  it.each([
    ["large_pdf_host_memory_insufficient", /available RAM.*large PDFs/],
    ["ingest_capacity_exhausted", /ingestion jobs.*Wait/],
    ["storage_insufficient", /disk space.*data drive/],
    ["memory_telemetry_unavailable", /could not verify available memory/],
  ])("explains %s for admission and managed failures", (reason, explanation) => {
    const details = { reason };
    const code = "service_overloaded";
    const message = "Service is temporarily overloaded";
    const error = { code, message, details, retryable: true };
    expect(userFacingErrorMessage(new ApiError({ kind: "api", ...error }))).toMatch(explanation);
    expect(managedOperationFailureMessage(operation({ operation_id: "op_resource", status: "failed", error }))).toMatch(explanation);
  });
});
