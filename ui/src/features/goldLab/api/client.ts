import { apiRequest } from "../../../api/client";
import type {
  GoldBaselineListResponse,
  GoldCampaign,
  GoldCampaignCreateRequest,
  GoldCampaignListResponse,
  GoldProject,
  GoldProjectCreateRequest,
  GoldProjectListResponse,
  GoldTaskListFilters,
  GoldTaskListResponse,
} from "../types";
import {
  validateGoldBaselineListResponse,
  validateGoldCampaign,
  validateGoldCampaignListResponse,
  validateGoldProject,
  validateGoldProjectListResponse,
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
  return validateGoldProject(raw);
}

export async function getGoldProject(
  projectId: string,
  signal?: AbortSignal,
): Promise<GoldProject> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/projects/${encodeURIComponent(projectId)}`,
    { signal },
  );
  return validateGoldProject(raw);
}

export async function archiveGoldProject(
  projectId: string,
): Promise<GoldProject> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/projects/${encodeURIComponent(projectId)}/archive`,
    { method: "POST" },
  );
  return validateGoldProject(raw);
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
  return validateGoldCampaign(raw);
}

export async function getGoldCampaign(
  campaignId: string,
  signal?: AbortSignal,
): Promise<GoldCampaign> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(campaignId)}`,
    { signal },
  );
  return validateGoldCampaign(raw);
}

export async function closeGoldCampaign(
  campaignId: string,
): Promise<GoldCampaign> {
  const raw = await apiRequest<unknown>(
    `/v1/gold-lab/campaigns/${encodeURIComponent(campaignId)}/close`,
    { method: "POST" },
  );
  return validateGoldCampaign(raw);
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
