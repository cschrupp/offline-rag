# Integrated CPU Stage 2 execution protocol

**Review checkpoint only.** The 36-submission workload and destructive
test cases below require separate execution authority. Submit nothing
against a live deployment.

## Frozen inputs

Use [workloads.json](workloads.json) and [Stage 1 bindings](stage1-bindings.json).
Verify the input manifest hashes and mount the identical provider fixture
read-only for both arms. Resolve the Recipes logical source by the
manifest's exact document and frozen inventory, and independently confirm
its identity against the original incident source scope. Require precisely
one match. Rich omits source IDs and must resolve to its sole expected
document. Use empty history for both. A Rich no-history retrieval question
differs from the earlier browser turn's resolver output.

Use original snapshot and index manifests and check their digests,
publication pointers, workspace revisions, exact source inventories and
real backing completeness. Verify both checkpoint and local reference
embedding file digests on the isolated host before inference. Stop on
any mismatch. The Stage 1 science settings digest predates the batching
field, so exclude that execution-only field when comparing against it;
compare all other effective settings exactly between arms.

The fixture uses the existing generator factory seam and deterministically
cites the first supplied evidence handle. It requires structured evidence
and generates a fixed synthetic sentence. It performs no network calls
and tests the citation and response contracts, not factual correctness.
Keep settings and fixture unchanged across arms. Run each arm in a single
process with the existing ONNX 8/1 profile, FP32 CPU Torch 2/2, four
effective CPUs, operation capacity one, 180 s query deadline and 30 s
application drain grace. Set Torch threads once before runtime startup
using an identical diagnostic launcher for both arms. Never switch
scorers at runtime.

## Admission schedule and exact counts

Run A then B as separate sessions, with one active app at a time. Each
uses a fresh copy of the same frozen data. Record session order as a
temporal limitation. Run Recipes then Rich in both arms. For each workload submit one request, a synchronized wave of two,
then a synchronized wave of four. Wait for backend terminal evidence or
verified rejection for every submission before the next wave. A wave
is a common client release barrier, not a guarantee of one acceptance.
No extra HTTP warm-up. Keep the first serial result and record its
model-initialization state. Per arm: 2 × (1 + 2 + 4) = 14 load submissions.

After the load waves per arm, use the Recipes binding for four additional
turn submissions, each with one deterministic, bounded fixture:

1. Disconnect with the worker held before the pre-rerank checkpoint.
   Observe the disconnect signal, release the barrier and require no
   scorer or provider execution.
2. Disconnect with the actual scorer forward held. Require no terminal
   trace or slot release until the held worker returns. Test the slot
   with an internal registry probe during the hold, not another HTTP
   submission.
3. Advance wall time past the unchanged 180 s cooperative deadline
   while the forward seam is held, then release before client watchdog
   expiry. Require a 504 at the next checkpoint and no provider call.
4. Hold a scorer during shutdown and pass transport grace. Observe
   cancellation, worker return and registry release before runtime
   resource closure. Only stop the isolated application.

Use the same bounded barrier placements and hold timings for both arms.
These hooks observe the real route, scorer and operation registry at test
seams. They must not replace scientific scoring or supply a different
operation lifecycle. Validate the lifecycle driver locally before requesting
authorization. Its guard and observation implementation is a remaining
pre-execution dependency. Do not add HTTP contenders, retries,
warm-ups or recovery submissions to the budget. Totals are 28 load,
eight lifecycle, 36 maximum and zero retries.

Count every client send once. Separately capture preflight admissions
and rejections, query admissions and rejections, backend terminal
outcomes, app cancellation, and transport delivery. Classify a 503 by
its guard or execution reason. Count query acceptance from the registry,
not from HTTP 200. Count scientific completion from terminal trace and
worker events, not client disconnect or client timeout. A successful
scientific trace may exist without delivered HTTP. Join client-side
monotonic spans and server-side operation/trace identities with a
diagnostic per-request ordinal. Preserve abandoned work, waves with
zero accepts, failures, errors and all timing outliers. Missing events
make the affected cell inconclusive.

For every accepted load request measure CPU-seconds, wall times for
assembler/scorer/forward, input count and batch shapes, prepass, process
RSS, container memory and queue/admission latency where meaningful.
Quantify actual concurrency; report aggregate host CPU separately.
Capture active inputs and score scatter in original order, FP32
tolerance `abs(delta) <= 1e-4 + 1e-5 * abs(baseline)`, exact full
ranking and tie-break, ordered anchors/evidence and packed bytes. Validate
the published snapshot/source scope and synthetic citation membership.
Record opaque IDs/hashes and numerical values without passage contents.
Assess Recipes and Rich separately. Stage 1's Rich outlier remains
historical evidence. Stage 2 cannot establish production p95.

## Preflight, abort and restore

Before maintenance reserve at least 4,800 s to automatic VM STOP,
including 900 s for restoration. Preserve the 2,400 s diagnostic
execution ceiling and abort if the reviewed time estimate cannot fit
within it. Require 6 GiB diagnostic RSS ceiling, at least 2 GiB host
available RAM throughout, sufficient disk for copy and rollback images,
no competing process or active production request, and an always-armed
host watchdog. Verify the limit applies during native calls. Use a
bounded client watchdog, proposed at 195 s for transport observation
including the 180 s cooperative deadline, and finite barrier holds.
Freeze these exact time limits and watchdog policy with the lifecycle
driver before reserving the VM window.

Stop production gracefully only after all gates pass. Stage a consistent
isolated data copy per arm, with exclusive Qdrant ownership of that copy.
Keep original models read-only, restrict scratch permissions, disable
external networking and run clients inside the isolated namespace.
Never open live Qdrant from another process. Verify original image,
restart policy, mount identities, live and ready health, and both
workspace/publication signatures before stopping anything.

On an invariant failure or resource/deadline breach, stop new
submissions, keep every attempted outcome, remove the isolated process
and restore the original container under the reserved independent
watchdog. Never count an aborted cell as a pass. Verify both HTTP 200
health endpoints, original image/mount/restart policy, revisions,
snapshots, source inventories and pointers. Check no diagnostic process
holds Qdrant storage before removing scratch data. If restoration fails,
retain sanitized diagnostic evidence and report the failed restoration
check. No production migration or strategy toggle is required.
