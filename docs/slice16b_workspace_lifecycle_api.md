# Slice 16B — Workspace/source lifecycle API

```text
STATUS: IMPLEMENTATION EVIDENCE CANDIDATE
HUMAN ACCEPTANCE: PENDING
16B: IMPLEMENTED CANDIDATE / NOT ACCEPTED
16C+: NOT AUTHORIZED / NOT STARTED
```

## Authority binding

| Item | Value |
| --- | --- |
| Authorized baseline / sealed 16A closeout | `155983fec59a3ae6434286276bd34dcfdaaf8968` |
| Accepted 16A implementation | `e73959be508541a1c50d4919606aaf3157a5fa8a` |
| Locked design authority | `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8` |
| Prior 16B candidate (F13–F16) | `39b2b60c2d11c198f3f4850cfaf97084a51ec9e8` |
| Branch | `implementation/16b-workspace-lifecycle-api` |
| Phase | **16B only** |

## Independent review rework (F17–F19)

Disposition was REWORK REQUIRED — FINAL NARROW PASS. This candidate closes live
sync-journal reconciliation on post-write AppError, true startup recovery-result
evidence, and non-vacuous generator-request capture. F13/F14/F7–F9 architecture
is preserved.

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

## Tests run

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

## Explicit non-scope

16C–16H, UI, Training Mode, Gold Lab, Slice 17/18, 9G, M7 closeout **NOT AUTHORIZED**.
This document does **not** accept 16B.
