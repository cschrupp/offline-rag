# OfflineRAG

### Seneca — Grounded knowledge workspace

A local-first, evaluated RAG platform for private technical knowledge, with
versioned workspaces, grounded conversational answers, claim-level citations,
evidence inspection, training workflows, and reproducible retrieval/generation
evaluation.

**Naming**

| Name | Role |
|---|---|
| **OfflineRAG** | Repository, local RAG engine, evaluation harness, CLI, and product/API platform (`offline-rag` package / image) |
| **Seneca — Grounded knowledge workspace** | Current user-facing React application experience over that platform |

Repository, Python package, CLI, and Docker image names remain **OfflineRAG** /
`offline-rag` unless renamed elsewhere by separate authority.

## Why this project exists

Most RAG demos prove only that a model can answer a few hand-picked questions
after indexing a PDF. OfflineRAG is built to answer harder engineering questions:

- How much does hybrid retrieval improve recall over dense retrieval alone?
- Does reranking improve ranking quality enough to justify its latency cost?
- When should the system abstain rather than generate an answer?
- Can every answer citation be traced to evidence actually retrieved and passed to the model?
- How does the system behave when retrieved documents contain prompt-injection instructions?

Evaluation is a first-class subsystem, not an afterthought.

## Core principles

- **Fully local/offline by design.** Documents, embeddings, queries, retrieval, reranking, generation, and evaluation remain on the local machine; the generative model is served by a separate local inference runtime.
- **Retrieval before generation.** Retrieval quality is measured independently from answer quality.
- **Hybrid retrieval by default.** Dense semantic retrieval is complemented by lexical retrieval for identifiers, acronyms, numbers, and exact phrases.
- **Rerank before generation.** A second-stage cross-encoder improves the final evidence ranking.
- **Small chunks for search, larger context for reasoning.** Hierarchical/parent-child retrieval preserves precision without starving the generator of context.
- **Abstention is a feature.** The system should explicitly say when the indexed corpus does not support an answer.
- **Citations are verified.** References must resolve to real evidence that was retrieved and included in the generation context.
- **Every architectural addition must earn its complexity.** Improvements should be supported by ablation or accepted evaluation evidence.

## Current capabilities

Landed in the accepted repository (not aspirational):

- local document ingestion by media type:
  - PDF via Docling (`DoclingPdfParser`)
  - TXT via native `TextParser`
  - Markdown (`.md` / `.markdown`) via native `MarkdownParser`
- structure-aware chunking
- Qwen3 embeddings (provisioned local weights; fake embedder for CI)
- BM25 lexical retrieval
- hybrid RRF fusion
- cross-encoder reranking
- hierarchical context assembly
- local grounded generation (external OpenAI-compatible endpoint)
- evidence sufficiency / abstention
- citation validation
- retrieval evaluation + generation/citation semantic evaluation (Slice 10)
- security / adversarial evaluation campaigns (Slice 13)
- performance measurement harness (Slice 14)
- FastAPI product/application layer (`src/offline_rag/app/`, `src/offline_rag/api/`)
- versioned workspaces, snapshots, source upload/versioning
- React **Seneca** UI (`ui/`)
- grounded multi-turn conversation (16D-B3)
- claim-level citations and Evidence inspection
- Current / Historical provenance
- Training Mode with compact Question Bank, progressive reveal, presentation view
- Question Bank JSON/Markdown portability and conversation Markdown/JSON export
- strict-offline deployment profile

## Active stack

| Layer | Choice | Status |
|---|---|---|
| PDF parsing | Docling (`DoclingPdfParser`) | ACTIVE |
| Text parsing | Native `TextParser` (`.txt`) | ACTIVE |
| Markdown parsing | Native `MarkdownParser` (`.md` / `.markdown`) | ACTIVE |
| Chunking | Structure-aware / parent-child | ACTIVE |
| Dense embeddings | Qwen3-Embedding-0.6B (default; fake for CI) | ACTIVE |
| Sparse retrieval | BM25 | ACTIVE |
| Vector store | Qdrant Local (in-process under `/data`) | ACTIVE |
| Fusion | Reciprocal Rank Fusion (RRF) | ACTIVE |
| Reranker | BGE reranker (default; fake for CI) | ACTIVE |
| Product / API | FastAPI (`offline_rag.app` + `offline_rag.api`) | ACTIVE |
| UI | React + Vite (Seneca) | ACTIVE |
| Generation runtime | External local OpenAI-compatible endpoint (Ollama default on host) | ACTIVE |
| Evaluation | Project-owned harness (retrieval, generation semantic, security, performance) | ACTIVE |
| Recovery / LangGraph adapter | Deferred | DEFERRED / NOT AUTHORIZED |
| NeMo Guardrails | Deferred | DEFERRED / NOT AUTHORIZED |

Derive configuration from `config/`, `pyproject.toml`, and `ui/package.json`.

## High-level architecture

```text
                              HOST MACHINE

                  +-----------------------------+
                  |  Local generation runtime   |
                  |  Ollama by default          |
                  |  OpenAI-compatible endpoint |
                  +--------------^--------------+
                                 | localhost / host gateway
                                 |
+--------------------------------+--------------------------------+
|                  OFFLINERAG APPLICATION                         |
|                                                                 |
|  React / Seneca  →  FastAPI product/application layer           |
|                           |                                     |
|              workspace / snapshot / admission contracts         |
|                           |                                     |
|              dense + lexical retrieval → RRF → reranker         |
|                           |                                     |
|                    context assembly                             |
|                           |                                     |
|                 evidence sufficiency                            |
|                           |                                     |
|              local generation client ---------------------------+
|                           |                                     |
|         answer blocks + claim citations                         |
|                           |                                     |
|         Evidence / provenance / traces                          |
|                                                                 |
|  /data volume          /models volume (embeddings/reranker)     |
+-----------------------------------------------------------------+
```

The generative model remains outside the application image. Product recovery is
**disabled** in the accepted disposition (Slice 12 efficacy evidence did not
justify promotion). A LangGraph adapter remains **NOT AUTHORIZED**. NeMo /
13D remains **DEFERRED / OPTIONAL / NOT AUTHORIZED**.

## Seneca product experience

```text
Create/open workspace
      ↓
Add/version local sources
      ↓
Select source scope
      ↓
Ask grounded question
      ↓
inspect claim-level citations and Evidence
      ↓
ask conversational follow-ups
      ↓
inspect Current/Historical provenance
      ↓
optionally use Training Mode
```

Training Mode (accepted 16D-C / A4) includes a compact Question Bank (search;
JSON/Markdown import-export), progressive answer/citation/evidence reveal,
presentation view, and conversation Markdown/JSON export.

**Hard boundary:** conversation export is not source ingestion. An exported
`.md` may later be uploaded only through an explicit human Add Sources action.
Exports never automatically become workspace knowledge.

## Deployment model

Flagship shape: one OfflineRAG container plus a local inference service on the
host. See `DEPLOYMENT.md`.

```bash
ollama serve
ollama pull <local-model>

docker build -f deploy/Dockerfile -t offline-rag:latest .
docker compose -f deploy/docker-compose.example.yml up --build
# Host publish is loopback-only: 127.0.0.1:8080 -> container :8080
```

Direct-host API (non-container):

```bash
uv sync
python -m offline_rag.api.server   # 127.0.0.1:8080
```

### Strict offline mode

`strict_offline: true` means no cloud API keys are required or consumed at
runtime; generation endpoint/model must match local allowlists; embedding and
reranker weights load from provisioned local files; runtime auto-downloads and
external telemetry are disabled where supported. Provisioning may require
internet; normal runtime must not.

## Measured performance evidence (Slice 14)

Slice 14 is **COMPLETE / ACCEPTED**. Evidence is descriptive under frozen
protocols; it does not define a latency SLO, declare a winner, or authorize
configuration promotion. Full provenance:
[`docs/milestone7_performance_ui.md`](docs/milestone7_performance_ui.md).

**Retrieval quality-vs-cost benchmark (14C; generation excluded)**

- Terminal run: `perfrun_deb7a58e49d0f64496553a16c3edc3a5b517deec5ec1c9ddd76831fee79627ca`
- Population: 44 cases; 440 measured observations; 88 warm-ups; 0 failures
- Observed warm totals (measured): hybrid p50 ≈ 5.62 s / p95 ≈ 8.31 s;
  hybrid + reranker p50 ≈ 7.41 s / p95 ≈ 13.53 s
- Development/regression fixture only — not publication-grade evidence.

**End-to-end generation-path benchmark (Level-C; separate population)**

- Terminal run: `perfrun_211ebf1f9bcdef93d1f14421b754ef5ff387e2e091dc7f603f455dd083fdbf39`
- Population: 5 queries; 5 warm-ups + 25 measured = 30 attempts
- Observed warm end-to-end (measured): p50 ≈ 50.83 s / p95 ≈ 144.59 s
- Observed warm generation (measured): p50 ≈ 13.71 s / p95 ≈ 64.06 s
- TTFT / decode / tokens-sec remain UNEVALUABLE on the accepted non-streaming
  generator path.

Do **not** merge 14C retrieval-path latency with Level-C end-to-end latency.

## Repository map

```text
offline-rag/
├── README.md
├── ROADMAP.md
├── DEPLOYMENT.md
├── DEVELOPMENT_GUIDE.md
├── PROJECT_STRUCTURE.md
├── pyproject.toml
├── config/
├── deploy/
├── docs/                 # slice evidence, amendments, plans
├── eval/                 # gold / evaluation datasets
├── models/               # provisioned local weights (gitignored content)
├── scripts/
├── src/offline_rag/      # engine + product/application layer
│   ├── app/              # product use-cases (workspaces, query, ingest, …)
│   ├── api/              # FastAPI surface
│   ├── evaluation/
│   └── …                 # ingestion, retrieval, generation, …
├── ui/                   # Seneca React application
└── tests/
```

See `PROJECT_STRUCTURE.md` for the current tree. Detailed provenance lives in
`ROADMAP.md` and `docs/`.

## Quick start

### CLI retrieval / generation path

```bash
uv sync
uv run python scripts/provision_docling.py
uv run python scripts/provision_tiktoken.py
# optional for real dense / rerank quality:
# uv run offline-rag provision embedding
# uv run offline-rag provision reranker

offline-rag ingest ./documents --corpus engineering
offline-rag chunk --corpus engineering
offline-rag index --corpus engineering
offline-rag index lexical --corpus engineering
offline-rag retrieve hybrid-rerank-context --corpus engineering --query "…"
# Configure approved local generation endpoint/model, then:
offline-rag query --corpus engineering --query "…"
offline-rag doctor --corpus engineering
```

### Seneca UI (local development)

Two processes: product API on `:8080`, Vite on `:5173` (proxies `/v1` and
`/health` to the API — see `ui/vite.config.ts`).

```bash
# terminal 1 — product API
uv sync
python -m offline_rag.api.server

# terminal 2 — Seneca UI
cd ui
npm install
npm run dev
```

Container profile (API + packaged frontend serving): see `DEPLOYMENT.md` and
`deploy/docker-compose.example.yml`.

### Validation commands

```bash
uv run pytest
uv run ruff check src tests
cd ui && npm test && npm run lint && npm run typecheck && npm run build
```

## Project status

| Gate | Status |
|---|---|
| Milestone 4 | Near-term engineering closed; **9G** publication expansion deferred |
| Milestone 5 | Development checkpoint reached; Slice **10A–10E** implemented / verified |
| Milestone 6 | **COMPLETE / ACCEPTED** |
| Milestone 7 | **IN PROGRESS** |
| Slice 14 | **COMPLETE / ACCEPTED** |
| Slice 15 | **COMPLETE / ACCEPTED** |
| Slice 16 | **IN PROGRESS / NOT COMPLETE** |
| 16A / 16B / 16C | **COMPLETE / ACCEPTED** |
| 16D-A / 16D-B2 / 16D-B3 / 16D-C | **COMPLETE / ACCEPTED / SEALED** |
| Amendment A4 | **ACCEPTED / LOCKED / SEALED** |
| 16E | **IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING** |
| 16F–16H | **NOT AUTHORIZED** |
| Slice 17 / 18 | **NOT AUTHORIZED** |
| M7 closeout | **NOT AUTHORIZED** |

Detailed SHAs and evidence: [`ROADMAP.md`](ROADMAP.md),
[`docs/slice16d_c_a4_closeout.md`](docs/slice16d_c_a4_closeout.md),
[`docs/milestone7_performance_ui.md`](docs/milestone7_performance_ui.md).

Still deferred / not authorized as product deliverables:

- publication-grade portfolio claims (`PORTFOLIO_DEMO.md` update gated)
- product LangGraph recovery / NeMo integration
- `config/base.yaml` scientific promotion
- cloud inference in the strict-offline core
- enterprise auth / RBAC
- distributed Qdrant / GraphRAG / multi-agent swarms

## Scope boundaries

### In scope (accepted)

- Fully local document ingestion and retrieval
- Dense + lexical hybrid retrieval, reranking, hierarchical context
- Local generation through an external local inference runtime
- Claim-level citations and Evidence inspection
- Workspace product API and Seneca UI through accepted Slice 16 gates
- Retrieval, generation-semantic, security, and performance evaluation

### Explicitly deferred

- Knowledge-graph / GraphRAG
- Fine-tuning of the generator
- Multi-agent swarms
- Cloud inference in the strict-offline/core profile
- Enterprise identity/RBAC
- Distributed vector-database deployment
- Product LangGraph recovery adapter
- NeMo Guardrails integration
- Publication-grade 9G promotion / M7 closeout packaging
