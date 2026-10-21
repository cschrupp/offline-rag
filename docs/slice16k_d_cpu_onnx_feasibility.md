# 16K-D CPU-ONNX-01 — Same-Model ONNX Runtime CPU Feasibility

**Experiment:** `16K-D-CPU-ONNX-01`  
**Implementation authority:** `S16-K-D-POST-CPUOV-CPU-ONNX-FEASIBILITY-IMPLEMENTATION-AUTH-001`  
**Exact parent:** `e5af0a78f25696a720de79a02777ea3836351fb1`  
**Branch:** `implementation/16k-d-cpu-onnx-feasibility`  
**Work class:** HARNESS / FEASIBILITY IMPLEMENTATION ONLY  

**Status:** POST-CPU-OV CPU ONNX FEASIBILITY HARNESS IMPLEMENTATION (execution locked)  

**Predecessor:** CPU-OV-01 STOP after INT8 128-screen TOO_SLOW (~39.75 min projected)  
**Further scientific execution:** NOT AUTHORIZED (`EXECUTION_AUTHORIZED=False`)

---

## 1. Question

Can the exact pinned Qwen3-Embedding-0.6B run on CPU through native in-process
Sentence Transformers + ONNX Runtime (dynamic INT8 AVX2) fast enough to make
CPU fallback practical, without materially changing retrieval behavior?

## 2. Frozen contract

| Field | Value |
|-------|--------|
| Model | `Qwen/Qwen3-Embedding-0.6B` |
| Revision | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` |
| Dimension | 1024 |
| Normalize | true |
| Batch | 32 (frozen; no sweep) |
| Backend | Sentence Transformers `backend="onnx"` |
| Provider | `CPUExecutionProvider` |
| ORT threads | intra-op 8 / inter-op 1 |
| FP32 ONNX | provenance/source artifact only |
| Candidate | one dynamic INT8 AVX2 derivative |
| Chunk manifest SHA256 | `de4ad6b5ab661ba74e8ab2ec5344aa41518fc1dd0e9d94eb08edfbc3073076c3` |
| Screen digest | `9dfda07f0b0801eaa413c741450b48595e1d702c2bca728862b8e20848c64807` |
| Screen rule | ≤25 min projected → parity; >25 → STOP and move to llama.cpp |

No Docker / TEI. No tuning sweep. No O1/O2/O3 ONNX optimization variants.
No alternate embedding model. Identity uses Seneca `require_embedding_artifacts()`.

## 3. Stop-conditional ladder

1. **FP32 ONNX source materialization** — local ST ONNX export, complete ST
   artifact tree, provenance hashes, synthetic doc/query smoke.
2. **QINT8 AVX2 derivative** — from accepted FP32 ONNX tree only; ST/Optimum
   `export_dynamic_quantized_onnx_model(..., "avx2")`; no HF re-download;
   fail-closed `observed_ONNX_INT8_quantization` from graph/initializers/ops
   (never from `avx2` label or `_qint8` filename); candidate tree hashed;
   reload + synthetic smoke.
3. **One 128-child speed screen** — same population/digest as CPU-OV-01;
   encode wall / chunks/s / projected 1296 / RSS / CPU runtime; candidate hash
   before and after.
4. **Parity** — `d2-retrieval-parity-v1` interface implemented; **not executed**
   under AUTH-001.
5. **Full 1296** — interface scaffolded; **not implemented/executed** under AUTH-001.

## 4. Parity thresholds (reuse D2)

| Metric | Requirement |
|--------|-------------|
| Median document cosine | ≥ 0.999 |
| Minimum document cosine | ≥ 0.995 |
| Median query cosine | ≥ 0.999 |
| Minimum query cosine | ≥ 0.995 |
| Top-1 agreement | ≥ 15/16 |
| Mean Top-10 overlap | ≥ 0.95 |
| Minimum Top-10 overlap | ≥ 0.80 |

## 5. Implementation surface

| Path | Role |
|------|------|
| `src/offline_rag/dense/cpu_onnx_feasibility.py` | Frozen constants + fail-closed planner |
| `src/offline_rag/dense/cpu_onnx_harness.py` | Locked entrypoints + provenance gates |
| `src/offline_rag/dense/cpu_onnx_executor.py` | Real ST/ONNX export/quantize/encode/parity |
| `scripts/diag_16k_d_dense/run_cpu_onnx_feasibility.py` | CLI (plan / refuse execution) |
| `experiments/16k_d_cpu_onnx/` | Isolated uv env for ONNX deps (not production) |
| `tests/unit/dense/test_cpu_onnx_feasibility.py` | Ladder + identity regressions |

## 6. Explicitly NOT AUTHORIZED

ONNX scientific sample execution · 128-child screen · parity probe ·
1296-child confirmation · production routing · ONNX thread sweep · batch sweep ·
O1/O2/O3 experimentation · TEI · Docker · llama.cpp · alternate embedding models ·
main promotion.

## 7. Invariants

1. No Hub-model substitution.
2. No semantic-contract reinvention (plain-v1 doc text; production query contract;
   normalize; dim 1024).
3. Projected full-corpus minutes are never confirmation evidence.
4. Thresholds are frozen constants.
5. ONNX INT8 identity is fail-closed via `observed_ONNX_INT8_quantization`
   (graph/initializers/ops), never request label or filename.
6. Final ≤25-minute gate uses measured `full_wall_minutes` + exact 1296 counts
   (when a later AUTH unlocks full confirm).
