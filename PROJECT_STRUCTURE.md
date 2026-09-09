# Project Structure

The project is organized around explicit domain boundaries. Framework-specific integrations live behind project-owned interfaces so that Docling, Qdrant, LangGraph, Ollama, or any other dependency can be replaced without rewriting the application core.

## Intended repository tree

```text
offline-rag/
├── README.md
├── project_description.md
├── detailed_implementation_slices.md
├── PROJECT_STRUCTURE.md
├── ARCHITECTURE_DECISIONS.md
├── EVALUATION_HARNESS.md
├── SECURITY_MODEL.md
├── DEVELOPMENT_GUIDE.md
├── ROADMAP.md
├── PORTFOLIO_DEMO.md
├── .env.example
├── .gitignore
├── pyproject.toml                 # create during Slice 0
├── DEPLOYMENT.md
├── deploy/
│   ├── Dockerfile.template
│   └── docker-compose.example.yml
│
├── config/
│   ├── base.yaml
│   ├── deployment/
│   │   ├── standalone_ollama.yaml
│   │   └── external_openai_compatible.yaml
│   └── experiments/
│       ├── dense_baseline.yaml
│       ├── bm25_baseline.yaml
│       ├── hybrid_rrf.yaml
│       ├── hybrid_rerank.yaml
│       └── agentic_recovery.yaml
│
├── data/                          # ignored except README/placeholders
│   ├── raw/
│   ├── manifests/
│   ├── processed/
│   └── qdrant/
│
├── models/                        # ignored; embedding/reranker assets only
│   ├── README.md
│   └── manifest.example.yaml
│
├── eval/
│   ├── README.md
│   ├── datasets/
│   │   ├── gold.example.jsonl
│   │   ├── negative.example.jsonl
│   │   └── adversarial.example.jsonl
│   ├── baselines/
│   ├── results/
│   └── reports/
│
├── src/
│   └── offline_rag/
│       ├── __init__.py
│       ├── cli.py
│       ├── settings.py
│       │
│       ├── domain/
│       │   ├── documents.py
│       │   ├── retrieval.py
│       │   ├── generation.py
│       │   ├── evaluation.py
│       │   └── traces.py
│       │
│       ├── ingestion/
│       │   ├── base.py
│       │   ├── docling_parser.py
│       │   ├── normalizer.py
│       │   ├── chunker.py
│       │   ├── ids.py
│       │   └── pipeline.py
│       │
│       ├── embeddings/
│       │   ├── base.py
│       │   ├── local_dense.py
│       │   └── registry.py
│       │
│       ├── index/
│       │   ├── qdrant_store.py
│       │   ├── corpus_manifest.py
│       │   └── migrations.py
│       │
│       ├── retrieval/
│       │   ├── dense.py
│       │   ├── bm25.py
│       │   ├── fusion.py
│       │   ├── reranker.py
│       │   ├── context.py
│       │   ├── confidence.py
│       │   └── service.py
│       │
│       ├── generation/
│       │   ├── base.py
│       │   ├── openai_compatible.py
│       │   ├── preflight.py
│       │   ├── prompts.py
│       │   ├── answer_schema.py
│       │   └── citations.py
│       │
│       ├── agents/
│       │   ├── state.py
│       │   ├── query_rewrite.py
│       │   ├── evidence_grade.py
│       │   └── retrieval_graph.py
│       │
│       ├── guardrails/
│       │   ├── document_boundary.py
│       │   ├── injection.py
│       │   ├── tool_policy.py
│       │   ├── citation_policy.py
│       │   └── offline_policy.py
│       │
│       ├── evaluation/
│       │   ├── dataset.py
│       │   ├── runner.py
│       │   ├── experiment.py
│       │   ├── compare.py
│       │   ├── metrics/
│       │   │   ├── retrieval.py
│       │   │   ├── generation.py
│       │   │   ├── citation.py
│       │   │   ├── abstention.py
│       │   │   ├── security.py
│       │   │   └── performance.py
│       │   └── judges/
│       │       ├── base.py
│       │       └── local_llm.py
│       │
│       ├── observability/
│       │   ├── logging.py
│       │   ├── timing.py
│       │   ├── resources.py
│       │   └── trace_store.py
│       │
│       └── api/
│           ├── app.py
│           ├── dependencies.py
│           └── routes/
│               ├── health.py
│               ├── documents.py
│               ├── query.py
│               ├── traces.py
│               └── evaluation.py
│
├── ui/                            # optional web client after core pipeline
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   ├── security/
│   └── fixtures/
│
├── scripts/
│   ├── README.md
│   └── benchmark_machine.py
│
└── docs/
    ├── benchmark_methodology.md
    ├── dataset_guidelines.md
    ├── trace_schema.md
    ├── known_limitations.md
    ├── offline_runtime_contract.md
    └── model_provisioning.md
```

## Boundary rules

### `domain/`

Contains project-owned schemas and value objects. It should not import Docling, Qdrant, LangGraph, FastAPI, or a specific inference backend.

### `ingestion/`

Converts external document formats into normalized project-owned `Document` and `Chunk` objects.

### `embeddings/`

Contains dense model adapters only. The rest of the application should not know whether embeddings come from Sentence Transformers, FastEmbed, or another local backend.

### `index/`

Owns Qdrant persistence and corpus/index lifecycle. Retrieval logic should not directly scatter database calls throughout the project.

### `retrieval/`

Owns candidate generation, fusion, reranking, context assembly, and confidence policy.

### `generation/`

Owns the model-agnostic local generation client, endpoint/model preflight, prompt construction, answer schema, and citation handling. The generative model itself is not part of the application image.

### `agents/`

Owns only conditional orchestration. Do not place basic retrieval logic here; the graph should call stable services.

### `guardrails/`

Owns security policies that should remain independent from the generator prompt where possible.

### `evaluation/`

Owns benchmark datasets, metrics, experiment tracking, comparison, and judge adapters. It may call production services, but production services must not depend on evaluator-specific logic.

### `observability/`

Owns traces, timing, resource metrics, and local logs.

### `api/`

Thin transport layer. Business logic should not live in FastAPI route functions.

## Runtime filesystem and service contracts

### `/data`

Writable persistent application state:

- raw/managed document copies where enabled;
- parsed artifacts/cache;
- Qdrant Local storage;
- manifests;
- experiment results;
- traces/logs according to retention settings.

### `/models`

Read-only or controlled local assets for **embedding and reranker models only**. Generator weights are managed by Ollama or another external local inference runtime.

### Generation endpoint

Configured externally through environment/config. Core code sees only the project-owned OpenAI-compatible interface.

## Why this structure matters

The structure intentionally prevents a common RAG failure mode: one large orchestration module with framework objects, database calls, prompt templates, metrics, and parsing logic mixed together.

A portfolio reviewer should be able to locate the retrieval logic, evaluation logic, and security policy independently.
