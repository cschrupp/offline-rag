# Development Guide

## 1. Development philosophy

Build the project as a sequence of measurable systems, not a sequence of framework integrations.

The preferred loop is:

```text
baseline -> observe failure -> form hypothesis -> implement change -> benchmark -> keep/revert
```

## 1b. Current local pipeline (Slices 0–8)

```bash
uv sync
uv run python scripts/provision_docling.py
uv run python scripts/provision_tiktoken.py
# optional for real dense / rerank quality:
# uv run offline-rag provision embedding
# uv run offline-rag provision reranker

offline-rag ingest <paths> --corpus <name>
offline-rag chunk --corpus <name>
offline-rag index --corpus <name>
offline-rag index lexical --corpus <name>
offline-rag retrieve --corpus <name> --query "..."
offline-rag retrieve lexical --corpus <name> --query "..."
offline-rag retrieve hybrid --corpus <name> --query "..."
offline-rag retrieve hybrid-rerank --corpus <name> --query "..."
offline-rag retrieve hybrid-rerank-context --corpus <name> --query "..."
offline-rag query --corpus <name> --query "..."
offline-rag eval retrieve --dataset <dir> --corpus <name>
offline-rag eval retrieve --method lexical --dataset <dir> --corpus <name>
offline-rag eval retrieve --method hybrid --dataset <dir> --corpus <name>
offline-rag eval retrieve --method hybrid-rerank --dataset <dir> --corpus <name>
offline-rag eval retrieve --method hybrid-rerank-context --dataset <dir> --corpus <name>
offline-rag eval compare --a <result-a.json> --b <result-b.json> [--json]
offline-rag eval query --dataset <dir> --corpus <name>
# Milestone 4 (9A–9E done; 9F pilot next):
# offline-rag gold propose|pool|prelabel|review|finalize|status
offline-rag doctor --corpus <name>
```

`offline-rag query` runs grounded generation via Slice 7 context assembly. Retrieval ablation remains under `retrieve` / `eval retrieve` / `eval compare`. Prefer GoldDataset v1 datasets (`offline-rag-gold-v1`); legacy `relevant_chunk_ids` gold still loads. Generation READY requires approved endpoint/model allowlists and a live OpenAI-compatible `/models` probe. Authoring READY (Slice 9A) is config + privacy only — no live probe; `doctor` reports the Authoring section. `offline-rag gold propose` (Slice 9B) performs one authorized proposal attempt per sampled seed. `offline-rag gold pool` (Slice 9C) builds `candidate-pooling-v1` pools from pending SilverCases (retrieval-only; no LLM). `offline-rag gold prelabel` (Slice 9D) runs blind double-pass local relevance judging (silver-only). `offline-rag gold review` / `gold finalize` (Slice 9E) provide localhost human adjudication and fail-closed GoldDataset publication.

Milestone 4 offline gold authoring (next: Slice **9F**) builds private-corpus gold locally; see `docs/slice9e_human_review.md`, `docs/slice9d_relevance_prelabel.md`, `docs/slice9c_candidate_pooling.md`, `docs/slice9b_gold_propose.md`, `docs/slice9a_gold_authoring.md`, and `docs/milestone4_offline_gold_authoring.md`. Do not treat silver/authoring drafts as gold.

For CI-scale dense/rerank/generation tests, set `indexing.embedding.implementation: fake` and/or `reranker.implementation: fake`, and inject `FakeGenerator` in unit tests. Do not rely on FakeEmbedder / FakeReranker / FakeGenerator for portfolio quality claims.

## 2. Keep the core path simple

Do not add an agent, judge model, new database, or more advanced retrieval method until the existing benchmark shows a failure that the change is intended to address.

## 3. Configuration discipline

All material experiment variables should live in configuration rather than hard-coded values.

Record at least:

- parser;
- chunker parameters;
- embedding model;
- sparse method;
- retriever top-k;
- fusion method;
- reranker model;
- reranker input/output k;
- context policy;
- generator model;
- prompt version;
- abstention policy;
- graph retry count.

## 4. Data/version discipline

Treat the corpus as versioned data.

A corpus manifest should record:

- source files and hashes;
- parser version;
- parser config;
- chunker version/config;
- number of documents;
- number of chunks;
- embedding/index build metadata.

Evaluation results are not comparable if they silently use different corpus versions.

## 5. Stable interfaces

Prefer project-owned protocols/ABCs for:

- parser;
- chunker;
- embedder;
- dense store;
- sparse retriever;
- fusion;
- reranker;
- generator;
- judge.

Do not pass framework-native objects across multiple layers.

## 6. Testing pyramid

### Unit tests

Fast, no large models.

Examples:

- ID generation and config hashes;
- structure-aware chunking with FakeTokenCounter;
- FakeEmbedder + dense index reuse / no-op;
- Recall/Precision/HitRate/nDCG/MRR math and GoldDataset identity;
- citation validation (future);
- config validation;

Real Docling PDF and optional real Qwen embedding loads belong in dedicated integration tests / provisioned environments.
- metric calculations;
- chunk mapping.

### Integration tests

Small local models/fixtures where possible.

Examples:

- parse -> chunk;
- chunk -> index (embed + Qdrant Local) -> retrieve;
- retrieve -> rerank;
- query -> citation validation.

### Regression tests

Small gold benchmark subset.

### Security tests

Adversarial documents and queries.

### Performance tests

Not part of every unit-test run; record separately on a documented benchmark machine.

## 7. Observability

Every query trace should have a trace ID and stage timings.

Suggested stages:

- query normalization;
- dense retrieval;
- sparse retrieval;
- fusion;
- reranking;
- context assembly;
- evidence grading;
- query rewriting;
- generation;
- citation validation.

Store enough metadata to reproduce why the answer occurred without logging sensitive data by default in a future multi-user deployment.

## 8. Model and inference management

Do not commit model weights.

Maintain two distinct model categories:

### Retrieval models — application-owned

Embedding and reranker models are part of the retrieval experiment definition. Provision their weights locally and mount/cache them under the documented `/models` contract. They must support local-only loading in strict-offline mode.

### Generative model — external local runtime

Do not package generator weights or an inference daemon into the OfflineRAG image. Use a project-owned OpenAI-compatible client and treat Ollama on the host as the default provider.

The generator configuration must include:

- base URL;
- model identifier;
- timeout;
- approved endpoint list;
- approved local model list/manifest.

Keep three conceptual hardware profiles:

### Minimum

- CPU-capable/low-resource Ollama model;
- small local embedding model;
- optional reranker disabled.

### Recommended workstation

- local Ollama using available GPU acceleration;
- local embedding model;
- local reranker;
- generator size chosen according to hardware.

### High-throughput local server

- vLLM, llama.cpp server, or another approved OpenAI-compatible runtime;
- larger generator where useful;
- larger reranker only when benchmark gains justify it.

Actual models and requirements should be benchmarked and documented at release time.

## 9. Prompt versioning

Treat prompts as code.

Each material prompt should have:

- a named file;
- a version identifier or git-traceable history;
- tests where appropriate;
- experiment metadata linking results to the prompt version.

## 10. Avoid hidden network dependencies

During implementation, some libraries may attempt model downloads, telemetry, remote tracing, or cloud fallback.

Separate **provisioning** from **runtime**.

Before claiming strict offline operation:

- provision embedding/reranker models locally;
- provision the generator in the external local inference runtime;
- disable runtime model auto-downloads where supported;
- configure retrieval-model loaders for local-only access;
- disable remote tracing/telemetry;
- reject unapproved generation endpoints;
- reject generator model identifiers not present in the local allowlist/manifest;
- run offline integration tests on a disconnected or egress-restricted host;
- record the exact runtime profile used for the claim.

Do not equate `localhost` with guaranteed offline execution: a local daemon may itself proxy to a cloud model. The approved-model manifest is therefore part of the offline contract.

## 11. Benchmark hygiene

Do not tune on the final test set indefinitely.

A mature harness should eventually have:

- development set;
- held-out test set;
- adversarial set;
- negative set.

For an early portfolio project, a single carefully labeled gold set is acceptable, but document that limitation.

## 12. Pull-request questions

For every significant retrieval change, answer:

1. What failure is this intended to solve?
2. Which benchmark queries exercise that failure?
3. What changed in Recall/MRR/nDCG?
4. What changed in latency/resources?
5. Did any query category regress?
6. Does the change increase operational complexity?
7. Is the complexity justified by the measured gain?

## 13. Definition of done for a feature

A feature is not done when code runs. It is done when:

- code path is tested;
- config is documented;
- trace output is available;
- benchmark impact is known when applicable;
- failure behavior is defined;
- README/docs reflect user-visible behavior.
