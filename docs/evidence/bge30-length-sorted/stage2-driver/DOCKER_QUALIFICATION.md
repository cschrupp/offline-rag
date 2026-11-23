# Stage 2 driver qualification checkpoint

**Local engineering qualification: PASS.**
**Native VM execution readiness: BLOCKED — host is stopped and cannot be inspected.**
**VM campaign, production change, PR merge, and activation remain unauthorized.**

Accepted integrated application source:

`1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e`

Pinned diagnostic image:

`sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04`

Driver implementation candidate: `90cd4159bab802b8d0797951f5a693f538eec666`
on `prep/stage2-docker-transport`, directly based on `67fe29f4`.

The complete consolidated authorization is retained in
[FULL_AUTHORIZATION.md](FULL_AUTHORIZATION.md). The final execution response
and exact limitations are retained in
[STAGE2_FINAL_RESPONSE.md](STAGE2_FINAL_RESPONSE.md).

## Completed local work

- Implemented the Docker/socket adapter over the accepted workspace
  conversation route, with per-send ordinal, operation, scientific trace,
  terminal, worker-return and actual slot-release correlation.
- Added route instrumentation only to the disposable diagnostic server. It
  wraps the accepted lifecycle methods and preserves their decisions.
- Added four lifecycle cases for both strategies: pre-rerank disconnect,
  held-forward disconnect, cooperative deadline after held forward, and
  shutdown drain past transport grace.
- Added an independent process supervisor that targets the exact labeled
  container, escalates to forced termination, verifies storage release, and
  restores a disposable baseline service.
- Added a locked 36-send schedule and fail-closed event validation. A send is
  counted before transport; no retry path exists.
- Kept ordinary local load requests at the accepted 180-second configured
  deadline. The explicitly designated deadline lifecycle case uses a
  diagnostic-only two-second per-operation override; it does not establish
  native 180-second timeout behavior.
- Used deterministic synthetic embedding, reranker, and generator fixtures in
  the local rehearsal. No provider/model call or external network was used.

## Final local rehearsal

The final full synthetic rehearsal is `LOCAL_SYNTHETIC_REHEARSAL_PASS`, session
`51c14191c20a4084`:

- 36 unique HTTP socket sends; 36 settlements; zero retries.
- 28 load and eight lifecycle requests.
- Consecutive: 18 submissions. Length-sorted-eight: 18 submissions.
- Both arms ran synchronized 1/2/4-client waves for Recipes and Rich.
- Load outcomes: 13 completed/HTTP 200, six preflight-capacity rejections
  (`query_preflight_capacity_exhausted`), and nine query-capacity rejections
  (`query_capacity_exhausted`). Rejection types remained distinct.
- Lifecycle outcomes, per strategy: one pre-rerank disconnect and one held
  forward disconnect (both workers returned before release); one cooperative
  deadline (`504`, `query_deadline_exceeded`); and one shutdown cancellation
  after transport grace, with owned resources retained until worker return.
- App response counts: 13 HTTP 200, 15 HTTP 503, four client-disconnect
  observations with server HTTP 204, two HTTP 504, and two shutdown HTTP 500.
  These are synthetic lifecycle observations, not product availability
  results.
- Both sessions reported four effective CPUs, PyTorch intra/inter threads
  `2/2`, the accepted 180-second configured query deadline, and zero external
  provider calls. Docker network mode was `none`.
- Independent restoration reported `restored`, exit code zero, no restoration
  error, and zero remaining session containers. The disposable baseline's
  health endpoint returned 200 before that exact test container was removed.
- The raw request/server event journal and all 36 terminal records are retained
  under [local-rehearsal/51c14191c20a4084](local-rehearsal/51c14191c20a4084).
  SHA-256 values for each retained file are in its `archive_manifest.json`.

Full counts and row-level outcomes are in the archived
`LOCAL_REHEARSAL_RESULT.json`. This rehearsal proves request lifecycle and
ownership accounting only. Synthetic inference does not test BGE numeric
parity, relevance, packed-context parity, native model latency, production
concurrency, or the effectiveness of length-sorted batching.

## Failure injections and development evidence

Adapter tests fail closed on missing terminal evidence, duplicate request
correlation, mismatched operation identity, premature slot release, and wrong
route. Docker integration tests cover diagnostic deadline, driver termination,
SIGTERM-ignoring container termination, disposable service restoration, and an
injected restoration-verification failure. The latter must return
`restoration_failed`, never PASS.

The preserved failed development run
[4f2ba51eefee4bde](local-rehearsal/development-failures/4f2ba51eefee4bde)
stopped after 19 attempts / 18 settlements. A global two-second accelerated
deadline caused a cold-arm preparation timeout before query-slot admission.
The watchdog removed the diagnostic container and restored the baseline.
The corrective moved acceleration to only the explicit deadline lifecycle
operation and restored ordinary load to the accepted 180-second setting. The
successful final rehearsal then passed. Earlier development iterations and
their resolutions are listed in
[DEVELOPMENT_FAILURES.md](DEVELOPMENT_FAILURES.md).

## Tests and artifact verification

The focused driver, adapter, and Docker-watchdog suites passed **19 tests**;
one optional host forward-hook test skipped because host Python lacked Torch.
The same forward-observer fixture was run inside the exact pinned image and
passed, proving outputs remain equal and hooks are removed after observation.

Ruff passed for the driver tree. Ruff format check passed with `py313` parsing
for the compatibility-preserving exception tuple syntax. Python compilation
passed. `verify_archive.py` validated the offline OCI archive, index, AMD64
manifest, image config, and pinned archive SHA. `verify_image.sh` confirmed the
image identity, 402 integrated source-file digests, dependency/runtime facts,
CPU-only Torch, default/opt-in strategy behavior, and unchanged reranker
fingerprint. `git diff --check` and shell syntax checks are required again on
the final commit.

## Host preflight: not run

Google Cloud read-only instance metadata reported `seneca-review` as
`TERMINATED` (machine type `e2-standard-4`). SSH and host inspection were not
attempted; the VM was not started, and no keys, permissions, service or
deployment state were changed. As the VM was stopped, the following remain
unverified against the actual host:

- Active image, container, restart policy, mounts, and HTTP health.
- Recipes/Rich workspace revisions, snapshot publications, source inventories,
  and backing stores.
- Actual model/tokenizer file hashes and effective scientific settings.
- Host CPU affinity/quota, RAM, disk, swap, non-Docker storage ownership, and
  current automatic-STOP deadline.
- Absence of concurrent native experiments or other Qdrant owners.

The read-only metadata preflight does not need a future maintenance window; the
isolated mode continues to require a verified STOP epoch with the full 4,800
second reserve. Neither mode has been run on this stopped VM. Host preflight
must be completed after the VM is independently available, before any later
maintenance authorization is considered.

## Current gate

Local driver implementation and full synthetic rehearsal are ready for
independent technical review. Native Stage 2 is **not ready to execute** until
host identity, settings, frozen publications/backing, resources, and safe
maintenance window are verified. No application changes, model changes,
deployment, default change, PR merge, or `main` promotion occurred.
