# Slice 16F-A — Gold Lab Contracts & Persistence Foundation

## Authority

| Item | Value |
|---|---|
| Frozen 16F design authority | `4fde40da2458d69f9249b8334210fc84e9f3239c` |
| Design artifact | `docs/slice16f_gold_lab_data_plane.md` |
| Human design acceptance | ACCEPTED |
| Independent design review | PASS |
| Branch | `implementation/16f-a-gold-lab-foundation` |
| Starting HEAD (16F-A) | `4fde40da2458d69f9249b8334210fc84e9f3239c` |
| Implementation SHA (16F-A) | `2933d6fdd85e511fc72897dfb946aa095774287c` |
| Documentation SHA (16F-A) | `c17d4681e438ba72e64f159a73343dbcd75a05b2` |
| Rework 1 starting HEAD | `b4de3409219dae8d7c0682707a8dff2facd7adbf` |
| Rework 1 implementation SHA | `3cf64b366556e02eb1275fd96e0ee5cb2c09fd3a` |
| Rework 1 documentation SHA | _(filled after docs commit)_ |

## Scope

16F-A implements only the persistence/contracts foundation:

- Gold Lab durable root (`PathSettings.gold_lab` → `data/gold-lab`)
- `GoldProject` / `GoldCampaign` contracts and lifecycle primitives
- Selection-policy contract + `cfg_` fingerprint
- Frozen semantic-contract identifiers
- Deterministic task / query / Hard Call identities
- Reviewable-case helper
- Pristine baseline admission
- Exact workspace / snapshot / corpus / chunk binding
- CURRENT-workspace race protection before campaign promote
- Historical candidate + source-seed validation
- Immutable `hard_calls.json`
- Atomic nested campaign publication (Gold-Lab-local; does not widen global flat `atomic_publish_directory`)
- Ledger envelope + append-only primitive + campaign-local `fcntl.flock` lease
- Filesystem coordination under `settings.paths.locks`

## Rework 1 — Commit-boundary / identity / ledger-integrity hardening

Hardening only (no redesign; no 16F-B entry):

- Final campaign commit holds `WorkspaceMutationLease` then `GoldLabProjectLease` across project/workspace revalidation and `os.replace`
- Frozen lock order: workspace → project (archive never acquires workspace lease)
- Strict frozen ID grammar validators (no prefix-only acceptance)
- Path helpers validate full grammar before filesystem join
- Stored `project_id` / `campaign_id` must match durable path identity
- Ledger immutable IDs validated before any ledger file publication
- Ledger task membership validated against sealed baseline case candidate pools
- Sealed baseline load verifies `authoring_run_id` + SHA-256 bytes

## Non-scope (explicit)

- 16F-B product mutation / idempotent command service / effective-state projection / scoring / coverage counters
- 16F-C GoldDataset export / registration
- 16F-D application/API data plane
- 16G–16H games / UI
- 9G (deferred)
- HTTP `/v1/...` Gold routes
- React / Training UI
- Scientific contract changes (`evaluation/gold.py`, gold_authoring models/finalize)
- GoldDataset-v1 modification
- Retrieval / default config promotion
- M7 pinned evidence edits

## Production files

### Package

- `src/offline_rag/app/gold_lab/__init__.py`
- `src/offline_rag/app/gold_lab/errors.py`
- `src/offline_rag/app/gold_lab/ids.py`
- `src/offline_rag/app/gold_lab/reviewable.py`
- `src/offline_rag/app/gold_lab/models.py`
- `src/offline_rag/app/gold_lab/paths.py`
- `src/offline_rag/app/gold_lab/leases.py`
- `src/offline_rag/app/gold_lab/publish.py`
- `src/offline_rag/app/gold_lab/baseline.py`
- `src/offline_rag/app/gold_lab/store.py`
- `src/offline_rag/app/gold_lab/campaigns.py`
- `src/offline_rag/app/gold_lab/ledger.py`

### Existing wiring

- `src/offline_rag/config/models.py` — `PathSettings.gold_lab`
- `src/offline_rag/config/loader.py` — `OFFLINE_RAG_DATA_DIR` remaps `gold_lab`
- `src/offline_rag/app/paths.py` — startup-owned required data dirs include `gold_lab`

## Persistence layout

```text
data/gold-lab/
  projects/<project_id>/project.json
  campaigns/<campaign_id>/
    campaign.json
    hard_calls.json
    baseline/authoring_run.json
    ledger/
    projection/
  datasets/          # empty root reserved (no 16F-C behavior)
  registrations/     # empty root reserved (no 16F-C behavior)
```

## Contracts implemented

| Contract | Identifier |
|---|---|
| Absolute relevance | `gold-absolute-relevance-v1` |
| Question check | `gold-question-check-v1` |
| Auxiliary preference | `gold-auxiliary-preference-v1` |
| Hard Call designation | `gold-hard-call-designation-v1` |
| Hard Calls artifact | `offline-rag-gold-hard-calls-v1` |
| Ledger | `offline-rag-gold-lab-ledger-v1` |
| Selection policy | `gold-selection-policy-v1` (`cfg_<sha256>`) |

## Tests

`tests/unit/app/test_slice16f_a_gold_lab_foundation.py`

Matrix coverage: paths, ids, selection policy, projects/lifecycle, baseline admission, exact binding + CURRENT race, historical identity, reviewable helper, Hard Calls, atomic campaign publication, ledger append/integrity, campaign locking, Rework 1 strict IDs / path safety / commit races / ledger membership / sealed baseline authority, non-scope surface assertions.

## Validation

```text
uv run pytest tests/unit/app/test_slice16f_a_gold_lab_foundation.py
uv run pytest tests/unit/app/test_slice16a_workspace_foundation.py
uv run ruff check src/offline_rag/app/gold_lab \
  src/offline_rag/config/models.py \
  src/offline_rag/config/loader.py \
  src/offline_rag/app/paths.py \
  tests/unit/app/test_slice16f_a_gold_lab_foundation.py
git diff --check
```

## Governance after 16F-A / Rework 1

| Gate | Status |
|---|---|
| 16F design authority | FROZEN at `4fde40da2458d69f9249b8334210fc84e9f3239c` |
| 16F-A | REWORK AUTHORIZED (this hardening) — not human-accepted |
| 16F-B / 16F-C / 16F-D | NOT AUTHORIZED |
| 16G–16H | NOT AUTHORIZED |
| 9G | DEFERRED / NOT AUTHORIZED |

After 16F-A (+ Rework 1) the repository has durable, auditable Gold Lab storage and immutable campaign provenance, but still no product/UI client path to create or mutate scientific truth.
