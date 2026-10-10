import { APPROVED_PRESENTATIONS_V1 } from "./approvedPresentations.v1";

export const RAPID_FIRE_GAME_ID = "goldgame_rapid_fire_v1";
export const RAPID_FIRE_PRESENTATION_ID = "goldpres_rapid_fire_single_card_v1";

export const QUESTION_CHECK_GAME_ID = "goldgame_question_check_v1";
export const QUESTION_CHECK_PRESENTATION_ID =
  "goldpres_question_check_source_panel_v1";

export type I2ExpertGame = "rapid_fire" | "question_check";

export function candidatePresentationForGame(game: I2ExpertGame): {
  gameId: string;
  presentationId: string;
} {
  if (game === "rapid_fire") {
    return {
      gameId: RAPID_FIRE_GAME_ID,
      presentationId: RAPID_FIRE_PRESENTATION_ID,
    };
  }
  return {
    gameId: QUESTION_CHECK_GAME_ID,
    presentationId: QUESTION_CHECK_PRESENTATION_ID,
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
