# CUDA qualification and release lineage

## Minimum GPU-backed qualification

On an approved isolated NVIDIA host, pin GPU model, driver, CUDA/Torch
build, CPU allocation, container digest, checkpoint/tokenizer, effective
device and precision. Use the actual shared application scorer in its
existing CUDA FP32 mode; fail if it falls back to CPU or a different
precision. Record production-equivalent math settings including TF32 and
autocast. Keep those settings identical across arms.

Exercise one short homogeneous small pool and one near-tie heterogeneous
30-pair pool (including passage truncation at 1,024). Warm each workload
once per arm and collect three counterordered paired passes, with the
same exact active-input, raw-logit tolerance, ranking, anchor, evidence
and packed-context gates as the CPU protocol. Use the approved isolated
snapshot fixture for context checks. Record loaded, allocated and reserved
GPU memory including reset per-arm peak counters, host RSS, CPU time
and completed scorer/assembler latency. Synchronize at timing boundaries
and use CUDA events for forward time, without adding synchronization to
production. Report both isolated outcomes and, before any concurrent
opt-in, a two-client smoke for capacity, failure and OOM behavior under
an agreed memory limit. No CUDA speed claim until measured, and a latency
regression can justify retaining consecutive on that hardware.

## Release dependency and rollback

| Ref | Identity at review | Relationship |
| --- | --- | --- |
| `main` | `8591aacc1810ba7265014c55a4d9327f7f755a02` | Ancestor of initialization line |
| Deployed source | `9c92e706c4b9e9d9ac0816a655bdf131cc63fca1` | Adds reranker lazy-init correction |
| `corrective/18d-r-reranker-initialization` | `f2dd2bda1890fb86ddb055ef101c2e5e098eba43` | One evidence commit after deployed source, 18 ahead of main at review |
| PR #3 reviewed head | `3a6317c51010de6242adf187554842de52ddf174` | Two commits after corrective branch |

The 18 commits include the wider 18D-R Engineering work and Docker,
HTTP-idempotency and Docling fixes as well as the initializer. Treat that
line as a release dependency with its own acceptance rather than retargeting
PR #3 directly to main today. Land a test-only Engineering heading fix
separately on the 18D-R integration line. Clear its independent acceptance
and CI gates, then land the approved initialization/dependency lineage.
Verify the initializer is in the destination ancestry and the feature diff
contains only authorized batching, tests and evidence. Retarget or create a
minimal reviewed integration diff only once the approved base is present.
If the full 18D-R line cannot land, review a separate minimal initializer
backport and verify its dependency closure before replaying the batching
delta. Never use the feature PR as approval for that ancestry.

If a future opt-in pilot fails, remove the override or set it to
`consecutive` and restart. Preserve the accepted checkpoint, snapshots,
publications and writable data. If image rollback is needed, use the last
approved image that contains the initialization correction. Compare
readiness, errors, query stage latency, and evidence parity against the
baseline after restoration. No merge, migration, deployment or opt-in
activation is authorized here.
