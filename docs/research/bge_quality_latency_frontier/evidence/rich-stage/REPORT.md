# Rich workspace retrieval stage attribution

**BGE accounted for 98.4% of warm assembly.** The cold call took 66.576 s
and the warm call took 31.108 s. Most of the cold-to-warm difference came
from the dense stage. BGE forward time stayed near 30.5 s.

| Non-overlapping stage | Cold (s) | Warm (s) |
|---|---:|---:|
| Dense retrieval, including Qwen3 | 34.422 | 0.465 |
| Lexical retrieval | 0.029 | 0.016 |
| RRF fusion | <0.001 | <0.001 |
| Reranker pair construction | <0.001 | <0.001 |
| BGE scorer, including first-use load when applicable | 31.787 | 30.615 |
| Reranker sorting | <0.001 | <0.001 |
| Context expansion and packing | 0.334 | 0.009 |
| Rounding and unclassified time | 0.004 | 0.003 |
| **Assembler total** | **66.576** | **31.108** |

[Stage waterfall](../../figures/08-rich-stage-waterfall.png) · [Machine-readable summary](SUMMARY.json)

The table uses leaf timers from the nested assembly metadata. The scorer's
30.357/30.592 s cold/warm forward times are included in the BGE row. BGE load
or wait was 1.327 s cold and negligible warm. The dense stage contains all
first-use dense costs and does not isolate model initialization.

## Scientific identity and comparison

The browser's query trace matched its conversation trace's resolver
retrieval SHA-256 (`7899eaca…`). The original normalized question hashed
to `68078feb…`. The diagnostic used the original question with no history.
It ran on the same revision-2 snapshot and all-active single-document
scope as the 39.775 s browser context observation, with a different
retrieval input and isolated process. Its warm call was 8.667 s shorter.
That difference cannot be attributed to warming or to the resolver alone.
No private history was accessed or reconstructed.

Both diagnostic calls fused and scored exactly 10 candidates with one
10 × 509 batch. Pair lengths were 502, 509, 477, 435, 268, 329, 508, 454,
499 and 485. The batch had 624 padded positions out of 5,090 (12.3%).
The candidate sequence, encoded tensors, positions, full rank order,
raw logits, anchor identities, three evidence units, and packed 3,729-token
context matched exactly between the calls. This is cold/warm identity on
the diagnostic workload. It does not establish equality to the historical
browser output.

## Runtime and resources

Deployed revision `9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`, image
`sha256:3bc83208a7526a49abed1b9bd9586b5ae4fd041771732e03030c3ac20419e692`,
container `e006597fd6e4e40939e49c1dd73da7c6d85f33d87d44929c15dc5f0f38bb7cac`,
BGE checkpoint `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`.
The historical Torch FP32 2/2 policy and Qwen3 CPU ONNX profile at 8/1
were preserved. The diagnostic saw four effective CPUs with no tighter
cgroup quota. Model/tokenizer hashes, retrieval settings hash, and index
identities were checked by the preflight probe.

| Resource | Cold | Warm |
|---|---:|---:|
| Assembler process CPU-seconds | 93.95 | 63.31 |
| BGE forward CPU-seconds | 60.63 | 61.29 |
| Sampled process peak cores | 2.00 | 2.00 |
| Sampled host peak busy | 53.0% | 52.4% |
| Process RSS at end | 3.81 GiB | 3.82 GiB |
| Cumulative process peak RSS | 4.03 GiB | 4.17 GiB |
| Minimum sampled host available RAM | 12.22 GiB | 12.20 GiB |

CPU readings use approximately three-second samples. Available swap stayed
unchanged in both sampled windows. Cumulative RSS is a process high-water
mark, not a stage-specific peak.

## Ranked next treatments

1. **Target warm BGE forward cost.** First compare compatible CPU
   execution budgets on representative single-batch long-passage workloads
   with a fixed checkpoint, fixed candidate pool and rank/evidence parity.
   Report both wall time and CPU-seconds. The Recipes sorted-eight result
   does not predict this case. Sorting these lengths into eight plus two
   would save only 56 padded positions, before accounting for an extra
   forward call. That is arithmetic, not a measured speedup.
2. **Investigate first-use dense cost separately.** If post-restart latency
   matters, instrument or qualify a bounded startup warm-up that separates
   Qwen3 session initialization from the first query, artifact I/O and index
   access. Warm-up would shift cold cost and would leave the measured warm
   BGE work in place.
3. **Address overlapping requests as a lifecycle issue.** The existing
   owned-worker path could limit repeated or abandoned work after separate
   design review. This isolated result does not measure concurrency or
   justify a query timeout, depth, batching or backend change.

The diagnostic reused the production assembler and prior lightweight scorer
instrumentation, mounted only in the isolated container. The original store
was closed before copying. The temporary process used isolated Qdrant,
read-only mounted models, and no network. Exactly two assembler calls ran,
with no generation or HTTP question submission.

## Restoration

Both health endpoints returned HTTP 200. The original container signature
with image, mounts and restart policy matched preflight. The follow-up
probe matched revision 2, snapshot and source-inventory digest. Diagnostic
storage and the temporary remote launcher were removed. The automatic
STOP policy remained in force.
