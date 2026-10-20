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

**Status:** D1 STALL-ATTRIBUTION TOOLING COMPLETE / READY FOR INDEPENDENT REVIEW  
**D0:** BASELINE COMPLETE / INDEPENDENTLY ACCEPTED  
**F001:** CLOSED  
**D1 scientific execution (D1-A / D1-B):** NOT AUTHORIZED  

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

## D1 tooling (this authority)

Contract: `dense-cuda-profile-v2` under env gate `OFFLINE_RAG_DIAG_DENSE_PROFILE=1`.

Per-batch observations (no private text): batch identity digest; chunk-ID digest;
item count; token-length min/median/p95/max; aggregate input tokens; padded-token
workload; padding fraction; host-wall encode ms; CUDA-event device ms (gated);
process CPU-time delta; voluntary/involuntary context-switch deltas; CUDA
allocator allocated/reserved/peak; external nvidia-smi utilization / clocks /
temperature / power / pstate / throttle reasons (null when unavailable).

Perturbation rule: CUDA event synchronize is diagnostic-gated only; disabled path
unchanged; external GPU samples run outside the encode critical path.

Supported (not executed here): D1-A full cold reproduction of
`D0-INCIDENT-1296-CHILD-V1`; D1-B targeted paired replay of predetermined
fast/slow/discordant batch identities (exact IDs + repetition frozen in later
execution AUTH).

## Explicitly NOT AUTHORIZED under this tooling authority

D1 scientific runs (D1-A/D1-B) · changing BF16 · changing batch 32 · changing
SDPA · FP16/D2 · batch sweep/D3 · attention/D4 · persistence/Qdrant/D5 ·
model/chunking/searchable-unit changes · production synchronization · CUDA
cache-clearing/eviction policy · HTTP-500 investigation · threshold modification ·
16K-E/F/G · main promotion.

## Evidence

- D0: `docs/evidence/16k_d_dense_cuda/` — authoritative clean rerun
  `d0_baseline_32e52024df47.json` (+ provenance / comparison artifacts).
- D1 tooling capability (non-scientific):
  `docs/evidence/16k_d_dense_cuda_tooling/d1_tooling_capability.json`
