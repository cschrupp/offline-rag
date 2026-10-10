import type {
  GoldBaselineSummary,
  GoldCampaign,
  GoldProject,
  GoldTaskSummary,
} from "../features/goldLab/types";
import { workspace } from "./mockApi";

export function goldProject(
  partial: Partial<GoldProject> & Pick<GoldProject, "project_id">,
): GoldProject {
  return {
    workspace_id: "ws_1",
    title: "Gold Bench",
    description: "Eval oriented",
    project_type: "benchmark",
    status: "active",
    created_at: "2026-03-01T12:00:00Z",
    ...partial,
  };
}

export function goldBaseline(
  partial: Partial<GoldBaselineSummary> &
    Pick<GoldBaselineSummary, "authoring_run_id">,
): GoldBaselineSummary {
  return {
    created_at: "2026-02-01T10:00:00Z",
    corpus_id: "corpus_1",
    corpus_name: "Ops Corpus",
    chunk_set_id: "chunkset_1",
    case_count: 4,
    reviewable_case_count: 3,
    ...partial,
  };
}

export function goldCampaign(
  partial: Partial<GoldCampaign> & Pick<GoldCampaign, "campaign_id">,
): GoldCampaign {
  return {
    project_id: "proj_1",
    workspace_id: "ws_1",
    project_type: "benchmark",
    snapshot_id: "snap_1",
    chunk_set_id: "chunkset_1",
    corpus_id: "corpus_1",
    corpus_name: "Ops Corpus",
    baseline_authoring_run_id: "run_1",
    workspace_revision_at_creation: 2,
    status: "open",
    created_at: "2026-03-02T08:00:00Z",
    ...partial,
  };
}

export function goldTask(
  partial: Partial<GoldTaskSummary> & Pick<GoldTaskSummary, "task_id">,
): GoldTaskSummary {
  return {
    task_kind: "absolute_relevance",
    campaign_id: "camp_1",
    case_id: "case_a",
    active: true,
    state: "pending",
    candidate_chunk_id: "chunk_1",
    effective_query: null,
    ...partial,
  };
}

export function usableWorkspace() {
  return workspace({ workspace_id: "ws_1", title: "Station Desk" });
}
