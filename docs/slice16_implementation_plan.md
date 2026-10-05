# Slice 16 — Implementation plan candidate

```text
STATUS: PLAN CANDIDATE
DESIGN AUTHORITY CANDIDATE: docs/slice16_design_authority.md
HUMAN ACCEPTANCE: PENDING
IMPLEMENTATION: NOT AUTHORIZED
BASELINE: c72215186524c9937de789adb1cf2056be13ea23
```

This plan decomposes Slice 16 into sequential phase gates. Coding still requires
explicit per-phase implementation authorization after design acceptance.

Authority candidate: [`docs/slice16_design_authority.md`](slice16_design_authority.md)
(S16-D01 … S16-D35).

```text
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
```

---

## Phase order

Use sequential phase gates unless explicitly redesigned:

```text
16A → 16B → 16C → 16D → 16E → 16F → 16G → 16H
```

Do not close Slice 16 automatically after 16H. Independent review and explicit
human acceptance remain required.

---

## 16A — Workspace contracts & persistence foundation

### Scope

- workspace/source identities;
- metadata/revisions;
- raw-source vault;
- operation/idempotency records;
- tombstone models;
- application use-case boundaries;
- error taxonomy extensions;
- **NO UI**.

### Must not

- mutate scientific pipeline semantics;
- bypass `offline_rag.app`;
- auto-publish unfinished candidates.

### Depends on

- accepted Slice 15 product/API surface;
- accepted Slice 16 design authority (when locked).

### Acceptance focus

- durable workspace/source/revision models;
- empty workspace validity (`current_snapshot_id = null`);
- vault privacy under `/data`;
- idempotency/revision record shapes without HTTP yet.

---

## 16B — Workspace/source lifecycle API

### Scope

- workspace CRUD;
- source CRUD;
- source replace;
- full-snapshot projection;
- idempotency;
- ETag/revision concurrency;
- managed mutation operations;
- operation status;
- workspace query adapter;
- source content delivery.

### Critical acceptance

- `manual_b_v05` with `OLD_MARKER` → replace `manual_b_v06` with `NEW_MARKER`
  → current N+1 retrieval/context/citations/answer contain no `OLD_MARKER`
  (S16-D12);
- crash/interruption: unfinished candidate never becomes current (S16-D15);
- stale `If-Match` / conflicting idempotency keys fail closed (S16-D14).

### Must not

- build a second RAG pipeline;
- introduce `/eval/*`;
- auto-resume scientific ingest after crash.

---

## 16C — React shell, design system & source-management UI

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

## 16D — Ask, Evidence & Training Mode

### Scope

- single-turn Ask;
- Sources | Ask | Evidence desktop layout;
- responsive drawers;
- citation chips;
- source preview;
- Current/Historical snapshot visibility;
- abstention presentation as successful safety outcomes;
- session-local visual history only;
- training presentation mode;
- saved prompts;
- hide/reveal answer/evidence.

### Must not

- conversational memory;
- send history as hidden query context;
- fabricate PDF text highlights without reliable mapping;
- LMS / accounts / grading.

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
- Gold Contribution score derivation.

### Must preserve

- existing `GoldDataset` v1;
- Silver→Gold boundary;
- human-finalized absolute relevance as canonical;
- exact `snapshot_id` / `chunk_set_id` binding.

### Must not

- auto-promote model labels to gold;
- migrate historical gold by filename/fuzzy text;
- automatically change retrieval defaults from new gold.

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
- final Slice-16 integration harness.

### Must not

- self-accept Slice 16;
- authorize Slice 17 / Slice 18 / M7 closeout;
- claim globally green unrelated suites.

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
PLAN CANDIDATE: PRESENT
IMPLEMENTATION: NOT AUTHORIZED
16A+: NOT AUTHORIZED
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
```
