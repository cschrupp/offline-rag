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

const QC_RF = [
  {
    game_id: "goldgame_question_check_v1",
    presentation_id: "goldpres_question_check_source_panel_v1",
    disposition: "ALLOW_PRODUCTION",
  },
  {
    game_id: "goldgame_rapid_fire_v1",
    presentation_id: "goldpres_rapid_fire_single_card_v1",
    disposition: "ALLOW_PRODUCTION",
  },
] as const;

describe("16G-I2 approved-presentations policy", () => {
  it("authorizes Question Check and Rapid Fire under 16N-A policy enablement", () => {
    expect([...APPROVED_PRESENTATIONS_V1]).toEqual([...QC_RF]);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1)).toBe(true);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1[0])).toBe(true);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1[1])).toBe(true);
    expect(
      isAllowProduction(RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID),
    ).toBe(true);
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
      JSON.stringify(["goldpres_evidence_sweep_spatial_grid_5_v1"]),
    );
    sessionStorage.setItem(
      "gold-lab-allow-production",
      JSON.stringify(["goldpres_chunk_duel_side_by_side_v1"]),
    );
    expect(
      isAllowProduction(RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID),
    ).toBe(true);
    expect(
      isAllowProduction(QUESTION_CHECK_GAME_ID, QUESTION_CHECK_PRESENTATION_ID),
    ).toBe(true);
    localStorage.clear();
    sessionStorage.clear();
  });
});
