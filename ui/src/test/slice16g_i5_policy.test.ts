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

const QC_ONLY = [
  {
    game_id: "goldgame_question_check_v1",
    presentation_id: "goldpres_question_check_source_panel_v1",
    disposition: "ALLOW_PRODUCTION",
  },
] as const;

describe("16G-I5 approved-presentations policy", () => {
  it("QC alone is ALLOW_PRODUCTION while Training stays independent of RF/ES/CD", () => {
    expect([...APPROVED_PRESENTATIONS_V1]).toEqual([...QC_ONLY]);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1)).toBe(true);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1[0])).toBe(true);
    expect(
      isAllowProduction(QUESTION_CHECK_GAME_ID, QUESTION_CHECK_PRESENTATION_ID),
    ).toBe(true);
    for (const [gameId, presentationId] of [
      [RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID],
      [EVIDENCE_SWEEP_GAME_ID, EVIDENCE_SWEEP_PRESENTATION_ID],
      [CHUNK_DUEL_GAME_ID, CHUNK_DUEL_PRESENTATION_ID],
    ] as const) {
      expect(isAllowProduction(gameId, presentationId)).toBe(false);
    }
  });
});
