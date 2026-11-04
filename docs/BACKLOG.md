# Seneca engineering backlog and deferred registry

**Status:** LIVE PLANNING / NON-AUTHORIZING\
**Canonical reference:** `main` (see Git for current tip)\
**Updated:** 2026-11-04

This document is the live queue for work that remains after the Human-accepted
Slice 16 closeout and the post-L6 parser-stack corrective.

Backlog registration is **not** implementation authority. Every executable
tranche still requires its normal design / implementation / execution authority.
Historical accepted or sealed evidence is not rewritten merely because a later
backlog item exists.

## 1. Current disposition and active queue

### Completed before the remaining beta gates

```text
S16K-R01 — CLOSED / HUMAN ACCEPTED
S16K-R02 — CLOSED / 16K-C HUMAN ACCEPTED
S16K-R03 — CLOSED / NOT_REPRODUCED; historical root cause not established
16K-E    — CLOSED / HUMAN ACCEPTED
16K-F    — COMPLETE / HUMAN ACCEPTED — SCOPED BETA
BETA-GAME-01 — COMPLETE / HUMAN ACCEPTED / PROMOTED
BETA-GOLD-POOL-01 — COMPLETE / INDEPENDENTLY ACCEPTED / PROMOTED
BETA-GAME-02 — ACTIVE / BOUNDED IMPLEMENTATION AUTHORIZED
```

16K-F functional acceptance is complete. Performance on the available
replacement corpus is **EMPIRICALLY_CHARACTERIZED / ACCEPTED_DESCRIPTIVE**;
there is no outstanding full-corpus performance gate for the current beta.
The original 39-primary / approximately 7.5–8k-child, 60-minute figure was a
preliminary engineering usability objective based on estimated workload size,
not an empirically calibrated full-corpus threshold. The exact historical
population is no longer reproducible. Preserve its original specification as
historical provenance; it is superseded as the current-corpus comparator and
was neither met nor failed by run_002. See
[`docs/evidence/16k_f_execution/16K_F_HUMAN_CAMPAIGN_CLOSEOUT.md`](evidence/16k_f_execution/16K_F_HUMAN_CAMPAIGN_CLOSEOUT.md)
and its linked sanitized `RUN_002_EVIDENCE_INDEX.md`.

### Remaining beta path

```text
16K-F accepted closeout
    -> promoted by pure fast-forward to main at eb1b3ba0415e05bf91d5e9e6171e087eedd473a9
    -> 16K-G regression/CI handoff COMPLETE / HUMAN ACCEPTED
    -> BETA-SETTINGS-01 user-editable generation configuration
    -> BETA-SETTINGS-02 user-editable Gold Lab Authoring configuration COMPLETE /
       ACCEPTED / PROMOTED at 6ff215702056b5708547cdc3a275aad08b0d75dc
    -> BETA-GAME-01 Quick Play and BETA-GOLD-POOL-01 complete / promoted
    -> BETA-GAME-02 contextual guidance and accessible game experience
       (authorized / implementation active)
    -> Slice 17 design-open authority remains NOT AUTHORIZED
```

Original Slice 16G is already accepted; 16K-G names the separate regression
handoff and must not be confused with that completed slice. The 16K-F
lineage is now promoted; this handoff does not authorize Slice 17.

### BETA-GAME-01 — Quick Play and reusable activity decks

**Priority:** P1 before beta acceptance\
**Status:** COMPLETE / HUMAN ACCEPTED / PROMOTED\
**Branch:** `implementation/beta-game-01-quick-play`

Provide a workspace-centered expert workflow over existing Gold Lab projects,
baselines, campaigns, tasks, managed operations, and append-only judgments.
Deck identity is bound to the published snapshot, corpus/chunk-set identities,
and versioned generation/selection policies. Selection is improvement-oriented;
Quick Play is not a representative benchmark. Production play is limited to
Question Check and Rapid Fire. Keep administrative project/campaign management
available under Advanced Gold Lab. Do not change Gold scientific semantics,
publication authority, relevance scale, or ledger guarantees. Slice 17 remains
NOT AUTHORIZED.

### BETA-GOLD-POOL-01 — Qualified query-prompt support for Gold pooling

**Priority:** P0 beta blocker
**Status:** COMPLETE / INDEPENDENTLY ACCEPTED / PROMOTED
**Branch:** `implementation/beta-gold-pool-01-query-prompt`

Restore the existing Gold six-arm `dense-model-query-prompt-v1` path on the
qualified CUDA FP16 and CPU ONNX FP32 runtimes. Preserve raw-query defaults,
qualified representation and index identities, registered-prompt validation,
complete-six-arm reviewability, and no-fallback behavior. Add a scoped P1
query-contract amendment, production-adapter/factory/local-pooling regressions,
and privacy-safe failure diagnostics. The consumed failed Quick Play operation
is historical evidence and is not retried by this work.

The implementation was accepted at `4ea5c92a9082621f167e8fcd2a64d085534633f9`
and promoted by fast-forward. Physical CUDA execution remains unverified; no
live Quick Play retry or Slice 17 work is implied.

### BETA-GAME-02 — Game experience and contextual help

**Priority:** P1 before beta acceptance\
**Status:** BOUNDED IMPLEMENTATION AUTHORIZED / ACTIVE\
**Branch:** `implementation/beta-game-02-experience`

Provide a context-sensitive How to play guide on every Gold Lab screen,
including Quick Play, production Question Check and Rapid Fire, completion
states, and Advanced Gold Lab. Keep instructions concise, responsive, keyboard
accessible, neutral about correctness, and free of withheld Gold metadata.
Preserve all existing game, mutation, persistence, and production-eligibility
contracts. No new games, scientific changes, or Slice 17 work are authorized.
See [`docs/beta_game_02_experience.md`](beta_game_02_experience.md) and the
user-reported beta QA record at
[`BETA_QA_LIVE_2026-11-04.md`](evidence/beta_game_02/BETA_QA_LIVE_2026-11-04.md).

## 2. Historical queue snapshot

The following entries preserve planning and governance context from earlier
stages. Their live status is superseded by the current disposition above.

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
**Status:** CLOSED — BOUNDED `NOT_REPRODUCED`\
**Accepted subject:** `d7e85fe4aa68520ebc6e1879996b60461655eede`\
**Historical root cause / fix:** NOT ESTABLISHED

The bounded current-main disposition did not reproduce the historical
Fireground CUDA/cublasGemmEx failure. This closes the R03 investigation with a
bounded `NOT_REPRODUCED` result; it does not claim the historical defect was
identified or fixed. The approximate-populated-corpus limitation remains part
of the result. Production code was not changed, and promotion was not
authorized.

The following fixture details are retained as provenance for the historical
incident, not as evidence that a current defect remains open:

Known Fireground fixture provenance:

```text
Fireground_Operational_Guides.pdf
bytes: 6,796,067
sha256: 01bea4d628ffea01aab164535c81392a8b42b9a587f9b6295f302a9938f2f0c2
```

### 16K-E — Ingestion worklist / progress / metrics UX

**Priority:** P0\
**Status:** CLOSED — COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED\
**Accepted technical subject:** `37883b7a90d5f5b73077aa72d478e5b9c38b1b52`\
**Closure evidence:** [`16K_E_CLOSURE.md`](evidence/16k_e_ingestion_worklist_progress/16K_E_CLOSURE.md)

The accepted implementation reuses the 16I / 16K-B operation architecture and
delivers the bounded ingestion worklist, progress, metrics, terminal summary,
and refresh/reconnect presentation. Historical planning notes describing
pre-implementation gaps are superseded by the closure record. 16K-F has since
closed as scoped beta acceptance and is promoted to `main`. 16K-G is the
current separate regression-handoff tranche; Slice 17 remains unopened.

### 16K-F — Real beta-corpus acceptance

**Priority:** P0\
**Functional acceptance:** COMPLETE / HUMAN ACCEPTED — SCOPED BETA\
**Performance status:** EMPIRICALLY CHARACTERIZED / ACCEPTED DESCRIPTIVE\
**Active full-corpus latency SLO:** NONE ESTABLISHED\
**Closeout:** [`16K_F_HUMAN_CAMPAIGN_CLOSEOUT.md`](evidence/16k_f_execution/16K_F_HUMAN_CAMPAIGN_CLOSEOUT.md)\
**Sanitized evidence index:** [`RUN_002_EVIDENCE_INDEX.md`](evidence/16k_f_execution/RUN_002_EVIDENCE_INDEX.md)

Human acceptance covers the 38-source replacement-corpus cold/warm evidence,
17/17 robustness cases, grounded retrieval, largest eligible PDF, managed
Markdown smoke, and the single 1,296-child proxy. Metrics are descriptive for
the replacement workload. The original 39-primary / approximately 7.5–8k-child,
60-minute figure was a preliminary planning objective; the estimated corpus
was not a verified, permanently reproducible roster, and its full-corpus
performance was not empirically calibrated. The original design itself
cautioned against linear extrapolation from the 1,296-child incident. Preserve
that design and its objective as historical provenance. It is not an active
acceptance gate, and no pass/fail claim is made against it.

### 16K-G — Slice-17 regression handoff

**Priority:** P0\
**Status:** COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED\
**Accepted subject:** `7de798850febff22a1a548b9e2795b07ba0ea81d`\
**Closeout:** [`16K_G_CLOSEOUT.md`](evidence/16k_g_regression_handoff/16K_G_CLOSEOUT.md)\
**Handoff:** [`16K_G_REGRESSION_HANDOFF.md`](evidence/16k_g_regression_handoff/16K_G_REGRESSION_HANDOFF.md)\
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

The handoff is independently reviewed and Human accepted. Slice 17 design-open
remains a separate authorization gate; this closeout does not authorize it.

### BETA-SETTINGS-01 — User-editable generation configuration

**Priority:** P1 before beta acceptance\
**Status:** COMPLETE / HUMAN ACCEPTED / PROMOTED\
**Accepted technical subject:** `3841e70db09b7fd12512a2502729a27512cad446`\
**Implementation memory:** [`beta_settings_01_user_generation_configuration.md`](beta_settings_01_user_generation_configuration.md)

Introduce deployment-selected `operator` and `user` ownership modes for
existing generation Settings. Operator mode remains the default and preserves
environment locks. User mode treats generation environment values as bootstrap
configuration and lets persisted product Settings take precedence after save.
The change is limited to generation configuration and preserves restart-before-
activation, strict-offline endpoint validation, API-key safety, and existing
operator deployments. BETA-GAME-01 is separately authorized; conversational
fluency and Slice 17 remain separate.

## 3. Separate robustness / release backlog

These items are real work but are **not** part of the mandatory 16K-E->F->G
sequence unless a later authority explicitly moves them there. BETA-HARDEN-01
is a P0 beta blocker and takes priority before beta acceptance.

### GPU-RESIDENCY-01 — CUDA model residency and memory release policy

**Priority:** P1 — reliability / resource-lifecycle follow-up\
**Status:** REGISTERED / POLICY OPTIONS NOT SELECTED\
**Implementation authority:** NONE

This reconciles the existing GPU-residency diagnostic work and R03 residual;
it does not claim a new diagnosis or duplicate the historical HTTP-500
reproduction task. The accepted constrained-free-VRAM and residency/allocator
campaigns did not reproduce the historical failure. The accepted residency
campaign was negative and did not satisfy the M0–M2 eligibility gate. API
process embedding-model tensor residency remains `not_established`; host-level
GPU memory could not be attributed to the API PID in the WSL observation path.

Keep these resource states distinct:

- **Model-weight residency:** live CUDA tensors retained by the model object.
- **PyTorch allocator cache:** process-local reserved blocks, including blocks
  not currently allocated to live tensors; `empty_cache()` does not release
  live model weights.
- **External/device ownership:** driver-reported memory held by other processes
  or device/runtime allocations not attributable to Seneca's model tensors.

Options for a future bounded product-policy decision:

1. **Resident:** retain the process-scoped model after first use; favors low
   repeat latency and current lifecycle simplicity, with sustained GPU memory
   occupancy.
2. **Idle eviction:** release model references after a frozen idle interval;
   could reduce live weight residency but adds reload latency and requires
   race-safe coordination with active work. Allocator-reserved memory may remain
   until separately released, and external memory is unaffected.
3. **Worker isolation:** host embedding in a separate process and terminate or
   recycle that worker to release its process-owned CUDA context and tensors;
   strengthens ownership boundaries at additional process and handoff cost.

No option is selected. A future authority must choose and measure the desired
latency/resource tradeoff before implementing unload, allocator, or model
selection behavior. This item does not authorize `empty_cache()`, model
unloading, device migration, worker isolation, or changes to runtime lifecycle.

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

## 4. Registered later candidates

### POST-M7-01 — Answer-level user feedback / continuous evaluation

**Status:** PLANNING REGISTERED / DESIGN NOT OPEN / IMPLEMENTATION NOT AUTHORIZED\
**Source:** `docs/slice16g_gap_registry_addendum.md`

Keep observational thumbs/reason feedback separate from Gold, benchmark truth,
automatic training data, and automatic regression-fixture promotion.

### 9G — Production gold / publication readiness

**Status:** DEFERRED / NOT AUTHORIZED

Do not resume merely because Gold Lab exists. Resume when the target corpus is
substantially complete/stable and publication-quality benchmarking is approaching.

## 5. Explicitly deferred / do not reopen by default

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

## 6. Downstream roadmap after active residuals

```text
16K-F scoped beta closeout accepted and promoted to main
        ->
16K-G regression handoff (candidate ready for independent review)
        ->
request Slice 17 design-open authority after 16K-G acceptance
        ->
Slice 17 — Regression CI (not authorized)
        ->
Slice 18 — Portfolio Release Package
        ->
Milestone 7 closeout
```

Slice 17, Slice 18, and M7 closeout remain unauthorized until separately opened.
