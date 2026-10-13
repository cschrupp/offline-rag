/**
 * Read-only Gold Lab campaign/task client boundary (16N-A).
 *
 * Presentation Review must import only from this module so mutation POSTs are
 * structurally unreachable from the preview subtree.
 */
import { apiRequest } from "../../../api/client";
import type {
  GoldCampaign,
  GoldTaskDetail,
  GoldTaskKind,
  GoldTaskListFilters,
  GoldTaskListResponse,
} from "../types";
import {
  validateGoldCampaign,
  validateGoldTaskDetail,
  validateGoldTaskListResponse,
} from "./validation";

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
