# PR #3 independent review follow-up response

**REVISE / HOLD MERGE.** The hosted frontend failure predates the batching
changes. The same heading assertion failed at the exact PR base and reviewed
head with identical UI blobs and dependency locks, 12 passed and one failed
on each. A temporary change to the test's level-one heading expectation made
all 13 pass at the base. Keep the test-only correction on the 18D-R
integration line. PR #3 makes no frontend change. [Reproduction details](CI_REPRODUCTION.md)

The sole test change adds a two-thread regression for each batching strategy.
The fixture exercises one shared, loaded tokenizer/model. It checks tokenizer
calls hold the lock, shows two model forwards can overlap and verifies that
their distinct scores stay attached to their original requests. The lock
covers the tokenizer's mutable padding and truncation state during prepass
and per-batch encoding. Model inference uses request-local tensors and score
maps. Native model contention and cancellation under load remain qualification
items beyond the fixture.

Existing tests cover empty and malformed pairs, score-count and finiteness
checks, stable equal-length ordering, active token and position parity,
1,024-token passage truncation, near ties, exact rank and packed evidence,
and snapshot binding. Consecutive remains the default. The depth, checkpoint,
scientific fingerprint and parity tolerance are unchanged.

156 targeted Python tests passed, including snapshot, initialization,
reranker/context, generation and failure observability suites. One existing
Starlette/FastAPI TestClient deprecation warning appeared. Ruff lint and
format and `git diff --check` passed. The original evidence files remain
unchanged.

The CPU pilot specifies 16 assembler calls for the two mandatory cases and
at most 40 with all frozen optional slots. Separate lifecycle limits are
28 workload submissions and eight failure/cancellation fixtures. CPU opt-in
requires fixed-depth evidence parity and bounded load/restoration checks.
CUDA has a separate FP32 GPU-backed plan for parity, timing and memory.
Neither pilot ran. No CUDA performance conclusion is supported. [CPU pilot](CPU_PILOT.md) · [CUDA and release dependency](CUDA_AND_RELEASE.md)

The release plan preserves the deployed lazy-initialization correction,
separates the frontend test-only repair, and keeps the feature delta distinct
from the wider 18D-R lineage. Roll back a future opt-in by returning to
consecutive batching and retaining the initializer. No production defaults,
deployments, publications or merges changed.

## Post-lock CPU development check

The existing benchmark ran on the final scorer at the reviewed head with the
local pinned FP32 BGE checkpoint, CPU-only Torch 2.14.0, 16 affinity-visible
CPUs and Torch threads 2/2. Both synthetic cases passed exact full-rank
and predeclared numerical parity. A tokenizer-only check with the same
local tokenizer also matched all 30 active pair inputs and right-padded
attention masks against the unpadded prepass in both grouping orders,
including pairs reaching the 1,024-token limit.

| Case | Consecutive median wall | Sorted-eight median wall | Consecutive median CPU | Sorted-eight median CPU |
| --- | ---: | ---: | ---: | ---: |
| short_homogeneous | 3.889 s | 3.890 s | 7.626 CPU-s | 7.724 CPU-s |
| mixed | 37.130 s | 13.489 s | 73.806 CPU-s | 26.866 CPU-s |

Maximum absolute logit difference was 1.91e-6. Raw rows retain per-batch
shapes and timing, prepass time and cumulative RSS. This was a single
development process with two observations per arm. CPU allocation and
workload differ from deployment. No assembler/inference API performance,
per-strategy memory peak or production latency claim follows from it.
[Post-lock measurements](post-lock-cpu.jsonl)
