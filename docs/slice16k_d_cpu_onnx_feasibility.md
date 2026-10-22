# 16K-D CPU-ONNX-01 — Same-Model ONNX Runtime CPU Feasibility

**Experiment:** `16K-D-CPU-ONNX-01`  
**Implementation authority:** `S16-K-D-POST-CPUOV-CPU-ONNX-FEASIBILITY-IMPLEMENTATION-AUTH-001`  
**Rework authority:** `S16-K-D-POST-CPUOV-CPU-ONNX-FEASIBILITY-IMPLEMENTATION-REWORK-AUTH-001`  
**Exact parent:** `e5af0a78f25696a720de79a02777ea3836351fb1`  
**Rework parent:** `c17ac13ee05dec1c476455c29dc4600bfb2b1071`  
**Branch:** `implementation/16k-d-cpu-onnx-feasibility`  
**Work class:** HARNESS / FEASIBILITY IMPLEMENTATION ONLY  

**Status:** HARNESS IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED (IR-002 at `7d8efb6…`)  

**Stage 0A AUTH-001 (historical):** FAIL — export OK (`3e1b23a7…`); smoke FAIL
missing `position_ids`. Evidence:
`docs/evidence/16k_d_cpu_onnx/fp32_stage0_fail_1792627284.json`.

**POSITION_IDS COMPAT:** IR-001 ACCEPT at `f6c3c62…` (arange direct-forward;
immutable tree untouched).

**Stage 0A RETRY AUTH-001:** PASS — load existing `fp32_v1` + compat + synthetic
smoke; tree before=after=`3e1b23a7…`; dim 1024; finite; normalize; `raw-query-v1`.
Evidence: `docs/evidence/16k_d_cpu_onnx/fp32_stage0_retry_pass_1792628295.json`.

**Accepted FP32 Stage-0 source tree (F001 pin):**
`3e1b23a7293cf599bc34d1d9875e5c4ecde45bf12fcd300a6cb66794b5bc4345`

**Stage 0B QINT8 AUTH-001:** PASS — AVX2 dynamic QINT8 derivative from accepted
FP32 tree; source unchanged; `observed_ONNX_INT8_quantization.verified=true`
(u8 initializers=394); smoke PASS. Evidence:
`docs/evidence/16k_d_cpu_onnx/qint8_stage0_pass_1792629730.json`.

**Accepted QINT8 candidate tree (screen pin):**
`dd2a07f39f383ddd73ee163a082f1a92f846529264543894a5beaad30fcb8092`
(`exports/qint8_avx2_v1/`)

**QINT8 128-screen AUTH-001:** PASS / **TOO_SLOW** — ~0.607 chunks/s;
encode wall ~210.9 s; projected ~35.60 min (>25). Candidate tree unchanged
`dd2a07f3…`. Evidence:
`docs/evidence/16k_d_cpu_onnx/qint8_128_screen_too_slow_1792631554.json`.

**CPU-ONNX-01 scientific outcome (planner):** STOP after QINT8 screen TOO_SLOW —
planner parity / full confirmation remain closed. Next path was llama.cpp Q8_0.

**POST-QWENCPU ONNX↔GPU-FP16 parity AUTH-001:** FAIL — direct `execute_parity()`
(subject `49b9753…`); candidate tree `dd2a07f3…` immutable; reference CUDA+FP16
observed; D2 gates fail (median doc cos ~0.754 ≪ 0.999; Top1 16/16; mean Top10
0.70). Thresholds not loosened. Shared-index ONNX CPU architecture NOT selected.
Evidence: `docs/evidence/16k_d_cpu_onnx/onnx_qint8_gpu_fp16_parity_fail_1792636983.json`.

**Predecessor:** CPU-OV-01 STOP after INT8 128-screen TOO_SLOW (~39.75 min projected)  
**Still closed:** full 1296 ONNX · production backend routing · default promotion ·
main (`EXECUTION_AUTHORIZED=False` on planner).

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
   (`verified` requires INT8/UINT8 weight initializers; quantization ops are
   supporting evidence only), never request label or filename (F002).
6. QINT8 derivative requires the exact accepted FP32 Stage-0 tree SHA before
   copy/quantization (F001).
7. Screen requires the exact accepted QINT8 candidate tree SHA before encode and
   after encode (F003).
8. Final ≤25-minute gate uses measured `full_wall_minutes` + exact 1296 counts
   (when a later AUTH unlocks full confirm).
9. When the loaded ONNX graph requires `position_ids`, Seneca injects
   zero-based `arange(seq)` expanded to `[batch, seq]` (Qwen3 direct-forward);
   never `attention_mask.cumsum`; never mutate the immutable FP32 export tree.
