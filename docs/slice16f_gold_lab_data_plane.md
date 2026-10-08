# 16F — Gold Lab Data Plane — Design Candidate

```text
16F GOLD LAB DATA PLANE
DESIGN CANDIDATE — REWORK 1

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

INITIAL DESIGN CANDIDATE:
e50b041ae8ef5a8624b74e00c4f32b859be62458
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

Rework 1 closes implementation-readiness gaps (R1-01 … R1-18) without redesigning
D01–D20 architecture.

## Existing scientific contracts (must reuse)

| Contract / type | Location | Identity |
|---|---|---|
| Finished gold | `src/offline_rag/evaluation/gold.py` | `offline-rag-gold-v1` |
| Authoring artifact | `src/offline_rag/gold_authoring/` | `offline-rag-gold-authoring-v1` |
| Authoring run | `GoldAuthoringRun` | `models.py` |
| Silver case | `SilverCase` | `draft_case_id` |
| Human review | `HumanReview` / `HumanJudgment` / `HumanReviewStatus` | `review_models.py` |
| Query canonicalize | `canonicalize_query()` | `review_models.py` |
| Finalizer | `src/offline_rag/gold_authoring/finalize.py` | projects to GoldDataset-v1 |
| Loader | `load_gold_dataset()` | fail-closed validation |
| Product snapshot | `CorpusReadSnapshot` | `app/snapshot.py` |
| Snapshot identity | `CanonicalSnapshotManifest` | `identity.corpus_id`, `identity.chunk_set_id` |
| Workspace corpus | `WorkspaceRecord.backing_corpus_name` | workspace models |

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
| `project_id` | `goldproj_<uuid4hex>` |
| `workspace_id` | owning workspace |
| `title` | human title |
| `description` | human description |
| `project_type` | `benchmark` \| `improvement` |
| `created_at` | creation timestamp |
| `status` | `active` \| `archived` |

`project_type` is scientifically meaningful provenance and **MUST NOT** silently
change after project creation.

### GoldCampaign

One immutable scientific binding within a project.

Conceptual fields:

| Field | Notes |
|---|---|
| `campaign_id` | `goldcamp_<uuid4hex>` |
| `project_id` | owning project (must resolve) |
| `workspace_id` | **MUST** equal `project.workspace_id` |
| `snapshot_id` | exact bound snapshot |
| `chunk_set_id` | exact bound chunk set |
| `corpus_id` | exact bound corpus id |
| `corpus_name` | exact bound corpus name |
| `selection_policy` | `gold-selection-policy-v1` (typed) |
| `baseline_authoring_run_id` | imported baseline identity |
| `baseline_sha256` | SHA-256 of immutable baseline bytes |
| `workspace_revision_at_creation` | revision captured at successful create |
| `created_at` | creation timestamp |
| `status` | `open` \| `closed` |

`snapshot_id` / `chunk_set_id` / `corpus_id` / `corpus_name` **MUST NOT** mutate
after campaign creation.

`project_type` is inherited from `GoldProject` and **MUST NOT** be independently
rewritten at campaign level.

No cross-workspace campaign under a project:

```text
campaign.project_id → project
campaign.workspace_id == project.workspace_id
```

A new workspace snapshot requires a **new** campaign where new adjudication is
appropriate. No filename / fuzzy / similarity migration of historical labels
(S16-D29).

### Lifecycle states (R1-05)

**GoldProject.status**

```text
active
archived
```

Transition: `active → archived` only. **No unarchive** in 16F v1.

Archived project:

- readable;
- existing artifacts readable;
- **no** new campaign creation;
- **no** new Gold Lab adjudication mutation through that project.

**GoldCampaign.status**

```text
open
closed
```

Transition: `open → closed` only. **No reopen** in 16F v1.

Closed campaign:

- readable;
- ledger immutable;
- **no** new / corrected human decisions;
- existing valid derived / export artifacts remain readable.

Export / registration of already-valid projected work **MAY** occur after
closure. Closing **MUST NOT** fabricate completeness.

---

## 16F-D03 — Campaign creation binding

### Pristine baseline human state (R1-01)

16F v1 campaign creation **MUST** accept only an authoring baseline with **no**
pre-existing substantive human adjudication.

For every `SilverCase`, **ACCEPT** when:

- `human_review` is absent; **or**
- `human_review` is semantically empty:
  - `status = pending`
  - `judgments = []`
  - `query_override = null`
  - `category_override.is_overridden = false`
  - `category_override.value = null`
  - `tags_override = null`
  - `grade_basis_query = null`

**REJECT** campaign import if any case contains:

- human judgment;
- `accepted` / `edited` / `rejected` status;
- query override;
- category override;
- tags override;
- grade basis;
- any other substantive human-review state.

Failure: explicit `baseline_human_state_present`-style error.

Model / prelabel state **MAY** remain in baseline. It remains advisory and
**MUST** be hidden from blind pre-commit task views.

**MUST NOT** implement migration / bootstrap of historical reviewed Slice-9 runs
in 16F v1 (future separately governed compatibility scope).

### Exact workspace / corpus / chunk binding (R1-02)

A 16F v1 baseline **MUST** have non-null / nonblank:

- `corpus_name`
- `corpus_id`
- `chunk_set_id`

Campaign creation requires **exact** equality:

```text
baseline.chunk_set_id
  == resolved_workspace_snapshot.identity.chunk_set_id

baseline.corpus_id
  == resolved_workspace_snapshot.identity.corpus_id

baseline.corpus_name
  == workspace.backing_corpus_name

resolved_workspace_snapshot.corpus_name
  == workspace.backing_corpus_name
```

Any mismatch: **FAIL CLOSED**.

Campaign stores these exact values. No aliasing, source-name matching, or fuzzy
migration.

### CURRENT-snapshot creation race (R1-03)

Campaign creation binds CURRENT ACTIVE workspace state. Freeze:

1. capture `workspace_id`;
2. capture workspace revision;
3. capture `current_snapshot_id`;
4. resolve that exact snapshot (`CorpusReadSnapshot`);
5. validate baseline against it;
6. before durable campaign publication, re-read / revalidate the workspace.

Required at commit:

```text
workspace still ACTIVE
workspace revision unchanged
current_snapshot_id unchanged
```

Otherwise: **STALE / CONFLICT** — **NO** campaign publication.

Record `workspace_revision_at_creation` in GoldCampaign provenance.

A later workspace mutation does **NOT** invalidate or rewrite an already
committed campaign.

### Candidate identity validation (R1-18)

Before campaign commit, validate every baseline case / candidate / source-seed
identity needed by the campaign against the bound immutable chunk set.

At minimum: all candidate `chunk_id`s exist in bound `chunk_set_id`.

Any unresolved candidate: **FAIL CLOSED**.

No CURRENT substitution. No omission. No fuzzy matching.

### Creation steps (summary)

1. load Workspace record;
2. require ACTIVE workspace;
3. require project resolvable and `project.workspace_id` match;
4. capture revision + `current_snapshot_id`;
5. resolve exact `CorpusReadSnapshot`;
6. validate imported `GoldAuthoringRun` (authoring-v1 + pristine human state);
7. require exact corpus / chunk_set equalities above;
8. validate all candidate chunk ids against bound chunk set;
9. copy authoring run into immutable campaign baseline storage;
10. record `baseline_sha256` of baseline bytes;
11. re-read / revalidate ACTIVE + revision + snapshot;
12. publish campaign atomically with `workspace_revision_at_creation`.

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

## 16F-D05 — Identity model (R1-07)

### Prefixes

| Identity | Form |
|---|---|
| `project_id` | `goldproj_<uuid4hex>` |
| `campaign_id` | `goldcamp_<uuid4hex>` |
| ledger record id | `goldrec_<uuid4hex>` |
| `judgment_id` | `goldjud_<uuid4hex>` |
| `task_id` | `goldtask_<sha256>` |
| query fingerprint | `goldquery_<sha256>` |
| hard-call designation | `goldhard_<sha256>` |
| case identity | existing `SilverCase.draft_case_id` |
| candidate identity | existing `chunk_id` |
| dataset identity | existing GoldDataset-v1 `gold_<sha256>` |

Use existing repository UUID / hash helpers where compatible
(`new_execution_id`-style uuid4hex; canonical JSON hashing for digests).

### Deterministic task payloads

Task IDs use deterministic canonical JSON over the payloads below, then
`goldtask_<sha256(...)>`.

**Absolute relevance — EXACTLY:**

```json
{
  "campaign_id": "...",
  "task_kind": "absolute_relevance",
  "case_id": "...",
  "candidate_chunk_id": "...",
  "semantic_contract": "..."
}
```

**Question Check — EXACTLY:**

```json
{
  "campaign_id": "...",
  "task_kind": "question_check",
  "case_id": "...",
  "semantic_contract": "..."
}
```

**Auxiliary pairwise preference:**

```json
{
  "campaign_id": "...",
  "task_kind": "auxiliary_preference",
  "case_id": "...",
  "candidate_pair": ["lower_chunk_id", "higher_chunk_id"],
  "semantic_contract": "..."
}
```

Pair order **MUST** be canonical / sorted.
Presentation ordering **MUST NOT** affect task identity.

### Query fingerprint

```text
canonical_query = canonicalize_query(query)   # existing gold_authoring helper
query_fingerprint = goldquery_<sha256(UTF-8 bytes of canonical_query)>
```

**Do NOT** include query fingerprint in stable absolute `task_id`.

`task_id` **MUST NOT** depend on timestamp, UI ordering, retrieval score/rank,
or presentation cosmetics.

---

## 16F-D06 — Atomic resumable task model

Gold Lab human work units are atomic and resumable (S16-D24).

### Task kinds (scientific / ledger)

| Kind | Role |
|---|---|
| `absolute_relevance` | canonical 0/1/2 |
| `question_check` | accept / edit / reject question |
| `auxiliary_preference` | explicitly NON-CANONICAL preference |

**Hard Call is NOT an independent scientific task kind** (R1-12).
It is a stable **designation** on an existing canonical absolute_relevance task.

16F may initially materialize only kinds needed by backend tests; **16G** owns
game presentations.

Case completion and Gold finalization are **deterministic derived milestones**,
not separate ledger event types created merely for scoring.

### Task state

```text
pending
completed
```

Do **NOT** add fake completion for rejected questions.

### Task activation (R1-08)

**QUESTION CHECK:** active for each reviewable case.

**ABSOLUTE RELEVANCE:**

- active only when current effective question decision is `accept` or `edit`;
- before Question Check completion: absolute tasks are **not** active in
  workload projection;
- after `reject`: absolute tasks are **not** active;
- after `accept` / `edit`: absolute tasks become active;
- after semantic edit: same stable task IDs remain; judgments bound to prior
  query fingerprint are ineffective; those tasks become `pending` against the
  new query.

This keeps stable task identity while preserving query-basis correctness.

### Hard Call designation (R1-12)

For v1, hard-call designation targets an `absolute_relevance` task.

Stable identity:

```text
goldhard_<sha256({
  campaign_id,
  target_task_id,
  designation_contract
})>
```

Designation provenance **MAY** derive from diagnostic policy / model
disagreement internally.

Pre-commit expert view **MUST NOT** reveal:

- model grade;
- model agreement;
- model confidence;
- retrieval score / rank;
- why the task was machine-designated.

Resolution occurs when the designated target task has a current effective
canonical judgment.

Contribution can therefore be:

```text
+1 canonical expert judgment
+5 designated Hard Call resolution
```

without introducing a second truth label.

### Workload selection

**MUST NOT** introduce distributed queue, task leasing, multi-user ownership, or
learner identity.

Future 16G workload choices (`1`, `5`, `10`, `25`, complete case, until stop)
**MUST** be implementable by selecting pending **active** tasks from this data
plane. 16F itself does **not** implement the chooser UI.

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
Each record is written atomically. Sequence is assigned by the storage layer,
not the client.

Existing records **MUST NEVER** be rewritten or deleted during ordinary
correction.

Projection reads records in monotonically increasing sequence order.

Malformed / missing / duplicate sequence or invalid record: **FAIL CLOSED**.
Do not repair silently.

---

## 16F-D08 — Ledger provenance / envelope (R1-10, R1-11)

### Required common envelope (expert-decision records)

| Field | Notes |
|---|---|
| `schema_version` | `offline-rag-gold-lab-ledger-v1` |
| `sequence` | storage-assigned |
| `record_id` | `goldrec_<uuid4hex>` |
| `record_type` | versioned event type |
| `judgment_id` | `goldjud_<uuid4hex>` |
| `task_id` | deterministic `goldtask_<sha256>` |
| `project_id` | |
| `campaign_id` | |
| `workspace_id` | |
| `snapshot_id` | campaign-bound |
| `chunk_set_id` | campaign-bound |
| `authoring_run_id` | baseline identity |
| `case_id` | `draft_case_id` |
| `query_fingerprint` | where semantically applicable |
| `candidate_chunk_id` | where applicable |
| `semantic_contract` | separate from presentation |
| `selection_policy_id` | from campaign policy |
| `selection_policy_fingerprint` | from campaign policy |
| `game_id` | nullable |
| `presentation_id` | nullable |
| `idempotency_key` | durable |
| `request_fingerprint` | durable |
| `created_at` | |
| `supersedes_judgment_id` | nullable |
| `payload` | typed body |

All fields needed to validate campaign provenance **MUST** be checked against
the immutable `GoldCampaign` rather than trusted from caller input.

### Ledger event types (R1-11)

Freeze at least:

| `record_type` | Role |
|---|---|
| `question_check` | expert judgment |
| `absolute_relevance` | expert judgment |
| `auxiliary_preference` | explicitly NON-CANONICAL |

Do **NOT** create case-completion or Gold-finalization ledger events merely to
obtain contribution points. Those are deterministic derived milestones.

Absolute judgment payload relevance:

```text
relevance = strict integer 0 | 1 | 2
```

Auxiliary preference **MUST** be explicitly typed auxiliary and **MUST NOT**
silently project into canonical 0/1/2 Gold truth.

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

## 16F-D10 — Correction / supersession (R1-13)

Corrections append new records. Never erase the prior judgment.

### Same-query correction

New absolute judgment **MUST** supersede the currently effective judgment for
the same task / query basis.

Reject:

- branching;
- cross-task;
- cross-campaign;
- superseding a non-current same-basis judgment.

### After semantic query edit

Old-query judgments become ineffective by query fingerprint.

A new judgment for the **SAME** stable task under the **NEW** query fingerprint:

- is **NOT** required to supersede the old-query judgment;
- begins the effective chain for the new query basis.

Historical old-query chain remains intact.

### Question Check correction

Uses the same append / supersession principle against the currently effective
Question Check judgment.

Effective state contains one current canonical judgment per stable task under
the current query basis (where applicable). Historical chain remains
inspectable.

---

## 16F-D11 — Query-basis invalidation

Preserve existing Slice-9 HumanReview semantics.

Each canonical absolute judgment **MUST** be bound to the effective query
identity used when the grade was committed, via
`goldquery_<sha256(UTF-8 canonicalize_query(query))>`.

If Question Check later changes the effective query:

1. historical judgments remain in the ledger;
2. judgments bound to the old query cease to be CURRENT / EFFECTIVE;
3. those candidate tasks become `pending` again (same stable `task_id`);
4. old grades **MUST NOT** project into current `HumanReview`;
5. old grades **MUST NOT** contribute current judgment points;
6. no history is erased.

Projection **MUST** set `HumanReview.grade_basis_query` to the exact effective
query when current judgments exist.

---

## 16F-D12 — Benchmark vs Improvement Gold + selection policy (R1-06)

`project_type` **MUST** be explicit:

```text
benchmark
improvement
```

### Selection policy contract

```text
gold-selection-policy-v1
```

Required fields:

| Field | Notes |
|---|---|
| `selection_policy_id` | policy identity |
| `project_type` | `benchmark` \| `improvement` |
| `parameters` | typed policy parameters |
| `selection_policy_fingerprint` | deterministic fingerprint |

Fingerprint is deterministic over canonical JSON of:

```json
{
  "contract": "gold-selection-policy-v1",
  "selection_policy_id": "...",
  "project_type": "...",
  "parameters": { }
}
```

using repository canonical JSON hashing semantics.

Policy / fingerprint are **immutable** for one campaign.
Changing selection policy requires a **new** campaign.

Benchmark project's policy **MUST** identify benchmark / representative
semantics. Improvement project's policy **MUST** identify diagnostic /
improvement semantics.

Do not prescribe every future policy algorithm in 16F.

Improvement Gold **MUST NOT** be presented as unbiased benchmark evidence
(S16-D28).

A 16F project of type `benchmark` does **NOT** by itself complete Slice 9G,
become publication-grade validation, authorize portfolio scientific claims, or
authorize retrieval / config promotion.

**9G** remains **DEFERRED / NOT AUTHORIZED**.

---

## 16F-D13 — Immutable baseline + derived projection

At campaign creation, copy the validated pristine `GoldAuthoringRun` into:

```text
campaigns/<campaign_id>/baseline/authoring_run.json
```

Treat that file as immutable campaign baseline.
The pre-existing Slice-9 authoring run remains untouched.

### Hash provenance (R1-17)

| Field | Meaning |
|---|---|
| `baseline_sha256` | SHA-256 of exact immutable `baseline/authoring_run.json` bytes |
| `projection_sha256` | SHA-256 of exact `projection/authoring_run.json` bytes used for export |

Do **not** call those semantic dataset identities.

Gold scientific dataset identity remains existing:

```text
gold_<sha256>
```

from GoldDataset-v1 semantic payload (`gold_dataset_id_from_payload`).

Current Gold Lab review state is derived:

```text
immutable baseline
+
effective Gold Lab ledger
=
projected GoldAuthoringRun
```

Projection output **MAY** be cached at `projection/authoring_run.json` but is
**DERIVED / REBUILDABLE**. Ledger + baseline remain authority.

---

## 16F-D14 — Question Check + SilverCase / HumanReview projection

### Question Check semantics (R1-09)

Current question-decision values:

```text
accept
edit
reject
```

Question Check is itself an append-only expert decision.

| Decision | Effect |
|---|---|
| `accept` | effective query / category / tags equal canonical proposal values |
| `edit` | record complete effective query / category / tags; require ≥1 semantic difference from proposal |
| `reject` | case projects to `HumanReviewStatus.REJECTED` |

Question Check corrections append and supersede the current Question Check
decision. Historical decisions remain. Only latest valid current decision is
effective.

### Silver / HumanReview projection

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
- reward / score for agreeing with model;
- why a Hard Call was machine-designated.

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

## 16F-D17 — Immutable dataset storage / registration (R1-16)

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

Registration is immutable once created.

First successful registration:

1. validate dataset through `load_gold_dataset()`;
2. verify `dataset_id`;
3. write registration atomically;
4. assign `registered_at` once.

Retry with same dataset / campaign and canonical equivalent registration:

- return existing registration;
- **DO NOT** rewrite;
- **DO NOT** change `registered_at`.

Conflicting existing registration: **FAIL CLOSED**.

Registration should include or make deterministically recoverable **exported
case IDs** so Gold-finalized contribution projection can determine which stable
campaign / case identities were finalized.

Record at least:

- `dataset_id`
- `project_id`
- `campaign_id`
- `project_type`
- `workspace_id`
- `snapshot_id`
- `chunk_set_id`
- baseline authoring_run identity / `baseline_sha256`
- `projection_sha256`
- dataset path
- `registered_at`
- exported case IDs (or recoverable equivalent)

“Registered” **MUST NOT** mean “production promoted” (S16-D30).

---

## 16F-D18 — Gold Contribution contract (R1-14, R1-15)

Scoring contract id:

```text
gold-contribution-v1
```

Projection is deterministic over **EFFECTIVE UNIQUE COMPLETED** identities
(S16-D34).

### A. Expert judgment +1

Count one when:

- absolute task is currently active;
- one current canonical judgment exists;
- judgment `query_fingerprint` equals current effective query fingerprint.

Old-query / superseded judgments: **0** current points.

### B. Question Check +5

Count once per stable campaign / case Question Check task when a current
effective decision exists: `accept` | `edit` | `reject`.

Correction / retry: never more than one bonus.

### C. Complete evidence map / case +10

Count once when:

- current question decision is `accept` or `edit`;
- every current candidate absolute task has a current effective judgment for
  the current query.

A complete all-zero map **MAY** receive the work-completion bonus but remains
scientifically non-finalizable under existing Gold rules.

`reject`: no case-complete bonus.

### D. Gold case finalized +15

Count once per stable campaign / case when that case appears in at least one
valid immutable GoldDataset registration for that campaign.

This is sticky historical completion: later correction / reopen does not award
a second bonus and does not erase that a valid immutable historical
finalization occurred.

Maximum 15 points per campaign / case for this category.

### E. Hard Call +5

Count once when:

- stable hard-call designation exists;
- target task currently has an effective canonical resolution.

If query edit invalidates the target judgment: Hard Call bonus becomes
non-effective until rejudged.

Never duplicate from correction / retry.

### Forbidden bonuses

No points merely for auxiliary pairwise preference.

**MUST NOT:** speed bonus; model-agreement bonus; leaderboard semantics.

### Raw counters (same projection)

| Counter | Definition |
|---|---|
| `expert_judgments` | count of current effective absolute tasks |
| `questions_reviewed` | stable Question Check tasks with current effective decision |
| `cases_completed` | count satisfying R1-14.C |
| `gold_finalized` | count satisfying R1-14.D |
| `hard_calls_resolved` | count satisfying R1-14.E |

**Campaign coverage:**

- numerator / denominator from **active** canonical absolute tasks;
- rejected cases are **excluded** from the denominator (absolute tasks not
  active after reject).

No counter from raw ledger row count.

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
- project / campaign models + lifecycle;
- identities + selection-policy contract;
- exact workspace snapshot / chunk / corpus binding;
- pristine-baseline admission;
- CURRENT-snapshot race revalidation;
- candidate chunk-set validation;
- immutable authoring baseline import;
- ledger record contracts / envelope;
- append primitive / locking;
- **NO** API;
- **NO** UI;
- **NO** Gold export.

### 16F-B — Effective-state / tasks / scoring

- deterministic task identities + activation;
- Question Check semantics;
- pending / completed task projection;
- idempotency;
- correction / supersession fold;
- query-basis invalidation;
- Hard Call designation;
- contribution-v1 projection + counters;
- **NO** games / UI.

### 16F-C — Scientific projection / export / registration

- deterministic SilverCase / HumanReview projection;
- existing invariant reuse;
- GoldDataset-v1 finalization;
- immutable dataset storage;
- local registration (idempotent);
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

1. project / campaign ids stable with frozen prefixes;
2. exact `snapshot_id` / `chunk_set_id` / `corpus_id` / `corpus_name` binding;
3. pristine baseline human-state admission / rejection;
4. CURRENT-snapshot race fails closed on revision / snapshot change;
5. campaign does not follow workspace CURRENT after source mutation;
6. baseline run copied / hashed / immutable (`baseline_sha256` = file bytes);
7. candidate chunk identities resolve against bound chunk set;
8. append ledger never rewrites historical records;
9. interrupted append does not produce a valid record;
10. same idempotency key + same request returns same result;
11. same key + different request conflicts;
12. supersession cannot branch / cross task / cross campaign;
13. only current same-basis judgment is effective;
14. query edit invalidates old-query judgments without erasing history and
    without requiring supersession of old-query judgments;
15. task activation: absolute inactive before Question Check / after reject;
16. partial review safely resumes;
17. expert pre-commit view excludes model / rank / score / hard-call reason;
18. Silver / HumanReview projection is deterministic;
19. human 0 grades retained in review projection;
20. GoldDataset-v1 export remains positive-only 1/2;
21. all-zero case cannot be falsely finalized (may earn case-complete points);
22. exported dataset validates through existing `load_gold_dataset()`;
23. registered dataset uses exact `dataset_id`;
24. re-registration is idempotent and does not rewrite `registered_at`;
25. benchmark / improvement + selection-policy provenance remain distinct;
26. retries / corrections do not inflate contribution score;
27. Hard Call designation awards +5 only with current effective target judgment;
28. no retrieval / default / config promotion;
29. no 9G status change;
30. archived project / closed campaign mutation gates enforced.

---

## Explicit non-scope

**MUST NOT** implement or authorize in 16F:

- 16G game UI (Rapid Fire, Evidence Sweep, Question Check UI, Chunk Duel);
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
- migration / bootstrap of historically reviewed Slice-9 authoring runs;
- edits to pinned `docs/milestone7_performance_ui.md` / Engineering evidence
  registry / manifest as part of opening 16F.

---

## Repository verification notes (design-time)

Verified against sealed baseline / this design branch:

| Check | Result |
|---|---|
| `offline-rag-gold-v1` in `evaluation/gold.py` | present |
| `offline-rag-gold-authoring-v1` in `gold_authoring` | present |
| `GoldAuthoringRun` / `SilverCase` | present |
| `HumanReview` / `HumanJudgment` / `HumanReviewStatus` | present |
| `canonicalize_query()` in `review_models.py` | present |
| `finalize.py` + `load_gold_dataset()` | present |
| `CorpusReadSnapshot` + `identity.corpus_id` / `identity.chunk_set_id` | present |
| `WorkspaceRecord.backing_corpus_name` | present |
| existing `src/offline_rag/app/gold_lab/` | **absent** |
| GoldDataset `ChunkJudgment.relevance` | `Literal[1, 2]` only |
| HumanJudgment.relevance | `Literal[0, 1, 2]` |

---

## Rework 1 closure checklist

```text
R1-01 Baseline human-state admission: FROZEN
R1-02 Exact workspace/corpus/chunk binding: FROZEN
R1-03 CURRENT-snapshot race: FROZEN
R1-04 Project/campaign relation: FROZEN
R1-05 Lifecycle states: FROZEN
R1-06 Selection-policy contract: FROZEN
R1-07 Identity algorithms: FROZEN
R1-08 Task activation: FROZEN
R1-09 Question Check semantics: FROZEN
R1-10 Ledger envelope: FROZEN
R1-11 Ledger event types: FROZEN
R1-12 Hard Call semantics: FROZEN
R1-13 Supersession/query-basis semantics: FROZEN
R1-14 Contribution projection: FROZEN
R1-15 Raw counters: FROZEN
R1-16 Registration idempotency: FROZEN
R1-17 Hash provenance: FROZEN
R1-18 Campaign create candidate validation: FROZEN
```

---

## Design disposition

```text
16F DESIGN GATE: OPEN (candidate — Rework 1)
16F IMPLEMENTATION: NOT AUTHORIZED
16F-A … 16F-D: NOT AUTHORIZED
16G–16H: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED

Do not self-accept.
Do not mark ACCEPTED / LOCKED.
Independent design review + human design acceptance required before any
implementation authorization.
```
