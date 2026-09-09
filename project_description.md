# Project Description — OfflineRAG

## 1. Working title

**OfflineRAG — Evaluated Local RAG for Private Technical Knowledge**

The name is intentionally provisional. The architecture and documentation should not depend on branding.

## 2. Executive summary

OfflineRAG is a fully local retrieval-augmented generation platform for querying sensitive technical documents without sending documents, embeddings, prompts, retrieved context, or model requests to cloud services. The application is packaged independently from the generative model and talks to a local OpenAI-compatible inference endpoint, with Ollama as the default deployment target.

The project has two equally important goals:

1. Build a high-quality, extensible offline RAG system for real technical knowledge work.
2. Serve as a strong portfolio demonstration of retrieval engineering, LLM systems design, evaluation, local inference integration, deployment architecture, security controls, and experimental rigor.

The design rejects the common “PDF -> fixed chunks -> embeddings -> vector search -> LLM” baseline as insufficient for serious technical retrieval. Instead it combines structure-aware parsing, dense and lexical retrieval, rank fusion, reranking, hierarchical context expansion, local generation, citation validation, conditional query recovery, explicit abstention, and a first-class evaluation harness.

## 3. Problem statement

Organizations and engineers often possess valuable technical knowledge in manuals, papers, procedures, standards, reports, and text files that cannot be uploaded to external AI services. Local LLMs solve only the inference part of the problem. Reliable question answering still requires a document intelligence and retrieval system capable of:

- preserving document structure;
- handling exact technical terminology and identifiers;
- finding semantically related passages;
- ranking evidence correctly;
- providing enough surrounding context for reasoning;
- refusing unsupported questions;
- citing the underlying evidence;
- resisting instructions embedded in retrieved content;
- and proving, quantitatively, that architectural changes actually improve performance.

OfflineRAG addresses that full pipeline.

## 4. Primary objectives

### 4.1 Functional objective

Given a local corpus of supported documents and a natural-language query, the system should return a grounded answer supported by traceable citations to the indexed corpus, or explicitly abstain when evidence is insufficient.

### 4.2 Privacy objective

The full core path must be executable without network access after models and dependencies have been provisioned.

The following must remain local during normal operation:

- source documents;
- parsed document representations;
- chunks and metadata;
- dense embeddings;
- sparse index data;
- user queries;
- retrieved passages;
- reranker requests;
- LLM prompts and outputs;
- evaluation datasets and scores.

### 4.3 Retrieval objective

The system should support and benchmark multiple retrieval configurations:

- dense only;
- lexical only;
- hybrid dense + lexical;
- hybrid + reranking;
- optional query rewriting / retry.

### 4.4 Evaluation objective

Every material retrieval or generation change should be measurable against a reproducible benchmark corpus and query set.

### 4.5 Portfolio objective

A technical reviewer should be able to inspect the repository and see evidence of:

- clean system decomposition;
- typed interfaces and explicit contracts;
- IR metrics and ablation testing;
- model-agnostic local-inference integration;
- secure RAG design;
- latency/resource trade-off analysis;
- reproducible experiments;
- CI regression testing;
- and a polished interactive demo.

## 5. Secondary objectives

- Make backends swappable through configuration.
- Make the default application distribution a single Docker container while keeping the generative model outside that image.
- Keep generation behind an OpenAI-compatible local API boundary; use Ollama as the default host runtime without coupling the application to it.
- Support engineering-focused corpora without hard-coding a single domain.
- Provide enough observability to inspect the complete retrieval path for a query.
- Allow experiments to be repeated from configuration files.
- Make the project usable as a reusable local knowledge subsystem for future applications.

## 6. Non-goals for the first release

The first release should not attempt to solve every possible RAG problem.

Explicit non-goals:

- general web search;
- cloud LLM APIs in the core path;
- multi-agent autonomous research;
- knowledge graph construction;
- GraphRAG;
- fine-tuning foundation models;
- distributed search infrastructure;
- enterprise authentication and tenancy;
- arbitrary multimodal figure reasoning;
- editing source documents;
- unbounded filesystem or shell access by the model.

## 7. Target users

### 7.1 Primary user

A technical professional who needs to query a private or local document corpus and requires evidence-backed answers.

### 7.2 Secondary user

An AI/ML engineer evaluating retrieval approaches, embedding models, rerankers, context policies, or local inference configurations.

### 7.3 Portfolio reviewer

A recruiter, hiring manager, or technical interviewer who needs to understand the project quickly and verify that its claims are supported by measurable results.

## 8. Representative use cases

### 8.1 Exact technical lookup

> What is the maximum working pressure specified for tool X?

Requires lexical sensitivity to model names, units, identifiers, and numbers.

### 8.2 Semantic retrieval

> What conditions can produce unexpectedly high deployment tension?

Requires semantic matching across passages that may use different wording.

### 8.3 Cross-document comparison

> How do the operating recommendations differ between the 2018 and 2024 procedures?

Requires metadata filters, multiple evidence sources, and citation coverage.

### 8.4 Procedural synthesis

> Summarize the recommended pre-job checks for this operation and cite each source section.

Requires multiple chunks and controlled synthesis.

### 8.5 Unanswerable question

> What does the corpus say about a subject it never discusses?

Expected outcome: explicit insufficient-evidence response.

### 8.6 Adversarial document

A retrieved document contains text such as “ignore previous instructions.”

Expected outcome: the text is treated as untrusted document content, never as control-plane instruction.

## 9. Functional requirements

### FR-01 Document ingestion

The system shall ingest local documents and produce a normalized document representation with stable identifiers and provenance metadata.

Initial formats:

- PDF;
- TXT;
- Markdown.

Additional formats may be enabled through Docling after the core path is stable.

### FR-02 Structural metadata

Each searchable unit should retain, where available:

- document ID;
- source path or source label;
- title;
- page number;
- section/subsection hierarchy;
- parent chunk ID;
- chunk ordinal;
- content type;
- ingestion version;
- content hash.

### FR-03 Dense indexing

The system shall generate local dense embeddings and store/query them through Qdrant.

### FR-04 Lexical retrieval

The system shall provide a sparse/lexical retrieval path, initially BM25.

### FR-05 Hybrid fusion

The system shall combine dense and lexical ranked lists using a configurable fusion policy, initially Reciprocal Rank Fusion.

### FR-06 Reranking

The system shall optionally rerank fused candidates with a local cross-encoder.

### FR-07 Context assembly

The system shall support searching small child chunks while expanding selected evidence into parent and/or neighboring context before generation.

### FR-08 Grounded generation

The generator shall receive only explicitly assembled context plus trusted system/developer instructions.

### FR-09 Citation production

Generated answers shall reference stable evidence IDs that can be resolved back to document/page/chunk metadata.

### FR-10 Citation validation

The system shall verify that cited chunks:

1. exist;
2. were retrieved for the request;
3. were present in the generation context.

Semantic claim-support validation may be added as a separate evaluation step.

### FR-11 Abstention

The system shall expose an explicit insufficient-evidence path rather than forcing generation.

### FR-12 Conditional query recovery

If evidence quality is below a configured threshold, the system may rewrite/decompose the query and retry retrieval within a fixed iteration budget.

### FR-13 Evaluation

The system shall provide a reusable evaluation runner for retrieval, generation, citation, abstention, security, and performance metrics.

### FR-14 Experiment registry

Every benchmark run shall store enough configuration and environment metadata to reproduce or compare the experiment.

### FR-15 Debug trace

A query trace shall make it possible to inspect:

- normalized query;
- rewritten query, if any;
- dense candidates;
- lexical candidates;
- fusion result;
- reranker result;
- final generation context;
- generated answer;
- citations;
- grounding/abstention decisions;
- latency per stage.

## 10. Non-functional requirements

### NFR-01 Offline execution

Once required dependencies and model weights are available locally, normal operation must not require cloud or internet services. The application container may communicate with an explicitly approved local/host inference endpoint (for example host Ollama). Strict-offline mode must reject unapproved generation endpoints and model identifiers.

### NFR-02 Reproducibility

Evaluation runs should be deterministic where feasible. Generation evaluation should record model, quantization, temperature, seed (when supported), prompt version, and context policy.

### NFR-03 Modularity

Core interfaces should permit replacement of:

- parser;
- chunker;
- embedding model;
- lexical retriever;
- vector store;
- fusion strategy;
- reranker;
- generator;
- judge model.

### NFR-04 Testability

Each major layer shall be independently testable with synthetic fixtures before end-to-end integration.

### NFR-05 Observability

Structured traces and timings should be available without coupling the project to an external SaaS observability platform.

### NFR-06 Resource awareness

The system shall report relevant RAM, VRAM, index-size, throughput, and latency measurements during benchmark runs.

### NFR-07 Security

Retrieved content must be treated as untrusted data. The generation model must not receive arbitrary filesystem, shell, or network access.

## 11. Reference architecture

```text
                              HOST MACHINE

                  +-----------------------------+
                  | Ollama / local LLM server   |
                  | OpenAI-compatible endpoint  |
                  +--------------^--------------+
                                 |
                       approved local endpoint
                                 |
+--------------------------------+--------------------------------+
|                  OFFLINERAG APPLICATION CONTAINER               |
|                                                                 |
|  source docs -> Docling -> normalized structure/chunks          |
|                         |                                       |
|                 +-------+--------+                              |
|                 v                v                              |
|           dense embeddings     BM25                            |
|                 |                |                              |
|                 +-------+--------+                              |
|                         v                                       |
|                   Qdrant Local                                 |
|                         |                                       |
|                    RRF fusion                                  |
|                         |                                       |
|                     reranker                                   |
|                         |                                       |
|                 context expansion                              |
|                         |                                       |
|              evidence quality decision                         |
|                  |               |                              |
|             sufficient     rewrite/retry                       |
|                  +-------+-------+                              |
|                          v                                      |
|             OpenAI-compatible generation client ---------------+
|                          |                                      |
|                 citation validation                             |
|                          |                                      |
|                  answer / abstention                            |
|                                                                 |
|          FastAPI + UI + evaluation harness + traces            |
+----------------------+---------------------+--------------------+
                       |                     |
                   /data volume         /models volume
                                        embed/rerank only
```

### Deployment boundary

The application container owns document intelligence, retrieval, embeddings, reranking, orchestration, evaluation, API/UI, and embedded/local vector persistence. The **generative model runtime is a separate local service**.

Default: Ollama on the host.

Compatible alternatives: any approved local OpenAI-compatible endpoint, including llama.cpp or vLLM deployments.

This is intentional separation of concerns rather than a compromise in the offline requirement: all data remains on the same local machine or explicitly approved local network boundary.

## 12. Data model concepts

### Document

Represents one ingested source artifact.

Suggested fields:

- `document_id`
- `source_uri` or local source label
- `title`
- `mime_type`
- `content_hash`
- `ingested_at`
- `parser_version`
- `metadata`

### Chunk

Represents one searchable unit.

Suggested fields:

- `chunk_id`
- `document_id`
- `parent_chunk_id`
- `text`
- `page_start`
- `page_end`
- `section_path`
- `chunk_index`
- `token_count`
- `content_type`
- `content_hash`
- `metadata`

### RetrievalCandidate

- `chunk_id`
- `dense_rank`
- `dense_score`
- `sparse_rank`
- `sparse_score`
- `fusion_rank`
- `fusion_score`
- `rerank_score`
- `retrieval_stage`

### Citation

- `citation_id`
- `chunk_id`
- `document_id`
- `page`
- `section_path`
- `claim_span` (optional)

### QueryTrace

Captures the end-to-end evidence path and timing without requiring the evaluator to infer what happened.

## 13. Retrieval strategy

### Stage A — candidate generation

Retrieve independently from dense and lexical systems.

Typical starting point:

- dense top-k: 30;
- lexical top-k: 30.

These values should be tuned experimentally rather than treated as final.

### Stage B — fusion

Use RRF as the first hybrid strategy because it combines ranked lists without requiring direct score calibration.

### Stage C — reranking

Apply a local cross-encoder to the fused candidates and select a smaller evidence set.

Starting point:

- fused candidates: 20–40;
- final reranked evidence: 4–8.

### Stage D — context expansion

For each winning child chunk, expand to a parent section or controlled neighboring context while enforcing a context budget.

### Stage E — quality decision

A retrieval-quality policy decides whether the evidence is sufficient for generation. The first implementation should be deterministic or score-based; an LLM grader can be evaluated later.

## 14. Generation strategy

Generation is accessed through a project-owned OpenAI-compatible client abstraction. Ollama on the host is the default deployment target, but application code must not depend on Ollama-specific behavior unless isolated in an optional adapter/preflight module.

The application shall configure at least:

- generation base URL;
- model identifier;
- timeout;
- temperature;
- maximum output tokens;
- strict-offline endpoint allowlist;
- local model allowlist/manifest.

The LLM should receive:

1. trusted system instructions;
2. normalized user question;
3. explicitly delimited untrusted evidence blocks;
4. evidence IDs and provenance metadata;
5. a structured answer contract.

The prompt should explicitly state that document content may contain instructions and that these are data, not executable instructions.

Temperature should default low for factual technical QA.

Embedding and reranking remain application-owned retrieval components. Their weights are provisioned separately and mounted/cached locally; they are not delegated to the generation server in v1.

## 15. Evaluation strategy

Evaluation is divided into independent layers so failure attribution remains possible.

### Retrieval

Use human-labeled relevant document/chunk judgments to calculate standard IR metrics.

### Generation

Evaluate answers only after retrieval performance is understood. Maintain the distinction between “the retriever did not provide the fact” and “the generator ignored or distorted the fact.”

### Citations

Perform deterministic provenance validation before semantic support scoring.

### Negative / abstention set

Maintain questions for which the corpus intentionally contains no answer.

### Adversarial set

Maintain documents/questions designed to test indirect prompt injection and evidence manipulation.

### Performance

Track resource and latency costs so quality gains can be judged against execution cost.

## 16. Gold dataset design

Human-authored benchmark questions should include category tags such as:

- `exact_keyword`
- `semantic`
- `acronym`
- `numeric`
- `table`
- `section_lookup`
- `comparison`
- `multi_document`
- `multi_hop`
- `negative`
- `adversarial`

The benchmark should store relevance at the finest practical granularity without making annotation prohibitively expensive.

## 17. Success criteria for portfolio release

A first portfolio-ready release should meet all of the following:

- fully local/offline end-to-end query path with an approved local generation endpoint;
- reproducible corpus ingestion;
- dense baseline implemented and evaluated;
- lexical baseline implemented and evaluated;
- hybrid retrieval implemented;
- reranker implemented;
- page/chunk citations exposed;
- gold evaluation set available;
- retrieval metrics published;
- at least one ablation study published;
- unanswerable questions produce explicit abstention with measurable performance;
- adversarial retrieval tests exist;
- basic local UI or trace viewer exists;
- one-container application deployment path with documented host-Ollama default;
- architecture and benchmark methodology documented.

## 18. Stretch goals

Only pursue these when supported by observed failure modes:

- SPLADE or learned sparse retrieval;
- ColBERT-style late interaction;
- table-specific indexing strategy;
- query decomposition for multi-hop questions;
- local semantic judge ensembles;
- reranker distillation;
- multimodal page evidence;
- document-version comparison tooling;
- incremental indexing / change detection;
- multiple local corpora with metadata isolation.

## 19. Key risks

### Risk: evaluation contamination

Synthetic questions generated directly from chunks may artificially favor the system.

**Mitigation:** maintain a separate human gold set and report synthetic results separately.

### Risk: chunk-ID instability

If changing chunking destroys benchmark labels, evaluation becomes expensive.

**Mitigation:** label relevance at document/page/semantic-span levels where possible and support a mapping layer between corpus versions.

### Risk: over-agentification

Agent loops can increase latency, cost, and unpredictability without improving retrieval.

**Mitigation:** implement agentic recovery only after deterministic hybrid retrieval and reranking are benchmarked.

### Risk: misleading global metrics

A strong average can hide weak table or numeric retrieval.

**Mitigation:** report metrics by query category and failure class.

### Risk: “offline” dependencies silently call the network

Model download helpers, telemetry, external judge APIs, or an Ollama/cloud-model configuration can compromise the claim.

**Mitigation:** add offline integration tests, explicit endpoint/model allowlists, local-only model loading for retrieval models, and document the provisioning vs runtime boundary.

## 20. Definition of project success

The project succeeds when it can answer not merely “does this RAG work?” but:

- how well does each retrieval strategy work;
- where does it fail;
- which component produces the improvement;
- what does that improvement cost;
- when does the system refuse to answer;
- and can every produced claim be traced to local evidence?
