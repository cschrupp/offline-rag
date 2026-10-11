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

export type GoldSourceContext = {
  chunk_id: string;
  document_id: string;
  document_title: string | null;
  source_name: string | null;
  section_path: string[];
  page_start: number | null;
  page_end: number | null;
  line_start: number | null;
  line_end: number | null;
  content_type: string;
  text: string;
};

export type GoldTaskDetailBase = {
  task_id: string;
  task_kind: GoldTaskKind;
  campaign_id: string;
  case_id: string;
  active: boolean;
  state: GoldTaskState;
  candidate_chunk_id: string | null;
  effective_query: string | null;
};

export type QuestionCheckPresentation = {
  kind: "question_check";
  proposed_query: string;
  proposed_category: string | null;
  proposed_tags: string[];
  source: GoldSourceContext | null;
};

export type QuestionCheckCurrentResult = {
  kind: "question_check";
  decision: "accept" | "edit" | "reject";
  effective_query: string | null;
  effective_category: string | null;
  effective_tags: string[];
};

export type AbsoluteRelevancePresentation = {
  kind: "absolute_relevance";
  effective_query: string;
  effective_category: string | null;
  effective_tags: string[];
  candidate: GoldSourceContext;
};

export type AbsoluteRelevanceCurrentResult = {
  kind: "absolute_relevance";
  relevance: 0 | 1 | 2;
};

export type QuestionCheckTaskDetail = GoldTaskDetailBase & {
  task_kind: "question_check";
  presentation: QuestionCheckPresentation;
  current_result: QuestionCheckCurrentResult | null;
};

export type AbsoluteRelevanceTaskDetail = GoldTaskDetailBase & {
  task_kind: "absolute_relevance";
  presentation: AbsoluteRelevancePresentation;
  current_result: AbsoluteRelevanceCurrentResult | null;
};

export type GoldTaskDetail = QuestionCheckTaskDetail | AbsoluteRelevanceTaskDetail;

export type GoldMutationRecordType =
  | "question_check"
  | "absolute_relevance"
  | "auxiliary_preference";

export type GoldMutationReceipt = {
  campaign_id: string;
  record_id: string;
  judgment_id: string;
  task_id: string;
  record_type: GoldMutationRecordType;
  sequence: number;
  created_at: string;
  replayed: boolean;
};

export type GoldRelevance = 0 | 1 | 2;

export type QuestionCheckAcceptBody = {
  decision: "accept";
  game_id: string;
  presentation_id: string;
};

export type QuestionCheckRejectBody = {
  decision: "reject";
  game_id: string;
  presentation_id: string;
};

export type QuestionCheckEditBody = {
  decision: "edit";
  effective_query: string;
  effective_category: string | null;
  effective_tags: string[];
  game_id: string;
  presentation_id: string;
};

export type QuestionCheckMutationBody =
  | QuestionCheckAcceptBody
  | QuestionCheckRejectBody
  | QuestionCheckEditBody;

export type GoldPreferenceMutationBody = {
  case_id: string;
  preferred_chunk_id: string;
  other_chunk_id: string;
  game_id: string;
  presentation_id: string;
};

export type GoldContribution = {
  contract: "gold-contribution-v1";
  campaign_id: string;
  total_score: number;
  expert_judgments: number;
  questions_reviewed: number;
  cases_completed: number;
  gold_finalized: number;
  hard_calls_resolved: number;
  completed_active_absolute_tasks: number;
  total_active_absolute_tasks: number;
  coverage_fraction: number | null;
  total_question_tasks: number;
};

/** Safe registration index fields for Calibration selection (no dataset_path). */
export type GoldRegistrationSummary = {
  dataset_id: string;
  baseline_sha256: string;
  projection_sha256: string;
  exported_case_ids: string[];
  registered_at: string;
};

export type GoldRegistrationListResponse = {
  campaign_id: string;
  registrations: GoldRegistrationSummary[];
};

export type GoldQcDisposition = "accept" | "edit" | "reject";

export type TrainingPackageJudgment = {
  chunk_id: string;
  relevance: 0 | 1 | 2;
};

export type TrainingPackageGoldJudgment = {
  chunk_id: string;
  relevance: 1 | 2;
};

export type TrainingPackageCandidate = {
  chunk_id: string;
  source: GoldSourceContext;
};

export type TrainingPackageAdjudicationCase = {
  case_id: string;
  qc_disposition: GoldQcDisposition;
  proposed_query: string;
  proposed_category: string | null;
  proposed_tags: string[];
  effective_query: string | null;
  effective_category: string | null;
  effective_tags: string[];
  question_source: GoldSourceContext | null;
  candidates: TrainingPackageCandidate[];
  relevance_judgments: TrainingPackageJudgment[];
};

export type TrainingPackageRegisteredCase = {
  case_id: string;
  query: string;
  category: string | null;
  tags: string[];
  judgments: TrainingPackageGoldJudgment[];
};

export type GoldTrainingCalibrationPackage = {
  schema_version: "offline-rag-gold-lab-training-calibration-package-v1";
  campaign_id: string;
  dataset_id: string;
  registration: {
    dataset_id: string;
    project_id: string;
    campaign_id: string;
    project_type: GoldProjectType;
    workspace_id: string;
    snapshot_id: string;
    chunk_set_id: string;
    corpus_id: string;
    corpus_name: string;
    baseline_authoring_run_id: string;
    baseline_sha256: string;
    projection_sha256: string;
    selection_policy_id: string;
    selection_policy_fingerprint: string;
    exported_case_ids: string[];
    registered_at: string;
  };
  registered_dataset: {
    schema_version: string;
    dataset_id: string;
    chunk_set_id: string;
    corpus_id: string;
    corpus_name: string;
    cases: TrainingPackageRegisteredCase[];
  };
  adjudication: {
    projection_sha256: string;
    cases: TrainingPackageAdjudicationCase[];
  };
};
