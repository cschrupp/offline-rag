# BGE-15 four-arm qualification proposal

**Execution pending.** These criteria were written before any new inference
or depth-15 measurements. They are proposed research gates and are not an
accepted production policy.

## Frozen experimental inputs

Start from the exact Recipes scope at revision 4 and baseline snapshot
`snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196`.
Use the original baked-French-fries retrieval question and its original
single-document scope. Use the deployed image, original BGE checkpoint,
tokenizer, raw-logit, passage-only at 1,024 tokens, tie-break and Torch FP32
2/2, plus the frozen Qwen3 CPU ONNX 8/1 profile. Keep dense and lexical
branch depths, RRF, index identities, output_k 10 and context anchor_k 5.
Use existing context expansion and packing. No generator.

| Arm | Reranker input cap | Execution strategy |
|---|---:|---|
| A | 30 | Consecutive 16+14 |
| B | 15 | Consecutive one batch of 15 |
| C | 30 | Stable length sorted 8+8+8+6 |
| D | 15 | Stable length sorted 8+7 |

At depth 15 the input must be the first 15 of the original fused order.
Verify the ordered identifiers before comparing scores or context. Keep both
branch depths at 30 and let the canonical RRF truncate only after fusion.
No arm may filter a BGE-30 output to manufacture an actual BGE-15 result.

## Publication and isolation prerequisite

Use graceful stop, one consistent copy of the original store, network
disabled and one exclusive Qdrant owner. Use the matching settings and
validated immutable snapshot for each depth. Use the candidate publication
procedure described in [publication preparation](PUBLICATION.md), including
a negative mismatched-configuration check, before spending a model call.
Preserve both manifests throughout. No live pointer or workspace edit.
Require the prior 30-minute minimum safety margin **and** sufficient time
for the complete campaign plus bounded restoration. At any failed preflight,
leave the original service up. No shortening the schedule to fit a nearly
expired VM window.

## Measurement and parity

Use a single isolated process with the two matching validated snapshot
bindings. Share the approved model resources and use one arm at a time.
Warm each arm once before collecting four balanced blocks. Suggested
Williams sequence A/B/D/C, B/C/A/D, C/D/B/A, D/A/C/B, which balances
position and first-order carryover. This is 20 calls total. Verify that
the proposed bounded time and memory fit before approval and execution.
Each comparison is paired within a block. Log actual candidate counts,
FP32 score identities, batch shape, padding, per-batch and total forward
wall and CPU, total BGE including any length prepass, complete assembler
wall and process CPU, sampled memory, and end RSS. Shared-process peak
RSS is not arm-specific. Retain all measurements and failures.

At fixed depth, require identical ordered candidates and active encoded
inputs, masks and position IDs, finite FP32 outputs, score association,
and exact rank/tie-break, anchor/evidence and packed-context identity.
Apply `abs(treatment-control) <= 1e-4 + 1e-5*abs(control)` per candidate
for C vs A and D vs B. A parity failure fails the associated batching
arm regardless of elapsed time. For depth changes record overlap,
reordered common candidates and all evidence differences. Exact
cross-depth evidence equality is not a realistic identification gate.
Use the separately judged quality gates below.

Research advancement screen: versus A, at least 20% median paired reduction
in both warm forward and assembler wall time, positive wall reductions
on both endpoints in at least three of four blocks, and at most 5% increase
in median paired process CPU-seconds. Also report B vs A, C vs A, D vs B
and D vs C separately, plus the blockwise difference-in-differences on
log assembler wall time. Interactions are descriptive on one query. No
claim about throughput, p95, or answers. Require quality separately
before proposing any product migration, even if the performance screen passes.

## Proposed production quality decision

Keep the human-reviewed 9H-P replay as development evidence. Before
a separately approved held-out run, freeze a representative paired and
independently adjudicated pool with naturally small and ≥30 pools,
different lengths, multilingual and technical query strata, and enough
cases for the predeclared paired intervals. Use BGE-30 as the comparator
at identical settings and source scope. Require paired lower 95% bounds
for BGE-15 minus BGE-30 above −0.02 on nDCG@10 and −0.05 on Recall@10,
with compatible nDCG@5, Recall@5 and HitRate@5 per-stratum harm review
under predeclared rules. Require no loss of the only judged directly
supporting passage from the top five and no adjudicated material
evidence-sufficiency regression. Require a separately frozen query-level
harm allowance before any holdout is opened. Report all losses even when
cohort means clear margins. Blindly judge the union of candidate passages
and actual packed contexts and, where feasible, exhaustively judge the
eligible corpus subset. Missing judgments or unsupported strata cannot
clear the gate. The two known development regressions must remain visible.
No inference or holdout inspection was performed in this preparation.
