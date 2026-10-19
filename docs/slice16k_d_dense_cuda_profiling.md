# Slice 16K-D — Dense / CUDA profiling (D0 baseline)

**Authority:** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IMPLEMENTATION-AUTH-001` — AUTHORIZED  
**Exact parent:** `33a031b6a1bbda0b3b80fa96c8bff0fdfcece06f`  
**Branch:** `implementation/16k-d-dense-cuda-profiling`  
**Controlling design:** `docs/slice16k_beta_ingestion_readiness_design.md` §9  
**Human-accepted design subject:** `0839b565cd60958141366048520236a71bf16fd0`  
**Status:** 16K-D D0 BASELINE COMPLETE / READY FOR INDEPENDENT REVIEW

## D0 scope (frozen)

Implement observational instrumentation + measure the authoritative current path:

- CUDA / batch size 32
- current Qwen3-Embedding-0.6B
- current searchable-unit policy / persistence / local Qdrant

Design §9.2 lists CUDA **FP32** / batch 32 as step 1. On this host,
harness-forced FP32 failed at first encode with `CUBLAS_STATUS_EXECUTION_FAILED`
(`cublasSgemm`) — evidence:
`docs/evidence/16k_d_dense_cuda/d0_fp32_force_FAILED_cublasSgemm.json`.
The measurable D0 cold baseline therefore uses **native as-loaded dtype**
(provisioned `torch_dtype=bfloat16`) with batch 32; production defaults remain
unchanged. FP16 treatment / batch sweep / attention / persistence / Qdrant
optimization / default promotion stay closed.

Primary workload: cold replay of the ~1296-child incident chunk set
(`chunkset_d0b1fee…` / `corpus_3c74b057…`), identity-only in repository evidence.

## Instrumentation

- Env gate: `OFFLINE_RAG_DIAG_DENSE_PROFILE=1`
- Module: `src/offline_rag/dense/profiling.py`
- Hooks: `src/offline_rag/dense/pipeline.py` (encode / artifact persistence /
  point construction / Qdrant upsert)
- Reuses 16K-B aggregate slots (`dense_generation_ms`,
  `dense_materialization_ms`, `dense_execution`, `model_input_tokens_per_sec`)
- Detailed per-batch records: evidence only (`dense_profile` in report metadata
  when gated on; not expanded into the durable ManagedOperationMetrics DTO)

## Evidence

`docs/evidence/16k_d_dense_cuda/`

Harness: `scripts/diag_16k_d_dense/run_d0_baseline.py`

## Explicitly closed until D0 IR accept + usability threshold freeze

FP16 treatment, batch-size sweep, optimized attention, persistence/Qdrant
optimization, default promotion, 16K-E/F/G, Slice 17/18, main promotion,
HTTP-500 GPU investigation reopen.
