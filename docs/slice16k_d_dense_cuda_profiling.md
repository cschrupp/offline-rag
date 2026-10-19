# Slice 16K-D — Dense / CUDA profiling (D0 baseline)

**Implementation authority:** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IMPLEMENTATION-AUTH-001` — AUTHORIZED  
**Exact implementation parent:** `33a031b6a1bbda0b3b80fa96c8bff0fdfcece06f`  
**Exact implementation candidate (IR-001 subject):** `32e52024df47b9add7ce02675a1d40555ac55eae`  
**Independent review (IR-001):** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-001` — REWORK REQUIRED (F001) — preserved as provenance  
**Rework authority:** `S16-K-D-D0-BASELINE-EVIDENCE-PROVENANCE-REWORK-AUTH-001` — AUTHORIZED  
**Exact rework technical execution subject:** `32e52024df47b9add7ce02675a1d40555ac55eae`  
**Branch:** `implementation/16k-d-dense-cuda-profiling`  
**Controlling design:** `docs/slice16k_beta_ingestion_readiness_design.md` §9  
**Human-accepted design subject:** `0839b565cd60958141366048520236a71bf16fd0`  
**Status:** 16K-D D0 BASELINE REWORK COMPLETE / READY FOR INDEPENDENT RE-REVIEW  
**F001:** CLOSED pending re-review (clean candidate-SHA rerun published; no `src/**` changes)

## D0 scope (frozen)

Observational instrumentation + measure the executable current path:

- CUDA / batch size 32
- current Qwen3-Embedding-0.6B
- current searchable-unit policy / persistence / local Qdrant

Design §9.2 lists CUDA **FP32** / batch 32 as step 1. On this host,
harness-forced FP32 failed at first encode with `CUBLAS_STATUS_EXECUTION_FAILED`
(`cublasSgemm`) — evidence:
`docs/evidence/16k_d_dense_cuda/d0_fp32_force_FAILED_cublasSgemm.json`.
The measurable D0 cold baseline therefore uses **native as-loaded dtype**
(provisioned `torch_dtype=bfloat16`) with batch 32; production defaults remain
unchanged.

Primary workload: cold replay of the ~1296-child incident chunk set
(`chunkset_d0b1fee…` / `corpus_3c74b057…`), identity-only in repository evidence.

## Instrumentation (unchanged in rework)

- Env gate: `OFFLINE_RAG_DIAG_DENSE_PROFILE=1`
- Module: `src/offline_rag/dense/profiling.py`
- Hooks: `src/offline_rag/dense/pipeline.py`
- Harness: `scripts/diag_16k_d_dense/run_d0_baseline.py`
- Rework: **docs/evidence only** — no `src/**` changes

## Evidence

`docs/evidence/16k_d_dense_cuda/`

| Artifact | Role |
|----------|------|
| `d0_baseline_33a031b6a1bb.json` | Historical development run (uncommitted tree); retained unmodified |
| `d0_baseline_32e52024df47.json` | Clean candidate-SHA rerun (authoritative subject for re-review) |
| `d0_baseline_32e52024df47_provenance_pre.json` / `_post.json` | HEAD/branch/cleanliness + source digests |
| `d0_baseline_32e52024df47_vs_33a031b6a1bb_comparison.json` | Side-by-side; do not average |
| `d0_fp32_force_FAILED_cublasSgemm.json` | FP32 lane falsification |

## Explicitly closed until D0 IR accept + usability threshold freeze

FP16 treatment, batch-size sweep, optimized attention, persistence/Qdrant
optimization, default promotion, 16K-E/F/G, Slice 17/18, main promotion,
HTTP-500 GPU investigation reopen. §9.2 optimization sequence needs scientific
reconciliation after D0 acceptance (BF16 already native).
