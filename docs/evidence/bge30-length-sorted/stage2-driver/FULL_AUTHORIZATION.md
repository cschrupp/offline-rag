# Seneca — Complete Stage 2 Engineering Without Further Micro-Checkpoints

## Human Authority — Execution Policy Reset

**This is a consolidated implementation authorization. Do not stop after partial progress or request review for routine engineering problems.**

Repository: `cschrupp/offline-rag`

Latest driver evidence:
`67fe29f4aa52266a0da8d8e26e05f65f0a872ad9`

Accepted integrated application:
`1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e`

Accepted diagnostic image:
`sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04`

Canonical protocol:
`docs/evidence/bge30-length-sorted/stage2-integration/PROTOCOL.md`

Existing driver:
`docs/evidence/bge30-length-sorted/stage2-driver/`

## Mission

**Finish the complete Stage 2 Docker/HTTP driver and demonstrate an end-to-end local rehearsal.**

The task is not to identify the next missing component. It is to implement all missing components, integrate them, test them, resolve routine failures, and deliver the completed engineering result.

You are authorized to make reasonable implementation decisions independently.

Do not interrupt execution merely because:

- A fixture needs to be written or corrected.
- A diagnostic observer is missing.
- An integration test fails.
- A Docker command requires adjustment.
- Server-side operation correlation needs instrumentation.
- A watchdog needs another implementation iteration.
- A test harness requires refactoring.
- A local synthetic rehearsal must be repeated after fixing a defect.
- A documentation assumption turns out to be incomplete.

These are engineering tasks within your authority, not new Human Authority decisions.

## Context recovery

Read the existing implementation and evidence in GitHub before modifying anything.

The integrated application, lifecycle and BGE batching algorithms have already passed independent source review.

Do not reopen their architectural decisions.

The current driver has a working scheduler, a partial Docker adapter, single-send socket transport, an independent watchdog primitive, image verification and preflight checks.

Build on that foundation, but replace or simplify scaffolding where doing so produces a more reliable complete solution.

Do not create another documentation-only checkpoint.

## Implementation authority

You may modify and add diagnostic driver code, Docker orchestration, test fixtures, local instrumentation, verification scripts, logs and tests.

You may use the existing provider-factory seam and diagnostic-only instrumentation around the real application.

For server-side correlation, implement an observer that associates the `X-Stage2-Ordinal` request with its actual operation handle and records admission, worker return, trace identity, terminal state and slot release.

Instrument the existing lifecycle without changing its decisions. For example, a diagnostic wrapper around the existing owned-worker boundary and registry methods is acceptable, provided it delegates to the original behavior and cannot fabricate successful outcomes.

Do not change production request schemas, scientific scoring, snapshot identity, trace semantics, or query-capacity policy.

Apply identical diagnostic instrumentation to both experimental arms.

Instrument and observe real native inference without replacing its inputs or outputs.

If a proposed mechanism fails, implement a better one. Do not treat the failure of your first approach as a project blocker.

## Finish the Docker/HTTP adapter

Complete `open()`, `submit()`, `abort()` and `close()`.

Support both load and lifecycle cases.

Make request correlation deterministic and independently verifiable.

A client response is not a worker completion. A disconnect is not a slot release. A timeout is not proof of termination.

For admitted operations, require genuine server-side completion and release evidence.

For rejected operations, verify the correct rejection reason and absence of an allocated scientific execution trace.

Treat ambiguous or missing records as failed observations, not successful completions.

Use a strict submission ledger so that no local or eventual native campaign can exceed the authorized submission budget.

## Finish all lifecycle controls

Implement the four existing cases, for both batching strategies:

1. Disconnect before reranking.
2. Disconnect during a held scorer forward.
3. Cooperative deadline recognition after held inference returns.
4. Shutdown drain beyond transport grace.

Use deterministic barriers, bounded timeouts and explicit release conditions.

Do not introduce artificial holds into ordinary performance measurements.

Rehearse the lifecycle cases locally with controlled synthetic resources first.

The native 180-second timeout behavior remains a separate execution-time observation; accelerated fixture tests must be labeled accordingly.

## Complete independent restoration

The watchdog must be able to restore a disposable baseline even if the main driver exits abnormally.

Test normal completion, driver termination, unresponsive diagnostic container and failed restoration verification.

The supervisor must target only the authorized session, remove its container, verify process termination and storage release, and execute the independent restoration procedure.

Preserve failure evidence. A failed restoration must never be reported as success.

Do not assume killing a Docker CLI process removes a running container.

## Full local rehearsal — mandatory

Once integrated, exercise the **complete 36-submission scheduler** against a disposable local Docker setup using Seneca's actual workspace route and deterministic synthetic inference.

The required schedule is:

- 28 load submissions.
- Eight lifecycle submissions.
- Both batching strategies.
- Synchronized 1/2/4-client waves.
- Zero retries.

Require full client/server correlation, terminal accounting, capacity ownership, Docker teardown and independent restoration.

Also run negative cases for missing terminal evidence, duplicate/mismatched correlation, premature slot release, watchdog abort and restoration failure.

Debug and rerun local rehearsals as necessary until the final implementation meets the acceptance criteria.

Do not count failed development attempts against the future native 36-submission budget; that budget applies to the separately authorized native campaign.

Do not declare the local qualification complete while known integration tests are failing.

## Read-only host preparation

After local qualification, complete any permitted non-destructive checks needed to prepare the execution host.

Verify the exact image and artifact identities, credential-free effective settings, published snapshot bindings, model files, CPU configuration and available resources.

Read-only checks must not stop or restart the original service, alter workspace data, or concurrently open live Qdrant backing.

Do not treat an insufficient future maintenance window as grounds to abandon non-destructive preparation. The maintenance-window requirement applies when scheduling the actual campaign.

If host access is unavailable, finish every locally executable part and identify the inaccessible checks precisely.

## Stop conditions

**Do not stop on ordinary implementation problems.**

Stop and request a new authority decision only if completing the task would require:

- A material change to approved scientific or production application behavior.
- An unapproved destructive action against the running service or its data.
- Beginning the native VM Stage 2 campaign without its separate execution authorization.
- Bypassing a demonstrated safety invariant that cannot be restored within this approved scope.
- Access or credentials that are genuinely unavailable and cannot be replaced by a legitimate local fixture.

Otherwise, make the engineering decision and continue.

If a genuinely blocking external dependency remains, complete all independent work before reporting it.

## Deliverable

Return **one completed qualification package**, not another proposal for the next small step.

Include the working adapter, complete local Docker rehearsal, raw correlation records, watchdog and restoration evidence, exact source revision, tests, image verification, and final native-execution readiness disposition.

Preserve failures and their resolutions in the evidence.

Commit and push the completed local engineering work on a reviewable branch.

Keep PRs #3–#6 unmerged and production unchanged.

**You have authority to finish this engineering task autonomously. Do not stop merely because the implementation is harder than expected.**