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
**D2 design IR-001:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-IR-001` — REWORK REQUIRED (F001–F004) — preserved  
**D2 design rework authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-REWORK-AUTH-001` — AUTHORIZED  
**Exact D2 design rework parent:** `80f4b09e0c85400d13c1f505a073cee6eab6f50b`  
**D2 design F001–F004:** CLOSED  
**D2 design IR-002:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-IR-002` — REWORK REQUIRED (F005–F006) — preserved  
**D2 design rework-2 authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-REWORK2-AUTH-001` — AUTHORIZED  
**Exact D2 design rework-2 parent:** `5da766959fa3557f9300fa3a3147f0bb4f3bd853`  
**D2 design F005–F006:** CLOSED  
**D2 design IR-003:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-IR-003` — ACCEPT  
**Exact independently accepted D2 design subject:** `8f96657d73b2213fb9b43557b001bc4c5a42188b`  
**D2 implementation authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-AUTH-001` — AUTHORIZED  
**Exact D2 implementation parent:** `8f96657d73b2213fb9b43557b001bc4c5a42188b`  
**D2 implementation IR-001:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-IR-001` — REWORK REQUIRED (F001–F005) — preserved  
**D2 implementation rework authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-REWORK-AUTH-001` — AUTHORIZED  
**Exact D2 implementation rework parent:** `b505c14ab8d0399b0cd5f6f7c796223ce5ccfe11`  
**D2 implementation F001–F005:** CLOSED  
**D2 implementation rework-2 authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-REWORK2-AUTH-001` — AUTHORIZED  
**Exact D2 implementation rework-2 parent:** `a488fb393d5f194bea91e337a928335e76cbd45f`  
**D2 design document:** `docs/slice16k_d_d2_practical_execution_optimization_design.md`  
**D2 harness:** `scripts/diag_16k_d_dense/run_d2_campaign.py`  

**Status:** D2 PRACTICAL EXECUTION OPTIMIZATION IMPLEMENTATION REWORK 2 COMPLETE / READY FOR INDEPENDENT RE-REVIEW  
**D0:** BASELINE COMPLETE / INDEPENDENTLY ACCEPTED  
**D1:** COMPLETE / INDEPENDENTLY ACCEPTED (scientific program closed for product pivot)  
**D1 tooling F001 / D1 analysis F001:** CLOSED  
**Contract (attribution tooling):** `dense-cuda-profile-v2`  
**D2 design:** COMPLETE / INDEPENDENTLY ACCEPTED  
**D2:** IMPLEMENTATION ONLY / EXECUTION NOT AUTHORIZED  
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

## D2 practical execution optimization

Authoritative design: `docs/slice16k_d_d2_practical_execution_optimization_design.md`
(IR-003 ACCEPT at `8f96657…`).

**Implementation (this tranche + rework F001–F005 + rework-2 F006–F009):**
explicit `indexing.embedding.precision` (`native`|`fp16`, default `native`; env
`OFFLINE_RAG_EMBEDDING_PRECISION`); FP16 CUDA-only fail-closed; post-load /
pre-encode conversion with observably verified float16 (no inferred success);
precision/batch excluded from embcfg_/index identity; D2 state machine in
`src/offline_rag/dense/d2_campaign.py` (parity+correctness both required True);
fail-closed observed preflight + locked real cell executor in
`src/offline_rag/dense/d2_execution.py` (mandatory history + always
`assert_transition_allowed`; `EXPECTED_EXECUTION_HEAD` fail-closed;
prepared corpus/chunk state verification; practical timing
encode/persist/point/qdrant/chunks/sec; governed
`assess-confirmation` for G1-3/G2-3); harness
`scripts/diag_16k_d_dense/run_d2_campaign.py` (`plan` / `preflight` /
`validate-transition` / `classify-failure` / `assess-confirmation`;
`execute-cell` requires `--history` and calls gated `execute_d2_cell` while
`EXECUTION_AUTHORIZED=False`).

Staged stop-conditional campaign (normal 4; G1 screen-fail→G2 = 6; G1
confirmation timing-fail→G2 = 7 absolute max; no discretionary eighth):

- **G1:** CUDA FP16 / batch 32 (two cold screens);
- **C0:** CPU · same Qwen · batch 32 · production path · no CUDA · no CPU tuning;
  observe/record effective dtype/backend/threads/RSS (not graded on 10/12 GPU proxy);
- **G2:** CUDA FP16 / batch 16 — only for G1 timing/variance failure or G1 valid
  resource failure (not for G1 FP16 parity/correctness failure; high VRAM alone
  is not a G2 trigger);
- **Gx-3:** confirmation only when the two-run screen says the lane remains
  mathematically eligible; then apply timing/variance gate + separate parity gate.

**Two-run screen (after both valid):** either >12 min, or both >10 min → no Gx-3
for that lane (G1 → open G2 after C0; G2 → STOP GPU). Otherwise both ≤12 and at
least one ≤10 → run Gx-3.

**G2 eligibility:** G1 timing/variance or valid resource failure → G2 may open;
G1 FP16 parity/correctness failure → STOP (G2 not opened). Any G2
parity/correctness failure is terminal for D2.

**Validity:** `valid` · `valid_negative_resource` · `invalid`. Correct-identity
CUDA OOM/resource exhaustion is valid negative (not auto-retry).

**Performance reference:** accepted clean D0 BF16/b32 only. D0 historical and
D1-A1/A2 are context/attribution only — not FP16 speedup controls, not D2
pass/fail, not §9.4 confirmation members.

Lighter instrumentation than D1; no per-batch CUDA-event sync for curiosity.
Retrieval-parity probe inputs/thresholds remain unfrozen until execution AUTH.

## Explicitly NOT AUTHORIZED under this implementation AUTH

D2 scientific/benchmark cell execution · FP16 model runs · CPU benchmark runs ·
parity execution · production default switch · model replacement · mechanical
D3–D5 · attention experiments · persistence/Qdrant opt · HTTP-500 reopen ·
16K-E/F/G · main.

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
