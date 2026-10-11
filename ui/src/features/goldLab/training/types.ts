import type {
  GoldQcDisposition,
  GoldRelevance,
  GoldSourceContext,
} from "../types";

export type TrainingTemplateId =
  | "evidence_select"
  | "relevance_recall"
  | "question_check"
  | "scenario_relevance_map";

export type BlindCandidateView = {
  chunkId: string;
  source: GoldSourceContext;
};

export type BlindEvidenceSelectExercise = {
  kind: "evidence_select";
  exerciseId: string;
  caseId: string;
  query: string;
  category: string | null;
  tags: string[];
  candidates: BlindCandidateView[];
};

export type EvidenceSelectAuthority = {
  exerciseId: string;
  caseId: string;
  /** REGISTERED DATASET TRUTH — positives only (1|2). */
  positiveChunkIds: string[];
  /** REGISTRATION-TIME ADJUDICATION TRUTH — complete 0|1|2 map. */
  relevanceByChunkId: Record<string, GoldRelevance>;
};

export type BlindRelevanceRecallExercise = {
  kind: "relevance_recall";
  exerciseId: string;
  caseId: string;
  query: string;
  category: string | null;
  tags: string[];
  steps: Array<{
    stepId: string;
    candidateChunkId: string;
    source: GoldSourceContext;
  }>;
};

export type RelevanceRecallAuthority = {
  exerciseId: string;
  caseId: string;
  relevanceByChunkId: Record<string, GoldRelevance>;
};

export type BlindQuestionCheckExercise = {
  kind: "question_check";
  exerciseId: string;
  caseId: string;
  proposedQuery: string;
  proposedCategory: string | null;
  proposedTags: string[];
  questionSource: GoldSourceContext;
};

export type QuestionCheckAuthority = {
  exerciseId: string;
  caseId: string;
  disposition: GoldQcDisposition;
  effectiveQuery: string | null;
  effectiveCategory: string | null;
  effectiveTags: string[];
};

export type BlindScenarioExercise = {
  kind: "scenario_relevance_map";
  exerciseId: string;
  caseId: string;
  /** Scenario stem — exactly effective_query. */
  scenarioStem: string;
  category: string | null;
  tags: string[];
  candidates: BlindCandidateView[];
};

export type ScenarioAuthority = {
  exerciseId: string;
  caseId: string;
  relevanceByChunkId: Record<string, GoldRelevance>;
};

export type BlindTrainingExercise =
  | BlindEvidenceSelectExercise
  | BlindRelevanceRecallExercise
  | BlindQuestionCheckExercise
  | BlindScenarioExercise;

export type TrainingAuthority =
  | EvidenceSelectAuthority
  | RelevanceRecallAuthority
  | QuestionCheckAuthority
  | ScenarioAuthority;

export type CompileIssue = {
  caseId: string;
  templateId: TrainingTemplateId;
  reason: string;
};

export type TrainingCompileResult = {
  datasetId: string;
  projectionSha256: string;
  drills: Array<
    | BlindEvidenceSelectExercise
    | BlindRelevanceRecallExercise
    | BlindQuestionCheckExercise
  >;
  scenarios: BlindScenarioExercise[];
  authorityByExerciseId: Map<string, TrainingAuthority>;
  issues: CompileIssue[];
};

export type LocalQcDisposition = "accept" | "edit" | "reject";
