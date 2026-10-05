# Slice 16 — Portfolio-Grade Knowledge & Training UI — Design Authority Candidate

```text
STATUS: DESIGN AUTHORITY CANDIDATE
DESIGN INTERVIEW: COMPLETE
HUMAN ACCEPTANCE: PENDING
IMPLEMENTATION: NOT AUTHORIZED
BASELINE: c72215186524c9937de789adb1cf2056be13ea23
```

**Authority role:** This document is the Slice 16 **design authority candidate**.
It is **not** accepted, locked, or implementation-authorizing until independent
review and explicit human acceptance.

**Related artifacts:**

- Implementation plan candidate:
  [`docs/slice16_implementation_plan.md`](slice16_implementation_plan.md)
- Historical pre-design frame (contextual only after acceptance):
  [`docs/slice16_portfolio_ui.md`](slice16_portfolio_ui.md)
- Inherited product/API architecture:
  [`docs/slice15_developer_api_packaging.md`](slice15_developer_api_packaging.md)

**Normative language:**

- **MUST / MUST NOT** — binding design requirements if this candidate is
  accepted.
- **SHOULD** — UX / presentation recommendations that implementation ought to
  follow unless a later accepted amendment says otherwise.
- **MAY** — permitted options.
- **DEFERRED** — explicitly out of Slice 16; not authorized here.

This candidate **MUST NOT** weaken accepted Slice 15 decisions. Accepted
historical benchmark/gold artifacts retain their existing governance claims
(development/regression/publication-readiness as already recorded). This
document does **not** claim a globally green test suite.

---

## Gate status

```text
SLICE 16 DESIGN INTERVIEW:       COMPLETE
DESIGN AUTHORITY CANDIDATE:      PRESENT (this document)
DESIGN ACCEPTANCE:               HUMAN REVIEW PENDING
IMPLEMENTATION:                  NOT AUTHORIZED
SLICE 17:                        NOT AUTHORIZED
SLICE 18:                        NOT AUTHORIZED
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

---

## S16-D08 — Corpus mapping

Each active workspace **MUST** map to one server-managed OfflineRAG product
corpus.

Ordinary users **MUST** work with workspace/source identities, not corpus
implementation names.

Workspace query adapters **MUST** ultimately invoke the same canonical
`grounded_v1` product query behavior.

---

## S16-D09 — Source identity and version lineage

Distinguish (**MUST**):

- `source_id` — stable logical source identity inside a workspace;
- `document_id` — content-derived immutable scientific document identity.

Replacing a source **MUST** preserve `source_id` and create a new
`document_id`/version.

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

- add;
- remove;
- replace;
- metadata rename/edit.

Internal mutation model (**MUST**):

```text
desired source set
  → isolated candidate
  → existing ingest/chunk/dense/lexical pipeline
  → validate
  → atomic publication
  → new current immutable snapshot
```

**MUST NOT** incrementally mutate live Qdrant/lexical scientific state merely to
mimic CRUD.

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

"Remove from workspace" (**MUST**):

- logical removal from current/future workspace state followed by new snapshot
  publication;
- historical immutable artifacts **MAY** remain locally.

"Delete workspace" (**MUST**):

- tombstone/remove from active product catalog;
- **MUST NOT** recursively erase all historical scientific state in Slice 16.

Permanent secure purge / reachability-aware garbage collection is **DEFERRED**.

UI **MUST NOT** imply irreversible erasure when only logical removal occurs.

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

Instructor-oriented, simplified presentation mode (**MUST** if Training Mode is
shipped in Slice 16).

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

Initial scoring contract (**MUST**):

| Points | Event |
| --- | --- |
| 1 | one canonical absolute 0/1/2 expert judgment |
| 5 | one Question Check completed |
| 10 | one complete evidence map/case completed |
| 15 | one Gold case finalized |
| 5 | one designated Hard Call resolved |

Score is a derived engagement metric, not scientific truth (**MUST**).

Also show raw counters (**MUST**):

- expert judgments;
- questions reviewed;
- cases completed;
- Gold finalized;
- campaign/coverage progress.

**MUST NOT:**

- leaderboard;
- speed bonus;
- model-agreement bonus.

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
DESIGN AUTHORITY CANDIDATE: PRESENT
HUMAN ACCEPTANCE: PENDING
IMPLEMENTATION: NOT AUTHORIZED
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
```

Independent review and human acceptance are required before any Slice 16
implementation phase (16A+) may be authorized.
