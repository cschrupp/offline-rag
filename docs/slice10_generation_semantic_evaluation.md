# Slice 10 — Generation & Citation Semantic Evaluation

**Status:** **10A–10E IMPLEMENTED / VERIFIED**. Milestone 5 development
checkpoint complete. **No prompt promotion.** Publication validation not claimed.
**Authoritative for:** Milestone 5 / Slice 10 (sub-slices 10A–10E)

This document is the Slice 10 design/contract authority. Runtime implementation
for 10A–10E is in-tree. Development A/B report:
[`docs/pilots/slice10e_generation_prompt_ab.md`](pilots/slice10e_generation_prompt_ab.md).

---

## 0. Frozen development fixture (non-promotional)

| Field | Value |
|---|---|
| `gold_dataset_id` | `gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172` |
| `authoring_run_id` | `authorrun_b28d88f64054491a837cb4a144cbe056` |
| `chunk_set_id` | `chunkset_6d4925ea8d66e7dc599a884e96bc5f6b094e4288d565372d15e6002086c41da2` |
| Cases | 22 total (`full-22`) |
| Human-reviewed sensitivity | `human-16` |
| Assistant-only | 6 (remain in `full-22`; excluded from `human-16`) |

Cohort membership is **not** a field on `offline-rag-gold-v1` cases. It is
defined by the frozen 9F provenance audit / 9H-P cohort tables:

- `docs/pilots/slice9f_gold_provenance_audit.json`
- `docs/pilots/slice9h_p_execution_plan.md` (§10)

Assistant-only `draft_case_id`s (excluded from `human-16`):

```text
draft_559331559a1a4a3eaf6f667db0727850
draft_ac3bfbaa86b4458ea1137742dc3829de
draft_e8bd3467bc52419e95d19a19dde839e2
draft_2083433ad52e4e00ad4214d3fec27464
draft_b88e163517ec47e29240171af181566d
draft_959387c7d1fc48f0a7ac4b38166d1fb1
```

This fixture is **development / regression only**. It cannot authorize
publication claims or production promotion (see §20).

---

## 1. Objective

Slice 10 measures **evidence-grounded generation and citation semantic quality**
against a **fixed evidence snapshot**, isolating generator/prompt/citation/
abstention behavior from retrieval recall, fusion, reranking, and context
expansion.

Primary scientific question:

> Given the right evidence, did the generator use it correctly?

Not:

> Did retrieval find the right evidence?

---

## 2. Current Slice 8 boundary

Slice 8 answers **operational** questions only:

| Question | Mechanism today |
|---|---|
| Did generation execute successfully? | `GroundedAnswerResult.status` |
| Did the model abstain? | `insufficient_evidence` + `abstention_reason` |
| Did output match `grounded-answer-v1`? | `parse_grounded_answer_v1` |
| Did cited IDs belong to current context? | `validate_citation_membership` |

Relevant repository surface (reconciled at design time):

| Area | Path |
|---|---|
| Orchestrator | `src/offline_rag/generation/orchestrate.py` — `GroundedAnswerOrchestrator.answer()` always assembles via `HybridRerankContextAssembler` then generates |
| Prompt builders | `src/offline_rag/generation/prompt.py` — `prompt-grounded-v1`, `prompt-grounded-provenance-v2` |
| Schema | `src/offline_rag/generation/schema.py` — `grounded-answer-v1` |
| Citations | `src/offline_rag/generation/citations.py` — membership + `ResolvedCitation` |
| Domain result | `src/offline_rag/domain/generation.py` — `GroundedAnswerResult` |
| Evidence units | `src/offline_rag/domain/indexing.py` — `EvidenceUnit` |
| Chunk provenance | `src/offline_rag/domain/documents.py` — `Chunk.order`, pages/lines, `section_path` |
| Evidence IDs | `src/offline_rag/context/clip.py` — `full_evidence_unit_id(source_chunk_id)` → `ev_…` |
| Operational eval | `src/offline_rag/generation/evaluate.py` — `QueryEvaluator` / `offline-rag eval query` |
| Provenance overlay | `config/experiments/generation_provenance_prompt.yaml` |
| Slice 8 contract | `docs/slice8_grounded_generation.md` |
| Eval harness note | `EVALUATION_HARNESS.md` (Layer D/E/F targets; Slice 8 = operational only) |

**Invariant:** Slice 8 production/`eval query` behavior must remain unchanged.
`offline-rag eval query` stays operational-only and is **not** repurposed into
semantic evaluation.

---

## 3. Definition of evidence-grounded correctness

**Locked term:** `evidence-grounded correctness`

An answer is semantically correct for Slice 10 when, **relative to the evidence
presented to the generator**:

1. it directly responds to the query;
2. its material factual claims are supported by the supplied evidence;
3. it does not contradict the supplied evidence;
4. it contains the essential answer reasonably available from that evidence;
5. it does not add unsupported prior knowledge.

It is **not**:

- external / world-truth fact checking;
- open-world verification;
- web-grounded correctness;
- retrieval recall;
- document-level completeness beyond supplied evidence.

Preferred vocabulary: **evidence-grounded correctness**, **faithfulness /
support**, **semantic completeness**. Do not write claims implying absolute
truth.

---

## 4. Evidence isolation principle

Slice 10 must **not** evaluate generator quality by independently re-running
arbitrary retrieval per prompt arm and then comparing answers.

Primary semantic evaluation uses a **fixed evidence snapshot**.

For any A/B comparison, lock:

```text
same query
same evidence text
same evidence IDs
same evidence order
same generator model
same temperature
same max_output_tokens
same output schema (grounded-answer-v1)
same recovery contract (no-retry-v1)
same reasoning contract (direct-output-v1)
```

Only the generation semantic axis under test may differ.

Initial controlled A/B:

| Arm | Prompt contract |
|---|---|
| A | `prompt-grounded-v1` |
| B | `prompt-grounded-provenance-v2` |

Arm B may expose trusted DOCUMENT / SECTION labels — that is the axis under
test (`config/experiments/generation_provenance_prompt.yaml`). Retrieval must
not contaminate the comparison.

---

## 5. Evidence mode: `gold-evidence-v1` (primary)

**Contract id (proposed):** `gold-evidence-v1`

For each GoldCase (`GoldCase.id`, query, category, tags, `judgments[]`):

```text
query
+ all positive gold child chunks (relevance ∈ {1, 2})
```

Builder resolves immutable `Chunk` artifacts from the frozen `chunk_set_id`
(via existing chunk-set snapshot access used by gold authoring).

Each selected gold child becomes an `EvidenceUnit` with:

| Field | Value |
|---|---|
| `kind` | `child` |
| `source_chunk_id` | gold `chunk_id` |
| `primary_anchor_chunk_id` | gold `chunk_id` |
| `contributing_anchor_chunk_ids` | `[gold chunk_id]` |
| `document_id` | from Chunk |
| `section_path` | from Chunk |
| page/line | from Chunk where available |
| `text` | exact `Chunk.text` (no mutation) |
| `evidence_unit_id` | `full_evidence_unit_id(source_chunk_id)` (existing Slice 7/8 identity) |
| `clipped` | `false` |
| `clip` | `null` |

Rules:

- Do **not** synthesize explanatory text into evidence.
- Do **not** expose relevance grade 1/2 to the generator (evaluator metadata only).
- Do **not** order by model retrieval score.
- Do **not** run parent/neighbor expansion in this mode (isolates generation from Slice 7 assembly policy).

### Deterministic ordering (locked)

```text
document_id ascending
→ Chunk.order ascending within document
→ chunk_id ascending as final tie-break
```

### Context budget (locked for v1)

`gold-evidence-v1` does **not** silently clip or drop gold positives.

If the ordered evidence set exceeds the generation-path token budget used by
the shared executor:

- fail closed for that case with a deterministic diagnostic
  (e.g. `evidence_budget_exceeded`);
- do not truncate;
- do not invent a partial gold subset without a new contract.

Repo check at design time (fixture + `context.max_context_tokens=6000`): all
22 positive gold evidence sets fit under budget. Hard-negative N=5 sets also
fit. Future corpora may not — budget failures remain visible diagnostics.

---

## 6. Future evidence mode: pipeline-context regression

**Design for later; not required for first implementation.**

Secondary mode may evaluate a frozen real Slice 7 `HybridRerankContextResult`
(or equivalent durable context snapshot). Useful for end-to-end regression;
must remain a **separate population** from `gold-evidence-v1`.

Do **not** silently mix both populations into one metric.

---

## 7. Evidence-set artifact

**Proposed schema:** `offline-rag-generation-evidence-set-v1`

Suggested envelope:

```text
schema_version
evidence_set_id          # content-addressed
evidence_contract        # e.g. gold-evidence-v1
source_gold_dataset_id
chunk_set_id
corpus_id
corpus_name
created_at
cohorts:                 # frozen membership mirrors
  human_16_case_ids[]
  assistant_only_case_ids[]
cases[]:
  case_id                # GoldCase.id
  query
  category
  tags
  label_cohort           # human_reviewed | assistant_only
  evidence_units[]:
    evidence_unit_id
    source_chunk_id
    document_id
    section_path
    page/line provenance
    text
    primary_anchor_chunk_id
    contributing_anchor_chunk_ids
  gold_judgments[]:      # evaluator metadata only
    chunk_id
    relevance
```

**Privacy:** LOCAL / PRIVATE. Do not commit source text or private evidence to
the public repository. Persist under `eval/results/` (gitignored) or equivalent.

**Identity:** `evidence_set_id` is deterministic / content-addressed from
semantic inputs (gold dataset identity + chunk_set_id + evidence_contract +
canonical case/evidence payload without wall-clock `created_at`). Repeated
construction from the same GoldDataset + ChunkSet + contract yields the same
semantic identity (follow existing `gold_` / `ev_` / `gencfg_` hashing patterns
in `src/offline_rag/core/ids.py`).

---

## 8. Deterministic metrics (Layer 1)

Deterministic checks take precedence over LLM judging wherever possible.

### Per generated result (minimum)

```text
generation status
answered / abstained
output schema success
citation membership validity
citation count
generator invoked
attempt count
generation failure reason
latency
generation_config_hash
prompt contract
model identity
evidence_set_id
evidence_contract
```

### Gold / evidence diagnostics (not semantic correctness)

Because each EvidenceUnit records contributing gold child identity:

```text
gold_positive_count
gold_grade2_count
gold_grade1_count
cited_evidence_count
cited_gold_chunk_ids
cited_gold_grade2_count
cited_gold_grade1_count
gold_citation_recall
grade2_citation_hit   # when case has grade-2 judgments
```

Definition:

```text
gold_citation_recall =
  |distinct positive gold chunks represented by citations|
  / |positive gold chunks supplied|
```

**Diagnostic only.** Do **not** call this citation semantic correctness: a
citation may point at a gold-relevant chunk yet fail to support the produced
statement.

---

## 9. Citation semantic definitions (Layer 2 inputs)

Slice 8 membership answers only: *was the cited `ev_` ID in the current
evidence namespace?*

Slice 10 separately evaluates support. `grounded-answer-v1` returns
answer-level citation lists, **not** claim-level inline spans. Do not pretend
exact claim→citation alignment exists. Do **not** redesign the output schema
for evaluation.

**Citation coverage:** Does the **union** of cited evidence support all
material factual claims in the answer?

**Citation usefulness:** Does **every** cited EvidenceUnit support at least one
material factual claim in the answer?

This distinguishes missing support vs gratuitous / irrelevant citations.

---

## 10. Local semantic judge contract

Optional evaluation infrastructure — **not** generator ground truth, **not**
GoldDataset truth, **not** allowed to modify labels.

Policy philosophy: same offline / private-network rules as OfflineRAG.

- No cloud fallback
- No hidden remote model
- Versioned judge prompt
- Structured JSON only
- Temperature `0.0`
- Fail closed on malformed responses
- No automatic retries in v1 unless separately designed and locked

**Initial prompt contract:** `generation-semantic-judge-v1`

Recorded judge configuration must include:

```text
provider
endpoint
model
temperature
max tokens
judge prompt contract
adapter contract
network_policy   # localhost_only | private_network (align with gold-authoring)
```

If generator model == judge model: allow the run but record
`same_model_self_judge = true` and treat as a limitation. Do not manufacture
independence.

### Failure semantics (locked for v1)

| Condition | Behavior |
|---|---|
| Judge unavailable / preflight fail | Do not invent scores; case judge status = `judge_unavailable`; Layer 2 aggregates exclude or null with explicit counts |
| Malformed / non-JSON / schema fail | `judge_failed` (fail closed); no retry |
| Judge disabled | Layer 1-only result; Layer 2 absent |

---

## 11. Judge rubric

For an **ANSWERED** case, judge only from:

```text
query
supplied evidence
answer
cited evidence IDs
```

No outside knowledge.

Structured dimensions (no single composite score):

| Dimension | Values |
|---|---|
| `answer_correctness` | `fully_correct` \| `partially_correct` \| `incorrect` |
| `faithfulness` | `fully_supported` \| `partially_supported` \| `unsupported` |
| `completeness` | `complete` \| `partial` \| `incomplete` |
| `citation_coverage` | `complete` \| `partial` \| `unsupported` |
| `citation_usefulness` | `all_useful` \| `some_irrelevant` \| `mostly_irrelevant` |

Bounded diagnostics:

```text
unsupported_claims: max 3
missing_key_points: max 3
irrelevant_citation_ids: []
rationale: bounded length
```

Aggregate dimensions separately. Primary strict answer-quality rate may be
reported as `fully_correct_rate`, but retain full distributions. Do **not**
collapse `partially_correct` with `incorrect` in raw artifacts.

---

## 12. Positive answerability evaluation

Population: `gold-evidence-v1` cases (positives intentionally supplied).

Deterministic Layer 1 expectations:

```text
answer_rate
false_abstention_rate
generation_failed_rate
citation_invalid_rate
```

Plus Layer 2 (if judge enabled) on answered cases.

This is **fundamentally different** from end-to-end pipeline abstention where
retrieval may fail. Keep populations separate in reports.

Run on `full-22`; analyze `human-16` as a **sensitivity cohort from the same
results** (do not rerun generation merely to create human-16) — same pattern as
9H-P.

---

## 13. Human hard-negative abstention design

Positive gold alone cannot evaluate abstention. Slice 10 needs an explicit
negative-evidence fixture.

**Contract id:** `human-grade0-hard-negative-v1` (**IMPLEMENTED / VERIFIED** in 10D)

**Scientific interpretation (locked):** a human relevance grade of `0` means the
candidate was adjudicated non-relevant under the complete human relevance map.
The fixture defines **expected behavior = abstain** (label-defined hard-negative
fixture / expected abstention under the fixture contract). Five individually
grade-0 chunks are **not** a mathematical proof that their combined text can
never support some answer by composition. Do not describe the fixture as
provably impossible to answer or information-free.

### Selection rules (locked)

Eligible cases: **`label_cohort == human_reviewed` only** (cohort map is
authoritative; durable `SilverCase.human_review` presence alone is insufficient).

For each eligible case:

1. Load the explicit frozen `GoldAuthoringRun` (`--authoring-run`); verify
   Gold ↔ Silver lineage (authoring_run_id when recorded, chunk_set_id, corpus
   identity) against the historical ChunkSet.
2. Require accepted/edited Silver with `review_complete()`,
   `grade_basis_query == effective_query() == GoldCase.query`, and matching
   category/tags.
3. Reconcile Silver human positives (relevance 1/2) exactly with
   `GoldCase.judgments` (chunk_id + relevance). Stale maps fail closed.
4. Keep candidates with **human** relevance = `0` that also have a stored
   `hybrid-rerank-v1` hit (at most one hit per candidate; duplicates fail).
5. Deterministic **selection** sort:

   ```text
   hybrid-rerank-v1 rank ascending
   → chunk_id ascending
   ```

6. Take **N = 5** (contract constant; not CLI-tunable). `<5` eligible → fail
   closed. No backfill from other retrievers / model grades / retrieval rerun.
7. Resolve exact `Chunk.text` from the same frozen ChunkSet (child only).
8. **Presentation** order for `EvidenceUnit[]` is independent of selection:

   ```text
   document_id ASC → Chunk.order ASC → chunk_id ASC
   ```

   Stored ranks live only in `hard_negative_selection.selected_candidates[]`
   and must not appear in generator prompts.
9. Expected behavior: **abstain**
   (`insufficient_evidence` / `model_abstain` = correct abstention under the
   fixture contract). `status == answered` = false answer. Do not merge
   `citation_invalid` / `generation_failed` / `empty_context` into those labels.

Do **not**:

- invent unrelated web questions;
- use assistant-only grade-0 maps as authoritative negatives for the primary
  abstention set;
- expose grades, ranks, or “expected abstain” labels to the generator or judge;
- mix positive gold chunks into negative `evidence_units`.

`expected_behavior` (`answer` | `abstain`) is part of `genevidence_` identity.
Typed abstention aggregates use contract
`generation-abstention-deterministic-v1` (rates over total negative-fixture
cases; empty `assistant_only` cohort keeps rates null).

### Feasibility (repo-verified at design time)

For all 22 gold-linked silver cases (including human-16): human grade-0 count
≥ 56; count of grade-0 candidates with `hybrid-rerank-v1` ranks ≥ 8. Therefore
**N = 5 is deterministically feasible** on this fixture. No OPEN DECISION on N
for the frozen 9F set. 10D does not authorize a live ICS run.

### Abstention metrics

Negative-evidence population:

```text
correct_abstention_rate
false_answer_rate
generation_failed_rate
citation_invalid_rate
empty_context_rate
```

If the model answers instead of abstaining, optional judge may classify whether
the answer is unsupported (Layer 2 diagnostic only; never rewrites Layer-1
false-answer labels). A false answer that the judge marks fully_supported /
fully_correct is a potential fixture-review signal — preserve both facts.

Keep negative and positive populations separate in aggregates and comparisons.
Positive-mode gold citation diagnostics remain null / non-applicable in
negative mode.

---

## 14. Result schemas

### `offline-rag-generation-semantic-eval-result-v1`

Suggested envelope:

```text
schema_version
run_id
gold_dataset_id
evidence_set_id
evidence_contract
corpus_id
chunk_set_id
generation_config_hash
generation semantic provenance
judge_enabled
judge semantic provenance
population                 # e.g. full-22 | human-16 subset label in aggregates
deterministic_aggregates
semantic_aggregates        # absent/null if judge disabled
abstention_aggregates
cases[]
started_at
completed_at
metadata
```

Per-case rows must preserve enough to audit judgment without regenerating:

- status, answer text, citation IDs, deterministic diagnostics, judge output
  (local/raw artifact)

Public/tracked reports: aggregates, contract identities, run IDs, taxonomy,
non-sensitive case identifiers — **not** source evidence text.

### `offline-rag-generation-semantic-eval-comparison-v1`

Artifact-only A/B comparison. **Never** reruns generation or judge.

Compatibility requires at least:

```text
same gold_dataset_id
same evidence_set_id
same case set
same semantic metric contract
```

Generation config / prompt contract **may** differ (that is the A/B axis).

---

## 15. Comparison semantics

First controlled A/B (sub-slice 10E):

| | A | B |
|---|---|---|
| Prompt | `prompt-grounded-v1` | `prompt-grounded-provenance-v2` |
| Evidence | same `gold-evidence-v1` snapshot | same |
| Negatives | same `human-grade0-hard-negative-v1` | same |
| Populations | `full-22` + `human-16` sensitivity | same results, post-hoc |

Per-case transitions to report (no composite winner):

```text
answer vs abstain
fully_correct
faithfulness
completeness
citation_coverage
citation_usefulness
latency
```

No production promotion from this fixture.

---

## 16. Proposed CLI

Do **not** overload `offline-rag eval query`.

Proposed surface (exact argparse nesting may follow current `eval` conventions
in `cli.py`):

```text
offline-rag eval generation \
    --config config/base.yaml \
    --dataset <GoldDataset path> \
    --corpus <name> \
    --cohort-map <cohort-map.json> \
    [--evidence-mode gold|human-hard-negative] \
    [--authoring-run <GoldAuthoringRun.json>] \
    [--judge] \
    [--evidence-output ...] \
    [--output ...] \
    [--json]
```

**10B status:** CLI surface implemented.
**10C status:** `--judge` Layer-2 local semantic judge implemented
(`evaluation.generation_semantic_judge`, arm-blind `generation-semantic-judge-v1`).
**10D status:** `--evidence-mode human-hard-negative` + required `--authoring-run`
builds `human-grade0-hard-negative-v1`. `--authoring-run` is rejected with
`--evidence-mode gold`.
**10E status:** artifact-only `offline-rag eval generation-compare`
(`offline-rag-generation-semantic-eval-comparison-v1`, `gencompare_` identity);
controlled v1 vs provenance-v2 measure-once A/B executed; development report at
[`docs/pilots/slice10e_generation_prompt_ab.md`](pilots/slice10e_generation_prompt_ab.md).
No prompt promotion.

---

## 17. Implementation sequence (10A–10E)

| Sub-slice | Deliver later | Explicitly out |
|---|---|---|
| **10A** | Evidence-set schema; `gold-evidence-v1` builder; content-addressed identity; fixed-evidence execution boundary (`GroundedGenerationExecutor`); result/comparison contracts; tests | **IMPLEMENTED / VERIFIED** |
| **10B** | Frozen provenance metadata in `genevidence_` identity; generator-only readiness; `generation-semantic-deterministic-v1`; typed aggregates; evidence/result persistence; cohort map; `offline-rag eval generation` | **IMPLEMENTED / VERIFIED** |
| **10C** | Independent `evaluation.generation_semantic_judge` (OD-10-4); `judgecfg_`; `generation-semantic-judge-v1` / output-v1; arm-blind judging; typed semantic aggregates; `--judge` | **IMPLEMENTED / VERIFIED** |
| **10D** | `human-grade0-hard-negative-v1`; N=5 hybrid-rerank stored-rank selection; Gold↔Silver reconciliation; selection vs presentation order; typed abstention aggregates; human_reviewed-only | **IMPLEMENTED / VERIFIED** |
| **10E** | Controlled v1 vs provenance-v2 A/B; full-22 + human-16 sensitivity; artifact-only compare; Slice 10 development report; **hard-stop** | **IMPLEMENTED / VERIFIED** (no auto-promote) |

Hard-stop after 10E report. Do not automatically promote
`prompt-grounded-provenance-v2`.

---

## 18. Privacy boundary

Private/local by default:

- generation answers
- source evidence
- judge inputs/outputs
- detailed semantic results

Location: `eval/results/` (gitignored) or equivalent.

Tracked documentation may contain aggregates, contract identities, run IDs,
high-level error taxonomy, non-sensitive case IDs.

Do not commit private corpus text for reproducibility. Strict offline/privacy
rules unchanged.

---

## 19. Development-fixture limitations

For the 22-case fixture, label all findings:

```text
development evidence
descriptive
non-promotional
```

- Preserve GoldDataset `category` / `tags`.
- Report overall, `human-16` sensitivity, by category only where n is
  meaningful, by document/module as diagnostic.
- Do not draw category conclusions from singleton groups.
- Report counts alongside every rate.
- No significance claims by default.

---

## 20. Promotion / publication boundary

**Layer 3 — publication claims** are **not** available from Slice 10 on this
fixture.

Requires future: substantially complete corpus, 9G production benchmark path,
formal evaluation methodology (post deferred-9G).

Never blend Layer 1 / Layer 2 / Layer 3 in reports.

Slice 10 does **not** authorize:

- retrieval tuning
- 9G execution
- formal 9H
- query rewrite / recovery agents / LangGraph
- prompt-injection / security milestone work
- `base.yaml` promotion
- `prompt-grounded-provenance-v2` promotion
- new generation retries / temperature tuning / generator model search
- judge model tournament
- claim-level output-schema redesign
- external web fact checking / cloud LLM judging
- production benchmark claims

If any become necessary: stop and request a new scope decision.

---

## 21. Test strategy

Design-time intent (implement in 10A+):

| Focus | Examples |
|---|---|
| Evidence builder | Deterministic `evidence_set_id`; stable ordering; exact Chunk.text; no grade leakage into prompt units |
| Executor boundary | Same prompt/parse/membership/resolve path as Slice 8; **Slice 8 tests remain byte/semantics compatible** |
| Metrics | `gold_citation_recall` arithmetic; abstention rates on synthetic fixtures |
| Judge | Schema fail-closed; no retry; `same_model_self_judge` flag |
| Hard negatives | N=5 selection golden tests against frozen silver ranks |
| Compare | Artifact-only; rejects mismatched `evidence_set_id` |
| Privacy | No accidental commit of evidence text in tracked fixtures |

No model/generation/retrieval/judge runs in this design pass.

---

## 22. Implementation map against current repository

### Shared generation boundary (critical)

Today `GroundedAnswerOrchestrator.answer()` always:

```text
HybridRerankContextAssembler.assemble
→ prompt construction
→ generator
→ grounded-answer-v1 parse
→ citation membership + resolve
→ GroundedAnswerResult
```

Slice 10 needs the **same** post-evidence path with **prebuilt**
`EvidenceUnit[]`.

**Recommended direction (name not locked):** extract an application-owned
internal helper — e.g. `GroundedGenerationExecutor` — or a private
`answer_from_evidence(...)` used by both:

- `GroundedAnswerOrchestrator` (Slice 8; evidence from assembler)
- `SemanticGenerationEvaluator` (Slice 10; evidence from evidence-set)

Must reuse:

```text
prompt construction (v1 / provenance-v2)
generator invocation (no-retry-v1)
strict parsing
abstention interpretation
citation membership validation
citation resolution
generation_config_hash / semantic provenance
```

**Critical invariant:** refactor must not change existing Slice 8 query
behavior. Existing Slice 8 tests remain compatible.

### Suggested package layout (indicative, not locked)

```text
src/offline_rag/generation/          # keep Slice 8; shared executor lives here
src/offline_rag/evaluation/
  generation_semantic/               # Slice 10 evaluator, metrics, compare
  # OR generation_semantic_*.py alongside retrieve eval modules
```

Prefer extending `src/offline_rag/evaluation/` for eval artifacts/metrics
(mirroring Slice 9 retrieve/compare) while keeping generation adapters under
`generation/`.

### Domain / IDs

- Reuse `EvidenceUnit`, `GroundedAnswerResult`, `ResolvedCitation`.
- Reuse `full_evidence_unit_id` — do not invent a parallel `ev_` scheme.
- New content-addressed ids: `evidence_set_id`, semantic-eval `run_id` prefix
  (follow `new_execution_id` patterns).
- Gold case key is `GoldCase.id` (not `case_id`).

### CLI

Add under existing `eval` subparsers beside `query` / `retrieve` / `compare`;
do not alter `eval query` semantics.

### Config

Reuse `generation.*` and experiment overlay
`generation_provenance_prompt.yaml` for prompt A/B. Judge config should follow
gold-authoring-style `network_policy` + approved endpoint/model allowlists
(separate from generator allowlists if needed, but same policy classes).

---

## 23. Metric hierarchy (Decision 15)

| Layer | Nature | Examples |
|---|---|---|
| **1** Deterministic / authoritative mechanics | No judge | Schema validity, status semantics, citation namespace, gold overlap diagnostics, answer vs abstain on controlled ± evidence |
| **2** Local semantic judgment | Judge-derived; always labeled | Correctness, faithfulness, completeness, citation coverage/usefulness |
| **3** Publication claims | Not available on 22-case fixture | Requires future 9G / formal methodology |

---

## 24. Required design review answers

### Q1. Can generator semantics be evaluated without rerunning retrieval?

**Yes.** Primary mode builds fixed `EvidenceUnit[]` from gold positives +
ChunkSet (`gold-evidence-v1`). Executor consumes prebuilt evidence; assembler
is not invoked for that path.

### Q2. Can v1/v2 receive byte-identical evidence text and IDs?

**Yes.** Both arms consume the same `evidence_set_id` snapshot (same texts,
`ev_` IDs, order). Only prompt construction differs (provenance metadata for
v2).

### Q3. Can evidence identity remain deterministic across runs?

**Yes.** Content-addressed `evidence_set_id` from gold + chunk_set + contract +
canonical payload; unit IDs via existing `full_evidence_unit_id`; ordering
locked in §5.

### Q4. Can Slice 8 production behavior remain unchanged?

**Yes, if** shared logic is extracted behind a boundary that
`GroundedAnswerOrchestrator.answer()` continues to call after assembly, with
Slice 8 tests guarding compatibility. `eval query` remains operational-only.

### Q5. Which metrics are deterministic versus judge-derived?

**Deterministic (Layer 1):** statuses, schema/membership, counts, gold citation
overlap diagnostics, controlled answer/abstention rates.  
**Judge-derived (Layer 2):** answer_correctness, faithfulness, completeness,
citation_coverage, citation_usefulness (+ bounded diagnostics).

### Q6. What constitutes citation semantic support given answer-level citations?

**Coverage** = union of cited units supports all material claims.  
**Usefulness** = each cited unit supports ≥1 material claim.  
No fake claim offsets; no output-schema change in Slice 10 scope.

### Q7. How is correct abstention tested without inventing external questions?

`human-grade0-hard-negative-v1`: original query + N=5 human grade-0 hard
negatives from 9C pools ranked by `hybrid-rerank-v1`, human-16 only.

### Q8. How are assistant-only cases separated from human-reviewed sensitivity?

Frozen provenance cohort lists. Run `full-22` once; compute `human-16`
aggregates post-hoc by excluding the six assistant-only `draft_case_id`s.
Primary abstention fixture uses human-16 only.

### Q9. How does the system fail when the local judge is unavailable or malformed?

Fail closed: `judge_unavailable` / `judge_failed`; no retries in v1; no
invented Layer 2 scores; aggregates null/excluded with explicit counts.
Layer 1 results may still persist.

### Q10. Which results may be called development vs publication evidence?

**Development:** all Slice 10 results on the frozen 22-case / human-16 fixture,
including provenance-v2 A/B.  
**Publication:** not available until future 9G-class benchmark + methodology.
Never promote defaults solely from this fixture.

---

## 25. Repo conflicts / reconciliation notes

| Item | Notes |
|---|---|
| Orchestrator API | `GroundedAnswerOrchestrator.answer()` assembles via Slice 7 then delegates to `GroundedGenerationExecutor.execute()` |
| Neutral ChunkSet access | Generic read-only access lives in `src/offline_rag/chunking/access.py`; `gold_authoring/chunk_access.py` is a compatibility re-export |
| `EVALUATION_HARNESS.md` | Status footer aligned with Milestone 5 / Slice 10 design; retrieval harness remains Slice 9 |
| Gold schema | Cases use `id` + `judgments[].relevance`; cohort labels live outside gold files |
| Silver hits | Field is `retriever`, not `retriever_id`; hard-neg design uses `hybrid-rerank-v1` |
| Provenance-v2 | Experimental overlay only; Slice 8 smoke used it; base default remains `prompt-grounded-v1` pending future evidence |
| Token budget | Fixture fits; fail-closed no-clip locked for gold-evidence-v1 |

---

## 26. OPEN DECISION items

| ID | Topic | Status |
|---|---|---|
| OD-10-1 | Exact Python class/module name for shared fixed-evidence executor | **RESOLVED** — `GroundedGenerationExecutor` in `src/offline_rag/generation/executor.py` |
| OD-10-2 | Exact on-disk layout under `evaluation/` vs `generation/` for Slice 10 modules | **RESOLVED** — runtime executor under `generation/`; Slice 10 contracts/builders under `evaluation/generation_semantic/` |
| OD-10-3 | Whether `pipeline-context` snapshot schema is a new artifact or reuse of durable `HybridRerankContextResult` serialization | **OPEN** — deferred until secondary mode is scheduled; not needed for 10A |
| OD-10-4 | Judge allowlist: share `generation.approved_*` vs separate `eval_judge.*` config block | **RESOLVED** — independent `evaluation.generation_semantic_judge` with its own approved endpoints/models, network_policy, and `judgecfg_` identity; no generation/authoring inheritance |

No OPEN DECISION on: evidence-grounded definition; gold-evidence primary mode;
fixed-evidence A/B isolation; N=5 hard-neg rule feasibility on frozen fixture;
Layer 1/2/3 hierarchy; non-promotion of provenance-v2 from this fixture.

---

## 27. Implementation status notes

- **10A / 10B / 10C / 10D / 10E:** implemented and verified in-tree (fixed
  positive evidence, Layer-1 deterministic metrics, independent Layer-2 judge,
  label-defined hard-negative abstention fixture, artifact-only
  `generation-compare`, controlled prompt A/B development experiment + report).
- Development A/B report: [`docs/pilots/slice10e_generation_prompt_ab.md`](pilots/slice10e_generation_prompt_ab.md).
- `prompt-grounded-provenance-v2` remains an experimental overlay candidate —
  **not** promoted; `prompt-grounded-v1` remains the control/default.
- The frozen 22-case / human-16 pilot and hard-negative fixture remain
  development/regression machinery only — not publication-grade.
- 9G / formal 9H remain deferred/frozen. Milestone 6 is **not** started by 10E.

**HARD STOP after Slice 10E.** Do not begin Milestone 6 under this slice.
