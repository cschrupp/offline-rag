/**
 * Versioned Gold Lab approved-presentations governance artifact (S16-D27 / D0).
 *
 * Production eligibility is determined solely by this repository artifact.
 *
 * 16N-A policy enablement:
 * - Question Check: S16-N-A-QC-ALLOW-PRODUCTION-AUTH-001
 *   (Human disposition S16-N-A-QC-PRESENTATION-HA-001 — ACCEPTED)
 * - Rapid Fire: S16-N-A-RF-ALLOW-PRODUCTION-AUTH-001
 *   (Human disposition S16-N-A-RF-PRESENTATION-HA-001 — ACCEPTED)
 *
 * Evidence Sweep and Chunk Duel remain unapproved.
 *
 * The array and each entry are deeply frozen so runtime mutation cannot grant
 * eligibility for unapproved presentations.
 */
export type PresentationDisposition = "ALLOW_PRODUCTION" | "DENIED";

export type ApprovedPresentationEntry = Readonly<{
  game_id: string;
  presentation_id: string;
  disposition: PresentationDisposition;
}>;

export const APPROVED_PRESENTATIONS_ARTIFACT_VERSION = "v1" as const;

/**
 * Exact QC + RF ALLOW_PRODUCTION set.
 * Question Check identity unchanged from the accepted QC policy subject.
 */
export const APPROVED_PRESENTATIONS_V1: readonly ApprovedPresentationEntry[] =
  Object.freeze([
    Object.freeze({
      game_id: "goldgame_question_check_v1",
      presentation_id: "goldpres_question_check_source_panel_v1",
      disposition: "ALLOW_PRODUCTION" as const,
    }),
    Object.freeze({
      game_id: "goldgame_rapid_fire_v1",
      presentation_id: "goldpres_rapid_fire_single_card_v1",
      disposition: "ALLOW_PRODUCTION" as const,
    }),
  ]);
