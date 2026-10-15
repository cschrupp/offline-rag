# Slice 16K — Beta ingestion readiness design

**Authority:** `S16-K-BETA-INGESTION-READINESS-DESIGN-OPEN-AUTH-001` — AUTHORIZED
**Exact design base:** `3a7d8ff2c442c5d4cd10c0c21637ebc4c52b65fa`
**Branch:** `design/16k-beta-ingestion-readiness`
**Status:** DESIGN OPEN / IMPLEMENTATION NOT AUTHORIZED
**Parent governance:** Slice 16 — COMPLETE / HUMAN ACCEPTED / CANONICAL

### Post-closeout activation statement

**16K is a post-closeout beta-readiness successor activated by first-user
workload evidence.** Opening 16K design does **not** reopen, revoke, qualify,
or invalidate the accepted Slice-16 closeout. The Human-accepted closeout
inventory conclusion that 16K was **DEFERRED / NOT REQUIRED / NOT AUTHORIZED**
for Slice-16 closeout remains correct historical provenance
(`docs/slice16_closeout_inventory.md` I-11) and must not be rewritten.

This design document alone does **not** authorize implementation, capacity
limit changes, timeout changes, OCR, FP16/FlashAttention, benchmarks, Slice 17
implementation, Slice 18, 9G, or M7 closeout.

---

## 1. Observed beta ingestion incident (authoritative)

### 1.1 Incident identity

| Field | Value |
|---|---|
| Workspace | `ws_fdd77b77611448eb93cdc239d2610281` |
| Operation | `wop_eac9e1a596fc4b63a394cb2d1f4ea592` (`source_add`) |
| UI symptom | Add sources → Interrupted · Finalizing semantic search index |
| Durable status | `interrupted` (`progress.step = materializing_dense_index`) |
| Server exception | `AppError: Request deadline exceeded` (`ErrorCode.REQUEST_TIMEOUT`) |
| Wall clock | ~73.5 minutes (`2026-10-15T04:44:00Z` → `2026-10-15T05:57:30Z`) |
| Configured ingest deadline | `api.ingest_deadline_seconds = 1800` (30 minutes) |

### 1.2 Root causes (confirmed)

1. **Deadline overrun on a lengthy dense stage.** Replace-ingest completed
   parse/chunk quickly, then dense-indexed **1296** child chunks
   (`denseindex_e29c7015…`, model `Qwen/Qwen3-Embedding-0.6B`). Cooperative
   checkpoints allow a single stage to run past the wall deadline; the next
   checkpoint (`pre_lexical`) raised `REQUEST_TIMEOUT`.
2. **UI stage lag / last-progress framing.** The last published progress step
   was `materializing_dense_index` (“Finalizing semantic search index”), even
   though dense indexing had completed and the abort occurred at the
   pre-lexical gate.
3. **Durable failure semantics.** Publication recovery terminalized the
   operation as `interrupted` with `recovery_note = recovered_A` and
   `error: null`, obscuring the timeout cause in the operator-facing record
   (API log retained the traceback; the op JSON did not).

### 1.3 First-beta corpus evidence

Candidate set under investigation (not published):

- Five inputs totaling ~3.6 MiB in the candidate spool (four PDFs + one large
  text), producing **1296** dense child vectors.
- Workspace tip remained at revision 4 with four active sources — the add did
  **not** publish.
- OCR is **out of scope** for 16K acceptance; beta corpus selection excludes
  OCR-required or OCR-dominated materials from the acceptance corpus.

---

## 2. Problem statement

Slice 16 accepted the **current admitted envelope**. First-user / beta
workloads that stay inside file-count and byte caps can still exceed the
ingest wall deadline during dense embedding, fail with opaque interrupt UX,
and leave operators without a truthful worklist, queue, or throughput picture.

16K designs the readiness tranche that makes managed ingestion correct,
observable, capacity-honest, and beta-corpus-accepted — then hands regression
coverage to Slice 17 — without reopening Slice 16.

---

## 3. Phase decomposition

Implementation remains gated; each phase needs a later explicit authority.

### 16K-A — Managed-ingestion correctness

- Preserve replace-ingest safety, leases, journals, and publication atomicity.
- Ensure `REQUEST_TIMEOUT` / cancel / shutdown map to durable terminal states
  with safe, machine-readable error codes (not silent `interrupted` /
  `error: null` when a typed AppError is available).
- Define whether an already-completed dense candidate may continue to lexical /
  publish under an explicit post-deadline policy, or must fail closed and
  retry as a new admission (design default: **fail closed + retry**; no silent
  continue past deadline without a later authorized policy).

### 16K-B — Ingestion observability

- Stage-accurate progress: ingest / chunk / dense (embed + materialize) /
  lexical / publish.
- Persist last progress and terminal error on the managed operation record.
- Operator-visible distinction among failed / interrupted / cancelled /
  succeeded.

### 16K-C — Workload / capacity model

- Relate admitted file count, total bytes, estimated chunks, and dense wall
  time to deadline and concurrency knobs.
- Produce an evidence-backed model for beta (not a silent limit raise).
- Keep current defaults as the baseline; any limit or deadline change requires
  separate implementation authority after design freeze/acceptance.

### 16K-D — Dense / CUDA profiling and optimization

- Profile embedding throughput, device selection, batching, and materialize
  cost on the beta corpus class.
- Optimization candidates (batch size, device path, optional acceleration) are
  design-tracked only; FP16 / FlashAttention / scientific config mutation are
  **not authorized** by this design-open authority.

### 16K-E — Ingestion worklist / progress / metrics UX

Operator surface for preparing and watching a managed source-add.

**Pre-submit (mutable worklist):**

- Mutable document worklist before admission.
- Append more documents.
- Remove individual documents before submission.
- Clear all.
- No claim of server-side durability for pre-submit staging beyond existing
  upload/spool rules until HTTP 202 admits the operation.

**Post-admit (durable; immutable membership in this tranche):**

- Durable admitted worklist after 202.
- Current document **or** truthful active-document set (whichever the
  implementation can report without lying).
- Completed / total / remaining document counts.
- Clickable remaining count exposing the queue.
- Per-document state.
- Generated vs reused embedding metrics.
- Throughput, elapsed time, and ETA.
- Expandable technical details.
- **No** per-item mutation/removal after admission in this tranche.

### 16K-F — Real beta-corpus acceptance

- Accept against a declared first-beta corpus (OCR-excluded).
- Pass criteria: publish succeeds within the authorized deadline/capacity
  model; progress and terminal states are truthful; worklist UX meets 16K-E.

### 16K-G — Slice-17 regression handoff

- Freeze the regression cases / fixtures / assertions 16K needs Slice 17 to
  police.
- Does **not** open Slice 17 design or implementation.

---

## 4. Design decisions (Q1–Q14)

| ID | Topic | Disposition (design-open) |
|---|---|---|
| Q1 | Activation trigger | **PROPOSED:** First-user / beta workload evidence (timeout interrupt on admitted envelope) activates 16K as post-closeout successor; Slice 16 closeout remains canonical. |
| Q2 | Relationship to closeout inventory I-11 | **PROPOSED:** Keep I-11 historical (deferred for closeout). Live tip moves to DESIGN OPEN without rewriting the inventory artifact. |
| Q3 | Fail-closed vs continue-after-deadline | **PROPOSED:** Fail closed at cooperative checkpoints when deadline expired; retry via new admission. No silent continue-to-publish in this design. |
| Q4 | Durable timeout semantics | **PROPOSED:** Typed `REQUEST_TIMEOUT` must persist on the managed op as `failed` (or equivalent terminal with error payload), not be overwritten by empty `interrupted` / `recovered_A` when AppError is available. |
| Q5 | Progress truthfulness | **PROPOSED:** Progress step must not claim a later stage than the last durable checkpoint; terminal reason must dominate the interrupt banner. |
| Q6 | OCR | **PROPOSED:** Excluded from 16K acceptance corpus and non-scope for this tranche. |
| Q7 | Source deduplication behavior | **PROPOSED:** Unchanged from accepted Slice-16 behavior; not redesigned in 16K. |
| Q8 | Incremental indexing | **PROPOSED:** Out of scope; replace-ingest model retained. |
| Q9 | Distributed / background queue redesign | **PROPOSED:** Out of scope; keep single-admit managed op model. |
| Q10 | Capacity / deadline changes | **PROPOSED:** Model first (16K-C); numeric raises only under later implementation authority after evidence. |
| Q11 | Dense acceleration (FP16 / FlashAttention) | **PROPOSED:** Design-tracked under 16K-D only; not authorized by design-open. |
| Q12 | Pre-submit worklist mutability (16K-E) | **ACCEPTED FOR DESIGN:** append / remove-one / clear-all before submit. |
| Q13 | Post-admit worklist immutability (16K-E) | **ACCEPTED FOR DESIGN:** durable after 202; no per-item mutation/removal in this tranche. |
| Q14 | Metrics surface (16K-E) | **ACCEPTED FOR DESIGN:** counts + clickable remaining queue + per-doc state + generated/reused embeddings + throughput/elapsed/ETA + expandable technical details. |

Q12–Q14 are frozen as design requirements for the 16K-E surface. Q1–Q11 remain
**PROPOSED** pending independent design review / Human design acceptance.

---

## 5. Acceptance boundaries

16K design acceptance (later freeze/HA) means the document is sufficient to
authorize phased implementation. It does **not** mean:

- Slice 16 is incomplete or reopened;
- capacity/deadline numbers are live;
- UI/product code may land;
- Slice 17 / 18 / 9G / M7 are opened.

16K implementation acceptance (later) will require phase-gated IR/HA and the
16K-F beta-corpus proof.

---

## 6. Explicit non-scope

Under this design-open authority and for the 16K design envelope unless a later
authority says otherwise:

- Python / product code changes
- React / TypeScript / UI code changes
- Configuration changes (including `ingest_deadline_seconds` live mutation)
- New capacity limits going live
- Timeout behavior changes going live
- FP16 / FlashAttention / scientific `base.yaml` mutation
- Benchmark execution as a design-open deliverable
- OCR
- Source deduplication behavior changes
- Incremental indexing
- Distributed / background queue redesign
- Slice 17 implementation
- Slice 18
- 9G
- M7 closeout
- Edits to accepted/sealed Slice-16 artifacts (including
  `docs/slice16_closeout_inventory.md`)

---

## 7. Evidence references

- API traceback: local API process log for
  `GET /v1/operations/wop_eac9e1a596fc4b63a394cb2d1f4ea592`
- Durable op:
  `data/workspaces/ws_fdd77b77611448eb93cdc239d2610281/operations/by_id/wop_eac9e1a596fc4b63a394cb2d1f4ea592.json`
- Dense manifest:
  `data/index-manifests/denseindex_e29c701572d7a0d4d46a9800a0a9104e69c8cd1468b73d01c4484ef41561b706.json`
  (`expected_child_count` / `indexed_child_count` = 1296)
- Deadline default: `api.ingest_deadline_seconds = 1800`
  (`src/offline_rag/config/models.py`)
- Checkpoint raise site: `OperationHandle.checkpoint` →
  `REQUEST_TIMEOUT` / `ingest_deadline_exceeded`
  (`src/offline_rag/app/operations.py`)
- UI label map: `materializing_dense_index` →
  “Finalizing semantic search index”
  (`ui/src/features/operations/progressTelemetry.ts`)

---

## 8. Governance footer

```text
Authority: S16-K-BETA-INGESTION-READINESS-DESIGN-OPEN-AUTH-001 — AUTHORIZED
Exact design base: 3a7d8ff2c442c5d4cd10c0c21637ebc4c52b65fa
16K: DESIGN OPEN / IMPLEMENTATION NOT AUTHORIZED
Slice 16: COMPLETE / HUMAN ACCEPTED / CANONICAL
Slice 17: NOT AUTHORIZED
Slice 18: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
Does NOT authorize implementation
Does NOT reopen Slice 16 closeout
Outstanding separate operation: promote 3a7d8ff… onto origin/main (still at e21b3e6…)
```
