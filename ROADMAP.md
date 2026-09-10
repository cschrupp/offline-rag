# Roadmap

## Milestone 0 — Design complete

- [x] Product definition
- [x] Architecture decision log
- [x] Implementation slices
- [x] Project structure
- [x] Evaluation strategy
- [x] Security model
- [x] Demo strategy

## Milestone 1 — Measurable dense RAG baseline

- [x] Repository and domain contracts (Slice 0)
- [x] Docling ingestion (Slice 1)
- [x] Structure-aware chunks (Slice 2)
- [x] Local dense embeddings (Slice 3; Qwen3-Embedding-0.6B + FakeEmbedder for CI)
- [x] Qdrant persistence (Slice 3; Qdrant Local)
- [x] Dense retrieval benchmark (`offline-rag eval retrieve`)
- [x] Minimal local retrieve CLI (`offline-rag retrieve`; full `query`/generation remains deferred)

**Release criterion:** reproducible Recall@k/MRR baseline on a small gold set.

**Status:** Slice 0–3 dense baseline done. See Milestone 2 for Slice 4+.

## Milestone 2 — Modern retrieval stack

- [x] BM25 / lexical baseline (Slice 4; project-owned inverted index + bm25-okapi-v1)
- [x] Hybrid retrieval / RRF fusion (Slice 5; query-time rrf-v1 over dense+lexical)
- [x] Cross-encoder reranking over fused pools (Slice 6; BGE bge-reranker-v2-m3 + FakeReranker)
- [ ] Parent/neighbor context expansion (Slice 7)
- [ ] Ablation report (Dense → +BM25 → +RRF → +reranker → +expansion)

**Release criterion:** measured comparison of dense, BM25, hybrid, and hybrid+reranker.

**Status:** Slice 6 hybrid-rerank implemented. Next: Slice 7 parent/neighbor expansion.

## Milestone 3 — Grounded local QA

- [ ] OpenAI-compatible generation client
- [ ] Ollama-on-host default profile
- [ ] strict-offline endpoint/model preflight
- [ ] structured answer schema
- [ ] citation provenance
- [ ] citation validator
- [ ] abstention path

**Release criterion:** grounded answer with resolvable source citations and explicit insufficient-evidence output.

## Milestone 4 — Evaluation platform

- [ ] generation metrics
- [ ] citation metrics
- [ ] negative set
- [ ] synthetic expansion
- [ ] experiment registry
- [ ] per-category reports
- [ ] regression benchmark subset

**Release criterion:** one command generates a comparable experiment artifact and report.

## Milestone 5 — Agentic recovery and security

- [ ] LangGraph state machine
- [ ] bounded query rewrite/retry
- [ ] evidence sufficiency policy
- [ ] indirect prompt-injection suite
- [ ] optional NeMo Guardrails evaluation

**Release criterion:** agentic recovery demonstrates measured benefit and adversarial test results are documented.

## Milestone 6 — Performance and UI

- [ ] stage latency instrumentation
- [ ] memory/VRAM metrics
- [ ] FastAPI service
- [ ] single-container OfflineRAG application image
- [ ] Qdrant Local standalone profile
- [ ] `/data` + `/models` volume contracts
- [ ] retrieval inspector
- [ ] citation source viewer
- [ ] evaluation dashboard

**Release criterion:** a reviewer can interactively compare retrieval modes and inspect evidence flow.

## Milestone 7 — Portfolio release

- [ ] public demo corpus instructions
- [ ] benchmark methodology page
- [ ] final ablation table
- [ ] architecture diagram
- [ ] demo video/GIF
- [ ] setup guide
- [ ] host-Ollama deployment guide
- [ ] strict-offline verification report
- [ ] known limitations
- [ ] CI regression checks

**Release criterion:** repository supports all public quality/security/performance claims with reproducible evidence.

## Post-v1 candidates

Only prioritize these when failures justify them:

- learned sparse retrieval / SPLADE;
- ColBERT-style late interaction;
- table-specific retrieval;
- multimodal page reasoning;
- query decomposition for true multi-hop tasks;
- document version diffing;
- incremental indexing GC / lifecycle tooling;
- corpus-level access policies;
- GraphRAG / knowledge graph if relation-heavy benchmarks warrant it.
