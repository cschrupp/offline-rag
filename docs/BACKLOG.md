# Seneca engineering backlog and deferred registry

**Status:** LIVE PLANNING / NON-AUTHORIZING  
**Canonical reference:** `main` at `7ca0c2332dbaf524fe777317cdd1aede7a795633`  
**Updated:** 2026-10-27

This document is the live queue for work that remains after the Human-accepted
Slice 16 closeout and the post-L6 parser-stack corrective.

Backlog registration is **not** implementation authority. Every executable
tranche still requires its normal design / implementation / execution authority.
Historical accepted or sealed evidence is not rewritten merely because a later
backlog item exists.

## 1. Active residual completion queue

The preferred order is:

```text
S16K-R01 governance reconciliation
    -> S16K-R02 16K-C Human-disposition normalization
    -> S16K-R03 Fireground CUDA current-main disposition
    -> 16K-E ingestion worklist / progress UX
    -> 16K-F real beta-corpus acceptance
    -> 16K-G Slice-17 regression handoff
    -> request Slice 17 design-open authority
```

This queue completes the already accepted 16K design sequence before opening
Slice 17. It does **not** reopen the original Slice 16 closeout.

### S16K-R01 — Post-L6 governance reconciliation

**Priority:** P0  
**Status:** OPEN / DOCUMENTATION + GOVERNANCE ONLY  
**Implementation authority:** NOT IMPLIED

The post-L6 CUDA profile-aware policy and workspace raw-byte corrective are now
ancestors of canonical `main`, but live documentation still contains their
pre-promotion terminals (`READY FOR INDEPENDENT REVIEW` / `PROMOTION NOT
AUTHORIZED`). The parser corrective has an explicit IR-002 / Human acceptance /
promotion closeout; the preceding CUDA/raw-byte tranches need their exact
recorded review/acceptance disposition reconciled without inventing acceptance.

Required work:

- identify the exact technical subjects and any existing IR / Human dispositions
  for the post-L6 CUDA product-policy implementation;
- identify the exact technical subject and any existing IR / Human disposition
  for the workspace raw-byte corrective;
- reconcile `ROADMAP.md`, `README.md`, and other live projections;
- preserve historical implementation-result text as historical provenance;
- do not alter L5 evidence, capacity measurements, or product-limit semantics.

Exit condition:

```text
live governance projection is internally consistent
+
no unverified ACCEPT / HA claim is introduced
```

### S16K-R02 — 16K-C Human-disposition normalization

**Priority:** P0  
**Status:** OPEN / GOVERNANCE ONLY  
**Technical subject:** `219c8551d208530ec93c5697ca5591ad52bfb228`

16K-C is recorded as `IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED` with
IR-002 `ACCEPT`, but the canonical ledger does not record a Human technical
acceptance comparable to 16K-A/B.

Required decision:

- either record the already-existing Human acceptance if durable evidence exists;
- or explicitly record that independent acceptance was intentionally terminal
  for 16K-C and no separate HA gate is required;
- otherwise request a bounded Human acceptance gate before 16K closure.

No implementation change is authorized by this item.

### S16K-R03 — Fireground CUDA / historical HTTP-500 disposition

**Priority:** P0  
**Status:** OPEN / SEPARATE RUNTIME RELIABILITY RESIDUAL  
**Execution authority:** NOT YET AUTHORIZED

Canonical 16K evidence still records:

```text
Fireground CUDA/cublasGemmEx runtime issue: OPEN / SEPARATE / NOT FIXED
Historical GPU-residency HTTP 500 root cause: UNRESOLVED
```

The constrained-free-VRAM campaign did not reproduce the historical failure,
and later CUDA qualification/product work succeeded, but the Fireground
residual itself was never given a current-main terminal disposition.

Known Fireground fixture provenance:

```text
Fireground_Operational_Guides.pdf
bytes: 6,796,067
sha256: 01bea4d628ffea01aab164535c81392a8b42b9a587f9b6295f302a9938f2f0c2
```

Next action should be a bounded current-main reproduction/disposition exercise,
not an open-ended optimization campaign.

Allowed terminals for a future authorized exercise:

```text
REPRODUCED -> open a narrowly attributed corrective
NOT_REPRODUCED -> record bounded non-reproduction and assess whether current
                  qualified runtime evidence supersedes the old residual
INCONCLUSIVE -> keep OPEN with exact reason
```

Do not claim the historical defect was "fixed" merely because it does not
reproduce.

### 16K-E — Ingestion worklist / progress / metrics UX

**Priority:** P0  
**Status:** PLANNED / ACCEPTED DESIGN EXISTS / IMPLEMENTATION NOT AUTHORIZED  
**Design:** `docs/slice16k_beta_ingestion_readiness_design.md` §10

Current product code contains useful partial substrate from 16I, including
fine-grained durable progress, but the accepted 16K-E product surface is not
complete.

Observed gaps on current `main` include:

- Add Sources file-picker changes replace the current selection rather than
  supporting append-more-files behavior;
- no per-file pre-submit Remove control;
- no Clear All control;
- public operation DTO exposes basic progress but not the durable worklist / rich
  operation metrics envisioned by 16K-E;
- operation presentation does not expose the remaining-document worklist/queue;
- no truthful active-document-set presentation for multi-document dense batches;
- generated/reused embedding counts, throughput, ETA, and technical execution
  details are not presented as designed where available/meaningful.

Reuse 16I contracts rather than creating a parallel progress architecture.
In-flight per-item removal remains explicitly out of scope.

Exit target: implementation candidate ready for independent review under a
separate 16K-E authority.

### 16K-F — Real beta-corpus acceptance

**Priority:** P0  
**Status:** PLANNED / ACCEPTED DESIGN EXISTS / EXECUTION NOT AUTHORIZED  
**Design:** `docs/slice16k_beta_ingestion_readiness_design.md` §11

The successful 64 MiB Shupe ingestion is valuable evidence, but it is not the
formal 16K-F acceptance matrix.

The accepted design requires structured evidence for at least:

1. representative ~1.3k-child cold workload;
2. largest legitimate text-bearing beta document / representation required for
   transport-vs-workload validation;
3. complete primary deduplicated non-OCR beta corpus, cold;
4. immediate warm-cache repeat of the same primary corpus.

Required checks include durable-operation lifetime semantics, atomic
publication, correct final source count, reconnect/recovery behavior, truthful
generated/reused counters and stage metrics, successful retrieval/query after
publication, material cache reuse on warm repeat, and the frozen full-corpus
usability requirement.

Private corpus content must remain external; evidence should be structured and
reproducible without committing private source bytes.

### 16K-G — Slice-17 regression handoff

**Priority:** P0  
**Status:** PLANNED / ACCEPTED DESIGN EXISTS / NOT AUTHORIZED  
**Design:** `docs/slice16k_beta_ingestion_readiness_design.md` §12

Produce the bounded handoff that separates:

- deterministic contracts appropriate for normal Slice-17 CI; from
- hardware-specific / empirical qualification that must remain scheduled or
  manually executed rather than generic PR blockers.

Candidate deterministic guarantees include managed-operation lifetime,
FAILED-vs-INTERRUPTED semantics, recovery A/B, worklist and metrics schemas,
progress monotonicity, capacity validation, OCR-required error mapping,
idempotency, cache identity, and atomic publication.

Real CUDA throughput is not automatically a generic CI gate.

Slice 17 design-open should be requested only after this handoff is complete.

## 2. Separate robustness / release backlog

These items are real work but are **not** part of the mandatory 16K-E->F->G
sequence unless a later authority explicitly moves them there.

### ROBUST-01 — Native PDF parser process isolation

**Priority:** P1  
**Status:** REGISTERED / DESIGN NOT OPEN / IMPLEMENTATION NOT AUTHORIZED

The `docling-parse` 7.23.1 upgrade closes the known Shupe crash fixture, but a
future native parser SIGSEGV can still terminate the API process because PDF
conversion executes in-process.

Target direction:

- execute native PDF parsing behind a subprocess/process boundary;
- translate abnormal child exit into a durable operation failure;
- preserve atomic publication;
- keep the API healthy after parser child failure;
- retain useful diagnostics without exposing unsafe internals publicly;
- preserve parser identity/provenance and strict-offline behavior.

Recommended timing: before public/release hardening, but it need not block
16K-E/F/G unless evidence changes.

### CI-BASELINE-01 — Repository-wide green-baseline normalization

**Priority:** P1  
**Status:** DEFER TO SLICE 17 DESIGN

Slice 16 explicitly did not claim a fully green repository baseline. Slice 17
should inventory the pre-existing lint/full-suite debt, classify intentional
exclusions, and establish deterministic CI without silently turning historical
performance observations into new SLOs.

### REL-01 — Container image size / CPU-CUDA release variants

**Priority:** P1 before Slice 18 public release  
**Status:** OPEN GITHUB ISSUE #1 / DEFERRED FROM CURRENT ACCEPTANCE

Current issue: approximately 10.3 GB reference image; investigate multi-stage
build, CPU-oriented default release image, and separate CUDA variant while
preserving accepted topology and `/data` / `/models` boundaries.

This is not a Slice-16 or 16K correctness blocker, but it should be resolved or
explicitly dispositioned before the portfolio release package is finalized.

### REL-02 — Portfolio release / public claims package

**Priority:** downstream  
**Status:** SLICE 18 / DESIGN NOT OPEN / NOT AUTHORIZED

Includes `PORTFOLIO_DEMO.md`, polished public documentation, architecture/demo
media, benchmark methodology, limitations, hardware/runtime profiles, and
reproducible install/run guidance. Claims must remain backed by accepted evidence.

## 3. Registered later candidates

### POST-M7-01 — Answer-level user feedback / continuous evaluation

**Status:** PLANNING REGISTERED / DESIGN NOT OPEN / IMPLEMENTATION NOT AUTHORIZED  
**Source:** `docs/slice16g_gap_registry_addendum.md`

Keep observational thumbs/reason feedback separate from Gold, benchmark truth,
automatic training data, and automatic regression-fixture promotion.

### 9G — Production gold / publication readiness

**Status:** DEFERRED / NOT AUTHORIZED

Do not resume merely because Gold Lab exists. Resume when the target corpus is
substantially complete/stable and publication-quality benchmarking is approaching.

## 4. Explicitly deferred / do not reopen by default

The following are **not** active queue items merely because they remain open or
historically unimplemented:

- Evidence Sweep production eligibility — NOT APPROVED;
- Chunk Duel production eligibility — NOT APPROVED;
- 320 px + 200% zoom observation — deferred/not required for accepted 16H;
- legacy FakeGenerator supersession debt — deferred/not required;
- 64/128 active-source envelope experiments — require separate contract/config
  authority;
- Question Bank replace-import — not authorized; merge-import is accepted;
- 16K-D full 1296 FP32 confirmation, default promotion, alternate models,
  further quantization, and mechanical D3/D4/D5 continuation — closed/deferred;
- future >=512 MiB per-source large-PDF target — research/product target only,
  not current policy;
- LangGraph recovery orchestration / NeMo Guardrails / Slice 13C/13D — deferred
  under Milestone 6 dispositions;
- enterprise auth/RBAC, multi-tenant policy, distributed Qdrant, permanent
  purge/GC, factual conversational memory as evidence, LMS integration,
  GraphRAG/multi-agent expansion — outside accepted Slice-16 scope.

Reopen any of these only when new evidence or a new product objective justifies
its own design/authority.

## 5. Downstream roadmap after active residuals

```text
finish active 16K residual queue
        ->
16K-G regression handoff
        ->
Slice 17 — Regression CI
        ->
Slice 18 — Portfolio Release Package
        ->
Milestone 7 closeout
```

Slice 17, Slice 18, and M7 closeout remain unauthorized until separately opened.
