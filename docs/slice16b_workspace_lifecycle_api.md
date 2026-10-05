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
| Prior 16B candidate (F1–F6) | `06413e89499db67aca5be7226f093245b9ed01ca` |
| Branch | `implementation/16b-workspace-lifecycle-api` |
| Phase | **16B only** |

## Independent review rework (F7–F12 + corpus guard)

Disposition was REWORK REQUIRED after F1–F6. This candidate closes live failure
recovery lease lifetime, pre-202 scientific validation, exact sync receipt replay,
sync crash recovery, complete async recovery results, workspace-owned corpus
protection, and full pipeline supersession proof. Workspace query binding is
preserved.

### F7 — corpus ownership through live failure recovery

Normal success already held `WorkspaceMutationLease` → `CorpusMutationLease`
through scientific publication, workspace commit, lineage, op success, and
journal drop.

Live failure path now recovers **before** releasing the corpus lease:

`WorkspaceMutationLease` → `CorpusMutationLease` → scientific work / publication
→ on exception: recover A or B (reuse already-held corpus lease; no nested
acquire) → repair pointer/workspace/lineage → terminalize managed op →
retain/drop journal → **then** release corpus → release workspace.

`NonEmptyPublicationCoordinator.recover` and `EmptyTransitionCoordinator.recover`
accept optional `corpus_lease=`. When held, they must not nested-acquire.
Startup recovery may still acquire its own corpus lease (runtime not READY).

### F8 — scientific preconditions before 202

For a **new** idempotency key, under `WorkspaceMutationLease` and before capacity
admission:

1. inspect existing idempotency identity first
2. matching existing → return it (even if historical If-Match is now stale)
3. conflicting key → `idempotency_conflict`
4. only if key is NEW: resolve workspace; reject unknown/tombstoned; compare
   revision to If-Match; validate source existence for PUT/DELETE; validate
   mutable state
5. then reserve / admit / launch

Stale valid If-Match on a new key → HTTP 409 `workspace_conflict` with no worker,
no ingest capacity, no scientific mutation.

### F9 — exact sync success/failure replay

`PATCH/DELETE` workspace and `PATCH` source metadata reconstruct public responses
exclusively from the frozen durable receipt/result. Live workspace state is never
mixed into an old success. FAILED ops re-raise the persisted
`ManagedOperationSafeError`. INTERRUPTED projects the interrupted contract — never
HTTP 200 merely because a live workspace exists.

### F10 — synchronous mutation crash recovery

`SyncMutationCoordinator` journals INTENT → workspace write → COMMITTED(+result)
→ op SUCCEEDED → journal drop. Startup runs sync recovery **before**
`interrupt_all_nonterminal()`:

- INTENT only / mutation never committed → interrupt/fail per contract
- COMMITTED with frozen result → reconstruct exact SUCCEEDED receipt

Covered crash points: after reservation before workspace write; after workspace
write before SUCCEEDED receipt — for PATCH workspace, DELETE workspace, PATCH
source.

### F11 — recovery-to-B reconstructs complete scientific result

Non-empty recovery projects `source_id`, `source_version`, `source_ids`,
`workspace_revision`, `workspace_status`, `snapshot_id` from lineage + committed
workspace (ADD/REPLACE from appended; REMOVE from superseded).

EMPTY recovery uses `removed_source_json` for removed `source_id` /
`source_version`, with `source_ids=[]`, `snapshot_id=null`,
`workspace_status=empty`.

### Workspace-owned corpus protection (S16-D08)

`assert_legacy_ingest_allowed` fails closed when `POST /v1/ingest` targets a
corpus that is any workspace's `backing_corpus_name`
(`reason=workspace_managed_corpus` / `workspace_conflict`). Standalone Slice-15
corpora unchanged. Lifecycle ingest passes `authorize_workspace_id` and
`assert_authorized_workspace_corpus` for its own backing corpus only.

### F12 — S16-D12 supersession through the retrieval stack

After v05→v06 replacement, assertions exercise the **actual** snapshot-bound
pipeline (not vault/JSON scans alone):

- current corpus manifest: old document_id absent, new present
- dense retrieval under bound index/collection: no old document_id / OLD_MARKER
- lexical retrieval under bound index: no old document_id / OLD_MARKER
- reranker never presented OLD_MARKER candidates
- assembled context contains no OLD_MARKER
- answered output cannot cite old document_id / contain OLD_MARKER
- adversarial OLD_MARKER query cannot resurrect superseded source

Batch add/remove HTTP campaign retained from F6.

## Receipt / result schema (`ManagedOperationResult`)

Frozen fields used for exact sync replay and recovered async success:

| Field | Sync workspace | Sync source | Async scientific |
| --- | --- | --- | --- |
| `workspace_revision` | yes | yes | yes |
| `workspace_status` | yes | yes | yes |
| `snapshot_id` | yes | yes | yes |
| `title` / `description` | yes | — | — |
| `source_count` | yes | — | — |
| `created_at` / `updated_at` | yes | yes | — |
| `source_id` / `source_version` | — | yes | yes (incl. recovered) |
| `source_ids` | — | — | yes |
| `display_name`, `content_type`, `byte_size`, `content_hash`, `document_id` | — | yes | — |
| `active_from_revision` / `active_from_snapshot_id` | — | yes | — |

No public `backing_corpus_name` or `vault_object_id`.

## Prior F1–F6 (retained)

Corpus lease spans cross-registry commit; durable sync idempotency reservation;
scientific idempotency before capacity; durable upload spool before 202; journal
outlives lineage + op terminalization; HTTP OLD→NEW + batch campaigns.

### Query binding (preserved)

`workspace.current_snapshot_id` → internal `resolve_snapshot` → torn-read check
→ shared `run_bound_snapshot_query`. No client `snapshot_id` DTO field.
Does not re-resolve `current.json` inside the bound path.

## HTTP contract

| Method | Path |
| --- | --- |
| GET/POST | `/v1/workspaces` |
| GET/PATCH/DELETE | `/v1/workspaces/{workspace_id}` |
| GET/POST | `/v1/workspaces/{workspace_id}/sources` |
| GET/PUT/PATCH/DELETE | `/v1/workspaces/{workspace_id}/sources/{source_id}` |
| GET | `/v1/workspaces/{workspace_id}/sources/{source_id}/content` |
| POST | `/v1/workspaces/{workspace_id}/query` |
| GET | `/v1/operations/{operation_id}` |

Slice-15 routes remain registered; workspace-owned backing corpora are guarded.

## Tests run

```text
uv run ruff check <touched 16B Python modules + integrity/rework tests>
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
→ 158 passed (16B/16A/15a/15c/15d) ; 53 passed (15b/15e/15f)

git diff --check
→ clean
```

Integrity suite (`test_slice16b_integrity_rework.py`) covers F7 live recovery/corpus
contention, F8 stale If-Match / unknown workspace/source / historical retry, F9
frozen replay, F10 sync crash recovery, F11 recovered ADD result shape,
workspace-owned corpus guard, and F12 dense/lexical/rerank/context isolation.

Full-repo pytest was not claimed as green; unrelated pre-existing debt is outside
this rework.

## Residual risks / deferred

- Crash-point matrix covers representative F7/F10/F11 points; not every journal
  phase is re-driven through the HTTP worker (unit journal recovery remains
  authoritative for A/B legality).
- Workspace-owned corpus guard enumerates workspace catalog records; extremely
  large catalogs would be a future scale concern, not a 16B acceptance gap.

## Explicit non-scope

16C–16H, UI, Training Mode, Gold Lab, Slice 17/18, 9G, M7 closeout **NOT AUTHORIZED**.
This document does **not** accept 16B.
