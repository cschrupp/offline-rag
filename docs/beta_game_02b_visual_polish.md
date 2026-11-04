# BETA-GAME-02B — Game identity, visual polish, and contribution rail

**Status:** BOUNDED IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT REVIEW
**Branch:** `implementation/beta-game-02b-visual-polish`
**Base:** canonical `main` at `5518e37a190b573a4658c2374acea88b525bebe9`

## Objective and boundaries

Give Quick Play and its two production-approved games a more recognizable,
approachable visual identity while preserving the established Seneca design
language. This is a frontend presentation change. Existing Gold scoring,
Question Check and Rapid Fire semantics, judgment mutations, session lifecycle,
source provenance, and production eligibility remain authoritative and
unchanged. No new games, backend behavior, scientific rules, or Slice 17 work
are included.

## Implemented

- Quick Play now presents Question Check and Rapid Fire as distinct activity
  cards with backend-provided pending counts and availability.
- Quick Play now has a campaign contribution rail backed exclusively by the
  existing `GET /v1/gold-lab/campaigns/{campaign_id}/contribution` endpoint and
  `gold-contribution-v1`. Contribution query keys remain campaign-specific,
  scores clear on workspace selection, and a contribution failure does not
  disable gameplay.
- Contribution and contextual-help rails can be collapsed independently.
  Desktop rail preferences and mobile disclosure states use separate
  namespaced local-storage keys; changing them does not remount or reset work.
- Question Check has a stronger question hierarchy and icon-labeled actions.
- Rapid Fire has distinct 0/1/2 choices with concise descriptions, keyboard
  shortcut names, and accessible descriptions. The existing key handling and
  mutation lockout are preserved.
- Source excerpt line spacing and metadata wrapping are improved.
- A successful judgment invalidates the relevant campaign contribution query
  so the Quick Play rail refreshes when the user returns.

## Review and validation

The implementation result and exact validation posture are recorded in
[`evidence/beta_game_02b/IMPLEMENTATION_RESULT.md`](evidence/beta_game_02b/IMPLEMENTATION_RESULT.md).

## Visual QA limit

Automated DOM and build checks were run. Manual browser validation at desktop,
narrow/mobile, and 200% zoom was not available in the implementation
environment; no visual pass is claimed for those sizes.
