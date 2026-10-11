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

describe("16G-I2 approved-presentations policy", () => {
  it("keeps the versioned artifact empty for ALLOW_PRODUCTION", () => {
    expect(APPROVED_PRESENTATIONS_V1).toEqual([]);
    expect(
      isAllowProduction(RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(
        QUESTION_CHECK_GAME_ID,
        QUESTION_CHECK_PRESENTATION_ID,
      ),
    ).toBe(false);
  });

  it("exposes frozen I2 candidate identities without allowing production", () => {
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
    localStorage.clear();
    sessionStorage.clear();
  });
});
