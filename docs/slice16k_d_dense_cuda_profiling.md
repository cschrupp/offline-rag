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

**Status:** 16K-D EXPERIMENTAL PLAN RECONCILED / STOP  
**D0:** BASELINE COMPLETE / INDEPENDENTLY ACCEPTED  
**F001:** CLOSED  

## Authoritative current lane (D0)

CUDA / **BF16** / batch **32** / **SDPA** — Qwen3-Embedding-0.6B.

Accepted D0 findings: encode-dominant (~99%); persistence/Qdrant negligible;
highly variable batch encode latency (stalls); sequence length alone does not
explain stalls; FP32-as-current-baseline assumption falsified.

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

## Explicitly NOT AUTHORIZED under this reconciliation

D1 diagnostic execution · FP16 treatment · batch sweep · attention changes ·
persistence/Qdrant optimization · production/default changes · 16K-E/F/G ·
Slice 17/18 · main · HTTP-500 GPU investigation reopen.

**Next substantive authority parent:** this reconciliation tip.  
**Next gate:** D1 — native BF16/batch-32/SDPA stall-attribution diagnostic
(separate execution AUTH).

## Evidence (D0)

`docs/evidence/16k_d_dense_cuda/` — authoritative clean rerun
`d0_baseline_32e52024df47.json` (+ provenance / comparison artifacts).
