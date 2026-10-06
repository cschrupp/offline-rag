# Slice 16B — Workspace/source lifecycle API

```text
STATUS: IMPLEMENTATION ACCEPTED
HUMAN ACCEPTANCE: ACCEPTED
16B: COMPLETE / ACCEPTED
ACCEPTED IMPLEMENTATION SHA:
eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
INDEPENDENT REVIEW: PASSED
16C: COMPLETE / ACCEPTED @ 936e41446eb1e3697f6b7d245659831f19cf0613
16D+: NOT AUTHORIZED / NOT STARTED
```

## Authority binding

| Item | Value |
| --- | --- |
| Authorized baseline / sealed 16A closeout | `155983fec59a3ae6434286276bd34dcfdaaf8968` |
| Accepted 16A implementation | `e73959be508541a1c50d4919606aaf3157a5fa8a` |
| Locked design authority | `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8` |
| **Accepted 16B implementation SHA** | `eb8baefc6e3eaf7df33668c85fbbfef22364bb0e` |
| Prior 16B candidate (F13–F16) | `39b2b60c2d11c198f3f4850cfaf97084a51ec9e8` |
| Branch | `implementation/16b-workspace-lifecycle-api` |
| Phase | **16B COMPLETE / ACCEPTED** |

Human acceptance applies **exactly** to SHA
`eb8baefc6e3eaf7df33668c85fbbfef22364bb0e`.

## Independent review rework (F17–F19)

Disposition was REWORK REQUIRED — FINAL NARROW PASS, then **PASS**. This accepted
implementation closes live sync-journal reconciliation on post-write AppError,
true startup recovery-result evidence, and non-vacuous generator-request capture.
F13/F14/F7–F9 architecture is preserved.

### F17 — live AppError reconciles sync journal (never blind-drop)

Unsafe prior path: after `workspace.json` landed, `except AppError` dropped the
sync journal and marked the operation FAILED — destroying recovery evidence for
an already-applied mutation.

**Live reconciliation** (`SyncMutationCoordinator.reconcile` under the
already-held `WorkspaceMutationLease`):

| Observation | Outcome |
| --- | --- |
| No sync journal | ordinary FAILED persistence; re-raise |
| Live workspace matches prepared exact result (B) | operation SUCCEEDED with frozen receipt; journal dropped; caller returns success |
| Live workspace still at pre-mutation revision (A) | operation FAILED with the AppError; journal dropped; re-raise |
| Neither (ambiguous) | `workspace_state_unavailable`; **journal retained**; operation left nonterminal |

Startup `recover()` uses the same rules with `failure=None` (A → INTERRUPTED).

### F18 — true startup recovery result matrix

Fault-inject SUCCEEDED crash while suppressing live `_fail_operation` recovery so
the durable B journal and nonterminal op survive into
`recover_workspace_transactions()`. Cases assert startup performed
terminalization:

1. SOURCE_ADD — full result contract
2. SOURCE_REPLACE — stable source_id, new version, committed set/snapshot
3. non-final SOURCE_REMOVE — removed identity + remaining set
4. final EMPTY REMOVE — removed identity, empty status, null snapshot

### F19 — non-vacuous generator evidence

F16 assembled-context capture retained. After `run_workspace_query`:

- assert assembled contexts include evidence units
- **assert `generator_requests`** (generation actually invoked)
- inspect each request’s `EVIDENCE:` block for absence of OLD_MARKER / old doc

Adversarial user text may mention OLD_MARKER; only evidence/context must exclude it.

### Prior F13–F16 / F7–F12 / F1–F6 (retained)

Prepared sync receipt before workspace write; directory-identity corpus ownership
fail-closed; live scientific recovery under corpus lease; pre-202 validation;
frozen sync replay; dense/lexical/rerank/context supersession; spool/journal/
query-binding contracts.

## Carried-forward contracts (inherited by 16D+ when authorized)

These are accepted Slice-16B contracts for downstream phases. They are **not**
authorization for 16D.

1. **Workspace scientific mutation lock order:** `WorkspaceMutationLease` →
   `CorpusMutationLease`.
2. **Cross-registry publication invariant:** active
   `workspace.current_snapshot_id` corresponds to that workspace-managed corpus
   current publication.
3. **Workspace-owned corpus protection:** legacy `/v1/ingest` MUST NOT mutate a
   workspace-owned backing corpus; workspace-directory identity reserves the
   deterministic backing-corpus namespace even if `workspace.json` is
   missing/corrupt.
4. **Scientific mutation semantics:** non-empty add/replace/remove → full
   desired-set projection → immutable snapshot → journaled workspace/publication
   commit.
5. **Final-source removal:** MUST use EMPTY transition; MUST NOT use empty
   scientific ingest; MUST NOT fabricate an empty snapshot.
6. **Idempotency:** scientific and synchronous mutations retain the accepted
   durable idempotency semantics.
7. **Sync mutation crash recovery:** exact expected success receipt is durable
   before `workspace.json` mutation; recovery distinguishes A (did not commit),
   B (exact prepared post-state), and ambiguous (fail closed; retain evidence).
8. **Scientific transaction recovery:** startup recovery converges
   publication/workspace state to legal A or B before READY.
9. **Query snapshot binding:** workspace query is server-bound to
   `workspace.current_snapshot_id`; client snapshot pinning remains forbidden;
   Slice-15 `/v1/query` behavior remains unchanged.
10. **Supersession isolation:** once source version N+1 is current, version N
    cannot participate in dense, lexical, reranking, context, citations, or
    answer generation.
11. **Durable source content:** workspace source preview/content is served from
    hash-verified local vault state; no filesystem path exposure.
12. **Managed operations:** no durable queue; admitted work starts immediately;
    progress/result state is durable; interrupted scientific work is not
    auto-resumed after crash.

## Tests run (accepted candidate)

```text
uv run ruff check <touched sync_journal/lifecycle + integrity tests>
→ All checks passed

uv run pytest \
  tests/unit/app/test_slice16b_workspace_api.py \
  tests/unit/app/test_slice16b_rework_hardening.py \
  tests/unit/app/test_slice16b_integrity_rework.py \
  tests/unit/app/test_slice16b_publication_journal.py \
  tests/unit/app/test_slice16b_query_binding.py \
  tests/unit/app/test_slice16a_workspace_foundation.py \
  tests/unit/app/test_slice15a_foundation.py \
  tests/unit/app/test_slice15b_runtime_health.py \
  tests/unit/app/test_slice15c_snapshots_leases_documents.py \
  tests/unit/app/test_slice15d_product_ingest.py \
  tests/unit/app/test_slice15e_product_query_traces.py \
  tests/unit/app/test_slice15f_admission_deadlines_shutdown.py -q
→ 229 passed

git diff --check
→ clean
```

Integrity suite specifically covers: 3 post-write live-AppError reconciliations;
ambiguous F17 fail-closed retention; 4 true startup F18 recovery-result cases;
non-vacuous F19 generator assertion.

Full-repo pytest was not claimed as green.

## Residual risks / deferred

- Ambiguous sync mid-state retains journal for operator/startup diagnosis by design.
- F18 traps suppress live `_fail_operation` only in tests; production live path
  remains F7 corpus-lease recovery.

## Explicit non-scope confirmation

Human acceptance applies to exactly SHA
`eb8baefc6e3eaf7df33668c85fbbfef22364bb0e`.

**16C** is separately **COMPLETE / ACCEPTED** at
`936e41446eb1e3697f6b7d245659831f19cf0613`. **16D–16H**, Training Mode, Gold
Lab, Slice 17, Slice 18, 9G, and Milestone 7 closeout remain **NOT AUTHORIZED**.
Slice 16 overall is **not** complete.
