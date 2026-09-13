# Project Structure

The project is organized around explicit domain boundaries. Framework-specific integrations live behind project-owned interfaces so that Docling, Qdrant, LangGraph, Ollama, or other dependencies can be replaced without rewriting the application core.

## Implemented through Slice 8 (current)

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
│   ├── lexical-indexes/, lexical-index-manifests/
│   └── qdrant/
├── models/
│   ├── docling/
│   ├── tokenizers/tiktoken/
│   ├── embeddings/qwen3-embedding-0.6b/
│   └── rerankers/bge-reranker-v2-m3/
├── eval/datasets/dense_smoke/
├── scripts/
│   ├── provision_docling.py
│   ├── provision_tiktoken.py
│   └── provision_embedding.py
├── docs/
│   ├── slice0_contracts.md … slice8_grounded_generation.md
│   └── model_provisioning.md
├── src/offline_rag/
│   ├── cli.py
│   ├── config/
│   ├── core/ids.py
│   ├── domain/          # documents, blocks, corpus, chunking, indexing, generation, …
│   ├── ingestion/       # parsers, Docling artifacts, ingest pipeline
│   ├── chunking/        # structure-aware chunker, tiktoken, chunk pipeline
│   ├── dense/           # embedders, Qdrant Local, index/retrieve/eval
│   ├── lexical/         # BM25 inverted index, analyze, score, retrieve/eval
│   ├── hybrid/          # query-time RRF (no hybrid index/state)
│   ├── rerank/          # hybrid-pool cross-encoder (no HybridRerankState)
│   ├── context/         # hybrid-rerank-context assembly (no ContextState)
│   ├── generation/      # grounded query (no GenerationState)
│   └── observability/
└── tests/
```

## Intended long-term tree

The tree below remains the target shape for later slices (expansion → generation, API, UI). Prefer evolving existing packages rather than renaming prematurely.

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
│       ├── hybrid_rerank_context.yaml
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
│   ├── lexical-indexes/
│   ├── lexical-index-manifests/
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
│       ├── lexical/               # Slice 4 (BM25 inverted index + retrieve + lexical eval)
│       ├── hybrid/                # Slice 5 (query-time rrf-v1; no hybrid index)
│       ├── rerank/                # Slice 6 (hybrid-pool CE; derived READY only)
│       ├── context/               # Slice 7 (structural expansion; derived READY only)
│       ├── generation/            # Slice 8 (grounded query; derived READY only; no GenerationState)
│       │
│       ├── embeddings/            # optional future split; dense/ currently owns adapters
│       ├── index/                 # optional future split
│       │
│       ├── retrieval/             # reserved; dense/lexical/hybrid/rerank/context stay owned
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
│       │   ├── gold.py
│       │   ├── metrics.py
│       │   ├── result.py
│       │   ├── runner.py
│       │   ├── compare.py
│       │   └── ...                    # Slice 9 retrieval-eval harness
│       │
│       ├── gold_authoring/            # Milestone 4 (Slice 9A boundary done)
│       │   ├── contracts.py
│       │   ├── config_hash.py
│       │   ├── privacy.py
│       │   ├── models.py
│       │   ├── readiness.py
│       │   ├── transport.py
│       │   ├── propose.py             # Slice 9B+
│       │   ├── pooling.py             # Slice 9C+
│       │   ├── prelabel.py            # Slice 9D+
│       │   ├── review.py              # Slice 9E+
│       │   └── finalize.py            # Slice 9E+
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

### `lexical/`

Project-owned inverted index, `technical-v1` analyzer, `bm25-okapi-v1` scorer, `LexicalRetriever`, and lexical eval (Slice 4). Independent of dense indexes.

### `hybrid/`

Query-time `HybridRetriever` + `ReciprocalRankFusion` (rrf-v1). Derived READY/NOT_READY only; no HybridState or hybrid index artifacts (Slice 5).

### `rerank/`

`HybridRerankRetriever` over hybrid pools + local `CrossEncoderReranker` / `FakeReranker`. Derived READY/NOT_READY only; no HybridRerankState (Slice 6).

### `context/`

`HybridRerankContextAssembler` + source-agnostic `ContextExpander`. Parent/neighbor structural evidence assembly with `ctxcfg_` identity. Derived READY/NOT_READY only; no ContextState (Slice 7).

### `embeddings/` / `index/` (future optional splits)

Slice 3 keeps adapters under `dense/`. Later refactors may split packages if the tree grows; do not duplicate contracts.

### `retrieval/`

Reserved mega-package slot; not used. Dense, lexical, hybrid, rerank, context, and generation live in their packages today.

### `generation/`

`GroundedAnswerOrchestrator` + OpenAI-compatible adapter / FakeGenerator. Prompt (`prompt-grounded-v1`), output (`grounded-answer-v1`), closed-world `ev_` citations, `gencfg_` identity, derived Generation READY only; no GenerationState (Slice 8). The generative model itself is not part of the application image.

### `agents/`

Owns only conditional orchestration. Do not place basic retrieval logic here; the graph should call stable services.

### `guardrails/`

Owns security policies that should remain independent from the generator prompt where possible.

### `evaluation/`

Owns finished GoldDataset loading/validation, retrieval metrics, experiment serialization, and comparison (`eval retrieve` / `eval compare`). It may call production retrieval services, but production services must not depend on evaluator-specific logic. Silver/authoring drafts are not gold.

### `gold_authoring/` (Milestone 4 — Slice 9A boundary done)

Owns the privacy-bounded local gold construction workflow (propose → pool → prelabel → review → finalize). Slice 9A shipped contracts, privacy, `authorcfg_`, lean silver/run models, and doctor readiness. Separate from `evaluation/` and from production generation prompt contracts. Notes: `docs/slice9a_gold_authoring.md`; plan: `docs/milestone4_offline_gold_authoring.md`.

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
