import { apiRequest } from "../../../api/client";
import type { Operation } from "../../../api/types";
import type {
  GoldBaselineListResponse,
  GoldCampaign,
  GoldCampaignCreateRequest,
  GoldCampaignListResponse,
  GoldContribution,
  GoldMutationReceipt,
  GoldPreferenceMutationBody,
  GoldProject,
  GoldProjectCreateRequest,
  GoldProjectListResponse,
  GoldRegistrationListResponse,
  GoldRelevance,
  GoldTrainingCalibrationPackage,
  QuestionCheckMutationBody,
} from "../types";
import { validateTrainingCalibrationPackage } from "./trainingPackageValidation";
import {
  validateGoldBaselineListResponse,
  validateGoldCampaign,
  validateGoldCampaignListResponse,
  validateGoldContribution,
  validateGoldMutationReceipt,
  validateGoldPreferenceReceipt,
  validateGoldProject,
  validateGoldProjectListResponse,
  validateGoldRegistrationListResponse,
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

export async function startGoldBaselineBootstrap(params: {
  projectId: string;
  proposalCount: number;
  prelabelEnabled: boolean;
  idempotencyKey: string;
}): Promise<Operation> {
  return apiRequest<Operation>(
    `/v1/gold-lab/projects/${encodeURIComponent(params.projectId)}/baseline-bootstrap`,
    {
      method: "POST",
      idempotencyKey: params.idempotencyKey,
      json: {
        proposal_count: params.proposalCount,
        prelabel_enabled: params.prelabelEnabled,
      },
    },
  );
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

export {
  getGoldCampaign,
  getGoldTask,
  listGoldTasks,
} from "./readClient";

export async function closeGoldCampaign(
  campaignId: string,
): Promise<GoldCampaign> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(campaignId)}/close`,
    { method: "POST" },
  );
  return validateGoldCampaign(raw, "Gold campaign", { campaignId });
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

export async function getGoldContribution(
  campaignId: string,
  signal?: AbortSignal,
): Promise<GoldContribution> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(campaignId)}/contribution`,
    { signal },
  );
  return validateGoldContribution(raw, campaignId);
}

export async function listGoldRegistrations(
  campaignId: string,
  signal?: AbortSignal,
): Promise<GoldRegistrationListResponse> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(campaignId)}/registrations`,
    { signal },
  );
  return validateGoldRegistrationListResponse(raw, campaignId);
}

export async function getGoldTrainingPackage(
  campaignId: string,
  datasetId: string,
  signal?: AbortSignal,
): Promise<GoldTrainingCalibrationPackage> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(campaignId)}/registrations/${encodeURIComponent(datasetId)}/training-package`,
    { signal },
  );
  return validateTrainingCalibrationPackage(raw, {
    campaignId,
    datasetId,
  });
}
