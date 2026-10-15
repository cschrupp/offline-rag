# Slice 16K — First-User Beta Ingestion Readiness

**Design-open authority:** `S16-K-BETA-INGESTION-READINESS-DESIGN-OPEN-AUTH-001` — AUTHORIZED
**Rework authority:** `S16-K-BETA-INGESTION-READINESS-DESIGN-REWORK-AUTH-001` — AUTHORIZED
**Addresses:** `S16-K-BETA-INGESTION-READINESS-DESIGN-OPEN-IR-001` — REWORK REQUIRED (R1–R5 binding)
**Human acceptance:** `S16-K-BETA-INGESTION-READINESS-DESIGN-HA-001` — ACCEPTED
**HA record authority:** `S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-AUTH-001` — AUTHORIZED
**Exact Human-accepted design subject:** `0839b565cd60958141366048520236a71bf16fd0`
**Exact design-open base:** `3a7d8ff2c442c5d4cd10c0c21637ebc4c52b65fa`
**Exact rework base:** `5c693c531ded432b10cf5f6ac19d558a1f4e9431`
**HA-record IR:** `S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-IR-001` — ACCEPT
**16K-A implementation authority:** `S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-AUTH-001` — AUTHORIZED
**16K-A independent review:** `S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-IR-002` — ACCEPT
**16K-A Human acceptance:** `S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-HA-001` — ACCEPTED
**16K-A HA record:** `S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-AUTH-001` — AUTHORIZED
**Exact Human-accepted 16K-A technical subject:** `1370b99327124045ad96005e829095683842c06f`
**16K-A branch:** `implementation/16k-a-managed-ingestion-correctness`
**16K-A HA-record IR:** `S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-IR-001` — ACCEPT
**16K-B implementation authority:** `S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-AUTH-001` — AUTHORIZED
**Exact 16K-B implementation base:** `39e5e09363193b2315ada9e56cb3e1c14ba9377d`
**16K-B independent review:** `S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-001` — REWORK REQUIRED (R1–R4)
**16K-B rework authority:** `S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-001` — AUTHORIZED
**Exact 16K-B rework base:** `85f01f40080fe485b6ddb7700855aa34280c9c75`
**16K-B independent review:** `S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-002` — REWORK REQUIRED (R3 / R4a / R4b)
**16K-B rework authority:** `S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-002` — AUTHORIZED
**Exact 16K-B rework-002 base / parent:** `533a07c3d1313d08eae5647e4c266d4fa3a439c5`
**16K-B branch:** `implementation/16k-b-ingestion-observability`
**Status:** DESIGN ACCEPTED / FROZEN
**16K-A:** IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED
**16K-B:** IMPLEMENTATION AUTHORIZED / NOT YET ACCEPTED
**16K-C → 16K-G:** NOT YET AUTHORIZED
**Frozen implementation order:** 16K-A → 16K-B → baseline evidence → 16K-C → 16K-D → 16K-E → 16K-F → 16K-G
**Parent governance:** Slice 16 — COMPLETE / HUMAN ACCEPTED / CANONICAL
**Product:** Seneca — Grounded knowledge workspace

### Post-closeout activation statement

**16K is a post-closeout beta-readiness successor activated by first-user
workload evidence.** Opening 16K design does **not** reopen, revoke, qualify,
or invalidate the accepted Slice-16 closeout. The Human-accepted closeout
inventory conclusion that 16K was **DEFERRED / NOT REQUIRED / NOT AUTHORIZED**
for Slice-16 closeout remains correct historical provenance
(`docs/slice16_closeout_inventory.md` I-11) and must not be rewritten.

Human design acceptance freezes this design. **16K-A** managed-ingestion
correctness is **IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN
ACCEPTED** at subject `1370b993…`. **16K-B** ingestion observability is
**IMPLEMENTATION AUTHORIZED / NOT YET ACCEPTED**; IR-001 required R1–R4 rework
from base `85f01f4…` (R1/R2 closed at `533a07c…`); IR-002 required R3/R4a/R4b
rework under REWORK-AUTH-002 from parent `533a07c…`. 16K-C→G, capacity
expansion, CUDA optimization, UI work, OCR, Slice 17/18, 9G, and M7 closeout
remain unauthorized.

---

## 1. Purpose and governance position

Slice 16K is a post-Slice-16 beta-readiness successor activated by first-user
workload evidence. It does not reopen, revise, or invalidate the accepted
Slice-16 closeout. Slice 16 remains **COMPLETE / HUMAN ACCEPTED / CANONICAL**.

The previously deferred 16K item — first-user corpus capacity model + empirical
validation — is now justified by an actual beta corpus and a reproducible
long-running source-add failure. Slice 17 remains a separate Regression CI
slice and is not opened by this design.

Implementation is not authorized by this document. Each implementation tranche
16K-A through 16K-G requires a separate bounded implementation authority,
independent review, and Human acceptance.

---

## 2. Trigger evidence

### 2.1 Managed source-add incident (reproducible performance incident)

| Field | Value |
|---|---|
| Workspace | `ws_fdd77b77611448eb93cdc239d2610281` |
| Operation | `wop_eac9e1a596fc4b63a394cb2d1f4ea592` (`source_add`) |
| Wall clock | ~73.5 minutes |
| Configured `ingest_deadline_seconds` | 1800 |
| Dense result | completed; **1296** child chunks indexed |
| Abort point | `checkpoint("pre_lexical")` |
| Surfaced error | Request deadline exceeded (`REQUEST_TIMEOUT`) |
| Durable status | `interrupted` |
| Durable error | `null` |
| Durable recovery note | `recovered_A` |
| Publication | prior revision retained; requested source not published |

Repository review established two separate correctness defects:

1. Workspace source Add/Replace/Remove already execute as detached **202 Accepted**
   managed operations but are admitted through the synchronous ingest deadline
   policy; and
2. Live publication recovery to A terminalizes the managed operation as
   **INTERRUPTED / recovered_A** before `_fail_operation()` can durably persist
   the known application error as **FAILED**.

The dense stage completed; the overall atomic source mutation did not. Lexical
indexing and publication were still pending when the next cooperative
checkpoint observed the already-expired absolute deadline.

The **~1,296-child** failing operation remains the reproducible performance
incident / cold-workload reproduction target. It is **not** the first-beta
corpus envelope.

### 2.2 First-beta corpus envelope

Supplied inventory (external/private; not committed to the repository):

| Envelope field | Value |
|---|---|
| Supplied files | **45** |
| Raw bytes | ~**1.05 GB** |
| Extractable characters | ~**14.6M** |
| Estimated tokens | ~**3.6M** |
| Estimated children (pre-dedupe, all 45) | ~**10.4k** |
| OCR-only / zero-text scans | **3** known items — **excluded** from beta acceptance |
| Non-OCR stress view (incl. duplicates/alternates) | ~**42** files / ~**10.4k** children |
| Primary deduplicated non-OCR view | ~**39** usable sources / ~**7.5–8k** children |

Baseline chunk settings used for estimates:

- child target: 350 tokens
- child max: 512 tokens
- tokenizer: tiktoken / cl100k_base
- structure-aware parent/child chunking

**Raw bytes are a transport/storage characteristic, not the scientific
workload metric.** Alternate representations (e.g. full-size PDF, compressed
PDF, and extracted TXT — including Lineman PDF/TXT/compressed variants and
image-heavy PDFs) can carry materially similar searchable text while differing
by orders of magnitude in raw bytes.

OCR implementation remains explicitly out of scope for 16K.

---

## 3. Goals

16K MUST:

1. make detached workspace source mutations correct for long-running local
   scientific work;
2. preserve truthful durable terminal causes (**FAILED** versus **INTERRUPTED**);
3. expose enough ingestion telemetry to diagnose long-running operations;
4. replace raw-byte-centric product-capacity assumptions with an empirically
   validated first-user workload model while retaining hard transport/storage
   safety guards;
5. profile and optimize CUDA dense embedding without silently changing
   scientific identity or retrieval behavior;
6. provide a premium, inspectable ingestion worklist UX (current document /
   active-document set, remaining count, queue inspection, pre-submit
   per-file removal);
7. validate the full deduplicated non-OCR beta corpus end to end; and
8. hand deterministic contracts to Slice 17 for regression protection.

---

## 4. Non-goals

16K MUST NOT introduce:

- OCR or scanned-document recognition;
- a distributed queue or multi-worker architecture;
- cloud embedding or cloud parsing;
- a new embedding model solely for speed;
- a new chunking strategy solely for speed;
- automatic semantic duplicate deletion;
- in-flight mutation of an already-admitted Add Sources request;
- incremental indexing (unless later profiling proves full reconstruction material
  and a separate authority opens it);
- 9G authorization;
- Slice 17 implementation;
- Slice 18 implementation;
- M7 closeout;
- publication-grade performance claims before empirical acceptance.

---

## 5. Frozen design questions (Q1–Q14)

| ID | Topic | Frozen disposition |
|---|---|---|
| Q1 | Governance position | 16K is a post-closeout beta-readiness successor. Slice 16 remains COMPLETE / HUMAN ACCEPTED / CANONICAL. Opening 16K does not reopen Slice 16. Inventory I-11 remains historical provenance. |
| Q2 | OCR | OCR-required documents are excluded from beta acceptance. A zero-searchable-text source MUST fail with an actionable bounded reason before expensive indexing; it MUST NOT be silently omitted from an atomic Add Sources mutation. |
| Q3 | Beta corpus views | Two evidence views: **primary** ≈ 39 usable sources / 7.5–8k children; **stress** ≈ 42 sources / ≈ 10.4k children. Source files remain external/private. The 1296-child incident remains a separate reproduction workload. |
| Q4 | Capacity model | Separate **transport/resource safety** from **workspace/search workload** (see §8 / 16K-C). Raw upload bytes are not the primary scientific measure. No final numeric expanded limits frozen until 16K-C/F evidence. Current 32-file / 25-MiB / 100-MiB envelope is baseline under investigation, not the conceptual model. |
| Q5 | Managed-operation lifetime | Detached workspace Add/Replace/Remove MUST NOT inherit the synchronous `/v1/ingest` whole-request absolute deadline. Synchronous `/v1/ingest` deadline remains unchanged unless separately authorized. Total managed-op wall time is **not** itself `REQUEST_TIMEOUT`. A future stall/watchdog policy may be designed separately. |
| Q6 | Cooperative cancellation | Shutdown/cancellation remains cooperative. Long-running dense work SHOULD expose control checkpoints between interruptible units, including embedding batches where feasible. Telemetry callbacks MUST remain non-authoritative and MUST NOT become cancellation mechanisms. |
| Q7 | Durable terminal semantics | Live known application failure after journal recovery MUST terminalize as **FAILED** with safe durable error. Crash/startup recovery of abandoned nonterminal work MAY terminalize as **INTERRUPTED**. Recovery A/B: live failure + recovered A → FAILED + error + `recovered_A`; startup/crash → A → INTERRUPTED / `recovered_A`; recovery to committed B → SUCCEEDED / `recovered_B`. |
| Q8 | Progress vs metrics | Existing 16I `ManagedOperationProgress` answers “where is the operation now?” and is not overloaded. Separate optional bounded **metrics** answer “what workload / how efficient?” Historical records remain valid with metrics absent/null. |
| Q9 | Durable worklist | Optional bounded durable worklist with total/pending counts, **active document set** (not a falsely singular current file), per-document name/state, optional per-document workload/reuse. Dense batches MAY span multiple documents. |
| Q10 | Queue mutability | Pre-submit staging is mutable: append, remove-one, clear-all, inspect count/bytes. After 202 admission / frozen idempotency fingerprint, worklist is inspectable but **immutable** in 16K — no per-item in-flight removal. |
| Q11 | Performance instrumentation | 16K-B/D baseline measures listed in §9 before optimization. Detailed per-batch profiles belong in benchmark/evidence artifacts, not necessarily every durable op record. |
| Q12 | CUDA optimization + parity | Order: instrumented baseline → FP16 → batch sweep → optimized attention if supported → persistence/Qdrant only if warranted. Any precision/attention change that alters numerical vectors MUST pass a retrieval/index **parity gate** before default; if retrieval-semantic, identity treatment MUST be revised explicitly. |
| Q13 | Performance acceptance | No invented numerical SLO in this design. 16K-B establishes baseline; a beta usability threshold MUST be frozen before 16K-D results are accepted. Qualitative fixed requirement: multi-hour dense indexing for the primary beta corpus is not acceptable. |
| Q14 | Slice 17 handoff | Slice 17 remains Regression CI and unopened. 16K-G hands deterministic contracts only. Real CUDA throughput is NOT automatically a generic CI gate. |

---

## 6. 16K-A — Managed-ingestion correctness

### Scope

- Separate detached managed-ingest admission from synchronous request-deadline
  admission.
- Preserve existing synchronous `/v1/ingest` deadline behavior.
- Managed mutation lifetime is **independent** of the HTTP request lifetime that
  returned 202.
- Introduce safe cooperative control checkpoints within long-running dense work
  as needed (including between dense batches where feasible).
- Split live recovery from startup/crash terminalization semantics (Q7).
- Preserve atomic source publication and idempotency.
- Ensure a known timeout/cancellation/application failure is durably queryable
  with its safe error.

### Frozen lifetime rule (R1)

| Path | Deadline / lifetime |
|---|---|
| Synchronous `/v1/ingest` | Retains its accepted request-style wall deadline |
| Detached workspace scientific mutations (Add/Replace/Remove after 202) | **No** request-style whole-job deadline; lifetime ≠ HTTP request lifetime |
| Shutdown / cancel | Cooperative at safe points |
| Future stall / watchdog | Separately designed; not `REQUEST_TIMEOUT` on total elapsed job time |

**Removed as default for detached workspace ingestion:** expire → fail closed at
next checkpoint → retry. That model was the primary architectural defect
identified by the incident.

### Required proofs

1. Managed Add Sources may exceed 1800 simulated seconds and still continue to
   lexical/publication.
2. Synchronous `/v1/ingest` retains its existing timeout contract.
3. Live failure recovered to A ends **FAILED** with error retained and
   `recovered_A`.
4. Startup abandoned operation recovered to A remains **INTERRUPTED** /
   `recovered_A`.
5. Recovered B remains **SUCCEEDED** / `recovered_B`.
6. Prior workspace revision/snapshot remains authoritative after failure A.
7. No partial source publication occurs.

---

## 7. 16K-B — Ingestion observability (durable contracts)

Preserve existing **16I** progress semantics. Define three separate concepts:

| Concept | Answers | Nature |
|---|---|---|
| **progress** | Where is execution now? | Existing 16I bounded progress object (preserved) |
| **metrics** | How much work / how fast / what execution path? | New optional bounded aggregate projection |
| **worklist** | Which documents are in this operation and what state? | New optional bounded durable structure |

Exact Python class names are implementation details; field semantics below are
frozen for design.

### 7.1 Progress (16I preserved)

Existing managed-operation progress remains the bounded answer to stage /
step / message / fraction. It MUST NOT be overloaded with full metrics or the
full worklist. Stage-accurate steps remain required (parse / chunk / dense
embed+materialize / lexical / publish).

### 7.2 Metrics (optional, additive, bounded)

Operations MAY expose a metrics/diagnostics projection. Historical records with
metrics absent/null remain valid.

**Workload**

- `requested_document_count`
- `pre_active_source_count` / `post_active_source_count` where meaningful
- `uploaded_raw_bytes`
- `parsed_searchable_document_count`
- `child_chunk_count` / searchable chunk count
- `oversized_unsplittable_count`

**Reuse / new work**

- parsed artifacts generated / reused (where available)
- chunk artifacts generated / reused
- embeddings **generated** / **reused** (public/UI terminology; not “bypassed”)

**Dense execution**

- `device` (resolved)
- `dtype`
- `batch_size`
- `attention_backend`
- `embedding_dimension`

**Throughput**

- generated chunks/sec
- model-input tokens/sec only when measured reliably

**Stage durations**

- parse; chunk; dense generation; dense materialization/Qdrant; lexical;
  publication/finalization; total

### 7.3 Worklist (optional, durable, bounded)

Admitted managed source mutations gain an optional durable worklist sufficient
to survive refresh/reconnect.

Required semantics:

- `total_document_count`
- `pending_count`
- `completed_count` / `remaining_count` where meaningful
- `active_documents`: **set** (0..N), not a falsely singular current file
- per document: display name; bounded phase/state; optional workload/reuse
  counts when known

Dense work is passage/batch oriented and MAY span more than one document. The
API and UI MUST represent multiple `active_documents` truthfully.

Candidate per-document phases: `pending`, `parsing`, `parsed`, `chunking`,
`chunked`, `indexing`, `indexed` / prepared (not yet globally published),
`failed`, `requires_ocr`. “Ready” is reserved for canonical published source
state.

### 7.4 ETA truth rule

ETA, when shown, MUST be calculated from **meaningful remaining new work**
(especially generated/new embedding work and unfinished stages), not naïvely
from total chunks when much of the operation is cache-reused. If remaining-new
work is unknown or statistically meaningless, omit ETA rather than invent one.

---

## 8. 16K-C — First-user capacity model

### Frozen separation (R3)

**Transport / resource safety** (upload/spool/disk):

- uploaded bytes per document
- request bytes
- request file count
- spool / disk protection

**Workspace / search workload** (scientific/product capacity):

- active source count
- parsed / extracted text
- searchable child count
- generated / reused embeddings
- dense / lexical indexing workload

Raw upload bytes remain transport/storage safety guards, **not** the primary
scientific workload measure.

The product contract MUST distinguish at least:

- maximum files in one upload request;
- maximum raw bytes per uploaded file;
- maximum raw bytes per upload request;
- maximum active sources per workspace;
- supported searchable child-chunk workload per workspace;
- staging/storage safety behavior.

Internal reconstruction of an existing desired workspace MUST NOT accidentally
reapply an HTTP request-size policy to already-vaulted sources.

Potential capacity admission after parsing/chunking MUST fail before expensive
dense work when the searchable workload is outside the empirically supported
envelope.

**No fixed new numeric production limits are chosen in this design.** The
current **32-file / 25-MiB / 100-MiB** envelope is the **baseline under
investigation**, not the conceptual capacity model. Exact configured limits
are evidence-driven under later 16K-C/F implementation authority.

---

## 9. 16K-D — Dense / CUDA profiling and optimization

### 9.1 Instrumentation-first baseline (frozen measurements)

Before optimization acceptance, measure at least:

- Qwen input-token **p50 / p95 / p99 / max**
- `oversized_unsplittable` count
- per-batch maximum sequence length
- model encode duration
- embedding-artifact persistence duration
- dense point construction duration
- Qdrant materialization / upsert duration
- device
- dtype
- batch size
- peak VRAM where obtainable
- chunks/sec
- model-input tokens/sec
- first-batch versus steady-state behavior

Also record where feasible (aligned with Q11): per-batch item count and
aggregate model input tokens; generated/reused embedding counts; lexical and
publication durations; attention backend; CUDA memory observations where safely
measurable.

Detailed per-batch profiling belongs in benchmark/evidence artifacts.

### 9.2 Controlled optimization sequence

Current code path context: SentenceTransformers / Qwen3-Embedding-0.6B, CUDA,
batch size 32, per-chunk JSON embedding artifacts, local Qdrant materialization.

Frozen order (one material variable at a time):

1. current CUDA **FP32** / batch 32 baseline (instrumented)
2. CUDA **FP16** / batch 32
3. FP16 **batch-size sweep**
4. compatible **optimized attention** path if operationally reliable
5. artifact-persistence optimization **only if** profiling shows material cost
6. Qdrant batching/materialization optimization **only if** profiling shows
   material cost

Investigate whether slow throughput is driven by FP32 execution, suboptimal
batch sizing, long-tail / oversized child sequences, attention implementation,
per-vector artifact serialization/fsync/atomic-write overhead, Python point
construction, and/or Qdrant local materialization.

### 9.3 Parity gate

Chunking semantics MUST NOT be changed merely to improve benchmark numbers.

Any FP16 / attention optimization that changes numerical vectors MUST pass a
**retrieval / index parity gate** before being classified as non-semantic
execution policy or becoming default. If execution precision proves
retrieval-semantic rather than merely execution-policy, its identity treatment
MUST be revised explicitly rather than silently reusing incompatible embedding
identities.

Optimization MUST preserve strict offline behavior. No optimization is accepted
without the 16K-B baseline. A beta usability threshold MUST be frozen before
16K-D optimization results are accepted (Q13).

---

## 10. 16K-E — Ingestion worklist / progress / metrics UX

Preserves the accepted queue decisions; consumes 16K-B contracts.

### 10.1 Pre-submit staging (mutable)

- selected document count
- aggregate raw upload bytes, labeled as transport/storage information
- file name and individual raw size
- per-file **Remove**
- **Append** more files without replacing the selection
- **Clear all**
- validation messages tied to the affected file
- idempotency fingerprint prepared only from the final submitted selection

### 10.2 Admitted operation view (immutable membership)

After **202 Accepted**, the submitted worklist is durable, inspectable, and
**immutable** (no per-item mutation/removal in this tranche).

Compact card SHOULD show:

- current high-level activity
- current document **or** truthful **active-document set**
- completed / total / remaining document counts where meaningful
- **clickable remaining count** exposing the queue
- passage/chunk progress
- generated / reused embeddings
- current throughput
- elapsed time
- ETA when statistically meaningful (per §7.4)
- execution device in compact form

If a dense batch spans several documents, wording MUST reflect that
(e.g. “Embedding 32 passages from 3 documents”); it MUST NOT fabricate a
singular current document.

### 10.3 Expandable worklist

The remaining-document control opens a drawer/popover of every submitted
document and bounded truthful state (phases per §7.3).

### 10.4 Details surface

Expandable technical details MAY show device/dtype/batch/attention, searchable
chunk totals, generated/reused embeddings, stage durations, upload bytes, and
other bounded beta diagnostics. The ordinary view MUST remain understandable
without opening Details.

### 10.5 Terminal summaries

Success SHOULD retain a compact summary (sources ready, searchable passages,
reused/generated embeddings, elapsed). Known application failures MUST show
actionable error copy. OCR-required failures MUST identify the affected
filename. Known failures MUST NOT collapse into generic Interrupted copy.

### 10.6 Queue mutation boundary

Per-file removal is authorized only before submission. In-flight per-item
removal would require a separate design and is out of scope for 16K.

---

## 11. 16K-F — Real beta-corpus acceptance

The acceptance harness MUST operate on an external corpus directory and emit
reproducible structured evidence without committing private source content.

Minimum empirical runs:

1. representative ~1.3k-child cold workload comparable to the observed incident;
2. largest legitimate text-bearing beta document / representation needed to
   validate transport-versus-workload policy;
3. complete primary deduplicated non-OCR beta corpus;
4. immediate warm-cache repeat of the same primary corpus.

Required validation includes:

- operation completes **without false request timeout** (detached managed path
  is not gated by whole-job `REQUEST_TIMEOUT`);
- no partial publication;
- final source count is correct;
- worklist survives refresh/reconnect;
- generated/reused counters are truthful;
- stage metrics are present and internally coherent;
- resulting workspace supports normal retrieval/query;
- cache reuse materially reduces repeated scientific work;
- usability threshold frozen after baseline is met.

**16K-F MUST NOT** require the beta corpus to finish “within the authorized
deadline” in the synchronous-request sense. Completion criteria are correctness,
truthful telemetry, capacity-model honesty, and the frozen usability threshold
— not inheritance of `ingest_deadline_seconds` as a whole-job wall for detached
mutations.

---

## 12. 16K-G — Slice-17 regression handoff

Produce a bounded handoff identifying which 16K guarantees are suitable for
deterministic Slice-17 CI and which remain hardware-specific empirical checks.

Handoff candidates include: managed-operation lifetime semantics; FAILED versus
INTERRUPTED; recovery A/B; worklist schema/projection; metrics schema/projection;
progress monotonicity; capacity validation; OCR-required error mapping;
idempotency; no partial publication.

Real CUDA throughput is NOT automatically a generic CI gate.

**16K-G does not authorize Slice 17 implementation.**

---

## 13. Implementation order

Required order:

`16K-A → 16K-B → baseline evidence → 16K-C → 16K-D → 16K-E → 16K-F → 16K-G`

Rationale: correctness first (so long benchmarks cannot die from the known
deadline bug); observability second; capacity after real workload measurement;
CUDA after baseline; UI consumes stable backend contracts; real corpus
acceptance validates the integrated system; regression handoff closes the track
without opening Slice 17.

Each tranche requires separate implementation authority.

---

## 14. Candidate code ownership by tranche

These are candidate ownership areas, **not** blanket implementation
authorization.

| Tranche | Candidate areas |
|---|---|
| 16K-A | `operations.py`, `ingest.py`, workspace lifecycle / publication journal / journal; focused correctness/recovery tests |
| 16K-B | operation/workspace models and projections; progress/metrics adapters; stage timing; benchmark/evidence harness; telemetry tests |
| 16K-C | API/config capacity settings; upload spool/envelope validation; workspace desired-set capacity; capabilities projection; capacity tests |
| 16K-D | dense embedder/pipeline execution policy; performance harness; parity/retrieval evidence |
| 16K-E | managed-operation DTO additive fields; Workspace staging-worklist UI; OperationProgress / tray; UI types/client/helpers/tests |
| 16K-F/G | beta acceptance harness/evidence docs; regression-handoff documentation/tests only as separately authorized |

---

## 15. Explicit non-scope (this design-open / rework authority)

- Python / product code changes
- React / TypeScript / UI code changes
- Configuration changes going live
- New capacity limits going live
- Timeout behavior changes going live
- FP16 / FlashAttention / scientific `base.yaml` mutation as authorized defaults
- Benchmark execution as a design deliverable
- OCR
- Source deduplication behavior redesign
- Incremental indexing
- Distributed / background queue redesign
- Slice 17 implementation
- Slice 18
- 9G
- M7 closeout
- Edits to accepted/sealed Slice-16 artifacts (including
  `docs/slice16_closeout_inventory.md`)
- Main promotion of any tip

---

## 16. Design acceptance requirements

Before implementation authority may be issued, independent design review MUST
confirm:

1. Slice-16 canonical state is not reopened or contradicted;
2. 16K / 17 / 18 / M7 authorization boundaries are explicit;
3. synchronous ingest deadline semantics are preserved unless separately scoped;
4. detached managed-operation lifetime is distinguished from HTTP request
   lifetime;
5. live failure versus crash recovery terminal states are unambiguous;
6. progress, metrics, and worklist contracts are separate and bounded;
7. pre-submit queue mutability versus admitted-operation immutability is
   explicit;
8. capacity is not modeled primarily by raw bytes;
9. CUDA optimization cannot silently alter scientific identity / retrieval
   semantics;
10. OCR remains out of scope and fails transparently;
11. real beta acceptance uses external/private data without repository leakage;
12. Slice 17 receives only a handoff, not implicit implementation authorization.

---

## 17. Evidence references

- API traceback / op: `wop_eac9e1a596fc4b63a394cb2d1f4ea592`
- Dense manifest: `denseindex_e29c7015…` (1296 children)
- Deadline default: `api.ingest_deadline_seconds = 1800`
- Checkpoint raise site: `OperationHandle.checkpoint` → `REQUEST_TIMEOUT`
- UI label map: `materializing_dense_index` → “Finalizing semantic search index”
- First-beta corpus: external/private inventory (§2.2); not in-repo

---

## 18. Governance footer

```text
Design-open: S16-K-BETA-INGESTION-READINESS-DESIGN-OPEN-AUTH-001 — AUTHORIZED
Rework: S16-K-BETA-INGESTION-READINESS-DESIGN-REWORK-AUTH-001 — AUTHORIZED
Addresses: S16-K-BETA-INGESTION-READINESS-DESIGN-OPEN-IR-001 — REWORK REQUIRED
Human acceptance: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-001 — ACCEPTED
HA record: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-AUTH-001 — AUTHORIZED
HA-record IR: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-IR-001 — ACCEPT
Exact Human-accepted design subject: 0839b565cd60958141366048520236a71bf16fd0
Exact design-open base: 3a7d8ff2c442c5d4cd10c0c21637ebc4c52b65fa
Exact rework base: 5c693c531ded432b10cf5f6ac19d558a1f4e9431
16K: DESIGN ACCEPTED / FROZEN
16K-A: IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED
  Implementation IR: S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-IR-002 — ACCEPT
  Human acceptance: S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-HA-001 — ACCEPTED
  HA record: S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-AUTH-001 — AUTHORIZED
  Exact Human-accepted technical subject: 1370b99327124045ad96005e829095683842c06f
  HA-record IR: S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-IR-001 — ACCEPT
16K-B: IMPLEMENTATION AUTHORIZED / NOT YET ACCEPTED
  Implementation authority:
    S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-AUTH-001 — AUTHORIZED
  Exact implementation base: 39e5e09363193b2315ada9e56cb3e1c14ba9377d
  Independent review:
    S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-001 — REWORK REQUIRED (R1–R4)
  Rework authority:
    S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-001 — AUTHORIZED
  Exact rework base: 85f01f40080fe485b6ddb7700855aa34280c9c75
  Independent review:
    S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-002 — REWORK REQUIRED (R3 / R4a / R4b)
  Rework authority:
    S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-002 — AUTHORIZED
  Exact rework-002 base / parent: 533a07c3d1313d08eae5647e4c266d4fa3a439c5
  Branch: implementation/16k-b-ingestion-observability
16K-C → 16K-G: NOT YET AUTHORIZED
Frozen order: 16K-A → 16K-B → baseline evidence → 16K-C → 16K-D → 16K-E → 16K-F → 16K-G
Slice 16: COMPLETE / HUMAN ACCEPTED / CANONICAL
Slice 17: NOT AUTHORIZED
Slice 18: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
Does NOT authorize 16K-C→G / capacity / CUDA / UI
Does NOT reopen Slice 16 closeout
Does NOT authorize main promotion
Outstanding separate operation: promote 3a7d8ff… onto origin/main (still at e21b3e6…)
```
