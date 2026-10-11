import { describe, expect, it } from "vitest";
import { APPROVED_PRESENTATIONS_V1 } from "../features/goldLab/policy/approvedPresentations.v1";
import {
  CHUNK_DUEL_GAME_ID,
  CHUNK_DUEL_PRESENTATION_ID,
  EVIDENCE_SWEEP_GAME_ID,
  EVIDENCE_SWEEP_LINEAR_LIST_PRESENTATION_ID,
  EVIDENCE_SWEEP_PRESENTATION_ID,
  QUESTION_CHECK_GAME_ID,
  QUESTION_CHECK_PRESENTATION_ID,
  RAPID_FIRE_GAME_ID,
  RAPID_FIRE_PRESENTATION_ID,
  candidatePresentationForGame,
  isAllowProduction,
} from "../features/goldLab/policy/presentations";

describe("16G-I3 approved-presentations policy", () => {
  it("keeps ALLOW_PRODUCTION empty for all four expert games", () => {
    expect(APPROVED_PRESENTATIONS_V1).toEqual([]);
    for (const [gameId, presentationId] of [
      [RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID],
      [QUESTION_CHECK_GAME_ID, QUESTION_CHECK_PRESENTATION_ID],
      [EVIDENCE_SWEEP_GAME_ID, EVIDENCE_SWEEP_PRESENTATION_ID],
      [CHUNK_DUEL_GAME_ID, CHUNK_DUEL_PRESENTATION_ID],
    ] as const) {
      expect(isAllowProduction(gameId, presentationId)).toBe(false);
    }
    expect(
      isAllowProduction(
        EVIDENCE_SWEEP_GAME_ID,
        EVIDENCE_SWEEP_LINEAR_LIST_PRESENTATION_ID,
      ),
    ).toBe(false);
  });

  it("exposes frozen I3 candidate identities", () => {
    expect(candidatePresentationForGame("evidence_sweep")).toEqual({
      gameId: EVIDENCE_SWEEP_GAME_ID,
      presentationId: EVIDENCE_SWEEP_PRESENTATION_ID,
    });
    expect(candidatePresentationForGame("chunk_duel")).toEqual({
      gameId: CHUNK_DUEL_GAME_ID,
      presentationId: CHUNK_DUEL_PRESENTATION_ID,
    });
  });
});
