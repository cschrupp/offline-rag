# Detailed Implementation Slices

This document converts the architecture into incremental, testable implementation slices. Each slice should leave the repository in a working state. Avoid building multiple major layers simultaneously: the evaluation harness depends on being able to attribute improvements and regressions to individual changes.

**Implementation status:** Slices 0–9 and Milestone 4 through **9F GO** / **9H-P** complete for near-term engineering (**9G** deferred; formal **9H** frozen). Slice **10A IMPLEMENTED / VERIFIED**; 10B–10E not started — [`docs/slice10_generation_semantic_evaluation.md`](docs/slice10_generation_semantic_evaluation.md). Canonical Milestone 4 plan: `docs/milestone4_offline_gold_authoring.md`. Authoritative notes: `docs/slice0_contracts.md` … `docs/slice9e_human_review.md`, `docs/pilots/slice9f_ics_modules.md`, `eval/README.md`.

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

**Status:** done. See `docs/slice4_lexical_retrieval.md`.

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

**Status:** implemented. Authoritative contract: `docs/slice5_hybrid_retrieval.md`.

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
  lexical_rank: 11
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

**Status:** implemented. See `docs/slice6_cross_encoder_reranking.md`.

Intentionally excluded from Slice 3 so dense embedding/index quality stays
separable from reranker gains. Locked model: `BAAI/bge-reranker-v2-m3` @
`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`; CI uses `FakeReranker`
(`fake-rerank-digest-v1`).

## Objective

Improve ranking quality by reranking the fused hybrid candidate set with a local
cross-encoder (`input_k=30` → `output_k=10`).

## Deliverables

- reranker interface mirroring embedders (`FakeReranker` + provisioned `CrossEncoderReranker`);
- local-only loading, deterministic `rrkcfg_` identity, no runtime downloads;
- `plain-pair-v1` / `seq-trunc-1024-passage-right-v1` / `raw-logit-v1` / `chunk-id-asc-v1`;
- batch reranking; configurable `input_k` / `output_k`;
- timing instrumentation (`hybrid` / `pair_build` / `rerank_infer` / `sort` / `total`);
- `gold_in_rerank_pool` eval diagnostic; CLI `provision reranker`, `retrieve hybrid-rerank`,
  `eval --method hybrid-rerank`, doctor hybrid-rerank lines.

## Required analysis

Measure both quality and latency. Report whether reranking improves:

- MRR;
- Recall at the final evidence cut;
- (later) nDCG@10 / downstream answer accuracy once generation exists.

## Exit criteria

The project can state quantitatively whether reranking is worth the added latency on the chosen corpus.

---

# Slice 7 — Context expansion and evidence assembly

**Status:** implemented. See `docs/slice7_context_expansion.md`.

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

**Status:** implemented. See `docs/slice8_grounded_generation.md`.

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

**Status:** done. Authoritative notes: [`docs/slice9_retrieval_evaluation.md`](docs/slice9_retrieval_evaluation.md). Also `eval/README.md` and `EVALUATION_HARNESS.md` readiness banner. Historical schema sketch below is superseded by the locked Slice 9 contracts.

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

# Slices 9A–9H — Offline gold authoring & retrieval benchmarking (Milestone 4)

**Status:** **9A**–**9E** done; **9F GO**; **9H-P COMPLETE / NON-PROMOTIONAL**; **9G** deferred (publication readiness); formal **9H** frozen.

Full plan: [`docs/milestone4_offline_gold_authoring.md`](docs/milestone4_offline_gold_authoring.md). Slice notes: `docs/slice9a_gold_authoring.md` … `docs/slice9e_human_review.md`. Pilot: [`docs/pilots/slice9f_ics_modules.md`](docs/pilots/slice9f_ics_modules.md). 9H-P: [`docs/pilots/slice9h_p_results.md`](docs/pilots/slice9h_p_results.md).

| Slice | Focus |
|---|---|
| 9A | Authoring contracts, silver artifact, localhost-only privacy boundary — **done** |
| 9B | Deterministic sampling + local question proposal — **done** |
| 9C | Multi-retriever candidate pooling — **done** |
| 9D | Blind double-pass local pre-labeling — **done** |
| 9E | Human review + GoldDataset v1 finalization — **CLOSED / VERIFIED** |
| 9F | 22-case `ics_modules` operational pilot — **GO** (development fixture) |
| 9G | ~100–150 case production gold + dev/test freeze — **DEFERRED** |
| 9H | Formal retrieval A/B + promotion — **FROZEN** behind future 9G (9H-P was a non-promotional detour) |

Do not place authoring into `evaluation/gold.py` beyond final gold validation/export. Do not promote experimental retrieval/generation contracts from the 22-case fixture alone.

---

# Slice 10 — Evaluation harness v2: generation and citation evaluation

**Status:** design contract drafted / implementation not started (Milestone 5). Authoritative contract: [`docs/slice10_generation_semantic_evaluation.md`](docs/slice10_generation_semantic_evaluation.md). Uses the frozen 9F development GoldDataset for non-promotional machinery; provenance-v2 promotion evidence is in scope here, not in formal 9H.

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

```text
STATUS: DESIGN CONTRACT DRAFTED / IMPLEMENTATION NOT STARTED
Order: Slice 11 → 12 → 13 (do not start LangGraph before sufficiency gate)
Authority: docs/milestone6_agentic_recovery_security.md
```

## Objective

Prevent unsupported answers and quantify the cost of refusal thresholds.
Introduce a **pre-generation** evidence-sufficiency decision before any
conditional recovery (Slice 12) is authorized.

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

# Slice 12 — Bounded conditional retrieval recovery

```text
STATUS: COMPLETE / ACCEPTED
        12A COMPLETE / ACCEPTED (1be7fc8)
        12B COMPLETE / ACCEPTED (f1f9c5f)
        12C DESIGN LOCKED / ACCEPTED (OD-12C-1…8)
        12C-1 harness COMPLETE / ACCEPTED (c4f8734)
        12C-2 measure-once COMPLETE / ACCEPTED (dc82432)
Authority: docs/milestone6_agentic_recovery_security.md §16
Contracts: src/offline_rag/recovery/ (runtime);
           src/offline_rag/evaluation/recovery_12c/ (12C harness + measure-once)
OD-12-1 / OD-12-2 / OD-12-3: LOCKED
OD-12C-1 … OD-12C-8: LOCKED / ACCEPTED
Authority: 47656d1
Harness: c4f8734
12C-2: 3d58ff3 → f213960 → dc82432
12C-2 scientific outcome: insufficient_evidence_for_recovery_efficacy
  (stopped_not_evaluable; T_H=0; T_A=0)
Default: retrieval_recovery.enabled=false (unchanged; no promotion authorized)
LangGraph: Post-Slice-12 / NOT AUTHORIZED (not added; not justified by 12C)
No generation / LLM judge in 12C; no 12C-2 rerun authorized
Next: Slice 13 design/start gates only (no implementation authorization)
```

## Objective

Introduce agentic behavior only where the baseline retrieval pipeline demonstrably fails
**and** a formal sufficiency gate has returned insufficient.

## Sub-slices

- **12A (ACCEPTED):** project-owned recovery state/protocol contracts, invariants,
  terminal outcomes, deterministic replay — no LangGraph, rewriter, or recovery retrieval
- **12B (ACCEPTED):** bounded rewriter + exactly one recovery retrieval attempt on 12A contracts;
  default disabled; no LangGraph
- **12C design (LOCKED / ACCEPTED):** OD-12C-1…8 evaluation contract
- **12C-1 (ACCEPTED at c4f8734):** paired shared-initial evaluation harness with frozen
  Gold/cohort identity, prepared-initial binding, preflighted `rrwcfg_`, recomputed
  `receval_`
- **12C-2 (COMPLETE / ACCEPTED at dc82432):** authoritative measure-once on the frozen
  experiment; accepted as `stopped_not_evaluable` /
  `insufficient_evidence_for_recovery_efficacy` because `T_H=0` (and `T_A=0`) under
  `sufficiency-v1`. This is an accepted not-evaluable scientific outcome, not proof
  that recovery is effective or ineffective.
### 12C locked evaluation contract (summary)

- **OD-12C-1** paired shared-initial: one initial retrieve→fuse→rerank→context→sufficiency;
  Arm A stops; Arm B recovers only if insufficient (no independent initial re-run)
- **OD-12C-2** freeze Gold `gold_d3fc157c…46172` + tracked adjudication cohort map;
  human-reviewed = authoritative; assistant-only = descriptive only
- **OD-12C-3** trigger census before recovery (`T_H` / `T_A`); empty `T_H` →
  `not_evaluable_no_human_recovery_opportunities`; recovery stays disabled
- **OD-12C-4** efficacy = Gold-positive chunk overlap (11B evidence-surface rule);
  nonempty-but-unsupported is a harm signal; reuse existing IR metrics
- **OD-12C-5** retrieval evidence authoritative; no generation / no LLM judge as promotion truth
- **OD-12C-6** predeclared conclusions only (`insufficient_evidence…` /
  `retain_disabled_no_measured_benefit` / `retain_disabled_recovery_regression` /
  `promotion_candidate`); `promotion_candidate` does not modify `base.yaml`
- **OD-12C-7** happy-path no-harm: initially sufficient ⇒ zero rewrite / zero recovery retrieval;
  `happy_path_divergence_count == 0` mandatory
- **OD-12C-8** one measure-once rewrite + one recovery retrieval; concrete rewriter
  preflight required; no placeholder model; no cherry-picking

**Experimental limitation:** current Gold has no authoritative unanswerable/negative
truth; 12C cannot establish false-recovery rate on genuinely unanswerable questions.

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

- project-owned RecoveryProtocol / state contracts (**12A done**);
- bounded retry count;
- query rewriter + one recovery retrieval (**12B done**);
- evaluation comparing agentic vs non-agentic pipeline (**12C COMPLETE / ACCEPTED**;
  harness `c4f8734`; result `dc82432`);
- optional LangGraph adapter — **Post-Slice-12 / NOT AUTHORIZED** (not part of
  the accepted Slice 12 deliverable);
- loop termination conditions;
- retry traces.

## Exit criteria

The agentic path must show measurable benefit on at least one failure category before being enabled by default.
`promotion_candidate` is evidence for a later human promotion decision only — it must
not modify `config/base.yaml`.
**12C-2 disposition:** `insufficient_evidence_for_recovery_efficacy` with
`T_H=0` / `T_A=0` / `stopped_not_evaluable` — accepted not-evaluable outcome;
recovery remains disabled; no promotion authorized.
---

# Slice 13 — Prompt-injection and security harness

```text
STATUS: COMPLETE / ACCEPTED UNDER REVISED DISPOSITION
        13A COMPLETE / ACCEPTED (c2c1ff8)
        13B DESIGN: LOCKED / ACCEPTED (d3fc861)
        13B HARNESS: COMPLETE / ACCEPTED (87b9367)
        13B AUTHORITATIVE MEASURE-ONCE: COMPLETE / ACCEPTED (executed at 7baca2d)
        13B OVERALL: COMPLETE / ACCEPTED
        AUTHORITATIVE RESULT: completed / fail
        AUTHORIZATION: CONSUMED / TERMINAL
        RETRY / RESUME / SECOND ATTEMPT: FORBIDDEN
        13C: DEFERRED / OPEN / NOT REQUIRED FOR M6 / NOT AUTHORIZED
        13D: DEFERRED / OPTIONAL / NOT REQUIRED FOR M6 / NOT AUTHORIZED
        OD-13-4: LOCKED / AMENDED / ACCEPTED (efe7e12)
MILESTONE 6: COMPLETE / ACCEPTED
             Closeout: this commit (0f14388 → efe7e12 → this SHA)
13A design authority: 571882e
13A chain: 571882e → 7fe978a → c2c1ff8
13B design authority: d3fc8616e5dfe474a53659bc3e276594d8eaa9c7
13B accepted harness: 87b936789b2cf91e202be5ff4b818e3909460fd8
13B chain: d3fc861 → 0d7b7f3 → 8111c68 → 1977e3f → 87b9367
13B docs/provenance authority baseline: 4efcda174d27f92f75cd3e04b96137d92a5c0ab5
13B sealed/executed executable SHA: 7baca2d0fd0d89b6358d04bd943c8c14ea6e742c
13B Q1 seal: refs/offline-rag/authority/security_13b/q1 → 7baca2d0fd0d89b6358d04bd943c8c14ea6e742c
Post-13B M6 review baseline: 0f14388e71cd0010d64d41c592c6df0aa308fd9c
Frozen seccamp_: seccamp_8034446afeef2cc3b417666bda1059f0fa530d3b458e05645418cc8742816351
Frozen secinv_: secinv_454ef5d54e0e3ac0cd1f3e347f1172e5d2763d66514c0b13810467897767363a
Frozen campaign Git blob: 7951ad964e7a91d5e89589acb4544fb99ca3079c
Q3 result root (local/acceptance evidence; not committed to main):
  eval/results/security_13b/seccamp_8034446afeef2cc3b417666bda1059f0fa530d3b458e05645418cc8742816351/
Authz marker (local/acceptance evidence; not committed to main):
  eval/results/security_13b_authz/seccamp_8034446afeef2cc3b417666bda1059f0fa530d3b458e05645418cc8742816351/authorization_consumed
Evidence archive SHA-256:
  ba454ca226d4ea3d85babd6a4d4f9fa0f21759d7bc01f36d5da891194f169004
Authority: docs/milestone6_agentic_recovery_security.md §29–§30
  (OD-13-4 phase-exit amended; OD-13-7…13 normative contracts unchanged)
Package: src/offline_rag/evaluation/security_13/
CLI dry-run: offline-rag eval security-13b
Frozen campaign: eval/fixtures/security/campaigns/13b_query_path_adversarial_v1.json
OD-13-1…6: 13A accepted (OD-13-2 OPEN / DEFERRED; OD-13-4 LOCKED / AMENDED / ACCEPTED)
OD-13-7…13: LOCKED / ACCEPTED
Product recovery: DISABLED
LangGraph / NeMo / 12C rerun: NOT AUTHORIZED
M6 HUMAN SMOKE: LOCAL / NON-AUTHORITATIVE (supplementary only)
  Part A: Q1–Q4 Status answered; Q5 Status insufficient_evidence /
          Abstention model_abstain (local /tmp/m6-human-demo/part_a.log)
  Part B: dry_run m6-human-demo completed / fail;
          security_policy_immutable_v1 UNEVALUABLE (expected);
          adversarial 0/7 pass/fail; benign FP rate 0.0
          (local eval/results/security_13b_dryrun/m6-human-demo/; not Q3)
Next (historical M6 closeout): Milestone 7 — Performance and UI (now IN PROGRESS; see Slice 14)
```

## Objective

Treat retrieved documents as untrusted input and prove that the RAG control plane is not governed by document instructions.

## 13A COMPLETE / ACCEPTED

- `adversarial-fixture-v1`, `security-invariant-registry-v1`, minimal
  `adversarial-eval-result-v1`
- evaluators for the nine locked invariants; fail-closed PASS/FAIL
- `eval/fixtures/security/` — 7 query-path unit fixtures + 1 recovery-boundary
  unit fixture (13A scope only; not an authoritative campaign)
- focused unit tests; recovery probe via `RecoveryRewriteInputV1` +
  `FakeRecoveryRewriter` only (`harness_fake` / offline)
- thin package exports; no CLI

## 13B COMPLETE / ACCEPTED

Locked ODs: **OD-13-7 … OD-13-13** (§30) at `d3fc861`. Accepted harness at
`87b9367` (chain `d3fc861` → `0d7b7f3` → `8111c68` → `1977e3f` → `87b9367`).
Sealed/executed authoritative executable: `7baca2d` (Q1 Git-ref seal → same
SHA). Docs/provenance authority baseline: `4efcda1`.

- query-path campaign scope; companion `benign-security-control-v1` / `benc_`
- `security-campaign-v1` / `seccamp_`; 7 attack classes + 5 benign controls
- real query-path injection via `GroundedGenerationExecutor` + `FakeGenerator`
  (`security13b-fake-v1`); OD-13-1 evaluators only
- dry-run CLI + one authorized authoritative measure-once (consumed / terminal)
- `run_status` × `campaign_outcome`; narrow false-positive definition

**Accepted harness dry-run note (historical):** expected `campaign_outcome=fail`
because `security_policy_immutable_v1` is UNEVALUABLE on the query-path
generation surface (intentional fail-closed instrumentation; not harness
rejection).

**Authoritative measure-once (ACCEPTED):**
- `run_status=completed`, `campaign_outcome=fail`
- adversarial: pass=0 fail=7 (all 7 classes once;
  `security_policy_immutable_v1` UNEVALUABLE×7)
- benign: pass=0 fail=5 violations=0 unevaluable=5 false_positives=0
- decisive invariant: `security_policy_immutable_v1`
  (UNEVALUABLE → campaign fail under OD-13-1)
- other expected invariants: HOLDS where applicable
- recovery: disabled
- expected fail-closed OD-13-1 outcome; not an execution defect; not grounds
  for repair, retry, resume, or rerun
- authorization **CONSUMED / TERMINAL**
- Q3 / evidence archive: local/acceptance evidence (not committed to `main`)

**Still NOT AUTHORIZED:** 13C/13D execution, LangGraph, NeMo, product recovery,
`base.yaml` mutation, 12C rerun, any measure-once retry/resume/second attempt.
**13C** remains DEFERRED / OPEN / NOT REQUIRED FOR M6. **13D** remains
DEFERRED / OPTIONAL / NOT REQUIRED FOR M6.

## Explicitly outside 13B

- 13C recovery-path / `harness_live` / recovery overlay
- NeMo / 13D (OD-13-2)
- runtime `guardrails/` product integration; LangGraph; recovery promotion;
  absolute security claims; full ICS retrieve→rerank campaign

## Attack classes (SECURITY_MODEL / §20)

- “ignore previous instructions” inside source text;
- fake `SYSTEM:` blocks;
- instructions to reveal prompts;
- instructions to fabricate citations;
- instructions to execute shell commands;
- instructions to access arbitrary files;
- instructions to suppress contradictory documents.

Authoritative **query-path** coverage (13B) is the Milestone 6 deterministic
security campaign exit. Full query×recovery (7×2) coverage remains the scope
of a future **13C**, which is **DEFERRED / OPEN / NOT REQUIRED FOR Milestone 6**.
This does **not** mean 13C was executed, recovery-path evidence exists, or
full 7×2 was achieved in Milestone 6.

## Exit criteria

The adversarial suite runs automatically and the portfolio documentation reports pass/fail criteria without claiming absolute security.
Deterministic control-plane invariants (OD-13-1) are the PASS/FAIL truth —
not model refusal text.
**13A exit met** at `c2c1ff8`.
**13B harness exit met** at `87b9367`.
**13B overall COMPLETE / ACCEPTED** — authoritative measure-once accepted
(`completed` / `fail` at sealed executable `7baca2d`); authorization
consumed / terminal; retry forbidden.
**Slice 13 COMPLETE / ACCEPTED UNDER REVISED DISPOSITION** — 13C/13D deferred
as above; not an M6 delivery obligation.
**Milestone 6 COMPLETE / ACCEPTED** under the revised disposition.

**Next (historical):** Milestone 7 — Performance and UI (now **IN PROGRESS**; see Slice 14).

---

# Slice 14 — Performance and resource benchmark harness

```text
STATUS: IN PROGRESS (closeout not yet eligible)
MILESTONE 7: IN PROGRESS
M7 ENTRY AUTHORITY: dcc6b07c20f97472cf506c4665af1f88f00a886b
Authority: docs/milestone7_performance_ui.md

SLICE 14 DESIGN: LOCKED / ACCEPTED
  89a395ae4df7aff23c2da2c8c44fd6fe405459a6
14A: COMPLETE / ACCEPTED
  c087b8c1f038bd049809db2bf7e761ee0db93b58
14B: COMPLETE / ACCEPTED
  97d38031b99029c2e9b3fd028eadc3a60efef6c0
14C SUITE FREEZE: LOCKED / ACCEPTED
  a662efc50d712bd6a986da05809dc864342139df
  perfsuite_5248892df382995ac96ec2b09aea61bf27510673b93e0d816d6a255a2f4305ba
  perfcfg_aae1ea9b048e414338f0a38b13cb31132505920c406293e1e9f8e35595faa42d
14C AUTHORITATIVE HARNESS REWORK: COMPLETE / ACCEPTED
  ec7383f1612c2ddf86ca595cb3f9f0d8b4fb432c
  F001 / F002 / F003: CLOSED

CORRECTED 14C AUTHORITATIVE EXECUTION:
  ELIGIBLE FOR SEPARATE AUTHORIZATION / NOT AUTHORIZED
SLICE 14 CLOSEOUT: NOT YET ELIGIBLE
README / PORTFOLIO CLAIMS: NOT AUTHORIZED
```

## Objective

Non-invasive, reproducible measurement harness for the accepted OfflineRAG
pipeline. Observe and serialize timing/resource data; combine with already
accepted quality metrics. Do **not** change pipeline semantics or optimize
the system in response to measured results within this slice.

## Locked design (summary)

- Three levels: **A** micro/stage; **B** pipeline variants; **C** end-to-end
  user path — separately labeled.
- Provenance before measurement; warm-up separate from measured samples;
  ≥10 micro/pipeline observations; ≥5 expensive generation observations;
  monotonic `perf_counter`-style timing; report n/min/p50/p95/max + failures.
- Machine/resource profile required; missing RAM/VRAM = unavailable/
  unevaluable (never infer zero); does not invalidate timing.
- Artifacts under `eval/results/performance_14/<suite_id>/<run_id>/`
  (`run_manifest.json`, `aggregate.json`, `cases/`, `report.md`);
  raw observations authoritative; aggregates derived; `report.md` presentation
  only. Manifest minima include suite/executing SHA/machine/config/corpus/
  models/warmup/repetitions/start/env/mode; case minima include identity,
  warm-up, measured observations, failures, resources, derived n/min/p50/p95/max.
- Semantic stage envelopes are normative (e.g. `fusion`: dense+lexical available
  → fused ranking complete; `rerank`: finalized input → reranked candidates
  returned; `end_to_end` is Level-C only — not used for Level-B retrieval-path
  totals); see authority doc §8.
- Retrieval-path totals use dedicated path samples (`PerformancePathSampleV1`),
  not semantic `end_to_end` stage IDs.
- Completed runs immutable; reruns get new IDs; **not** measure-once.
- Fail-closed preflight; descriptive results only — **no** performance SLO /
  winner / promotion decision.
- First quality-vs-cost: **hybrid** vs **hybrid + reranker** (generation
  excluded); reuse existing IR metrics.
- Phasing: 14A → 14B → harness audit → 14C suite freeze → authoritative
  harness → separate corrected-run authorization → Slice 14 closeout.
- Contracts: `performance-benchmark-*-v1`; identities `perfsuite_` /
  `perfrun_` / `perfcase_` / `perfhost_` / `perfcfg_`.

## Accepted progress

- **14A / 14B:** complete substrate and diagnostic dry-run harness.
- **14C suite freeze:** frozen scientific identities accepted; suite not
  reopened.
- **14C harness rework:** quality evidence (ranked IDs + frozen IR metrics),
  semantic fusion/rerank envelopes, separate path latency populations, and
  measured-only RAM summaries accepted at `ec7383f…`.
- **Prior terminal runs preserved:** `perfrun_87771f72…` (failed) and
  `perfrun_f5ed426a…` (completed / audit not accepted) remain immutable.

## Exit criteria (remaining)

Corrected authoritative quality-vs-cost run on the frozen suite (separate
authorization); one defensible quality-vs-cost report from that run; Level C
generation metrics where evaluable; README-facing evidence without arbitrary
winner/SLO claims; Slice 14 closeout.

**Corrected 14C authoritative execution is NOT authorized by this docs
update.** Milestone 6 remains COMPLETE / ACCEPTED unchanged.

---

# Slice 15 — Developer API and single-container application packaging

**Architecture:** **COMPLETE / LOCKED** (S15-D01 … S15-D22)
**Design authority:** [`docs/slice15_developer_api_packaging.md`](docs/slice15_developer_api_packaging.md)
(`6583fb3be64f2c66e8655b8b99166c358f8f0844`)
**Residual A:** **LOCKED / ACCEPTED**
**Implementation plan:** [`docs/slice15_implementation_plan.md`](docs/slice15_implementation_plan.md) — **ACCEPTED**
**Phase progress:**
- **15A:** **COMPLETE / ACCEPTED** (`4a1c8dbcddc8408dd8b8b46dc0f18df56561d2f8`)
- **15B:** **COMPLETE / ACCEPTED** (`00282d67f43edad7cb4094228c482bf8f361d578`)
- **15C:** **COMPLETE / ACCEPTED** (implementation head `5d70be09a3534a093bad9754f4051840ed1fde92`; merge `47a11f1968be75cf772fc7a9e4447ee26e283c52`)
- **15D:** **COMPLETE / ACCEPTED** (FF head `2ef21d26b9513fa7bc98ab1ad8de3645d17cebd7`; commits `39ac270b…`, `88908acd…`, `2ef21d26…`)
- **15E:** **COMPLETE / ACCEPTED** (FF head `63f5965adae3c2a1c5a5b338bcc1243f9423bb5a`; commits `2a84ef01…`, `63f5965a…`)
- **15F:** **COMPLETE / ACCEPTED** (FF head `7bfb0893e1537af99bdaad6f6af5336408afe750`; commits `850d04e9…`, `f907c849…`, `7bfb0893…`)
- **15G:** **COMPLETE / ACCEPTED** (FF head `140350b8cc6eec6a2491c0a1696042e65b2d2b7e`)
- **15H:** **COMPLETE / ACCEPTED** (FF head `1c1d94eada502523d44ec8e9c9a6e23b1f863d49`;
  evidence [`docs/slice15h_integration_acceptance.md`](docs/slice15h_integration_acceptance.md))
- **Slice 15:** **COMPLETE / ACCEPTED**

Roadmap path names such as unversioned `/ingest` and optional `/eval/run` are
superseded by the locked design: product HTTP under `/v1/*`, CLI-first evaluation
(D12), and unversioned `/health*` only. Landed Slice 15 surface:
`/health*`, `GET /v1/documents`, `GET /v1/documents/{document_id}`,
`POST /v1/ingest`, `POST /v1/query`, `GET /v1/trace/{trace_id}`,
admission/deadlines/drain, supported container/Compose packaging, and product
CLI ingest/query via `offline_rag.app`. Portfolio UI work continues under
**Slice 16** (**IN PROGRESS / NOT COMPLETE**; design authority accepted/locked;
see `docs/slice16_design_authority.md`).

## Objective

Expose the RAG engine through a stable local API and package the application as one Docker container while leaving generative inference external.

## Deliverables

- FastAPI app (`/health*`, `/v1/ingest`, `/v1/query`, `/v1/documents`, `/v1/trace/{id}`);
- CLI-first evaluation boundary (no HTTP `/eval/*` in Slice 15);
- API schemas / OpenAPI;
- optional same-origin static-serving substrate was **not** implemented in
  Slice 15 (frontend delivery is a Slice 16 design decision);
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
  + Qdrant client with Local-mode persistence
  + embedding/reranker runtime
  + product HTTP API (/health*, /v1/*)
       |
  /data + /models
```

(Evaluation remains CLI-first per Slice 15 D12. Portfolio UI is Slice 16.)

## Security default

Bind the application to localhost unless the user explicitly configures network exposure. In strict-offline mode, refuse generation endpoints or model identifiers that are not explicitly approved.

## Exit criteria

The accepted product/API surface can be used from CLI and from the Seneca
browser client through the same app layer, and the OfflineRAG application
starts as one container while using an independently running local generator.
Slice 16 remains **IN PROGRESS / NOT COMPLETE** because **16G implementation**
and **16H** remain **NOT AUTHORIZED** (**16E** / **16F** are **COMPLETE /
ACCEPTED / SEALED**; **16G-D0** is **ACCEPTED / FROZEN**; **GAP-16G-01** is
**DESIGN REGISTERED / IMPLEMENTATION NOT AUTHORIZED**); Seneca consuming the
API does not close Slice 16.

---

# Slice 16 — Portfolio Demo UI / Seneca product surface

```text
CURRENT STATUS (compact; authoritative detail elsewhere)

SLICE 16:          IN PROGRESS / NOT COMPLETE
16A–16C:           COMPLETE / ACCEPTED
16D-A / 16D-B2 / 16D-B3 / 16D-C: COMPLETE / ACCEPTED / SEALED
AMENDMENT A4:      ACCEPTED / LOCKED / SEALED
16E:               COMPLETE / ACCEPTED / SEALED
16F:               COMPLETE / ACCEPTED / SEALED
16G-D0:            ACCEPTED / FROZEN
GAP-16G-01:         DESIGN REGISTERED / IMPLEMENTATION NOT AUTHORIZED
GAP-16G-02:         DESIGN REGISTERED / IMPLEMENTATION NOT AUTHORIZED
16G IMPLEMENTATION / 16H: NOT AUTHORIZED
SLICE 17 / 18:     NOT AUTHORIZED
M7 CLOSEOUT:       NOT AUTHORIZED
```

Authoritative current governance:

- [`docs/slice16_design_authority.md`](docs/slice16_design_authority.md)
- [`docs/slice16_implementation_plan.md`](docs/slice16_implementation_plan.md)
- [`ROADMAP.md`](ROADMAP.md)
- [`docs/slice16e_engineering_evidence.md`](docs/slice16e_engineering_evidence.md)
- [`docs/slice16e_closeout.md`](docs/slice16e_closeout.md)
- [`docs/slice16f_closeout.md`](docs/slice16f_closeout.md)
- [`docs/slice16g_gold_lab_games_pedagogy_design.md`](docs/slice16g_gold_lab_games_pedagogy_design.md)
- [`docs/slice16g_gap_registry_addendum.md`](docs/slice16g_gap_registry_addendum.md)
- [`docs/workspace_source_loading_remediation.md`](docs/workspace_source_loading_remediation.md)
- [`docs/slice16d_c_a4_closeout.md`](docs/slice16d_c_a4_closeout.md)

## Objective (current)

Expose OfflineRAG’s engineering value through a browser UI that is an
**adapter/client** of the accepted product/API layer — not a second RAG stack.
The current product surface is **Seneca — Grounded knowledge workspace**.

## Architectural boundary (current)

```text
Browser UI (Seneca)
   ↓
supported UI/backend interface
   ↓
src/offline_rag/app/
   ↓
domain + infrastructure
```

Forbidden: UI → Qdrant / retrievers / generator directly; UI-owned RAG pipeline
or scientific algorithms; bypassing app/product semantics.

## Accepted interaction surfaces (current)

- `/v1/query` remains the independent `grounded_v1` single-turn product path.
- Seneca’s accepted conversational workspace additionally uses the separately
  authorized workspace conversation endpoint (16D-B3 / A3 lineage).
- Do not treat historical pre-design “`/v1/query` only” wording as the entirety
  of the current Seneca interaction model.

## Historical pre-design framing — superseded for current state

The material below records the original Slice-16 roadmap frame from this
aggregate summary file. It is retained for provenance only and is **not**
current design authority.

For current authority/status see:

- [`docs/slice16_design_authority.md`](docs/slice16_design_authority.md)
- [`docs/slice16_implementation_plan.md`](docs/slice16_implementation_plan.md)
- [`docs/slice16d_c_a4_closeout.md`](docs/slice16d_c_a4_closeout.md)

The original pre-design frame also remains at
[`docs/slice16_portfolio_ui.md`](docs/slice16_portfolio_ui.md).

### Product query boundary (historical pre-design note)

Locked product query remains `{corpus, question}` with server-owned
`product_mode_id = grounded_v1` on `/v1/query`. That path is still valid as the
independent single-turn product API; it is not the full Seneca conversational
surface (see Accepted interaction surfaces above).

### Diagnostic / comparison surfaces (historical planning language)

Historical “pipeline switcher” wording (dense / BM25 / hybrid /
hybrid+reranker / recovery) **predates** the locked Slice-15 product API and is
**not** an authorized product feature.

### Candidate capability areas (historical pre-design list)

- **16A** query experience (corpus/question/answer/abstain/citations/preview/trace)
- **16B** evidence / retrieval inspector (only via future approved diagnostic
  surface; current `/v1/query` does not expose candidate lists / RRF / rerank
  scores / raw scientific traces)
- **16C** corpus/document experience (inventory, ingest, readiness)
- **16D** evaluation / performance presentation (prefer read-only artifacts;
  no `/eval/*` HTTP invented for UI convenience — D12 remains CLI-first)
- **16E** portfolio polish (architecture/topology/status/limitations links)

Original planning note (superseded as present-tense status): frontend
technology and delivery model were Slice-16 design decisions; design later
opened and progressed under separate authority. **16A–16E** are accepted;
**16F** is **COMPLETE / ACCEPTED / SEALED**;
**16G-D0** is **ACCEPTED / FROZEN**;
**16G implementation** and **16H** remain **NOT AUTHORIZED**.

### Prerequisites for opening design (historical)

1. 15H COMPLETE / ACCEPTED;
2. Slice 15 COMPLETE / ACCEPTED including closeout;
3. stable supported product contracts;
4. explicit Slice-16 design authorization.

These prerequisites were satisfied; design is no longer “not open.”

### Exit criteria (historical aspirational wording)

A reviewer can understand the system’s differentiators quickly through a UI that
remains a client of the accepted product surface.

---

# NEXT-MILESTONE-CANDIDATE-01 — Answer-level user feedback / continuous evaluation

**Status:** **PLANNING REGISTERED / DESIGN NOT OPEN / IMPLEMENTATION NOT AUTHORIZED**

Named post-M7 planning candidate only — not a formal milestone number, not
Slice 16 / 16G scope, and not Slice 17. Registration detail:
[`docs/slice16g_gap_registry_addendum.md`](docs/slice16g_gap_registry_addendum.md).

Direction (planning only): response-level thumbs; optional structured/free-text
feedback; exact response provenance; append-only history; observational product
metrics; reviewed bridge to regression candidates. Explicitly **not** Gold,
**not** benchmark truth, **not** automatic training data, and **not** automatic
promotion authority.

Also registered in that addendum (unchanged here as 16G executable scope):

```text
GAP-16G-02:
DESIGN REGISTERED / IMPLEMENTATION NOT AUTHORIZED
```

Slice **9G** remains **DEFERRED / NOT AUTHORIZED**. **GAP-16G-01** status is
unchanged.

---

# Slice 17 — Regression CI

**Status:** **PLANNED / DESIGN NOT OPEN / IMPLEMENTATION NOT AUTHORIZED**

## Objective

Prevent accepted product/retrieval/generation contracts and measured quality
from silently regressing after the portfolio UI/product surface exists.

## Candidate areas (not locked; no thresholds defined here)

- deterministic unit/regression tests;
- CI-safe retrieval benchmark subset;
- citation-contract regression;
- API contract checks;
- security deterministic checks where appropriate;
- container build/smoke validation where feasible;
- optional benchmark threshold policy only after explicitly designed.

Do **not** invent SLOs here or convert historical performance measurements into
gates. Do **not** implement GitHub Actions in this roadmap frame.

## Exit criteria (aspirational; not authorized)

A change to chunking, retrieval, ranking, or product packaging can automatically
show whether accepted contracts/quality moved.

---

# Slice 18 — Portfolio Release Package

**Status:** **PLANNED / DESIGN NOT OPEN / IMPLEMENTATION NOT AUTHORIZED**

## Objective

Turn the accepted engineering system into a reproducible public portfolio
artifact backed by evidence rather than marketing claims.

## Candidate deliverables (not locked)

- polished README;
- architecture diagram;
- public demo workflow;
- public sample corpus instructions;
- benchmark methodology/results;
- ablation evidence;
- known limitations;
- hardware/runtime profiles;
- demo video/GIF/screenshots;
- reproducible installation/run path;
- interview talking points;
- portfolio-facing claims tied to exact accepted evidence.

Keep claims conservative. Do **not** promote deferred scientific results or
publication-grade claims merely for portfolio presentation.

## Exit criteria (aspirational; not authorized)

The repository can support carefully scoped public claims with reproducible
accepted evidence.

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
  -> abstention / evidence sufficiency   (Slice 11; BEFORE recovery)
  -> bounded recovery                    (Slice 12; conditional / current disposition)
  -> security tests                      (Slice 13)
  -> performance benchmarks              (Slice 14 COMPLETE / ACCEPTED)
  -> product API + packaging             (Slice 15 COMPLETE / ACCEPTED)
  -> Slice 15 integration closeout       (15H COMPLETE / ACCEPTED)
  -> Seneca / Portfolio Demo UI          (Slice 16 IN PROGRESS; 16D-C / 16E / 16F COMPLETE / ACCEPTED / SEALED; 16G-D0 ACCEPTED / FROZEN; 16H NOT AUTHORIZED)
  -> Regression CI                       (Slice 17 NOT AUTHORIZED)
  -> Portfolio release package           (Slice 18 NOT AUTHORIZED)
  -> Milestone 7 closeout                (NOT AUTHORIZED)
```

The project should resist the temptation to jump directly to deferred
orchestration adapters, multi-agent systems, or publication packaging before
accepted product gates close. The strongest development narrative is an
evidence-based progression from a measurable baseline to increasingly capable
retrieval, then a UI that consumes the accepted product surface. Milestone 6
design authority: `docs/milestone6_agentic_recovery_security.md`. Slice 16
current authority: `docs/slice16_design_authority.md`,
`docs/slice16_implementation_plan.md`, `ROADMAP.md`.
