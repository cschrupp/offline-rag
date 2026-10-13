/**
 * Versioned Gold Lab approved-presentations governance artifact (S16-D27 / D0).
 *
 * Production eligibility is determined solely by this repository artifact.
 *
 * 16N-A QC policy enablement (S16-N-A-QC-ALLOW-PRODUCTION-AUTH-001):
 * Question Check only, after Human presentation disposition
 * S16-N-A-QC-PRESENTATION-HA-001 — ACCEPTED.
 *
 * Rapid Fire, Evidence Sweep, and Chunk Duel remain unapproved.
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
 * Exact QC-only ALLOW_PRODUCTION set authorized by
 * S16-N-A-QC-ALLOW-PRODUCTION-AUTH-001.
 */
export const APPROVED_PRESENTATIONS_V1: readonly ApprovedPresentationEntry[] =
  Object.freeze([
    Object.freeze({
      game_id: "goldgame_question_check_v1",
      presentation_id: "goldpres_question_check_source_panel_v1",
      disposition: "ALLOW_PRODUCTION" as const,
    }),
  ]);
