import { describe, expect, it } from "vitest";
import { APPROVED_PRESENTATIONS_V1 } from "../features/goldLab/policy/approvedPresentations.v1";
import {
  QUESTION_CHECK_GAME_ID,
  QUESTION_CHECK_PRESENTATION_ID,
  RAPID_FIRE_GAME_ID,
  RAPID_FIRE_PRESENTATION_ID,
  candidatePresentationForGame,
  isAllowProduction,
} from "../features/goldLab/policy/presentations";

const QC_ONLY = [
  {
    game_id: "goldgame_question_check_v1",
    presentation_id: "goldpres_question_check_source_panel_v1",
    disposition: "ALLOW_PRODUCTION",
  },
] as const;

describe("16G-I2 approved-presentations policy", () => {
  it("authorizes Question Check only under 16N-A QC policy enablement", () => {
    expect([...APPROVED_PRESENTATIONS_V1]).toEqual([...QC_ONLY]);
    expect(
      isAllowProduction(RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(
        QUESTION_CHECK_GAME_ID,
        QUESTION_CHECK_PRESENTATION_ID,
      ),
    ).toBe(true);
  });

  it("exposes frozen I2 candidate identities", () => {
    expect(candidatePresentationForGame("rapid_fire")).toEqual({
      gameId: RAPID_FIRE_GAME_ID,
      presentationId: RAPID_FIRE_PRESENTATION_ID,
    });
    expect(candidatePresentationForGame("question_check")).toEqual({
      gameId: QUESTION_CHECK_GAME_ID,
      presentationId: QUESTION_CHECK_PRESENTATION_ID,
    });
  });

  it("does not consult browser storage for production eligibility", () => {
    localStorage.setItem(
      "gold-lab-allow-production",
      JSON.stringify([RAPID_FIRE_PRESENTATION_ID]),
    );
    sessionStorage.setItem(
      "gold-lab-allow-production",
      JSON.stringify([QUESTION_CHECK_PRESENTATION_ID]),
    );
    expect(
      isAllowProduction(RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(QUESTION_CHECK_GAME_ID, QUESTION_CHECK_PRESENTATION_ID),
    ).toBe(true);
    localStorage.clear();
    sessionStorage.clear();
  });
});
