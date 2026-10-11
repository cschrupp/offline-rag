import {
  CHUNK_DUEL_GAME_ID,
  CHUNK_DUEL_PRESENTATION_ID,
  EVIDENCE_SWEEP_GAME_ID,
  EVIDENCE_SWEEP_PRESENTATION_ID,
  QUESTION_CHECK_GAME_ID,
  QUESTION_CHECK_PRESENTATION_ID,
  RAPID_FIRE_GAME_ID,
  RAPID_FIRE_PRESENTATION_ID,
} from "../policy/presentations";
import type { GoldTrainingCalibrationPackage } from "../types";
import type {
  AbsoluteLocalRecord,
  CalibrationGameKind,
  DuelLocalRecord,
  QuestionLocalRecord,
} from "./types";

export const CALIBRATION_EVIDENCE_SCHEMA =
  "offline-rag-gold-calibration-evidence-v1" as const;

const GAME_IDS = {
  rapid_fire: {
    game_id: RAPID_FIRE_GAME_ID,
    presentation_id: RAPID_FIRE_PRESENTATION_ID,
  },
  evidence_sweep: {
    game_id: EVIDENCE_SWEEP_GAME_ID,
    presentation_id: EVIDENCE_SWEEP_PRESENTATION_ID,
  },
  question_check: {
    game_id: QUESTION_CHECK_GAME_ID,
    presentation_id: QUESTION_CHECK_PRESENTATION_ID,
  },
  chunk_duel: {
    game_id: CHUNK_DUEL_GAME_ID,
    presentation_id: CHUNK_DUEL_PRESENTATION_ID,
  },
} as const;

export type CalibrationEvidenceArtifact = {
  schema_version: typeof CALIBRATION_EVIDENCE_SCHEMA;
  generated_at: string;
  campaign_id: string;
  dataset_id: string;
  projection_sha256: string;
  baseline_sha256: string;
  snapshot_id: string;
  chunk_set_id: string;
  corpus_id: string;
  corpus_name: string;
  game_id: string;
  presentation_id: string;
  case_ids: string[];
  session: {
    started_at: string;
    ended_at: string;
    total_items: number;
    answered_items: number;
    completed: boolean;
    abandoned: boolean;
  };
  metrics: Record<string, number | Record<string, number>>;
  responses: Array<Record<string, unknown>>;
};

function absoluteMetrics(records: AbsoluteLocalRecord[]) {
  const agreement = records.filter((r) => r.matched).length;
  const response_distribution = { "0": 0, "1": 0, "2": 0 };
  const authority_distribution = { "0": 0, "1": 0, "2": 0 };
  let revision = 0;
  let durationSum = 0;
  for (const record of records) {
    response_distribution[String(record.localRelevance) as "0" | "1" | "2"] += 1;
    authority_distribution[
      String(record.authorityRelevance) as "0" | "1" | "2"
    ] += 1;
    revision += record.timing.revisionCount;
    durationSum += record.timing.durationMs ?? 0;
  }
  return {
    agreement_count: agreement,
    agreement_fraction: records.length === 0 ? 0 : agreement / records.length,
    local_revision_count: revision,
    local_revision_rate: records.length === 0 ? 0 : revision / records.length,
    mean_item_time_ms: records.length === 0 ? 0 : durationSum / records.length,
    response_distribution,
    authority_distribution,
  };
}

function questionMetrics(records: QuestionLocalRecord[]) {
  const agreement = records.filter((r) => r.dispositionMatched).length;
  const response_distribution = { accept: 0, edit: 0, reject: 0 };
  const authority_distribution = { accept: 0, edit: 0, reject: 0 };
  let revision = 0;
  let durationSum = 0;
  for (const record of records) {
    response_distribution[record.local.decision] += 1;
    authority_distribution[record.authorityDisposition] += 1;
    revision += record.timing.revisionCount;
    durationSum += record.timing.durationMs ?? 0;
  }
  return {
    disposition_agreement_count: agreement,
    disposition_agreement_fraction:
      records.length === 0 ? 0 : agreement / records.length,
    local_revision_count: revision,
    local_revision_rate: records.length === 0 ? 0 : revision / records.length,
    mean_item_time_ms: records.length === 0 ? 0 : durationSum / records.length,
    response_distribution,
    authority_distribution,
  };
}

function duelMetrics(records: DuelLocalRecord[]) {
  let preference_a_count = 0;
  let preference_b_count = 0;
  let revision = 0;
  let durationSum = 0;
  for (const record of records) {
    if (record.preferredSide === "a") preference_a_count += 1;
    else preference_b_count += 1;
    revision += record.timing.revisionCount;
    durationSum += record.timing.durationMs ?? 0;
  }
  return {
    preference_a_count,
    preference_b_count,
    interaction_count: records.length,
    local_revision_count: revision,
    local_revision_rate: records.length === 0 ? 0 : revision / records.length,
    mean_item_time_ms: records.length === 0 ? 0 : durationSum / records.length,
  };
}

export function buildCalibrationEvidence(params: {
  pkg: GoldTrainingCalibrationPackage;
  game: CalibrationGameKind;
  startedAt: string;
  endedAt: string;
  totalItems: number;
  absoluteRecords?: AbsoluteLocalRecord[];
  questionRecords?: QuestionLocalRecord[];
  duelRecords?: DuelLocalRecord[];
}): CalibrationEvidenceArtifact {
  const ids = GAME_IDS[params.game];
  const answered =
    params.absoluteRecords?.length ??
    params.questionRecords?.length ??
    params.duelRecords?.length ??
    0;
  const completed = answered === params.totalItems && params.totalItems > 0;
  const abandoned = answered < params.totalItems;

  let metrics: Record<string, number | Record<string, number>> = {};
  let responses: Array<Record<string, unknown>> = [];
  let caseIds: string[] = [];

  if (params.absoluteRecords) {
    metrics = absoluteMetrics(params.absoluteRecords);
    caseIds = [...new Set(params.absoluteRecords.map((r) => r.caseId))];
    responses = params.absoluteRecords.map((r) => ({
      case_id: r.caseId,
      candidate_chunk_id: r.candidateChunkId,
      local_relevance: r.localRelevance,
      authority_relevance: r.authorityRelevance,
      matched: r.matched,
      revision_count: r.timing.revisionCount,
      duration_ms: r.timing.durationMs,
      shown_at: r.timing.shownAt,
      committed_at: r.timing.committedAt,
    }));
  } else if (params.questionRecords) {
    metrics = questionMetrics(params.questionRecords);
    caseIds = [...new Set(params.questionRecords.map((r) => r.caseId))];
    responses = params.questionRecords.map((r) => ({
      case_id: r.caseId,
      local_decision: r.local.decision,
      local_effective_query:
        r.local.decision === "edit" ? r.local.effective_query : null,
      authority_disposition: r.authorityDisposition,
      disposition_matched: r.dispositionMatched,
      revision_count: r.timing.revisionCount,
      duration_ms: r.timing.durationMs,
      shown_at: r.timing.shownAt,
      committed_at: r.timing.committedAt,
    }));
  } else if (params.duelRecords) {
    metrics = duelMetrics(params.duelRecords);
    caseIds = [...new Set(params.duelRecords.map((r) => r.caseId))];
    responses = params.duelRecords.map((r) => ({
      case_id: r.caseId,
      preferred_chunk_id: r.preferredChunkId,
      other_chunk_id: r.otherChunkId,
      preferred_side: r.preferredSide,
      authority_relevance_a: r.authorityRelevanceA,
      authority_relevance_b: r.authorityRelevanceB,
      revision_count: r.timing.revisionCount,
      duration_ms: r.timing.durationMs,
      shown_at: r.timing.shownAt,
      committed_at: r.timing.committedAt,
    }));
  }

  const completion_time_ms = Math.max(
    0,
    Date.parse(params.endedAt) - Date.parse(params.startedAt),
  );

  return {
    schema_version: CALIBRATION_EVIDENCE_SCHEMA,
    generated_at: params.endedAt,
    campaign_id: params.pkg.campaign_id,
    dataset_id: params.pkg.dataset_id,
    projection_sha256: params.pkg.registration.projection_sha256,
    baseline_sha256: params.pkg.registration.baseline_sha256,
    snapshot_id: params.pkg.registration.snapshot_id,
    chunk_set_id: params.pkg.registration.chunk_set_id,
    corpus_id: params.pkg.registration.corpus_id,
    corpus_name: params.pkg.registration.corpus_name,
    game_id: ids.game_id,
    presentation_id: ids.presentation_id,
    case_ids: caseIds,
    session: {
      started_at: params.startedAt,
      ended_at: params.endedAt,
      total_items: params.totalItems,
      answered_items: answered,
      completed,
      abandoned,
    },
    metrics: {
      ...metrics,
      completion_time_ms,
      completion_fraction:
        params.totalItems === 0 ? 0 : answered / params.totalItems,
    },
    responses,
  };
}

export function downloadCalibrationEvidence(
  artifact: CalibrationEvidenceArtifact,
): void {
  const filename = `gold-calibration-${artifact.dataset_id}-${artifact.presentation_id}.json`;
  const blob = new Blob([`${JSON.stringify(artifact, null, 2)}\n`], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
