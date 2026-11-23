# Historical Research Excerpt — Rich Small-Pool Batching

This recovered chapter was not embedded in any fetched research report. It preserves the exploratory result without changing the canonical research report or authorizing production use. The original scratch copy was `/tmp/seneca-rich-batching-chapter.md`; its protocol, figure, and raw-evidence links point to the research branch that retains those artifacts.


## 12. Rich workspace — changing batch size on the same ten pairs

This experiment isolates consecutive batch grouping as the only treatment.
The prior Rich diagnostic showed a costly warm forward pass despite low
padding. The experiment kept the original snapshot, no-history question,
fused candidate order, tokenizer, BGE FP32 checkpoint and Torch 2/2 policy.
The Qwen3 CPU embedding profile remained fixed. The four groupings were
A: 10, B: 5+5, C: 4+4+2, and D: 2+2+2+2+2. This study did not sort the
pairs by length or reduce the reranker depth.

The accepted protocol specified four warm-ups and the measured schedules
A/B/D/C, B/C/A/D, C/D/B/A and D/A/C/B. Every measured treatment is compared
to the A call in its block. The unchanged gate requires median paired
forward and assembler wall reductions of at least 20%, at least three
positive pairs on both wall endpoints, no more than 5% median paired
assembler CPU increase, and exact scientific output within the prespecified
raw-logit tolerance. See the [accepted protocol](https://github.com/cschrupp/offline-rag/blob/experiment/rich-small-pool-cpu-batching/docs/research/bge_quality_latency_frontier/evidence/small-pool-design/PROTOCOL.md).

The first attempt's retained stream ended at 17 of 20 observations and
contained no restoration confirmation. The original deployment passed
preflight after the operator restarted the VM. The fresh complete schedule
writes evidence locally on the VM and is analyzed separately. Partial
timing observations from the earlier attempt are retained and excluded
from the complete paired comparison.

**Result: all three treatments passed scientific parity. None met the
performance advancement gate.** Batch size two yielded the largest observed
median gains: 7.6% forward wall, 7.8% assembler wall, and 7.8% assembler
CPU. It improved both wall endpoints in three of four blocks and still
fell short of the required 20% medians.

| Treatment | Median paired forward reduction | Median paired assembler reduction | Median paired assembler CPU reduction | Positive wall pairs (forward / assembler) | Parity | Advances |
|---|---:|---:|---:|---:|---|---|
| B · 5+5 | −1.2% | −1.5% | −1.2% | 1/4 · 1/4 | Pass | No |
| C · 4+4+2 | −0.7% | −0.8% | −0.6% | 1/4 · 1/4 | Pass | No |
| D · five pairs of two | +7.6% | +7.8% | +7.8% | 3/4 · 3/4 | Pass | No |

![Paired warm wall and CPU reductions by grouping](https://github.com/cschrupp/offline-rag/blob/experiment/rich-small-pool-cpu-batching/docs/research/bge_quality_latency_frontier/figures/09-rich-small-pool-paired.png)

*Figure 9. Each dot compares one measured treatment call against A in
the same block. Dark marks show paired medians. Positive values favor the
treatment. Dashed lines show the preregistered wall and CPU gates.*

| Measured block | A assembler (s) | B assembler (s) | C assembler (s) | D assembler (s) |
|---|---:|---:|---:|---:|
| 1 · A/B/D/C | 25.926 | 26.353 | 26.333 | 24.317 |
| 2 · B/C/A/D | 31.375 | 26.321 | 26.528 | 34.423 |
| 3 · C/D/B/A | 26.853 | 27.294 | 27.113 | 24.303 |
| 4 · D/A/C/B | 26.811 | 27.180 | 26.985 | 24.268 |

Block 2 matters. The A and D calls were slower than their counterparts
in other blocks, and D regressed 9.7% against A on assembly. The run does
not establish the cause of that variation. All four blocks are retained.
The earlier 31.108-second warm diagnostic remains a separate observation,
while the table uses only this run's matched references.

D reduced padding from 624 to 178 positions, a 71% reduction in padding
and an 8.8% reduction in total positions. It also changed one forward
call into five. That arithmetic is compatible with a modest measured
benefit here and does not predict the observed timing by itself.
B and C removed only 5 and 24 padded positions respectively. The
accepted large Recipes sorted-eight gain is a separate result from
another length distribution and a different grouping strategy.

All 15 arm-to-A checks passed, including the warm-up comparisons.
The maximum absolute raw-logit difference was 2.86e-6. Ordered
candidate identities, active model inputs, full ranks, anchors, all
three evidence units and the 3,729-token context matched. The raw log
retains batch widths, every per-batch timing, scorer and assembler
CPU, resource observations and bounded identity hashes for all 20 calls.
End RSS for measured calls was about 3.83 GiB in A and B, 3.88 GiB in C
and 3.89 GiB in D. Process high-water RSS reached 4.18 GiB across the
shared process. Sampled host available memory dipped to about 5.22 GiB
and recovered. The shared process and sampled measurements do not
identify arm-specific memory peaks or explain transient system behavior.

**Engineering decision.** Keep the existing consecutive grouping for this
workload. Smaller batches preserved scientific output but did not reach
the predeclared threshold. Keep the result scoped to one long-passage,
ten-pair query on four vCPUs. It does not determine p95, concurrent
capacity or a policy for other workloads. The BGE-15 experiment remains
separate and was not run here.

[All 20 trials and paired gates](https://github.com/cschrupp/offline-rag/blob/experiment/rich-small-pool-cpu-batching/docs/research/bge_quality_latency_frontier/evidence/rich-small-pool-execution/SUMMARY.json) ·
[Raw measurements](https://github.com/cschrupp/offline-rag/blob/experiment/rich-small-pool-cpu-batching/docs/research/bge_quality_latency_frontier/evidence/rich-small-pool-execution/MEASUREMENTS.log) ·
[Execution and restoration evidence](https://github.com/cschrupp/offline-rag/blob/experiment/rich-small-pool-cpu-batching/docs/research/bge_quality_latency_frontier/evidence/rich-small-pool-execution/EXECUTION.md)
