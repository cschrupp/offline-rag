# 16K-D CPU-GGUF-01 — Same-Model llama.cpp Q8_0 CPU Feasibility

**Experiment:** `16K-D-CPU-GGUF-01`  
**Implementation authority:** `S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-AUTH-001`  
**Exact parent:** `5fca0844878b1c73ce23e75a7dee9023b4730a9f`  
**Branch:** `implementation/16k-d-cpu-gguf-feasibility`  
**Work class:** HARNESS / FEASIBILITY IMPLEMENTATION ONLY  

**Status:** HARNESS IMPLEMENTATION CANDIDATE (awaiting independent review)  

**Predecessor:** CPU-ONNX-01 CLOSED / INSUFFICIENT PERFORMANCE after QINT8
128-screen TOO_SLOW (~35.60 min projected; required ≤25).  

**Scientific execution:** NOT AUTHORIZED (`EXECUTION_AUTHORIZED=False`).  
No GGUF download, llama-server startup, synthetic embedding, 128 screen,
parity, or full 1296 under this authority.

---

## 1. Question

Can the official Qwen3-Embedding-0.6B Q8_0 GGUF run on CPU through local
llama-server (`--embeddings`, `--pooling last`, `--n-gpu-layers 0`) fast enough
to make CPU fallback practical, without materially changing retrieval behavior?

## 2. Frozen contract

| Field | Value |
|-------|--------|
| GGUF repo | `Qwen/Qwen3-Embedding-0.6B-GGUF` |
| GGUF revision | `71a379860247873620c83349673f4bcbdbc24922` |
| GGUF file | `Qwen3-Embedding-0.6B-Q8_0.gguf` |
| GGUF SHA256 | `a0e820fb3f8f448d3582862f9161bfaf58a63f89b46353f061e017597655821c` |
| Dimension | 1024 |
| Normalize | true (application + llama.cpp pooled Euclidean) |
| Batch | 32 application request groups |
| Backend | local `llama-server` subprocess (not Docker / not Ollama) |
| Pooling | `last` |
| GPU layers | `0` (CPU only; fail-closed) |
| Threads | `--threads 8` / `--threads-batch 8` |
| Query text | `raw-query-v1` |
| Chunk manifest SHA256 | `de4ad6b5ab661ba74e8ab2ec5344aa41518fc1dd0e9d94eb08edfbc3073076c3` |
| Screen digest | `9dfda07f0b0801eaa413c741450b48595e1d702c2bca728862b8e20848c64807` |
| Screen rule | ≤25 min projected → parity; >25 → STOP → model-change territory |

No Hub download during scientific execution. llama-server binary is externally
supplied and recorded (path, SHA256, `--version`, arch, command line).  
Batch/ubatch remain runtime defaults (not frozen to Qwen example `-ub 8192`).  
No Seneca ONNX `position_ids` patch — llama.cpp owns token positions.

## 3. Stop-conditional ladder

1. **Stage-0 artifact/runtime compat** — exact GGUF SHA; llama-server identity;
   CPU-only startup; load Q8_0; ready; synthetic doc/query; 1024-d finite
   normalized; pooling=last; clean shutdown. No corpus screen.
2. **One 128-child speed screen** — same population/digest as OV/ONNX; model
   loaded before timer; four 32-input `/v1/embeddings` requests inside timing;
   no warm-up; encode wall / chunks/s / projected 1296.
3. **Parity** — `d2-retrieval-parity-v1` interface implemented; **not executed**
   under AUTH-001. Q8_0 is not assumed to share CUDA FP16 vector space.
4. **Full 1296** — interface scaffolded; **not implemented/executed** under AUTH-001.

## 4. Parity thresholds (reuse D2; locked)

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
| `src/offline_rag/dense/cpu_gguf_feasibility.py` | Frozen constants + fail-closed planner |
| `src/offline_rag/dense/cpu_gguf_client.py` | `/v1/embeddings` HTTP client (httpx) |
| `src/offline_rag/dense/cpu_gguf_server.py` | Local llama-server subprocess manager |
| `src/offline_rag/dense/cpu_gguf_harness.py` | Locked entrypoints + provenance preflight |
| `src/offline_rag/dense/cpu_gguf_executor.py` | Real Stage-0 / screen / parity (unlocked only) |
| `scripts/diag_16k_d_dense/run_cpu_gguf_feasibility.py` | CLI (plan / refuse execution) |
| `tests/unit/dense/test_cpu_gguf_feasibility.py` | Ladder + lock regressions |

## 6. Explicitly NOT AUTHORIZED

GGUF scientific download · llama-server scientific startup · synthetic embedding ·
128 screen · parity · full 1296 · Q5/Q6/Q4 · thread sweep · batch/ubatch sweep ·
GPU offload · Docker · Ollama · production routing · alternate embedding model ·
main promotion.

## 7. Prior CPU path projections (context)

| Runtime | 1296 projection |
|---------|-----------------|
| OpenVINO FP16 | ~47.1 min |
| OpenVINO INT8 | ~39.75 min |
| ONNX QINT8 AVX2 | ~35.60 min |
| Required | ≤25 min |
