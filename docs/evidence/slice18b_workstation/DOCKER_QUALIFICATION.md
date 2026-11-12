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
host model tree was not modified. Local generation used the user's existing
Windows Ollama service through `host.docker.internal:11434/v1`, with only
`qwen3.6:35b-a3b` approved. Hugging Face and Transformers offline flags were
set, and Seneca strict-offline mode remained enabled.

The following returned HTTP 200: `/health`, `/health/live`, `/health/ready`,
`/`, `/v1/settings/compute`, and `/v1/capabilities`.

Compute resolved `embedding.device=auto` to `cpu_onnx_fp32_v1`,
`onnx_fp32_v1`, `sentence_transformers_onnx`, `CPUExecutionProvider`, FP32,
1024 dimensions, with CUDA unavailable. After the product query, the embedding
runtime state was `READY`. The large-PDF runtime capability was reported
eligible.

One synthetic text source was admitted and published. Ingestion completed in
44.585 seconds with one parsed searchable document, one chunk, one generated
CPU embedding, and one lexical index entry. No ingestion errors were reported.

The bounded question asked for the museum opening days and hours. The local
Ollama answer matched the synthetic source and returned one citation. The
citation's `source_id` and `document_id` resolved to the active source, and the
query `snapshot_id` matched the workspace's `current_snapshot_id`.

The container was then removed and recreated from the same exact-candidate
image while retaining the named `/data` volume and read-only `/models` mount.
The active workspace, revision 2, source, document ID and snapshot remained
present without re-ingestion. The same question then returned an `answered`
result with the same source/document citation and snapshot. The post-replacement
query took 90.817 seconds; the first took 81.925 seconds. These are bounded
smoke timings, not a benchmark.

Before Windows Ollama was available, one separate attempt returned the safe
`generation_unavailable` response. It made no cloud call. That initial failure
is preserved as historical context; it was not counted as a successful query.

## Local model operations and limitations

Before the final exact-candidate rebuild, one standalone synthetic embedding
operation and one synthetic reranker score ran against the same production
runtime code and dependency graph, with model files mounted read-only and
network disabled. The embedding returned 1024 finite values and reached READY using
`cpu_onnx_fp32_v1` / `onnx_fp32_v1` / `CPUExecutionProvider` / FP32. The
reranker returned one finite raw score on CPU. No model download or external
service call occurred. These are functional smoke results, not parity or
throughput benchmarks. The exact-candidate product queries also exercised the
configured production retrieval path with reranking enabled.

No cloud generation endpoint was configured or called. The exact-candidate
product path completed ingestion, embedding, retrieval, reranking, local
generation, citation provenance checks, container replacement, and a
successful grounded query without re-ingestion.

**18B-R: PASS** for the bounded Docker runtime qualification scope. The
initial unavailable-Ollama attempt remains documented above and does not
replace or overwrite the successful evidence.

The host's original `models/` tree contains files not readable by UID 10001.
Qualification used a temporary container-readable copy mounted read-only;
the original tree was left unchanged. Deployment must provision model assets
with container-readable permissions.
