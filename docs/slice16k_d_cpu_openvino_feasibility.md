# 16K-D CPU-OV-01 — Same-Model OpenVINO CPU Feasibility

**Experiment:** `16K-D CPU-OV-01 — SAME-MODEL OPENVINO CPU FEASIBILITY`  
**Implementation authority:** `S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-AUTH-001`  
**Rework2 authority:** `S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-REWORK2-AUTH-002` — AUTHORIZED  
**Exact rework2 parent:** `50906c4665a3d1d73fe9693207bcf1a0d82a65d5` (Stage-0 evidence tip)  
**Underlying implementation base:** `eea4c976a351fbb41d1cd3efc1337198813c2e22`  
**Branch:** `implementation/16k-d-cpu-openvino-feasibility`  
**Work class:** HARNESS / FEASIBILITY IMPLEMENTATION REWORK2  

**Status:** POST-D2 CPU OPENVINO FEASIBILITY HARNESS IMPLEMENTATION REWORK2 COMPLETE / READY FOR INDEPENDENT RE-REVIEW  

**Stage-0 execution:** PASS under `…-STAGE0-EXECUTION-AUTH-001` at `eea4c97…`  
**D2 predecessor:** CAMPAIGN COMPLETE / G1 SELECTED  
**Further execution:** NOT AUTHORIZED (`EXECUTION_AUTHORIZED=False`; no screen/parity/full)  

---

## 1. Question

Can the exact pinned Qwen3-Embedding-0.6B run on CPU through OpenVINO fast enough
to make CPU fallback practical, without materially changing retrieval behavior?

## 2. Frozen model identity

| Field | Value |
|-------|--------|
| Model | `Qwen/Qwen3-Embedding-0.6B` |
| Revision | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` |
| Dimension | 1024 |
| Normalize | true |
| Batch | 32 (frozen; no sweep) |
| Chunk manifest SHA256 | `de4ad6b5ab661ba74e8ab2ec5344aa41518fc1dd0e9d94eb08edfbc3073076c3` |

No alternate embedding model is allowed. Identity uses Seneca
`require_embedding_artifacts()` (fail closed).

## 3. Candidates

| ID | Backend | Device | Weights |
|----|---------|--------|---------|
| OV-FP16 | Sentence Transformers `backend="openvino"` | CPU | FP16 |
| OV-INT8 | same | CPU | INT8 (conditional) |

Export/load must originate from Seneca's locally provisioned pinned checkpoint.
Hub substitution / silent re-download fails closed.

Pooling/normalization must use Sentence Transformers' OpenVINO path (not raw
OpenVINO token-embedding export alone).

## 4. Stop-conditional ladder

1. **Stage 0 — export/compat gate (FP16 only)** — local export, load, dim 1024,
   finite, normalize, doc+query paths, provenance, artifact hashes. Fail → STOP.
   INT8 export is **not** Stage 0.
2. **Stage 1 — 128-child speed screen** (SHA256(chunk_id) ascending, first 128).
   Projection: `1296 / chunks_per_sec` minutes (screening only; not confirmation).
3. **Screen rules (OV-FP16):**
   - projected ≤15 min → skip INT8; proceed to parity then (later AUTH) full run;
   - 15–25 min → also prepare OV-INT8 (`export_int8` then screen); choose faster
     parity-passing candidate;
   - \>25 min → do not full-run FP16; open `export_int8` then INT8 screen.
4. **Conditional INT8 preparation** — `export_int8` only after the planner opens
   INT8 eligibility (never at Stage 0).
5. **Parity** reuses `d2-retrieval-parity-v1` (64 docs / 16 queries, same
   thresholds). Reference: CUDA/FP16/b32 (D2 G1 selected candidate).
   - OV-FP16 parity FAIL → STOP (do not open INT8).
   - OV-INT8 parity FAIL or projected \>25 → STOP.
6. **Select exactly one candidate.**
7. **Full 1296 confirmation** — measured wall ≤25 min (`FEASIBLE_MAX_MIN`) with
   generated=1296, reused=0, failed=0, vectors=1296, dimension=1024. Screen
   projections never satisfy this gate. Actual full run NOT AUTHORIZED here.

## 5. Parity thresholds (reuse D2)

| Metric | Requirement |
|--------|-------------|
| Median document cosine | ≥ 0.999 |
| Minimum document cosine | ≥ 0.995 |
| Median query cosine | ≥ 0.999 |
| Minimum query cosine | ≥ 0.995 |
| Top-1 agreement | ≥ 15/16 |
| Mean Top-10 overlap | ≥ 0.95 |
| Minimum Top-10 overlap | ≥ 0.80 |

## 6. Implementation surface

| Path | Role |
|------|------|
| `src/offline_rag/dense/cpu_ov_feasibility.py` | Frozen constants + fail-closed planner |
| `src/offline_rag/dense/cpu_ov_harness.py` | Locked entrypoints + provenance gates |
| `src/offline_rag/dense/cpu_ov_executor.py` | Real ST/OpenVINO export/encode/parity/full |
| `scripts/diag_16k_d_dense/run_cpu_ov_feasibility.py` | CLI (plan / refuse execution) |
| `experiments/16k_d_cpu_openvino/` | Isolated uv env for OV deps (not production) |
| `tests/unit/dense/test_cpu_ov_feasibility.py` | Ladder + F001–F004 regressions |

## 7. Explicitly NOT AUTHORIZED

OpenVINO scientific sample execution · 128-child screen · parity probe ·
1296-child confirmation · production `make_embedder()` routing · runtime auto
selection · default changes · alternate models · ONNX · llama.cpp · CPU thread
tuning · batch sweep · production dependency promotion · main.

## 8. Invariants

1. No Hub-model substitution.
2. No semantic-contract reinvention (plain-v1 doc text; production query contract;
   normalize; dim 1024).
3. Projected full-corpus minutes are never treated as confirmation evidence.
4. Thresholds are frozen constants (no post-hoc adjustment API).
5. Stage-0 is FP16-only; INT8 conversion requires planner eligibility.
6. Final ≤25-minute gate uses measured `full_wall_minutes` + exact 1296 counts.

## 9. Rework findings closed (IR-001 / IR-002)

| Finding | Closure |
|---------|---------|
| F001 stub executor | `cpu_ov_executor.py` implements export/load/encode/parity/full; harness unlocks into it |
| F002 weak provenance | `require_embedding_artifacts` + manifest SHA256 `de4ad6b5…` |
| F003 unused ≤25 gate | `full_confirm_passes()` wired into `plan_next` |
| F004 INT8 at Stage 0 | Stage-0 FP16-only; conditional `export_int8` stage |
| F005 CLI missing export-dir | `--export-dir` required/passed for screen/parity/full-confirm |
| F006 encode-only full confirm | `execute_full_confirm` uses isolated `run_indexing` + OV embedder inject |
| F007 missing CPU host facts | `capture_cpu_host_runtime_facts()` on screen/full evidence |
