# Slice 16 — Portfolio Demo UI

```text
STATUS: PRE-DESIGN / ROADMAP FRAME
DESIGN AUTHORITY: NONE
DESIGN: NOT OPEN
IMPLEMENTATION: NOT AUTHORIZED
```

This document is a **roadmap frame only**. It does **not** lock Slice 16
architecture, technology choices, or implementation authorization.

**Prerequisite dependency (governance order):**

```text
14  Performance evidence          COMPLETE / ACCEPTED
15  Product/API/container         COMPLETE / ACCEPTED
15H Integration acceptance /
    Slice-15 closeout             COMPLETE / ACCEPTED
                                  at 1c1d94eada502523d44ec8e9c9a6e23b1f863d49
16  Portfolio Demo UI             PLANNED / DESIGN NOT OPEN
                                  IMPLEMENTATION NOT AUTHORIZED
```

Slice **15H** closed Slice 15 and validated the API/container product boundary
(**15H was not the UI phase**). The closeout prerequisite for opening a Slice 16
design interview is now satisfied. This document still does **not** authorize
Slice 16 design or implementation until an explicit separate authorization is
issued.

Historical open criteria (now met):

1. Slice 15H completed independent integration acceptance;
2. Slice 15 is COMPLETE / ACCEPTED (including closeout);
3. supported API contracts are stable;
4. integration findings relevant to UI consumption are resolved or
   explicitly accepted (see
   [`docs/slice15h_integration_acceptance.md`](slice15h_integration_acceptance.md)).

---

## 1. Purpose

Expose the engineering value of OfflineRAG through a browser UI built on the
accepted product/API layer without duplicating backend retrieval or generation
logic in the frontend.

The UI must remain an **adapter/client** of the product/backend surface.

---

## 2. Inherited architectural boundary

```text
Browser UI
   ↓
supported UI/backend interface
   ↓
src/offline_rag/app/
   ↓
domain + infrastructure
```

**Forbidden:**

- UI → Qdrant directly
- UI → retrievers directly
- UI → generator directly
- UI-owned RAG pipeline
- UI-owned scientific algorithms
- UI bypassing app/product semantics

---

## 3. Locked product query boundary (Slice 15)

Until explicitly redesigned under a future architecture decision, the locked
product query remains:

```json
{
  "corpus": "manuals",
  "question": "..."
}
```

with server-owned `product_mode_id = grounded_v1`.

Slice 15 locked:

- one canonical grounded product query;
- no client algorithm/mode selector;
- no scientific knobs in `POST /v1/query`;
- no client snapshot pinning;
- no recovery-mode selector.

### Diagnostic / comparison surfaces — DESIGN REQUIRED

Older roadmap text mentioned a “pipeline switcher” (dense / BM25 / hybrid /
hybrid+reranker / recovery). That wording **predates** the locked Slice-15
product API and is **not** an authorized product feature.

The portfolio UI may eventually visualize or compare retrieval/evaluation
variants, but Slice 16 design must determine whether this is:

1. visualization of already-recorded evaluation artifacts;
2. a separate developer/diagnostic interface;
3. CLI-generated artifacts rendered by the UI;
4. another explicitly designed non-product surface.

It must **not** silently expand `POST /v1/query` with algorithm selection or
other scientific knobs.

---

## 4. Candidate capability areas (NOT locked requirements)

### 16A — Query experience

Potential scope:

- corpus selection;
- question input;
- answer;
- successful abstention state;
- citations;
- source/document preview;
- page/section provenance;
- trace identifier where useful.

Must use supported backend contracts.

### 16B — Evidence / retrieval inspector

Potential scope:

- final cited evidence;
- document/chunk provenance;
- retrieval diagnostics available through a future approved diagnostic surface;
- ranking/evidence visualization.

Do **not** claim that current `/v1/query` exposes dense/lexical candidate lists,
RRF internals, reranker scores, or raw scientific `QueryTrace`. Those are not
part of the current Slice-15 product response. A later Slice-16 design decision
must determine how any inspector obtains such information safely.

### 16C — Corpus/document experience

Potential scope:

- current published corpus inventory;
- documents;
- document provenance;
- ingest flow;
- ingest terminal result;
- corpus readiness/error presentation.

Existing Slice-15 endpoints may support much of this.

### 16D — Evaluation / performance presentation

Potential scope:

- render existing evaluation artifacts;
- benchmark summaries;
- latency/resource evidence;
- abstention results;
- security/adversarial evidence.

Prefer read-only presentation of accepted artifacts. Do **not** create
`/eval/*` HTTP endpoints merely because a UI wants them (Slice 15 D12:
CLI-first evaluation). Any future server-side evaluation interface requires
explicit design authority.

### 16E — Portfolio polish

Potential scope:

- system architecture explanation;
- transparent local/offline topology;
- model/runtime status;
- known limitations;
- reproducibility links.

---

## 5. Open design questions

Technology selection is a Slice-16 design decision. Do **not** lock
React/Vue/Svelte/HTMX/etc. here.

Candidate questions:

- SPA vs server-rendered/static frontend;
- same-origin serving vs separate development frontend;
- TypeScript vs minimal JS;
- component library policy;
- visualization library;
- whether production static assets are packaged inside the OfflineRAG image;
- development hot-reload workflow;
- offline dependency/build requirements.

The Slice-15 optional static-serving substrate was deliberately not implemented,
so Slice 16 design must decide the frontend delivery model explicitly.

---

## 6. Explicit non-goals (this pre-design frame)

- No UI implementation in this document’s lifetime until Slice 16 is authorized.
- No product API expansion to support algorithm selection.
- No scientific pipeline duplication in the browser.
- No Milestone 7 closeout via UI alone.
- No portfolio claim promotion beyond accepted evidence.

---

## 7. Prerequisites for opening design

Before a formal Slice-16 design interview/authority document:

1. ~~15H COMPLETE / ACCEPTED~~ **DONE** (`1c1d94e…`;
   [`slice15h_integration_acceptance.md`](slice15h_integration_acceptance.md));
2. ~~Slice 15 COMPLETE / ACCEPTED including closeout~~ **DONE**;
3. stable supported product contracts for UI consumption — **met** by accepted
   Slice 15 surface;
4. explicit design authorization citing this roadmap frame and Slice-15
   architecture authority — **still required** (not granted by this document).
