# 16F-D — Gold Lab Application / API Data Plane (Implementation Evidence)

```text
16F-D GOLD LAB APPLICATION / API DATA PLANE
IMPLEMENTATION EVIDENCE — STOP FOR INDEPENDENT IMPLEMENTATION REVIEW
```

## Authority

| Item | Value |
|---|---|
| Frozen 16F design | `4fde40da2458d69f9249b8334210fc84e9f3239c` |
| Accepted 16F-A | `2e4d51b06763ed04bce8b6e2d60337f61082bc64` |
| Accepted 16F-B | `f4fe892044f8443594d7629e5b49a3d9f39b6297` |
| Accepted 16F-C | `646b1f178e10b49d3f39322dff8314dbd4f9987e` |
| Frozen 16F-D0 design | `7df8a151c6bf47ab9c93d54edf9bece4e3f6ed39` |
| Frozen design document | `docs/slice16f_d_application_api_design.md` |
| Starting HEAD | `7df8a151c6bf47ab9c93d54edf9bece4e3f6ed39` |
| Implementation SHA | `IMPLEMENTATION_SHA_PENDING` |
| Documentation SHA | `DOCUMENTATION_SHA_PENDING` |

## Production footprint

New:

- `src/offline_rag/app/gold_lab/application.py` — facade + centralized translator
- `src/offline_rag/app/gold_lab/views.py` — public DTO projections
- `src/offline_rag/app/gold_lab/historical_source.py` — immutable historical reader
- `src/offline_rag/api/gold_lab.py` — FastAPI `/v1/gold-lab` router (17 routes)

Narrow modifications:

- `src/offline_rag/api/app.py` — register gold router before SPA fallback
- `src/offline_rag/app/runtime.py` — lazy `runtime.gold_lab`
- `src/offline_rag/app/errors.py` — Gold `ErrorCode`s + SafeErrorDetails IDs

Test adaptation:

- `tests/unit/app/test_slice16f_a_gold_lab_foundation.py` — nonscope allows authorized
  `api/gold_lab.py` + `api/app.py` wiring only

## Route count

Exactly **17** Gold Lab v1 routes under `/v1/gold-lab` (no extras).

## Facade wiring

`ApplicationRuntime.gold_lab` lazily constructs `GoldLabApplicationService(runtime)`.

Facade composes accepted:

`GoldLabStore`, `GoldCampaignService`, `GoldLabMutationService`,
`GoldLabScientificExportService`, `WorkspaceStore`, registration validators,
historical source reader.

No direct ledger append, no local contribution recomputation, no scientific
finalizer duplication.

## Historical reader

Implements the frozen immutable chain:

validated corpus/snapshot path → snapshot schema/ID → root-confined corpus +
chunk-set manifests with semantic ID recomputation → canonical chunk artifact
derivation → exact on-disk `artifact_bytes_hash` → provenance → chunk lookup.

Does **not** call `ProductPublicationRegistry.resolve_snapshot()` for task
evidence. Independent of current embedding/reranker/Qdrant/lexical readiness.

## Baseline A/B/C/D

Shared resolver used by discovery and campaign create.

- A absent → `gold_baseline_unknown` / 404
- B corrupt/identity → `gold_state_unavailable` / 409
- C stale CURRENT binding → `gold_conflict` / 409
- D pristine-ineligible (`baseline_human_state_present`,
  `baseline_identity_missing`) → preflight `gold_conflict` / 409
- post-preflight escape of D reasons → translator `gold_state_unavailable`

Discovery suppresses B/C/D.

## Error translator

`translate_gold_lab_error` maps the frozen exhaustive reason table (~169 reasons).
Unknown future reasons → `internal_error` + `gold_lab_unmapped_error`.
Never returns raw `GoldLabError` prose.

## Tests

Primary:

- `tests/unit/app/test_slice16f_d_gold_lab_api.py`
- `tests/unit/app/test_slice16f_d_gold_lab_historical_source.py`

Commands / results (local):

```text
uv run pytest tests/unit/app/test_slice16f_d_*.py
→ 14 passed

uv run pytest tests/unit/app/test_slice16f_a_gold_lab_foundation.py
→ 22 passed

uv run pytest tests/unit/app/test_slice16f_b_effective_state.py
→ 24 passed

uv run pytest tests/unit/app/test_slice16f_c_scientific_export.py
→ 20 passed

uv run pytest tests/unit/app/test_slice15b_runtime_health.py \
             tests/unit/app/test_slice16b_workspace_api.py
→ 20 passed
```

Ruff over 16F-D production/test files: PASS

`git diff --check`: PASS

## Explicit non-scope

No UI / React / games / workloads / 16G / 16H / 9G.
No retrieval/config/`base.yaml` promotion.
No GoldDataset-v1 / finalizer / ledger / contribution-weight semantic edits.
No ManagedOperation / 202 Gold responses.
No model/provider/embedding/reranker calls for Gold task detail.

Frozen design document was not semantically edited.
