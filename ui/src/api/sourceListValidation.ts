import { ApiError } from "./errors";
import type { Source, SourceListResponse } from "./types";

function unexpectedResponse(message: string): ApiError {
  return new ApiError({
    kind: "unexpected",
    code: "unexpected_response",
    message,
    retryable: true,
    status: 200,
  });
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isPositiveInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isNonNegativeInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function validateSourceEntry(raw: unknown, index: number): Source {
  if (!raw || typeof raw !== "object") {
    throw unexpectedResponse(
      `Source list entry ${index} was unreadable.`,
    );
  }
  const row = raw as Record<string, unknown>;
  if (!isNonEmptyString(row.source_id)) {
    throw unexpectedResponse(`Source list entry ${index} is missing source_id.`);
  }
  if (!isPositiveInt(row.version)) {
    throw unexpectedResponse(`Source list entry ${index} has an invalid version.`);
  }
  if (typeof row.display_name !== "string") {
    throw unexpectedResponse(
      `Source list entry ${index} has an invalid display_name.`,
    );
  }
  if (typeof row.content_type !== "string") {
    throw unexpectedResponse(
      `Source list entry ${index} has an invalid content_type.`,
    );
  }
  if (!isNonNegativeInt(row.byte_size)) {
    throw unexpectedResponse(
      `Source list entry ${index} has an invalid byte_size.`,
    );
  }
  if (!isNonEmptyString(row.content_hash)) {
    throw unexpectedResponse(
      `Source list entry ${index} has an invalid content_hash.`,
    );
  }
  if (!(row.document_id === null || typeof row.document_id === "string")) {
    throw unexpectedResponse(
      `Source list entry ${index} has an invalid document_id.`,
    );
  }
  if (typeof row.created_at !== "string") {
    throw unexpectedResponse(
      `Source list entry ${index} has an invalid created_at.`,
    );
  }
  if (!isPositiveInt(row.active_from_revision)) {
    throw unexpectedResponse(
      `Source list entry ${index} has an invalid active_from_revision.`,
    );
  }
  if (
    !(
      row.active_from_snapshot_id === null ||
      typeof row.active_from_snapshot_id === "string"
    )
  ) {
    throw unexpectedResponse(
      `Source list entry ${index} has an invalid active_from_snapshot_id.`,
    );
  }
  return {
    source_id: row.source_id,
    version: row.version,
    display_name: row.display_name,
    content_type: row.content_type,
    byte_size: row.byte_size,
    content_hash: row.content_hash,
    document_id: row.document_id as string | null,
    created_at: row.created_at,
    active_from_revision: row.active_from_revision,
    active_from_snapshot_id: row.active_from_snapshot_id as string | null,
  };
}

/**
 * Runtime validation for GET /v1/workspaces/{id}/sources.
 * Invalid successful payloads must fail closed as unexpected responses,
 * never as an empty source list.
 */
export function validateSourceListResponse(
  raw: unknown,
  requestedWorkspaceId: string,
): SourceListResponse {
  if (raw === null || raw === undefined) {
    throw unexpectedResponse(
      "Source list response was empty or unreadable.",
    );
  }
  if (typeof raw !== "object" || Array.isArray(raw)) {
    throw unexpectedResponse("Source list response was not a valid object.");
  }
  const obj = raw as Record<string, unknown>;
  if (!isNonEmptyString(obj.workspace_id)) {
    throw unexpectedResponse("Source list response is missing workspace_id.");
  }
  if (obj.workspace_id !== requestedWorkspaceId) {
    throw unexpectedResponse(
      "Source list response did not match the requested workspace.",
    );
  }
  if (!isPositiveInt(obj.revision)) {
    throw unexpectedResponse("Source list response has an invalid revision.");
  }
  if (!Array.isArray(obj.sources)) {
    throw unexpectedResponse("Source list response is missing sources.");
  }
  const sources = obj.sources.map((entry, index) =>
    validateSourceEntry(entry, index),
  );
  return {
    workspace_id: obj.workspace_id,
    revision: obj.revision,
    sources,
  };
}
