# 16K-D Dual-Backend P2 — Product / API / UI Integration Design

**Design authority:** `S16-K-D-DUAL-BACKEND-P2-PRODUCT-API-UI-INTEGRATION-DESIGN-AUTH-001` — AUTHORIZED  
**Exact design-open parent:** `7563ce0736307dd3bf303289b6d0a25bce79c4f9`  
**Branch:** `design/16k-d-dual-backend-p2-product-api-ui-integration`  
**Status:** DESIGN OPEN / IMPLEMENTATION NOT AUTHORIZED  

**Inherited P1 implementation authority:** `S16-K-D-DUAL-BACKEND-P1-QUALIFIED-RUNTIME-SUBSTRATE-IMPLEMENTATION-AUTH-001`  
**Inherited P1 Human acceptance:** `S16-K-D-DUAL-BACKEND-P1-QUALIFIED-RUNTIME-SUBSTRATE-IMPLEMENTATION-HA-001` — ACCEPTED  
**Exact accepted P1 technical subject:** `fae82b2455cfdd0d1622065904a35895372740b6`  
**P1 HA-record tip (governance only):** `bdecd52891309c2c2e4ddee7d3c74174ad606290`  

**Architecture authority:** dual-backend embedding architecture (Rounds 1–12) — HUMAN ACCEPTED / FROZEN  
**Design posture:** architecture-conformance **integration** design over the accepted substrate — **not** a new architecture exercise.

---

## 1. Purpose

Define exact product/runtime, API, and Seneca UI integration contracts for the accepted dual-backend embedding substrate delivered by P1, without reopening frozen architecture or authorizing implementation.

P2 translates already-accepted architecture into durable integration contracts. Independent acceptance of this design is a prerequisite before any separate P2 **implementation** authority may be opened.

---

## 2. Inherited frozen architectural facts (do not reopen)

The following are accepted and binding for P2 integration design:

1. Closed production profile vocabulary: `cuda_fp16_v1`, `cpu_onnx_fp32_v1`.
2. Exactly one selected embedding execution profile per process.
3. No mid-run backend fallback / no silent profile switching.
4. Shared logical embedding / index / collection identity across accepted profiles (profile/provider/device are not durable identity).
5. Process-owned lazy runtime lifecycle (`UNLOADED` → `LOADING` → `READY`, with terminal failure semantics as frozen).
6. P1 owns artifact trust / representation readiness inspection and the `QualifiedEmbeddingRuntime` substrate (accepted at `fae82b2…`).
7. Phase ownership split remains: **P1** substrate · **P2** product/API/UI integration · **P3** provisioning/acquisition · **P4** later acceptance/promotion.
8. Architecture Round 10 already freezes structural P2 ownership sketches (`ApplicationRuntime` / `ProcessResources.embedder`, Compute Settings projection facts, candidate source surfaces, explicit non-scope). P2 design here **conforms and concretizes**; it does not redesign those facts.

---

## 3. Scope boundary

### 3.1 Allowed under this design authority

- Architecture-conformance integration decisions and contracts
- Interfaces and lifecycle/wiring into existing app runtime
- API configuration and observability contracts
- UI state / UX contracts for compute/device/profile/readiness/failure
- Error / status / readiness / fallback semantics (product-facing)
- Compatibility requirements with existing YAML, CLI, and settings
- Persistence / mutability of user compute preferences
- Acceptance criteria and deterministic test matrix structure
- Exact P2 implementation surface decomposition (files/tasks) — design only
- Explicit exclusions for P3 / P4 / campaigns / main / merge / promotion

### 3.2 Not allowed under this design authority

- Production implementation of any kind
- Provisioning / download / package acquisition logic (P3)
- New scientific execution, parity, screen, or performance campaigns
- Representation qualification changes or new profiles
- P3 / P4 work
- Merge, main promotion, or default promotion
- Reopening P1 science/architecture or rewriting accepted P1 technical subject `fae82b2…`

---

## 4. Frozen constraints for the integration design process

1. Prefer conformance to accepted Round 10 / dual-backend architecture over invention.
2. Ask and freeze remaining **integration** decisions one at a time; do not invent the full product contract in one pass.
3. Where architecture already decides a fact, record it as **INHERITED / FROZEN** rather than re-deciding it.
4. Distinguishing “eligible to open later” from “authorized now” remains mandatory: this authority opens **design only**.
5. P2 implementation remains **NOT AUTHORIZED** until this design is independently accepted and a separate implementation AUTH is explicitly issued.

---

## 5. Open integration decision ledger

Status key: `OPEN` · `INHERITED/FROZEN` · `FROZEN` · `DEFERRED-TO-P3` · `DEFERRED-TO-P4`

| ID | Decision | Status |
|---|---|---|
| D01 | Product/runtime ownership and where profile resolution occurs | OPEN |
| D02 | Process lifecycle and resource ownership | OPEN |
| D03 | API configuration and observability surface | OPEN |
| D04 | Explicit CPU / CUDA / AUTO user semantics | OPEN |
| D05 | Readiness / error / fallback semantics (product-facing) | OPEN |
| D06 | Workspace / query / ingest interaction with selected embedding profile | OPEN |
| D07 | UI controls and user-visible status | OPEN |
| D08 | Compatibility with existing configuration files and CLI behavior | OPEN |
| D09 | Persistence semantics for user compute preferences | OPEN |
| D10 | Startup vs runtime mutability | OPEN |
| D11 | API schema and backward compatibility | OPEN |
| D12 | Security / offline boundary | OPEN |
| D13 | What P2 may know about installed representations vs what remains P3 | OPEN |
| D14 | Failure / recovery behavior | OPEN |
| D15 | Test strategy and deterministic acceptance matrix | OPEN |
| D16 | Exact P2 implementation surface | OPEN |
| D17 | Explicit exclusions for P3 / P4 / campaigns / main | OPEN |
| D18 | Independent-review gates for design and later implementation | OPEN |

Architecture-level facts listed in §2 are **INHERITED/FROZEN** and are not ledger re-openings.

---

## 6. Acceptance criteria structure (to be completed after decision freeze)

When the ledger above is fully dispositioned, this document must include:

1. Exact conformance claims to inherited architecture / P1 substrate.
2. Exact product/API/UI contracts frozen by D01–D18.
3. Exact non-scope and P3/P4 exclusions.
4. Deterministic acceptance matrix outline for a future P2 implementation authority.
5. Explicit statement that design IR ACCEPT does not authorize implementation.

Terminal design disposition target:

```text
P2 DESIGN COMPLETE / READY FOR INDEPENDENT DESIGN REVIEW
IMPLEMENTATION NOT AUTHORIZED
```

Only after independent design acceptance may a separate P2 implementation authority become eligible to open.

---

## 7. Explicit non-authorization

This document and its design-open commit do **not** authorize:

- P2 implementation
- P3 provisioning
- P4 acceptance / promotion
- campaigns
- main / merge / default promotion

---

## 8. Document history

| Event | Subject / tip | Note |
|---|---|---|
| DESIGN OPEN | parent `7563ce0…` | Authority opened; integration ledger OPEN; implementation NOT AUTHORIZED |
