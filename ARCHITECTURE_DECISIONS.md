# Architecture Decisions

This file records the reasoning behind major decisions so future development does not accidentally reverse a choice without understanding its purpose.

## ADR-001 — Fully local core path

**Decision:** Normal runtime must support operation with no external inference or embedding APIs.

**Reasoning:** Privacy is part of the product identity, not merely a deployment option. It also demonstrates local-inference integration and explicit runtime trust boundaries.

**Consequence:** Model provisioning may require internet access initially, but runtime behavior must have a clearly documented strict-offline mode. Communication to an explicitly approved local inference endpoint is permitted.

---

## ADR-002 — Docling for initial document intelligence

**Decision:** Use Docling as the first parser and structure-aware document layer.

**Reasoning:** Technical PDFs often contain headings, tables, lists, captions, page structure, and scanned content that are degraded by plain text extraction.

**Constraint:** Normalize Docling output into project-owned models. Do not let Docling types become the system's domain model.

---

## ADR-003 — Qdrant over an in-memory-only vector index

**Decision:** Use local Qdrant as the primary dense/hybrid search store.

**Reasoning:** The project needs persistent collections, metadata filtering, stable payloads, document deletion/update, and a credible production-like retrieval layer.

**Alternative:** FAISS can remain useful for microbenchmarks, but should not define the main persistence API.

---

## ADR-004 — Hybrid retrieval is a target, not the baseline

**Decision:** Implement and measure dense and BM25 independently before combining them.

**Reasoning:** The portfolio value comes from proving why hybrid retrieval is needed rather than simply claiming that it is best practice.

---

## ADR-005 — RRF as the first fusion method

**Decision:** Use Reciprocal Rank Fusion before score-weighted fusion.

**Reasoning:** Dense and lexical scores are not naturally calibrated to the same scale. RRF produces a strong, interpretable baseline without score normalization.

**Future:** Weighted fusion may be evaluated if the benchmark indicates a benefit.

---

## ADR-006 — Reranking as a separate stage

**Decision:** Candidate generation and reranking remain separate abstractions.

**Reasoning:** Fast retrievers should maximize recall; the cross-encoder should optimize ranking quality on a smaller candidate pool. Keeping them separate enables clean latency/quality ablations.

---

## ADR-007 — Parent-child retrieval

**Decision:** Search small chunks, generate from expanded context.

**Reasoning:** Large chunks hurt search precision; tiny chunks often lack the context needed by a generator. Parent-child retrieval separates these two requirements.

---

## ADR-008 — LangGraph only for conditional recovery

**Decision:** The normal happy path remains deterministic. LangGraph coordinates bounded query rewrite/retry only when retrieval is insufficient.

**Reasoning:** Agent loops introduce latency and nondeterminism. They should be justified by benchmark improvements.

---

## ADR-009 — OpenAI-compatible generation boundary

**Decision:** Use a project-owned OpenAI-compatible client contract for generation. Ollama running outside the application container is the default deployment target; llama.cpp, vLLM, and other approved local compatible servers remain swappable.

**Reasoning:** The RAG engine should not be coupled to one inference server. Keeping model execution outside the application image reduces GPU/runtime packaging complexity and makes the deployment boundary explicit.

**Consequence:** The application must provide endpoint/model preflight validation and must not rely on Ollama-specific semantics in core retrieval code.

---

## ADR-010 — Evaluation harness is project-owned

**Decision:** Core retrieval metrics, citation provenance checks, security tests, and experiment tracking are implemented in project code. External libraries may supplement but not define the evaluation architecture.

**Reasoning:** Standard IR metrics are simple, deterministic, and critical enough to own. This also makes evaluation assumptions explicit.

---

## ADR-011 — Human gold set remains authoritative

**Decision:** Synthetic evaluation questions are stored and reported separately from human-authored gold questions.

**Reasoning:** Synthetic questions can be useful for coverage but can also favor the generation process that produced them.

---

## ADR-012 — Abstention is an explicit output state

**Decision:** `INSUFFICIENT_EVIDENCE` or an equivalent structured state is part of the application contract.

**Reasoning:** A system that always generates an answer cannot be trusted in technical work. Refusal thresholds should be tunable and measured.

---

## ADR-013 — Retrieved content is untrusted data

**Decision:** Retrieved documents never gain instruction priority because of their contents.

**Reasoning:** RAG introduces indirect prompt-injection risk. The control plane must remain outside the document text.

**Implementation implications:**

- evidence blocks are explicitly delimited;
- tools exposed to the model are minimal/read-only;
- the model does not receive arbitrary shell/filesystem/network tools;
- citation validation is deterministic;
- retries are bounded.

---

## ADR-014 — No GraphRAG or knowledge graph in v1

**Decision:** Defer graph-based retrieval.

**Reasoning:** Complexity is not justified until the benchmark demonstrates a recurring relation/multi-hop failure that hierarchical hybrid retrieval cannot solve.

---

## ADR-015 — No generator fine-tuning in v1

**Decision:** Use prompting, retrieval, and local model selection before fine-tuning.

**Reasoning:** Most initial quality problems in document QA are more likely retrieval/evidence problems than generator adaptation problems.

---

## ADR-016 — Traceability over hidden framework magic

**Decision:** Every query should be inspectable stage-by-stage.

**Reasoning:** The project is both a tool and a portfolio artifact. A reviewer should be able to see why an answer was produced and what evidence path led to it.
---

## ADR-017 — Single application container, external generation runtime

**Decision:** The flagship portfolio deployment packages OfflineRAG as one application container, but does not bundle the generative LLM or its inference runtime.

The container owns:

- FastAPI and static UI;
- Docling ingestion;
- embedding and reranker runtimes;
- Qdrant Local persistence;
- retrieval/orchestration;
- evaluation and tracing.

The host/local environment owns generation through Ollama by default.

**Reasoning:** This preserves one-command application deployment while avoiding an oversized image, duplicated GPU libraries, model-weight distribution, and inference-engine coupling.

**Consequence:** `/data` and `/models` are explicit persistent/mounted filesystem contracts. `/models` contains retrieval-model assets only in v1.

---

## ADR-018 — Strict offline mode uses explicit trust allowlists

**Decision:** Strict-offline mode validates both the generation endpoint and model identifier against explicit configuration/manifest allowlists. Retrieval models must load from local paths/cache without runtime downloads.

**Reasoning:** A localhost inference daemon can itself support cloud-backed models; checking only that the base URL is local is not sufficient to justify a strict offline claim.

**Consequence:** Offline verification includes configuration checks plus integration tests performed on a disconnected or egress-restricted host profile.

---

## ADR-019 — Qdrant Local for standalone, Qdrant server as scale-up path

**Decision:** The standalone portfolio profile uses Qdrant Local/embedded persistence inside the application container. A server-backed Qdrant adapter remains part of the interface contract for larger deployments.

**Reasoning:** Embedded persistence keeps the flagship demo genuinely single-container while preserving the same project-owned index abstraction for later scale-up.

---

## ADR-020 — Qwen3-Embedding-0.6B as Slice 3 dense baseline

**Decision:** Portfolio dense baseline uses `Qwen/Qwen3-Embedding-0.6B` at a pinned revision, 1024-d, L2-normalized, cosine similarity. CI uses `FakeEmbedder` without weights. Embedding text is plain chunk text (`plain-v1`) with no section/title decoration. Indexing is a separate `offline-rag index` stage over child chunks only; embeddings are content-addressed and reusable when vector semantics are unchanged.

**Reasoning:** A small, local-friendly embedding model keeps provisioning and offline runtime credible while remaining swappable. Separating FakeEmbedder from the portfolio model prevents CI from implying quality. Plain-v1 keeps embedding inputs auditable and avoids silent prompt-style decoration.

**Consequence:** Real quality runs require `offline-rag provision embedding` (or equivalent local directory). Runtime loads with `local_files_only=True` and never downloads.

---

## ADR-021 — Offline gold authoring is human-adjudicated and privacy-bounded

**Decision:** After Slice 9's retrieval evaluation harness, Milestone 4 adds a separate `gold_authoring` subsystem that builds private-corpus GoldDataset v1 artifacts using an approved local LLM as an annotation assistant. Final relevance labels require explicit human approval. Silver/authoring drafts are never accepted by `eval retrieve` as gold. Authoring does not reuse Slice 8 production generation prompt contracts or change `gencfg_` / grounded-answer defaults. Authoring endpoints fail closed unless explicitly allowlisted; default network policy is `localhost_only`, with optional later `private_network` wording that must not claim single-machine isolation when LAN inference is used.

**Reasoning:** Private technical corpora cannot be uploaded to cloud annotation or evaluation services without breaking the product's privacy identity. Automating proposal/pooling/pre-labeling makes gold construction practical, but model grades must not become ground truth. Keeping authoring separate from evaluation and from production generation prevents contract contamination and silent promotion of experimental retrieval/generation settings.

**Consequence:** Implementation proceeds strictly 9A→9H. Slices **9A** and **9B** are complete (`gold propose`); next is **9C** pooling. DeepEval/Ragas/Giskard/NotebookLM are not required architecture. Promotion of Arm H / query-prompt / provenance-v2 remains an explicit later decision (9H for retrieval contracts; Slice 10 for provenance-v2). Canonical plan: `docs/milestone4_offline_gold_authoring.md`. Notes: `docs/slice9a_gold_authoring.md`, `docs/slice9b_gold_propose.md`.
