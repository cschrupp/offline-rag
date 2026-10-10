import { ApiError } from "../../../api/errors";
import type {
  AbsoluteRelevanceCurrentResult,
  AbsoluteRelevancePresentation,
  GoldBaselineListResponse,
  GoldBaselineSummary,
  GoldCampaign,
  GoldCampaignListResponse,
  GoldMutationReceipt,
  GoldMutationRecordType,
  GoldProject,
  GoldProjectListResponse,
  GoldSourceContext,
  GoldTaskDetail,
  GoldTaskKind,
  GoldTaskListResponse,
  GoldTaskSummary,
  QuestionCheckCurrentResult,
  QuestionCheckPresentation,
} from "../types";

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

function isNonNegativeInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isPositiveInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
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

export type ExpectedGoldProjectIdentity = {
  projectId?: string;
  workspaceId?: string;
};

export function validateGoldProject(
  raw: unknown,
  label = "Gold project",
  expected?: ExpectedGoldProjectIdentity,
): GoldProject {
  const row = asRecord(raw, label);
  if (!isNonEmptyString(row.project_id)) {
    throw unexpectedResponse(`${label} is missing project_id.`);
  }
  if (!isNonEmptyString(row.workspace_id)) {
    throw unexpectedResponse(`${label} is missing workspace_id.`);
  }
  if (!isString(row.title)) {
    throw unexpectedResponse(`${label} has an invalid title.`);
  }
  if (!isString(row.description)) {
    throw unexpectedResponse(`${label} has an invalid description.`);
  }
  if (row.project_type !== "benchmark" && row.project_type !== "improvement") {
    throw unexpectedResponse(`${label} has an invalid project_type.`);
  }
  if (row.status !== "active" && row.status !== "archived") {
    throw unexpectedResponse(`${label} has an invalid status.`);
  }
  if (!isString(row.created_at)) {
    throw unexpectedResponse(`${label} has an invalid created_at.`);
  }
  if (
    expected?.projectId !== undefined &&
    row.project_id !== expected.projectId
  ) {
    throw unexpectedResponse(
      `${label} did not match the requested project.`,
    );
  }
  if (
    expected?.workspaceId !== undefined &&
    row.workspace_id !== expected.workspaceId
  ) {
    throw unexpectedResponse(
      `${label} did not match the requested workspace.`,
    );
  }
  return {
    project_id: row.project_id,
    workspace_id: row.workspace_id,
    title: row.title,
    description: row.description,
    project_type: row.project_type,
    status: row.status,
    created_at: row.created_at,
  };
}

export function validateGoldProjectListResponse(
  raw: unknown,
): GoldProjectListResponse {
  const obj = asRecord(raw, "Gold project list");
  if (!Array.isArray(obj.projects)) {
    throw unexpectedResponse("Gold project list is missing projects.");
  }
  return {
    projects: obj.projects.map((entry, index) =>
      validateGoldProject(entry, `Gold project list entry ${index}`),
    ),
  };
}

function validateBaseline(
  raw: unknown,
  index: number,
): GoldBaselineSummary {
  const row = asRecord(raw, `Baseline ${index}`);
  if (!isNonEmptyString(row.authoring_run_id)) {
    throw unexpectedResponse(`Baseline ${index} is missing authoring_run_id.`);
  }
  if (!isString(row.created_at)) {
    throw unexpectedResponse(`Baseline ${index} has an invalid created_at.`);
  }
  if (!isNonEmptyString(row.corpus_id)) {
    throw unexpectedResponse(`Baseline ${index} is missing corpus_id.`);
  }
  if (!isString(row.corpus_name)) {
    throw unexpectedResponse(`Baseline ${index} has an invalid corpus_name.`);
  }
  if (!isNonEmptyString(row.chunk_set_id)) {
    throw unexpectedResponse(`Baseline ${index} is missing chunk_set_id.`);
  }
  if (!isNonNegativeInt(row.case_count)) {
    throw unexpectedResponse(`Baseline ${index} has an invalid case_count.`);
  }
  if (!isNonNegativeInt(row.reviewable_case_count)) {
    throw unexpectedResponse(
      `Baseline ${index} has an invalid reviewable_case_count.`,
    );
  }
  return {
    authoring_run_id: row.authoring_run_id,
    created_at: row.created_at,
    corpus_id: row.corpus_id,
    corpus_name: row.corpus_name,
    chunk_set_id: row.chunk_set_id,
    case_count: row.case_count,
    reviewable_case_count: row.reviewable_case_count,
  };
}

export function validateGoldBaselineListResponse(
  raw: unknown,
  requestedProjectId: string,
): GoldBaselineListResponse {
  const obj = asRecord(raw, "Baseline list");
  if (!isNonEmptyString(obj.project_id)) {
    throw unexpectedResponse("Baseline list is missing project_id.");
  }
  if (obj.project_id !== requestedProjectId) {
    throw unexpectedResponse(
      "Baseline list did not match the requested project.",
    );
  }
  if (!Array.isArray(obj.baselines)) {
    throw unexpectedResponse("Baseline list is missing baselines.");
  }
  return {
    project_id: obj.project_id,
    baselines: obj.baselines.map((entry, index) =>
      validateBaseline(entry, index),
    ),
  };
}

export type ExpectedGoldCampaignIdentity = {
  campaignId?: string;
  projectId?: string;
};

export function validateGoldCampaign(
  raw: unknown,
  label = "Gold campaign",
  expected?: ExpectedGoldCampaignIdentity,
): GoldCampaign {
  const row = asRecord(raw, label);
  if (!isNonEmptyString(row.campaign_id)) {
    throw unexpectedResponse(`${label} is missing campaign_id.`);
  }
  if (!isNonEmptyString(row.project_id)) {
    throw unexpectedResponse(`${label} is missing project_id.`);
  }
  if (!isNonEmptyString(row.workspace_id)) {
    throw unexpectedResponse(`${label} is missing workspace_id.`);
  }
  if (row.project_type !== "benchmark" && row.project_type !== "improvement") {
    throw unexpectedResponse(`${label} has an invalid project_type.`);
  }
  if (!isNonEmptyString(row.snapshot_id)) {
    throw unexpectedResponse(`${label} is missing snapshot_id.`);
  }
  if (!isNonEmptyString(row.chunk_set_id)) {
    throw unexpectedResponse(`${label} is missing chunk_set_id.`);
  }
  if (!isNonEmptyString(row.corpus_id)) {
    throw unexpectedResponse(`${label} is missing corpus_id.`);
  }
  if (!isString(row.corpus_name)) {
    throw unexpectedResponse(`${label} has an invalid corpus_name.`);
  }
  if (!isNonEmptyString(row.baseline_authoring_run_id)) {
    throw unexpectedResponse(`${label} is missing baseline_authoring_run_id.`);
  }
  if (!isPositiveInt(row.workspace_revision_at_creation)) {
    throw unexpectedResponse(
      `${label} has an invalid workspace_revision_at_creation.`,
    );
  }
  if (row.status !== "open" && row.status !== "closed") {
    throw unexpectedResponse(`${label} has an invalid status.`);
  }
  if (!isString(row.created_at)) {
    throw unexpectedResponse(`${label} has an invalid created_at.`);
  }
  if (
    expected?.campaignId !== undefined &&
    row.campaign_id !== expected.campaignId
  ) {
    throw unexpectedResponse(
      `${label} did not match the requested campaign.`,
    );
  }
  if (
    expected?.projectId !== undefined &&
    row.project_id !== expected.projectId
  ) {
    throw unexpectedResponse(
      `${label} did not match the requested project.`,
    );
  }
  return {
    campaign_id: row.campaign_id,
    project_id: row.project_id,
    workspace_id: row.workspace_id,
    project_type: row.project_type,
    snapshot_id: row.snapshot_id,
    chunk_set_id: row.chunk_set_id,
    corpus_id: row.corpus_id,
    corpus_name: row.corpus_name,
    baseline_authoring_run_id: row.baseline_authoring_run_id,
    workspace_revision_at_creation: row.workspace_revision_at_creation,
    status: row.status,
    created_at: row.created_at,
  };
}

export function validateGoldCampaignListResponse(
  raw: unknown,
  requestedProjectId: string,
): GoldCampaignListResponse {
  const obj = asRecord(raw, "Campaign list");
  if (!isNonEmptyString(obj.project_id)) {
    throw unexpectedResponse("Campaign list is missing project_id.");
  }
  if (obj.project_id !== requestedProjectId) {
    throw unexpectedResponse(
      "Campaign list did not match the requested project.",
    );
  }
  if (!Array.isArray(obj.campaigns)) {
    throw unexpectedResponse("Campaign list is missing campaigns.");
  }
  const campaigns = obj.campaigns.map((entry, index) =>
    validateGoldCampaign(entry, `Campaign list entry ${index}`),
  );
  for (const campaign of campaigns) {
    if (campaign.project_id !== requestedProjectId) {
      throw unexpectedResponse(
        "Campaign list contained a campaign for a different project.",
      );
    }
  }
  return {
    project_id: obj.project_id,
    campaigns,
  };
}

function validateTask(raw: unknown, index: number): GoldTaskSummary {
  const row = asRecord(raw, `Task ${index}`);
  if (!isNonEmptyString(row.task_id)) {
    throw unexpectedResponse(`Task ${index} is missing task_id.`);
  }
  if (
    row.task_kind !== "question_check" &&
    row.task_kind !== "absolute_relevance"
  ) {
    throw unexpectedResponse(`Task ${index} has an invalid task_kind.`);
  }
  if (!isNonEmptyString(row.campaign_id)) {
    throw unexpectedResponse(`Task ${index} is missing campaign_id.`);
  }
  if (!isNonEmptyString(row.case_id)) {
    throw unexpectedResponse(`Task ${index} is missing case_id.`);
  }
  if (typeof row.active !== "boolean") {
    throw unexpectedResponse(`Task ${index} has an invalid active flag.`);
  }
  if (row.state !== "pending" && row.state !== "completed") {
    throw unexpectedResponse(`Task ${index} has an invalid state.`);
  }
  if (
    !(
      row.candidate_chunk_id === null ||
      typeof row.candidate_chunk_id === "string"
    )
  ) {
    throw unexpectedResponse(
      `Task ${index} has an invalid candidate_chunk_id.`,
    );
  }
  if (
    !(row.effective_query === null || typeof row.effective_query === "string")
  ) {
    throw unexpectedResponse(`Task ${index} has an invalid effective_query.`);
  }
  return {
    task_id: row.task_id,
    task_kind: row.task_kind,
    campaign_id: row.campaign_id,
    case_id: row.case_id,
    active: row.active,
    state: row.state,
    candidate_chunk_id: row.candidate_chunk_id as string | null,
    effective_query: row.effective_query as string | null,
  };
}

export function validateGoldTaskListResponse(
  raw: unknown,
  requestedCampaignId: string,
): GoldTaskListResponse {
  const obj = asRecord(raw, "Task list");
  if (!isNonEmptyString(obj.campaign_id)) {
    throw unexpectedResponse("Task list is missing campaign_id.");
  }
  if (obj.campaign_id !== requestedCampaignId) {
    throw unexpectedResponse(
      "Task list did not match the requested campaign.",
    );
  }
  if (!Array.isArray(obj.tasks)) {
    throw unexpectedResponse("Task list is missing tasks.");
  }
  const tasks = obj.tasks.map((entry, index) => validateTask(entry, index));
  for (const task of tasks) {
    if (task.campaign_id !== requestedCampaignId) {
      throw unexpectedResponse(
        "Task list contained a task for a different campaign.",
      );
    }
  }
  return {
    campaign_id: obj.campaign_id,
    tasks,
  };
}

const BLINDNESS_FORBIDDEN_KEYS = new Set([
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
  "reason_code",
  "hard_call_reason",
  "hard_call_designation",
]);

function assertNoBlindnessLeak(value: unknown, path: string): void {
  if (value === null || value === undefined) return;
  if (Array.isArray(value)) {
    value.forEach((entry, index) =>
      assertNoBlindnessLeak(entry, `${path}[${index}]`),
    );
    return;
  }
  if (typeof value !== "object") return;
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (BLINDNESS_FORBIDDEN_KEYS.has(key)) {
      throw unexpectedResponse(
        `Task detail contained forbidden scientific enrichment at ${path}.${key}.`,
      );
    }
    assertNoBlindnessLeak(child, `${path}.${key}`);
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

function validateSourceContext(
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

function validateQuestionPresentation(
  raw: unknown,
): QuestionCheckPresentation {
  const row = asRecord(raw, "Question Check presentation");
  if (row.kind !== "question_check") {
    throw unexpectedResponse(
      "Question Check presentation.kind mismatch.",
    );
  }
  if (typeof row.proposed_query !== "string") {
    throw unexpectedResponse(
      "Question Check presentation has an invalid proposed_query.",
    );
  }
  if (!Array.isArray(row.proposed_tags)) {
    throw unexpectedResponse(
      "Question Check presentation has an invalid proposed_tags.",
    );
  }
  for (const [index, tag] of row.proposed_tags.entries()) {
    if (typeof tag !== "string") {
      throw unexpectedResponse(
        `Question Check presentation proposed_tags[${index}] must be a string.`,
      );
    }
  }
  const source =
    row.source === null
      ? null
      : validateSourceContext(row.source, "Question Check source");
  return {
    kind: "question_check",
    proposed_query: row.proposed_query,
    proposed_category: nullableString(
      row.proposed_category,
      "Question Check presentation.proposed_category",
    ),
    proposed_tags: row.proposed_tags as string[],
    source,
  };
}

function validateAbsolutePresentation(
  raw: unknown,
): AbsoluteRelevancePresentation {
  const row = asRecord(raw, "Absolute relevance presentation");
  if (row.kind !== "absolute_relevance") {
    throw unexpectedResponse(
      "Absolute relevance presentation.kind mismatch.",
    );
  }
  if (typeof row.effective_query !== "string") {
    throw unexpectedResponse(
      "Absolute relevance presentation has an invalid effective_query.",
    );
  }
  if (!Array.isArray(row.effective_tags)) {
    throw unexpectedResponse(
      "Absolute relevance presentation has an invalid effective_tags.",
    );
  }
  for (const [index, tag] of row.effective_tags.entries()) {
    if (typeof tag !== "string") {
      throw unexpectedResponse(
        `Absolute relevance presentation effective_tags[${index}] must be a string.`,
      );
    }
  }
  return {
    kind: "absolute_relevance",
    effective_query: row.effective_query,
    effective_category: nullableString(
      row.effective_category,
      "Absolute relevance presentation.effective_category",
    ),
    effective_tags: row.effective_tags as string[],
    candidate: validateSourceContext(
      row.candidate,
      "Absolute relevance candidate",
    ),
  };
}

function validateQuestionCurrent(
  raw: unknown,
): QuestionCheckCurrentResult {
  const row = asRecord(raw, "Question Check current_result");
  if (row.kind !== "question_check") {
    throw unexpectedResponse("Question Check current_result.kind mismatch.");
  }
  if (
    row.decision !== "accept" &&
    row.decision !== "edit" &&
    row.decision !== "reject"
  ) {
    throw unexpectedResponse(
      "Question Check current_result has an invalid decision.",
    );
  }
  if (!Array.isArray(row.effective_tags)) {
    throw unexpectedResponse(
      "Question Check current_result has invalid effective_tags.",
    );
  }
  for (const [index, tag] of row.effective_tags.entries()) {
    if (typeof tag !== "string") {
      throw unexpectedResponse(
        `Question Check current_result effective_tags[${index}] must be a string.`,
      );
    }
  }
  return {
    kind: "question_check",
    decision: row.decision,
    effective_query: nullableString(
      row.effective_query,
      "Question Check current_result.effective_query",
    ),
    effective_category: nullableString(
      row.effective_category,
      "Question Check current_result.effective_category",
    ),
    effective_tags: row.effective_tags as string[],
  };
}

function validateAbsoluteCurrent(
  raw: unknown,
): AbsoluteRelevanceCurrentResult {
  const row = asRecord(raw, "Absolute relevance current_result");
  if (row.kind !== "absolute_relevance") {
    throw unexpectedResponse(
      "Absolute relevance current_result.kind mismatch.",
    );
  }
  if (row.relevance !== 0 && row.relevance !== 1 && row.relevance !== 2) {
    throw unexpectedResponse(
      "Absolute relevance current_result.relevance must be 0, 1, or 2.",
    );
  }
  return {
    kind: "absolute_relevance",
    relevance: row.relevance,
  };
}

export function validateGoldTaskDetail(
  raw: unknown,
  requested: {
    campaignId: string;
    taskId: string;
    expectedKind?: GoldTaskKind;
  },
): GoldTaskDetail {
  assertNoBlindnessLeak(raw, "task");
  const summary = validateTask(raw, 0);
  if (summary.campaign_id !== requested.campaignId) {
    throw unexpectedResponse(
      "Task detail did not match the requested campaign.",
    );
  }
  if (summary.task_id !== requested.taskId) {
    throw unexpectedResponse("Task detail did not match the requested task.");
  }
  if (
    requested.expectedKind !== undefined &&
    summary.task_kind !== requested.expectedKind
  ) {
    throw unexpectedResponse(
      "Task detail task_kind did not match the selected game.",
    );
  }

  const obj = asRecord(raw, "Task detail");
  if (summary.task_kind === "question_check") {
    const presentation = validateQuestionPresentation(obj.presentation);
    const current_result =
      obj.current_result === null || obj.current_result === undefined
        ? null
        : validateQuestionCurrent(obj.current_result);
    if (summary.state === "pending" && current_result !== null) {
      throw unexpectedResponse(
        "Pending Question Check task unexpectedly contained current_result.",
      );
    }
    return {
      ...summary,
      task_kind: "question_check",
      presentation,
      current_result,
    };
  }

  if (!summary.active) {
    throw unexpectedResponse(
      "Rapid Fire cannot operate on an inactive absolute-relevance task.",
    );
  }
  if (obj.presentation === null || obj.presentation === undefined) {
    throw unexpectedResponse(
      "Active absolute-relevance task is missing presentation.",
    );
  }
  const presentation = validateAbsolutePresentation(obj.presentation);
  const current_result =
    obj.current_result === null || obj.current_result === undefined
      ? null
      : validateAbsoluteCurrent(obj.current_result);
  if (summary.state === "pending" && current_result !== null) {
    throw unexpectedResponse(
      "Pending absolute-relevance task unexpectedly contained current_result.",
    );
  }
  return {
    ...summary,
    task_kind: "absolute_relevance",
    presentation,
    current_result,
  };
}

export function validateGoldMutationReceipt(
  raw: unknown,
  requested: {
    campaignId: string;
    taskId: string;
    expectedRecordType: GoldMutationRecordType;
  },
): GoldMutationReceipt {
  const row = asRecord(raw, "Mutation receipt");
  if (!isNonEmptyString(row.campaign_id)) {
    throw unexpectedResponse("Mutation receipt is missing campaign_id.");
  }
  if (row.campaign_id !== requested.campaignId) {
    throw unexpectedResponse(
      "Mutation receipt did not match the requested campaign.",
    );
  }
  if (!isNonEmptyString(row.task_id)) {
    throw unexpectedResponse("Mutation receipt is missing task_id.");
  }
  if (row.task_id !== requested.taskId) {
    throw unexpectedResponse(
      "Mutation receipt did not match the requested task.",
    );
  }
  if (!isNonEmptyString(row.record_id)) {
    throw unexpectedResponse("Mutation receipt is missing record_id.");
  }
  if (!isNonEmptyString(row.judgment_id)) {
    throw unexpectedResponse("Mutation receipt is missing judgment_id.");
  }
  if (
    row.record_type !== "question_check" &&
    row.record_type !== "absolute_relevance" &&
    row.record_type !== "auxiliary_preference"
  ) {
    throw unexpectedResponse("Mutation receipt has an invalid record_type.");
  }
  if (row.record_type !== requested.expectedRecordType) {
    throw unexpectedResponse(
      "Mutation receipt record_type did not match the selected game.",
    );
  }
  if (!isPositiveInt(row.sequence)) {
    throw unexpectedResponse("Mutation receipt has an invalid sequence.");
  }
  if (typeof row.created_at !== "string") {
    throw unexpectedResponse("Mutation receipt has an invalid created_at.");
  }
  if (typeof row.replayed !== "boolean") {
    throw unexpectedResponse("Mutation receipt has an invalid replayed flag.");
  }
  return {
    campaign_id: row.campaign_id,
    record_id: row.record_id,
    judgment_id: row.judgment_id,
    task_id: row.task_id,
    record_type: row.record_type,
    sequence: row.sequence,
    created_at: row.created_at,
    replayed: row.replayed,
  };
}
