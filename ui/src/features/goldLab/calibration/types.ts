import type { GoldQcDisposition, GoldRelevance, GoldSourceContext } from "../types";

export type BlindAbsoluteItem = {
  itemId: string;
  caseId: string;
  candidateChunkId: string;
  query: string;
  category: string | null;
  tags: string[];
  source: GoldSourceContext;
};

export type AbsoluteAuthority = {
  caseId: string;
  candidateChunkId: string;
  relevance: GoldRelevance;
};

export type BlindQuestionItem = {
  itemId: string;
  caseId: string;
  proposedQuery: string;
  proposedCategory: string | null;
  proposedTags: string[];
  questionSource: GoldSourceContext | null;
};

export type QuestionAuthority = {
  caseId: string;
  disposition: GoldQcDisposition;
  effectiveQuery: string | null;
  effectiveCategory: string | null;
  effectiveTags: string[];
};

export type BlindDuelItem = {
  itemId: string;
  caseId: string;
  query: string;
  category: string | null;
  tags: string[];
  chunkA: { chunkId: string; source: GoldSourceContext };
  chunkB: { chunkId: string; source: GoldSourceContext };
};

export type DuelAuthority = {
  caseId: string;
  chunkAId: string;
  chunkBId: string;
  relevanceA: GoldRelevance;
  relevanceB: GoldRelevance;
};

export type LocalQuestionResponse =
  | { decision: "accept" }
  | { decision: "reject" }
  | {
      decision: "edit";
      effective_query: string;
      effective_category: string | null;
      effective_tags: string[];
    };

export type CalibrationGameKind =
  | "rapid_fire"
  | "evidence_sweep"
  | "question_check"
  | "chunk_duel";

export type ItemTiming = {
  shownAt: string;
  committedAt: string | null;
  durationMs: number | null;
  revisionCount: number;
};

export type AbsoluteLocalRecord = {
  itemId: string;
  caseId: string;
  candidateChunkId: string;
  localRelevance: GoldRelevance;
  authorityRelevance: GoldRelevance;
  matched: boolean;
  timing: ItemTiming;
};

export type QuestionLocalRecord = {
  itemId: string;
  caseId: string;
  local: LocalQuestionResponse;
  authorityDisposition: GoldQcDisposition;
  dispositionMatched: boolean;
  timing: ItemTiming;
};

export type DuelLocalRecord = {
  itemId: string;
  caseId: string;
  preferredSide: "a" | "b";
  preferredChunkId: string;
  otherChunkId: string;
  authorityRelevanceA: GoldRelevance;
  authorityRelevanceB: GoldRelevance;
  timing: ItemTiming;
};
