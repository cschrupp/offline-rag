# Milestone 4 — Offline Gold Authoring & Retrieval Benchmarking

**Position:** after Slice 9 (Evaluation Harness v1), before Slice 10 (Generation/Citation Semantic Evaluation).

**Milestone 4 engineering checkpoint reached.** Slice **9F** **GO**; **9H-P**
**COMPLETE / NON-PROMOTIONAL**. Slice **9G** is **DEFERRED — PUBLICATION
READINESS**. Formal **9H** is **FROZEN** behind future 9G. Canonical
**publication** order remains **9G → formal 9H**.

The frozen 22-case / human-16 9F GoldDataset
(`gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172`)
is a **development/regression fixture only**.

**Next operational track (project):** Milestone **5** / Slice **10** — design
contract drafted / implementation not started:
[`slice10_generation_semantic_evaluation.md`](slice10_generation_semantic_evaluation.md).
See also [`ROADMAP.md`](../ROADMAP.md).

Slice **9F** report: [`pilots/slice9f_ics_modules.md`](pilots/slice9f_ics_modules.md).  
9H-P: [`pilots/slice9h_p_pilot_contract.md`](pilots/slice9h_p_pilot_contract.md) /
[`pilots/slice9h_p_results.md`](pilots/slice9h_p_results.md).

Slice **9E** (`offline-rag gold review` / `gold finalize`) is **CLOSED / VERIFIED** — see [`slice9e_human_review.md`](slice9e_human_review.md).
Slice **9D** (`offline-rag gold prelabel`) is done — see [`slice9d_relevance_prelabel.md`](slice9d_relevance_prelabel.md).
Slice **9C** (`offline-rag gold pool`) is done — see [`slice9c_candidate_pooling.md`](slice9c_candidate_pooling.md).
Slice **9B** (`offline-rag gold propose`) is done — see [`slice9b_gold_propose.md`](slice9b_gold_propose.md).
Slice **9A** (contracts + privacy + doctor) is done — see [`slice9a_gold_authoring.md`](slice9a_gold_authoring.md).

---

## Status entering / within milestone

- Slices 0–8 implemented; Slice 8 validated end-to-end.
- Slice 9 evaluation harness complete at commit `9073c37` ([`slice9_retrieval_evaluation.md`](slice9_retrieval_evaluation.md)).
- Slice **9A** complete: `authoring:` config, `authorcfg_`, privacy dual-gate, lean silver/run models, doctor readiness.
- Slice **9B** complete: `source-sampling-random-v1`, `question-proposal-v1`, local authoring Chat Completions path, quality gates, `offline-rag gold propose`, silver-run persistence (no seed-body/raw-response copies).
- Slice **9C** complete: `candidate-pooling-v1` six-arm historical pooling, `offline-rag gold pool`, union/dedupe/`chunk_id` identity, pool inspection order, privacy-preserving candidate provenance (no body text / no grades).
- Slice **9D** complete: `relevance-prelabel-v1` candidate-at-a-time blind double-pass judging, `blind-order-v1`, `relevance-judge-context-v1`, `prelabel-agreement-v1`, `offline-rag gold prelabel`, silver-only model judgments + review-priority aids.
- Slice **9E** complete / CLOSED / VERIFIED.
- Slice **9F** **GO** (22-case `ics_modules` GoldDataset + filled pilot report).
- **9H-P** **COMPLETE / NON-PROMOTIONAL** (measure-once retrieval pilot on frozen 9F gold).
- Slice **9G** **DEFERRED — PUBLICATION READINESS** (not a near-term engineering dependency).
- Formal Slice **9H** **FROZEN** behind future 9G.
- `GoldDataset v1`, deterministic retrieval metrics, serialized evaluation artifacts, and `offline-rag eval compare` are available.
- `model-query-prompt-v1`, `exclude-heading-only-v1` / Arm H, and `prompt-grounded-provenance-v2` remain validated experimental candidates.
- No experimental contracts are promoted to `base.yaml`.

---

## Objective

Build a practical, repeatable, fully local workflow for constructing high-quality retrieval gold datasets from private technical corpora.

Privacy guarantee:

> **Private source documents and their derived text must not require transmission to a cloud model or external annotation service in order to build, update, or evaluate a gold dataset.**

Gold construction should be substantially automated by a local LLM, while final relevance judgments remain human-adjudicated.

Target workflow shift:

```text
manual invent questions → manual corpus search → manual JSONL editing
```

into:

```text
sample source material
  → locally propose questions
  → automatically pool candidate evidence
  → locally pre-grade candidates
  → human review
  → finalize GoldDataset v1
```

The local model is an **annotation assistant**, not the source of ground truth.

---

## Design principles

### 1. Gold is human-adjudicated

The local LLM may propose questions, categories/tags, candidate chunks, pre-grades `0/1/2`, duplicates, ambiguity flags, and missed-positive searches.

It must never automatically convert its own judgments into final gold labels. Export to GoldDataset v1 requires explicit human approval.

### 2. Source-seeded question generation

Questions are generated from authoritative corpus content, not from retrieval failures alone:

```text
ChunkSet → representative sampling → source chunk + DOCUMENT/SECTION context
  → local LLM → candidate user questions
```

### 3. Multi-retriever pooling

For every proposed query, build a high-recall candidate pool across six existing retrieval paths (lexical plain-v1, dense baseline/raw-query-v1, dense `model-query-prompt-v1`, Arm H dense, hybrid RRF, hybrid-rerank). Union/deduplicate by `chunk_id`. Do not modify production retrieval algorithms or defaults; use historically bound indexes. Do not auto-inject the source seed or expand neighborhoods into the pool (9C).

### 4. Blind pre-labeling

When the local model judges candidates, hide retrieval method, score, rank, and source-seed identity. Present DOCUMENT / SECTION / chunk text only. Shuffle candidate order deterministically.

### 5. Two-pass local judging

Grade each pool at least twice with different deterministic orders using the GoldDataset v1 scale (`2` / `1` / `0`). Record agreement/disagreement. Neither pass becomes gold automatically.

### 6. Silver and gold are different artifacts

`SilverCase` / authoring drafts hold proposals, pools, model passes, and human status. Only reviewed cases export to `GoldDataset v1`. Silver artifacts must not be accepted by `offline-rag eval retrieve` as gold.

### 7. Gold remains retrieval-model independent

Final GoldDataset v1 retains only Slice 9 semantics (`query`, `category`, `tags`, chunk judgments). No model rationale, retrieval scores, ranks, methods, or LLM confidence in gold semantic identity.

### 8. Gold authoring ≠ production generation

Do not reuse Slice 8 grounded-answer prompt contracts for authoring. Separate authoring contracts/config. Do not alter `gencfg_`, `grounded-answer-v1`, `prompt-grounded-v1`, or `prompt-grounded-provenance-v2` via authoring work.

---

## Privacy contract

### Default security rule

Authoring LLM endpoints must be explicitly approved local/private endpoints.

No automatic fallback to OpenAI, Google, Anthropic, Hugging Face hosted inference, DeepEval/Ragas cloud defaults, or external annotation APIs.

Missing or unauthorized endpoint: **fail closed**.

### Privacy terminology

| Mode | Meaning | Portfolio wording |
|---|---|---|
| Strict single-machine | `localhost` / `127.0.0.1` only | Documents never leave the machine. |
| Private-LAN | Approved model server on another privately controlled host | Documents never leave the local/private environment. |

Do not claim literal single-machine isolation when inference occurs over LAN.

Conceptual config:

```text
authoring.network_policy = localhost_only   # Slice 9A
# private_network optional later if useful
```

---

## Dependency policy

Do **not** make DeepEval, Ragas, Giskard, NotebookLM, or another evaluation framework a required architectural dependency.

OfflineRAG already owns parsing through comparison. Useful ideas may be adopted internally.

Optional later: export/import to a **locally hosted** Label Studio (or similar). Must remain optional; the canonical workflow works without external hosted services.

Optional later (after private gold works): public benchmark adapters (BEIR / `ir_datasets`) as a secondary track — never a replacement for private-corpus gold authoring.

---

## Package and CLI boundary

```text
src/offline_rag/gold_authoring/   # authoring subsystem (create silver → export gold)
src/offline_rag/evaluation/       # Slice 9 consume finished GoldDataset v1
```

Do not place authoring behavior into `evaluation/gold.py` beyond final GoldDataset-v1 validation/export.

Proposed CLI namespace:

```text
offline-rag gold propose
offline-rag gold pool
offline-rag gold prelabel
offline-rag gold review
offline-rag gold finalize
offline-rag gold status
```

`gold review` / `gold finalize` are implemented (Slice 9E). Optional `gold status` and pilot tooling continue in later slices. Intended end-user flow:

```bash
offline-rag gold propose --corpus ics_modules --count 20
offline-rag gold pool --run <authoring-run.json>
offline-rag gold prelabel --run <authoring-run.json>
offline-rag gold review --run <authoring-run.json>
offline-rag gold finalize --run <authoring-run.json>
```

---

## Authoring artifact

Versioned local artifact (not GoldDataset v1):

```text
offline-rag-gold-authoring-v1
```

Preserves enough state to resume human review without regenerating: run identity, corpus/`chunk_set_id`, authoring contracts, generator identity, sampling config, draft cases (seed, proposals, pool, model passes A/B, disagreement, human status, human final judgments).

Authoring-only metadata does not enter GoldDataset semantic identity.

---

## Implementation order (strict)

```text
9A contracts + privacy boundary
  → 9B source sampling + local query proposals
  → 9C multi-retriever pooling
  → 9D blind double-pass pre-labeling
  → 9E human review + GoldDataset finalization
  → 9F 20-case ics_modules pilot + workflow assessment / freeze
  → 9G ~100–150 case production gold + dev/test freeze
  → 9H retrieval A/B + promotion decision
  → Slice 10 generation/citation semantic evaluation
```

### Authorized evaluation detour — 9H-P (COMPLETE)

After 9F GO, 9G expansion was capacity-blocked / later deferred to publication
readiness. A bounded evaluation-only detour, **9H-P**, benchmarked the frozen
22-case 9F GoldDataset before 9G.

**Status:** **COMPLETE / NON-PROMOTIONAL** — results:
[`pilots/slice9h_p_results.md`](pilots/slice9h_p_results.md).

This does not satisfy 9G, does not consume the formal 9H promotion decision,
and cannot change retrieval defaults.

Authoritative contract:
[`pilots/slice9h_p_pilot_contract.md`](pilots/slice9h_p_pilot_contract.md)

---

## Slice 9A — Gold Authoring Contracts & Privacy Boundary

**Status:** done. Authoritative notes: [`slice9a_gold_authoring.md`](slice9a_gold_authoring.md).

**Goal:** Create the authoring subsystem boundary without generating a real dataset yet.

**Implemented:** `AuthoringSettings` / `authoring:` block; lean `GoldAuthoringRun` / `SilverCase`; contracts `openai-compatible-authoring-v1`, `question-proposal-v1`, `relevance-prelabel-v1`, `offline-rag-gold-authoring-v1`; `authorcfg_` hash; dual-gate privacy (`allowlist` AND `network_policy`); doctor Authoring section; gold-loader rejection of authoring schema.

**Acceptance (met):** Authoring package instantiates independently of retrieval evaluation; unauthorized endpoint fails before text transmission; production generation contracts/hashes unchanged; GoldDataset v1 unchanged; `base.yaml` retrieval/generation defaults unchanged.

---

## Slice 9B — Deterministic Source Sampling & Local Question Proposal

**Status:** done. Authoritative notes: [`slice9b_gold_propose.md`](slice9b_gold_propose.md).

**Goal:** Automatically create useful candidate questions from the authoritative ChunkSet.

**Implemented:** `source-sampling-random-v1`; `proposal-context-seed-provenance-v1`; `question-proposal-v1`; `openai-compatible-authoring-v1` Chat Completions path; `proposal-quality-gates-v1`; `proposal-attempt-once-v1`; `offline-rag gold propose`; silver persistence without seed-body/raw-response copies.

**Acceptance (met):** Fixed `chunk_set_id` + sampling seed + authoring contract + local model records reproducible proposal provenance. No proposal enters GoldDataset automatically.

---

## Slice 9C — Multi-Retriever Candidate Pooling

**Goal:** High-recall candidate pools before adjudication.

**Implemented:** `candidate-pooling-v1` six-arm ensemble (lexical plain-v1, dense baseline/raw-query-v1, dense `model-query-prompt-v1`, Arm H / `exclude-heading-only-v1`, hybrid RRF, hybrid-rerank); depths 50/50/50/50/50/20; historical `chunk_set_id` preflight; union/dedupe by `chunk_id`; pool inspection order (min rank ↑, arm count ↓, `chunk_id` ↑); `offline-rag gold pool`; privacy-preserving candidate provenance (IDs/metadata/hits only — no body text); case-local complete-six-arm-or-fail semantics. Experimental arms remain unpromoted. No seed injection, neighborhood expansion, grades, or LLM calls.

**Acceptance (met):** Each successfully pooled draft query yields a deterministic pool with `chunk_id`, DOCUMENT/SECTION provenance, and reconstructable text via historical `chunk_set_id` + `chunk_id`. Candidate membership is not a relevance claim.

See [`slice9c_candidate_pooling.md`](slice9c_candidate_pooling.md).

---

## Slice 9D — Local Blind Relevance Pre-Labeling

**Goal:** Reduce human workload without delegating gold truth.

**Implemented:** `relevance-prelabel-v1` (strict `{grade:0|1|2, rationale}`); candidate-at-a-time 2N judging; `relevance-judge-context-v1` QUERY/DOCUMENT/SECTION/CANDIDATE envelope; `blind-order-v1` dual deterministic execution orders; `prelabel-agreement-v1` (agree/adjacent/polar + case review flags + `high|medium|low` priority); case-atomic complete-pair or no durable prelabel; `offline-rag gold prelabel --run [--output] [--force]`. Model grades remain silver-only; no human_status mutation; no GoldDataset finalize.

See [`slice9d_relevance_prelabel.md`](slice9d_relevance_prelabel.md).

---

## Slice 9E — Local Human Review & Finalization

**Status:** done — see [`slice9e_human_review.md`](slice9e_human_review.md).

`offline-rag gold review --run <authoring-run>` serves a loopback-only native UI; human decisions persist on silver. `offline-rag gold finalize --run … [--output] [--force]` publishes qualifying `accepted`/`edited` cases to `offline-rag-gold-v1`. No Label Studio.

Corrective invariants (post-implementation): validate GoldDataset in the temporary publish directory before promotion; historical evidence fails closed (no placeholder/CURRENT); strict JSON mutation booleans/intent; real `::1` bind when IPv6 is available; HTTP review mutations are transactional with their evidence-backed success response (no durable write if response construction fails).

---

## Slice 9F — 20-Case Authoring Pilot

**Status:** **GO**.

**Authoritative GoldDataset:**
`gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172`
(22 cases; lineage `authorrun_b28d88f64054491a837cb4a144cbe056` /
`chunkset_6d4925ea8d66e7dc599a884e96bc5f6b094e4288d565372d15e6002086c41da2`).

**Ops docs:**

- Runbook: [`slice9f_pilot_runbook.md`](slice9f_pilot_runbook.md)
- Report template: [`slice9f_pilot_report_template.md`](slice9f_pilot_report_template.md)
- Filled report: [`pilots/slice9f_ics_modules.md`](pilots/slice9f_ics_modules.md)
- Provenance audit: [`pilots/slice9f_gold_provenance_audit.json`](pilots/slice9f_gold_provenance_audit.json)

**Nature:** Operational validation of the locked 9B→9E workflow on `ics_modules`. No new runtime architecture, schemas, freeze enforcement, append-propose, coverage quotas, or pilot CLI.

**Authoritative start (after fail-closed preflight):**

```text
offline-rag gold propose --corpus ics_modules --count 40 --seed 0
```

**Lineage:** one historical `chunk_set_id`, one `authoring_run_id`; prepare pool + prelabels before review; freeze upstream state at the first durable human mutation; finalize with ordinary `gold finalize` only (default paths; no cross-run stitching).

**Success gate (written GO / ADJUST / NO-GO):** ≥20 finalized `accepted`/`edited` cases; meaningful query-type coverage recorded; four process judgments (proposal / pool / rubric / model-assistance); no unresolved contract-breaking defect; no pilot-only retrieval/model promotion. Module 1 ≤1 finalized case via source-seed `document_id` (canonical title fallback only). Pending may remain at finalize. Post-pilot human-review accounting amendment (≥16 human-reviewed finalized) is recorded in the filled report / provenance audit and does not rewrite this historical case-count gate.

---

## Slice 9G — Production Retrieval Gold Set

**Status:** **DEFERRED — PUBLICATION READINESS** (not a near-term engineering
dependency). Do not mark complete.

**Goal (historical / future):** First serious private retrieval benchmark
(~120 accepted; practical range 100–150).

Resume only once the target corpus is substantially complete and stable and
publication-quality benchmarking is approaching. Current corpus coverage is too
partial to justify the expert effort for a production-scale benchmark now.

Before retrieval optimization, split ≈80 development / ≈40 held-out (for a
120-case set), stratified by documents/modules, categories, and difficulty.
Held-out is frozen; do not use held-out failures for iterative tuning. If
held-out inspection becomes necessary, treat the test set as consumed and create
a future replacement rather than pretending it remains untouched.

Semantic changes produce a new GoldDataset identity under Slice 9 rules.

**Future adjudication requirement (not authorized now):** Do not scale the
current candidate-by-candidate human review UI for production gold. Redesign
around quiz/puzzle-style evidence validation (best passage, multi-select
support, none-of-the-above, direct vs supporting) while preserving explicit
human ground truth and provenance.

The frozen 9F 22-case / human-16 set remains a **development/regression fixture
only**; it does not satisfy 9G.

---

## Slice 9H — Retrieval Candidate Evaluation & Promotion Decision

**Status:** **FROZEN** behind future 9G. Formal promotional decision remains
reserved. See also the completed non-promotional **9H-P** detour
([`pilots/slice9h_p_results.md`](pilots/slice9h_p_results.md)).

**Goal:** Use the Slice 9 harness on real gold.

Candidates include baseline dense, `model-query-prompt-v1`, Arm H / `exclude-heading-only-v1`, and combinations; keep lexical/hybrid/rerank in stage analysis. Persist `offline-rag-retrieval-eval-result-v1` and compare with `eval compare`.

Promotion requires meaningful metric gains, acceptable category regressions, acceptable latency/cost, and generalization beyond the Module 1 smoke case. Explicit architectural decision — no automatic composite winner.

This slice may justify promoting retrieval contracts (`model-query-prompt-v1`, `exclude-heading-only-v1`). It does **not** justify promoting `prompt-grounded-provenance-v2` (generation-semantic → Slice 10).

**9H-P** produced pilot evidence/hypotheses only and **cannot** authorize those promotions. Formal 9H waits for future 9G.

---

## Explicitly out of scope for Milestone 4

Do not:

- upload documents to NotebookLM or cloud LLMs for private gold;
- make DeepEval/Ragas/Giskard required;
- let local-model labels become gold automatically;
- create gold only from retrieval failures;
- promote Arm H / provenance-v2 / change `base.yaml` during authoring-pipeline implementation;
- change retrieval algorithms during authoring-pipeline implementation;
- start Slice 10 or build an LLM-as-judge answer evaluator in this milestone.

---

## Definition of success

A user can add/update private technical documents and create or refresh a retrieval benchmark without sending source text outside the approved local environment:

```text
ingest → chunk/index
  → gold propose → pool → prelabel → review → finalize
  → GoldDataset v1
  → eval retrieve → eval compare
```

Human effort concentrates on **review and adjudication**, not manual search or JSON authoring.

---

## Portfolio description

### Offline Gold Authoring

OfflineRAG includes a privacy-preserving benchmark-authoring workflow for proprietary technical corpora.

Rather than requiring documents to be uploaded to an external evaluation service, the system can use an approved local language model to propose evaluation questions, build high-recall candidate pools from multiple retrievers, and pre-label passage relevance.

Human adjudication remains authoritative. Reviewed cases are finalized into immutable, versioned GoldDataset artifacts with graded passage-level relevance and deterministic identity.

This enables repeatable retrieval evaluation and configuration A/B testing while keeping private document content inside the user's local environment.

---

## Architectural principle

```text
PRIVATE DOCUMENTS
  → local ingestion/chunking
  → local gold authoring
  → human-adjudicated GoldDataset
  → deterministic retrieval evaluation
  → serialized experiments
  → A/B comparison
  → evidence-based promotion decisions
```

The project therefore does not merely claim that retrieval is offline. It aims to demonstrate that **the complete private-document evaluation lifecycle—from ingestion through benchmark construction and retrieval measurement—can operate without requiring document content to be sent to a cloud service.**
