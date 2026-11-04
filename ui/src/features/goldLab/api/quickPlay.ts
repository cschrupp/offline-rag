import { apiRequest } from "../../../api/client";

export type QuickPlayGame = {
  game_id: "question_check" | "rapid_fire";
  label: string;
  pending_count: number;
};

export type QuickPlayState = {
  schema_version: "quick-play-state-v1";
  workspace_id: string;
  workspace_title: string;
  workspace_revision?: number;
  snapshot_id?: string | null;
  project_id?: string | null;
  campaign_id?: string;
  status:
    | "not_ready"
    | "needs_generation"
    | "generating"
    | "generation_failed"
    | "baseline_available"
    | "campaign_ready"
    | "playable"
    | "complete"
    | "empty_population"
    | "blocked";
  reason?: string;
  operation?: {
    operation_id: string;
    status: string;
    failure_summary?: string | null;
    result?: Record<string, unknown> | null;
  } | null;
  question_check_pending?: number;
  rapid_fire_pending?: number;
  next_game?: QuickPlayGame["game_id"] | null;
  available_games?: QuickPlayGame[];
};

export function getQuickPlayState(
  workspaceId: string,
  signal?: AbortSignal,
): Promise<QuickPlayState> {
  return apiRequest<QuickPlayState>(
    `/v1/gold-lab/quick-play/workspaces/${encodeURIComponent(workspaceId)}`,
    { signal },
  );
}

export function prepareQuickPlay(params: {
  workspaceId: string;
  action: "start" | "replenish";
  idempotencyKey: string;
}): Promise<QuickPlayState> {
  return apiRequest<QuickPlayState>(
    `/v1/gold-lab/quick-play/workspaces/${encodeURIComponent(params.workspaceId)}/prepare`,
    {
      method: "POST",
      idempotencyKey: params.idempotencyKey,
      json: { action: params.action },
    },
  );
}
