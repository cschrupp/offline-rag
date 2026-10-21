# 16K-D CPU-OV-01 — Same-Model OpenVINO CPU Feasibility

**Experiment:** `16K-D CPU-OV-01 — SAME-MODEL OPENVINO CPU FEASIBILITY`  
**Implementation authority:** `S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-AUTH-001` — AUTHORIZED  
**Exact parent:** `137bd65a9c0c11fd7989e9c72857730ba21e3191`  
**Branch:** `implementation/16k-d-cpu-openvino-feasibility`  
**Work class:** HARNESS / FEASIBILITY IMPLEMENTATION ONLY  

**Status:** POST-D2 CPU OPENVINO FEASIBILITY HARNESS IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT REVIEW  

**D2 predecessor:** CAMPAIGN COMPLETE / G1 SELECTED  
**Accepted D2 freeze tip (parent lineage):** `137bd65…`  
**Execution:** NOT AUTHORIZED under this AUTH  

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

No alternate embedding model is allowed.

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

1. **Stage 0 — export/compat gate** (local export, load, dim 1024, finite,
   normalize, doc+query paths, provenance, artifact hashes). Fail → STOP.
2. **Stage 1 — 128-child speed screen** (SHA256(chunk_id) ascending, first 128).
   Projection: `1296 / chunks_per_sec` minutes (screening only; not confirmation).
3. **Screen rules (OV-FP16):**
   - projected ≤15 min → skip INT8; proceed to parity then (later AUTH) full run;
   - 15–25 min → also screen OV-INT8; choose faster parity-passing candidate;
   - \>25 min → do not full-run FP16; open INT8 screen.
4. **Stage 2 — parity** reuses `d2-retrieval-parity-v1` (64 docs / 16 queries,
   same thresholds). Reference: CUDA/FP16/b32 (D2 G1 selected candidate).
   - OV-FP16 parity FAIL → STOP (do not open INT8).
   - OV-INT8 parity FAIL or projected \>25 → STOP.
5. **Stage 3 — select exactly one candidate.**
6. **Stage 4 — one full 1296 confirmation** — eligibility machinery only under
   this AUTH; actual full run NOT AUTHORIZED here.

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
| `src/offline_rag/dense/cpu_ov_harness.py` | Export/screen/parity/full-run entrypoints (locked) |
| `scripts/diag_16k_d_dense/run_cpu_ov_feasibility.py` | CLI (plan / refuse execution) |
| `experiments/16k_d_cpu_openvino/` | Isolated uv env for OV deps (not production) |
| `tests/unit/dense/test_cpu_ov_feasibility.py` | Ladder invariant regressions |

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
