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
                  | Ollama                 |
                  | local generator model  |
                  | :11434                 |
                  +-----------^------------+
                              |
                    host.docker.internal
                              |
        +---------------------+---------------------+
        |          OFFLINERAG CONTAINER            |
        |                                           |
        | FastAPI + UI                              |
        | Docling                                   |
        | embeddings + reranker                     |
        | Qdrant Local                              |
        | LangGraph                                  |
        | evaluation harness                        |
        +---------------+---------------------------+
                        |
                 +------+-------+
                 |              |
               /data          /models
              writable        read-only
                         embed/rerank weights
```

## 4. Runtime filesystem contract

### `/data` — writable/persistent

Suggested layout:

```text
/data/
├── raw/
├── manifests/
├── processed/
├── qdrant/
├── eval/
├── traces/
└── logs/
```

### `/models` — retrieval models only

```text
/models/
├── embeddings/
└── reranker/
```

Generator weights belong to the external inference runtime and are not mounted into OfflineRAG.

## 5. Target quick start

These commands describe the intended release interface. Activate them once
Phase **15G** container packaging lands. Phases **15A/15B/15C/15D/15E/15F**
already provide the in-process FastAPI substrate, `/health*` probes,
`/v1/documents*`, `POST /v1/ingest`, `POST /v1/query`, `GET /v1/trace/{trace_id}`,
and admission/deadlines/drain; the application image remains later Slice 15 work.

### Host provisioning

```bash
ollama serve
ollama pull <approved-local-model>
```

Provision embedding/reranker weights into `./models` separately.

### macOS / Windows Docker Desktop

```bash
docker run --rm \
  -p 127.0.0.1:8080:8080 \
  -v "$(pwd)/data:/data" \
  -v "$(pwd)/models:/models:ro" \
  -e OFFLINE_RAG_STRICT_OFFLINE=true \
  -e OFFLINE_RAG_LLM_BASE_URL=http://host.docker.internal:11434/v1 \
  -e OFFLINE_RAG_LLM_MODEL=<approved-local-model> \
  -e OFFLINE_RAG_APPROVED_LLM_MODELS=<approved-local-model> \
  offline-rag:latest
```

### Linux

Add the host gateway explicitly:

```bash
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -p 127.0.0.1:8080:8080 \
  -v "$(pwd)/data:/data" \
  -v "$(pwd)/models:/models:ro" \
  -e OFFLINE_RAG_STRICT_OFFLINE=true \
  -e OFFLINE_RAG_LLM_BASE_URL=http://host.docker.internal:11434/v1 \
  -e OFFLINE_RAG_LLM_MODEL=<approved-local-model> \
  -e OFFLINE_RAG_APPROVED_LLM_MODELS=<approved-local-model> \
  offline-rag:latest
```

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
`/health/ready` fail.

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

Later UI work should still load when Ollama is stopped and show a clear
generation-unavailable state; that is separate from process `/health/ready`.

## 8. Scale-up profile

The application boundary remains unchanged when scaling:

```text
OfflineRAG container
    |
    +--> Qdrant server (optional)
    |
    +--> vLLM / llama.cpp server / Ollama
```

Do not introduce the server-backed topology until corpus scale or throughput benchmarks justify it.

## 9. Image strategy

Recommended release artifacts:

- `offline-rag:<version>-cpu` if retrieval models need CPU-only dependencies;
- `offline-rag:<version>-cuda` only if embedding/reranking GPU acceleration materially benefits the demo and packaging remains manageable.

The generator's GPU stack remains outside both images.

## 10. Portfolio phrasing

Use:

> Fully local/offline RAG with a single-container application and a model-agnostic local generation boundary. Ollama works out of the box; no cloud API is required.

Avoid:

> Everything runs in one container.

That would be inaccurate by design.
