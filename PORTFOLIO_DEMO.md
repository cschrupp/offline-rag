# Portfolio Demo Plan

**Current readiness:** Through Slice 8 you can demo ingest → chunk → dense and lexical index → retrieval ladder → `hybrid-rerank-context` → grounded `query` / `eval query`. UI/dashboard remains later.

## Demo objective

Show, in a few minutes, that OfflineRAG is not merely “chat with PDFs.” The demo should make retrieval engineering, evaluation, grounding, and security visible.

## Suggested narrative

### 1. Privacy premise

Open with one sentence:

> The complete RAG path runs locally. OfflineRAG is one container for document intelligence, retrieval, evaluation, and UI; generation is served separately by a local Ollama model, with no cloud API required.

Do not spend the demo on installation details.

### 2. Ask a difficult technical question

Prefer a query that cannot be solved reliably with simple exact matching.

Show the final answer with page-level citations.

### 3. Open the retrieval inspector

Display:

- dense top candidates;
- BM25 top candidates;
- fused list;
- reranker scores;
- final context.

This is the moment that differentiates the project from ordinary chat interfaces.

### 4. Toggle retrieval modes

Run the same question using:

- dense only;
- BM25 only;
- hybrid;
- hybrid + reranker.

Highlight how the rank of the correct evidence changes.

### 5. Show the evaluation dashboard

Present the benchmark table and one category breakdown.

Ideal discussion:

> Hybrid retrieval improved exact-identifier and acronym queries, while reranking produced the largest MRR improvement. Table queries remain the main weakness.

The exact statement must come from real project results.

### 6. Ask an unanswerable question

Show explicit abstention.

Then show the negative-set metric proving this behavior is evaluated rather than hard-coded for one example.

### 7. Run an adversarial case

Use a document containing an indirect prompt injection. Show that it appears in retrieved evidence but does not alter system behavior.

### 8. End on engineering trade-offs

Show one quality-vs-latency comparison.

Example structure:

> The reranker improved MRR by X points at a median latency cost of Y ms on this hardware.

## UI panels worth building

### Chat / answer

- question;
- answer;
- citation chips;
- evidence viewer.

### Retrieval trace

- query normalization;
- dense results;
- lexical results;
- fusion;
- reranker;
- context expansion;
- rewrite loop.

### Evaluation

- experiment selector;
- aggregate metrics;
- category metrics;
- latency/resources;
- failed query browser.

### Corpus

- indexed documents;
- pages/chunks;
- parser warnings;
- manifest/version.

## Deployment moment worth showing

Keep installation brief, but include one slide/screenshot showing the separation:

```text
OfflineRAG container  ->  local OpenAI-compatible endpoint  ->  Ollama
```

The point is not “we used Ollama.” The point is that the retrieval platform is model-agnostic, the application remains a single container, and generation/runtime hardware can change independently.

A useful portfolio badge/claim once verified:

> Single-container RAG application. Bring your own local model runtime. No cloud service required.

## What not to emphasize

- framework logos;
- number of agents;
- oversized architecture diagrams;
- “state of the art” claims without benchmark support;
- polished chat styling before evaluation evidence.

## Interview talking points

Be prepared to explain:

1. Why dense-only retrieval fails on technical identifiers.
2. Why RRF is useful when dense and lexical scores have different scales.
3. Why reranking is separated from candidate generation.
4. Why parent-child retrieval improves precision/context trade-offs.
5. How the system distinguishes retrieval failure from generation failure.
6. How abstention thresholds are measured.
7. Why indirect prompt injection is a RAG-specific threat.
8. Why agentic query rewriting is conditional rather than always-on.
9. Why the generative model is outside the application container and how strict offline execution was verified.
10. What component you would improve next based on the observed failure distribution.
