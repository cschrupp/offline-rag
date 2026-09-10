# Detailed Implementation Slices

This document converts the architecture into incremental, testable implementation slices. Each slice should leave the repository in a working state. Avoid building multiple major layers simultaneously: the evaluation harness depends on being able to attribute improvements and regressions to individual changes.

**Implementation status:** Slices 0–3 are implemented. Planned next: 4 BM25 → 5 RRF → 6 rerank → 7 expansion → 8+ generation. Authoritative Slice 0–3 notes live under `docs/slice0_contracts.md` … `docs/slice3_dense_retrieval.md`.

---

# Slice 0 — Repository foundation and system contracts

**Status:** done.

## Objective

Establish the project skeleton, configuration system, stable data contracts, local logging, and test strategy before integrating large models or databases.

## Deliverables

- Python package layout under `src/offline_rag/`.
- `pyproject.toml` created during implementation.
- Configuration loading and validation.
- Pydantic/dataclass schemas for:
  - Document;
  - Chunk;
  - RetrievalCandidate;
  - RetrievalResult;
  - Citation;
  - QueryTrace;
  - ExperimentConfig;
  - EvaluationResult.
- Stable ID policy.
- Structured local logging.
- Unit-test framework.
- CLI shell (`offline-rag`); later slices filled real commands beyond doctor.

## Implemented commands (through Slice 3)

```text
offline-rag doctor
offline-rag ingest ...
offline-rag chunk ...
offline-rag chunk inspect ...
offline-rag provision embedding
offline-rag index ...
offline-rag index inspect ...
offline-rag retrieve ...
offline-rag eval retrieve ...
```

`query` / generation and broader `eval run|compare` remain later slices.

## Key design decision

Every chunk and document needs deterministic provenance. Do not use random UUIDs as the only identity if the same corpus may be rebuilt.

A possible chunk ID input:

```text
hash(document_content_hash, parser_version, chunker_config_hash, page, section_path, chunk_index, chunk_text_hash)
```

## Tests

- schema validation;
- config loading;
- hash stability;
- serialization round-trip;
- invalid config rejection.

## Exit criteria

- `pytest` passes with no model dependencies.
- A sample `Document` and `Chunk` can be serialized and restored without information loss.
- Configuration overrides are explicit and traceable.

## Portfolio evidence

Clean architecture starts before model integration. This slice demonstrates that the system is designed as an engineering project rather than a notebook.

---

# Slice 1 — Document parsing and normalized ingestion

**Status:** done.

## Objective

Create a deterministic document ingestion path using Docling and normalize the parser output into project-owned schemas.

## Deliverables

- parser adapter interface;
- Docling implementation;
- TXT/Markdown fallback path where appropriate;
- extraction of page/section provenance;
- normalized document representation;
- ingestion report containing warnings and parser statistics;
- local corpus manifest.

## Important constraint

Do not leak Docling-specific objects across the application boundary. Convert parser output into project-owned domain models.

## Metadata to preserve where available

- source filename;
- logical title;
- page number;
- headings / section path;
- table/list/code block type;
- document order;
- parser warnings;
- OCR use;
- raw source hash.

## Tests

Fixture corpus should include:

- born-digital PDF;
- scanned PDF if practical;
- TXT;
- Markdown;
- document with headings;
- document with table;
- repeated ingestion of the same file.

## Exit criteria

- repeated ingestion yields the same normalized content IDs when config is unchanged;
- page provenance survives normalization;
- parser failures are explicit rather than silently ignored;
- ingestion can run with network disabled.

---

# Slice 2 — Structure-aware chunking and parent-child model

**Status:** done. Implemented as a project-owned structure-aware chunker over ParsedDocument (not a Docling chunker adapter).

## Objective

Produce searchable child chunks and context-bearing parent units while preserving document hierarchy.

## Deliverables

- project-owned structure-aware chunker (not Docling HybridChunker);
- configurable target/max token counts (tiktoken);
- parent-child relationships;
- neighbor relationships or ordering metadata;
- token accounting;
- chunk inspection CLI/report.

## Design rules

1. Search units should be small enough for retrieval precision.
2. Generation context should not be constrained to the exact child chunk.
3. Headings and section paths should travel with child content.
4. Tables should not be blindly split by character count.
5. Chunk configuration must be recorded in the corpus manifest.

## Tests

- chunk boundaries are deterministic;
- every child resolves to a document;
- every parent ID resolves;
- token limits are respected;
- page information remains valid after chunking;
- empty/duplicate chunks are rejected or normalized.

## Exit criteria

A document can be parsed, chunked, inspected, and reconstructed into an ordered sequence with intact provenance.

---

# Slice 3 — Dense retrieval baseline

**Status:** done. See `docs/slice3_dense_retrieval.md` for the locked contracts (plain-v1 text, Qwen3-Embedding-0.6B, Qdrant Local, IndexState, `retrieve`, `eval retrieve`).

## Objective

Establish the first measurable retrieval baseline before implementing hybrid search.

## Deliverables

- embedding interface;
- one local embedding backend;
- Qdrant adapter;
- index creation and persistence;
- metadata filtering;
- dense `top_k` retrieval;
- query trace for dense candidates;
- minimal retrieval benchmark runner.

## Benchmark before proceeding

Even with a tiny manually labeled dataset, record:

- Recall@1;
- Recall@5;
- Recall@10;
- MRR;
- median retrieval latency.

These become the baseline against which later components are judged.

## Tests

- embeddings are deterministic enough for the selected backend/config;
- vectors match expected dimensionality;
- metadata round-trips through Qdrant;
- deleted/reindexed documents do not leave unintended duplicates;
- retrieval respects metadata filters.

## Exit criteria

A query returns ranked chunks with stable provenance and a benchmark report can be generated.

---

# Slice 4 — Lexical retrieval baseline

## Objective

Add a lexical retrieval path independent from dense retrieval.

## Deliverables

- lexical retriever interface;
- BM25 implementation;
- tokenization policy documented;
- lexical candidate trace;
- separate lexical benchmark.

## Why separate first

Before hybridization, measure BM25 independently. This reveals where lexical search beats dense search and creates the evidence for combining them.

## Query categories to inspect

- acronyms;
- model numbers;
- exact phrases;
- units;
- part numbers;
- standards/section identifiers;
- numeric lookup.

## Exit criteria

Dense and BM25 can be benchmarked on the same gold set and compared by query category.

---

# Slice 5 — Hybrid retrieval and rank fusion

## Objective

Combine dense and lexical results using Reciprocal Rank Fusion.

## Deliverables

- fusion interface;
- RRF implementation;
- deduplication policy keyed by stable chunk ID;
- fused trace showing source ranks;
- configurable dense/sparse top-k;
- hybrid benchmark.

## Query trace example

```text
chunk_123
  dense_rank: 3
  sparse_rank: 11
  rrf_score: ...
  fused_rank: 2
```

## Tests

- deterministic RRF ordering for fixed inputs;
- duplicate chunk IDs collapse correctly;
- a candidate present in only one retriever remains eligible;
- metadata filters are consistently applied.

## Exit criteria

Hybrid retrieval produces measurable results and an ablation table can compare dense vs BM25 vs hybrid.

---

# Slice 6 — Cross-encoder reranking

**Reserved after Slice 5.** Intentionally excluded from Slice 3 so dense embedding/index
quality stays separable from reranker gains. Model not locked until Slice 6 design interview
(compare local options on multilingual ability, context length, latency, deploy size).

## Objective

Improve ranking quality by reranking the fused candidate set with a local cross-encoder
(candidate pool e.g. top 30–100 → final top 5–10).

## Deliverables

- reranker interface mirroring embedders (`FakeReranker` + provisioned `CrossEncoderReranker`);
- local-only loading, deterministic config identity, no runtime downloads;
- batch reranking;
- configurable candidate and output sizes;
- timing instrumentation;
- benchmark delta vs hybrid-only (quality + latency).

## Required analysis

Measure both quality and latency. Report whether reranking improves:

- MRR;
- nDCG@10;
- Recall at the final evidence cut;
- downstream answer accuracy once generation exists.

## Exit criteria

The project can state quantitatively whether reranking is worth the added latency on the chosen corpus.

---

# Slice 7 — Context expansion and evidence assembly

## Objective

Use precise child retrieval while providing larger coherent context to the generator.

## Deliverables

- context assembler;
- parent expansion;
- neighbor expansion as configurable strategy;
- context budget enforcement;
- duplicate/overlap suppression;
- evidence-block formatting;
- context trace.

## Policies to evaluate

- child only;
- whole parent;
- child + N neighbors;
- parent clipped to token budget.

## Exit criteria

The system can show exactly which searchable chunks caused which context blocks to be sent to the generator.

---

# Slice 8 — External local generation boundary and structured citations

## Objective

Produce grounded answers from explicitly assembled local evidence while keeping generative model execution outside the application process/container.

## Deliverables

- project-owned generation interface;
- OpenAI-compatible local client implementation;
- Ollama-on-host default configuration;
- endpoint and model preflight checks;
- strict-offline endpoint allowlist;
- approved-local-model manifest/allowlist;
- structured answer schema;
- citation IDs emitted by the model or generated through controlled post-processing;
- deterministic citation validator;
- answer trace.

## Generator contract

The model should be instructed to:

- use only supplied evidence for corpus claims;
- distinguish evidence from instructions;
- avoid inventing citations;
- abstain when context is insufficient;
- cite evidence IDs for factual claims.

Application code must depend on the generic generation interface, not on Ollama-specific client calls. Ollama-specific health/model inspection logic, if needed, belongs in preflight/adapter code.

## Strict-offline preflight

Before a strict-offline query, verify at minimum:

1. configured endpoint is explicitly approved;
2. configured model identifier is in the local model allowlist/manifest;
3. no cloud fallback is configured by OfflineRAG;
4. retrieval models are available locally;
5. remote tracing/judge integrations are disabled.

## Citation validation

Before returning an answer, verify:

1. cited ID exists;
2. cited ID was retrieved;
3. cited ID was included in context.

A failure should be visible, not silently repaired without trace.

## Exit criteria

A user can run the generator outside OfflineRAG (Ollama by default), ask a question through the application, and receive an answer with resolvable document/page evidence. Switching to another compatible local endpoint requires configuration only.

# Slice 9 — Evaluation harness v1: deterministic retrieval metrics

## Objective

Make evaluation a reusable subsystem with a stable dataset schema and experiment output format.

## Deliverables

- `gold.jsonl` schema;
- benchmark loader;
- relevance labels;
- Recall@k;
- Precision@k;
- MRR;
- nDCG@k;
- hit rate;
- per-category metrics;
- experiment result serialization;
- comparison report.

## Dataset record minimum

```json
{
  "id": "q_001",
  "question": "...",
  "categories": ["numeric", "exact_keyword"],
  "relevant_documents": ["doc_a"],
  "relevant_chunks": ["chunk_a"],
  "answerable": true
}
```

## Experiment metadata

Record at minimum:

- git commit;
- timestamp;
- corpus manifest hash;
- parser/chunker config;
- embedding model;
- sparse retriever config;
- fusion config;
- reranker config;
- top-k values;
- hardware summary;
- runtime versions.

## Exit criteria

Running two experiment configs yields directly comparable machine-readable and human-readable results.

---

# Slice 10 — Evaluation harness v2: generation and citation evaluation

## Objective

Measure the generator independently from retrieval and distinguish deterministic checks from semantic judge metrics.

## Deliverables

- reference answer/fact schema;
- exact/numeric answer checks where possible;
- citation resolvability metric;
- citation retrieved-set metric;
- citation context-set metric;
- optional local semantic judge adapter;
- faithfulness/correctness/completeness scoring pipeline;
- generation benchmark report.

## Critical rule

Never collapse retrieval and generation into one score only. Always preserve enough information to answer:

> Did retrieval fail, or did generation fail despite having the correct evidence?

## Exit criteria

A failed answer can be classified at least as retrieval failure, evidence-assembly failure, citation failure, or generation failure.

---

# Slice 11 — Abstention and evidence sufficiency

## Objective

Prevent unsupported answers and quantify the cost of refusal thresholds.

## Deliverables

- negative/unanswerable dataset split;
- deterministic retrieval-confidence features;
- abstention policy;
- false-answer metric;
- false-refusal metric;
- threshold sweep report.

## Candidate features

- top reranker score;
- score margin;
- number of high-confidence chunks;
- cross-retriever agreement;
- evidence diversity;
- metadata match quality.

An LLM relevance grader may be evaluated later, but do not require it initially.

## Exit criteria

The system has a measured operating point balancing useful answers against unsupported generation.

---

# Slice 12 — Conditional LangGraph retrieval recovery

## Objective

Introduce agentic behavior only where the baseline retrieval pipeline demonstrably fails.

## Initial graph

```text
START
  |
  v
normalize query
  |
  v
retrieve -> fuse -> rerank
  |
  v
evidence sufficient?
  |               |
 yes              no
  |                |
  |           rewrite query
  |                |
  |           retry retrieval
  |                |
  +--------+-------+
           |
           v
        generate
           |
           v
  citation validation
           |
           v
          END
```

## Deliverables

- LangGraph state model;
- bounded retry count;
- query rewriter;
- loop termination conditions;
- retry traces;
- evaluation comparing agentic vs non-agentic pipeline.

## Exit criteria

The agentic path must show measurable benefit on at least one failure category before being enabled by default.

---

# Slice 13 — Prompt-injection and security harness

## Objective

Treat retrieved documents as untrusted input and prove that the RAG control plane is not governed by document instructions.

## Deliverables

- adversarial document fixtures;
- indirect prompt-injection test cases;
- system/document delimiter policy;
- read-only retrieval tool boundary;
- network-disabled runtime test where practical;
- maximum graph iteration policy;
- citation manipulation tests;
- optional NeMo Guardrails integration after deterministic controls.

## Attack classes

- “ignore previous instructions” inside source text;
- fake `SYSTEM:` blocks;
- instructions to reveal prompts;
- instructions to fabricate citations;
- instructions to execute shell commands;
- instructions to access arbitrary files;
- instructions to suppress contradictory documents.

## Exit criteria

The adversarial suite runs automatically and the portfolio documentation reports pass/fail criteria without claiming absolute security.

---

# Slice 14 — Performance and resource benchmark harness

## Objective

Measure the local execution cost of each pipeline stage.

## Deliverables

- stage timers;
- p50/p95 aggregation;
- parsing throughput;
- embedding throughput;
- index build time;
- Qdrant retrieval timing;
- reranking timing;
- generation TTFT and tokens/sec;
- RAM/VRAM capture where feasible;
- benchmark machine profile.

## Required comparison

Every quality-improving feature should eventually have a quality-vs-cost view.

Example:

```text
reranker ON:
  MRR +8.1%
  p50 +145 ms
  VRAM +1.2 GB
```

## Exit criteria

The README can present at least one defensible quality/latency trade-off.

---

# Slice 15 — Developer API and single-container application packaging

## Objective

Expose the RAG engine through a stable local API and package the application as one Docker container while leaving generative inference external.

## Deliverables

- FastAPI app;
- `/health`;
- `/ingest`;
- `/query`;
- `/documents`;
- `/trace/{id}`;
- `/eval/run` or CLI-first evaluation boundary;
- API schemas;
- static UI serving strategy;
- standalone Qdrant Local persistence under `/data/qdrant`;
- `/data` persistent volume contract;
- `/models` read-only retrieval-model volume/cache contract;
- Dockerfile for OfflineRAG application only;
- Compose/example run profile that connects to host Ollama;
- Linux `host-gateway` documentation;
- `offline-rag doctor` checks for generation endpoint, model approval, model files, storage permissions, and offline-mode configuration.

## Deployment contract

The application image must **not** contain the generative LLM weights or require an embedded LLM server. Default generation is provided by host Ollama through the OpenAI-compatible endpoint.

Expected topology:

```text
Host Ollama :11434
       ^
       |
OfflineRAG container :8080
  + Qdrant Local
  + embedding/reranker runtime
  + API/UI/evaluation
       |
  /data + /models
```

## Security default

Bind the application to localhost unless the user explicitly configures network exposure. In strict-offline mode, refuse generation endpoints or model identifiers that are not explicitly approved.

## Exit criteria

The backend can be used from a CLI and browser UI through the same service layer, and the entire OfflineRAG application starts as one container while using an independently running local Ollama model.

# Slice 16 — Portfolio demo UI

## Objective

Expose the internals that demonstrate engineering value rather than hiding everything behind a chat bubble.

## Required views

### Query view

- question;
- final answer;
- citations;
- source preview.

### Retrieval inspector

- dense candidates;
- lexical candidates;
- fusion rank;
- reranker score;
- final evidence;
- query rewrite if triggered.

### Pipeline switcher

Allow controlled comparison of:

- dense;
- BM25;
- hybrid;
- hybrid + reranker;
- full agentic recovery.

### Evaluation dashboard

- aggregate retrieval metrics;
- metrics by query category;
- experiment comparison;
- latency distribution summary;
- abstention performance;
- adversarial test status.

## Exit criteria

A reviewer can understand the system's differentiators in under two minutes without reading the source code.

---

# Slice 17 — Regression CI

## Objective

Prevent retrieval-quality regressions from being hidden by implementation changes.

## Deliverables

- small CI-safe benchmark subset;
- baseline metrics artifact;
- configurable regression thresholds;
- report attached to pull requests or CI logs;
- deterministic tests that do not require a large generator when possible.

## Example gates

- fail if Recall@5 drops more than an agreed tolerance;
- fail if citation resolvability < 100%;
- fail if adversarial deterministic tests fail;
- warn if p95 retrieval latency increases above threshold.

## Exit criteria

A change to chunking, retrieval, or ranking can automatically show whether it helped or hurt the benchmark.

---

# Slice 18 — Portfolio release package

## Objective

Turn the functioning project into a compelling public artifact.

## Deliverables

- polished README;
- architecture diagram;
- benchmark methodology;
- benchmark results;
- ablation table;
- demo video or GIF;
- public sample corpus instructions;
- reproducible setup instructions;
- hardware profiles;
- known limitations;
- roadmap;
- interview talking points.

## Exit criteria

The repository can support the following claims with evidence:

1. The core path runs locally/offline.
2. Hybrid retrieval outperforms at least one single-retriever baseline on the chosen benchmark, or the project clearly reports if it does not.
3. Reranking has a quantified effect.
4. Retrieval and generation failures are measured separately.
5. Citations are provenance-validated.
6. The system has an explicit abstention mechanism.
7. Indirect prompt-injection behavior is tested.
8. Quality/latency trade-offs are measured.

---

# Recommended implementation order summary

```text
Foundation
  -> ingestion
  -> chunking
  -> dense baseline
  -> BM25 baseline
  -> hybrid/RRF
  -> reranker
  -> context expansion
  -> local generation/citations
  -> deterministic eval harness
  -> generation/citation eval
  -> abstention
  -> LangGraph recovery
  -> security tests
  -> performance benchmarks
  -> API
  -> UI
  -> CI
  -> portfolio release
```

The project should resist the temptation to jump directly to LangGraph, multiple agents, or a polished UI. The strongest development narrative is an evidence-based progression from a measurable baseline to increasingly capable retrieval.
