# Seneca engineering backlog and deferred registry

**Status:** LIVE PLANNING / NON-AUTHORIZING\
**Canonical reference:** `main` (see Git for current tip)\
**Updated:** 2026-10-31

This document is the live queue for work that remains after the Human-accepted
Slice 16 closeout and the post-L6 parser-stack corrective.

Backlog registration is **not** implementation authority. Every executable
tranche still requires its normal design / implementation / execution authority.
Historical accepted or sealed evidence is not rewritten merely because a later
backlog item exists.

## 1. Active residual completion queue

Completed governance reconciliations precede the remaining active queue:

```text
S16K-R01 CLOSED — post-L6 governance reconciliation
    -> S16K-R02 CLOSED — 16K-C Human-disposition normalization
    -> S16K-R03 Fireground CUDA current-main disposition
    -> 16K-E ingestion worklist / progress UX
    -> 16K-F real beta-corpus acceptance
    -> 16K-G Slice-17 regression handoff
    -> request Slice 17 design-open authority
```

This queue completes the already accepted 16K design sequence before opening
Slice 17. It does **not** reopen the original Slice 16 closeout.

### S16K-R01 — Post-L6 governance reconciliation

**Priority:** P0\
**Status:** CLOSED — INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED\
**Implementation authority:** NOT IMPLIED

**Reconciliation subject:** `d60e253ce28eb5227983a53ec70a221b8dfdc28c`\
**Independent review:** `S16K-R01 IR-001 — ACCEPT`\
**Human acceptance:** ACCEPTED

The post-L6 CUDA profile-aware policy and workspace raw-byte corrective are
ancestors of canonical `main`. That establishes canonical code presence, but it
does not establish dedicated Human acceptance or tranche-specific promotion.
The parser corrective has a separate, explicit IR-002 / Human acceptance /
promotion closeout; that later fast-forward carried these earlier commits as
ancestors and does not retroactively close their acceptance gates.

History and live evidence were checked for this reconciliation candidate:

| Tranche | Technical subject / result tip | Repository-recorded disposition | Canonical / promotion history |
|---|---|---|---|
| Post-L6 CUDA profile-aware product policy | Candidate `5e08fb710113ab2289254192be7a680898a8ca96`; smoke/result tip `83971b9fa74409cffb5a3a7b772a699f687eb132` | `IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT REVIEW`; no dedicated implementation IR or Human acceptance record was found | Ancestor of `main`; no tranche-specific promotion authority or closeout record found |
| Workspace raw-byte ceiling corrective | Candidate `736af75aebb09526993264e5ee7344d384b4e64f`; governance pin `d9ddc4cd54b3b3966bfae28044439378ddee031f` | `IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT REVIEW`; the earlier result says promotion was not authorized. No dedicated repository IR or Human acceptance record was found. An earlier review acceptance is reported in this conversation, but is not durably recorded in the reachable repository history. | Ancestor of `main` through the later parser-stack fast-forward; this does not replace the earlier “promotion not authorized” record or create tranche-specific promotion authority |

Accordingly, the candidate records implementation and canonical presence for
both tranches, but does not claim repository-verified independent acceptance,
Human acceptance, or dedicated promotion for either. The raw-byte review
acceptance reported in conversation remains explicitly distinguished from a
durable Git disposition. Existing implementation-result and historical
ROADMAP entries remain unchanged as provenance.

IR-001 accepted the reconciliation subject with findings F001–F006 closed.
The review confirmed scope purity, both lineages, the later parser-promotion
boundary, historical provenance preservation, and the documentation-only
verification posture. The reviewer noted that the candidate had been committed
to `main` before review; this governance record is a successor commit and does
not treat that sequence as prior acceptance.

Human acceptance was granted for the exact reconciliation subject above. This
acceptance closes R01 only; it does not accept the underlying CUDA policy or
raw-byte implementation tranches. This successor commit records the acceptance
and closure.

Completed reconciliation scope:

- identified the exact technical subjects and repository-recorded IR / Human dispositions
  for the post-L6 CUDA product-policy implementation;
- identified the exact technical subject and repository-recorded IR / Human disposition
  for the workspace raw-byte corrective;
- reconciled `ROADMAP.md`, `README.md`, and `docs/BACKLOG.md`;
- preserved historical implementation-result text as provenance;
- left L5 evidence, capacity measurements, and product-limit semantics unchanged.

Exit condition:

```text
live governance projection is internally consistent
+
no unverified ACCEPT / HA claim is introduced
+
IR-001 ACCEPT and Human acceptance recorded for the exact reconciliation subject
```

### S16K-R02 — 16K-C Human-disposition normalization

**Priority:** P0\
**Status:** CLOSED — HUMAN ACCEPTED / SEQUENCING GAP RECORDED\
**Authority:** `S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-HA-001`\
**Technical subject:** `219c8551d208530ec93c5697ca5591ad52bfb228`

16K-C implementation is complete and independently accepted by IR-002. Human
acceptance is now recorded for the exact technical subject above under the
bounded HA authority. This closes the missing 16K-C Human gate.

Historical sequence finding:

- 16K-C IR-002 acceptance-record successor:
  `33a031b6a1bbda0b3b80fa96c8bff0fdfcece06f`
- 16K-D was subsequently authorized with that commit as its exact parent.
- Therefore, 16K-D proceeded before 16K-C's required Human acceptance was
  durably closed. This is a historical sequencing governance gap.
- The later 16K-C acceptance does not rewrite that sequence and does not by
  itself invalidate independently accepted 16K-D evidence.

This R02 closure is documentation-only. It authorizes no implementation,
scientific execution, additional 16K-D work, or 16K-E/F/G tranche.

### S16K-R03 — Fireground CUDA / historical HTTP-500 disposition

**Priority:** P0\
**Status:** OPEN / SEPARATE RUNTIME RELIABILITY RESIDUAL\
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

**Priority:** P0\
**Status:** PLANNED / ACCEPTED DESIGN EXISTS / IMPLEMENTATION NOT AUTHORIZED\
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

**Priority:** P0\
**Status:** PLANNED / ACCEPTED DESIGN EXISTS / EXECUTION NOT AUTHORIZED\
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

**Priority:** P0\
**Status:** PLANNED / ACCEPTED DESIGN EXISTS / NOT AUTHORIZED\
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
sequence unless a later authority explicitly moves them there. BETA-HARDEN-01
is a P0 beta blocker and takes priority before beta acceptance.

### BETA-HARDEN-01 — Large-PDF admission and failed-operation recovery

**Priority:** P0 — beta blocker\
**Status:** CLOSED / HUMAN ACCEPTED / PROMOTED

Technical implementation subject: `7ebf56796779449090fb85b4a0ac6c944c01f1f1`.
Durable result: [`docs/evidence/beta_harden_01/IMPLEMENTATION_RESULT.md`](evidence/beta_harden_01/IMPLEMENTATION_RESULT.md).
Independent review: IR-001 — ACCEPT. Human acceptance: ACCEPTED.
Fast-forward promotion tip: `793ef6d75388052d3790864b218acdcb3953ffd5`.

A valid `SOURCE_ADD` can fail before ingestion because the large-PDF CUDA
pre-admission check requires at least `7,156,531,200` bytes of effective GPU
capacity (about 7.16 GB decimal). Retries under unchanged host conditions then
receive the same admission rejection. Separately, the failed-operation tray
retains terminal cards after their operation references have been removed from
local storage.

The backend releases the workspace mutation lease and operation-capacity handle
in `finally`; the observed retry loop is caused by the admission policy and UI
state reconciliation, not a permanently poisoned CUDA runtime.

Corrective scope:

- remove or revise the obsolete large-PDF CUDA pre-admission threshold so a
  valid PDF of at most 90 MiB is not rejected solely by that gate;
- retain upload limits: PDF 90 MiB; other supported text files 25 MiB;
- rely on the corrected CUDA embedding path (`use_cache=false`, token-aware
  batching, direct FP16, and bounded CUDA OOM recovery);
- preserve atomic publication and safe terminal failure on genuine runtime OOM;
- keep CPU fallback deferred;
- consume detached `run_in_executor()` future exceptions so managed failures do
  not emit `Future exception was never retrieved`;
- make `ActiveOperationsBootstrap` remove terminal operations from rendered
  state when their active-operation references are forgotten;
- prevent failed operation cards from accumulating after reconciliation or
  dismissal;
- return source mutation controls to a usable state after an operation fails;
- improve capacity-error copy if any legitimate admission rejection remains.

The user-facing upload-limit copy for both Add Source and Replace Source is:

```text
Maximum upload file size: 90 MiB for PDF, 25 MiB for other text files
```

Indexing, cache identity, publication, and workspace rebuild semantics remain
unchanged.

Acceptance target:

1. Trigger a controlled failed `SOURCE_ADD`.
2. Verify the previously published workspace remains intact.
3. Verify the mutation lease and operation-capacity handle are released.
4. Verify the failed operation is surfaced once.
5. After terminal reconciliation or dismissal, verify its card neither remains
   nor reappears.
6. Verify Add / Replace controls are usable again without restarting Seneca.
7. Verify a subsequent valid `SOURCE_ADD` succeeds in the same process.
8. Verify no `Future exception was never retrieved` warning is emitted.
9. Verify a valid PDF larger than 25 MiB and at most 90 MiB is not rejected
   solely by the obsolete CUDA pre-admission threshold.
10. Verify genuine CUDA exhaustion still fails safely without partial
    publication.

The bounded implementation was separately authorized. This status grants no
Human acceptance, promotion, or authority for downstream beta work.

### TEST-STARTUP-01 — Diagnose managed-operation TestClient startup hang

**Priority:** P2\
**Status:** REGISTERED / NON-BLOCKING TO BETA

Selected managed-operation recovery tests can wait indefinitely while entering
`fastapi.testclient.TestClient`. A faulthandler trace shows the test thread
waiting for the AnyIO portal startup handshake; it does not identify which
application startup activity is responsible. The focused recovery-test batch
and isolated cases timed out without an assertion failure.

The same process-recovery behavior passed through a live API restart: a
non-terminal source-add was interrupted during PDF parsing, startup marked it
`INTERRUPTED`, the prior publication remained intact, and a subsequent source
add succeeded in the recovered process. Therefore this test-infrastructure
issue does not currently block beta.

Next action: diagnose the `TestClient` lifespan/startup wait and restore
bounded automated coverage for managed-operation restart recovery. Do not
reopen product recovery semantics unless new live evidence fails.

### ROBUST-01 — Native PDF parser process isolation

**Priority:** P1\
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

**Priority:** P1\
**Status:** DEFER TO SLICE 17 DESIGN

Slice 16 explicitly did not claim a fully green repository baseline. Slice 17
should inventory the pre-existing lint/full-suite debt, classify intentional
exclusions, and establish deterministic CI without silently turning historical
performance observations into new SLOs.

### REL-01 — Container image size / CPU-CUDA release variants

**Priority:** P1 before Slice 18 public release\
**Status:** OPEN GITHUB ISSUE #1 / DEFERRED FROM CURRENT ACCEPTANCE

Current issue: approximately 10.3 GB reference image; investigate multi-stage
build, CPU-oriented default release image, and separate CUDA variant while
preserving accepted topology and `/data` / `/models` boundaries.

This is not a Slice-16 or 16K correctness blocker, but it should be resolved or
explicitly dispositioned before the portfolio release package is finalized.

### REL-02 — Portfolio release / public claims package

**Priority:** downstream\
**Status:** SLICE 18 / DESIGN NOT OPEN / NOT AUTHORIZED

Includes `PORTFOLIO_DEMO.md`, polished public documentation, architecture/demo
media, benchmark methodology, limitations, hardware/runtime profiles, and
reproducible install/run guidance. Claims must remain backed by accepted evidence.

## 3. Registered later candidates

### POST-M7-01 — Answer-level user feedback / continuous evaluation

**Status:** PLANNING REGISTERED / DESIGN NOT OPEN / IMPLEMENTATION NOT AUTHORIZED\
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
