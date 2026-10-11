import type { GoldTrainingCalibrationPackage } from "../types";
import type {
  AbsoluteAuthority,
  BlindAbsoluteItem,
  BlindDuelItem,
  BlindQuestionItem,
  DuelAuthority,
  QuestionAuthority,
} from "./types";

export type AbsoluteCalibrationBundle = {
  items: BlindAbsoluteItem[];
  authorityByItemId: Map<string, AbsoluteAuthority>;
};

export type QuestionCalibrationBundle = {
  items: BlindQuestionItem[];
  authorityByItemId: Map<string, QuestionAuthority>;
};

export type DuelCalibrationBundle = {
  items: BlindDuelItem[];
  authorityByItemId: Map<string, DuelAuthority>;
};

/** Preserve adjudication case order, then candidate order from the package. */
export function compileAbsoluteItems(
  pkg: GoldTrainingCalibrationPackage,
): AbsoluteCalibrationBundle {
  const items: BlindAbsoluteItem[] = [];
  const authorityByItemId = new Map<string, AbsoluteAuthority>();

  for (const adj of pkg.adjudication.cases) {
    if (adj.qc_disposition !== "accept" && adj.qc_disposition !== "edit") {
      continue;
    }
    if (!adj.effective_query) continue;
    const judgmentByChunk = new Map(
      adj.relevance_judgments.map((j) => [j.chunk_id, j.relevance]),
    );
    for (const candidate of adj.candidates) {
      const relevance = judgmentByChunk.get(candidate.chunk_id);
      if (relevance === undefined) continue;
      const itemId = `${adj.case_id}::${candidate.chunk_id}`;
      items.push({
        itemId,
        caseId: adj.case_id,
        candidateChunkId: candidate.chunk_id,
        query: adj.effective_query,
        category: adj.effective_category,
        tags: [...adj.effective_tags],
        source: candidate.source,
      });
      authorityByItemId.set(itemId, {
        caseId: adj.case_id,
        candidateChunkId: candidate.chunk_id,
        relevance,
      });
    }
  }

  return { items, authorityByItemId };
}

export function compileQuestionItems(
  pkg: GoldTrainingCalibrationPackage,
): QuestionCalibrationBundle {
  const items: BlindQuestionItem[] = [];
  const authorityByItemId = new Map<string, QuestionAuthority>();

  for (const adj of pkg.adjudication.cases) {
    const itemId = `qc::${adj.case_id}`;
    items.push({
      itemId,
      caseId: adj.case_id,
      proposedQuery: adj.proposed_query,
      proposedCategory: adj.proposed_category,
      proposedTags: [...adj.proposed_tags],
      questionSource: adj.question_source,
    });
    authorityByItemId.set(itemId, {
      caseId: adj.case_id,
      disposition: adj.qc_disposition,
      effectiveQuery: adj.effective_query,
      effectiveCategory: adj.effective_category,
      effectiveTags: [...adj.effective_tags],
    });
  }

  return { items, authorityByItemId };
}

/** First two distinct candidates per accepted/edited case (package order). */
export function compileDuelItems(
  pkg: GoldTrainingCalibrationPackage,
): DuelCalibrationBundle {
  const items: BlindDuelItem[] = [];
  const authorityByItemId = new Map<string, DuelAuthority>();

  for (const adj of pkg.adjudication.cases) {
    if (adj.qc_disposition !== "accept" && adj.qc_disposition !== "edit") {
      continue;
    }
    if (!adj.effective_query || adj.candidates.length < 2) continue;
    const [a, b] = adj.candidates;
    if (!a || !b) continue;
    const judgmentByChunk = new Map(
      adj.relevance_judgments.map((j) => [j.chunk_id, j.relevance]),
    );
    const relevanceA = judgmentByChunk.get(a.chunk_id);
    const relevanceB = judgmentByChunk.get(b.chunk_id);
    if (relevanceA === undefined || relevanceB === undefined) continue;
    const itemId = `duel::${adj.case_id}::${a.chunk_id}::${b.chunk_id}`;
    items.push({
      itemId,
      caseId: adj.case_id,
      query: adj.effective_query,
      category: adj.effective_category,
      tags: [...adj.effective_tags],
      chunkA: { chunkId: a.chunk_id, source: a.source },
      chunkB: { chunkId: b.chunk_id, source: b.source },
    });
    authorityByItemId.set(itemId, {
      caseId: adj.case_id,
      chunkAId: a.chunk_id,
      chunkBId: b.chunk_id,
      relevanceA,
      relevanceB,
    });
  }

  return { items, authorityByItemId };
}
