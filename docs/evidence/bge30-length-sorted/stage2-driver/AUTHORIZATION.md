# Seneca — CPU Stage 2 Driver Qualification and Final Execution Gate

## Independent review disposition

Accept the integrated source candidate:

`1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e`

Accept its provenance and research evidence at:

`bb3f614188e95f9d83d3b0cccbf9452dac7f67e7`

Draft PR #6:
https://github.com/cschrupp/offline-rag/pull/6

Both hosted backend and frontend jobs have passed on the source commit and evidence head.

The derivative diagnostic image design is acceptable for isolated qualification, subject to verifying the exact Docker artifact on the intended execution host.

**This authorization permits local driver implementation, offline rehearsal, and non-destructive readiness preparation only. It does not authorize VM maintenance or the 36-submission campaign.**

## Task 1 — Implement the bounded Stage 2 driver

Use the frozen protocol:

`docs/evidence/bge30-length-sorted/stage2-integration/PROTOCOL.md`

Implement the exact workload schedule for:

- Recipes revision 4.
- Rich revision 2.
- BGE-30 consecutive.
- BGE-30 length_sorted_8.

Enforce 28 load submissions and eight lifecycle submissions maximum, 36 total, zero retries.

Count all client sends, including rejected, disconnected, canceled and failed requests.

Use the same diagnostic image, application route, provider fixture, source scope and scientific configuration for both strategies.

Only the batching strategy may vary.

## Task 2 — Validate lifecycle and watchdog behavior locally

Rehearse the complete driver against synthetic local fixtures before using real model artifacts.

Prove:

- Wave synchronization and request counting.
- No extra warm-up or retry.
- Preflight and query-slot rejection classification.
- Operation identity and terminal-event correlation.
- Client disconnect versus actual worker completion.
- Cooperative deadline recognition after held inference.
- Capacity retention until worker termination.
- Shutdown drain beyond transport grace.
- Bounded barrier release and cleanup following exceptions.
- Client watchdog and independent host watchdog behavior.
- Resource-limit abort stops new submissions.
- No incomplete session can be reported as passing.

The driver must provide a bounded way to observe the actual scorer forward without replacing its scientific computation.

If this requires changing application source or scientific inference behavior, stop and present the conflict for independent review.

Do not use the production VM for these rehearsals.

## Task 3 — Reconcile the diagnostic image artifact

Inspect the locally retained image identified as:

`sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04`

Verify image identity, source file digests, provider fixture, Python environment, CPU-only Torch, execution defaults and scientific fingerprints.

Prepare an offline export/import procedure with explicit digest verification.

Distinguish Docker image ID from repository or manifest digest. Verify the appropriate identities rather than assuming those fields are interchangeable.

Do not substitute a rebuilt derivative if its identity or effective dependencies differ without recording and reviewing that difference.

Prepare host-side read-only verification commands, but do not execute VM maintenance.

## Task 4 — Freeze artifact and publication checks

Make the host preflight executable and fail-closed.

Require:

- Exact Recipes logical source identity and original question scope.
- Exact Rich single-document binding.
- Workspace revisions and published snapshot IDs.
- Snapshot manifests and real backing completeness.
- Source inventories and publication pointers.
- BGE model and tokenizer file digests.
- ONNX embedding representation file digests.
- Identical scientific settings for both arms.
- Four effective CPUs, prescribed Torch and ONNX settings.
- Exclusive isolated Qdrant ownership.
- Read-only model files and no external network access.

A missing source, mismatched artifact or incomplete publication must stop before service maintenance.

## Task 5 — Freeze operational limits

Use the proposed envelope unless independent review explicitly revises it:

- At least 4,800 seconds before automatic VM STOP.
- At most 2,400 seconds of diagnostic execution.
- At least 900 seconds reserved for restoration.
- Diagnostic RSS ceiling of 6 GiB.
- At least 2 GiB of host available RAM.
- 180-second cooperative query deadline.
- Independently bounded client and host watchdogs.

Reconcile the proposed 195-second client watchdog with the actual shutdown, held-inference and cleanup sequence.

Demonstrate that watchdog expiry cannot cause premature capacity release or resource closure.

## Task 6 — Acceptance evidence

Deliver:

1. Driver source and exact revision.
2. Full local rehearsal results.
3. Verified local image identity and offline transfer procedure.
4. Frozen, validated workload manifest.
5. Source and artifact preflight procedure.
6. Resource and deadline budget.
7. Explicit abort and restoration state machine.
8. Per-submission accounting and reporting schema.
9. Remaining limitations and failed gates.
10. Exact proposed final VM execution authorization.

Retain this authorization prompt and complete Codex response.

Commit and push a separate reviewable preparation revision.

Do not merge PRs #3–#6, deploy, modify production, change defaults, touch live workspace data, or begin Stage 2.

**Stop at the final execution-readiness checkpoint for independent review.**