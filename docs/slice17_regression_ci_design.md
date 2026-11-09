# Slice 17 — Regression CI and Repository Baseline

**Status:** DESIGN AND IMPLEMENTATION AUTHORIZED / ACTIVE
**Canonical starting point:** `5a793766bb4ecd88278cd0bf3a892572ec30f67a`
**Branch:** `feature/slice17-regression-ci`

## Objective

Establish a deterministic, reproducible CI baseline for Seneca from a clean
checkout. CI must protect accepted product contracts without requiring a GPU,
model weights, Ollama, OpenRouter credentials, a private corpus, or empirical
performance measurements.

The first step is a measured repository baseline. Workflow commands and test
selection must follow observed results; no workflow or test correction may
precede the baseline inventory. Historical performance observations are not CI
thresholds.

## Governing inputs

- [`16K-G regression handoff`](evidence/16k_g_regression_handoff/16K_G_REGRESSION_HANDOFF.md)
- [`16K-G closeout`](evidence/16k_g_regression_handoff/16K_G_CLOSEOUT.md)
- [`REL-03-P0 design`](rel03_external_inference_demo_profile.md)
- [`REL-03-P0 live qualification`](evidence/rel03_p0_live_smoke/REL03_P0_LIVE_SMOKE.md)
- [`CI-BASELINE-01 and TEST-STARTUP-01`](BACKLOG.md)
- `DEVELOPMENT_GUIDE.md`, `pyproject.toml`, `uv.lock`, `ui/package.json`, and
  `ui/package-lock.json`

The accepted 16K-G handoff is the minimum deterministic regression contract
map. Slice 17 selects and executes those contracts; the handoff itself is not
evidence that every candidate test already passes.

## Bounded tranches

These are sequential parts of one slice, not separate projects:

1. **17A — Baseline Inventory:** reproduce locked installs and run backend and
   frontend baseline commands independently. Record exact results before any
   test or workflow change.
2. **17B — Required Deterministic Backend CI:** select deterministic tests
   from the measured baseline, retain static checks, and include the REL-03
   mocked profile-isolation suite.
3. **17C — Required Frontend CI:** include the measured lint, typecheck, test,
   and build commands using the committed npm lockfile.
4. **17D — REL-03 Profile-Isolation Regression:** make
   `tests/unit/test_rel03_external_inference_demo_profile.py` required and
   prove the test lane cannot contact OpenRouter or receive a real secret.
5. **17E — Startup-Hang Disposition and CI Closeout:** diagnose
   `TEST-STARTUP-01` within bounded test-infrastructure scope, establish its
   explicit disposition, and report final local and hosted CI results.

## 17A — Baseline before changes

Use a clean checkout and the committed dependency locks. Do not update
dependencies to make an install or test pass.

Backend target is Python 3.14. Record Python, `uv`, and OS versions, then run
and report each independently:

```bash
uv sync --frozen
uv run ruff check src tests
uv run pytest
```

The full pytest inventory must have a bounded wall time. A timeout or hang is a
failure disposition, not a pass. Record pass, fail, skip, xfail, collection or
import errors, duration, timeout status, and failing test IDs.

From `ui/`, run each independently and record its exact result:

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Use Node 22 or newer per the package metadata. A failed command must not prevent
the remaining baseline commands from being inventoried. Do not initially edit
tests to obtain green output.

Every observed failure receives exactly one disposition:

- **A — Product regression:** accepted behavior is broken.
- **B — Test defect:** test setup or expectation conflicts with the accepted
  contract.
- **C — CI/environment defect:** test depends on nondeterministic local state,
  unsupported lifecycle behavior, accidental network access, or an
  environment-specific assumption.
- **D — Non-generic qualification:** hardware, private corpus, live model, or
  empirical performance evidence that is intentionally outside PR CI.
- **E — Historical/non-authoritative debt:** test or script no longer
  represents accepted product behavior. Preserve and disposition it; do not
  silently delete it.

No broad `pytest --ignore`, blanket skips, or unlisted exclusions are allowed.
Each exclusion must identify the exact test/file, reason, category, and owner
for unresolved follow-up.

## 17B — Required deterministic backend lane

Only after 17A identifies the safe baseline, the backend lane will run the
frozen install, Ruff, and selected deterministic pytest set. Prefer fake
embedders, rerankers, generators, temporary data roots, synthetic fixtures,
and controlled clocks. Do not require model provisioning or external services.

Required contract families include:

- managed-operation lifecycle, capacity and mutation-lease release, and durable
  terminal state;
- `FAILED` versus `INTERRUPTED`, valid prior/committed publication recovery,
  and no partial publication;
- worklist schemas, legacy/null projection, durable admission, idempotency, and
  truthful unavailable metrics;
- progress bounds, monotonicity, operation identity, and API projection;
- capacity decision functions with injected memory, disk, and source-limit
  inputs rather than the CI host as oracle;
- parser and ingestion correctness, safe failure mapping, usable short/text
  PDFs, atomicity, and cache identity, without requiring OCR provisioning;
- deterministic failure-recovery contracts, including mocked CUDA OOM where
  applicable.

Do not require real process killing in PR unit tests or assert physical elapsed
times, progress frequency, host memory, or GPU state.

## 17C — Required frontend lane

Run `npm ci`, lint, typecheck, tests, and build as separate visible steps. Pure
UI tests must not require a backend server. Do not weaken ESLint or TypeScript
settings merely to make the baseline green; correct only demonstrated bounded
defects.

Keep accepted UI coverage for workspace lifecycle, ingestion worklists,
operation progress, conversation actions and provenance, Training Mode
boundaries, Quick Play, Question Check, Rapid Fire, contribution rail, and
answer-actions menu. REL-03 has no UI feature; do not add an OpenRouter UI test.

## 17D — REL-03 profile isolation

Require `tests/unit/test_rel03_external_inference_demo_profile.py` in the
generic mocked lane. Assert the default remains `standalone_ollama` with
`strict_offline=true`; the portfolio profile owns the exact OpenRouter endpoint
and model with operator locks; secret projections are redacted; and grounded
generation, conversation actions, and Gold authoring use the external adapter
under mocks.

The generic lane must fail closed against accidental live HTTP to
`openrouter.ai`. It receives no `.env`, external API key, or other real
credential. Recovery rewriting and the semantic judge remain independently
configured and are not redirected or activated.

## 17E — TEST-STARTUP-01

Diagnose the smallest known `TestClient` startup stall with a bounded timeout,
`faulthandler`, thread/task dump, clean temporary data root, and no model or
network dependency. Establish whether the cause is application startup,
runtime recovery, resource construction, TestClient/AnyIO lifecycle, fixture
ownership, stale state, or another evidenced component.

Accept exactly one disposition:

- **RESOLVED:** root cause established and corrected; affected deterministic
  test becomes required.
- **ISOLATED:** cause remains partly unknown, but a bounded deterministic
  equivalent covers the accepted contract; preserve the original invocation
  outside the required lane and document the limitation.
- **OPEN NONBLOCKING:** no deterministic replacement established; keep the
  affected invocation visibly out of blocking CI and retain the debt.

This work does not authorize runtime redesign, worker/process topology changes,
or recovery-semantics changes. A substantial product architecture finding
returns as a separate review item.

## Workflow contract

After the baseline and test set are established, implement one canonical
`.github/workflows/ci.yml` with backend and frontend jobs. Use pull-request and
push-to-main triggers, Linux, Python 3.14, Node 22+, frozen/locked installs,
finite job timeouts, and concurrency that may cancel superseded PR runs but
does not hide canonical main failures. Do not add Docker, model provisioning,
scheduled benchmarks, CUDA, live OpenRouter, or multiple overlapping workflow
systems.

The workflow commands must materially match local qualification. If hosted CI
cannot execute because of repository/account configuration, report
`CI_EXECUTION_UNAVAILABLE`; do not claim a hosted pass.

## Explicitly outside generic CI

Keep CUDA load/VRAM/OOM/throughput, real embedding performance, the 38-source
16K-F campaign, large-PDF RSS, host memory/disk capacity, real Ollama or
OpenRouter calls, and all performance benchmarks outside required PR checks.
Preserve their existing evidence. Do not create performance SLOs from
historical Slice 14 or 16K-F observations.

Slice 17 does not authorize Slice 18, Cloud Run, REL-01, product features,
BETA-CONV-02, new Gold science, distributed Qdrant, or arbitrary test rewrites.

## Evidence and completion

Record 17A in `docs/evidence/slice17/BASELINE_INVENTORY.md` before CI/test
corrections. Record final commands, counts, exclusions, startup-hang
disposition, local qualification, and hosted run identity (if available) in
`docs/evidence/slice17/IMPLEMENTATION_RESULT.md`.

Preferred history preserves baseline-before-fix chronology: documentation and
design; baseline inventory; workflow and bounded corrections; final evidence.
Stop after candidate qualification for independent review. Do not promote.

Slice 17 is ready for later Human acceptance only when the required backend and
frontend lanes are deterministic and green, REL-03 isolation is mocked and
required, secrets and live inference are absent, empirical checks remain
outside the generic gate, TEST-STARTUP-01 has an explicit disposition, and the
workflow matches demonstrated local commands.
