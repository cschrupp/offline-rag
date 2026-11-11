# Slice 18B Revision 2 — Docker Runtime Qualification

## Image and runtime

- Candidate source SHA: `ab1c11c57118668dd6ac44beb0a69e4ef5f5f522`.
- Image: `offline-rag:18b-qual`.
- Docker image ID: `sha256:b3f9571190db8ad13f6ebe598969e14d5130b54d0c643db9490ca6394edb1c0c`.
- Image size: `2,346,647,004` bytes.
- Runtime UID/GID: `10001:10001`.
- `/data`: writable named Docker volume; `/models`: read-only external bind.
- Image Python: `3.14.10`; Torch: `2.14.0+cpu`; CUDA build: `null`;
  CUDA available: `false`; installed `nvidia-*` distributions: `0`.
- `offline_rag` imports from `/app/.venv/lib/python3.14/site-packages`; `/app/src`
  and `uv` are absent; compiled `/app/ui/index.html` and the installed
  `/app/.venv/bin/offline-rag` CLI are present and usable.

## Exact-candidate HTTP checks

The final rebuilt image was run as UID 10001 with the approved CPU release
configuration, strict-offline flags, persistent data volume, and a read-only
temporary copy of the already-provisioned local model assets. The original
host model tree was not modified.

The following returned HTTP 200: `/health`, `/health/live`, `/health/ready`,
`/`, `/v1/settings/compute`, and `/v1/capabilities`.

Compute resolved `embedding.device=auto` to `cpu_onnx_fp32_v1`,
`onnx_fp32_v1`, `sentence_transformers_onnx`, `CPUExecutionProvider`, FP32,
1024 dimensions, with CUDA unavailable. The large-PDF runtime capability was
reported eligible. The post-startup embedding state was `UNLOADED`; runtime
smoke calls described below were performed before the exact-candidate rebuild
against the same production source/dependency/Docker inputs. This distinction
is retained because revision 2 changed packaging, tests and documentation,
not production application source or dependencies.

One synthetic source was admitted into a qualification workspace. The earlier
local query attempt returned the safe `generation_unavailable` response
because no Ollama service was listening at the configured local endpoint.
No cloud endpoint was called and no fallback was attempted. The source/workspace
metadata (revision 2, one active source) remained visible after replacing the
container while preserving `/data`. A successful grounded answer, citations,
and post-replacement usable query were not established.

## Local model operations and limitations

Before the final exact-candidate rebuild, one synthetic embedding operation
and one synthetic reranker score ran against the same production runtime code
and dependency graph, with model files mounted read-only and network disabled.
The embedding returned 1024 finite values and reached READY using
`cpu_onnx_fp32_v1` / `onnx_fp32_v1` / `CPUExecutionProvider` / FP32. The
reranker returned one finite raw score on CPU. No model download or external
service call occurred. These are functional smoke results, not parity or
throughput benchmarks.

The exact-candidate image was subsequently rebuilt and its CPU-only package,
API readiness, compute/capability responses and persisted workspace metadata
were verified. Because the required product generation/citation chain could
not complete without local Ollama, **18B-R remains PARTIAL, not PASS**.

The host's original `models/` tree contains files not readable by UID 10001.
Qualification used a temporary container-readable copy mounted read-only;
the original tree was left unchanged. Deployment must provision model assets
with container-readable permissions.
