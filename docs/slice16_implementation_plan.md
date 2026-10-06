# Slice 16 — Implementation plan

```text
STATUS: ACCEPTED IMPLEMENTATION PLAN
DESIGN AUTHORITY: ACCEPTED / LOCKED
AUTHORITY SHA: e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
16A: COMPLETE / ACCEPTED
ACCEPTED SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
16B: COMPLETE / ACCEPTED
ACCEPTED SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16C: COMPLETE / ACCEPTED
ACCEPTED SHA: 936e41446eb1e3697f6b7d245659831f19cf0613
AMENDMENT A1: DESIGN CANDIDATE / HUMAN ACCEPTANCE PENDING
  docs/slice16_amendment_a1_seneca_product_ux.md
16D-A / 16D-B / 16D-C: NOT AUTHORIZED
16E–16H: NOT AUTHORIZED
BASELINE: c72215186524c9937de789adb1cf2056be13ea23
```

This plan decomposes Slice 16 into sequential phase gates. Plan acceptance does
**NOT** authorize execution. Coding still requires explicit per-phase
implementation authorization. 16A, 16B, and 16C have been separately authorized,
implemented, reviewed, and **ACCEPTED**. Later phases remain gated.

Locked design authority: [`docs/slice16_design_authority.md`](slice16_design_authority.md)
(S16-D01 … S16-D35) at AUTHORITY SHA
`e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`.

Amendment A1 design candidate (**HUMAN ACCEPTANCE PENDING**; not yet locked
implementation authority):
[`docs/slice16_amendment_a1_seneca_product_ux.md`](slice16_amendment_a1_seneca_product_ux.md).

16A evidence: [`docs/slice16a_workspace_foundation.md`](slice16a_workspace_foundation.md)

16B evidence: [`docs/slice16b_workspace_lifecycle_api.md`](slice16b_workspace_lifecycle_api.md)

16C evidence: [`docs/slice16c_react_shell_source_ui.md`](slice16c_react_shell_source_ui.md)

```text
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
```

---

## Phase order

Use sequential phase gates unless explicitly redesigned:

```text
16A [ACCEPTED]
 ↓
16B [ACCEPTED]
 ↓
16C [ACCEPTED / SEALED]
 ↓
16D-A [NOT AUTHORIZED]
 ↓
16D-B [NOT AUTHORIZED]
 ↓
16D-C [NOT AUTHORIZED]
 ↓
16E
 ↓
16F
 ↓
16G
 ↓
16H
```

```text
AMENDMENT A1 DESIGN CANDIDATE
HUMAN ACCEPTANCE PENDING
```

The revised 16D-A / 16D-B / 16D-C decomposition above is proposed by Amendment
A1 and is **not** locked implementation authority until A1 is accepted.

Do not close Slice 16 automatically after 16H. Independent review and explicit
human acceptance of the implemented slice remain required. **16A**, **16B**, and
**16C** are **COMPLETE / ACCEPTED**; **16D-A / 16D-B / 16D-C** and **16E–16H**
remain **NOT AUTHORIZED**. Slice 16 overall is **not** complete.

---

## 16A — Workspace contracts & persistence foundation

```text
STATUS: COMPLETE / ACCEPTED
ACCEPTED SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
Evidence: docs/slice16a_workspace_foundation.md
```

### Scope

- workspace/source identities;
- metadata/revisions (presentation metadata vs scientific publication);
- empty-workspace / depublication state contract (S16-D07 / S16-D13);
- raw-source vault;
- operation/idempotency records;
- tombstone models;
- application use-case boundaries;
- error taxonomy extensions (including empty/not-ready query);
- **NO UI**.

### Must not

- mutate scientific pipeline semantics;
- bypass `offline_rag.app`;
- auto-publish unfinished candidates;
- fabricate empty scientific snapshots;
- treat display-only metadata edits as snapshot-creating mutations.

### Depends on

- accepted Slice 15 product/API surface;
- locked Slice 16 design authority
  (`e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`).

### Acceptance focus

- durable workspace/source/revision models;
- empty workspace validity (`current_snapshot_id = null`, `sources = []`);
- depublication / retirement storage semantics preserving historical artifacts
  while clearing active current publication;
- distinct workspace revision advancement for display-only metadata vs
  content/membership publication;
- vault privacy under `/data`;
- idempotency/revision record shapes without HTTP yet;
- scoring contract/version identifier may be deferred until 16F unless naturally
  part of shared contract scaffolding.

---

## 16B — Workspace/source lifecycle API

```text
STATUS: COMPLETE / ACCEPTED
ACCEPTED SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
AUTHORIZED BASELINE: 155983fec59a3ae6434286276bd34dcfdaaf8968
ACCEPTED 16A SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
16C: COMPLETE / ACCEPTED @ 936e41446eb1e3697f6b7d245659831f19cf0613
16D+: NOT AUTHORIZED
Evidence: docs/slice16b_workspace_lifecycle_api.md
```

### Inherited contracts from accepted 16A

These are inherited implementation contracts (not new design scope). Accepted 16B
MUST:

- use `WorkspaceMutationLease` → `CorpusMutationLease` lock order (never
  reverse);
- integrate outstanding EMPTY-journal recovery into startup/readiness before
  workspace mutation/query surfaces become ready;
- never call retirement/restore publication helpers without holding the corpus
  mutation lease;
- compose `ManagedOperationStore` with already-held workspace leases where
  orchestration requires one atomic mutation section.

### Scope

- workspace CRUD;
- source CRUD;
- source replace;
- full-snapshot projection for non-empty membership mutations;
- final-source removal EMPTY / depublication transition (S16-D13);
- display-only metadata PATCH without snapshot rebuild (S16-D11);
- idempotency;
- ETag/revision concurrency;
- managed mutation operations;
- operation status;
- workspace query adapter (fail closed when EMPTY);
- source content delivery.

### Critical acceptance

1. Normal add / remove / replace (non-empty result) publishes a new immutable
   snapshot (S16-D11).
2. `manual_b_v05` with `OLD_MARKER` → replace `manual_b_v06` with `NEW_MARKER`
   → current N+1 retrieval/context/citations/answer contain no `OLD_MARKER`
   (S16-D12).
3. Final-source removal: one-source workspace → remove final source → workspace
   EMPTY (`sources = []`, `current_snapshot_id = null`) → old source not
   queryable through current workspace/product path; no empty Slice-15 ingest;
   crash leaves either prior one-source+publication or committed EMPTY with no
   active publication (S16-D13).
4. Display-only rename: workspace revision advances; `snapshot_id` remains
   unchanged (S16-D11).
5. Byte-identical replacement creates a new source version iff the operation is
   accepted as a new version; `document_id` changes iff content identity
   changes; idempotent retry does not create another source version (S16-D09).
6. Crash/interruption of unfinished candidate never becomes current (S16-D15).
7. Stale `If-Match` / conflicting idempotency keys fail closed (S16-D14).

### Must not

- build a second RAG pipeline;
- introduce `/eval/*`;
- auto-resume scientific ingest after crash;
- fabricate empty scientific snapshots;
- rebuild corpus on display-only metadata edits.

---

## 16C — React shell, design system & source-management UI

```text
STATUS: COMPLETE / ACCEPTED
ACCEPTED SHA: 936e41446eb1e3697f6b7d245659831f19cf0613
INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
AUTHORIZED BASELINE: a0a8a3f9a38807f40676a9a249cd7c7b186c09cb
ACCEPTED 16B SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16D+: NOT AUTHORIZED
Evidence: docs/slice16c_react_shell_source_ui.md
```

### Scope

- React/TS/Vite shell;
- same-origin production static delivery;
- routing;
- TanStack Query;
- design tokens (S16-D06);
- responsive nav;
- Overview;
- workspace library;
- source management;
- operation progress UX;
- offline-bundled assets;
- WCAG foundations.

### Must not

- fake data in production surfaces;
- runtime CDN dependency under strict offline;
- Redux by default;
- scientific controls in source UI.

---

## 16D-A — Seneca Product Foundation & Query-Scope Substrate

```text
STATUS: NOT AUTHORIZED / NOT STARTED
AMENDMENT A1: DESIGN CANDIDATE / HUMAN ACCEPTANCE PENDING
```

Proposed by Amendment A1. Not locked until A1 is accepted. Not authorized for
implementation by this plan update alone.

### Future scope (candidate)

- Seneca brand application; provisional stoa favicon/logo; canonical title;
- compact source rail; source `⋮` CRUD; de-emphasized metadata management;
- compact operation completion UX; capacity presentation;
- explicit internal YAML capacity defaults; read-only capabilities endpoint;
- Settings cog/page; generation runtime configuration API/persistence;
- endpoint/model probe; restart-required semantics;
- source-scoped query DTO; server-side source→document binding;
- dense + lexical pre-ranking scope enforcement; scoped-query provenance.

### Must not

- implement full Ask/Evidence UX merely because the query substrate exists;
- weaken generation allow-list security;
- hot-swap live generation clients without restart-required semantics;
- treat source checkboxes as workspace membership mutations.

---

## 16D-B — Ask & Evidence Workspace

```text
STATUS: NOT AUTHORIZED / NOT STARTED
AMENDMENT A1: DESIGN CANDIDATE / HUMAN ACCEPTANCE PENDING
```

### Future scope (candidate)

- Sources | Ask | Evidence desktop layout;
- responsive drawers;
- source-selection checkboxes;
- single-turn Ask;
- answer rendering;
- citation chips;
- evidence panel;
- source preview;
- Current/Historical snapshot visibility;
- abstention presentation as successful safety outcomes;
- session-local visual history only.

### Must not

- conversational memory;
- send history as hidden query context;
- fabricate PDF text highlights without reliable mapping.

---

## 16D-C — Training Mode

```text
STATUS: NOT AUTHORIZED / NOT STARTED
AMENDMENT A1: DESIGN CANDIDATE / HUMAN ACCEPTANCE PENDING
```

### Future scope (candidate)

- **required** instructor-oriented Training Mode (S16-D19 — not optional);
- saved prompts;
- hide/reveal answer/evidence;
- larger presentation-friendly typography;
- optional fullscreen/presentation layout.

### Must not

- LMS / accounts / grading;
- treat Training Mode as deferred/optional Slice-16 scope.

---

## Historical note — former monolithic 16D gate

Prior plan text treated Ask, Evidence, and Training Mode as a single **16D**
gate. Amendment A1 proposes subdividing that gate into **16D-A / 16D-B / 16D-C**
for implementation governance. Until A1 is accepted, that subdivision remains a
design candidate only.

---

## 16E — Engineering Evidence

### Scope

- deterministic accepted-evidence exporter;
- static UI evidence manifest;
- Evaluation page;
- pipeline comparisons from accepted artifacts;
- performance evidence;
- safety/robustness evidence;
- Architecture page;
- provenance drill-down.

### Must not

- `/eval/*` runtime API;
- scientific controls / run-benchmark buttons;
- numeric zero for missing telemetry;
- claim publication-grade results beyond existing artifact governance.

---

## 16F — Gold Lab data plane

### Scope

- Gold projects/campaigns;
- append-only judgment ledger;
- atomic resumable tasks;
- projection into existing Silver/HumanReview;
- benchmark vs improvement project type;
- selection policy provenance;
- snapshot/chunk-set binding;
- corrections/supersession;
- canonical export/registration;
- Gold Contribution score as effective-state projection with scoring
  contract/version identifier (S16-D34) — not raw append-event count.

### Must preserve

- existing `GoldDataset` v1;
- Silver→Gold boundary;
- human-finalized absolute relevance as canonical;
- exact `snapshot_id` / `chunk_set_id` binding;
- append-only ledger as audit source while score uses effective unique
  completed contributions.

### Must not

- auto-promote model labels to gold;
- migrate historical gold by filename/fuzzy text;
- automatically change retrieval defaults from new gold;
- inflate contribution score from idempotent retries or superseding
  corrections.

---

## 16G — Gold Lab games & pedagogical training compiler

### Scope

- Rapid Fire;
- Evidence Sweep;
- Question Check;
- Chunk Duel;
- calibration mode;
- `presentation_id` tracking;
- workload chooser;
- Gold contribution dashboard;
- source-grounded pedagogy;
- gold-derived evidence drills;
- scenario/debrief presentation.

### Must

- keep Chunk Duel auxiliary (not silent absolute gold);
- keep learner actions from creating gold;
- calibrate presentation variants before production-quality gold use.

### Must not

- happy/sad emotional relevance faces;
- leaderboards / speed rewards / model-agreement rewards;
- decorative cognitive-load fire imagery.

---

## 16H — Integration / accessibility / portfolio acceptance

### Scope

- cross-surface integration;
- responsive acceptance;
- WCAG 2.2 AA audit;
- keyboard-only flows;
- source supersession integration;
- operation recovery UX;
- strict-offline/static-asset checks;
- container/static delivery verification;
- portfolio evidence consistency;
- no fake data;
- final Slice-16 integration harness;
- **empirical source/corpus capacity validation** on a declared local reference
  machine (Amendment A1 candidate; e.g. 32 / 64 / 128 sources and increasing
  active-source byte totals). Defaults must not be raised by intuition alone.

### Must not

- self-accept Slice 16;
- authorize Slice 17 / Slice 18 / M7 closeout;
- claim globally green unrelated suites;
- promise NotebookLM-equivalent cloud capacity.

### Exit condition

Evidence candidate + independent review + explicit human acceptance only.

---

## Explicit non-scope (entire Slice 16 plan)

- authentication / multi-tenant product;
- LMS / certification;
- multi-turn conversational RAG;
- permanent secure purge/GC;
- distributed queues / multi-worker redesign;
- issue #1 image-size optimization;
- Slice 17 / Slice 18 / Milestone 7 closeout.

---

## Authorization note

```text
IMPLEMENTATION PLAN: ACCEPTED
DESIGN AUTHORITY: ACCEPTED / LOCKED
AUTHORITY SHA: e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
16A: COMPLETE / ACCEPTED
ACCEPTED SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
16B: COMPLETE / ACCEPTED
ACCEPTED SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16C: COMPLETE / ACCEPTED
ACCEPTED SHA: 936e41446eb1e3697f6b7d245659831f19cf0613
AMENDMENT A1: DESIGN CANDIDATE / HUMAN ACCEPTANCE PENDING
16D-A / 16D-B / 16D-C: NOT AUTHORIZED
16E–16H: NOT AUTHORIZED
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
```

Plan acceptance alone did **not** authorize execution. 16A, 16B, and 16C were
separately authorized and are now **COMPLETE / ACCEPTED**. Amendment A1 is a
**design candidate** with human acceptance pending; the proposed 16D-A/B/C
decomposition is therefore **not** locked implementation authority yet.
**16D-A / 16D-B / 16D-C** and **16E–16H** remain **NOT AUTHORIZED**. Slice 16
overall is **not** complete.
