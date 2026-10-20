# 16K-D D1 — Scientific matrix freeze

**Authority:** `S16-K-D-D1-SCIENTIFIC-MATRIX-FREEZE-AUTH-001` — AUTHORIZED  
**Exact parent:** `016e338bf2b848e30cd89c7ba6ace6e6f39d1139`  
**Branch:** `implementation/16k-d-dense-cuda-profiling`  
**Status:** 16K-D D1 SCIENTIFIC MATRIX FROZEN / STOP  

**Prerequisite:** D1 stall-attribution tooling COMPLETE / INDEPENDENTLY ACCEPTED  
- technical subject: `433725952c15a2feed4b65986d03e254d08d1568`  
- evidence/docs subject: `c98d878e2e1327e984e60ceb59e507b6965962fe`  
- contract: `dense-cuda-profile-v2`  

**Lane (unchanged):** Qwen3-Embedding-0.6B / CUDA / BF16 / batch 32 / SDPA  

**Scientific execution (D1-A / D1-B):** NOT AUTHORIZED under this freeze.  
This document freezes the matrix only. A separate bounded execution AUTH is required.

---

## Scientific question

Under the unchanged accepted lane, why do deterministic batches fall into
sharply different latency regimes?

D1 must distinguish, as far as evidence permits:

- batch content / padded sequence-shape effects;
- actual GPU/device execution time;
- host/WSL scheduling or synchronization delay;
- GPU clocks / utilization / power / thermal state;
- relevant CUDA allocator/runtime state.

D1 is not an optimization campaign and must not alter the lane.

---

## D1-A — full cold reproduction family

### Workload

Exact frozen workload: `D0-INCIDENT-1296-CHILD-V1`

Required each cell:

- new fresh process;
- independently reset cold state;
- same exact workload and lane;
- `generated=1296` / `reused=0` required;
- all 41 batches profiled under `dense-cuda-profile-v2`.

### Cells

| Cell | Definition |
|------|------------|
| **D1-A1** | First independent cold full reproduction |
| **D1-A2** | Second independent cold full reproduction |

**A2 must not reuse A1 embeddings or Qdrant.** Fresh cold materials for A2.

### Purpose

Determine whether the same batch identities remain in the slow regime and
correlate them with device-time, shape, and system-state measurements.

### Attribution-only wall times

D1-A runs are attribution runs, not usability-threshold confirmation runs.
Diagnostic synchronization means their wall times **must not** be substituted
into the §9.4 10/12-minute production-performance gate.

---

## D1-B — targeted replay cells

### Preselection rule (frozen; D0-only)

Selection is frozen entirely from the two pre-D1 D0 runs (historical + clean).
**D1-A results must not modify D1-B membership.**

Classification used only for this preselection:

| Class | Rule |
|-------|------|
| consistent fast | &lt;15 s in both D0 runs |
| consistent slow | &gt;30 s in both D0 runs |
| discordant | crossed those regimes between D0 runs |

### Frozen batch cells

`batch_index` values match D0 profiler 0-based indices (batch size 32).

| Cell | batch_index | D0 class | max seq | aggregate tokens | Historical / clean |
|------|-------------|----------|---------|------------------|--------------------|
| **F1** | 1 | consistent fast | 492 | 10,800 | 8.35 s / 4.96 s |
| **S1** | 14 | consistent slow | 495 | 10,786 | 59.02 s / 97.06 s |
| **F2** | 17 | consistent fast | 490 | 11,341 | 8.48 s / 8.86 s |
| **S2** | 13 | consistent slow | 493 | 11,317 | 59.10 s / 93.34 s |
| **D1** | 4 | discordant | 489 | 10,188 | 112.61 s / 9.30 s |
| **D2** | 6 | discordant | 483 | 8,955 | 49.07 s / 7.87 s |

Pairs **1↔14** and **17↔13** are intentionally close in existing D0
sequence-shape measures while exhibiting radically different latency.

### Batch identity derivation (fail-closed)

Private corpus artifacts are not tracked in GitHub; numeric index alone is not
sufficient evidence.

At execution, **before the first provider/model call**:

1. reconstruct the exact frozen chunk set;
2. sort eligible jobs by `chunk_id`, matching the production pipeline;
3. partition consecutively at batch size 32;
4. derive batches 1, 14, 17, 13, 4, and 6;
5. compute ordered chunk-ID digest and `batch_identity_digest` for each;
6. write those identities into pre-execution evidence.

If child count, workload hashes, sorting contract, batch membership, or
reconstruction differs from the frozen D0 workload: **STOP before model
execution.**

### Repetition / order

One fresh D1-B process with one model load for the targeted campaign.
No per-cell model reload, cache clearing, `empty_cache()`, allocator
manipulation, artificial memory pressure, or precision change.

No unmeasured “warm-up” encode using any selected batch. Model loading may
occur normally; the first selected encode remains measured.

**6 measured encodes per selected batch**, arranged as counterbalanced pair
blocks (**36 targeted encode calls total**):

**Block P1 — shape-matched pair**

`1,14 → 14,1 → 1,14 → 14,1 → 1,14 → 14,1`

**Block P2 — shape-matched pair**

`17,13 → 13,17 → 17,13 → 13,17 → 17,13 → 13,17`

**Block P3 — discordant pair**

`4,6 → 6,4 → 4,6 → 6,4 → 4,6 → 6,4`

Pair order alternates to reduce monotonic time/thermal-order confounding.

---

## Required per-encode evidence

D1-A (every batch) and every D1-B encode must retain (no private text):

- exact batch identity / digest;
- item count;
- token distribution;
- padded-token workload and padding fraction;
- host encode wall;
- CUDA device elapsed;
- wall-minus-device gap;
- CPU user / system / total delta;
- voluntary / involuntary context-switch delta;
- allocated / reserved / peak CUDA memory;
- before / after external utilization;
- graphics / SM / memory clocks;
- temperature;
- power;
- P-state;
- throttle reasons;
- runtime / GPU / software identity.

Unavailable metrics remain explicit null/unavailable.

---

## Frozen analysis (cells fixed before results)

Report, without changing cells after seeing results:

- D1-A1 vs D1-A2 batch-rank correlation;
- comparison with both D0 runs where fields permit;
- wall vs CUDA-device correlation;
- wall−device residual distribution;
- latency relationship with max sequence length, aggregate tokens,
  padded-token workload, and padding fraction;
- fast-vs-slow paired comparison for 1↔14 and 17↔13;
- within-batch D1-B dispersion across six repetitions;
- behavior of discordant batches 4 and 6;
- associations with CPU/context switching, allocator state, clocks, power,
  temperature, P-state and throttle observations.

**No causal claim solely from correlation.**

---

## Validity / retry rule

A scientific result that is surprising, slow, fast, or inconvenient is **not**
grounds for rerun.

A cell may be replaced only for an execution-invalid condition such as tooling
failure, incomplete evidence, wrong workload identity, or process failure.
Preserve the invalid attempt and reason.

**No discretionary “one more run.”**

---

## D1 decision boundary

D1 does not need to discover an ultimate GPU root cause.

It is sufficient if the evidence establishes whether later D2 comparisons can
be made fairly and materially narrows attribution among:

- deterministic batch/content/shape effect;
- GPU/device execution;
- host/scheduling/synchronization;
- power/clock/thermal state;
- allocator/runtime state;
- unresolved mixture.

D1 itself does not promote or modify any production policy.

---

## Explicitly NOT AUTHORIZED under this freeze

D1-A execution · D1-B execution · D2 FP16 · D3 batch sweep · D4 attention ·
D5 persistence/Qdrant · threshold changes · production sync/cache policy ·
HTTP-500 reopen · 16K-E/F/G · main.

---

## Next gate

The successor SHA of this freeze becomes the exact parent for one bounded
D1-A → D1-B scientific execution AUTH.
