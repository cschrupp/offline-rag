# Slice 17 — Regression CI Implementation Result

**Status:** Corrective candidate prepared; hosted run pending
**Branch:** `feature/slice17-regression-ci`
**Canonical starting point:** `5a793766bb4ecd88278cd0bf3a892572ec30f67a`
**Baseline inventory:** `415616b5c330352d02b85371edb68d89a87408fb`
**Baseline supplement:** `18780a43c2a2b9c9099a92c7a0dc0846a89901c2`

This record describes the bounded CI candidate and its local qualification. It
does not claim a hosted GitHub Actions run, slice acceptance, or promotion.

## Workflow

The candidate adds one canonical workflow at
`.github/workflows/ci.yml`:

- Runs on pull requests and pushes to `main`.
- Uses Linux, Python 3.14, Node 22, frozen `uv` dependencies, and `npm ci`.
- Has separate backend and frontend jobs with 20-minute job timeouts.
- Cancels superseded pull-request runs, but does not cancel main-branch runs.
- Grants only `contents: read`.
- Does not provision CUDA, models, external credentials, Docker, private
  corpora, or empirical performance measurements.

The backend job runs targeted Ruff checks and the deterministic test-file set
below. It sets external inference credentials to empty values, routes proxy
traffic to a closed loopback port, and includes a test-level DNS guard for
`openrouter.ai` in the REL-03 profile-isolation suite. REL-03 tests use mocks;
no live inference was performed.

## Required backend lane

The workflow statically checks `src/offline_rag/app`, `src/offline_rag/api`,
and the selected test files. Its deterministic pytest set is:

```text
tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py
tests/unit/app/test_slice16b_publication_journal.py
tests/unit/app/test_slice15d_product_ingest.py
tests/unit/app/test_slice16k_b_ingestion_observability.py
tests/unit/app/test_slice16i_managed_operation_progress.py
tests/unit/app/test_slice16k_c_capacity_model.py
tests/unit/test_large_source_capacity_l4_harness.py
tests/unit/test_ingestion_pipeline.py
tests/unit/test_slice16k_f_corpus_preparation.py
tests/unit/test_slice16k_r04_preflight.py
tests/unit/test_rel03_external_inference_demo_profile.py
```

Locally, targeted Ruff passed. The required test set passed: **209 passed in
28.02 seconds**, with one Starlette/httpx deprecation warning. The tests were
run in a compatible unsandboxed context because this restricted Codex sandbox
can stall on a TestClient cross-thread wake path. No OpenRouter, Ollama, or
other model calls occurred.

Repository-wide Ruff is not claimed green. After the bounded corrections,
`uv run ruff check src tests` reported **156 remaining diagnostics**. The exact
file, line, and rule for each is recorded in
[`RUFF_REMAINING_DIAGNOSTICS.md`](RUFF_REMAINING_DIAGNOSTICS.md). The required
app/API/test lane is intentionally narrower; the remaining repository debt is
visible rather than silently treated as a pass or repaired wholesale.

## Required frontend lane

The workflow exposes `npm ci`, lint, typecheck, tests, and build as separate
steps. Local checks passed:

| Command | Result |
| --- | --- |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm test` | PASS — 49 files, 459 tests in 159.19 seconds |
| `npm run build` | PASS; Vite emitted its existing advisory for a JavaScript chunk over 500 kB |

`npm ci` completed from the committed lockfile without changing dependency
manifests or locks. npm reported 10 moderate and 3 high advisories; no
dependency updates or audit-driven changes were made under this slice.

The bounded frontend corrections update stale accessible-name queries and
incomplete operation fixtures, and address the four observed React Hooks lint
errors without changing lint configuration. Preview task freezing and
preferred-baseline initialization semantics are preserved with narrowly
documented rule suppressions.

## TEST-STARTUP-01 disposition

The exact test
`tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_managed_add_survives_simulated_deadline_and_publishes`
passed in a compatible unsandboxed run in 5.47 seconds and is included in the
required CI backend lane. In the restricted Codex sandbox, the invocation can
stall while the test thread waits for the AnyIO portal startup handshake; a
thread dump locates the wait at `TestClient.__enter__`, while the portal thread
is idle in selector polling. Prior accepted API verification identified a
sandbox cross-thread wake-socket `EPERM`. The present dump is not itself a
syscall trace, and the underlying sandbox behavior remains unexplained at the
kernel level.

Disposition: **PENDING HOSTED CONFIRMATION**. The exact test is green in the
compatible unsandboxed execution environment and remains required in hosted
CI. Hosted execution has not occurred yet. No production runtime change was
made; the sandbox-specific stall is documented and does not establish a
product recovery defect. If the test passes on the supported hosted runner,
record `RESOLVED FOR SUPPORTED CI EXECUTION`; if it fails or stalls, reopen the
investigation without weakening the lane.

The full backend baseline run is separately preserved in
[`BASELINE_SUPPLEMENT_01.md`](BASELINE_SUPPLEMENT_01.md): 42 failures, 2,176
passes, one skip, and eight warnings in 567.85 seconds. Repeated failures were
classified and exact exclusions are retained there. This bounded CI candidate
does not claim the entire repository test suite is green.

## Hosted status and limits

No hosted GitHub Actions run was available during preparation. Hosted status is
therefore **PENDING / NOT CLAIMED**. The first eligible pull-request or
main-branch push event must establish hosted execution; if repository or
account configuration prevents it, report `CI_EXECUTION_UNAVAILABLE` rather
than a pass.

CUDA/device-memory behavior, real models and external services, private
corpora, large-corpus ingestion, physical capacity, and all performance
benchmarks remain outside generic CI. The workflow does not create latency or
performance SLOs.

## Independent review corrective pass

The bounded corrections requested for candidate
`ddb015fe584fa32ce2c430c4ee943cf52f12d5c9` are handled as follows:

| Finding | Disposition |
| --- | --- |
| F001 — Empty REL-03 inputs make the default CI environment invalid | Removed external inference key variables from the workflow. GitHub secrets are not injected into jobs unless explicitly configured. |
| F002 — Independent rewriter/judge configuration was not asserted | Added a deterministic profile-overlay test using distinct local configurations; no HTTP calls. Focused REL-03 suite: 20 passed in 1.73 seconds. |
| F003 — Startup status claimed resolution before hosted execution | Changed to `PENDING HOSTED CONFIRMATION`; the exact test remains in CI. No hosted run is claimed. |
| F004 — Ruff exclusions lacked an exact inventory | Reran full Ruff after bounded corrections. The 156 remaining diagnostics are listed by file, line, and rule in the linked Ruff inventory. |

The hosted pull-request run is the remaining verification gate for both CI
jobs and `TEST-STARTUP-01`.

## Candidate disposition

```yaml
slice: 17
implementation: CANDIDATE_PREPARED
local_backend_lane: PASS
local_frontend_lane: PASS
rel03_profile_isolation: MOCKED_AND_REQUIRED
test_startup_01: PENDING_HOSTED_CONFIRMATION
hosted_ci: NOT_YET_EXECUTED
repository_wide_ruff: HISTORICAL_DEBT_REMAINS
full_pytest_suite: BASELINE_FAILURES_DOCUMENTED
human_acceptance: PENDING
promotion: NOT_AUTHORIZED
```
