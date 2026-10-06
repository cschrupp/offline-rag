# Slice 16 — Portfolio Demo UI

```text
STATUS: HISTORICAL PRE-DESIGN FRAME
DESIGN INTERVIEW: COMPLETE
DESIGN AUTHORITY: ACCEPTED / LOCKED
  docs/slice16_design_authority.md
AUTHORITY SHA: e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
IMPLEMENTATION PLAN: ACCEPTED
  docs/slice16_implementation_plan.md
16A: COMPLETE / ACCEPTED
ACCEPTED SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
16B: COMPLETE / ACCEPTED
ACCEPTED SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16C: COMPLETE / ACCEPTED
ACCEPTED SHA: 936e41446eb1e3697f6b7d245659831f19cf0613
AMENDMENT A1: ACCEPTED / LOCKED
  5060e2aeb4825f265072a1f870c3c963eace3b30
  docs/slice16_amendment_a1_seneca_product_ux.md
16D-A / 16D-B / 16D-C: NOT AUTHORIZED / NOT STARTED
```

This document is the **historical pre-design / roadmap frame** for Slice 16.
It is **not** design authority. Normative decisions live in
[`docs/slice16_design_authority.md`](slice16_design_authority.md)
(S16-D01 … S16-D35), accepted and locked at AUTHORITY SHA
`e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`. Amendment A1
([`docs/slice16_amendment_a1_seneca_product_ux.md`](slice16_amendment_a1_seneca_product_ux.md))
is **ACCEPTED / LOCKED** supplemental design authority at
`5060e2aeb4825f265072a1f870c3c963eace3b30` (product **Seneca — Grounded
knowledge workspace**). This historical frame remains contextual only.
**16A** is **COMPLETE / ACCEPTED**
at `e73959be508541a1c50d4919606aaf3157a5fa8a`. **16B** is **COMPLETE / ACCEPTED**
at `eb8baefc6e3eaf7df33668c85fbbfef22364bb0e`. **16C** is **COMPLETE / ACCEPTED**
at `936e41446eb1e3697f6b7d245659831f19cf0613`. **16D-A / 16D-B / 16D-C** remain
**NOT AUTHORIZED / NOT STARTED**. Portfolio UI overall remains **not complete**.

**Prerequisite dependency (governance order):**

```text
14  Performance evidence          COMPLETE / ACCEPTED
15  Product/API/container         COMPLETE / ACCEPTED
15H Integration acceptance /
    Slice-15 closeout             COMPLETE / ACCEPTED
                                  at 1c1d94eada502523d44ec8e9c9a6e23b1f863d49
16  Portfolio Demo UI             DESIGN INTERVIEW COMPLETE
                                  DESIGN AUTHORITY ACCEPTED / LOCKED
                                  AUTHORITY SHA e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
                                  IMPLEMENTATION PLAN ACCEPTED
                                  16A COMPLETE / ACCEPTED
                                  ACCEPTED SHA e73959be508541a1c50d4919606aaf3157a5fa8a
                                  16B COMPLETE / ACCEPTED
                                  ACCEPTED SHA eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
                                  16C COMPLETE / ACCEPTED
                                  ACCEPTED SHA 936e41446eb1e3697f6b7d245659831f19cf0613
                                  AMENDMENT A1 ACCEPTED / LOCKED
                                    5060e2aeb4825f265072a1f870c3c963eace3b30
                                  16D-A / 16D-B / 16D-C NOT AUTHORIZED
                                  Slice 16 overall NOT COMPLETE
```

Slice **15H** closed Slice 15 and validated the API/container product boundary
(**15H was not the UI phase**). The Slice 16 design interview is **COMPLETE**.
Design authority is **ACCEPTED / LOCKED**. **16A**, **16B**, and **16C** are
**COMPLETE / ACCEPTED**. Amendment A1 is **ACCEPTED / LOCKED**. This frame still
does **not** authorize **16D-A / 16D-B / 16D-C**, Slice 17, Slice 18, or
Milestone 7 closeout.

Historical open criteria (met before the design interview):

1. Slice 15H completed independent integration acceptance;
2. Slice 15 is COMPLETE / ACCEPTED (including closeout);
3. supported API contracts are stable;
4. integration findings relevant to UI consumption are resolved or
   explicitly accepted (see
   [`docs/slice15h_integration_acceptance.md`](slice15h_integration_acceptance.md)).

---

## 1. Purpose (historical frame)

Expose the engineering value of OfflineRAG through a browser UI built on the
accepted product/API layer without duplicating backend retrieval or generation
logic in the frontend.

The UI must remain an **adapter/client** of the product/backend surface.

Normative product objectives, audience, and presentation honesty rules are now
candidates in S16-D01 / S16-D02 of the design authority candidate.

---

## 2. Inherited architectural boundary (historical frame)

```text
Browser UI
   ↓
supported UI/backend interface
   ↓
src/offline_rag/app/
   ↓
domain + infrastructure
```

**Forbidden (unchanged; formalized as S16-D03):**

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
  "corpus": "<logical_corpus_name>",
  "question": "<single-turn question>"
}
```

with server-owned `product_mode_id = grounded_v1`.

Slice 16 workspace query adapters (S16-D08 / S16-D16 / S16-D17) **MUST**
preserve that grounded single-turn semantics; conversational memory remains
deferred.

---

## 4. Capability areas (superseded by authority candidate)

Earlier pre-design capability sketches (query experience, evidence inspector,
corpus/document UX, evaluation presentation, portfolio polish) are retained
here only as historical context. Binding decisions are S16-D07–S16-D34 in
[`docs/slice16_design_authority.md`](slice16_design_authority.md).

---

## 5. Frontend delivery (historical note)

The Slice-15 optional static-serving substrate was deliberately not implemented.
S16-D04 / S16-D05 now candidate-formalize same-origin production static delivery
from the OfflineRAG application container, with optional Vite hot-reload in
development only.

---

## 6. Explicit non-goals (historical frame)

- No UI implementation until Slice 16 is implementation-authorized.
- No product API expansion to support algorithm selection.
- No scientific pipeline duplication in the browser.
- No Milestone 7 closeout via UI alone.
- No portfolio claim promotion beyond accepted evidence.
- No Slice 17 / Slice 18 authorization by this document.

See also S16-D35 deferred list in the locked design authority.

---

## 7. Design interview / acceptance status

```text
DESIGN INTERVIEW: COMPLETE
DESIGN AUTHORITY: ACCEPTED / LOCKED
  docs/slice16_design_authority.md
AUTHORITY SHA: e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
IMPLEMENTATION PLAN: ACCEPTED
  docs/slice16_implementation_plan.md
16A: COMPLETE / ACCEPTED
ACCEPTED SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
16B: COMPLETE / ACCEPTED
ACCEPTED SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16C: COMPLETE / ACCEPTED
ACCEPTED SHA: 936e41446eb1e3697f6b7d245659831f19cf0613
AMENDMENT A1: ACCEPTED / LOCKED
  5060e2aeb4825f265072a1f870c3c963eace3b30
16D-A / 16D-B / 16D-C: NOT AUTHORIZED
16E–16H: NOT AUTHORIZED
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
```

1. ~~15H COMPLETE / ACCEPTED~~ **DONE**
2. ~~Slice 15 COMPLETE / ACCEPTED including closeout~~ **DONE**
3. ~~stable supported product contracts~~ **DONE**
4. ~~design interview~~ **DONE**
5. ~~human acceptance of design authority~~ **DONE** (locked at
   `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`)
6. ~~16A / 16B / 16C implementation acceptance~~ **DONE**
7. ~~Amendment A1 human acceptance~~ **DONE** (locked at
   `5060e2aeb4825f265072a1f870c3c963eace3b30`)
8. explicit 16D-A / 16D-B / 16D-C implementation authorization — **NOT GRANTED**
