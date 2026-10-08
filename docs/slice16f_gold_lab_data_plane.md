# 16F — Gold Lab Data Plane — Design Candidate

```text
16F GOLD LAB DATA PLANE
DESIGN CANDIDATE

INDEPENDENT DESIGN REVIEW:
PENDING

HUMAN DESIGN ACCEPTANCE:
PENDING

IMPLEMENTATION:
NOT AUTHORIZED

16F-A / 16F-B / 16F-C / 16F-D:
NOT AUTHORIZED

16G–16H:
NOT AUTHORIZED

9G:
DEFERRED / NOT AUTHORIZED

SLICE 17 / 18 / M7 CLOSEOUT:
NOT AUTHORIZED

SEALED STARTING BASELINE:
d53b29645882b2ecfa9bd6cde25c215e9d4a3921
(16E COMPLETE / ACCEPTED / SEALED)
```

## Purpose

Materialize the **16F Gold Lab data plane** as a product/application layer over
the existing scientific gold-authoring and evaluation machinery.

This document freezes implementation-ready design decisions for later gated
subphases. It does **not** authorize code, schemas, APIs, UI, tests, or 16G.

Locked Slice-16 authority remains:

- [`docs/slice16_design_authority.md`](slice16_design_authority.md)
  (AUTHORITY SHA `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`)
- [`docs/slice16_implementation_plan.md`](slice16_implementation_plan.md)

Normative decisions reused here: **S16-D23 … S16-D34**. Explicit deferrals:
**S16-D35**. Those decisions are **not** reopened by this materialization.

## Existing scientific contracts (must reuse)

| Contract / type | Location | Identity |
|---|---|---|
| Finished gold | `src/offline_rag/evaluation/gold.py` | `offline-rag-gold-v1` |
| Authoring artifact | `src/offline_rag/gold_authoring/` | `offline-rag-gold-authoring-v1` |
| Authoring run | `GoldAuthoringRun` | `models.py` |
| Silver case | `SilverCase` | `draft_case_id` |
| Human review | `HumanReview` / `HumanJudgment` / `HumanReviewStatus` | `review_models.py` |
| Finalizer | `src/offline_rag/gold_authoring/finalize.py` | projects to GoldDataset-v1 |
| Loader | `load_gold_dataset()` | fail-closed validation |

Relevance semantics (unchanged):

```text
0 = irrelevant
1 = supporting
2 = direct
```

`GoldDataset` v1 `ChunkJudgment` stores only positive **1/2**. Human **0**
grades remain in authoring / HumanReview state and in the Gold Lab ledger.

**MUST NOT** modify GoldDataset-v1 semantic identity.
**MUST NOT** create a second scientific gold format.

---

## 16F-D01 — Architectural boundary

16F is a **product/application data plane** over existing scientific
gold-authoring/evaluation machinery.

Recommended later package:

```text
src/offline_rag/app/gold_lab/
```

Dependency direction (**MUST**):

```text
Browser / future UI
        ↓
supported API
        ↓
app/gold_lab
        ↓
offline_rag.gold_authoring
offline_rag.evaluation.gold
```

`gold_authoring` / `evaluation.gold` **MUST NOT** import `app/gold_lab`.

**MUST NOT:**

- create a second `GoldDataset` schema;
- create a second relevance scale;
- create a second retrieval/evaluation pipeline;
- put scientific adjudication logic in React;
- auto-promote model labels;
- alter retrieval defaults;
- satisfy or deem Slice **9G** complete.

---

## 16F-D02 — Project / campaign model

### GoldProject

Stable user-facing effort.

Conceptual fields:

| Field | Notes |
|---|---|
| `project_id` | opaque stable random identity |
| `workspace_id` | owning workspace |
| `title` | human title |
| `description` | human description |
| `project_type` | `benchmark` \| `improvement` |
| `created_at` | creation timestamp |
| `status` | project lifecycle status |

`project_type` is scientifically meaningful provenance and **MUST NOT** silently
change after project creation.

### GoldCampaign

One immutable scientific binding within a project.

Conceptual fields:

| Field | Notes |
|---|---|
| `campaign_id` | opaque stable random identity |
| `project_id` | owning project |
| `workspace_id` | owning workspace |
| `snapshot_id` | exact bound snapshot |
| `chunk_set_id` | exact bound chunk set |
| `corpus_id` | from product snapshot / authoring binding |
| `corpus_name` | from product snapshot / authoring binding |
| `selection_policy` | versioned provenance |
| `baseline_authoring_run_id` | imported baseline identity |
| `baseline_sha256` | hash of immutable baseline bytes |
| `created_at` | creation timestamp |
| `status` | campaign lifecycle status |

`snapshot_id` / `chunk_set_id` **MUST NOT** mutate after campaign creation.

A new workspace snapshot requires a **new** campaign where new adjudication is
appropriate. No filename / fuzzy / similarity migration of historical labels
(S16-D29).

---

## 16F-D03 — Campaign creation binding

Initial 16F campaign creation is from the **CURRENT ACTIVE** workspace snapshot.

Creation **MUST**:

1. load the Workspace record;
2. require workspace status **ACTIVE**;
3. resolve `workspace.current_snapshot_id` through the existing product snapshot;
4. obtain exact `snapshot_id` / `chunk_set_id` / `corpus_id` / `corpus_name`;
5. validate the imported `GoldAuthoringRun` (`offline-rag-gold-authoring-v1`);
6. require exact compatible `chunk_set_id`;
7. verify corpus identity where present;
8. copy the authoring run into immutable campaign baseline storage;
9. record SHA-256 of baseline bytes.

If any binding differs: **FAIL CLOSED**.

After creation, workspace mutation:

- **MUST NOT** update campaign binding;
- **MUST NOT** migrate judgments;
- **MUST NOT** substitute CURRENT chunk set.

Historical campaigns remain historical.

---

## 16F-D04 — Persistence root

Candidate implementation root:

```text
data/gold-lab/
```

Later implementation **MAY** add:

```text
PathSettings.gold_lab = Path("data/gold-lab")
```

Conceptual layout:

```text
data/gold-lab/
  projects/<project_id>/project.json

  campaigns/<campaign_id>/
    campaign.json
    baseline/
      authoring_run.json
    ledger/
      <sequence>_<record_id>.json
    projection/
      authoring_run.json

  datasets/<dataset_id>/
    meta.json
    cases.jsonl

  registrations/<dataset_id>/<campaign_id>.json
```

Private Gold Lab state remains under `/data`.
**MUST NOT** commit user/private Gold Lab data to Git.

---

## 16F-D05 — Identity model

| Identity | Class | Notes |
|---|---|---|
| `project_id` | opaque stable random | |
| `campaign_id` | opaque stable random | |
| `task_id` | **deterministic** stable | from canonical task identity |
| ledger record id | opaque unique append | |
| `judgment_id` | opaque unique | judgment records |
| case identity | existing | `SilverCase.draft_case_id` |
| candidate identity | existing | `chunk_id` |
| dataset identity | existing | GoldDataset-v1 `gold_<sha256>` |

`task_id` **MUST NOT** depend on:

- timestamp;
- UI ordering;
- retrieval score / rank;
- presentation cosmetics.

For an absolute relevance task, stable identity includes at least:

```text
campaign_id
task semantic kind
case_id
candidate chunk_id
semantic_contract
```

**Query fingerprint is NOT part of stable task identity.**

Reason: a semantic query edit invalidates the old judgment and requires
rejudgment, but **MUST NOT** create a second scoring identity for the same
campaign / case / candidate task.

---

## 16F-D06 — Atomic resumable task model

Gold Lab human work units are atomic and resumable (S16-D24).

Data-plane task kinds **MUST** support:

| Kind | Role |
|---|---|
| `absolute_relevance` | canonical 0/1/2 |
| `question_check` | accept / edit / reject question |
| `auxiliary_preference` | non-canonical preference (e.g. Chunk Duel) |
| `hard_call` | designated hard-call resolution |

16F may initially materialize only kinds needed by backend tests; **16G** owns
game presentations.

Case completion and Gold finalization are **completion milestones**, not
separate relevance semantics.

Task state is a deterministic projection:

```text
pending
completed
```

**MUST NOT** introduce:

- distributed queue;
- task leasing;
- multi-user ownership;
- learner identity.

Future 16G workload choices (`1`, `5`, `10`, `25`, complete case, until stop)
**MUST** be implementable by selecting pending tasks from this data plane.
16F itself does **not** implement the chooser UI.

---

## 16F-D07 — Append-only ledger

Ledger contract name:

```text
offline-rag-gold-lab-ledger-v1
```

The ledger is the **audit authority** (S16-D25).

Recommended physical representation: one immutable JSON record per file:

```text
campaigns/<campaign_id>/ledger/
  000000000001_<record_id>.json
  000000000002_<record_id>.json
  ...
```

Sequence allocation + publication occurs under a campaign-local filesystem lock.
Each record is written atomically.

Existing records **MUST NEVER** be rewritten or deleted during ordinary
correction.

Projection reads records in monotonically increasing sequence order.

Malformed / missing / duplicate sequence or invalid record: **FAIL CLOSED**.
Do not repair silently.

---

## 16F-D08 — Ledger provenance

All judgment records **MUST** support S16-D25 provenance:

| Field | Notes |
|---|---|
| `judgment_id` | opaque unique |
| `task_id` | deterministic stable task |
| `project_id` | |
| `campaign_id` | |
| `workspace_id` | |
| `snapshot_id` | campaign-bound |
| `chunk_set_id` | campaign-bound |
| `authoring_run_id` | baseline / projected identity |
| `case_id` | `draft_case_id` |
| query identity / fingerprint | bound at commit time |
| candidate identity | where applicable |
| `semantic_contract` | separate from presentation |
| `game_id` / `presentation_id` | where applicable |
| `selection_policy` | provenance |
| timestamp | |
| `supersedes_judgment_id` | when corrected |

Absolute judgment:

```text
relevance = strict integer 0 | 1 | 2
```

Auxiliary preference:

- **MUST** be explicitly typed auxiliary;
- **MUST NOT** silently project into canonical 0/1/2 Gold truth.

The ledger **MAY** define additional versioned event record types for:

- `question_check`;
- `case_completion`;
- `hard_call_resolution`;
- `gold_export_registration`.

All event types remain explicit and versioned.

---

## 16F-D09 — Idempotency

Gold Lab mutation commands **MUST** be idempotent, with semantics equivalent to
existing workspace mutation behavior:

```text
same idempotency key + same canonical request
  → same result / same ledger record

same idempotency key + different canonical request
  → explicit conflict
```

A retry **MUST NOT** append another effective contribution.

Idempotency metadata / request fingerprint **MUST** be durable enough to survive
process restart.

**MUST NOT** rely only on React / client deduplication.

---

## 16F-D10 — Correction / supersession

Corrections append new records. Never erase the prior judgment.

For canonical relevance correction:

```text
new judgment.supersedes_judgment_id
  MUST reference the currently effective judgment for the SAME task
```

Reject:

- unknown superseded id;
- cross-task supersession;
- cross-campaign supersession;
- superseding a non-current judgment;
- branching correction chains.

Effective state contains one current canonical judgment per stable task.
Historical chain remains inspectable.

---

## 16F-D11 — Query-basis invalidation

Preserve existing Slice-9 HumanReview semantics.

Each canonical absolute judgment **MUST** be bound to the effective query
identity used when the grade was committed, via a deterministic canonical query
fingerprint.

If Question Check later changes the effective query:

1. historical judgments remain in the ledger;
2. judgments bound to the old query cease to be CURRENT / EFFECTIVE;
3. those candidate tasks become `pending` again;
4. old grades **MUST NOT** project into current `HumanReview`;
5. old grades **MUST NOT** contribute current judgment points;
6. no history is erased.

Projection **MUST** set `HumanReview.grade_basis_query` to the exact effective
query when current judgments exist.

---

## 16F-D12 — Benchmark vs Improvement Gold

`project_type` **MUST** be explicit:

```text
benchmark
improvement
```

Selection policy is versioned provenance.

| Type | Selection | Use |
|---|---|---|
| Benchmark | representative / frozen | unbiased evaluation claims (separately governed) |
| Improvement | uncertainty, disagreement, errors, hard negatives, regressions, source-version changes, other recorded diagnostic policies | diagnosis / future improvement |

Improvement Gold **MUST NOT** be presented as unbiased benchmark evidence
(S16-D28).

A 16F project of type `benchmark` does **NOT** by itself:

- complete Slice 9G;
- become publication-grade validation;
- authorize portfolio scientific claims;
- authorize retrieval / config promotion.

**9G** remains **DEFERRED / NOT AUTHORIZED**.

---

## 16F-D13 — Immutable baseline + derived projection

At campaign creation, copy the validated `GoldAuthoringRun` into:

```text
campaigns/<campaign_id>/baseline/authoring_run.json
```

Treat that file as immutable campaign baseline.
The pre-existing Slice-9 authoring run remains untouched.

Current Gold Lab review state is derived:

```text
immutable baseline
+
effective Gold Lab ledger
=
projected GoldAuthoringRun
```

Projection output **MAY** be cached at:

```text
projection/authoring_run.json
```

but it is **DERIVED / REBUILDABLE**. Ledger + baseline remain authority.

---

## 16F-D14 — SilverCase / HumanReview projection

Projection **MUST** use existing:

- `SilverCase`
- `HumanReview`
- `HumanJudgment`
- `HumanReviewStatus`

Do not create replacement scientific review models.

For canonical candidate judgments, preserve the full human grade map including
**0 / 1 / 2**.

Map question state + candidate coverage back to existing review invariants:

| Condition | Status |
|---|---|
| question accepted unchanged + complete current candidate grading + ≥1 positive | `ACCEPTED` |
| question edited + complete current candidate grading against edited query + ≥1 positive | `EDITED` |
| question rejected | `REJECTED` |
| partial / incomplete | `PENDING` |

Complete all-zero candidate grading:

- **MUST NOT** fabricate Gold eligibility;
- must remain non-finalizable until expert disposition makes the case valid
  (e.g. question rejection / later correction).

Existing model / prelabel judgments remain advisory and unchanged.

---

## 16F-D15 — Blind expert authority

Before independent expert judgment, task presentation / data transfer **MUST
NOT** expose (S16-D31):

- retrieval method;
- retrieval rank;
- retrieval score;
- model relevance grade;
- model agreement;
- model confidence;
- reward / score for agreeing with model.

The immutable baseline may contain prelabel information internally.
The pre-commit task view / projection **MUST** exclude it.

After commitment, authoritative source context **MAY** be exposed as allowed by
S16-D31.

**16G** owns the visual / game implementation later.

---

## 16F-D16 — Canonical export

Final export **MUST** remain:

```text
offline-rag-gold-v1
meta.json
cases.jsonl
```

Do not add scientific fields to GoldDataset-v1 identity.

16F **MUST** project to a valid existing `GoldAuthoringRun` / `HumanReview`
state and reuse existing Gold finalization semantics
(`src/offline_rag/gold_authoring/finalize.py`).

Canonical export preserves:

- human **0** grades in ledger / projected HumanReview;

while GoldDataset-v1 contains only positive:

- **1** supporting;
- **2** direct;

as today.

No automatic model labels enter `GoldDataset`.

---

## 16F-D17 — Immutable dataset storage / registration

Candidate storage:

```text
data/gold-lab/datasets/<dataset_id>/
  meta.json
  cases.jsonl
```

A dataset directory is immutable.

If the same `dataset_id` already exists:

- validate existing bytes / semantic identity;
- treat exact equivalent publication as idempotent;
- conflict / fail on mismatch.

No `--force` overwrite semantics for registered Gold Lab datasets.

Registration contract candidate:

```text
offline-rag-gold-registration-v1
```

Registration path:

```text
data/gold-lab/registrations/<dataset_id>/<campaign_id>.json
```

Record at least:

- `dataset_id`
- `project_id`
- `campaign_id`
- `project_type`
- `workspace_id`
- `snapshot_id`
- `chunk_set_id`
- baseline authoring_run identity / hash
- projection identity / hash
- dataset path
- registration timestamp

Registration **MUST** validate with existing `load_gold_dataset()`.

“Registered” **MUST NOT** mean “production promoted” (S16-D30).

---

## 16F-D18 — Gold Contribution contract

Scoring contract id:

```text
gold-contribution-v1
```

Projection is deterministic over **EFFECTIVE UNIQUE COMPLETED** identities
(S16-D34). Weights inherited exactly:

| Points | Effective completed contribution |
|---|---|
| 1 | currently effective canonical absolute 0/1/2 expert judgment for one unique stable candidate task |
| 5 | Question Check completed once per stable question-check identity |
| 10 | complete evidence map / case once per stable campaign/case identity |
| 15 | Gold case finalized once per stable campaign/case identity |
| 5 | designated Hard Call resolved once per stable hard-call identity |

No points merely for auxiliary pairwise preference.

**MUST NOT:**

- speed bonus;
- model-agreement bonus;
- leaderboard semantics.

Idempotent retries: **NO** duplicate score.
Judgment correction: **NO** duplicate judgment point.
Reopen / re-complete: **NO** second completion bonus for the same stable
identity.

Expose from the same projection:

- total contribution score;
- expert judgment count;
- questions reviewed;
- cases completed;
- Gold finalized count;
- campaign coverage / progress.

Score is engagement / progress metadata, **not** scientific truth.

---

## 16F-D19 — Crash / concurrency model

Slice 16 remains local / single-product-instance.
Multi-worker / shared-state redesign is **DEFERRED** (S16-D35).

Use filesystem locks for mutation serialization.

Crash guarantees:

- existing immutable ledger records survive;
- no partially written ledger record becomes valid;
- derived projections may be rebuilt;
- incomplete export **MUST NOT** become registered;
- existing registered GoldDataset remains intact;
- no automatic scientific promotion occurs after restart.

A crash between dataset publication and registration may leave an unregistered
immutable dataset; recovery may validate / register it explicitly /
idempotently. It **MUST NOT** infer promotion.

---

## 16F-D20 — Implementation subphases

Later implementation remains separately gated.

### 16F-A — Contracts & persistence foundation

- package boundary;
- settings / path root;
- project / campaign models;
- identities;
- exact workspace snapshot / chunk binding;
- immutable authoring baseline import;
- ledger record contracts;
- append primitive / locking;
- **NO** API;
- **NO** UI;
- **NO** Gold export.

### 16F-B — Effective-state / tasks / scoring

- deterministic task identities;
- pending / completed task projection;
- idempotency;
- correction / supersession fold;
- query-basis invalidation;
- effective state;
- contribution-v1 projection;
- **NO** games / UI.

### 16F-C — Scientific projection / export / registration

- deterministic SilverCase / HumanReview projection;
- existing invariant reuse;
- GoldDataset-v1 finalization;
- immutable dataset storage;
- local registration;
- existing evaluation-loader compatibility;
- no retrieval / config promotion.

### 16F-D — Application / API data plane

Exact HTTP DTOs / errors **MUST** be frozen before implementation of 16F-D.

Purpose: provide the safe backend surface required by future **16G**.

No Gold Lab games / UI in 16F-D.
No 16G implementation by implication.

---

## Acceptance invariants (future tests)

Future implementation authorization **MUST** require tests covering at least:

1. project / campaign ids stable;
2. exact `snapshot_id` / `chunk_set_id` binding;
3. campaign does not follow workspace CURRENT after source mutation;
4. baseline run copied / hashed / immutable;
5. candidate chunk identities resolve against bound chunk set;
6. append ledger never rewrites historical records;
7. interrupted append does not produce a valid record;
8. same idempotency key + same request returns same result;
9. same key + different request conflicts;
10. supersession cannot branch / cross task / cross campaign;
11. only current judgment is effective;
12. query edit invalidates old-query judgments without erasing history;
13. partial review safely resumes;
14. expert pre-commit view excludes model / rank / score signals;
15. Silver / HumanReview projection is deterministic;
16. human 0 grades retained in review projection;
17. GoldDataset-v1 export remains positive-only 1/2;
18. all-zero case cannot be falsely finalized;
19. exported dataset validates through existing `load_gold_dataset()`;
20. registered dataset uses exact `dataset_id`;
21. re-registration is idempotent;
22. benchmark / improvement provenance remains distinct;
23. retries / corrections do not inflate contribution score;
24. no retrieval / default / config promotion;
25. no 9G status change.

---

## Explicit non-scope

**MUST NOT** implement or authorize in 16F:

- 16G game UI (Rapid Fire, Evidence Sweep, Question Check, Chunk Duel);
- training compiler;
- leaderboards;
- learner identity / mastery / spaced repetition;
- 9G production-gold expansion;
- formal 9H;
- retrieval promotion;
- reranker / model fine-tuning;
- automatic training;
- external annotation SaaS;
- authentication / multi-user;
- distributed queues;
- M7 closeout;
- edits to pinned `docs/milestone7_performance_ui.md` / Engineering evidence
  registry / manifest as part of opening 16F.

---

## Repository verification notes (design-time)

Verified against sealed baseline `d53b296…`:

| Check | Result |
|---|---|
| `offline-rag-gold-v1` in `evaluation/gold.py` | present |
| `offline-rag-gold-authoring-v1` in `gold_authoring` | present |
| `GoldAuthoringRun` / `SilverCase` | present |
| `HumanReview` / `HumanJudgment` / `HumanReviewStatus` | present |
| `finalize.py` + `load_gold_dataset()` | present |
| existing `src/offline_rag/app/gold_lab/` | **absent** (no conflicting implementation) |
| GoldDataset `ChunkJudgment.relevance` | `Literal[1, 2]` only |
| HumanJudgment.relevance | `Literal[0, 1, 2]` |

---

## Design disposition

```text
16F DESIGN GATE: OPEN (this candidate)
16F IMPLEMENTATION: NOT AUTHORIZED
16F-A … 16F-D: NOT AUTHORIZED
16G–16H: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED

Do not self-accept.
Independent design review + human design acceptance required before any
implementation authorization.
```
