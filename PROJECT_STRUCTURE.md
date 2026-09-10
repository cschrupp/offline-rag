# Project Structure

The project is organized around explicit domain boundaries. Framework-specific integrations live behind project-owned interfaces so that Docling, Qdrant, LangGraph, Ollama, or other dependencies can be replaced without rewriting the application core.

## Implemented through Slice 3 (current)

```text
offline-rag/
├── README.md
├── ROADMAP.md
├── pyproject.toml
├── config/
│   ├── base.yaml
│   ├── deployment/
│   └── experiments/
├── data/                          # gitignored content; .gitkeep placeholders
│   ├── raw/, processed/, manifests/, corpora/
│   ├── chunks/, chunk-manifests/
│   ├── embeddings/, index-manifests/
│   └── qdrant/
├── models/
│   ├── docling/
│   ├── tokenizers/tiktoken/
│   └── embeddings/qwen3-embedding-0.6b/
├── eval/datasets/dense_smoke/
├── scripts/
│   ├── provision_docling.py
│   ├── provision_tiktoken.py
│   └── provision_embedding.py
├── docs/
│   ├── slice0_contracts.md … slice3_dense_retrieval.md
│   └── model_provisioning.md
├── src/offline_rag/
│   ├── cli.py
│   ├── config/
│   ├── core/ids.py
│   ├── domain/          # documents, blocks, corpus, chunking, indexing, retrieval, …
│   ├── ingestion/       # parsers, Docling artifacts, ingest pipeline
│   ├── chunking/        # structure-aware chunker, tiktoken, chunk pipeline
│   ├── dense/           # embedders, Qdrant Local, index/retrieve/eval
│   └── observability/
└── tests/
```

## Intended long-term tree

The tree below remains the target shape for later slices (BM25 → RRF → rerank → expansion → generation, API, UI). Prefer evolving existing packages rather than renaming prematurely.

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
├── pyproject.toml                 # present (Slice 0+)
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
│   ├── corpora/
│   ├── chunks/
│   ├── chunk-manifests/
│   ├── embeddings/
│   ├── index-manifests/
│   └── qdrant/
│
├── models/                        # ignored; embedding/reranker/docling/tokenizer assets
│   ├── README.md
│   ├── manifest.example.yaml
│   ├── docling/
│   ├── tokenizers/
│   ├── embeddings/
│   └── reranker/
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
│       ├── ingestion/             # Slice 1
│       ├── chunking/              # Slice 2 (structure-aware; not Docling chunker)
│       ├── dense/                 # Slice 3 (embed + Qdrant Local + retrieve + dense eval)
│       │
│       ├── embeddings/            # optional future split; dense/ currently owns adapters
│       ├── index/                 # optional future split
│       │
│       ├── retrieval/             # future: BM25, fusion, rerank, context
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
    ├── slice0_contracts.md
    ├── slice1_ingestion.md
    ├── slice2_chunking.md
    ├── slice3_dense_retrieval.md
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

Converts external document formats into normalized project-owned `ParsedDocument` / `ContentBlock` objects and corpus manifests (Slice 1). Does not create retrieval chunks.

### `chunking/`

Structure-aware parent/child chunking over ParsedDocuments (Slice 2).

### `dense/`

Embedding adapters, EmbeddingArtifact cache, Qdrant Local backend, dense index publish, `DenseRetriever`, and minimal dense eval (Slice 3).

### `embeddings/` / `index/` (future optional splits)

Slice 3 keeps adapters under `dense/`. Later refactors may split packages if the tree grows; do not duplicate contracts.

### `retrieval/`

Future: BM25 (4), fusion (5), reranking (6), context assembly (7), then generation/confidence (8+).

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
