# PR #3 isolated CPU Stage 1 result

**Recipes passed Stage 1. Rich passed scientific parity and missed the
performance screen.** All 16 authorized calls completed, with one warm-up
per arm and three counterbalanced measured pairs per workload.

| Workload | Median paired assembler reduction | Forward reduction | Assembler CPU reduction | Result |
| --- | ---: | ---: | ---: | --- |
| Recipes, 30 candidates | 44.15% | 45.70% | 44.18% | Pass |
| Rich, 10 candidates | −1.26% | −1.29% | −1.07% | Performance screen missed |

Recipes measured assembler times were 60.040–60.616 s consecutive and
33.357–33.757 s sorted-eight. Rich measured 26.690–27.208 s consecutive
and 26.755–45.731 s sorted-eight. The 45.731 s treatment observation
is retained. Forward execution accounted for 45.098 s of that call.
This design cannot establish the cause of the outlier.

Every pair matched candidate order, active input and position hashes,
full ranking and tie-break, anchor and evidence order, and packed-context
hash. The maximum raw-logit delta was 3.81e-6 for Recipes and 2.62e-6
for Rich, within the preregistered tolerance. The closest adjacent Recipes
logit margin in the first measured baseline was about 0.000145.

Representative Recipes batch shapes changed from 16×368 and 14×406 to
8×86, 8×166, 8×241, and 6×406. Rich changed from 10×509 to 8×502 and
2×509. Padding and prepass measurements for every call are in the raw
rows. Peak process RSS was 4.23 GiB and minimum sampled available host
memory was 4.61 GiB. The longest assembler call was 76.532 s.

The diagnostic used the production runtime image plus read-only overlays
of the exact application files changed at PR #3 head
`6900aeb33f063492ab6709a73707ed1e65e6ab8d`. It used the normal scorer
and assembler with diagnostic hooks, FP32 Torch CPU 2/2, four effective
CPUs, and the frozen Qwen3 CPU ONNX profile. Both strategies shared one
model sequentially. The container used network isolation and copied
Qdrant data. The Rich case used the original question without history.
Its retrieval text differs from the historical browser resolver output.

Two setup attempts ended before any assembler call, first because the
container UID could not read staged source files and then because the
diagnostic probe omitted a retriever import. Restoration passed after
each. The final run used readable bind files and the corrected probe.
It made all 16 assembler calls with no call retries.

[Authorization](AUTHORIZATION.md), [paired summary](SUMMARY.txt),
[measurements](measurements.jsonl), [CPU and memory samples](samples.log),
and [snapshot/configuration identities](before.json) are retained.
To regenerate the summary run `python summarize.py measurements.jsonl`.
The resource sample rows contain epoch, available KiB, and aggregate
host CPU counters from /proc/stat. CPU-seconds in the summary are measured
per assembler call.

The separate Engineering assertion correction is [draft PR #4](https://github.com/cschrupp/offline-rag/pull/4).
Its 13 focused and 478 full frontend tests passed locally, along with
lint, typecheck and build. Both hosted jobs passed in run 45034833565.
PR #3 stays draft. Its run 44983174130 passed backend and still failed
the pre-existing heading assertion.

Recipes is eligible for independent review of the next bounded gate.
Rich provides no basis for opt-in. No Stage 2, activation, production
query, deployment, merge, CUDA work, or publication migration occurred.

Restoration passed. The original container, image, mounts and restart
policy were verified. Both health endpoints returned HTTP 200. Recipes
and Rich workspace revisions, snapshots, source inventory hashes and
publication pointers matched the preflight byte for byte. The diagnostic
container and isolated data copy were removed. [Restoration](RESTORATION.log)
