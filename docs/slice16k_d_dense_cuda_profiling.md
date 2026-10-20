# Slice 16K-D — Dense / CUDA profiling (D0 baseline)

**Implementation authority:** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IMPLEMENTATION-AUTH-001` — AUTHORIZED  
**Exact implementation parent:** `33a031b6a1bbda0b3b80fa96c8bff0fdfcece06f`  
**Exact independently accepted technical subject:** `32e52024df47b9add7ce02675a1d40555ac55eae`  
**Exact independently accepted evidence subject:** `70abf3003ba37cd983772e084f9616fe3678a17a`  
**Branch:** `implementation/16k-d-dense-cuda-profiling`  
**Controlling design:** `docs/slice16k_beta_ingestion_readiness_design.md` §9  
**Human-accepted design subject:** `0839b565cd60958141366048520236a71bf16fd0`  

**Historical independent review (IR-001):** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-001` — REWORK REQUIRED (F001) — preserved as provenance  
**Rework authority:** `S16-K-D-D0-BASELINE-EVIDENCE-PROVENANCE-REWORK-AUTH-001` — AUTHORIZED  
**Exact rework technical execution subject:** `32e52024df47b9add7ce02675a1d40555ac55eae`  
**Independent review (IR-002):** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-002` — ACCEPT  
**Acceptance-record authority:** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-002-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact acceptance-record parent:** `70abf3003ba37cd983772e084f9616fe3678a17a`  

**Status:** 16K-D D0 BASELINE COMPLETE / INDEPENDENTLY ACCEPTED  
**F001:** CLOSED (clean candidate-SHA evidence rerun; no `src/**` changes)

## Accepted D0 scientific conclusions

1. **Authoritative current lane:** CUDA / BF16 / batch 32 / SDPA (Qwen3-Embedding-0.6B).
2. **FP32-as-current-baseline assumption:** FALSIFIED (native load is BF16).
3. **Bottleneck:** model encode dominates (~99% of dense runtime on the clean run).
4. **Persistence / Qdrant optimization:** NOT JUSTIFIED by D0 (seconds vs ~25 min encode).
5. **Timing variability:** encode latency is highly variable / intermittently stalls;
   the clean-run wall ≈ 25.2 min is **not** a deterministic constant (historical
   development run ≈ 35.8 min); accepted finding is the two-regime stall
   phenomenon, not a fixed wall-clock SLO.
6. **Sequence length alone** does not obviously explain stalls.

Primary workload: cold `D0-INCIDENT-1296-CHILD-V1` (`chunkset_d0b1fee…` /
`corpus_3c74b057…`); identity-only in repository evidence.

## Instrumentation (accepted)

- Env gate: `OFFLINE_RAG_DIAG_DENSE_PROFILE=1`
- Module: `src/offline_rag/dense/profiling.py`
- Hooks: `src/offline_rag/dense/pipeline.py`
- Harness: `scripts/diag_16k_d_dense/run_d0_baseline.py`

## Evidence

`docs/evidence/16k_d_dense_cuda/`

| Artifact | Role |
|----------|------|
| `d0_baseline_32e52024df47.json` | Authoritative clean candidate-SHA rerun |
| `d0_baseline_32e52024df47_provenance_pre.json` / `_post.json` | Source digests + HEAD binding |
| `d0_baseline_32e52024df47_vs_33a031b6a1bb_comparison.json` | Historical vs clean (do not average) |
| `d0_baseline_33a031b6a1bb.json` | Historical development run; retained unmodified |
| `d0_fp32_force_FAILED_cublasSgemm.json` | Development diagnostic only (not an accepted FP32 experiment) |

## Explicitly still closed

BF16 batch sweep · attention/backend treatments · any FP16 experiment ·
persistence/Qdrant optimization · default promotion · usability-threshold freeze ·
§9.2 treatment-sequence reconciliation · 16K-E/F/G · main · HTTP-500 reopen.

Treatment-sequence reconciliation and beta usability-threshold freeze require a
**separate** authority after this acceptance-record tip.
