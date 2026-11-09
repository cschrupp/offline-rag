# Slice 17A — Repository Baseline Inventory

**Status:** Recorded before test corrections or CI workflow changes
**Baseline commit:** `415616b5c330352d02b85371edb68d89a87408fb`
**Canonical starting point:** `5a793766bb4ecd88278cd0bf3a892572ec30f67a`
**Branch:** `feature/slice17-regression-ci`
**Inventory date:** 2026-11-09

This inventory records the observed baseline on the Slice 17 feature branch
after the documentation-only opening commit. No test, application, dependency,
or workflow files were changed before these commands ran. No model, OpenRouter,
Ollama, GPU, private corpus, or live application inference was used.

## Environment

| Component | Observed version / identity |
| --- | --- |
| OS | Ubuntu 24.04 under WSL2; Linux `6.18.33.2-microsoft-standard-WSL2`, x86_64 GNU/Linux |
| Python used by project | Python 3.14.5 |
| `uv` | 0.11.18 |
| Node.js | v22.23.3 |
| npm | 12.2.0 |

The system `python3` was 3.12.7; project commands used the locked Python 3.14.5
environment. The repository requires Python `>=3.14,<3.15`; `ui/package.json`
requires Node `>=22`.

## Backend baseline

Commands were run separately. `UV_CACHE_DIR` is redirected to `/tmp` because
the default user cache was not writable in this environment; this did not
change dependency declarations or lockfiles.

| Command | Result | Evidence |
| --- | --- | --- |
| `UV_CACHE_DIR=/tmp/slice17-uv-cache uv sync --frozen` | PASS; 150 packages checked; lock unchanged | Command output in execution record; no dependency update |
| `UV_CACHE_DIR=/tmp/slice17-uv-cache uv run ruff check src tests` | FAIL; 165 diagnostics | `/tmp/slice17-baseline-ruff.log` |
| `UV_CACHE_DIR=/tmp/slice17-uv-cache timeout 900 uv run pytest` | TIMEOUT, exit 124 after 900 seconds; 2,219 tests collected; no assertion failure or final pass/skip/xfail summary observed | `/tmp/slice17-baseline-pytest.log` |

Ruff diagnostic counts by rule:

```text
B017 6, BLE001 1, F401 12, F541 1, I001 43, PIE807 2, PIE808 1,
PIE810 1, PLR0402 1, PLR1730 1, PYI034 1, RUF012 5, RUF022 9,
RUF046 3, RUF059 5, RUF100 13, S110 9, SIM102 4, SIM103 9,
SIM113 1, SIM114 1, SIM117 12, TRY004 20, UP035 3, UP047 1
```

Pytest output shows the three tests in
`tests/integration/test_docling_pdf.py` completed, then progress entered
`tests/unit/api/test_diag_gpu_probe.py`. The command produced no final summary
and no exact blocked test ID was established. This is a timeout, not a pass.
The managed-operation `TEST-STARTUP-01` remains open for the bounded 17E
investigation; the observed output alone does not establish that it caused this
full-suite timeout.

The Docling integration tests comprise:

- `tests/integration/test_docling_pdf.py::test_pdf_fixture_checksum` — a
  deterministic fixture checksum check; it completed in the observed run.
- `tests/integration/test_docling_pdf.py::test_docling_born_digital_pdf_parse`
  — requires provisioned local Docling artifacts and performs real PDF parsing.
- `tests/integration/test_docling_pdf.py::test_ingest_pdf_via_pipeline` —
  requires the same artifacts and runs the real parser through ingestion.

The last two are non-generic qualification tests for the generic PR lane because
that lane must not provision model/parser artifacts. Their observed local
success does not make them generic deterministic CI tests. Preserve them as
separate qualification coverage; do not blanket-ignore the integration file.

## Frontend baseline

Commands ran separately from `ui/`. The first `npm ci` attempt could not resolve
the package registry in the restricted network environment. Retrying with an
explicit temporary npm cache and the permitted registry connection succeeded;
the package lock was not changed.

| Command | Result | Evidence |
| --- | --- | --- |
| `npm_config_cache=/tmp/slice17-npm-cache npm ci` | PASS; 249 packages added, 250 audited; npm reported 10 moderate and 3 high advisories | Execution output; no dependency updates |
| `npm run lint` | FAIL; 4 errors and 2 warnings | `/tmp/slice17-baseline-ui-lint.log` |
| `npm run typecheck` | FAIL; 5 TypeScript diagnostics in one pre-existing CUDA OOM test fixture | Command output; detailed file/lines below |
| `npm test` | FAIL; 49 files: 47 passed, 2 failed; 459 tests: 456 passed, 3 failed; 172.08 seconds | `/tmp/slice17-baseline-ui-test.log` |
| `npm run build` | FAIL before Vite build; same five TypeScript diagnostics as `npm run typecheck` | `/tmp/slice17-baseline-ui-build.log` |

### Frontend findings

**TypeScript fixture errors (category B):** all five diagnostics are in
`ui/src/test/slice16k_r04_cuda_oom.test.tsx`: missing `operation_id` at lines
14, 38, and 52, and missing `retryable` at lines 75 and 100. The build failure
is the same typecheck failure, not a separate build defect. Owner: 17C, for a
bounded fixture correction before requiring typecheck/build in CI.

**UI test failures (category B, subject to focused confirmation before edits):**

1. `src/test/slice16g_i2_expert_work.test.tsx > 16G-I2 Rapid Fire / Question
   Check session (direct work session) > commits Rapid Fire with exact body,
   ids, idempotency, and frozen cohort` — test expects rendered text matching
   `/0 — Irrelevant/`; current control presentation exposes that label
   differently.
2. `src/test/slice16g_i6_integration_preflight.test.tsx > 16G-I6 A — keyboard /
   accessible interaction preflight > Rapid Fire: Tab reaches judgment
   controls; shortcut and Enter commit` — test helper exhausts its search for
   the “Rapid Fire Supporting button”. Source review indicates its text-based
   predicate may not match the control's accessible label; confirm keyboard
   focus behavior before changing the assertion.
3. `src/test/slice16g_i6_integration_preflight.test.tsx > 16G-I6 G — scientific
   semantic preservation > keeps RF/ES absolute 0/1/2, QC accept/edit/reject,
   Chunk Duel auxiliary only` — test expects text matching `/0 Irrelevant/`,
   while the current Rapid Fire control presents the label differently.

These are recorded as test-contract mismatches to investigate, not silently
deleted or weakened. Owners: 17C for the two label expectations and keyboard
selector after focused verification.

**Lint findings (category E pending bounded review):** `npm run lint` reports
four `react-hooks/set-state-in-effect` errors in
`QuestionCheckPreviewSession.tsx:62`, `RapidFirePreviewSession.tsx:59`,
`GoldBaselineBootstrapForm.tsx:93`, and `GoldCampaignCreateForm.tsx:38`, plus
two `react-hooks/exhaustive-deps` warnings in the preview session files. These
are baseline lint debt; no behavior defect was established by lint alone.
Owner: 17C to decide whether small safe corrections are needed for a green
required lint lane, or to retain a precise, documented disposition without
weakening lint configuration.

The npm advisory report is informational baseline output. No dependency
upgrades or audit-driven changes are authorized by this inventory.

## Required mocked REL-03 coverage and workflow inventory

`tests/unit/test_rel03_external_inference_demo_profile.py` exists and uses
`httpx.MockTransport` for completion/model requests plus fake clients for
settings and authoring probes. It contains sentinel credential-redaction
assertions and default-profile / exact-profile checks. The test source inspected
does not configure a real OpenRouter client or send network requests. It must
remain in the required deterministic backend lane, with CI receiving no `.env`
or real credential and with outbound `openrouter.ai` access blocked or guarded.

No tracked files exist under `.github/workflows` at this baseline. No hosted CI
run exists or is claimed.

## Failure dispositions (A–E)

| Category | Baseline disposition |
| --- | --- |
| **A — Product regression** | None demonstrated by these baseline checks. This is not a general product acceptance claim. |
| **B — Test defect** | Five TypeScript fixture errors and the three named Rapid Fire UI failures above. Confirm each against the accepted UI contract before correcting or selecting tests. |
| **C — CI/environment defect** | Full backend pytest timed out at 900 seconds with no exact blocked test identified. Investigate using the bounded 17E procedure; do not claim `TEST-STARTUP-01` is the cause without evidence. Initial UV-cache permission and npm registry-resolution failures were environment setup issues and were resolved using temporary caches / permitted registry access. |
| **D — Non-generic qualification** | The two named Docling parse/ingestion tests require local parser artifacts and real parsing; keep outside generic PR CI while preserving separate execution. Fixture checksum remains generic. |
| **E — Historical/non-authoritative debt** | 165 Ruff findings and four UI lint errors / two warnings are baseline static-analysis debt pending bounded disposition. Do not weaken lint rules to manufacture a pass. |

## Scope and preservation

- Baseline work changed no application code, tests, package manifests, lockfiles,
  or workflow files.
- The only pre-inventory commit on this branch is the documentation-only Slice
  17 opening commit `415616b5c330352d02b85371edb68d89a87408fb`.
- Command logs remain in `/tmp/slice17-baseline-*` and are not repository
  artifacts.
- `TEST-STARTUP-01` remains **OPEN**, assigned to 17E. The full-suite timeout
  is recorded separately because its exact blocking test was not established.
- No production changes, test corrections, CI workflow, hosted CI execution,
  model execution, or promotion occurred during 17A.

## Next bounded step

With this evidence recorded, 17B and 17C may select the deterministic backend
and frontend lanes and make only bounded corrections justified by these
failures. Preserve this baseline unchanged; later evidence belongs in a
separate implementation-result record.
