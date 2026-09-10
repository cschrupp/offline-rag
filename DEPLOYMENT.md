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

These commands describe the intended release interface; activate them once Slice 15 is implemented.

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

`offline-rag doctor` currently reports (Slice 4):

```text
Docling / tokenizer / embedding artifact readiness
Corpus / Chunking / Dense index / Lexical index status (CURRENT | STALE | …)
Configured paths writable (including lexical-indexes)
Strict-offline compatibility checks
```

Generation endpoint reachability remains future work until Slice 8+.

Eventual fuller report:

```text
OfflineRAG readiness
--------------------
Data directory writable          PASS
Retrieval model files present    PASS
Qdrant Local writable            PASS
Generation endpoint approved     PASS
Generation endpoint reachable    PASS
Generation model approved        PASS
Cloud API keys configured        NONE
Remote tracing enabled           NO
Strict offline                   PASS
```

`/health` should distinguish application liveness from generation readiness. The UI should still load when Ollama is stopped and show a clear generation-unavailable state.

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
