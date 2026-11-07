# BETA-CONV-01A — EVAL-READY-01 Readiness Handoff

**Starting commit:** `dea11cd3117cda2970704b7de9dddb1b681464ca`  
**Accepted preparation implementation:**
`bece868ba7210a154d14f6d900fe49a8a12e4a99`  
**Milestone:** preparation only; no real-model call, held-out scoring, planner
activation, or promotion.

## Completed within this milestone

- Added a normalized evidence adapter that calls only the canonical
  `POST /v1/workspaces/{workspace_id}/conversation/turn` route. It consumes the
  app's persisted conversation/query traces and instruments the existing
  generator, retrieval, and transform execution boundaries. It does not create
  an application, router, or executor.
- Added exact one-to-one alias binding against the complete active-source
  population, selected-scope translation, citation normalization, and checks
  that reject unknown or duplicate identities.
- Added case/arm/repetition identity checks and preserved API errors, timeouts,
  and transport failures as observations. Planner durations remain recorded
  when an HTTP failure follows an invoked planner. No raw query, prior turn,
  answer, credential, live source ID, or unrestricted exception text is placed
  in normalized observations.
- Added adapter tests for alias scope, source identity, timeout denominator
  retention, planner timing, and arm/configuration mismatch.
- Added synthetic schedule candidates for the 120 held-out IDs only. The
  ignored local artifact contains no request text or labels. It has a
  serialized alternative and a pair-interleaved alternative, each with 720
  `(case, arm, repeat)` attempts and 359 predeclared warm pairs. The first
  attempt per arm is labeled `cold_start`; all later attempts are
  `warm_interactive`. Exactly one alternative must be selected before a future
  freeze; the schedule is not frozen or authorized for execution.
- Added a fail-closed readiness checker for annotation, safety, historical
  mapping, API qualification, environment, schedule, methodology, and custody
  gates. Its current candidate state correctly remains blocked.
- Recorded the actual preparation host separately from any accepted
  evaluation host. NVML reports GPU access blocked; model identity is absent.
- Added the superseding exception-driven governance amendment without
  rewriting prior authorities or acceptance records.

## Existing deterministic failure matrix

The existing planner unit regressions already cover malformed/duplicate-key
JSON and non-strict JSON values, unexpected schema fields/types, invalid and
unselected source references, wrong prior-turn roles, invalid Unicode span
offsets, unsupported options, provider timeout, transport failure,
pre-planner cancellation, and context-window exhaustion. These tests exercise
the deterministic planner validation and turn failure boundaries with fake
providers; they make no model request. The route-level adapter test additions
use the accepted canonical app fixture, but execution of that test module
stalled at `TestClient` startup in this environment. API route qualification is
therefore still incomplete here.

## Inputs that cannot be self-certified by Codex

- Two independent annotators have not been assigned. Both existing private
  packets contain 300 unlabeled rows; each packet has a distinct custody role
  only after actual independent assignment. No labels or adjudications were
  fabricated.
- The historical challenge roster has 13 cases but lacks an independent
  completeness mapping to BETA-CONV-01 IR-001 through IR-004.
- The 40 new safety-family slots remain empty. They require independent
  authorship, including at least 15 Spanish families; generated variations
  would not satisfy this requirement.
- The held-out candidate is reproducible from the committed builder and is
  therefore not confidential. No independent custodian is assigned.
- The current WSL2 preparation environment is not approved as the evaluation
  host, and no approved local model ID, revision/checksum, or serving settings
  were supplied.
- The exact schedule alternative, operational watchdog/resource envelope,
  methodology review, and freeze identities remain pending.

## Proposed execution bounds (not approved or frozen)

The private schedule candidate records these proposals for later review: one
request in flight, one local model instance, no production traffic, a 300
second per-request watchdog, an eight-hour campaign wall watchdog, and a stop
if host available memory falls below 4 GiB. The 300 second request limit
contains the accepted 120 second provider-call bound plus a second downstream
generation call and application overhead. A campaign watchdog that expires
before all observations are durable makes the matrix incomplete and
`NOT_EVALUABLE`; no partial subset may be scored as a complete campaign.
These operational limits require independent review and explicit approval in a
later execution authorization. The accepted numerical scientific thresholds
are unchanged.

## Current machine-check result

`EVAL_READY_01_READINESS_STATE_CANDIDATE.json` is pending on independent
annotation, challenge authorship/review, canonical-route test execution,
reference host/model identity, schedule selection, methodology acceptance, and
held-out custody. `scripts/beta_conv_01a_eval_readiness.py` returns `BLOCKED`
for this state. The held-out split has not been scored.
