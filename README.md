# OfflineRAG

**An evaluated, fully local RAG platform for private technical knowledge.**

OfflineRAG is a portfolio-grade retrieval-augmented generation system designed for sensitive technical documents. The project emphasizes retrieval quality, reproducible evaluation, grounded answers, traceable citations, and secure local execution rather than simply demonstrating that a chatbot can answer questions about PDFs.

## Why this project exists

Most RAG demos prove only that a model can answer a few hand-picked questions after indexing a PDF. OfflineRAG is designed to answer harder engineering questions:

- How much does hybrid retrieval improve recall over dense retrieval alone?
- Does reranking improve ranking quality enough to justify its latency cost?
- When should the system abstain rather than generate an answer?
- Can every answer citation be traced to evidence actually retrieved and passed to the model?
- How does the system behave when retrieved documents contain prompt-injection instructions?
- Which document types or query classes remain difficult: tables, numeric lookup, acronyms, comparisons, or multi-document synthesis?

The project therefore treats **evaluation as a first-class subsystem**, not as an afterthought.

## Core principles

- **Fully local/offline by design.** Documents, embeddings, queries, retrieval, reranking, generation, and evaluation remain on the local machine; the generative model is served by a separate local inference runtime.
- **Retrieval before generation.** Retrieval quality is measured independently from answer quality.
- **Hybrid retrieval by default.** Dense semantic retrieval is complemented by lexical retrieval for identifiers, acronyms, numbers, engineering terminology, and exact phrases.
- **Rerank before generation.** A second-stage cross-encoder improves the final evidence ranking.
- **Small chunks for search, larger context for reasoning.** Hierarchical/parent-child retrieval preserves precision without starving the generator of context.
- **Abstention is a feature.** The system should explicitly say when the indexed corpus does not support an answer.
- **Citations are verified.** References must resolve to real chunks that were retrieved and included in the generation context.
- **Agentic behavior is conditional.** Query rewriting and retry are used only when evidence quality is insufficient.
- **Every architectural addition must earn its complexity.** Improvements should be supported by ablation results.

## Proposed stack

| Layer | Default choice | Notes |
|---|---|---|
| Parsing | Docling | Layout-aware PDF/document understanding, OCR when needed, structural metadata |
| Chunking | Structure-aware / hybrid chunking | Preserve headings, pages, tables, parent-child relationships |
| Dense embeddings | Qwen3-Embedding-0.6B (default) | Swappable; BGE-M3 reserved for later experiments |
| Sparse retrieval | BM25 initially | Strong baseline for exact technical terms; SPLADE can be evaluated later |
| Vector/search database | Qdrant Local | Persistent local path; server mode deferred |
| Fusion | Reciprocal Rank Fusion (RRF) | Simple, robust hybrid baseline |
| Reranker | Qwen3-Reranker or BGE reranker | Second-stage cross-encoder ranking |
| Orchestration | LangGraph + small LangChain integrations | Explicit retrieval/rewrite/retry/abstain graph |
| Generation runtime | External local OpenAI-compatible endpoint | Ollama on the host is the default; llama.cpp/vLLM remain swappable alternatives |
| API | FastAPI | Local API boundary between UI and RAG engine |
| Guardrails | Deterministic controls + optional NeMo Guardrails | Retrieval security, citation validation, prompt-injection resistance |
| Evaluation | Custom harness + optional Ragas/DeepEval adapters | IR metrics, answer metrics, citation metrics, abstention, security, performance |

## High-level architecture

```text
                              HOST MACHINE

                  +-----------------------------+
                  |  Local generation runtime   |
                  |  Ollama by default          |
                  |  OpenAI-compatible endpoint |
                  +--------------^--------------+
                                 | localhost/host gateway
                                 |
+--------------------------------+--------------------------------+
|                  OFFLINERAG APPLICATION CONTAINER               |
|                                                                 |
|  PDF / TXT / MD                                                 |
|         |                                                       |
|      Docling                                                    |
|         |                                                       |
|  structured chunks                                              |
|     +---+---+                                                   |
|     |       |                                                   |
|   dense    BM25                                                 |
|     |       |                                                   |
|     +---+---+ -> Qdrant Local -> RRF -> reranker               |
|                                  |                              |
|                           context expansion                     |
|                                  |                              |
|                              LangGraph                          |
|                                  |                              |
|                          generation client ---------------------+
|                                  |                              |
|                           citation checks                       |
|                                  |                              |
|                           grounded answer                       |
|                                                                 |
|  FastAPI + static UI + evaluation harness + local traces        |
+--------------------------+----------------------+---------------+
                           |                      |
                       /data volume          /models volume
                                           embeddings/reranker
                                           weights only
```

The **generative model is intentionally outside the application image**. OfflineRAG owns retrieval and evaluation; Ollama (or another local OpenAI-compatible server) owns model execution. This keeps the image smaller, makes GPU/runtime support replaceable, and preserves a clean inference boundary.

## Deployment model

The flagship deployment target is **one OfflineRAG Docker container plus a local inference service already running on the host**. Ollama is the documented default because it makes local model provisioning and hardware support a separate concern from the RAG application.

Target runtime shape:

```text
ollama serve                         # host
ollama pull <local-model>            # provisioning step

docker run ... offline-rag:latest   # application container

Browser -> http://localhost:8080
```

The container persists application state through `/data` and receives locally provisioned embedding/reranker weights through `/models`. It does **not** contain the generative model.

Generation is configured through a generic interface:

```yaml
generation:
  provider: openai_compatible
  base_url: http://host.docker.internal:11434/v1
  model: <approved-local-model>
```

Later deployments can point the same client at llama.cpp, vLLM, or another compatible local server without changing retrieval code. See `DEPLOYMENT.md` and `docs/offline_runtime_contract.md`.

### Strict offline mode

`strict_offline: true` means:

- no cloud API keys are required or consumed;
- the generation endpoint must match an explicit local endpoint allowlist;
- the generation model must match an explicit locally approved model allowlist/manifest;
- embedding and reranker models must load from already provisioned local files/cache;
- runtime auto-downloads and external tracing/telemetry are disabled where supported;
- offline verification is part of the integration/security test suite.

Provisioning may require internet access. Normal runtime must not.

## What makes this portfolio-worthy

The differentiator is not the chat UI. The differentiator is the experimental discipline around retrieval and grounded generation.

The project should eventually publish an ablation table similar to:

| Pipeline | Recall@5 | MRR | nDCG@10 | Answer accuracy | Citation accuracy | p50 latency |
|---|---:|---:|---:|---:|---:|---:|
| Dense baseline | TBD | TBD | TBD | TBD | TBD | TBD |
| BM25 baseline | TBD | TBD | TBD | TBD | TBD | TBD |
| Hybrid | TBD | TBD | TBD | TBD | TBD | TBD |
| Hybrid + reranker | TBD | TBD | TBD | TBD | TBD | TBD |
| Hybrid + reranker + conditional rewrite | TBD | TBD | TBD | TBD | TBD | TBD |

The goal is to be able to make evidence-backed statements such as:

> Adding the reranker improved MRR by X% while increasing median retrieval latency by Y ms. Query rewriting improved difficult semantic queries but produced little gain on exact-keyword questions.

## Evaluation dimensions

### Retrieval

- Recall@1 / @5 / @10
- Precision@k
- Mean Reciprocal Rank (MRR)
- nDCG@k
- Hit rate
- Per-query-category performance

### Generation

- Answer correctness
- Faithfulness / groundedness
- Completeness
- Unsupported-claim rate

### Citations

- Citation resolvability
- Citation-in-retrieved-set rate
- Citation-in-context rate
- Citation entailment/support

### Abstention

- Correct abstention rate
- False-answer rate
- False-refusal rate

### Security

- Direct prompt injection
- Indirect prompt injection in retrieved documents
- Fake system messages in documents
- Citation manipulation attempts
- Tool / filesystem access attempts

### Performance

- Parse throughput
- Embedding throughput
- Index build time
- Retrieval p50/p95
- Reranking p50/p95
- End-to-end p50/p95
- Time to first token
- Generation tokens/sec
- RAM/VRAM usage
- Index size

## Repository map

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
├── DEPLOYMENT.md
├── deploy/
│   ├── Dockerfile.template
│   └── docker-compose.example.yml
├── config/
│   ├── base.yaml
│   ├── deployment/
│   └── experiments/
├── models/
│   ├── README.md
│   └── manifest.example.yaml
├── eval/
│   └── datasets/
├── src/
│   └── offline_rag/
├── tests/
└── scripts/
```

See `PROJECT_STRUCTURE.md` for the current Slice 0–3 tree and the intended long-term module layout.

## Development sequence

The project is intentionally sliced so each stage produces a working, testable system.

1. **Foundation and contracts** — repository, configuration, IDs, logging, typed interfaces. *(done)*
2. **Document ingestion** — Docling parsing, metadata normalization, deterministic document/parsed IDs. *(done)*
3. **Structure-aware chunking** — parent/child chunks, neighbor links, chunk-set state. *(done)*
4. **Dense baseline** — local embeddings, Qdrant Local, `retrieve`, dense Recall@k/MRR. *(done)*
5. **Lexical baseline and hybrid retrieval** — BM25 + RRF.
6. **Reranking** — second-stage cross-encoder.
7. **Hierarchical context** — child retrieval + parent/neighbor expansion.
8. **Grounded generation** — generic local inference client, Ollama default, answer schema, page-level citations.
9. **Evaluation harness** — gold dataset expansion, experiment registry, generation metrics.
10. **Abstention and confidence policy** — explicitly handle missing evidence.
11. **Agentic recovery** — conditional LangGraph rewrite/retry.
12. **Security and guardrails** — document-injection tests and hard controls.
13. **Performance benchmarking** — latency, throughput, memory, VRAM.
14. **Demo UI** — query inspector, retrieval visualization, benchmark dashboard.
15. **Portfolio packaging** — reproducible benchmark report, architecture diagram, demo scenario.

Detailed exit criteria are in `detailed_implementation_slices.md`. Slice notes: `docs/slice0_contracts.md` … `docs/slice3_dense_retrieval.md`.

## Quick start (through dense retrieve)

```bash
uv sync
uv run python scripts/provision_docling.py      # PDF support
uv run python scripts/provision_tiktoken.py     # chunk budgets
# For real dense quality (large download):
# uv run offline-rag provision embedding

offline-rag ingest ./documents --corpus engineering
offline-rag chunk --corpus engineering
offline-rag index --corpus engineering          # requires provisioned Qwen unless embedding.implementation=fake
offline-rag retrieve --corpus engineering --query "maximum operating pressure"
offline-rag doctor --corpus engineering
```

Default config expects Qwen weights under `models/embeddings/qwen3-embedding-0.6b/`. CI and unit tests use `FakeEmbedder` / fake tokenizer so they do not require Qwen weights.

## Demo experience

**Today (Slice 3):** ingest → chunk → dense index → retrieve / eval retrieve / doctor.

**Target demo** should allow a user to:

1. Ingest a small set of public technical documents.
2. Ask an engineering question.
3. Inspect the dense and sparse candidates.
4. Observe RRF fusion and reranker scores.
5. Open the exact source page/chunk behind a citation.
6. Compare dense-only vs hybrid vs hybrid+reranker.
7. Ask an unanswerable question and see correct abstention.
8. Trigger an adversarial document test and observe that retrieved instructions are treated as data.
9. Open an evaluation dashboard showing the measured impact of each retrieval component.

## Scope boundaries

### In scope

- Fully local document ingestion and retrieval
- PDF/TXT/MD first, with other Docling-supported formats added incrementally
- Dense + lexical hybrid retrieval
- Cross-encoder reranking
- Hierarchical context expansion
- Local generation through an external local inference runtime
- Page/chunk citations
- Retrieval and generation evaluation
- Abstention and prompt-injection defenses
- Reproducible experiment configuration

### Explicitly deferred

- Knowledge-graph RAG
- GraphRAG
- Fine-tuning of the generator
- Multi-agent swarms
- Cloud inference in the strict-offline/core profile
- Enterprise identity/RBAC
- Distributed vector-database deployment
- Complex multimodal reasoning over arbitrary figures

These can be added only if evaluation reveals a concrete need.

## Suggested corpus for the portfolio demo

Use public, redistributable technical documents rather than proprietary material. Prefer a compact domain where exact terminology, tables, sections, acronyms, and cross-document comparisons matter. The engine should remain domain-agnostic even if the showcased corpus is engineering-focused.

## Project status

**Phase:** Milestone 1 dense baseline implemented (Slices 0–3).

Working local path: ingest → chunk → index → retrieve → dense eval.
Next: Slice 4 BM25 → Slice 5 RRF → Slice 6 reranker → Slice 7 context expansion → Slice 8+ generation/`query`.

See `ROADMAP.md` and `docs/slice3_dense_retrieval.md`.
