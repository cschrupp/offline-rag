import { ApiError } from "../../../api/errors";
import type {
  GoldSourceContext,
  GoldTrainingCalibrationPackage,
  TrainingPackageAdjudicationCase,
  TrainingPackageCandidate,
  TrainingPackageGoldJudgment,
  TrainingPackageJudgment,
  TrainingPackageRegisteredCase,
} from "../types";

export const TRAINING_PACKAGE_SCHEMA_VERSION =
  "offline-rag-gold-lab-training-calibration-package-v1" as const;

const FORBIDDEN_KEYS = new Set([
  "retrieval_hits",
  "retriever",
  "rank",
  "score",
  "embedding_score",
  "reranker_score",
  "model_judgment",
  "model_grade",
  "model_confidence",
  "model_agreement",
  "prelabel",
  "prelabel_summary",
  "prelabel_provenance",
  "proposal_rationale",
  "reason_code",
  "hard_call_reason",
  "dataset_path",
]);

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

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function asRecord(raw: unknown, label: string): Record<string, unknown> {
  if (raw === null || raw === undefined) {
    throw unexpectedResponse(`${label} was empty or unreadable.`);
  }
  if (typeof raw !== "object" || Array.isArray(raw)) {
    throw unexpectedResponse(`${label} was not a valid object.`);
  }
  return raw as Record<string, unknown>;
}

function assertNoForbidden(value: unknown, path: string): void {
  if (value === null || value === undefined) return;
  if (Array.isArray(value)) {
    value.forEach((entry, index) =>
      assertNoForbidden(entry, `${path}[${index}]`),
    );
    return;
  }
  if (typeof value !== "object") return;
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (FORBIDDEN_KEYS.has(key)) {
      throw unexpectedResponse(
        `Training package contained forbidden field at ${path}.${key}.`,
      );
    }
    assertNoForbidden(child, `${path}.${key}`);
  }
}

function nullableString(value: unknown, label: string): string | null {
  if (value === null) return null;
  if (typeof value === "string") return value;
  throw unexpectedResponse(`${label} must be a string or null.`);
}

function nullableInt(value: unknown, label: string): number | null {
  if (value === null) return null;
  if (typeof value === "number" && Number.isInteger(value)) return value;
  throw unexpectedResponse(`${label} must be an integer or null.`);
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value)) {
    throw unexpectedResponse(`${label} must be an array.`);
  }
  for (const [index, entry] of value.entries()) {
    if (typeof entry !== "string") {
      throw unexpectedResponse(`${label}[${index}] must be a string.`);
    }
  }
  return value as string[];
}

function validateSource(
  raw: unknown,
  label: string,
): GoldSourceContext {
  const row = asRecord(raw, label);
  if (!isNonEmptyString(row.chunk_id)) {
    throw unexpectedResponse(`${label} is missing chunk_id.`);
  }
  if (!isNonEmptyString(row.document_id)) {
    throw unexpectedResponse(`${label} is missing document_id.`);
  }
  if (!Array.isArray(row.section_path)) {
    throw unexpectedResponse(`${label} has an invalid section_path.`);
  }
  for (const [index, part] of row.section_path.entries()) {
    if (typeof part !== "string") {
      throw unexpectedResponse(
        `${label} section_path[${index}] must be a string.`,
      );
    }
  }
  if (typeof row.content_type !== "string") {
    throw unexpectedResponse(`${label} has an invalid content_type.`);
  }
  if (typeof row.text !== "string") {
    throw unexpectedResponse(`${label} has an invalid text.`);
  }
  return {
    chunk_id: row.chunk_id,
    document_id: row.document_id,
    document_title: nullableString(row.document_title, `${label}.document_title`),
    source_name: nullableString(row.source_name, `${label}.source_name`),
    section_path: row.section_path as string[],
    page_start: nullableInt(row.page_start, `${label}.page_start`),
    page_end: nullableInt(row.page_end, `${label}.page_end`),
    line_start: nullableInt(row.line_start, `${label}.line_start`),
    line_end: nullableInt(row.line_end, `${label}.line_end`),
    content_type: row.content_type,
    text: row.text,
  };
}

function validateGoldJudgment(
  raw: unknown,
  label: string,
): TrainingPackageGoldJudgment {
  const row = asRecord(raw, label);
  if (!isNonEmptyString(row.chunk_id)) {
    throw unexpectedResponse(`${label} is missing chunk_id.`);
  }
  if (row.relevance !== 1 && row.relevance !== 2) {
    throw unexpectedResponse(
      `${label} relevance must be 1 or 2 (GoldDataset positives only).`,
    );
  }
  return { chunk_id: row.chunk_id, relevance: row.relevance };
}

function validateAdjJudgment(
  raw: unknown,
  label: string,
): TrainingPackageJudgment {
  const row = asRecord(raw, label);
  if (!isNonEmptyString(row.chunk_id)) {
    throw unexpectedResponse(`${label} is missing chunk_id.`);
  }
  if (row.relevance !== 0 && row.relevance !== 1 && row.relevance !== 2) {
    throw unexpectedResponse(`${label} relevance must be 0, 1, or 2.`);
  }
  return { chunk_id: row.chunk_id, relevance: row.relevance };
}

function validateCandidate(
  raw: unknown,
  label: string,
): TrainingPackageCandidate {
  const row = asRecord(raw, label);
  if (!isNonEmptyString(row.chunk_id)) {
    throw unexpectedResponse(`${label} is missing chunk_id.`);
  }
  const source = validateSource(row.source, `${label}.source`);
  if (source.chunk_id !== row.chunk_id) {
    throw unexpectedResponse(
      `${label} source.chunk_id must match candidate chunk_id.`,
    );
  }
  return { chunk_id: row.chunk_id, source };
}

function validateRegisteredCase(
  raw: unknown,
  label: string,
): TrainingPackageRegisteredCase {
  const row = asRecord(raw, label);
  if (!isNonEmptyString(row.case_id)) {
    throw unexpectedResponse(`${label} is missing case_id.`);
  }
  if (!isNonEmptyString(row.query)) {
    throw unexpectedResponse(`${label} is missing query.`);
  }
  if (!Array.isArray(row.judgments)) {
    throw unexpectedResponse(`${label} is missing judgments.`);
  }
  return {
    case_id: row.case_id,
    query: row.query,
    category: nullableString(row.category, `${label}.category`),
    tags: stringArray(row.tags, `${label}.tags`),
    judgments: row.judgments.map((entry, index) =>
      validateGoldJudgment(entry, `${label}.judgments[${index}]`),
    ),
  };
}

function validateAdjudicationCase(
  raw: unknown,
  label: string,
): TrainingPackageAdjudicationCase {
  const row = asRecord(raw, label);
  if (!isNonEmptyString(row.case_id)) {
    throw unexpectedResponse(`${label} is missing case_id.`);
  }
  if (
    row.qc_disposition !== "accept" &&
    row.qc_disposition !== "edit" &&
    row.qc_disposition !== "reject"
  ) {
    throw unexpectedResponse(`${label} has an invalid qc_disposition.`);
  }
  if (!isString(row.proposed_query)) {
    throw unexpectedResponse(`${label} has an invalid proposed_query.`);
  }
  const candidates = Array.isArray(row.candidates)
    ? row.candidates.map((entry, index) =>
        validateCandidate(entry, `${label}.candidates[${index}]`),
      )
    : (() => {
        throw unexpectedResponse(`${label} is missing candidates.`);
      })();
  const relevance_judgments = Array.isArray(row.relevance_judgments)
    ? row.relevance_judgments.map((entry, index) =>
        validateAdjJudgment(entry, `${label}.relevance_judgments[${index}]`),
      )
    : (() => {
        throw unexpectedResponse(`${label} is missing relevance_judgments.`);
      })();

  if (row.qc_disposition === "reject") {
    if (row.effective_query !== null) {
      throw unexpectedResponse(
        `${label} reject effective_query must be null.`,
      );
    }
    if (row.effective_category !== null) {
      throw unexpectedResponse(
        `${label} reject effective_category must be null.`,
      );
    }
    const tags = stringArray(row.effective_tags, `${label}.effective_tags`);
    if (tags.length !== 0) {
      throw unexpectedResponse(
        `${label} reject effective_tags must be empty.`,
      );
    }
    if (relevance_judgments.length !== 0) {
      throw unexpectedResponse(
        `${label} reject relevance_judgments must be empty.`,
      );
    }
    return {
      case_id: row.case_id,
      qc_disposition: "reject",
      proposed_query: row.proposed_query,
      proposed_category: nullableString(
        row.proposed_category,
        `${label}.proposed_category`,
      ),
      proposed_tags: stringArray(row.proposed_tags, `${label}.proposed_tags`),
      effective_query: null,
      effective_category: null,
      effective_tags: [],
      question_source:
        row.question_source === null || row.question_source === undefined
          ? null
          : validateSource(row.question_source, `${label}.question_source`),
      candidates,
      relevance_judgments: [],
    };
  }

  if (!isNonEmptyString(row.effective_query)) {
    throw unexpectedResponse(
      `${label} accept/edit requires a non-empty effective_query.`,
    );
  }
  if (candidates.length === 0) {
    throw unexpectedResponse(
      `${label} accept/edit requires a nonempty candidate universe.`,
    );
  }
  const candidateIds = new Set(candidates.map((c) => c.chunk_id));
  const judgmentIds = new Set(relevance_judgments.map((j) => j.chunk_id));
  if (candidateIds.size !== candidates.length) {
    throw unexpectedResponse(`${label} has duplicate candidate chunk_ids.`);
  }
  if (judgmentIds.size !== relevance_judgments.length) {
    throw unexpectedResponse(`${label} has duplicate relevance chunk_ids.`);
  }
  if (
    candidateIds.size !== judgmentIds.size ||
    [...candidateIds].some((id) => !judgmentIds.has(id))
  ) {
    throw unexpectedResponse(
      `${label} requires exactly one relevance label per candidate.`,
    );
  }

  return {
    case_id: row.case_id,
    qc_disposition: row.qc_disposition,
    proposed_query: row.proposed_query,
    proposed_category: nullableString(
      row.proposed_category,
      `${label}.proposed_category`,
    ),
    proposed_tags: stringArray(row.proposed_tags, `${label}.proposed_tags`),
    effective_query: row.effective_query,
    effective_category: nullableString(
      row.effective_category,
      `${label}.effective_category`,
    ),
    effective_tags: stringArray(row.effective_tags, `${label}.effective_tags`),
    question_source:
      row.question_source === null || row.question_source === undefined
        ? null
        : validateSource(row.question_source, `${label}.question_source`),
    candidates,
    relevance_judgments,
  };
}

export function validateTrainingCalibrationPackage(
  raw: unknown,
  expected: { campaignId: string; datasetId: string },
): GoldTrainingCalibrationPackage {
  assertNoForbidden(raw, "$");
  const top = asRecord(raw, "Training calibration package");
  if (top.schema_version !== TRAINING_PACKAGE_SCHEMA_VERSION) {
    throw unexpectedResponse(
      "Training package schema_version mismatch.",
    );
  }
  if (top.campaign_id !== expected.campaignId) {
    throw unexpectedResponse(
      "Training package campaign_id did not match the request.",
    );
  }
  if (top.dataset_id !== expected.datasetId) {
    throw unexpectedResponse(
      "Training package dataset_id did not match the request.",
    );
  }

  const registration = asRecord(top.registration, "registration");
  if (registration.campaign_id !== top.campaign_id) {
    throw unexpectedResponse(
      "registration.campaign_id must match package campaign_id.",
    );
  }
  if (registration.dataset_id !== top.dataset_id) {
    throw unexpectedResponse(
      "registration.dataset_id must match package dataset_id.",
    );
  }
  if (!isNonEmptyString(registration.projection_sha256)) {
    throw unexpectedResponse("registration is missing projection_sha256.");
  }
  if (!isNonEmptyString(registration.baseline_sha256)) {
    throw unexpectedResponse("registration is missing baseline_sha256.");
  }
  if (!isNonEmptyString(registration.chunk_set_id)) {
    throw unexpectedResponse("registration is missing chunk_set_id.");
  }
  if (!isNonEmptyString(registration.corpus_id)) {
    throw unexpectedResponse("registration is missing corpus_id.");
  }
  if (!isString(registration.corpus_name)) {
    throw unexpectedResponse("registration has an invalid corpus_name.");
  }
  if (!isNonEmptyString(registration.snapshot_id)) {
    throw unexpectedResponse("registration is missing snapshot_id.");
  }
  if (
    registration.project_type !== "benchmark" &&
    registration.project_type !== "improvement"
  ) {
    throw unexpectedResponse("registration has an invalid project_type.");
  }

  const registered_dataset = asRecord(
    top.registered_dataset,
    "registered_dataset",
  );
  if (registered_dataset.dataset_id !== top.dataset_id) {
    throw unexpectedResponse(
      "registered_dataset.dataset_id must match package dataset_id.",
    );
  }
  if (registered_dataset.chunk_set_id !== registration.chunk_set_id) {
    throw unexpectedResponse(
      "registered_dataset.chunk_set_id must match registration.",
    );
  }
  if (registered_dataset.corpus_id !== registration.corpus_id) {
    throw unexpectedResponse(
      "registered_dataset.corpus_id must match registration.",
    );
  }
  if (registered_dataset.corpus_name !== registration.corpus_name) {
    throw unexpectedResponse(
      "registered_dataset.corpus_name must match registration.",
    );
  }
  if (!Array.isArray(registered_dataset.cases)) {
    throw unexpectedResponse("registered_dataset is missing cases.");
  }

  const adjudication = asRecord(top.adjudication, "adjudication");
  if (adjudication.projection_sha256 !== registration.projection_sha256) {
    throw unexpectedResponse(
      "adjudication.projection_sha256 must match registration.",
    );
  }
  if (!Array.isArray(adjudication.cases)) {
    throw unexpectedResponse("adjudication is missing cases.");
  }

  const package_: GoldTrainingCalibrationPackage = {
    schema_version: TRAINING_PACKAGE_SCHEMA_VERSION,
    campaign_id: top.campaign_id as string,
    dataset_id: top.dataset_id as string,
    registration: {
      dataset_id: registration.dataset_id as string,
      project_id: registration.project_id as string,
      campaign_id: registration.campaign_id as string,
      project_type: registration.project_type,
      workspace_id: registration.workspace_id as string,
      snapshot_id: registration.snapshot_id as string,
      chunk_set_id: registration.chunk_set_id as string,
      corpus_id: registration.corpus_id as string,
      corpus_name: registration.corpus_name as string,
      baseline_authoring_run_id:
        registration.baseline_authoring_run_id as string,
      baseline_sha256: registration.baseline_sha256 as string,
      projection_sha256: registration.projection_sha256 as string,
      selection_policy_id: registration.selection_policy_id as string,
      selection_policy_fingerprint:
        registration.selection_policy_fingerprint as string,
      exported_case_ids: stringArray(
        registration.exported_case_ids,
        "registration.exported_case_ids",
      ),
      registered_at: registration.registered_at as string,
    },
    registered_dataset: {
      schema_version: String(registered_dataset.schema_version ?? ""),
      dataset_id: registered_dataset.dataset_id as string,
      chunk_set_id: registered_dataset.chunk_set_id as string,
      corpus_id: registered_dataset.corpus_id as string,
      corpus_name: registered_dataset.corpus_name as string,
      cases: registered_dataset.cases.map((entry, index) =>
        validateRegisteredCase(entry, `registered_dataset.cases[${index}]`),
      ),
    },
    adjudication: {
      projection_sha256: adjudication.projection_sha256 as string,
      cases: adjudication.cases.map((entry, index) =>
        validateAdjudicationCase(entry, `adjudication.cases[${index}]`),
      ),
    },
  };

  for (const field of [
    "project_id",
    "workspace_id",
    "baseline_authoring_run_id",
    "selection_policy_id",
    "selection_policy_fingerprint",
    "registered_at",
  ] as const) {
    if (!isNonEmptyString(package_.registration[field])) {
      throw unexpectedResponse(`registration is missing ${field}.`);
    }
  }

  return package_;
}
