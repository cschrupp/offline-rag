import { apiRequest } from "../../../api/client";
import type {
  GoldBaselineListResponse,
  GoldCampaign,
  GoldCampaignCreateRequest,
  GoldCampaignListResponse,
  GoldMutationReceipt,
  GoldPreferenceMutationBody,
  GoldProject,
  GoldProjectCreateRequest,
  GoldProjectListResponse,
  GoldRelevance,
  GoldTaskDetail,
  GoldTaskKind,
  GoldTaskListFilters,
  GoldTaskListResponse,
  QuestionCheckMutationBody,
} from "../types";
import {
  validateGoldBaselineListResponse,
  validateGoldCampaign,
  validateGoldCampaignListResponse,
  validateGoldMutationReceipt,
  validateGoldPreferenceReceipt,
  validateGoldProject,
  validateGoldProjectListResponse,
  validateGoldTaskDetail,
  validateGoldTaskListResponse,
} from "./validation";

export async function listGoldProjects(
  signal?: AbortSignal,
): Promise<GoldProjectListResponse> {
  const raw = await apiRequest<unknown>("/v1/gold-lab/projects", { signal });
  return validateGoldProjectListResponse(raw);
}

export async function createGoldProject(
  body: GoldProjectCreateRequest,
): Promise<GoldProject> {
  const raw = await apiRequest<unknown>("/v1/gold-lab/projects", {
    method: "POST",
    json: body,
  });
  return validateGoldProject(raw, "Gold project", {
    workspaceId: body.workspace_id,
  });
}

export async function getGoldProject(
  projectId: string,
  signal?: AbortSignal,
): Promise<GoldProject> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/projects/${encodeURIComponent(projectId)}`,
    { signal },
  );
  return validateGoldProject(raw, "Gold project", { projectId });
}

export async function archiveGoldProject(
  projectId: string,
): Promise<GoldProject> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/projects/${encodeURIComponent(projectId)}/archive`,
    { method: "POST" },
  );
  return validateGoldProject(raw, "Gold project", { projectId });
}

export async function listGoldBaselines(
  projectId: string,
  signal?: AbortSignal,
): Promise<GoldBaselineListResponse> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/projects/${encodeURIComponent(projectId)}/baselines`,
    { signal },
  );
  return validateGoldBaselineListResponse(raw, projectId);
}

export async function listGoldCampaigns(
  projectId: string,
  signal?: AbortSignal,
): Promise<GoldCampaignListResponse> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/projects/${encodeURIComponent(projectId)}/campaigns`,
    { signal },
  );
  return validateGoldCampaignListResponse(raw, projectId);
}

export async function createGoldCampaign(
  projectId: string,
  body: GoldCampaignCreateRequest,
): Promise<GoldCampaign> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/projects/${encodeURIComponent(projectId)}/campaigns`,
    {
      method: "POST",
      json: body,
    },
  );
  return validateGoldCampaign(raw, "Gold campaign", { projectId });
}

export async function getGoldCampaign(
  campaignId: string,
  signal?: AbortSignal,
): Promise<GoldCampaign> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(campaignId)}`,
    { signal },
  );
  return validateGoldCampaign(raw, "Gold campaign", { campaignId });
}

export async function closeGoldCampaign(
  campaignId: string,
): Promise<GoldCampaign> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(campaignId)}/close`,
    { method: "POST" },
  );
  return validateGoldCampaign(raw, "Gold campaign", { campaignId });
}

export async function listGoldTasks(
  campaignId: string,
  filters?: GoldTaskListFilters,
  signal?: AbortSignal,
): Promise<GoldTaskListResponse> {
  const params = new URLSearchParams();
  if (filters?.kind) params.set("kind", filters.kind);
  if (filters?.state) params.set("state", filters.state);
  if (filters?.active !== undefined) {
    params.set("active", String(filters.active));
  }
  if (filters?.case_id) params.set("case_id", filters.case_id);
  const query = params.toString();
  const path =
    `/v1/gold-lab/campaigns/${encodeURIComponent(campaignId)}/tasks` +
    (query ? `?${query}` : "");
  const raw = await apiRequest<unknown>(path, { signal });
  return validateGoldTaskListResponse(raw, campaignId);
}

export async function getGoldTask(
  campaignId: string,
  taskId: string,
  expectedKind?: GoldTaskKind,
  signal?: AbortSignal,
): Promise<GoldTaskDetail> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(campaignId)}/tasks/${encodeURIComponent(taskId)}`,
    { signal },
  );
  return validateGoldTaskDetail(raw, {
    campaignId,
    taskId,
    expectedKind,
  });
}

export async function submitGoldRelevance(params: {
  campaignId: string;
  taskId: string;
  relevance: GoldRelevance;
  gameId: string;
  presentationId: string;
  idempotencyKey: string;
}): Promise<GoldMutationReceipt> {
  const body = {
    relevance: params.relevance,
    game_id: params.gameId,
    presentation_id: params.presentationId,
  };
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(params.campaignId)}/tasks/${encodeURIComponent(params.taskId)}/relevance`,
    {
      method: "POST",
      idempotencyKey: params.idempotencyKey,
      json: body,
    },
  );
  return validateGoldMutationReceipt(raw, {
    campaignId: params.campaignId,
    taskId: params.taskId,
    expectedRecordType: "absolute_relevance",
  });
}

export async function submitGoldQuestionCheck(params: {
  campaignId: string;
  taskId: string;
  body: QuestionCheckMutationBody;
  idempotencyKey: string;
}): Promise<GoldMutationReceipt> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(params.campaignId)}/tasks/${encodeURIComponent(params.taskId)}/question-check`,
    {
      method: "POST",
      idempotencyKey: params.idempotencyKey,
      json: params.body,
    },
  );
  return validateGoldMutationReceipt(raw, {
    campaignId: params.campaignId,
    taskId: params.taskId,
    expectedRecordType: "question_check",
  });
}

export async function submitGoldPreference(params: {
  campaignId: string;
  body: GoldPreferenceMutationBody;
  idempotencyKey: string;
}): Promise<GoldMutationReceipt> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(params.campaignId)}/preferences`,
    {
      method: "POST",
      idempotencyKey: params.idempotencyKey,
      json: params.body,
    },
  );
  return validateGoldPreferenceReceipt(raw, {
    campaignId: params.campaignId,
  });
}
