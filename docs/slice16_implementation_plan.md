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
AMENDMENT A1: ACCEPTED / LOCKED
  5060e2aeb4825f265072a1f870c3c963eace3b30
  docs/slice16_amendment_a1_seneca_product_ux.md
AMENDMENT A2: ACCEPTED / LOCKED / SEALED
  dce3456e519cb6c96570e20f5af800d00cafb5a7
  docs/slice16_amendment_a2_conversational_grounding.md
  A2 GOVERNANCE CLOSEOUT: f0bdf78d0ae6a79737055d324b22fc35e1e501f5
16D-A: COMPLETE / ACCEPTED / SEALED
IMPLEMENTATION: 4f8962f2893ab433e6ea269ad54e46f67771ca70
LAST SEALED IMPLEMENTATION BASELINE:
  a952a75bc07191b213a5113eee53cb967fef8326
OBSERVED 16D-B1 CANDIDATE:
  6b6524001f063a628505f572e7ca13d954a38260
  PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
16D-B1 FOUNDATION REMEDIATION:
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
16D-C: REWORK 2 IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING
        EVIDENCE: docs/slice16d_c_training_mode.md
AMENDMENT A4: HUMAN-APPROVED / LOCKED / IMPLEMENTED CANDIDATE / ACCEPTANCE PENDING
        A4 MATERIALIZATION: d12f6322ef13915002b49dcc8f1211052a66dcc5
        A4 DOC: docs/slice16_amendment_a4_workspace_portability_shell.md
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

Amendment A1 (**ACCEPTED / LOCKED** supplemental design authority):
[`docs/slice16_amendment_a1_seneca_product_ux.md`](slice16_amendment_a1_seneca_product_ux.md)
at `5060e2aeb4825f265072a1f870c3c963eace3b30`.

Amendment A2 (**ACCEPTED / LOCKED / SEALED** at
`dce3456e519cb6c96570e20f5af800d00cafb5a7`; governance closeout
`f0bdf78d0ae6a79737055d324b22fc35e1e501f5`):
[`docs/slice16_amendment_a2_conversational_grounding.md`](slice16_amendment_a2_conversational_grounding.md).
A2 authoritatively supersedes only its enumerated clauses and revises the Ask
path into **16D-B1 (observed) / 16D-B2 / 16D-B3** then **16D-C**. A2 acceptance
did **not** by itself authorize B2/B3/C. B1 foundation upload remediation is
**ACCEPTED / SEALED** (implementation
`c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified closeout
`b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`); that acceptance does **not**
grant product acceptance to the legacy B1 Ask/Evidence UX. **16D-B2** is
**COMPLETE / ACCEPTED / SEALED** at
`baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`. **16D-B3** is **COMPLETE / ACCEPTED / SEALED** at
`9c178ffb033cde41849379fc914f321697ff8691` (A3 **ACCEPTED / LOCKED / SEALED** at `da1082d95630c12eaf0ce1a3b8d005aaa60d2f73`; see
[`docs/slice16d_b3_conversational_workspace.md`](slice16d_b3_conversational_workspace.md)).
**16D-C** is **REWORK 2 IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING** (see
[`docs/slice16d_c_training_mode.md`](slice16d_c_training_mode.md)).

16A evidence: [`docs/slice16a_workspace_foundation.md`](slice16a_workspace_foundation.md)

16B evidence: [`docs/slice16b_workspace_lifecycle_api.md`](slice16b_workspace_lifecycle_api.md)

16C evidence: [`docs/slice16c_react_shell_source_ui.md`](slice16c_react_shell_source_ui.md)

16D-A evidence: [`docs/slice16d_a_seneca_product_foundation_query_scope.md`](slice16d_a_seneca_product_foundation_query_scope.md)

16D-B1 foundation remediation evidence:
[`docs/slice16d_b1_upload_foundation_remediation.md`](slice16d_b1_upload_foundation_remediation.md)

16D-B2 evidence:
[`docs/slice16d_b2_grounded_answer_v2.md`](slice16d_b2_grounded_answer_v2.md)

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
16D-A [COMPLETE / ACCEPTED / SEALED]
 ↓
16D-B1 [OBSERVED CANDIDATE / PRODUCT ACCEPTANCE WITHHELD]
 ↓
B1 foundation remediation [ACCEPTED / SEALED @ c68cc3f8… / closeout b5fa1e85…]
 ↓
16D-B2 [COMPLETE / ACCEPTED / SEALED @ baa16eba…]   ← Grounded Answer V2
 ↓
16D-B3 [COMPLETE / ACCEPTED / SEALED @ 9c178ffb… / A3 da1082d9…]
        ← Conversational workspace
 ↓
16D-C [REWORK 2 IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING]
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
AMENDMENT A1: ACCEPTED / LOCKED
5060e2aeb4825f265072a1f870c3c963eace3b30
AMENDMENT A2: ACCEPTED / LOCKED / SEALED
dce3456e519cb6c96570e20f5af800d00cafb5a7
docs/slice16_amendment_a2_conversational_grounding.md
A2 CLOSEOUT: f0bdf78d0ae6a79737055d324b22fc35e1e501f5
```

Under accepted A2, Ask/Evidence decomposes into **B1 / B2 / B3** (see A2-D24).
**16D-A** is **COMPLETE / ACCEPTED / SEALED**. Observed B1 candidate
`6b652400…` remains **PRODUCT ACCEPTANCE WITHHELD / NOT SEALED**. B1
foundation upload remediation is **ACCEPTED / SEALED** (implementation
`c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified closeout
`b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`). **16D-B2** is
**COMPLETE / ACCEPTED / SEALED** at
`baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`. **16D-B3** is **COMPLETE / ACCEPTED / SEALED** at
`9c178ffb033cde41849379fc914f321697ff8691` (A3 **ACCEPTED / LOCKED / SEALED** at `da1082d95630c12eaf0ce1a3b8d005aaa60d2f73`; see
[`docs/slice16d_b3_conversational_workspace.md`](slice16d_b3_conversational_workspace.md)).
**16D-C** is **REWORK 2 IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING**.

Do not close Slice 16 automatically after 16H. Independent review and explicit
human acceptance of the implemented slice remain required. **16A**, **16B**,
**16C**, **16D-A**, and **16D-B2** are **COMPLETE / ACCEPTED**; legacy B1
product UX acceptance remains **WITHHELD**; B1 foundation remediation is
**ACCEPTED / SEALED**; **16D-B3** is **COMPLETE / ACCEPTED / SEALED**; **16D-C** is
**IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING**; **16E–16H** remain **NOT
AUTHORIZED**. Slice 16 overall is **not** complete.

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
STATUS: COMPLETE / ACCEPTED
IMPLEMENTATION: 4f8962f2893ab433e6ea269ad54e46f67771ca70
AMENDMENT A1: ACCEPTED / LOCKED @ 5060e2aeb4825f265072a1f870c3c963eace3b30
AUTHORIZED BASELINE: 185d3e3d2bd472ffaddf72cfddc49c7e38a3a146
EVIDENCE: docs/slice16d_a_seneca_product_foundation_query_scope.md
```

Authoritative under accepted Amendment A1. **16D-A** is **COMPLETE / ACCEPTED**
at `4f8962f2893ab433e6ea269ad54e46f67771ca70`. **16D-B / 16D-C** remain
**NOT AUTHORIZED / NOT STARTED**.

### Accepted scope

- Seneca brand application; provisional stoa favicon/logo; canonical title;
- compact source rail; source `⋮` CRUD; de-emphasized metadata management;
- compact operation completion UX; capacity presentation;
- explicit internal YAML capacity defaults; read-only capabilities endpoint;
- Settings cog/page; generation runtime configuration API/persistence;
- product-managed local/LAN approval (not Internet under strict-offline);
- operator/environment locks that cannot be bypassed from the UI;
- endpoint/model probe against prospective policy (no activate/persist on probe);
- ACTIVE vs PENDING configuration; restart-required semantics;
- source-scoped query DTO; server-side source→document binding;
- dense + lexical pre-ranking scope enforcement; scoped-query provenance.

### Must not

- implement full Ask/Evidence UX merely because the query substrate exists;
- weaken generation allow-list security or approve public Internet endpoints
  under strict-offline merely because Settings accepted typed input;
- bypass operator/environment locks with product-managed approvals;
- activate or persist generator configuration from Test Connection alone;
- report PENDING generator settings via capabilities as if ACTIVE;
- hot-swap live generation clients without restart-required semantics;
- treat source checkboxes as workspace membership mutations.

---

## 16D-B — Ask & Evidence Workspace (decomposed under accepted A2)

```text
AMENDMENT A1: ACCEPTED / LOCKED @ 5060e2aeb4825f265072a1f870c3c963eace3b30
AMENDMENT A2: ACCEPTED / LOCKED / SEALED @ dce3456e519cb6c96570e20f5af800d00cafb5a7
A2 CLOSEOUT: f0bdf78d0ae6a79737055d324b22fc35e1e501f5
PREREQUISITE 16D-A: COMPLETE / ACCEPTED / SEALED @ 4f8962f2893ab433e6ea269ad54e46f67771ca70
LAST SEALED IMPLEMENTATION BASELINE:
  a952a75bc07191b213a5113eee53cb967fef8326
```

Historical A1 text treated 16D-B as a single Ask/Evidence gate (single-turn Ask,
citation chips, session-local history). Accepted A2 authoritatively replaces
that with B1/B2/B3 below. Do **not** implement B2/B3/C without separate
authorization.

### 16D-B1 — Ask/Evidence Engineering Foundation

```text
STATUS: OBSERVED IMPLEMENTATION CANDIDATE
PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
OBSERVED SHA: 6b6524001f063a628505f572e7ca13d954a38260
HISTORICAL DISPOSITION: useful engineering substrate;
  legacy product UX acceptance withheld
EVIDENCE (historical): docs/slice16d_b_ask_evidence_workspace.md
```

Useful substrate preserved (not release-accepted Ask UX):

- source selection;
- scoped query;
- exact-version evidence;
- Current / Historical semantics;
- PDF / text evidence preview;
- session presentation primitives.

Known A2 product findings remain assigned downstream (not fixed by upload
remediation):

- F7 desktop shell too narrow → B3
- F8 dynamic content spill/containment → B3
- F9 composer lifecycle → B3
- F10 single-turn interaction too primitive → B3

### 16D-B1 FOUNDATION REMEDIATION

```text
STATUS: ACCEPTED / SEALED
ACCEPTED IMPLEMENTATION:
  c68cc3f8f16a2588ba093886f3e48e1c7037f83f
VERIFIED CLOSEOUT:
  b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90
INDEPENDENT CLOSEOUT REVIEW: PASSED
IMPLEMENTATION BASELINE:
  6b6524001f063a628505f572e7ca13d954a38260
EVIDENCE: docs/slice16d_b1_upload_foundation_remediation.md
FINDINGS CLOSED: B1-U1 / B1-U2 / B1-U3 / B1-U4 / B1-R1
```

Accepted upload-foundation scope only (does **not** grant legacy B1 product
UX acceptance):

- browser multi-file source-upload reliability;
- pre-202 AbortController / cancellation;
- honest transport-error classification;
- transport-ambiguity-safe idempotent retry;
- R1 canceled-upload fresh-intent duplicate hazard fix.

### 16D-B2 — Grounded Answer V2 & Claim Citations

```text
STATUS: COMPLETE / ACCEPTED / SEALED
ACCEPTED IMPLEMENTATION: baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149
INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
REWORK 1: COMPLETE
EVIDENCE: docs/slice16d_b2_grounded_answer_v2.md
```

Delivered (A2-D12–D18 / B2 portion of A2-D24): response-local E1/E2 handles;
Grounded Answer V2 blocks; excerpts; claim citation cards; structured
abstention. **No** conversational orchestration in B2.

### 16D-B3 — Conversational Workspace

```text
STATUS: COMPLETE / ACCEPTED / SEALED

ACCEPTED IMPLEMENTATION:
9c178ffb033cde41849379fc914f321697ff8691

INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
REWORK 1: COMPLETE
REWORK 2: COMPLETE
REWORK 3: COMPLETE
REWORK 3A: COMPLETE

AUTHORIZED BASELINE:
28aad06f89e6d00a0b81b51f9c2de38fed06cb22

REWORK 3 BASELINE:
528e7dbb10fdde24ea1ea7db71a4e35c2a9222e1

AMENDMENT A3:
ACCEPTED / LOCKED / SEALED
MATERIALIZATION: da1082d95630c12eaf0ce1a3b8d005aaa60d2f73

EVIDENCE:
docs/slice16d_b3_conversational_workspace.md

16D-C:
NOT AUTHORIZED / NOT STARTED
```

**Accepted / sealed scope:** B3 on
`implementation/16d-b3-conversational-workspace` at `9c178ffb033cde41849379fc914f321697ff8691` provides
conversation/turn orchestration; bounded contextual resolver; fresh retrieval
through the shared scientific core; New conversation / composer lifecycle;
per-turn provenance; Current/Historical behavior; Grounded Answer V2 claim
citations; full-viewport desktop workspace under Amendment A3; independently
collapsible desktop Sources/Evidence rails; hard overflow containment; and
responsive narrow drawers. Owns F7/F8/F9/F10 where applicable.

**Historical prerequisites (already satisfied — not active gates):** B3
activation required verified B2 closeout and branching from the authorized B2
closeout / B3 baseline. Those prerequisites were met; B3 is no longer “not yet
started” or awaiting B2 activation.

### Must not (all B* gates)

- factual conversational memory / prior answers as evidence;
- second RAG pipeline;
- fabricate PDF text highlights without reliable mapping;
- treat B1 foundation remediation acceptance as legacy Ask UX acceptance;
- treat B3 acceptance as automatic C acceptance
  (**16D-C** is an implementation candidate pending independent human acceptance).

---

## 16D-C — Training Mode

```text
STATUS: IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING
EVIDENCE: docs/slice16d_c_training_mode.md
AMENDMENT A1: ACCEPTED / LOCKED @ 5060e2aeb4825f265072a1f870c3c963eace3b30
AMENDMENT A2: ACCEPTED / LOCKED / SEALED @ dce3456e519cb6c96570e20f5af800d00cafb5a7
AUTHORIZED BASELINE: 396aa329e6c0413eb69aacd39067a70d9b478b72
BRANCH: implementation/16d-c-training-mode
```

### Accepted implementation scope (candidate)

- **required** instructor-oriented Training Mode (S16-D19 — not optional);
- saved prompts seed / start conversation turns (A2-D25);
- hide/reveal answer / citations / evidence on grounded assistant turns;
- larger presentation-friendly typography;
- optional fullscreen/presentation layout;
- frontend-only pedagogical layer over accepted B3 conversation path.

### Must not

- LMS / accounts / grading;
- treat Training Mode as deferred/optional Slice-16 scope;
- second RAG path / training-specific scientific pipeline.

---

## Historical note — former monolithic 16D gate

Prior plan text treated Ask, Evidence, and Training Mode as a single **16D**
gate. Accepted Amendment A1 subdivided that gate into **16D-A / 16D-B / 16D-C**
for implementation governance. Phase execution remains separately gated.

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
AMENDMENT A1: ACCEPTED / LOCKED
  5060e2aeb4825f265072a1f870c3c963eace3b30
AMENDMENT A2: ACCEPTED / LOCKED / SEALED
  dce3456e519cb6c96570e20f5af800d00cafb5a7
  A2 CLOSEOUT: f0bdf78d0ae6a79737055d324b22fc35e1e501f5
16D-A: COMPLETE / ACCEPTED / SEALED
IMPLEMENTATION: 4f8962f2893ab433e6ea269ad54e46f67771ca70
OBSERVED 16D-B1 CANDIDATE:
  6b6524001f063a628505f572e7ca13d954a38260
  PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
16D-B1 FOUNDATION REMEDIATION:
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
16D-C: REWORK 2 IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING
AMENDMENT A4: HUMAN-APPROVED / LOCKED / IMPLEMENTED CANDIDATE / ACCEPTANCE PENDING
16E–16H: NOT AUTHORIZED
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
```

Plan acceptance alone did **not** authorize execution. 16A, 16B, 16C,
16D-A, and 16D-B2 were separately authorized and are now **COMPLETE /
ACCEPTED**. Amendment A1 is **ACCEPTED / LOCKED** at
`5060e2aeb4825f265072a1f870c3c963eace3b30`. Amendment A2 is **ACCEPTED /
LOCKED / SEALED** at `dce3456e519cb6c96570e20f5af800d00cafb5a7` (closeout
`f0bdf78d0ae6a79737055d324b22fc35e1e501f5`). **16D-A** is **COMPLETE /
ACCEPTED / SEALED** at `4f8962f2893ab433e6ea269ad54e46f67771ca70`. Observed
16D-B1 candidate `6b652400…` remains **PRODUCT ACCEPTANCE WITHHELD**. B1
foundation remediation is **ACCEPTED / SEALED** (implementation
`c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified closeout
`b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`). **16D-B2** is **COMPLETE /
ACCEPTED / SEALED** at `baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`.
**16D-B3** is **COMPLETE / ACCEPTED / SEALED** at `9c178ffb033cde41849379fc914f321697ff8691` (A3
**ACCEPTED / LOCKED / SEALED** at `da1082d95630c12eaf0ce1a3b8d005aaa60d2f73`). **16D-C** is
**IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING**. **16E–16H**
remain **NOT AUTHORIZED**. Slice 16 overall is **not** complete.
