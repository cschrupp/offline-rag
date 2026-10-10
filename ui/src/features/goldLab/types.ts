export type GoldProjectType = "benchmark" | "improvement";
export type GoldProjectStatus = "active" | "archived";
export type GoldCampaignStatus = "open" | "closed";
export type GoldTaskKind = "question_check" | "absolute_relevance";
export type GoldTaskState = "pending" | "completed";

export type GoldProject = {
  project_id: string;
  workspace_id: string;
  title: string;
  description: string;
  project_type: GoldProjectType;
  status: GoldProjectStatus;
  created_at: string;
};

export type GoldProjectListResponse = {
  projects: GoldProject[];
};

export type GoldBaselineSummary = {
  authoring_run_id: string;
  created_at: string;
  corpus_id: string;
  corpus_name: string;
  chunk_set_id: string;
  case_count: number;
  reviewable_case_count: number;
};

export type GoldBaselineListResponse = {
  project_id: string;
  baselines: GoldBaselineSummary[];
};

export type GoldCampaign = {
  campaign_id: string;
  project_id: string;
  workspace_id: string;
  project_type: GoldProjectType;
  snapshot_id: string;
  chunk_set_id: string;
  corpus_id: string;
  corpus_name: string;
  baseline_authoring_run_id: string;
  workspace_revision_at_creation: number;
  status: GoldCampaignStatus;
  created_at: string;
};

export type GoldCampaignListResponse = {
  project_id: string;
  campaigns: GoldCampaign[];
};

export type GoldTaskSummary = {
  task_id: string;
  task_kind: GoldTaskKind;
  campaign_id: string;
  case_id: string;
  active: boolean;
  state: GoldTaskState;
  candidate_chunk_id: string | null;
  effective_query: string | null;
};

export type GoldTaskListResponse = {
  campaign_id: string;
  tasks: GoldTaskSummary[];
};

export type GoldProjectCreateRequest = {
  workspace_id: string;
  title: string;
  description: string;
  project_type: GoldProjectType;
};

export type GoldCampaignCreateRequest = {
  baseline_authoring_run_id: string;
  selection_policy_id: string;
  selection_policy_parameters: Record<string, never>;
  hard_calls: [];
};

export type GoldTaskListFilters = {
  kind?: GoldTaskKind;
  state?: GoldTaskState;
  active?: boolean;
  case_id?: string;
};
