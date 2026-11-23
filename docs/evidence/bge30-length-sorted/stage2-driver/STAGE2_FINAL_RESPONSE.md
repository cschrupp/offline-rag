# Codex — Stage 2 Engineering Completion Response

## Disposition

**Local Stage 2 driver qualification: PASS.**
**Native VM execution readiness: BLOCKED pending read-only host qualification.**
**No native workload, production activation, merge, deployment, or promotion occurred.**

Repository branch: `prep/stage2-docker-transport`

Starting revision: `67fe29f4aa52266a0da8d8e26e05f65f0a872ad9`

Driver implementation candidate: `90cd4159bab802b8d0797951f5a693f538eec666`

Accepted integrated application source: `1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e`
Pinned diagnostic image: `sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04`

The exact consolidated Human authorization is retained in
[FULL_AUTHORIZATION.md](FULL_AUTHORIZATION.md). It explicitly keeps PRs #3–#6
unmerged and excludes native Stage 2, production changes, and main promotion.

## Implemented

- Completed the Docker/HTTP adapter, single-send socket client, lifecycle
  barriers, per-request server observer, and independent watchdog supervisor.
- Uses the existing workspace conversation endpoint and real application
  operation registry. Test instrumentation wraps the original methods without
  replacing admission, lifecycle, scoring, or persistence decisions.
- Correlates each actual socket send to one server HTTP receive, admission
  result, operation, worker result, scientific trace if present, HTTP response,
  and slot release. Missing, duplicate, mismatched, or premature evidence
  fails closed.
- The watchdog removes only a matching session-labeled diagnostic container,
  escalates when graceful stop is ignored, checks that scratch storage is no
  longer mounted, then restarts and verifies a separately identified
  disposable baseline service.
- Implemented all four approved lifecycle cases for both batching strategies.
- Corrected the host-preflight wrapper so read-only metadata inspection does
  not require a future maintenance window. `isolated` mode still requires the
  full 4,800-second verified STOP reserve.
- No production source, scientific settings, model assets, dependency lock,
  or live workspace were changed.

## Local execution and results

Final successful local rehearsal: session `51c14191c20a4084`.

- 36 unique submissions, 36 settlements; exactly 28 load plus eight
  lifecycle; no retries.
- 18 per strategy: `consecutive` and `length_sorted_8`.
- Both strategies exercised the synchronized one-, two-, and four-client
  waves for Recipes and Rich.
- Load outcomes: 13 completed, six preflight-overload rejections, and nine
  query-slot-overload rejections, with distinct correct 503 reasons.
- Each strategy completed its four lifecycle cases: two disconnect
  cancellations after actual worker return; one deadline timeout; and one
  shutdown cancellation after transport grace. Slot/resource release followed
  worker return.
- The image had no network, the application reported four effective CPUs and
  PyTorch `2/2`, normal configured query deadline `180` seconds, and zero
  external provider calls. Only each dedicated local deadline case received a
  diagnostic two-second deadline override. This accelerated fixture does not
  qualify native 180-second behavior.
- The independent supervisor reported baseline restoration success, no
  restoration error, and zero diagnostic containers left. No product service
  was stopped or replaced; this was entirely local and disposable.
- Raw `events.jsonl`, `driver-events.jsonl`, and all 36 correlated terminal
  records are retained in
  [local-rehearsal/51c14191c20a4084](local-rehearsal/51c14191c20a4084), with
  per-file SHA-256 values in `archive_manifest.json`.

This was a synthetic route/lifecycle rehearsal, not performance measurement or
scientific parity qualification. The fake inference fixtures do not test
approved BGE outputs, ranking, evidence selection, packed-context identity,
native latency, or production concurrency.

## Negative tests and preserved failed attempt

The focused suite passed 19 tests, with one optional host-side Torch test
skipped because the host Python lacked Torch. The identical deterministic
forward-observer test ran inside the pinned image and passed: native model
output was unchanged and temporary hooks were removed.

Negative coverage includes missing terminal evidence, duplicate HTTP
correlation, mismatched operation ID, premature release, wrong route, driver
termination, watchdog deadline, SIGTERM-ignoring diagnostic container, and
restoration verification failure. A restoration failure returns an explicit
failure state and cannot generate a pass result.

The earlier attempt at
[development-failures/4f2ba51eefee4bde](local-rehearsal/development-failures/4f2ba51eefee4bde)
failed after 19 attempts / 18 settlements: a global two-second accelerated
deadline caused a preparation timeout on a cold arm. The independent watchdog
removed the diagnostic container and restored the baseline. I preserved its
raw journal and restoration record. The corrected per-request deadline
override kept ordinary loads at 180 seconds; the later full 36-send rehearsal
passed. Earlier fixture, correlation, copy-permission, and event-window
iteration defects were resolved before this final successful run; no
incomplete run is classified as a pass.

## Verification commands

Commands run on the final driver code:

```bash
ruff check docs/evidence/bge30-length-sorted/stage2-driver
ruff format --check --target-version py313 docs/evidence/bge30-length-sorted/stage2-driver
python -m py_compile docs/evidence/bge30-length-sorted/stage2-driver/*.py
pytest -q -rs \
  docs/evidence/bge30-length-sorted/stage2-driver/test_driver.py \
  docs/evidence/bge30-length-sorted/stage2-driver/test_docker_adapter.py \
  docs/evidence/bge30-length-sorted/stage2-driver/test_watchdog_supervisor.py
python docs/evidence/bge30-length-sorted/stage2-driver/rehearse_stage2.py
python docs/evidence/bge30-length-sorted/stage2-driver/verify_archive.py \
  /tmp/seneca-stage2-qualified-image.tar
bash docs/evidence/bge30-length-sorted/stage2-driver/verify_image.sh
bash -n docs/evidence/bge30-length-sorted/stage2-driver/preflight_host.sh
git diff --check
```

Results: Ruff PASS; format PASS; compilation PASS; **19 passed, 1 skipped**;
full local rehearsal PASS; image archive identity PASS; pinned image runtime and
all 402 integrated source digests PASS. The test and rehearsal ran against the
actual HTTP application route in the exact image but used synthetic backing
and controlled fake inference.

## Read-only host preparation

The configured Google Cloud project and authenticated `gcloud` API were
available. A read-only Compute Engine metadata query reported the target VM
status as **TERMINATED**, machine type `e2-standard-4`. I did not attempt SSH,
start the VM, register keys, alter permissions, or change deployment state.

Consequently, the actual host image/container/mounts/health, live workspace
bindings and backing completeness, model and tokenizer files, effective
settings, disk/RAM/swap, non-Docker Qdrant ownership, and current automatic STOP
deadline remain unverified. The preflight script now permits metadata mode
without a maintenance-window epoch; however it cannot be executed until the
host is available. Read-only host qualification is still a prerequisite to
proposing native execution authority.

## Changed paths

Only files under `docs/evidence/bge30-length-sorted/stage2-driver/` changed:
driver/adapter/observer fixtures, tests, preflight runner, and evidence. No
application module changed. Driver implementation commit is
`90cd4159bab802b8d0797951f5a693f538eec666`; the evidence-only closeout commit
and pushed branch head are reported in the final completion handoff. No hosted
workflow result is claimed unless one is attached to those exact commits.

## Remaining authority boundary

Native execution is not authorized by local qualification. Before any later
native campaign, independently verify the actual host and frozen publications,
settings, model artifacts, ownership, resource floors, no competing work, and
the complete STOP/restoration window. Preserve the 36-submission maximum,
zero-retry rule, unchanged scientific settings, and explicit no-deployment/no-
merge boundary.
