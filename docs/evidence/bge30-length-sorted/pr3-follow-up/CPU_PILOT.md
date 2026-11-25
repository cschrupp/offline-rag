# Bounded CPU opt-in pilot proposal

**For independent review.** Authorize each stage separately before running it.
Keep production on consecutive batching. A successful pilot can support a
later opt-in decision for its qualified scope.

## Frozen inputs and preflight

Pin the reviewed feature image, production comparison base, CPU quota and
affinity (four effective CPUs), Torch FP32 2/2, memory/swap limit, model and
tokenizer digests, existing Qwen3 profile, application configuration and image
digest. The arms must differ only in `OFFLINE_RAG_RERANKER_BATCHING_STRATEGY`.
Use the installed application scorer and canonical assembler, with test-side
observation of the tokenizer and model calls. Never swap the model, chooser,
scorer or ranking implementation. Freeze query hash, history policy,
candidate ceiling 30, source scope, and dense/lexical backing identities.

| Slot | Required workload |
| --- | --- |
| 1 | Recipes incident question, published revision 4, original single-source scope, 30 candidates and heterogeneous lengths |
| 2 | Rich revision 2, ten candidates, mostly homogeneous, same no-history question as the accepted isolated study |
| 3 | Approved short homogeneous case, 11–29 candidates |
| 4 | Approved long homogeneous case, 30 candidates |
| 5 | Approved short heterogeneous case, up to 10 candidates |

Bind Recipes to `snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196`
and Rich to `snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca`.
The Rich case uses the original question directly and differs from the
historical resolver-derived browser workload. Select optional cases from
rights-cleared data using baseline length metadata before seeing sorted-eight
outcomes. Classify short as median post-truncation length ≤256, long as ≥384,
homogeneous as P90−P10 ≤64 and heterogeneous as ≥160. Report unfilled optional
slots and the resulting scope limitation. Stop if either required case or
its validated backing cannot be bound. Freeze an absolute test deadline, per-call
timeout and RSS budget before requesting execution authority.

Confirm no competing work, sufficient free disk and RAM, and sufficient time
before VM automatic STOP for copying, execution and a reserved restoration
window of at least 15 minutes. Require original image, mounts, restart
policy, readiness, workspace revisions and source inventory in the preflight.
Stop the original container gracefully before copying writable data. Use
restricted isolated data copies, exclusive Qdrant ownership, original model
mounts read-only and network disabled. Save a restoration command and activate
cleanup on ordinary errors and interrupts. Restore before the deadline rather
than relying on cleanup at automatic STOP.

## Stage 1 — exact bounded measurement

Run one warm-up per arm and three measured pairs per case, at most **40
assembler calls**, with **16 calls** for the two required cases alone. Use
A/B, B/A, A/B for the first frozen case and reverse for successive cases.
For every arm session, execute in the same isolated process scope with the
same model residency policy. If keeping both strategies in one process,
use two application-created scorers with the same production-created loaded
checkpoint tuple and independent settings, strictly sequential access, and
document that test fixture. Run one application instance at a time. Never
warm up by querying the live workspace service.

Record wall and process CPU time for scorer and assembler, forward wall
time and shape per batch, prepass, actual pair lengths/padded workload,
process peak and sampled RSS, host memory and CPU. Capture actual candidate
IDs/input order and active input IDs, masks and applicable position IDs
by ordinal. Check one finite raw FP32 logit per input with
`abs(delta) <= 1e-4 + 1e-5 * abs(baseline)`. Exact full ranked IDs and
tie-break, anchors, evidence identities/order and packed context bytes must
match. Check the full 30-score ordering from the existing canonical sorter
even where assembly retains only its normal anchors. Report near-tie margins
and failed, timed-out and incomplete observations.

Review each required workload separately. A proposed opt-in scope must pass
parity and the existing exploratory performance screen of ≥20% median paired
assembler and forward wall reduction, ≤5% median paired assembler CPU increase,
and no budget overrun. Report all three pairs. A slow Rich result keeps that
shape unqualified. It cannot be offset by a faster Recipes result. The pilot
does not establish a production latency percentile or an automatic selection rule.

## Stage 2 — separate bounded lifecycle checks

After parity, use isolated Docker with the actual intended route and a local
non-generative fixture at the provider seam. Same admission configuration
and resource cap per arm. For each of the two required workloads per arm,
run one serial request, one two-client wave, and one four-client wave. Cap
at **28 submissions** across arms. Capture queue/admission, response, error,
CPU, memory, snapshot and completion. Include ordinary admission rejection
in the report. Count every submission and retry zero.

Separately run one fixture per arm for disconnect before rerank, disconnect
during rerank, deadline at the next checkpoint and shutdown drain, at most
**eight additional submissions**. Assert no premature capacity reuse,
duplicate terminal records or generation after recognized cancellation.
Record if the synchronous workspace route continues work after disconnect.
The managed query route has different lifecycle semantics. Do not use one
route as proof for the other. No live provider calls. A regression in
failure, timeout or cancellation behavior blocks user-facing activation.

## Restoration and review

Stop diagnostic processes, restart the original container, and verify it
remains running with the original image, mount modes and restart policy.
Require HTTP 200 on live and ready, and recheck revision, snapshot and source
inventory for both workspaces. Remove isolated copies only after verified
restoration and evidence capture. Retain sanitized numeric measurements,
scientific identity hashes, failed gates and restoration results. No VM
execution, opt-in change or deployment was performed for this follow-up.
