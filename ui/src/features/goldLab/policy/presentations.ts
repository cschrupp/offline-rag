import { APPROVED_PRESENTATIONS_V1 } from "./approvedPresentations.v1";

export const RAPID_FIRE_GAME_ID = "goldgame_rapid_fire_v1";
export const RAPID_FIRE_PRESENTATION_ID = "goldpres_rapid_fire_single_card_v1";

export const QUESTION_CHECK_GAME_ID = "goldgame_question_check_v1";
export const QUESTION_CHECK_PRESENTATION_ID =
  "goldpres_question_check_source_panel_v1";

export const EVIDENCE_SWEEP_GAME_ID = "goldgame_evidence_sweep_v1";
export const EVIDENCE_SWEEP_PRESENTATION_ID =
  "goldpres_evidence_sweep_spatial_grid_5_v1";

/** Reserved D0 alternate — not implemented/approved in I3. */
export const EVIDENCE_SWEEP_LINEAR_LIST_PRESENTATION_ID =
  "goldpres_evidence_sweep_linear_list_5_v1";

export const CHUNK_DUEL_GAME_ID = "goldgame_chunk_duel_v1";
export const CHUNK_DUEL_PRESENTATION_ID =
  "goldpres_chunk_duel_side_by_side_v1";

export type I2ExpertGame = "rapid_fire" | "question_check";
export type I3ExpertGame = "evidence_sweep" | "chunk_duel";
export type ExpertWorkGame = I2ExpertGame | I3ExpertGame;

export function candidatePresentationForGame(game: ExpertWorkGame): {
  gameId: string;
  presentationId: string;
} {
  if (game === "rapid_fire") {
    return {
      gameId: RAPID_FIRE_GAME_ID,
      presentationId: RAPID_FIRE_PRESENTATION_ID,
    };
  }
  if (game === "question_check") {
    return {
      gameId: QUESTION_CHECK_GAME_ID,
      presentationId: QUESTION_CHECK_PRESENTATION_ID,
    };
  }
  if (game === "evidence_sweep") {
    return {
      gameId: EVIDENCE_SWEEP_GAME_ID,
      presentationId: EVIDENCE_SWEEP_PRESENTATION_ID,
    };
  }
  return {
    gameId: CHUNK_DUEL_GAME_ID,
    presentationId: CHUNK_DUEL_PRESENTATION_ID,
  };
}

/**
 * Production eligibility from the versioned repository artifact only.
 * Never consult browser storage, query params, or environment variables.
 */
export function isAllowProduction(
  gameId: string,
  presentationId: string,
): boolean {
  return APPROVED_PRESENTATIONS_V1.some(
    (entry) =>
      entry.game_id === gameId &&
      entry.presentation_id === presentationId &&
      entry.disposition === "ALLOW_PRODUCTION",
  );
}

export function isI2ExpertGame(game: string): game is I2ExpertGame {
  return game === "rapid_fire" || game === "question_check";
}

export function isI3ExpertGame(game: string): game is I3ExpertGame {
  return game === "evidence_sweep" || game === "chunk_duel";
}

export function isExpertWorkGame(game: string): game is ExpertWorkGame {
  return isI2ExpertGame(game) || isI3ExpertGame(game);
}
