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
**Exact D1 scientific execution subject (harness tip):** `177620a3440c310759775dbf303420b80df7a05c`  
**Exact sealed D1 cell evidence tip:** `4326586fe0ce3b7ca4c40ded743272d72ba53036`  

**D1 scientific IR-001:** `S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-IR-001` — REWORK REQUIRED (F001 analysis publication) — preserved  
**D1 analysis publication rework authority:** `S16-K-D-D1-SCIENTIFIC-ANALYSIS-PUBLICATION-REWORK-AUTH-001` — AUTHORIZED  
**Exact D1 analysis rework parent:** `4326586fe0ce3b7ca4c40ded743272d72ba53036`  
**D1 scientific IR-002:** `S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-IR-002` — ACCEPT  
**Exact independently accepted D1 analysis publication subject:** `7be6a2b5c7ca7b521f0c642d6a024a1e421d6636`  
**D1 F001:** CLOSED  

**D2 practical execution optimization design authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-AUTH-001` — AUTHORIZED  
**Exact D2 design parent:** `7be6a2b5c7ca7b521f0c642d6a024a1e421d6636`  
**D2 design document:** `docs/slice16k_d_d2_practical_execution_optimization_design.md`  

**Status:** D2 PRACTICAL EXECUTION OPTIMIZATION DESIGN COMPLETE / READY FOR INDEPENDENT REVIEW  
**D0:** BASELINE COMPLETE / INDEPENDENTLY ACCEPTED  
**D1:** COMPLETE / INDEPENDENTLY ACCEPTED (scientific program closed for product pivot)  
**D1 tooling F001 / D1 analysis F001:** CLOSED  
**Contract (attribution tooling):** `dense-cuda-profile-v2`  
**D2:** DESIGN ONLY / EXECUTION NOT AUTHORIZED  
**Program pivot:** scientific optimization → bounded product-engineering optimization

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

## Treatment sequence

**Practical sequence (frozen by D2 design):**  
`D0 → D1 attribution → D2 practical execution optimization → decision`

Historical mechanical sequence
`D2 precision → D3 batch sweep → D4 attention → D5 persistence/Qdrant`:
**SUPERSEDED**. Later work is evidence-triggered, not mechanically scheduled.

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

## D1 scientific (independently accepted)

Freeze: `docs/slice16k_d_d1_scientific_matrix_freeze.md`.  
Evidence: `docs/evidence/16k_d_dense_cuda/d1/`.  
Analysis: `d1-frozen-analysis-v2` + `d1_scientific_interpretation.md`.

D1 SHALL NOT continue root-cause investigation unless a later product decision
requires it.

## D2 practical execution optimization (design only)

Authoritative design: `docs/slice16k_d_d2_practical_execution_optimization_design.md`.

Staged stop-conditional campaign (max 6 new full cold runs; likely 4):

- **G1:** CUDA FP16 / batch 32 (two cold screens);
- **C0:** CPU production baseline (mandatory; not graded on 10/12-minute GPU proxy);
- **G2:** CUDA FP16 / batch 16 — conditional if G1 inadequate;
- **Gx-3:** one confirmation run of the GPU candidate for §9.4 three-run set.

Reuse sealed BF16 D0/D1 evidence as reference. Lighter instrumentation than D1;
no per-batch CUDA-event sync for curiosity. Retrieval-parity probe must be frozen
in the execution AUTH before treatment runs.

## Explicitly NOT AUTHORIZED under this design AUTH

D2 harness · D2 executions · FP16/CPU calls · production/default changes ·
model replacement · mechanical D3–D5 · attention experiments · persistence/Qdrant
opt · HTTP-500 reopen · 16K-E/F/G · main.

## Evidence

- D0: `docs/evidence/16k_d_dense_cuda/` — authoritative clean rerun
  `d0_baseline_32e52024df47.json` (+ provenance / comparison artifacts).
- D1 tooling capability (non-scientific):
  `docs/evidence/16k_d_dense_cuda_tooling/d1_tooling_capability.json`
- D1 matrix freeze: `docs/slice16k_d_d1_scientific_matrix_freeze.md`
- D1 scientific evidence: `docs/evidence/16k_d_dense_cuda/d1/`
  (`d1_preflight.json`, `d1_a1.json`, `d1_a2.json`, `d1_b.json`,
  `d1_analysis.json` v2, `d1_scientific_interpretation.md`;
  preserved invalid: `d1_preflight_INVALID.json`)
