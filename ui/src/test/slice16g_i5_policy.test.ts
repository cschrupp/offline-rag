import { describe, expect, it } from "vitest";
import { APPROVED_PRESENTATIONS_V1 } from "../features/goldLab/policy/approvedPresentations.v1";
import {
  CHUNK_DUEL_GAME_ID,
  CHUNK_DUEL_PRESENTATION_ID,
  EVIDENCE_SWEEP_GAME_ID,
  EVIDENCE_SWEEP_PRESENTATION_ID,
  isAllowProduction,
  QUESTION_CHECK_GAME_ID,
  QUESTION_CHECK_PRESENTATION_ID,
  RAPID_FIRE_GAME_ID,
  RAPID_FIRE_PRESENTATION_ID,
} from "../features/goldLab/policy/presentations";

describe("16G-I5 approved-presentations policy", () => {
  it("remains empty while Training operates independently of Gold Mode gate", () => {
    expect(APPROVED_PRESENTATIONS_V1).toEqual([]);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1)).toBe(true);
    for (const [gameId, presentationId] of [
      [RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID],
      [QUESTION_CHECK_GAME_ID, QUESTION_CHECK_PRESENTATION_ID],
      [EVIDENCE_SWEEP_GAME_ID, EVIDENCE_SWEEP_PRESENTATION_ID],
      [CHUNK_DUEL_GAME_ID, CHUNK_DUEL_PRESENTATION_ID],
    ] as const) {
      expect(isAllowProduction(gameId, presentationId)).toBe(false);
    }
  });
});
