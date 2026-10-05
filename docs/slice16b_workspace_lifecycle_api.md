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
| Prior 16B candidate (F7–F12) | `2df2ea61b73c62c27dacc1c82eb898c758fc62c3` |
| Branch | `implementation/16b-workspace-lifecycle-api` |
| Phase | **16B only** |

## Independent review rework (F13–F16)

Disposition was REWORK REQUIRED — NARROW FINAL PASS. This candidate closes the
sync journal torn-write window, fail-closed workspace corpus ownership, complete
scientific recovery-result matrix evidence, and captured bound-query context
isolation. F7–F12 scientific transaction architecture is preserved.

### F13 — sync journal torn-write closed

Unsafe prior window: INTENT durable → `workspace.json` lands → crash before
`mark_workspace_committed()` → recovery treated INTENT as “never committed” (A)
even though the mutation landed.

**Mechanism:** prepare the exact post-mutation `ManagedOperationResult` first and
persist it in the sync journal at `intent_recorded` **before** writing
`workspace.json`. Then save the prepared workspace record, flip phase to
`workspace_committed`, terminalize the op, drop the journal.

**Post-state recognition on INTENT recovery:**

| Observation | Outcome |
| --- | --- |
| Live workspace matches prepared receipt (mutation-specific fields) | **B** → SUCCEEDED with frozen result |
| Live `revision == expected_revision` (mutation never landed) | **A** → INTERRUPTED |
| Neither | fail closed `sync_post_state_unrecognized` |

Recognition uses title/description/revision/status/snapshot/source_count/timestamps
for workspace PATCH/DELETE, and full source receipt fields for source metadata
PATCH — not merely `revision == expected + 1`.

Crash matrix covered for each of PATCH workspace, DELETE workspace, PATCH source:

1. after INTENT before workspace write → A
2. after workspace write before journal committed (no `mark_workspace_committed`) → B
3. after journal committed before op SUCCEEDED → B

### F14 — workspace corpus ownership fail-closed

`ws_*` directory identity reserves `backing_corpus_name_for(directory)` (`wsc_*`).
Legacy `/v1/ingest` against that corpus:

- valid record → `workspace_conflict` / `workspace_managed_corpus`
- tombstoned → blocked
- missing or corrupt/inconsistent `workspace.json` →
  `workspace_state_unavailable` (never silently unowned)
- unrelated standalone corpus → Slice-15 unchanged

Lifecycle ingest still uses explicit `authorize_workspace_id`.

### F15 — recovered scientific result matrix

Crash after durable B commit before op SUCCEEDED; startup recovery yields
`SUCCEEDED` with result equal to the normal-success contract for:

1. SOURCE_ADD — `source_id` / `source_version` / `source_ids` / revision / status / snapshot
2. SOURCE_REPLACE — stable `source_id`, new `source_version`, committed set + N+1 snapshot
3. non-final SOURCE_REMOVE — removed identity + remaining `source_ids` + republished snapshot
4. final EMPTY REMOVE — removed identity, `source_ids=[]`, `snapshot_id=null`, `status=empty`

### F16 — assembled context isolation

F12 dense/lexical/rerank/citation/answer checks retained. Added instrumentation of
`HybridRerankContextAssembler.assemble` on the canonical
`workspace.current_snapshot_id → resolve → run_bound_snapshot_query` path, plus a
recording `FakeGenerator`. After v05→v06:

- assembled context contains no `OLD_MARKER` / old `document_id`
- generator EVIDENCE block contains neither (query may mention OLD adversarially)
- reranker never presented OLD candidates

### Prior F7–F12 / F1–F6 (retained)

Live failure recovery under held corpus lease; pre-202 scientific validation;
frozen sync replay; complete async recovery results; durable spool; journal
outlives op terminalization; batch add/remove; server-owned query binding.

## Receipt / result schema (`ManagedOperationResult`)

Unchanged from F9/F11: frozen fields reconstruct workspace_view / source_view /
scientific op results without live-state mixing. Sync INTENT journals now
**always** carry `result_json` (prepared expected receipt) before workspace write.

## HTTP contract

Unchanged. Slice-15 routes remain registered; workspace-owned backing corpora
are guarded fail-closed by directory identity.

## Tests run

```text
uv run ruff check <touched sync_journal/corpus_ownership/lifecycle + integrity tests>
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
→ 221 passed

git diff --check
→ clean
```

Integrity suite specifically covers: 3× sync mutation three-point crash matrix;
ADD/REPLACE/REMOVE/EMPTY recovered results; corrupt/missing/tombstone ownership;
full OLD→NEW context instrumentation.

Full-repo pytest was not claimed as green.

## Residual risks / deferred

- Ambiguous mid-state (workspace advanced but receipt mismatch) fails closed rather
  than guessing; operators must repair manually — intentional.
- Catalog directory scan remains fine at 16B scale.

## Explicit non-scope

16C–16H, UI, Training Mode, Gold Lab, Slice 17/18, 9G, M7 closeout **NOT AUTHORIZED**.
This document does **not** accept 16B.
