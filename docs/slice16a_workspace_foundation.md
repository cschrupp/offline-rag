# Slice 16A — Workspace contracts & persistence foundation

```text
STATUS: IMPLEMENTATION ACCEPTED
HUMAN ACCEPTANCE: ACCEPTED
16A: COMPLETE / ACCEPTED
ACCEPTED IMPLEMENTATION SHA:
e73959be508541a1c50d4919606aaf3157a5fa8a
INDEPENDENT REVIEW: PASSED
16B: COMPLETE / ACCEPTED @ eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16C+: NOT AUTHORIZED / NOT STARTED
```

## Authority binding

| Item | Value |
| --- | --- |
| Authorized baseline | `9f4b98f983a353f19c8e9f7e343cf8958ea8c525` |
| Locked design authority | `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8` |
| Accepted implementation SHA | `e73959be508541a1c50d4919606aaf3157a5fa8a` |
| Branch | `implementation/16a-workspace-foundation` |
| Phase | **16A COMPLETE / ACCEPTED** |

## Implementation summary

16A adds the durable application-layer substrate for future workspace lifecycle
work (16B), without HTTP routes, UI, ingest orchestration, or query adapters.

Introduced under `src/offline_rag/app/workspace/`:

- domain contracts: `WorkspaceRecord`, `SourceVersionRecord`, revisions,
  managed-operation records;
- `WorkspaceMutationLease` — fcntl live-owner serialization;
- `WorkspaceStore` — lease-guarded revision CAS persistence;
- `RawSourceVault` — private raw-object store with server-generated physical IDs
  and metadata identity cross-checks;
- `ManagedOperationStore` — durable idempotency/operation records with frozen
  lifecycle transitions (not a queue);
- publication retirement primitives preserving immutable snapshot manifests;
- `EmptyTransitionCoordinator` — journaled cross-registry EMPTY transition /
  recovery to legal states A or B.

Slice-15 `ProductPublicationRegistry` publish/resolve semantics are unchanged
except clearing stale `retired.json` audit metadata after successful publish.
Empty scientific ingest was **not** introduced.

## Storage layout

Under `settings.paths.workspaces` (DATA_DIR/`workspaces`):

```text
workspaces/
  ws_<hex>/
    workspace.json
    vault/
      objects/vobj_<hex>          # raw bytes (server name)
      meta/vobj_<hex>.json        # display name + hash metadata
    operations/
      by_id/wop_<hex>.json
      by_idempotency/idem_<sha256>.json   # points at operation_id
    journal/
      empty_transition.json       # present only while EMPTY transition in flight
```

Locks:

```text
/data/locks/workspace.<workspace_id>.lock   # fcntl.flock live-owner lease
```

Product publication retirement (per backing corpus):

```text
corpora/<backing_corpus>/product/
  current.json          # SOLE authority for current product publication
  retired.json          # audit/recovery metadata only (never overrides current.json)
  snapshots/<snap>.json # immutable; never deleted by retirement/recovery
```

## Workspace mutation serialization (F1)

- Primitive: `WorkspaceMutationLease` on `/data/locks/workspace.<id>.lock`
- Semantics match `CorpusMutationLease`: exclusive non-blocking flock; process
  death releases ownership; filename alone ≠ busy; fail fast with
  `workspace_conflict` / `reason=lease_held`
- `apply_metadata_patch`, `tombstone`, `create`, `save`, and EMPTY coordinator
  begin/steps/recover execute under this lease
- Nested acquire avoided via optional held-lease parameter
- While `empty_transition.json` exists, ordinary mutations fail closed with
  `empty_transition_in_progress` (journal fence across split step calls)

### Lock acquisition ordering (frozen / enforced)

```text
workspace lease → corpus lease
```

Never acquire in the opposite order. EMPTY coordinator paths that mutate or
restore product publication (`step_retire_publication`, recovery A/B pointer
work) acquire `CorpusMutationLease` for `journal.backing_corpus_name` **while
the workspace lease is already held**. Low-level retirement/restore helpers
remain caller-serialized and do not acquire the corpus lease internally
(Slice-15 ingest already owns it through `publish()`).

Contention: holding `CorpusMutationLease` for the backing corpus causes
`step_retire_publication` to fail `corpus_busy` without modifying
`current.json`.

## Idempotency identity (F2)

Canonical fingerprint envelope:

```json
{"kind": "<ManagedOperationKind>", "expected_revision": N|null, "payload": {...}}
```

Persisted as `request_fingerprint = reqfp_<sha256(canonical_json(envelope))>`.

Same key + same kind + same expected_revision + same payload → same operation.
Any difference → `idempotency_conflict`.

## Managed-operation serialization (F7)

`ManagedOperationStore.begin` and `update_status` run inside a
`WorkspaceMutationLease` critical section (optional already-held lease for
16B composition). When acquiring their own lease they use **blocking** flock
so concurrent callers serialize rather than fail-fast. The section covers:

- idempotency index existence/read + identity comparison;
- operation record + index creation;
- status read + transition validation + durable write.

Concurrent same-key/same-identity → one stable `operation_id`.
Concurrent same-key/different-identity → one winner + one `idempotency_conflict`.
Concurrent terminal transitions from RUNNING → exactly one terminal wins;
loser re-reads committed terminal and fails closed.

## Managed-operation state machine (F3)

```text
PENDING → PREPARING | RUNNING | FAILED | INTERRUPTED
PREPARING → RUNNING | FAILED | INTERRUPTED
RUNNING → SUCCEEDED | FAILED | INTERRUPTED
SUCCEEDED, FAILED, INTERRUPTED → terminal
```

Idempotent rewrite of the same terminal status is allowed.
Illegal transitions fail closed with `workspace_state_unavailable` /
`illegal_operation_status_transition`. Retries are new operations.
Terminal immutability holds under concurrency (lease-guarded), not only
sequentially.

## Retirement / publication authority (F4 / F8)

- `current.json` (existence + valid pointer) is the **sole** authority for
  whether a corpus currently has a product publication
- `retired.json` is **audit / recovery metadata only** — its presence MUST NOT
  override an existing valid `current.json` (not a two-bit state machine)
- Cleared opportunistically by `restore_current_publication_pointer` and by
  `ProductPublicationRegistry.publish` after writing `current.json`
- Recovery to A clears stale `retired.json` even when `current.json` already
  exists (crash between marker write and pointer unlink)
- Historical snapshot manifests remain untouched

## Vault identity verification (F5)

`RawSourceVault.get_meta` / `load_bytes` require:

- `meta.workspace_id == requested workspace_id`
- `meta.object_id == requested object_id`

Mismatch → `workspace_state_unavailable` with
`vault_workspace_id_mismatch` or `vault_object_id_mismatch`.

## Contracts introduced

- Workspace status: `active` | `empty` | `tombstoned`
- EMPTY invariant: `sources == []` and `current_snapshot_id == null`
- ACTIVE invariant: ≥1 active source and `current_snapshot_id != null`
- Revision: monotonic positive int; `serialize_revision()` for future If-Match
- Source lineage: stable `source_id`, advancing `version`, content-derived
  `document_id` (changes iff content identity changes)

## Depublication / retirement semantics

`retire_current_publication(settings, corpus_name)` (caller holds corpus lease):

1. writes `product/retired.json` audit metadata with last snapshot id (if any);
2. unlinks `product/current.json` (authority bit);
3. leaves `product/snapshots/*` intact.

A crash may leave both files briefly; while `current.json` exists it remains
authoritative. After retirement (pointer gone), `resolve()` fails as
unpublished (`corpus_unknown` / `not_published`). Ordinary Slice-15 republish /
pointer restore establishes a future current and clears the audit marker.

## Crash-recovery mechanism

`EmptyTransitionCoordinator` persists an atomic journal before cross-registry
mutation:

```text
intent_recorded → publication_retired → workspace_emptied → committed
```

`recover(workspace_id)` is idempotent and lands in:

- **A** — prior non-empty workspace + prior publication current; or
- **B** — EMPTY workspace + no active current publication.

Rule of thumb: if workspace is already EMPTY, complete to B (ensure retired);
otherwise restore prior workspace JSON + ensure current pointer (A), clearing
stale `retired.json` even when the pointer already exists. Historical
snapshot manifests are never deleted. Competing metadata mutations cannot
commit while the journal fence is present. Publication restore/retire under
recovery holds corpus lease inside the workspace lease.

## Error code additions

| Code | HTTP (frozen for 16B) | Meaning |
| --- | --- | --- |
| `workspace_unknown` | 404 | Missing / tombstoned (active resolution) |
| `workspace_not_ready` | 409 | Empty / not query-ready |
| `workspace_conflict` | 409 | Revision / lease / transition conflict |
| `operation_unknown` | 404 | Managed op missing |
| `idempotency_conflict` | 409 | Same key, different identity envelope |
| `workspace_state_unavailable` | 409 | Corrupt / illegal state transition |

`SafeErrorDetails` extended with `workspace_id`, `source_id`, `operation_id`.

## Tests run

```text
uv run ruff check src/offline_rag/app/workspace src/offline_rag/app/publication.py \
  tests/unit/app/test_slice16a_workspace_foundation.py
→ All checks passed

uv run pytest \
  tests/unit/app/test_slice16a_workspace_foundation.py \
  tests/unit/app/test_slice15a_foundation.py \
  tests/unit/app/test_slice15c_snapshots_leases_documents.py \
  tests/unit/app/test_slice15g_container_packaging.py -q
→ 99 passed

git diff --check
→ clean
```

Coverage includes F1–F5 plus F6–F8: corpus-lease contention on EMPTY
retirement; concurrent begin (same/conflicting identity); concurrent terminal
status race; recovery A clears stale `retired.json` when `current.json` still
present; current overrides marker for resolve authority.

## Known limitations / deferred beyond 16A

- No workspace HTTP CRUD / multipart upload / query adapter (delivered in
  accepted **16B**)
- No end-to-end add/remove/replace orchestration or ingest invocation
  (delivered in accepted **16B**)
- No UI / Training Mode / Gold Lab (**16C+** — **NOT AUTHORIZED**)
- No automatic EMPTY transition from product APIs in 16A (primitives only;
  product EMPTY path delivered in accepted **16B**)
- Journal recovery is local/filesystem; no multi-worker redesign
- Startup/readiness integration of outstanding EMPTY-journal recovery was a
  **16B obligation** and is recorded as accepted under
  `docs/slice16b_workspace_lifecycle_api.md`

## Carried-forward contracts (inherited by accepted 16B / later phases)

1. **Workspace mutation ordering:** `WorkspaceMutationLease` →
   `CorpusMutationLease` (never reverse).
2. **Product publication authority:** `current.json` is the sole
   current-publication authority; `retired.json` is audit/recovery metadata
   only.
3. **Managed-operation serialization:** `begin` / `update_status` serialize
   through the workspace lease (optional already-held lease for composition).
4. **EMPTY transition recovery:** startup/readiness must recover outstanding
   journals before workspace mutation/query surfaces become ready.

These contracts are accepted 16A foundation constraints. Accepted 16B
implementation evidence:
[`docs/slice16b_workspace_lifecycle_api.md`](slice16b_workspace_lifecycle_api.md)
at `eb8baefc6e3eaf7df33668c85fbbfef22364bb0e`.

## Explicit non-scope confirmation

Human acceptance of **16A** applies to exactly SHA
`e73959be508541a1c50d4919606aaf3157a5fa8a`.

**16B** is separately **COMPLETE / ACCEPTED** at
`eb8baefc6e3eaf7df33668c85fbbfef22364bb0e`. **16C–16H**, Slice 17, Slice 18,
9G, and Milestone 7 closeout remain **NOT AUTHORIZED**. Slice 16 overall is
**not** complete.
