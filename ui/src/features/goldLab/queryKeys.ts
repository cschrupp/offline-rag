import type { GoldTaskListFilters } from "./types";

function stableFilters(filters?: GoldTaskListFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.state) params.set("state", filters.state);
  if (filters.active !== undefined) params.set("active", String(filters.active));
  if (filters.case_id) params.set("case_id", filters.case_id);
  return params.toString();
}

export const goldLabQueryKeys = {
  all: ["gold-lab"] as const,
  projects: ["gold-lab", "projects"] as const,
  project: (projectId: string) => ["gold-lab", "project", projectId] as const,
  baselines: (projectId: string) =>
    ["gold-lab", "baselines", projectId] as const,
  campaigns: (projectId: string) =>
    ["gold-lab", "campaigns", projectId] as const,
  campaign: (campaignId: string) =>
    ["gold-lab", "campaign", campaignId] as const,
  tasks: (campaignId: string, filters?: GoldTaskListFilters) =>
    ["gold-lab", "tasks", campaignId, stableFilters(filters)] as const,
  task: (campaignId: string, taskId: string) =>
    ["gold-lab", "task", campaignId, taskId] as const,
};
