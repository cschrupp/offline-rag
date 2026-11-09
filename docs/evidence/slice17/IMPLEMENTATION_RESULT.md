# Slice 17 — Regression CI Implementation Result

**Status:** IR-002 corrective locally qualified; post-correction hosted run pending
**Branch:** `feature/slice17-regression-ci`
**Canonical starting point:** `5a793766bb4ecd88278cd0bf3a892572ec30f67a`
**Baseline inventory:** `415616b5c330352d02b85371edb68d89a87408fb`
**Baseline supplement:** `18780a43c2a2b9c9099a92c7a0dc0846a89901c2`

This record documents the bounded CI candidate, local qualification, and
hosted GitHub Actions results. It does not claim slice acceptance or promotion.

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
below. REL-03 deployment-profile/model/key variables are absent from the job
environment; proxy traffic is routed to a closed loopback port. The REL-03
profile-isolation suite also guards against DNS access to `openrouter.ai` and
uses mocks; no live inference was performed.

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
18.00 seconds**, with one Starlette/httpx deprecation warning. The tests were
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
| `npm test` | PASS — 49 files, 459 tests in 173.58 seconds |
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
required CI backend lane. The test selects the explicit fake tokenizer and
replaces only the tiktoken-artifact readiness probe; the real FastAPI lifespan,
Docling check, generation-config check, and remaining startup work still run.
The exact test passed again locally in 1.89 seconds with this fixture. In the
restricted Codex sandbox, the invocation can stall while the test thread waits
for the AnyIO portal startup handshake; a thread dump locates the wait at
`TestClient.__enter__`, while the portal thread is idle in selector polling.
Prior accepted API verification identified a sandbox cross-thread wake-socket
`EPERM`. The present dump is not itself a syscall trace, and the underlying
sandbox behavior remains unexplained at the kernel level.

The exact test passed in hosted PR run `42574304259`; that run reported 142
passed and 67 skipped overall. Its explicit fake-tokenizer path could not take
the tiktoken-artifact skip. IR-002 applies the same deterministic setup to the
other tests in its required suites. The exact test also passed in the clean
local corrected lane; fresh hosted confirmation for the corrected lane is
pending. The sandbox-specific stall remains documented and no production
runtime change was made.

The full backend baseline run is separately preserved in
[`BASELINE_SUPPLEMENT_01.md`](BASELINE_SUPPLEMENT_01.md): 42 failures, 2,176
passes, one skip, and eight warnings in 567.85 seconds. Repeated failures were
classified and exact exclusions are retained there. This bounded CI candidate
does not claim the entire repository test suite is green.

## Hosted status and limits

The first PR-triggered runs did not execute jobs. Runs `42571509744` and
`42572040099` ended with workflow-level failure and zero jobs;
`gh run view --verbose` reported a workflow-file issue. Static validation
identified two defects: the nonexistent `astral-sh/setup-uv@v10` ref, and
case-insensitive duplicate environment keys `NO_PROXY` / `no_proxy`. The
workflow now pins the verified `v10.3.3` release and keeps only `NO_PROXY`.
These runs are workflow-configuration failures, not test results. Hosted status
for the prior candidate is **PASS** from run `42574304259`, where both jobs
executed and passed. A fresh PR run is pending for the IR-002 corrective. If
future repository or account configuration prevents hosted execution, report
`CI_EXECUTION_UNAVAILABLE` rather than a pass.

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
| F002 — Independent rewriter/judge configuration was not asserted | Added a deterministic profile-overlay test using distinct local configurations; no HTTP calls. Focused REL-03 suite: 20 passed in 1.09 seconds on this candidate. |
| F003 — Startup status claimed resolution before hosted execution | Interim status was `PENDING HOSTED CONFIRMATION`; after hosted run `42574304259` passed the exact test, it is now `RESOLVED FOR SUPPORTED CI EXECUTION`. |
| F004 — Ruff exclusions lacked an exact inventory | Reran full Ruff after bounded corrections. The 156 remaining diagnostics are listed by file, line, and rule in the linked Ruff inventory. |

The first two hosted attempts exposed workflow-only setup defects. The
corrective pins the valid setup-uv release and removes the duplicate
case-insensitive proxy key. Runs `42571509744` and `42572040099` are not test
results because GitHub created no jobs.

The first parsed hosted run, `42572292895`, created both jobs. The backend
lint/install steps passed; pytest reported 140 passed, 68 skipped, and one
failure. The failure was
`test_remote_ancestry_begins_at_15d_baseline`: the test requires historical
commit `02544e3974da6e26ec512a83f856b1e8d864d86d`, which is absent from the
default depth-1 checkout. The backend checkout now requests full history so
that this required ancestry contract has its input. The exact
`test_managed_add_survives_simulated_deadline_and_publishes` test was among the
artifact-dependent skips: its shared fixture required a provisioned tiktoken
cache even though this lifecycle check uses a fake embedder and does not test
tokenizer behavior. That one test now selects the existing deterministic fake
tokenizer explicitly and substitutes only the tiktoken-artifact readiness
probe. The real FastAPI lifespan, Docling readiness check, generation
configuration check, and remaining startup path still execute; other tests in
the module retain their real-artifact requirement. The frontend job in run
`42572292895` completed **PASS** across
lint, typecheck, 49 files / 459 tests, and build. Its backend failures and
skipped lifecycle test were resolved and verified in the subsequent run below.

PR run `42574304259` completed both hosted jobs **PASS** on corrective commit
`53e170cdd4f55c5c0a5cf6fe4f4c5257a740c4cb`. Backend setup, lint, and the
required deterministic regressions passed (142 passed, 67 artifact-dependent
skips, one deprecation warning); the exact managed-add startup test passed.
Frontend dependency installation, lint, typecheck, tests, and build all passed.
This run resolves the hosted-execution gate for this corrective. The current
evidence-only update will trigger one final PR run to validate the recorded
status and documentation.

Independent re-review identified that the 67 skips were all shared-fixture
guards for missing tiktoken artifacts in three required suites. The exact
pre-correction node IDs and the shared skip reason are recorded in
[`HOSTED_SKIP_INVENTORY_IR002.md`](HOSTED_SKIP_INVENTORY_IR002.md). The current
corrective removes that accidental dependency without changing production
startup policy. Each of the three modules selects the existing fake tokenizer
for its generic request/publication/recovery/observability tests and narrowly
replaces only startup's tokenizer-artifact readiness probe. Docling readiness,
generation static validation, the FastAPI lifespan, and all other runtime
startup behavior remain active. None of these suites tests tokenizer
provisioning or token identity.

In a clean tracked clone with tokenizer artifacts absent, the exact required
backend lane then reported **209 passed, 0 skipped**, with one
Starlette/httpx deprecation warning in 37.67 seconds. This includes the exact
managed-add startup regression. Targeted Ruff passed; focused REL-03 tests
reported 20 passed. The post-IR-002 hosted run is still pending. No models or
external inference were used.

## Candidate disposition

```yaml
slice: 17
implementation: CANDIDATE_PREPARED
local_backend_lane: PASS_209_ZERO_SKIPS_CLEAN_CLONE
local_frontend_lane: PASS
rel03_profile_isolation: MOCKED_AND_REQUIRED
test_startup_01: PRIOR_HOSTED_PASS_CURRENT_HEAD_RECHECK_PENDING
hosted_ci: PRIOR_HEAD_PASS_POST_IR002_PENDING
repository_wide_ruff: HISTORICAL_DEBT_REMAINS
full_pytest_suite: BASELINE_FAILURES_DOCUMENTED
human_acceptance: PENDING
promotion: NOT_AUTHORIZED
```
