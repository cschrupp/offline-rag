# Slice 17A — Baseline Execution Supplement

**Status:** Supplemental baseline evidence, recorded before CI qualification
**Baseline code subject:** `415616b5c330352d02b85371edb68d89a87408fb`
**Branch:** `feature/slice17-regression-ci`
**Date:** 2026-11-09

This supplement adds the complete backend run from a compatible, unsandboxed
execution context and the bounded investigation of the `TestClient` stall. It
does not replace or rewrite the original baseline inventory.

## Backend full-suite outcome

The first sandboxed invocation was:

```bash
UV_CACHE_DIR=/tmp/slice17-uv-cache timeout 900 uv run pytest
```

It collected 2,219 tests, printed three completed Docling integration tests,
then stopped making progress before a summary. The watchdog returned 124 after
900 seconds. Its terse progress output did not identify the active test.

The same complete suite was then run outside the restricted sandbox:

```bash
UV_CACHE_DIR=/tmp/slice17-uv-cache timeout 900 uv run pytest -q
```

Observed result: **42 failed, 2,176 passed, 1 skipped, 8 warnings in 567.85
seconds**. This run completed; it did not hang. A failure-only replay reported
41 failures and one pass in 70.05 seconds. The quiet replay did not retain the
identity of the one non-reproduced failure. The subsequent verbose replay
reproduced the same 41 failures listed below. The extra one-off failure is
therefore classified **C** as non-reproducible run-context/test-order
instability; its exact test ID was not retained in the quiet output and is an
evidence limitation of that run.

### Category B — Test setup or expectation defect (30 reproduced cases)

These cases fail through stale mocks, fixture shapes, assertions or expected
copy that no longer match the accepted implementation. They are not selected
for the deterministic Slice 17 lane; relevant currently accepted 16K contracts
are covered by the passing selected suites in the implementation result.

```text
tests/unit/app/test_slice15a_foundation.py::test_d08_catalog_complete_and_mapped
tests/unit/app/test_slice15e_product_query_traces.py::test_query_reuses_process_scoped_resources
tests/unit/app/test_slice15f_admission_deadlines_shutdown.py::test_query_overload_and_independent_capacity_classes
tests/unit/app/test_slice15f_admission_deadlines_shutdown.py::test_cancel_keeps_capacity_until_worker_ends
tests/unit/app/test_slice15f_admission_deadlines_shutdown.py::test_short_deadline_maps_to_request_timeout
tests/unit/app/test_slice15f_admission_deadlines_shutdown.py::test_generation_timeout_when_deadline_not_expired
tests/unit/app/test_slice15f_admission_deadlines_shutdown.py::test_query_disconnect_records_request_cancelled
tests/unit/app/test_slice15f_admission_deadlines_shutdown.py::test_grace_expiry_does_not_fabricate_request_timeout
tests/unit/app/test_slice15f_admission_deadlines_shutdown.py::test_health_live_responsive_during_drain_and_held_query
tests/unit/app/test_slice15f_admission_deadlines_shutdown.py::test_product_query_passes_control_checkpoint_into_orchestrator
tests/unit/app/test_slice15g_container_packaging.py::test_compose_static_contract
tests/unit/app/test_slice15h_integration_closeout.py::test_complete_product_path_replace_and_read_during_ingest
tests/unit/app/test_slice15h_integration_closeout.py::test_secret_non_leakage_in_health_errors_traces
tests/unit/app/test_slice15h_integration_closeout.py::test_query_overload_fail_fast
tests/unit/app/test_slice16b_integrity_rework.py::test_f7_failure_recovery_holds_corpus_lease
tests/unit/app/test_slice16b_integrity_rework.py::test_f12_pipeline_supersession_isolation
tests/unit/app/test_slice16b_rework_hardening.py::test_f6_supersession_old_marker_absent
tests/unit/app/test_slice16b_rework_hardening.py::test_f6_batch_add_remove_without_reupload
tests/unit/app/test_slice16l_embedding_auto_device.py::test_no_mid_run_cpu_fallback
tests/unit/test_grounded_generation.py::test_unauthorized_endpoint_not_probed
tests/unit/test_lexical_exclude_zero_term_v1.py::test_managed_operation_metrics_lexical_projection_and_legacy_null
tests/unit/test_slice12b_recovery_runtime.py::test_non_empty_initial_skips_rewrite_and_second_retrieval
tests/unit/test_slice12b_recovery_runtime.py::test_disabled_recovery_skips_rewrite_on_empty
tests/unit/test_slice12b_recovery_runtime.py::test_enabled_empty_recovers_and_generates_with_original_query
tests/unit/test_slice12b_recovery_runtime.py::test_noop_rewrite_accepted
tests/unit/test_slice12b_recovery_runtime.py::test_persistent_insufficiency_after_recovery
tests/unit/test_slice12b_recovery_runtime.py::test_rewrite_failure_no_recovery_retrieval
tests/unit/test_slice12b_recovery_runtime.py::test_recovered_context_latency_used_in_generation_provenance
tests/unit/test_slice12b_recovery_runtime.py::test_recovery_execution_failure_no_retry
tests/unit/test_slice12b_recovery_runtime.py::test_lineage_mismatch_fails_closed
```

The repeated failure classes include fake callables missing newer keyword
parameters, fake Qdrant objects missing the current `search` contract,
structured-output fixtures rejected by the current response contract, stale
error-text expectations, and incomplete fixture fields. No product regression
was established by these failures.

### Category C — Environment or local-state defect

```text
tests/unit/test_slice13b_authoritative_wiring.py::test_authoritative_pin_mismatch_fails_preflight_without_q3_writes
```

This test consults the repository's ignored `eval/results/security_13b/`
directory, which already contains local artifacts. It fails the clean-root
assertion even though its actual Q3 output is redirected under `tmp_path`.
The generated artifacts are not tracked. A hosted clean checkout does not have
this local state. This test is not included in the required lane.

The isolated managed-operation test with a sandbox stall is
`tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_managed_add_survives_simulated_deadline_and_publishes`.
With `-o faulthandler_timeout=10`, the pytest thread was waiting in AnyIO's
`run_sync_from_thread`; the `asyncio-portal` thread was idle in
`selectors.select`, and the stack located the wait at
`starlette.testclient.TestClient.__enter__`. The same exact test passed outside
the restricted sandbox in 5.47 seconds. Prior accepted API verification
identified the sandbox's cross-thread wake-socket `EPERM`; the current dump
confirms the lifecycle wait location, but is not itself a syscall trace.

**17E disposition: RESOLVED for CI execution.** No product runtime change was
needed. The affected deterministic test remains in the required backend lane,
which runs on a normal hosted Linux runner. This Codex sandbox may still hang
on that exact invocation; use the compatible unsandboxed test command for local
verification. This disposition does not assert a kernel-level cause beyond the
prior `EPERM` evidence and the comparative run.

### Category E — Historical/non-authoritative test debt (10 reproduced cases)

```text
tests/unit/app/test_slice15h_integration_closeout.py::test_openapi_exact_product_path_set
tests/unit/app/test_slice15h_integration_closeout.py::test_d08_closeout_evidence_matrix_complete
tests/unit/test_performance14_level_c_preflight.py::test_reranker_model_path_missing_fails
tests/unit/test_slice16e_engineering_evidence.py::test_committed_manifest_byte_identical_and_stable_id
tests/unit/test_slice16e_engineering_evidence.py::test_deterministic_record_ordering
tests/unit/test_slice16e_engineering_evidence.py::test_source_hash_emitted_and_locator_preserved
tests/unit/test_slice16e_engineering_evidence.py::test_14c_machine_extraction_from_committed_artifacts
tests/unit/test_slice16e_engineering_evidence.py::test_check_mode_passes_and_detects_drift
tests/unit/test_slice16e_engineering_evidence.py::test_security_and_recovery_semantics_present_in_manifest
tests/unit/test_slice16e_engineering_evidence.py::test_level_c_approximate_and_unevaluable
```

The OpenAPI test freezes a historical route set that predates accepted Gold Lab
and settings routes; the D08 closeout matrix likewise freezes an older error
catalog. The performance preflight uses a stale frozen lexical identity. The
16E evidence tests depend on a source hash for
`docs/milestone7_performance_ui.md` that no longer matches that document. These
tests remain preserved but are not authoritative gates for the current beta or
Slice 17's required contracts.

## Frontend baseline corrections and result

The initial frontend baseline found five stale `Operation` fixture fields and
three Rapid Fire test queries that inspected rendered text instead of the
accepted accessible button names. These were bounded test corrections; no
product semantics or UI labels changed. The four baseline `react-hooks` lint
errors were corrected without changing ESLint configuration. Three intentional
one-time state initializations retain narrow, documented rule suppressions so
the preview snapshot and preferred-baseline behavior remain unchanged.

Final frontend commands and results:

| Command | Result |
| --- | --- |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm test` | PASS — 49 files, 459 tests |
| `npm run build` | PASS; Vite reports its existing advisory that one JS chunk exceeds 500 kB |

The three UI test failures are closed; the five CUDA-OOM fixture typing errors
are closed. The npm audit output during `npm ci` reported 10 moderate and 3
high advisories. No dependencies were upgraded and the advisories were not
modified under Slice 17.

## Bounded required backend lane

The exact required test-file set is listed in
[`BASELINE_INVENTORY.md`](BASELINE_INVENTORY.md) and encoded in
`.github/workflows/ci.yml`. It includes the REL-03 mocked profile-isolation
suite. The test process receives empty external credential variables, a
closed-loopback HTTP(S) proxy, and a test-level DNS guard for `openrouter.ai`.

Final verification after the bounded corrections:

| Check | Result |
| --- | --- |
| Targeted Ruff over `src/offline_rag/app`, `src/offline_rag/api`, and the required backend tests | PASS |
| Required deterministic backend set | PASS — 208 tests, 31.69 seconds, 1 Starlette/httpx deprecation warning |
| Real OpenRouter/Ollama/model calls | None |

The full-repository Ruff baseline reported 165 findings before the bounded
lint cleanup. The CI lane intentionally checks the required backend app/API
and test paths rather than treating all historical repository lint findings
as Slice 17 blockers. The full-repository Ruff command was not rerun after the
targeted cleanup; the old repository-wide debt remains outside this lane and
must not be described as globally clean.

No hosted CI run was available during preparation. The workflow will be
exercised by the first eligible pull-request or main push event; no hosted
result is claimed here.
