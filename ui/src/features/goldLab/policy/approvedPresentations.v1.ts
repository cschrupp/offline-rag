/**
 * Versioned Gold Lab approved-presentations governance artifact (S16-D27 / D0).
 *
 * Production eligibility is determined solely by this repository artifact.
 * Under 16G-I2-AUTH-001 the ALLOW_PRODUCTION set is empty: no calibration
 * evidence or Human ALLOW_PRODUCTION disposition has been authorized for the
 * I2 Rapid Fire / Question Check presentations.
 */
export type PresentationDisposition = "ALLOW_PRODUCTION" | "DENIED";

export type ApprovedPresentationEntry = {
  game_id: string;
  presentation_id: string;
  disposition: PresentationDisposition;
};

export const APPROVED_PRESENTATIONS_ARTIFACT_VERSION = "v1" as const;

/** Empty under 16G-I2-AUTH-001 — do not add I2 presentations without governed disposition. */
export const APPROVED_PRESENTATIONS_V1: readonly ApprovedPresentationEntry[] =
  Object.freeze([]);
