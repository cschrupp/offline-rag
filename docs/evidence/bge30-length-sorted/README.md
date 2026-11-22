# BGE-30 length-sorted batching

The PyTorch cross-encoder defaults to consecutive batching using
`reranker.batch_size` (16 by default). To opt in on a development checkout,
set the following in the YAML overlay used by the application.

```yaml
reranker:
  batching_strategy: length_sorted_8
```

For Docker or a service environment, pass
`OFFLINE_RAG_RERANKER_BATCHING_STRATEGY=length_sorted_8`. The field is
validated at settings load. Restart the development process so it builds
its process-scoped scorer with the new settings. Roll back by removing
the override or setting it to `consecutive` and restarting the process.

Both strategies use the existing CPU/CUDA device resolver, the pinned
BGE checkpoint and tokenizer, passage-only truncation at 1,024 tokens,
and one raw logit per pair. Sorted-eight measures actual truncated lengths,
orders by length and original ordinal, and restores scores to original
ordinals before canonical ranking. The tokenizer lock protects shared
mutable padding and truncation settings. It does not enclose model forward
or device transfer. Explicit GPU synchronization is confined to the local
benchmark.

The strategy is excluded from the scientific fingerprint because the
candidate pool, score interpretation, and ranking policy remain the same.
Floating-point differences can still change near ties. Treat exact ranking
and evidence parity as a qualification gate, and keep consecutive batching
for an unqualified device or workload. The evaluation tolerance is
`abs(delta) <= 1e-4 + 1e-5 * abs(baseline)`. Existing snapshots retain their
IDs. The resolved strategy and device are available in retrieval and
assembly metadata and generation diagnostics under `reranker_execution`.
The durable product trace schema is unchanged, preserving rollback reads.

The [research decision memorandum](https://github.com/cschrupp/offline-rag/blob/27b1389654f7c89e72e98447bd81d34cc38b03fe/docs/research/bge_quality_latency_frontier/evidence/production-qualification/DECISION_MEMO.md)
describes the separate production qualification. The Recipes result
motivates testing heterogeneous workloads. The Rich ten-pair experiment
found no smaller consecutive batch that reached its 20% improvement gate.
Those workloads do not set a runtime selection threshold.

## Reproduce development checks

```bash
pytest -q tests/unit/test_cross_encoder_batching.py \
  tests/unit/test_cross_encoder_initialization.py \
  tests/unit/test_hybrid_rerank.py tests/unit/test_context_expansion.py

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python \
  docs/evidence/bge30-length-sorted/benchmark.py \
  models/rerankers/bge-reranker-v2-m3 --device cpu
```

On an approved CUDA host, repeat with `--device cuda`. The benchmark
checks logit tolerance and exact rankings on synthetic inputs using the
local FP32 model. It synchronizes CUDA around forward and scorer timing.
Elapsed time includes the prepass and tokenization. Process CPU time,
batch widths, and cumulative peak RSS are reported. Peak RSS is shared by
both strategies within the benchmark process, so it cannot establish
per-strategy or GPU memory requirements.

Before an opt-in CPU pilot, run representative fixed-depth parity on query
and context assembly, then check latency, resource use, failures, and
cancellation under load. Document the exact image, model artifacts, device
and runtime settings. Keep the consecutive override available for rollback.
