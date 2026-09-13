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
- [x] Minimal local retrieve CLI (`offline-rag retrieve`; grounded `query` arrives in Milestone 3 / Slice 8)

**Release criterion:** reproducible Recall@k/MRR baseline on a small gold set.

**Status:** Slice 0–3 dense baseline done. See Milestone 2 for Slice 4+.

## Milestone 2 — Modern retrieval stack

- [x] BM25 / lexical baseline (Slice 4; project-owned inverted index + bm25-okapi-v1)
- [x] Hybrid retrieval / RRF fusion (Slice 5; query-time rrf-v1 over dense+lexical)
- [x] Cross-encoder reranking over fused pools (Slice 6; BGE bge-reranker-v2-m3 + FakeReranker)
- [x] Parent/neighbor context expansion (Slice 7; hybrid-rerank-context + ContextExpander)
- [ ] Ablation report (Dense → +BM25 → +RRF → +reranker → +expansion)

**Release criterion:** measured comparison of dense, BM25, hybrid, hybrid+reranker, and +context assembly.

**Status:** Slice 7 hybrid-rerank-context implemented. Ablation report still open.

## Milestone 3 — Grounded local QA

- [x] OpenAI-compatible generation client
- [x] Ollama-on-host default profile
- [x] strict-offline endpoint/model preflight
- [x] structured answer schema
- [x] citation provenance
- [x] citation validator
- [x] abstention path

**Release criterion:** grounded answer with resolvable source citations and explicit insufficient-evidence output.

**Status:** Slice 8 grounded generation implemented (`offline-rag query` / `eval query`).

### Validated end-to-end smoke profile

Slice 8 was validated end-to-end on the `ics_modules` corpus using the
following composed profile:

- Dense passage: `plain-v1`
- Dense query: `model-query-prompt-v1`
- Dense searchable units: `exclude-heading-only-v1`
- Lexical: `plain-v1`
- Fusion: `rrf-v1`
- Reranker: `plain-pair-v1`
- Context: Slice 7 baseline contract
- Generation prompt: `prompt-grounded-provenance-v2`
- Output: `grounded-answer-v1`
- Reasoning: `direct-output-v1`
- Recovery: `no-retry-v1`

Result: `PROVENANCE-PROMPT-MATERIAL`.

Identity-dependent Module 1 and Module 2 queries became grounded answers
when trusted document/section provenance was exposed to generation, while
self-contained answerability and genuine abstention behavior were preserved.
Retrieval/context inputs were identical across the generation A/B.

`model-query-prompt-v1`, `exclude-heading-only-v1`, and
`prompt-grounded-provenance-v2` are validated experimental candidates,
not defaults. Historical/base contracts remain unchanged pending broader
retrieval/generation evidence under the Slice 9 harness (and Slice 10
for generation semantics). `prompt-grounded-v1` remains the generation
control/default.

Reproduce the smoke profile by composing existing orthogonal overlays
(`base` + `dense_no_heading_peers` + `generation_provenance_prompt`); do
not treat that composition as a promoted default.

See [`docs/memory_query_heading_provenance.md`](docs/memory_query_heading_provenance.md)
for the detailed retrieval-heading, query-contract, and
generation-provenance investigation and A/B results.

## Milestone 4 — Evaluation platform

- [x] deterministic retrieval metrics / GoldDataset v1 (Slice 9)
- [x] shared retrieval-eval result artifact + `eval compare` (Slice 9)
- [x] category aggregates on retrieval-eval results (Slice 9)
- [ ] generation metrics (Slice 10)
- [ ] citation metrics (Slice 10)
- [ ] negative set
- [ ] synthetic expansion
- [ ] experiment registry
- [ ] regression benchmark subset / large corpus gold labeling

**Release criterion:** one command generates a comparable experiment artifact and report.

**Status:** Slice 9 retrieval measurement platform done (`eval retrieve` + `eval compare`). Ablation reports and generation/citation semantic metrics remain open.

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
