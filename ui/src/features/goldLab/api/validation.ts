import { ApiError } from "../../../api/errors";
import type {
  GoldBaselineListResponse,
  GoldBaselineSummary,
  GoldCampaign,
  GoldCampaignListResponse,
  GoldProject,
  GoldProjectListResponse,
  GoldTaskListResponse,
  GoldTaskSummary,
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
