# Evaluation Harness

**Current readiness (Slice 9):** Retrieval quality evaluation is implemented end-to-end.

- Gold: native `offline-rag-gold-v1` (`meta.json` + `cases.jsonl`, graded `judgments[]`, optional `category`/`tags`) with legacy `relevant_chunk_ids` read-compat (normalized to relevance `1`).
- CLI: `offline-rag eval retrieve [--method dense|lexical|hybrid|hybrid-rerank|hybrid-rerank-context]` and `offline-rag eval compare --a … --b … [--json]`.
- Metrics: Recall/Precision/HitRate/nDCG@{1,5,10}, MRR, conditional HitRate@30; zero-positive cases report quality metrics as null; macro-average over quality-eligible queries only.
- Artifacts: `offline-rag-retrieval-eval-result-v1` (shared envelope + method diagnostics) and `offline-rag-retrieval-eval-comparison-v1` (exact-float win/loss/tie; no retrieval rerun).
- Slice 8 `offline-rag eval query` remains operational generation outcomes only (answered / abstention / generation_failed / citation_invalid).

**Next (Milestone 4):** Offline gold authoring (Slices 9A–9H) builds human-adjudicated private-corpus gold via a local LLM assistant + review workflow, then uses this harness for retrieval A/B and promotion decisions. Canonical plan: [`docs/milestone4_offline_gold_authoring.md`](docs/milestone4_offline_gold_authoring.md). Next decision track: **Slice 9A** (contracts + privacy boundary). Silver/authoring drafts must never be accepted as gold by `eval retrieve`.

**Later (Milestone 5 / Slice 10):** Semantic answer/citation quality metrics.

Sections below retain the broader portfolio target schema; prefer `eval/README.md` and `eval/datasets/slice9_validation/` for the implemented GoldDataset v1 contract.

## Purpose

The evaluation harness is a first-class subsystem. It exists to separate retrieval failures from generation failures, support ablation studies, prevent regressions, and make project claims measurable.

## 1. Evaluation layers

### Layer A — Ingestion integrity

Questions:

- Did parsing preserve the information needed for retrieval?
- Are pages/headings/tables represented correctly?
- Are chunk IDs stable?

Possible checks:

- parser warning counts;
- empty-page detection;
- text coverage on known fixtures;
- deterministic chunk-count/hash checks;
- table preservation fixtures.

### Layer B — Retrieval

Metrics:

- Recall@k;
- Precision@k;
- MRR;
- nDCG@k;
- hit rate;
- category-level performance.

Retrieval should be evaluated independently for:

- dense;
- BM25;
- hybrid RRF;
- hybrid + reranker;
- agentic recovery.

### Layer C — Evidence assembly

Questions:

- Were the correct child chunks found?
- Did context expansion include the necessary parent/surrounding evidence?
- Did context-budget clipping remove crucial evidence?

Suggested metrics:

- gold evidence coverage in final context;
- context precision;
- number of duplicate/overlapping tokens;
- context token count.

### Layer D — Generation

Metrics:

- correctness;
- faithfulness;
- completeness;
- unsupported-claim rate.

Where possible, use deterministic checks for numeric or exact answers before using an LLM judge.

### Layer E — Citations

Deterministic checks:

1. citation resolves to a real chunk;
2. cited chunk was retrieved;
3. cited chunk was included in generation context.

Semantic check:

4. cited evidence supports the associated claim.

### Layer F — Abstention

Maintain a dedicated negative set.

Metrics:

- correct abstention rate;
- false-answer rate;
- false-refusal rate;
- threshold curves.

### Layer G — Security

Adversarial tests should include retrieved instructions attempting to:

- override system policy;
- reveal hidden prompts;
- fabricate citations;
- ignore contradictory evidence;
- call nonexistent tools;
- access filesystem/network resources;
- alter answer format.

### Layer H — Performance

Record:

- parsing pages/sec;
- embedding chunks/sec;
- indexing throughput;
- retrieval p50/p95;
- reranking p50/p95;
- TTFT;
- tokens/sec;
- end-to-end p50/p95;
- RAM/VRAM;
- index size.

## 2. Gold dataset schema

Recommended JSONL record:

```json
{
  "id": "q_0042",
  "question": "What is the maximum working pressure of tool X?",
  "categories": ["numeric", "exact_keyword"],
  "answerable": true,
  "relevant_documents": ["doc_tool_manual"],
  "relevant_pages": [142],
  "relevant_chunks": ["chunk_abc"],
  "expected_facts": [
    {
      "fact": "Maximum working pressure is 15,000 psi",
      "supporting_chunks": ["chunk_abc"]
    }
  ],
  "reference_answer": "15,000 psi",
  "notes": "Exact numeric lookup"
}
```

For an unanswerable query:

```json
{
  "id": "q_negative_001",
  "question": "Who won the 2026 Formula One championship?",
  "categories": ["negative"],
  "answerable": false,
  "relevant_documents": [],
  "relevant_pages": [],
  "relevant_chunks": [],
  "expected_facts": []
}
```

## 3. Query categories

Use tags so averages do not hide weak failure modes.

Recommended initial categories:

- `exact_keyword`
- `semantic`
- `acronym`
- `numeric`
- `table`
- `section_lookup`
- `procedure`
- `comparison`
- `multi_document`
- `multi_hop`
- `negative`
- `adversarial`

## 4. Human vs synthetic data

### Human gold

- authoritative benchmark;
- manually checked relevance;
- smaller but higher confidence.

### Synthetic expansion

- generated from source passages by a local model;
- useful for broader regression coverage;
- must be labeled as synthetic;
- should never silently replace human gold.

Reports should show results separately.

## 5. Retrieval metrics

### Recall@k

Fraction of relevant evidence recovered within top-k.

Use when the primary question is whether the generator ever had access to the correct evidence.

### Precision@k

Fraction of top-k results that are relevant.

Useful for context efficiency and noise analysis.

### MRR

Mean reciprocal rank of the first relevant result.

Useful for measuring how quickly relevant evidence appears.

### nDCG@k

Useful when relevance is graded or multiple relevant items exist and ranking quality matters across the whole result list.

## 6. Experiment definition

Each experiment should be declarative and immutable after results are recorded.

Example:

```yaml
experiment:
  name: hybrid_qwen_bge_reranker
  notes: "RRF hybrid plus local cross-encoder"

corpus:
  manifest: data/manifests/demo_corpus.json

chunking:
  strategy: docling_hybrid
  max_tokens: 512

dense:
  enabled: true
  model: qwen3-embedding
  top_k: 30

lexical:
  enabled: true
  method: bm25
  top_k: 30

fusion:
  method: rrf
  rrf_k: 60

reranker:
  enabled: true
  model: bge-reranker-v2-m3
  input_k: 30
  output_k: 6

context:
  parent_expansion: true
  neighbor_window: 0

generation:
  enabled: false
```

## 7. Result artifact

Every run should write a machine-readable result object containing:

- experiment config hash;
- git commit;
- corpus manifest hash;
- dataset hash;
- runtime versions;
- machine profile;
- metric values;
- per-query results;
- errors;
- timing summary.

Never store only a screenshot or markdown table.

## 8. Ablation plan

Minimum portfolio ablation:

1. dense only;
2. BM25 only;
3. dense + BM25 + RRF;
4. hybrid + reranker;
5. hybrid + reranker + context expansion;
6. full pipeline with conditional rewrite.

The purpose is not to force every additional stage to “win.” A negative result is useful if clearly measured.

## 9. Regression policy

Create a smaller CI benchmark subset once the harness is stable.

Potential gates:

- Recall@5 may not regress more than tolerance;
- citation resolvability must remain 100%;
- deterministic security tests must remain 100%;
- p95 retrieval latency regression produces warning/failure depending on threshold.

## 10. Judge-model policy

LLM-as-judge metrics are optional and secondary.

When used:

- judge must use an approved local inference endpoint/model for the strict-offline claim;
- judge model/version must be recorded;
- prompts must be versioned;
- deterministic metrics should take precedence where applicable;
- multiple judge models may be compared for sensitivity on a small sample.

## 11. Failure taxonomy

Every failed end-to-end answer should be classifiable as one or more of:

- parse failure;
- chunking/provenance failure;
- candidate-generation miss;
- fusion/ranking failure;
- reranker failure;
- context-expansion failure;
- context-budget clipping failure;
- generator correctness failure;
- citation failure;
- abstention-policy failure;
- security-policy failure.

This taxonomy is central to deciding what to improve next.
