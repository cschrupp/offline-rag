# 16K-D CPU-OV-01 — Same-Model OpenVINO CPU Feasibility

**Experiment:** `16K-D CPU-OV-01 — SAME-MODEL OPENVINO CPU FEASIBILITY`  
**Implementation authority:** `S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-AUTH-001`  
**Rework5 authority:** `S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-REWORK5-AUTH-001` — AUTHORIZED  
**Exact rework5 parent:** `b267542bdebc1c6ef0de3b7d9e1bcdfbdaa45912`  
**Accepted harness subject (IR-005):** `f9bed0af0d2fa045690c8050ba8f585fc8a0165f`  
**Underlying implementation base:** `eea4c976a351fbb41d1cd3efc1337198813c2e22`  
**Branch:** `implementation/16k-d-cpu-openvino-feasibility`  
**Work class:** HARNESS / FEASIBILITY IMPLEMENTATION REWORK5 (F010 INT8 identity)  

**Status:** POST-D2 CPU OPENVINO FEASIBILITY HARNESS IMPLEMENTATION REWORK5 COMPLETE / READY FOR INDEPENDENT RE-REVIEW  

**Accepted implementation subject (IR-004):** `769116132ed91543732db9f80503e539fb66b234`  
**Follow-up tip (OVConfig/ST integration fix):** `22ef4994cef2d55d618c8a260f241e62a05de5e7`  
**Evidence tip (AUTH-001 FAIL record):** `0a6900345b7d66a5213fe20700e84a418232e2cd`  

**Stage-0 (historical):** PASS under `…-STAGE0-EXECUTION-AUTH-001` at `eea4c97…`  
**Stage-0 IR storage (inspected):** FP32 — compatibility PASS stands; not OV-FP16 storage  
**Historical Stage-0 export tree:** `7e48d6d9f9b839c4dee427340857e239c33258ee80b3cf2bb9df1476569e1e00`  
**FP16 materialization at 7691161:** FAIL (`TypeError`: ST `ov_config` rejects `OVConfig` object) — evidence recorded  
**FP16 ST re-export AUTH-002:** ABORTED / ENVIRONMENTAL (SIGBUS on fresh ST save)  
**FP16 lowmem AUTH-001:** ABORTED / IMPLEMENTATION EXECUTION DEFECT — F009 — not a scientific FAIL  
**F009:** CLOSED (IR-005)  
**FP16 lowmem AUTH-002:** PASS — IR-001 ACCEPT — candidate tree `c1ebe0b8435ce8d32526875822f933f5f96999d7c44d13698c0b6b8a91d3f252` (`exports/fp16_lowmem_v2`; IR=fp16; observed CPU inference=fp32)  
**FP16 128-screen AUTH-001:** PASS / **TOO_SLOW** — IR-001 ACCEPT — ~0.459 chunks/s; projected ~47.1 min (>25); FP16 parity/full CLOSED; INT8 preparation OPEN  
**Candidate description:** OpenVINO CPU / FP16 IR storage / observed CPU inference precision FP32  
**D2 predecessor:** CAMPAIGN COMPLETE / G1 SELECTED  
**Further execution:** NOT AUTHORIZED (INT8 materialization/screen / parity / full / production / main closed; `EXECUTION_AUTHORIZED=False`)  

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
| F008 precision identity | Separate requested / observed IR / observed CPU inference; FP16 via post-export `compress_to_fp16`; no label-derived dtype |
| F009 unsafe in-place IR compress | CLOSED (IR-005): distinct same-FS temp IR → validate non-zero + fp16 → replace; never `save_model` onto the source path |
| F010 INT8 identity not fail-closed | `observed_INT8_weight_compression` from i8/u8 Constant evidence + NNCF `INT8_ASYM` provenance; refuse fp16/fp32 IR when requested=int8; derivative no-retrace materialization path |
