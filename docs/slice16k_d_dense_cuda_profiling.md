# Slice 16K-D — Dense / CUDA profiling

**Implementation authority:** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IMPLEMENTATION-AUTH-001` — AUTHORIZED  
**Exact independently accepted technical subject:** `32e52024df47b9add7ce02675a1d40555ac55eae`  
**Exact independently accepted evidence subject:** `70abf3003ba37cd983772e084f9616fe3678a17a`  
**Branch:** `implementation/16k-d-dense-cuda-profiling`  
**Controlling design:** `docs/slice16k_beta_ingestion_readiness_design.md` §9  

**Historical IR-001:** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-001` — REWORK REQUIRED (F001) — preserved  
**IR-002:** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-002` — ACCEPT  
**Acceptance-record authority:** `S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-002-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact acceptance-record parent / tip (pre-reconciliation):** `70abf30…` / `c801401a486c6ecd425840649fdd6f6893c50f18`  

**Experimental-plan reconciliation authority:** `S16-K-D-EXPERIMENTAL-PLAN-RECONCILIATION-AUTH-001` — AUTHORIZED  
**Exact reconciliation parent:** `c801401a486c6ecd425840649fdd6f6893c50f18`  
**Exact reconciliation tip (D1 tooling parent):** `4449f0053faf972726955db889e83ffcda8a2143`  

**D1 stall-attribution tooling authority:** `S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-AUTH-001` — AUTHORIZED  
**Exact D1 tooling parent:** `4449f0053faf972726955db889e83ffcda8a2143`  

**D1 tooling IR-001 (historical):** `S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-IR-001` — REWORK REQUIRED (F001) — preserved  
**D1 tooling rework authority:** `S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-REWORK-AUTH-001` — AUTHORIZED  
**Exact D1 tooling rework parent:** `9690ffb7b55502c8060563e94e3a8cf024c82360`  
**D1 tooling IR-002:** `S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-IR-002` — ACCEPT  
**D1 tooling IR-002 acceptance-record authority:** `S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-IR-002-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact D1 tooling acceptance-record parent:** `c98d878e2e1327e984e60ceb59e507b6965962fe`  
**Exact independently accepted D1 tooling technical subject:** `433725952c15a2feed4b65986d03e254d08d1568`  
**Exact independently accepted D1 tooling evidence/docs subject:** `c98d878e2e1327e984e60ceb59e507b6965962fe`  

**D1 scientific matrix freeze authority:** `S16-K-D-D1-SCIENTIFIC-MATRIX-FREEZE-AUTH-001` — AUTHORIZED  
**Exact D1 matrix freeze parent:** `016e338bf2b848e30cd89c7ba6ace6e6f39d1139`  
**D1 matrix freeze document:** `docs/slice16k_d_d1_scientific_matrix_freeze.md`  

**D1 scientific execution authority:** `S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-AUTH-001` — AUTHORIZED  
**Exact D1 scientific execution parent:** `0ecf2f74e4d283f59ab932abbdaee6ebb821a5ac`  

**Status:** D1 SCIENTIFIC EXECUTION AUTHORIZED / IN PROGRESS  
**D0:** BASELINE COMPLETE / INDEPENDENTLY ACCEPTED  
**D1 tooling:** COMPLETE / INDEPENDENTLY ACCEPTED  
**D1 tooling F001:** CLOSED  
**Contract:** `dense-cuda-profile-v2`  
**D1 scientific matrix:** FROZEN  
**D1 scientific execution sequence:** D1-A1 → D1-A2 → D1-B (fixed; no adaptive changes)

## Authoritative current lane (unchanged)

CUDA / **BF16** / batch **32** / **SDPA** — Qwen3-Embedding-0.6B.

Accepted D0 findings: encode-dominant (~99%); persistence/Qdrant negligible;
highly variable batch encode latency (stalls); sequence length alone does not
explain stalls; FP32-as-current-baseline assumption falsified.

D0 clue shaping D1: slow/fast regimes are far more repeatable by batch identity
than by host noise alone (clean vs historical rank correlation ~0.81; of 20
batches >30 s in clean, all 20 also >30 s historically). D1 priority is therefore
batch content/shape and model/device execution first, with host/WSL/power/thermal
as competing explanations.

## Frozen beta usability thresholds (§9.4)

Reference host + cold `D0-INCIDENT-1296-CHILD-V1` (generated=1296, reused=0):

| Gate | Threshold |
|------|-----------|
| Proxy usability | median wall ≤ **10 min** |
| Variance guard | no confirmation run > **12 min** |
| Repeatability | **3** clean cold confirmation runs |
| Correctness | no indexing / retrieval / parity regression |
| 16K-F full corpus | primary ~7.5–8k-child cold dense ≤ **60 min** |

The ~25.2 min clean D0 baseline **fails** the 10-minute proxy — as intended.
The 10-minute gate is a screening target, not a linear scaling claim to 16K-F.

## Reconciled treatment sequence (§9.2.2)

`D0 (accepted) → D1 stall attribution → D2 BF16 vs FP16 → D3 batch sweep → D4 attention (conditional) → D5 persistence/Qdrant (if ≥10% wall)`

Historical FP32→FP16→batch sequence: **SUPERSEDED** (provenance only).

## D1 tooling (independently accepted)

Contract: `dense-cuda-profile-v2` under env gate `OFFLINE_RAG_DIAG_DENSE_PROFILE=1`.

Per-batch observations (no private text): batch identity digest; chunk-ID digest;
item count; token-length min/median/p95/max; aggregate input tokens; padded-token
workload; padding fraction; host-wall encode ms; CUDA-event device ms (gated);
process CPU-time delta; voluntary/involuntary context-switch deltas; CUDA
allocator allocated/reserved/peak; external nvidia-smi utilization / clocks /
temperature / power / pstate / throttle reasons (null when unavailable).

Interval contract: CUDA event setup → rusage-before → wall-start → encode →
wall-stop → rusage-after → CPU delta → CUDA end-event/synchronize. Thus
`encode_ms` and `process_cpu_delta` share the encode-body interval.

Perturbation rule: CUDA event synchronize is diagnostic-gated only; disabled path
unchanged; external GPU samples run outside the encode critical path.

## D1 scientific matrix (frozen; execution NOT AUTHORIZED)

Authoritative freeze: `docs/slice16k_d_d1_scientific_matrix_freeze.md`.

- **D1-A1 / D1-A2:** two independent cold full reproductions of
  `D0-INCIDENT-1296-CHILD-V1` (`generated=1296` / `reused=0`); no A1 reuse for
  A2; attribution-only (not §9.4 substitutes).
- **D1-B cells:** `batch_index` 1, 14, 17, 13, 4, 6 (F1/S1/F2/S2/D1/D2), selected
  solely from pre-D1 D0 runs; D1-A must not alter membership.
- **D1-B order:** counterbalanced pair blocks P1/P2/P3; 6 measured encodes per
  selected batch (36 total); one process / one model load; no warm-up on
  selected batches.
- Fail-closed identity derivation before any model call; frozen analysis and
  validity/retry rules as in the freeze document.

## Explicitly NOT AUTHORIZED

D1-A/B scientific execution · changing BF16 · changing batch 32 · changing
SDPA · FP16/D2 · batch sweep/D3 · attention/D4 · persistence/Qdrant/D5 ·
model/chunking/searchable-unit changes · production synchronization · CUDA
cache-clearing/eviction policy · HTTP-500 investigation · threshold modification ·
16K-E/F/G · main promotion.

## Evidence

- D0: `docs/evidence/16k_d_dense_cuda/` — authoritative clean rerun
  `d0_baseline_32e52024df47.json` (+ provenance / comparison artifacts).
- D1 tooling capability (non-scientific):
  `docs/evidence/16k_d_dense_cuda_tooling/d1_tooling_capability.json`
- D1 matrix freeze: `docs/slice16k_d_d1_scientific_matrix_freeze.md`
