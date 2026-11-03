# 16K-G — Regression and CI Handoff

**Status:** IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT REVIEW
**Authorized base:** `eb1b3ba0415e05bf91d5e9e6171e087eedd473a9`
**Scope:** Map accepted 16K guarantees to deterministic regression gates and
separate them from empirical, host-specific qualification.
**Authority boundary:** This handoff does not implement CI, modify product code,
or authorize Slice 17.

## Purpose and decision

Slice 17 should turn stable, deterministic 16K contracts into repeatable
regression checks. The checks should use synthetic fixtures, controlled clocks,
fake embedders, and temporary data roots where possible. A generic pull-request
job must not require a particular GPU, CUDA driver, corpus, or host memory state.

The current repository has no `.github/workflows` directory and GitHub reported
no status checks for the reviewed 16K-F branch. This document is a handoff for
a future, separately authorized Slice 17 design/implementation; it is not a
claim that CI exists or is passing.

## Deterministic regression candidates

| Contract | Existing test locations | Recommended generic CI treatment |
|---|---|---|
| Managed operation outlives the request that admitted it; shared capacity and mutation-lease cleanup | `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py` (`test_managed_and_sync_share_ingest_capacity_and_drain`, publication critical-section/shutdown cases); `tests/unit/app/test_slice15d_product_ingest.py` | Required deterministic Python tests. Assert durable terminal state and resource release, not wall-clock throughput. |
| `FAILED` versus `INTERRUPTED`; recovery to prior A or committed B | `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py` (`test_live_recovery_a_then_fail_preserves_error`, `test_startup_recovery_a_interrupts`, `test_recovery_b_succeeds`); `tests/unit/app/test_slice16b_publication_journal.py`; `tests/unit/test_slice12a_recovery_protocol.py`; `tests/unit/test_slice12b_recovery_runtime.py` | Required deterministic state/journal tests. Keep real process-kill/restart as a separate integration smoke, not a timing-sensitive unit assertion. |
| Worklist schema, legacy/null projection, immutability, durable admission and idempotent replay | `tests/unit/app/test_slice16k_b_ingestion_observability.py`; `ui/src/test/slice16k_e_ingestion_worklist.test.tsx` | Required Python and UI contract tests. Validate API schema and rendered operation state independently. |
| Metrics schema and truthful unavailable values | `tests/unit/app/test_slice16k_b_ingestion_observability.py`; `tests/unit/test_slice16k_f_corpus_preparation.py` | Required deterministic validation tests. Missing measurements remain unavailable; no synthetic zero timing. Campaign-evidence validators do not replace API schema tests. |
| Progress bounds, monotonicity, identity, and projection | `tests/unit/app/test_slice16i_managed_operation_progress.py`; `ui/src/test/slice16i_operation_progress_telemetry.test.tsx` | Required deterministic Python/UI tests. Do not assert progress update frequency or elapsed-time thresholds. |
| Capacity limits and preflight ordering | `tests/unit/app/test_slice16k_c_capacity_model.py`; `tests/unit/app/test_slice16k_b_ingestion_observability.py`; `tests/unit/test_large_source_capacity_l4_harness.py` | Required deterministic tests with fixed capability/memory/disk inputs and fakes. Host eligibility and actual available resources are not generic-CI facts. |
| OCR-required zero-block rejection, safe reason mapping, and atomicity | `tests/unit/test_ingestion_pipeline.py`; `tests/unit/app/test_slice16k_b_ingestion_observability.py`; `ui/src/test/slice16k_e_ingestion_worklist.test.tsx`; `ui/src/test/slice16h_integration_acceptance.test.tsx` | Required synthetic parser/API/UI tests. Preserve acceptance of short or partially text-bearing PDFs with usable blocks. Do not require an OCR engine. |
| Idempotency and content/cache identity | `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py`; `tests/unit/app/test_slice16k_b_ingestion_observability.py`; `tests/unit/test_ingestion_pipeline.py` | Required deterministic byte-identity and replay tests. Cache hits may be asserted using controlled artifacts; do not infer GPU acceleration from reuse. |
| No partial publication on failure; prior snapshot remains visible | `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py`; `tests/unit/app/test_slice16b_publication_journal.py`; `tests/unit/app/test_slice15d_product_ingest.py`; `tests/unit/test_ingestion_pipeline.py` | Required deterministic failure-injection tests. Compare revision, snapshot, and active source identities before and after rejection. |
| Safe retry, terminal operation recovery, and user-visible error/worklist state | `ui/src/test/slice16h_integration_acceptance.test.tsx`; `ui/src/test/slice16k_e_ingestion_worklist.test.tsx`; `ui/src/test/workspace_source_loading_state.test.tsx`; `ui/src/test/slice16k_r04_cuda_oom.test.tsx` | Required UI tests for deterministic state transitions and error mapping; do not use sleep-based timing as the oracle. |

These are candidate contract tests already present in the repository, not a
claim that each file was executed in this handoff. Slice 17 should select stable
commands and report results from its own implementation/CI run.

## Empirical and host-specific checks

Keep these outside the generic deterministic PR gate. Run them as explicit,
recorded qualification or release checks when the relevant hardware/corpus is
available:

- CUDA model load, real embedding throughput, VRAM residency, allocator reserve,
  device-wide memory, CUDA OOM behavior under actual drivers, and performance
  deltas. Mocked CUDA-OOM retry tests remain suitable for generic CI, but do not
  establish physical-device qualification.
- Large-PDF parser RSS, native parser stability, temporary-disk amplification,
  and end-to-end latency on representative real documents.
- Actual host `MemAvailable`, GPU availability, filesystem free-space, and
  product capability eligibility. Unit tests can cover the decision function
  with injected values; they cannot qualify the executing host.
- The accepted 38-source 16K-F cold/warm campaign and grounded queries. Preserve
  its descriptive evidence in
  [`RUN_002_EVIDENCE_INDEX.md`](../16k_f_execution/RUN_002_EVIDENCE_INDEX.md).
  The original 39-primary/60-minute objective is retired for the current beta
  and was not passed or failed by the replacement-corpus measurements.
- Supplemental Markdown managed-API smoke and largest-source live ingestion;
  retain their evidence as environment-specific checks rather than multiplying
  generic CI runtime or depending on private corpus data.

The repository has an `integration` pytest marker, but this review found no
workflow configuration that schedules it. Slice 17 should explicitly decide
which fast deterministic suites run on each pull request and which heavier
integration suites run separately. Do not classify an unconfigured command as
a current required check.

## Known CI risk and current limits

`TEST-STARTUP-01` remains open: a selected `TestClient` lifespan/startup batch
waited at startup without an assertion failure, and its responsible startup
component is not established. The real abrupt-kill/restart recovery scenario
was separately exercised successfully. Slice 17 should not mislabel that hang
as a product recovery failure; it should either keep the affected invocation
out of a blocking lane with a visible follow-up, or resolve the startup hang
before making that invocation a required check.

No test suite, type check, linter, workflow, corpus run, or hardware execution
was run for this documentation-only handoff. The source/test mapping above is
based on repository inspection. There is no claim of CI success.

## Slice 17 boundary

Slice 17 may use this handoff to design a bounded deterministic regression CI
plan. It must separately decide workflow placement, required commands, timeout
budgets, dependency/service provisioning, and treatment of the known startup
hang. Real CUDA throughput is not a generic CI gate. Slice 17 implementation,
new product behavior, new scientific qualification, and beta performance SLOs
remain outside this 16K-G handoff.
