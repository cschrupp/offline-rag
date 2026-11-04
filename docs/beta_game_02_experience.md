# BETA-GAME-02 — Game experience and contextual help

**Status:** BOUNDED IMPLEMENTATION AUTHORIZED / ACTIVE\
**Branch:** `implementation/beta-game-02-experience`\
**Base:** canonical `main` at `4ea5c92a9082621f167e8fcd2a64d085534633f9`

## Objective and product boundary

Make Gold Lab a clear, approachable expert-review experience by providing
short, context-sensitive instructions on every Gold Lab route. This is a UI
presentation change only. Question Check and Rapid Fire meanings, mutation
receipts, unresolved-mutation lockout, session lifecycle, Gold schemas, source
blinding, and production eligibility remain unchanged. Evidence Sweep and
Chunk Duel do not gain production authority.

## Required guide behavior

- One centralized typed registry supplies static, testable instructions for
  Quick Play, generation progress/failure/empty/playable/complete states,
  Question Check, Rapid Fire, save progress, errors, completion, and Advanced
  Gold Lab project/campaign/preview/contribution/calibration/training screens.
- Desktop uses a secondary right-side complementary guide rail; narrow layouts
  use a native, keyboard-operable inline disclosure before page content.
- Guide expansion does not reset a task, draft, or session. No focus trap,
  overlay, hover-only affordance, or motion-dependent information is used.
- Copy explains that Question Check evaluates the question rather than answers
  it. Rapid Fire explains 0 = Irrelevant, 1 = Supporting evidence, and 2 = Direct
  evidence, with a neutral example.
- The guide never reveals answer keys, correctness scores, model confidence,
  hidden judgments, or withheld metadata.

## Live QA provenance

The user-reported observations and their limits are recorded separately in
[`evidence/beta_game_02/BETA_QA_LIVE_2026-11-04.md`](evidence/beta_game_02/BETA_QA_LIVE_2026-11-04.md).
That record is not an independent replay or broad beta acceptance.

## Implementation status

The implementation candidate and validation results are recorded in
[`evidence/beta_game_02/IMPLEMENTATION_RESULT.md`](evidence/beta_game_02/IMPLEMENTATION_RESULT.md).
Manual desktop/mobile visual QA and any unexecuted responsive checks remain
explicitly identified there.
