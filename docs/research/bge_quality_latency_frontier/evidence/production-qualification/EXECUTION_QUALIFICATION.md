# BGE-30 consecutive versus sorted-eight

**Proposed only.** Use the deployed FP32 BGE checkpoint and canonical
assembler with input_k 30, output_k 10, the existing anchor and source
contracts, frozen Qwen3, and Torch 2/2. Compare consecutive baseline with
stable length sorting, eight-pair batches, and restoration of score order.
Take work through the same scoped RRF, scorer and assembler. Keep every
available input pair, including when the pool has fewer than 30.

## Population and custody

Build an approved, source-rights-cleared roster before observing arm
results. Select 48 unique queries in four cells of 12. Use naturally
different pools, including ≤10, 11–29, and ≥30 eligible candidates,
and cover technical manuals, procedural guides, long narrative or
reference documents, and tables or mixed-layout PDFs. Include English,
Spanish, and cross-language query/document cases. Group variants by
document family. Exclude the incident questions and their paraphrases
from held-out estimation. Use them as named development controls.

Define length after canonical passage-only truncation, before padding.
For sampling, short means median pair length ≤256 tokens and long means
median ≥384. Homogeneous means P90 minus P10 ≤64 tokens and heterogeneous
means ≥160. Freeze exact query identities and tier assignments from
baseline metadata, with ambiguous middle-band cases recorded and sampled
as sensitivity if independently authorized. These cutoffs organize the
evaluation. They are not a runtime policy or claims about the prevalence
of the cells. Record gaps instead of replacing unavailable cases with
synthetic stand-ins. Use 12 additional development queries, disjoint by
document family, to design any conditional rule.

## Quality and performance

Require identical original candidate IDs in order, pair association, and
identical active model input IDs, masks and positions after unpadding. Only
right-padding extent and batch ordering may change. Use finite FP32 raw
logits and `abs(candidate-baseline) <= 1e-4 + 1e-5*abs(baseline)` for each
candidate. Exact ranks and canonical tie-break, anchors, ordered evidence
units, and packed context must match per query and trial. Log near ties,
rank flips and aborted calls. Any scientific parity failure blocks the
affected candidate scope, regardless of timing. Record actual padded widths in both arms, require unchanged
per-candidate truncation outputs, and independently verify score scatter. Keep measurements and gate results even when parity fails.

Use a pinned image/host, fixed CPU affinity/quota, software, RAM/swap,
model artifacts and session settings. Use one warm-up per arm per query,
then three paired measured blocks A/B, B/A, A/B, reversing the first-arm
sequence for alternating queries under a frozen seed. Freeze host
selection, warm-up order, block order and timeout/error accounting before
measurement. Capture assembler and scorer wall time and CPU-seconds,
tokenization/sorting/scatter cost, actual shapes and padded slots,
sampled memory and end/peak RSS. Report paired per-query medians, ranges
and query-family bootstrap intervals by cell. Retain invalid, timed-out
or incomplete comparisons with reasons. An incomplete required cell
cannot clear the gate. Do not infer HTTP p95 from these calls.

Proposed performance screen for a stated scope: at least 20% median
paired assembler and forward wall reduction, no more than 5% median
paired assembler CPU increase, and a majority of paired queries
improving in every included cell. Compare tails and peak RSS with an
agreed Docker budget. Scope with fewer than the planned observations
stays unresolved. Do not imply a 20% gain on every request.

## Conditional execution

On development cases calculate the **net** shape benefit, including the
cost to obtain true truncated lengths, reorder and scatter scores. Observe
both padded-slot reduction and the sum of batch size × padded width²;
neither substitutes for measured speed. Candidate features include
pool size, sequence length spread, padding reduction and number of
additional forward calls. Use a simple reversible predicate from those
features, with the existing scorer as the default for unknown or
unsupported shape regions. Chart universal, conditional and baseline
results separately. Freeze any predicate and all thresholds before
held-out access, and use a later explicitly authorized validation run
for the frozen conditional policy. If benefit concentrates in long,
heterogeneous pools, do not generalize to small or homogeneous pools.
Report short-case prepass overhead even if the policy would fall back.

## Load and lifecycle qualification

Use a separate nonproduction Docker instance on the reference CPU host.
Measure serial requests and bounded concurrency at 1, 2 and 4 offered
clients, preserving the approved admission setting across arms. Separate
queue time, accepted/rejected counts, service wall, CPU cost, memory,
readiness and completion. A bound of one accepted query must be visible
as bounded rejection or queue policy in the agreed contract. Do not
silently grant more capacity to the treatment. Use synthetic fixture
callbacks or an authorized local generator stub only if exercising HTTP.
No external-provider dependency in this comparison.

Test success, deliberate overload, client disconnect before and during
rerank, deadline at the next checkpoint, and shutdown drain. Require
no early capacity release, duplicate completion, stale snapshot binding
or generation after a recognized cancellation checkpoint. Record that
native forward execution cannot be interrupted cooperatively until it
returns. The deployed synchronous workspace route bypasses the managed
worker used by /v1/query. Verify actual route behavior with fixtures,
and treat managed-worker adoption as a separate design if the rollout
depends on it. No worse error, deadline or cancellation behavior is
acceptable. Freeze load volume, latency/error regression limits and
memory budget as part of approving the load stage.
