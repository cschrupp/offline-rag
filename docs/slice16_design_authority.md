# Slice 16 — Portfolio-Grade Knowledge & Training UI — Design Authority

```text
HISTORICAL STATUS SNAPSHOT / PRE-A2
Captured before Amendment A2.
Not the current implementation-gate state.
Current status is governed by accepted A2 and the Authorization note
later in this document.

STATUS: ACCEPTED / LOCKED
DESIGN INTERVIEW: COMPLETE
HUMAN ACCEPTANCE: ACCEPTED
AUTHORITY SHA: e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
16A: COMPLETE / ACCEPTED
ACCEPTED SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
16B: COMPLETE / ACCEPTED
ACCEPTED SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16C: COMPLETE / ACCEPTED
ACCEPTED SHA: 936e41446eb1e3697f6b7d245659831f19cf0613
16D-A: COMPLETE / ACCEPTED
ACCEPTED SHA: 4f8962f2893ab433e6ea269ad54e46f67771ca70
16D-B: IMPLEMENTED CANDIDATE / HUMAN ACCEPTANCE PENDING
16D-C: NOT AUTHORIZED
AMENDMENT A1: ACCEPTED / LOCKED
  5060e2aeb4825f265072a1f870c3c963eace3b30
  docs/slice16_amendment_a1_seneca_product_ux.md
BASELINE: c72215186524c9937de789adb1cf2056be13ea23
```

**Authority role:** This document is the Slice 16 **design authority**.
S16-D01 … S16-D35 are **normative** Slice-16 design decisions. Design was
accepted and locked at AUTHORITY SHA
`e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`. Acceptance/lock of design does
**not** by itself authorize implementation; **16A**, **16B**, **16C**, and
**16D-A** were separately authorized and are now **COMPLETE / ACCEPTED** at
`e73959be508541a1c50d4919606aaf3157a5fa8a`,
`eb8baefc6e3eaf7df33668c85fbbfef22364bb0e`,
`936e41446eb1e3697f6b7d245659831f19cf0613`, and
`4f8962f2893ab433e6ea269ad54e46f67771ca70`.

**Historical / pre-A2 status note (not current):** under the undivided A1
Ask/Evidence gate, **16D-B** was recorded as **IMPLEMENTED CANDIDATE /
HUMAN ACCEPTANCE PENDING**, and **16D-C** as **NOT AUTHORIZED**. That
vocabulary is preserved as provenance only. Current implementation-gate
state is governed by accepted Amendment A2 and the Authorization note
later in this document (observed B1 product UX withheld; B1 foundation
remediation **ACCEPTED / SEALED**; **16D-B2 COMPLETE / ACCEPTED / SEALED**;
**16D-B3 COMPLETE / ACCEPTED / SEALED** at `9c178ffb033cde41849379fc914f321697ff8691`; A3 **ACCEPTED / LOCKED / SEALED**; **16D-C COMPLETE / ACCEPTED / SEALED**).

```text
AMENDMENT A1:
ACCEPTED / LOCKED
5060e2aeb4825f265072a1f870c3c963eace3b30
docs/slice16_amendment_a1_seneca_product_ux.md
```

S16-D01 … S16-D35 remain accepted/locked at
`e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`. Amendment A1 is **supplemental
accepted/locked** authority at `5060e2aeb4825f265072a1f870c3c963eace3b30`. A1
acceptance does **not** authorize later phase implementation. **16D-C**
remains **NOT AUTHORIZED** until separate explicit implementation
authorization.

**Related artifacts:**

- Accepted implementation plan:
  [`docs/slice16_implementation_plan.md`](slice16_implementation_plan.md)
- Amendment A1 (**ACCEPTED / LOCKED**):
  [`docs/slice16_amendment_a1_seneca_product_ux.md`](slice16_amendment_a1_seneca_product_ux.md)
  at `5060e2aeb4825f265072a1f870c3c963eace3b30`
- Accepted 16A evidence:
  [`docs/slice16a_workspace_foundation.md`](slice16a_workspace_foundation.md)
- Accepted 16B evidence:
  [`docs/slice16b_workspace_lifecycle_api.md`](slice16b_workspace_lifecycle_api.md)
- Accepted 16C evidence:
  [`docs/slice16c_react_shell_source_ui.md`](slice16c_react_shell_source_ui.md)
- Accepted 16D-A evidence:
  [`docs/slice16d_a_seneca_product_foundation_query_scope.md`](slice16d_a_seneca_product_foundation_query_scope.md)
- 16D-B implementation evidence candidate:
  [`docs/slice16d_b_ask_evidence_workspace.md`](slice16d_b_ask_evidence_workspace.md)
- Historical pre-design frame (contextual only):
  [`docs/slice16_portfolio_ui.md`](slice16_portfolio_ui.md)
- Inherited product/API architecture:
  [`docs/slice15_developer_api_packaging.md`](slice15_developer_api_packaging.md)

**Normative language:**

- **MUST / MUST NOT** — binding design requirements.
- **SHOULD** — UX / presentation recommendations that implementation ought to
  follow unless a later accepted amendment says otherwise.
- **MAY** — permitted options.
- **DEFERRED** — explicitly out of Slice 16; not authorized here.

This authority **MUST NOT** weaken accepted Slice 15 decisions. Accepted
historical benchmark/gold artifacts retain their existing governance claims
(development/regression/publication-readiness as already recorded). This
document does **not** claim a globally green test suite.

---

## Gate status (historical / pre-A2)

```text
HISTORICAL STATUS SNAPSHOT / PRE-A2
Captured before Amendment A2.
Not the current implementation-gate state.
Current status is governed by accepted A2 and the Authorization note
later in this document.

SLICE 16 DESIGN INTERVIEW:       COMPLETE
SLICE 16 DESIGN AUTHORITY:       ACCEPTED / LOCKED
AUTHORITY SHA:                   e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
SLICE 16 IMPLEMENTATION PLAN:    ACCEPTED
16A:                             COMPLETE / ACCEPTED
ACCEPTED SHA:                    e73959be508541a1c50d4919606aaf3157a5fa8a
16B:                             COMPLETE / ACCEPTED
ACCEPTED SHA:                    eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16C:                             COMPLETE / ACCEPTED
ACCEPTED SHA:                    936e41446eb1e3697f6b7d245659831f19cf0613
AMENDMENT A1:                    ACCEPTED / LOCKED
                                 5060e2aeb4825f265072a1f870c3c963eace3b30
                                 docs/slice16_amendment_a1_seneca_product_ux.md
16D-A:                           COMPLETE / ACCEPTED
ACCEPTED SHA:                    4f8962f2893ab433e6ea269ad54e46f67771ca70
16D-B3:                          COMPLETE / ACCEPTED / SEALED
16D-C:                           COMPLETE / ACCEPTED / SEALED
AMENDMENT A4:                    ACCEPTED / LOCKED / SEALED
16E–16H:                         NOT AUTHORIZED
SLICE 17:                        NOT AUTHORIZED
SLICE 18:                        NOT AUTHORIZED
9G:                              DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT:                     NOT AUTHORIZED
```

---

## S16-D01 — Product objectives

Priority order (**MUST**):

1. strong technical portfolio demonstration;
2. genuinely useful private knowledge/training product for a firefighter captain;
3. preserve accepted OfflineRAG scientific/product architecture.

Portfolio presentation **MUST** expose real system state and behavior.
**MUST NOT** introduce fake demo mode, canned answers, fabricated metrics, or
mock citations.

---

## S16-D02 — Audience

Primary presentation audience (**MUST**):

- technical recruiter;
- engineering manager;
- interviewer.

First real operational user (**MUST**):

- firefighter captain using private departmental/training material.

Junior firefighters **MAY** be Training Mode users, but Slice 16 **MUST NOT**
introduce accounts, identity, enrollment, grading, certification, or LMS
semantics.

---

## S16-D03 — Architectural boundary

Inherited boundary remains (**MUST**):

```text
Browser UI
  ↓
supported Slice-16/Slice-15 application/API surface
  ↓
src/offline_rag/app/
  ↓
domain + infrastructure
```

**MUST NOT:**

- UI → Qdrant;
- UI → retriever;
- UI → generator;
- UI-owned RAG/scientific algorithms;
- UI bypass of application/product semantics.

Existing Slice 15 `grounded_v1` pipeline remains canonical (**MUST**).

---

## S16-D04 — Production topology

Production (**MUST**):

- one OfflineRAG application/container serves both `/v1/*` backend API and
  compiled frontend static assets;
- browser and API are same-origin.

Development **MAY** use a separate Vite hot-reload process.

**MUST NOT** require a second frontend production service.

**MUST NOT** depend on a runtime CDN under strict-offline operation.

---

## S16-D05 — Frontend technology

Selected stack (**MUST**, if Slice 16 is implemented after acceptance):

- React
- TypeScript
- Vite
- React Router
- TanStack Query

Backend/server state **MUST** belong in TanStack Query or an equivalent
query/mutation abstraction. **MUST NOT** introduce Redux by default.

Local presentation state **SHOULD** remain ordinary React state/context unless
later complexity provides evidence otherwise.

Component primitives **MUST** be accessibility-capable. Exact low-level
component package **MAY** be selected during frontend implementation without
reopening architecture provided the design/accessibility contract holds.

---

## S16-D06 — Visual system / accessibility

Visual direction (**SHOULD**): modern operational knowledge system with
restrained fire-service identity.

Core palette (**SHOULD**):

| Token | Hex |
| --- | --- |
| deep navy | `#0B1F33` |
| slate | `#24384A` |
| warm surface | `#F6F7F8` |
| white | `#FFFFFF` |
| primary text | `#17212B` |
| muted text | `#5B6875` |
| action blue | `#175CD3` |
| fire-service red | `#B42318` |
| brass/gold | `#9A6700` |
| ready/success | `#027A48` |

Normal actions **MUST** use blue, not red. Red **MUST** be reserved for
identity / destructive / critical meaning.

Typography (**SHOULD**): Inter preferred with bundled/offline assets and
appropriate system fallbacks.

Accessibility target (**MUST**): WCAG 2.2 AA minimum.

Design rules (**MUST**):

- large practical targets, generally ~44×44 px where possible;
- keyboard navigation;
- visible focus;
- no color-only status;
- semantic labels/headings;
- 200% zoom usability;
- reduced-motion support;
- no hover-only required information.

---

## S16-D07 — Workspace / Notebook model

Slice 16 **MUST** introduce a stable user-facing Workspace/Notebook identity
above immutable product corpus snapshots.

Workspace conceptual fields (**MUST** support):

- `workspace_id`
- `title`
- `description`
- `revision`
- backing corpus identity
- `current_snapshot_id` | `null`
- `created_at`
- `updated_at`
- `status`

`workspace_id` **MUST** be opaque/stable. Human title **MUST NOT** be corpus
identity.

An empty workspace is valid (**MUST**):

- `current_snapshot_id = null`
- `sources = []`

Empty workspaces **MAY** be created directly, or reached by the final-source
removal / depublication transition defined in S16-D13. Empty is a first-class
workspace state, **not** a fabricated empty scientific snapshot.

---

## S16-D08 — Corpus mapping

Each non-empty active workspace **MUST** map to one server-managed OfflineRAG
product corpus whose current publication corresponds to
`current_snapshot_id`.

Ordinary users **MUST** work with workspace/source identities, not corpus
implementation names.

Workspace query adapters **MUST** ultimately invoke the same canonical
`grounded_v1` product query behavior when a current publication exists.

When a workspace is EMPTY (`sources = []` and `current_snapshot_id = null`),
workspace query **MUST** fail closed as workspace/corpus empty/not-ready and
**MUST NOT** resolve any previously current historical snapshot (S16-D13).

---

## S16-D09 — Source identity and version lineage

Distinguish (**MUST**):

- `source_id` — stable logical source identity inside a workspace;
- `document_id` — content-derived immutable scientific document identity
  (existing OfflineRAG content-identity rules);
- source version / lineage event — workspace-level version of that logical
  source.

Normative replacement rule (**MUST**):

- `source_id` remains stable for the logical source;
- every successful replacement creates a new source version / lineage event;
- `document_id` is derived from the replacement content using existing
  scientific identity rules;
- `document_id` changes **iff** the replacement content identity changes;
- a byte-identical replacement **MAY** therefore keep the same `document_id`
  while still recording a distinct source-version operation when that
  replacement is accepted as a new version;
- an idempotent retry of the same replacement operation **MUST NOT** create
  another source version.

For the normal `manual_b_v05` → `manual_b_v06` case with changed content,
`document_id` changes and S16-D12 supersession isolation still applies
unchanged.

Retain lineage metadata (**MUST**):

- source version;
- filename/display name;
- `document_id`;
- active-from workspace revision/snapshot;
- active-through revision/snapshot where applicable.

---

## S16-D10 — Local raw-source vault

Persist user source objects locally under `/data` (**MUST**).

Unchanged sources **MUST NOT** need browser re-upload when another source is
added/removed/replaced.

The raw-source vault is private product state (**MUST**).

**MUST NOT** commit private source or gold artifact content to the public
repository.

---

## S16-D11 — CRUD projection onto immutable snapshots

User-facing operations (**MUST** support):

- add source;
- remove source;
- replace source;
- display-only metadata rename/edit (workspace title/description; source
  display label / user-facing rename; other explicitly non-scientific
  presentation metadata).

### Content / membership mutations

For add / remove / replace operations that leave one or more active sources
(**MUST**):

```text
desired source set
  → isolated candidate
  → existing ingest/chunk/dense/lexical pipeline
  → validate
  → atomic publication
  → new current immutable snapshot
```

Removing the final active source is the explicit EMPTY / depublication
transition in S16-D13 (**MUST NOT** run empty Slice-15 ingest).

**MUST NOT** incrementally mutate live Qdrant/lexical scientific state merely to
mimic CRUD.

### Display-only metadata mutations

Display-only presentation metadata edits (**MUST**):

- advance workspace revision / ETag;
- persist metadata transactionally;
- **MUST NOT** rebuild the corpus;
- **MUST NOT** create a new `snapshot_id` merely because presentation metadata
  changed.

Workspace revision and scientific `snapshot_id` remain distinct for this
reason (S16-D14).

If a metadata field is later determined to participate in scientific
provenance or corpus identity, it is **not** display-only and requires a
separately frozen contract before implementation.

---

## S16-D12 — Supersession isolation

This is a hard safety invariant (**MUST**).

Example: `manual_b_v05.pdf` is replaced by `manual_b_v06.pdf`.

After successful N+1 publication:

- v06 **MUST** participate in current queries;
- v05 **MUST NOT** participate in current dense retrieval;
- v05 **MUST NOT** participate in current lexical retrieval;
- v05 **MUST NOT** participate in reranking;
- v05 **MUST NOT** enter current context;
- v05 **MUST NOT** appear in current citations;
- v05 **MUST NOT** influence current answers.

Historical snapshot N **MAY** retain v05 for provenance/history.

If processing v06 fails, snapshot N **MUST** remain current and no half-updated
product state **MUST** be exposed.

Acceptance **MUST** include unique `OLD_MARKER` / `NEW_MARKER` regression
coverage and: query N → replace → query → N+1 isolation.

---

## S16-D13 — Removal and purge

### Remove when one or more sources remain

When removal leaves one or more active sources (**MUST**):

- logically remove the source from current/future workspace state;
- project the remaining desired source set through the S16-D11 content /
  membership pipeline;
- publish a new current immutable snapshot;
- historical immutable artifacts for the removed source **MAY** remain locally.

### SPECIAL CASE — removing the final active source (EMPTY transition)

Accepted Slice-15 ingest does **not** publish empty source sets. Therefore,
when removal changes a workspace from one active source to zero active sources
(**MUST**):

- **MUST NOT** attempt empty Slice-15 ingest;
- **MUST NOT** fabricate an empty scientific snapshot;
- the workspace **MUST** atomically transition to EMPTY state:
  - `sources = []`
  - `current_snapshot_id = null`
- the backing corpus **MUST** be depublished / retired from current product
  resolution so it is no longer reachable as the current publication for
  workspace/product use;
- historical snapshot manifests/artifacts **MAY** remain locally for
  provenance;
- subsequent workspace query **MUST** fail closed as workspace/corpus
  empty/not-ready and **MUST NOT** resolve the previously current historical
  snapshot;
- adding a future first source **MUST** construct and publish a new real
  snapshot (normal S16-D11 content/membership path).

#### Backing-corpus depublication / retirement (application-level)

Slice 16 **MUST** define an application-level depublication / retirement
operation sufficient for 16A/16B to freeze DTO, error, and storage semantics
before implementation. Normative intent:

- clear or retire the active current publication pointer (or equivalent
  product-visible current publication state) for the workspace's backing
  corpus;
- preserve historical snapshot manifests/artifacts under `/data`;
- advance workspace revision / ETag as part of the same atomic EMPTY
  transition;
- leave durable operation status consistent with S16-D15;
- expose an explicit empty/not-ready failure mode for workspace query (exact
  error DTO frozen before 16B).

This is a Slice-16 application/product-resolution contract. It does **not**
authorize changing Slice-15 scientific ingest to accept empty corpora.

#### Crash consistency for final-source removal

Failure during final-source removal **MUST** leave exactly one of:

- **A.** prior one-source workspace + prior publication still active; or
- **B.** committed EMPTY workspace (`sources = []`,
  `current_snapshot_id = null`) + no active current publication.

**MUST NOT** leave split-brain state where workspace metadata says empty but
workspace query can still reach the retired source through the current
workspace/product path.

### Delete workspace

"Delete workspace" (**MUST**):

- tombstone/remove from active product catalog;
- **MUST NOT** recursively erase all historical scientific state in Slice 16.

Permanent secure purge / reachability-aware garbage collection is **DEFERRED**.

UI **MUST NOT** imply irreversible erasure when only logical removal or
depublication occurs.

---

## S16-D14 — Idempotency and optimistic concurrency

Workspace/source mutations **MUST** use:

- `Idempotency-Key: <opaque operation key>`
- workspace revision/ETag semantics via `If-Match: <expected workspace revision>`

Distinguish (**MUST**):

- operation identity;
- workspace revision;
- scientific `snapshot_id`.

Same idempotency key + same canonical request (**MUST**): return/recover the
same operation/result.

Same idempotency key + conflicting request (**MUST**): fail closed with an
explicit conflict.

Stale workspace revision (**MUST**): fail with conflict and require client
refresh.

---

## S16-D15 — Durable managed mutation operations

Long-running source mutations **MUST** have durable operation status so browser
refresh or reconnect does not make work disappear.

This is **NOT** a durable job queue.

Rules (**MUST**):

- preserve existing small bounded admission;
- no unbounded queue;
- fail fast when capacity unavailable;
- admitted operation **MAY** continue independently of browser refresh;
- operation status/result is locally persisted;
- process crash **MUST NOT** auto-publish an unfinished candidate;
- process restart **MAY** mark incomplete operations interrupted/failed;
- prior published workspace snapshot remains valid;
- no automatic resume of scientific ingest after crash.

---

## S16-D16 — Product API extension

Existing accepted Slice 15 endpoints remain valid (**MUST**).

Slice 16 **MUST** add a workspace-oriented application API above them.

At minimum design for (**MUST**):

```text
GET/POST    /v1/workspaces
GET/PATCH/DELETE
            /v1/workspaces/{workspace_id}
GET/POST    /v1/workspaces/{workspace_id}/sources
GET/PUT/PATCH/DELETE
            /v1/workspaces/{workspace_id}/sources/{source_id}
GET         /v1/workspaces/{workspace_id}/sources/{source_id}/content
POST        /v1/workspaces/{workspace_id}/query
GET         /v1/operations/{operation_id}
```

Exact DTOs/error additions are frozen before the relevant implementation
subphase starts (**MUST**).

New routes **MUST** call application-layer use cases; they **MUST NOT** build a
second RAG pipeline.

---

## S16-D17 — Query experience

Backend remains **SINGLE-TURN** (**MUST**).

Conversational memory is **DEFERRED**.

UI **MAY** retain a visual/session-local question history for convenience, but
every query is independent and current backend behavior remains `grounded_v1`.

**MUST NOT** send history/memory as hidden query context.

---

## S16-D18 — Citations and evidence

Desktop core layout (**SHOULD**): Sources | Ask | Evidence.

Citation chips **MUST** open exact evidence context.

Evidence surface **SHOULD** expose where available:

- source;
- section;
- page;
- line;
- snapshot provenance.

PDF (**MUST**): minimum requirement is source preview + page navigation to the
cited page. Highlighting exact cited text is desirable where reliable
coordinate/text mapping exists, but **MUST NOT** be fabricated.

Text/Markdown (**SHOULD**): scroll/highlight relevant line/section where
provenance permits.

Current answers **MUST** display Current snapshot status. Historical trace
inspection **MUST** explicitly display Historical snapshot.

`insufficient_evidence` and `model_abstain` are successful safety outcomes
(**MUST**), not generic red application failures.

---

## S16-D19 — Training Mode

Slice 16 **MUST** provide an instructor-oriented Training Mode. Training Mode
is an accepted Slice-16 capability (delivered in implementation phase 16D),
not an optional add-on.

Initial features (**MUST**):

- select/use workspace;
- enter/select reusable training question;
- hide/reveal answer;
- hide/reveal citations;
- hide/reveal source evidence;
- larger presentation-friendly typography;
- optional fullscreen/presentation layout.

**MUST NOT:**

- learner accounts;
- gradebook;
- certification;
- enrollment;
- LMS.

Reusable local training prompts **MAY** be stored per workspace.

---

## S16-D20 — Engineering Evaluation surface

Engineering area (**MUST**) contain:

- Evaluation;
- Architecture.

Evaluation is **READ-ONLY** presentation of accepted artifacts (**MUST**).

**MUST NOT:**

- add `/eval/*` HTTP API solely for UI;
- add a run-benchmark button;
- add tuning controls;
- add k/reranker/mode switches affecting live product query.

Pipeline comparisons **MUST** display accepted/frozen experiment evidence.

---

## S16-D21 — Static evidence manifest

Accepted evaluation/performance evidence **MUST** be transformed by a
deterministic, repository-owned exporter/build step into a presentation-safe
static manifest.

The manifest **MUST** preserve provenance:

- dataset identity;
- suite/run identity;
- executing SHA;
- configuration/model identity;
- machine profile where applicable;
- timestamp/provenance references.

Missing telemetry **MUST** display unavailable/unevaluable, never numeric zero.

---

## S16-D22 — Architecture / Overview presentation

Overview is real product state, not a fake portfolio mode (**MUST**).

Primary overview (**SHOULD**):

- workspace;
- source count;
- system readiness;
- last successful knowledge update;
- local/private status;
- Ask;
- Add Sources;
- Training Mode.

Lower-level portfolio cards **MAY** link to real Evaluation/Architecture
evidence.

Architecture page **MUST** distinguish:

- product architecture;
- snapshot/data architecture;
- deployment architecture.

---

## S16-D23 — Gold canonical semantics

`GoldDataset` v1 remains canonical retrieval-evaluation gold (**MUST**).

Existing relevance semantics remain (**MUST**):

- `0` = irrelevant;
- `1` = supporting evidence;
- `2` = direct evidence.

Human-finalized gold remains authoritative (**MUST**).

Local model prelabels remain advisory/silver (**MUST**).
**MUST NOT** auto-promote model labels to human gold.

---

## S16-D24 — Atomic resumable expert judgments

The human work unit becomes an atomic, resumable judgment rather than a complete
75–100+ candidate case session (**MUST**).

Expert **MUST** be able to choose workloads such as:

- 1;
- 5;
- 10;
- 25;
- complete case;
- until stop.

Partial human review **MUST** persist safely.

Existing rule remains (**MUST**): a case is eligible for final `GoldDataset`
publication only when canonical completion/quality invariants are satisfied.

---

## S16-D25 — Append-only Gold Lab ledger

Introduce local append-only Gold Lab records under `/data` (**MUST**).

Record (**MUST** support):

- `judgment_id`
- `task_id`
- project/campaign identity
- `workspace_id`
- `snapshot_id`
- `chunk_set_id`
- authoring_run_id/case identity where applicable
- query/candidate identity
- semantic contract
- game/presentation id
- absolute relevance or auxiliary preference
- selection policy
- timestamp
- `supersedes_judgment_id` if corrected

Current HumanReview/Silver state is a deterministic projection of latest valid
canonical absolute judgments (**MUST**).

Corrections append; **MUST NOT** erase judgment history.

---

## S16-D26 — Game semantics vs presentation

Separate (**MUST**):

- `semantic_contract`
- from `game_id` / `presentation_id`.

Canonical v1 games (**MUST**):

- **Rapid Fire** — absolute 0/1/2; one candidate at a time;
- **Evidence Sweep** — absolute 0/1/2; spatial/batch interaction;
- **Question Check** — accept/edit/reject proposed question;
- **Chunk Duel** — pairwise auxiliary preference; **MUST NOT** silently become
  canonical absolute gold.

Use neutral semantic icons (**MUST**).
**MUST NOT** use happy/sad emotional faces for relevance because they imply that
one label is morally/better rewarded.

Game variety **MUST** come from genuinely different cognitive/interaction loops,
not cosmetic reskins only.

---

## S16-D27 — Gold game calibration

Before a presentation/game variant can create production-quality canonical gold,
calibrate it against previously adjudicated cases (**MUST**).

Observe at least (**SHOULD**):

- agreement;
- 0/1/2 distribution;
- unsure rate;
- correction rate;
- completion time;
- abandonment.

If a presentation materially biases judgments, repair or disallow it for
canonical gold (**MUST**).

Record `presentation_id` with judgments so UI-induced effects remain measurable
(**MUST**).

---

## S16-D28 — Benchmark Gold vs Improvement Gold

Keep distinct (**MUST**):

- **Benchmark Gold** — frozen/representative selection policy; used for unbiased
  evaluation/claims;
- **Improvement Gold** — may use active/error/uncertainty/disagreement
  selection, hard negatives, retrieval disagreements, regressions,
  source-version changes; used for diagnosis/future improvement.

**MUST NOT** report active-selected Improvement Gold as an unbiased benchmark.

---

## S16-D29 — Gold snapshot binding

Every Gold task **MUST** be pinned to exact:

- `snapshot_id`
- `chunk_set_id`

Source replacement **MUST NOT** migrate historical gold by filename, fuzzy text,
or similarity.

Old labels remain labels for the historical chunk set (**MUST**).

A new workspace/source version requires an explicitly new/updated gold campaign
where appropriate (**MUST**).

---

## S16-D30 — Gold incorporation

Finalized `GoldDataset` (**MUST**):

- remain exportable as canonical `meta.json` + `cases.jsonl`;
- be registered locally;
- be available to existing evaluation tooling;
- can drive Evaluation-page coverage/provenance;
- **MUST NOT** automatically change retrieval defaults;
- **MUST NOT** automatically retrain/rerank/fine-tune/promote production
  behavior.

Any model/retrieval improvement requires a separate governed experiment and
promotion decision (**MUST**).

---

## S16-D31 — Gold Mode vs Training Mode authority

Gold Mode (**MUST**): expert creates truth.

Training Mode (**MUST**): learner consumes expert-validated truth.

Learner interactions **MUST NEVER** become scientific gold automatically.

Gold expert judgment **MUST** be blind to model judgment/retrieval score/rank
before the independent judgment.

After commitment, an optional after-action/source-context view **MAY** expose
authoritative surrounding context and permit an explicitly recorded correction.

---

## S16-D32 — Pedagogical contract

Training experiences **SHOULD** use:

```text
recall
  → commit
  → corrective/source-grounded feedback
  → authoritative source
  → occasional self-explanation
  → application/scenario
  → debrief
```

Use interleaving of topics/task styles where appropriate (**SHOULD**).

Difficulty **SHOULD** come from discriminating meaningful close cases, not
artificial speed pressure.

**MUST NOT:**

- leaderboards;
- speed rewards;
- reward for agreeing with the model.

Personalized spaced repetition/mastery tracking is **DEFERRED** because it
requires persistent learner identity/state.

---

## S16-D33 — Visual pedagogy

Use meaningful source-grounded visuals where available (**SHOULD**):

- actual manual diagrams;
- actual figures;
- relevant source pages;
- incident-command charts;
- relevant source photographs.

Avoid decorative cognitive-load additions (**MUST NOT**):

- random fire photographs;
- animated flames;
- flashing sirens;
- irrelevant GIFs;
- unrelated imagery.

Scenario text that introduces procedural facts **MUST** be source-grounded or
captain-approved before being treated as authoritative training content.

Finalized gold **MAY** deterministically generate safe evidence-selection
training:

- grade 2 → direct evidence;
- grade 1 → supporting evidence;
- hard grade 0 → plausible distractors.

---

## S16-D34 — Gold Contribution score

Root Overview **MUST** display persistent transparent Gold contribution metrics.

The append-only Gold Lab ledger (S16-D25) remains the audit source. The
contribution score **MUST** be a deterministic projection over **effective**
completed work, not a raw count of append-only ledger rows.

Initial scoring contract (**MUST**), applied to effective unique completed
identities:

| Points | Effective completed contribution |
| --- | --- |
| 1 | one currently effective canonical absolute 0/1/2 expert judgment for a unique task/candidate |
| 5 | one Question Check completed (once per stable completed identity) |
| 10 | one complete evidence map/case completed (once per stable completed identity) |
| 15 | one Gold case finalized (once per stable completed identity) |
| 5 | one designated Hard Call resolved (once per stable completed identity) |

Projection rules (**MUST**):

- an idempotent retry **MUST NOT** award duplicate points;
- superseding/correcting a judgment via `supersedes_judgment_id` **MUST NOT**
  produce additional judgment points merely because a second ledger record
  exists;
- only the currently effective canonical judgment for a unique task/candidate
  contributes the judgment point;
- reopening/revising work **MUST NOT** duplicate a completion bonus unless a
  future accepted scoring-version contract explicitly says otherwise.

Score is a derived engagement metric, not scientific truth (**MUST**).

Scoring presentation **MUST** record a scoring contract/version identifier so
future scoring changes do not silently rewrite historical semantics.

Also show raw counters (**MUST**), derived from the same effective-state
projection (not inflated by superseded/retried ledger events):

- expert judgments;
- questions reviewed;
- cases completed;
- Gold finalized;
- campaign/coverage progress.

**MUST NOT:**

- leaderboard;
- speed bonus;
- model-agreement bonus;
- inflate score from raw append-event count.

---

## S16-D35 — Explicit deferrals / non-goals

Deferred beyond Slice 16 (**MUST NOT** implement in Slice 16):

- authentication / authorization / multi-user tenancy;
- LMS / course enrollment / gradebook / certification;
- conversational memory / multi-turn RAG;
- permanent secure purge / GC;
- personalized spaced repetition / mastery model;
- live product pipeline selector;
- client scientific knobs;
- automatic training/promotion from new gold;
- distributed queues;
- multi-worker / shared-state redesign;
- cloud source upload;
- arbitrary external annotation SaaS.

---

## Decision index

| ID | Title |
| --- | --- |
| S16-D01 | Product objectives |
| S16-D02 | Audience |
| S16-D03 | Architectural boundary |
| S16-D04 | Production topology |
| S16-D05 | Frontend technology |
| S16-D06 | Visual system / accessibility |
| S16-D07 | Workspace / Notebook model |
| S16-D08 | Corpus mapping |
| S16-D09 | Source identity and version lineage |
| S16-D10 | Local raw-source vault |
| S16-D11 | CRUD projection onto immutable snapshots |
| S16-D12 | Supersession isolation |
| S16-D13 | Removal and purge |
| S16-D14 | Idempotency and optimistic concurrency |
| S16-D15 | Durable managed mutation operations |
| S16-D16 | Product API extension |
| S16-D17 | Query experience |
| S16-D18 | Citations and evidence |
| S16-D19 | Training Mode |
| S16-D20 | Engineering Evaluation surface |
| S16-D21 | Static evidence manifest |
| S16-D22 | Architecture / Overview presentation |
| S16-D23 | Gold canonical semantics |
| S16-D24 | Atomic resumable expert judgments |
| S16-D25 | Append-only Gold Lab ledger |
| S16-D26 | Game semantics vs presentation |
| S16-D27 | Gold game calibration |
| S16-D28 | Benchmark Gold vs Improvement Gold |
| S16-D29 | Gold snapshot binding |
| S16-D30 | Gold incorporation |
| S16-D31 | Gold Mode vs Training Mode authority |
| S16-D32 | Pedagogical contract |
| S16-D33 | Visual pedagogy |
| S16-D34 | Gold Contribution score |
| S16-D35 | Explicit deferrals / non-goals |

---

## Authorization note

```text
SLICE 16 DESIGN AUTHORITY: ACCEPTED / LOCKED
AUTHORITY SHA: e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
SLICE 16 IMPLEMENTATION PLAN: ACCEPTED
16A: COMPLETE / ACCEPTED
ACCEPTED SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
16B: COMPLETE / ACCEPTED
ACCEPTED SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16C: COMPLETE / ACCEPTED
ACCEPTED SHA: 936e41446eb1e3697f6b7d245659831f19cf0613
AMENDMENT A1: ACCEPTED / LOCKED
  5060e2aeb4825f265072a1f870c3c963eace3b30
AMENDMENT A2: ACCEPTED / LOCKED / SEALED
  dce3456e519cb6c96570e20f5af800d00cafb5a7
  docs/slice16_amendment_a2_conversational_grounding.md
  A2 CLOSEOUT: f0bdf78d0ae6a79737055d324b22fc35e1e501f5
16D-A: COMPLETE / ACCEPTED / SEALED
ACCEPTED SHA: 4f8962f2893ab433e6ea269ad54e46f67771ca70
OBSERVED 16D-B1 CANDIDATE:
  6b6524001f063a628505f572e7ca13d954a38260
  PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
B1 FOUNDATION REMEDIATION:
  ACCEPTED / SEALED
  ACCEPTED IMPLEMENTATION: c68cc3f8f16a2588ba093886f3e48e1c7037f83f
  VERIFIED CLOSEOUT: b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90
  INDEPENDENT CLOSEOUT REVIEW: PASSED
16D-B2: COMPLETE / ACCEPTED / SEALED
  ACCEPTED IMPLEMENTATION: baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149
  INDEPENDENT REVIEW: PASSED
  HUMAN ACCEPTANCE: ACCEPTED
  REWORK 1: COMPLETE
16D-B3: COMPLETE / ACCEPTED / SEALED
        ACCEPTED IMPLEMENTATION: 9c178ffb033cde41849379fc914f321697ff8691
        INDEPENDENT REVIEW: PASSED
        HUMAN ACCEPTANCE: ACCEPTED
        REWORK 1: COMPLETE
        REWORK 2: COMPLETE
        REWORK 3: COMPLETE
        REWORK 3A: COMPLETE
        AUTHORIZED BASELINE: 28aad06f89e6d00a0b81b51f9c2de38fed06cb22
        A3: ACCEPTED / LOCKED / SEALED
        A3 MATERIALIZATION: da1082d95630c12eaf0ce1a3b8d005aaa60d2f73
        EVIDENCE: docs/slice16d_b3_conversational_workspace.md
        A3 DOC: docs/slice16_amendment_a3_full_viewport_workspace.md
16D-C: COMPLETE / ACCEPTED / SEALED
  EVIDENCE: docs/slice16d_c_training_mode.md
AMENDMENT A4: ACCEPTED / LOCKED / SEALED
  A4 MATERIALIZATION: d12f6322ef13915002b49dcc8f1211052a66dcc5
  A4 DOC: docs/slice16_amendment_a4_workspace_portability_shell.md
16E–16H: NOT AUTHORIZED
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
```

Design acceptance/lock does **not** by itself authorize later phases. **16A**,
**16B**, **16C**, **16D-A**, and **16D-B2** were separately authorized and
are **COMPLETE / ACCEPTED**. Amendment A1 is **ACCEPTED / LOCKED** at
`5060e2aeb4825f265072a1f870c3c963eace3b30`. Amendment A2 is **ACCEPTED /
LOCKED / SEALED** at `dce3456e519cb6c96570e20f5af800d00cafb5a7` (closeout
`f0bdf78d0ae6a79737055d324b22fc35e1e501f5`) and did **not** by itself
authorize B2/B3/C implementation. B1 foundation remediation is **ACCEPTED /
SEALED** (implementation `c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified
closeout `b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`). Legacy B1 product UX
remains **PRODUCT ACCEPTANCE WITHHELD**. **16D-B2** is **COMPLETE /
ACCEPTED / SEALED** at `baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`.
**16D-B3** is **COMPLETE / ACCEPTED / SEALED** at `9c178ffb033cde41849379fc914f321697ff8691` (A3
**ACCEPTED / LOCKED / SEALED** at `da1082d95630c12eaf0ce1a3b8d005aaa60d2f73`). Amendment A4 is
**ACCEPTED / LOCKED / SEALED**. **16D-C** is **COMPLETE / ACCEPTED / SEALED** at
`0381e0461f68c5fc09e7be2c7699d434e8b8a9cb` (closeout
`docs/slice16d_c_a4_closeout.md`).
**16E–16H** remain **NOT AUTHORIZED**. Slice 16 overall is **not** complete.
