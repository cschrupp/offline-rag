# Deployment Guide

## 1. Deployment decision

The flagship portfolio profile is:

> **One OfflineRAG application container + one external local generation runtime.**

Ollama on the host is the default generation runtime. The application communicates through a project-owned OpenAI-compatible client. llama.cpp server, vLLM, or another explicitly approved local compatible endpoint can replace Ollama without changing retrieval code.

## 2. Why the generator is not in the container

Keeping generation outside the application image:

- avoids distributing large generator weights;
- avoids coupling OfflineRAG to one GPU/inference runtime;
- reduces image size and CUDA packaging complexity;
- makes model changes independent from application releases;
- keeps the portfolio focus on document intelligence, retrieval, evaluation, and guardrails;
- makes a future workstation -> GPU-server migration configuration-only.

This does **not** weaken the offline claim when the inference endpoint and model are local and approved.

## 3. Standalone topology

```text
                              HOST

                  +------------------------+
                  | Ollama (or approved    |
                  | local OpenAI-compat    |
                  | endpoint) :11434       |
                  +-----------^------------+
                              |
                    host.docker.internal
                              |
        +---------------------+---------------------+
        |          OFFLINERAG CONTAINER            |
        |                                           |
        | FastAPI (one ASGI worker)                 |
        | Docling / embeddings / reranker           |
        | Qdrant client with Local-mode persistence |
        | product /v1/* + /health*                  |
        +---------------+---------------------------+
                        |
                 +------+-------+
                 |              |
               /data          /models
              writable        read-only
                         provisioned non-generator
                         assets (no LLM weights)
```

Supported topology notes:

- **Qdrant client with Local-mode persistence** under `/data/qdrant` (not an
  embedded Qdrant server process, and not a Compose Qdrant service).
- **One process / one ASGI worker** only in the supported profile.
- Slice 15 has **no application authentication or TLS**.
- Deferred portfolio work (retrieval inspector, citation viewer, evaluation
  dashboard, optional future orchestration adapters) is **not** part of this
  packaging profile.

## 4. Runtime filesystem contract

### `/data` — writable / persistent product state

`OFFLINE_RAG_DATA_DIR=/data` rebases the accepted durable path model to:

```text
/data/
├── raw/
├── manifests/
├── processed/
├── corpora/
├── chunks/
├── chunk-manifests/
├── embeddings/
├── index-manifests/
├── lexical-indexes/
├── lexical-index-manifests/
├── qdrant/
├── traces/
├── staging/
├── locks/
├── logs/
└── eval/
    └── results/
```

Startup (`ApplicationRuntime`) owns creation of required directories. `doctor`
is read-only and must not mutate `/data`.

**Linux bind-mount ownership:** the container runs as UID/GID `10001:10001`.
The host `./data` directory (or volume) must be writable by UID `10001`, or an
equivalent supported volume arrangement must be used. Example:

```bash
mkdir -p data models
sudo chown -R 10001:10001 data
```

### `/models` — external provisioned non-generator assets

`/models` is external, pre-provisioned, reproducible, normally mounted
read-only, and is **not** durable corpus state. Expected categories:

```text
/models/
├── docling/
├── tokenizers/
│   └── tiktoken/
├── embeddings/
└── rerankers/
```

Do **not** bundle these weights into the application image. Do **not** enable
runtime Hugging Face / model download fallbacks. Missing required assets keep
the accepted fail-closed readiness behavior (`/health/ready` → `503`).

Generator weights remain entirely outside `/models` and outside the app image.

## 5. Supported quick start (Slice 15G packaging)

### Build the application image

From the repository root:

```bash
docker build -f deploy/Dockerfile -t offline-rag:latest .
```

The build context excludes `.git`, `.env`, `data/`, `models/`, and other local
artifacts via `.dockerignore`. Local provisioned weights and private `/data`
content must not enter the build context.

### Compose (recommended)

Provision host generator + models, then:

```bash
# Host generator (example: Ollama)
ollama serve
ollama pull <approved-local-model>

export OFFLINE_RAG_LLM_MODEL=<approved-local-model>
export OFFLINE_RAG_APPROVED_LLM_MODELS=<approved-local-model>

# Linux: ensure ./data is writable by UID 10001
mkdir -p data models
# sudo chown -R 10001:10001 data   # when using a bind mount on Linux

docker compose -f deploy/docker-compose.example.yml up --build
```

Compose profile summary:

| Item | Value |
|---|---|
| Service | `offline-rag` only |
| Host publish | `127.0.0.1:8080:8080` (loopback only) |
| Container bind | `0.0.0.0:8080` with `OFFLINE_RAG_ALLOW_NON_LOOPBACK=true` |
| Host generator bridge | `host.docker.internal:host-gateway` |
| Mounts | `../data:/data` (rw), `../models:/models:ro` |
| App shutdown grace | `OFFLINE_RAG_SHUTDOWN_GRACE_SECONDS=30` |
| Compose stop grace | `stop_grace_period: 45s` (accommodates app drain) |
| Workers / replicas | single process, single worker; no replica count |

**Warning:** changing the published port mapping to `8080:8080` or
`0.0.0.0:8080:8080` exposes an **unauthenticated** Slice-15 service to the
network. The application cannot enforce Docker host-port overrides. Do not add
app auth/TLS as a packaging workaround in Slice 15.

### Direct `docker run`

#### macOS / Windows Docker Desktop

```bash
docker run --rm \
  -p 127.0.0.1:8080:8080 \
  -v "$(pwd)/data:/data" \
  -v "$(pwd)/models:/models:ro" \
  -e OFFLINE_RAG_CONFIG=/app/config/base.yaml \
  -e OFFLINE_RAG_DATA_DIR=/data \
  -e OFFLINE_RAG_MODELS_DIR=/models \
  -e OFFLINE_RAG_STRICT_OFFLINE=true \
  -e OFFLINE_RAG_HTTP_HOST=0.0.0.0 \
  -e OFFLINE_RAG_HTTP_PORT=8080 \
  -e OFFLINE_RAG_ALLOW_NON_LOOPBACK=true \
  -e OFFLINE_RAG_SHUTDOWN_GRACE_SECONDS=30 \
  -e HF_HUB_OFFLINE=1 \
  -e TRANSFORMERS_OFFLINE=1 \
  -e OFFLINE_RAG_LLM_BASE_URL=http://host.docker.internal:11434/v1 \
  -e OFFLINE_RAG_LLM_MODEL=<approved-local-model> \
  -e OFFLINE_RAG_APPROVED_LLM_MODELS=<approved-local-model> \
  -e OFFLINE_RAG_APPROVED_LLM_ENDPOINTS=http://host.docker.internal:11434/v1 \
  offline-rag:latest
```

#### Linux

Add the host gateway explicitly:

```bash
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -p 127.0.0.1:8080:8080 \
  -v "$(pwd)/data:/data" \
  -v "$(pwd)/models:/models:ro" \
  -e OFFLINE_RAG_CONFIG=/app/config/base.yaml \
  -e OFFLINE_RAG_DATA_DIR=/data \
  -e OFFLINE_RAG_MODELS_DIR=/models \
  -e OFFLINE_RAG_STRICT_OFFLINE=true \
  -e OFFLINE_RAG_HTTP_HOST=0.0.0.0 \
  -e OFFLINE_RAG_HTTP_PORT=8080 \
  -e OFFLINE_RAG_ALLOW_NON_LOOPBACK=true \
  -e OFFLINE_RAG_SHUTDOWN_GRACE_SECONDS=30 \
  -e HF_HUB_OFFLINE=1 \
  -e TRANSFORMERS_OFFLINE=1 \
  -e OFFLINE_RAG_LLM_BASE_URL=http://host.docker.internal:11434/v1 \
  -e OFFLINE_RAG_LLM_MODEL=<approved-local-model> \
  -e OFFLINE_RAG_APPROVED_LLM_MODELS=<approved-local-model> \
  -e OFFLINE_RAG_APPROVED_LLM_ENDPOINTS=http://host.docker.internal:11434/v1 \
  offline-rag:latest
```

Optional generator API keys may be passed from the host environment
(`OFFLINE_RAG_LLM_API_KEY`) but must never be baked into the image.

### Direct-host process (non-container)

Default bind remains loopback:

```bash
python -m offline_rag.api.server
# listens on 127.0.0.1:8080
```

Non-loopback binds (`0.0.0.0`, `::`, LAN addresses) fail closed unless
`OFFLINE_RAG_ALLOW_NON_LOOPBACK=true`. Policy is enforced before the listener
starts (startup/configuration failure, not a product HTTP error).

## 6. Strict-offline contract

Strict offline means the complete workload can run without internet/cloud services after provisioning. It does not mean every process is inside one container.

At runtime OfflineRAG should:

1. require the generation base URL to match an approved local endpoint;
2. require the model identifier to match an approved local-model manifest/list;
3. load embedding/reranker assets locally only;
4. disable cloud judge/tracing/embedding fallbacks;
5. avoid runtime package/model downloads;
6. expose a `doctor` command that reports the complete offline readiness state.

For the strongest verification, run the demo on a machine with internet disconnected or outbound egress blocked while allowing container-to-host communication.

## 7. Health/readiness checks

### HTTP probes (landed in Slice 15B)

Process health is served by the FastAPI app:

| Endpoint | Meaning | Success | Failure |
|---|---|---|---|
| `GET /health` | Liveness alias | `200 {"status":"live"}` | process down |
| `GET /health/live` | Cheap process liveness | `200 {"status":"live"}` | process down |
| `GET /health/ready` | Cached runtime readiness | `200 {"status":"ready"}` | `503 runtime_not_ready` |

`/health/ready` reads startup-established process state only. It must not load
models, probe the generator, hash artifacts, rebuild Qdrant, or scan corpus
readiness. An approved but unreachable generator does **not** by itself make
`/health/ready` fail. Deliberately absent `/models` assets may correctly keep
readiness at `503`; do not download assets merely to force a green ready probe.

### Doctor (diagnostic / non-mutating)

`offline-rag doctor` remains the deep offline diagnostic. As of Slice **15B** it
is strictly read-only: no `mkdir`, write probes, downloads, provisioning,
repair, rebuild, or publish. Missing required directories are reported `ABSENT`;
writability uses permission inspection only. Startup—not doctor—creates required
`/data` trees.

Doctor currently reports:

```text
Docling / tokenizer / embedding / reranker artifact readiness
Corpus / Chunking / Dense / Lexical / Hybrid / Hybrid-rerank / Context status
Generation status (READY | NOT_READY) + approved endpoint/model probe
Configured paths present / inspection-only writability (incl. traces/staging/locks)
Strict-offline compatibility checks
```

Generation readiness (doctor/query path) requires Context READY,
`generation.enabled`, approved endpoint/model allowlists, a constructible
OpenAI-compatible adapter, and a successful non-generative `/models` probe that
lists the selected model. Doctor never pulls models or sends completions.

## 8. Scale-up profile

The application boundary remains unchanged when scaling:

```text
OfflineRAG container
    |
    +--> Qdrant server (optional; not the Slice 15 supported profile)
    |
    +--> vLLM / llama.cpp server / Ollama
```

Do not introduce the server-backed topology until corpus scale or throughput benchmarks justify it. Multi-worker and multi-replica topologies are unsupported in Slice 15.

## 9. Image strategy

Recommended release artifacts:

- `offline-rag:<version>` application image built from `deploy/Dockerfile`
  (Python 3.14, non-root `10001:10001`, no generator weights).

The generator's GPU stack remains outside the application image.

**Technical debt (not a Slice 15G acceptance blocker):** the current application
image is large (~10.3 GB) because the Python ML dependency graph may pull
CUDA-capable PyTorch artifacts. The image is not bloated by bundled model
weights or `/data` (the architectural requirement). After Slice 15 acceptance,
investigate multi-stage builds plus CPU/CUDA image variants. See
[`docs/container_image_optimization.md`](docs/container_image_optimization.md)
and GitHub issue
[#1](https://github.com/cschrupp/offline-rag/issues/1).
Do not change the dependency architecture as an unreviewed packaging fix.

## 10. Portfolio phrasing

Use:

> Fully local/offline RAG with a single-container application and a model-agnostic local generation boundary. Ollama works out of the box; no cloud API is required.

Avoid:

> Everything runs in one container.

That would be inaccurate by design.
