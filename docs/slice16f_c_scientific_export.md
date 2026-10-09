# Slice 16F-C — Gold Lab Scientific Projection / Export / Registration

## Authority

| Item | Value |
|---|---|
| Frozen 16F design authority | `4fde40da2458d69f9249b8334210fc84e9f3239c` |
| Accepted 16F-A authority | `2e4d51b06763ed04bce8b6e2d60337f61082bc64` |
| Accepted 16F-B authority | `f4fe892044f8443594d7629e5b49a3d9f39b6297` |
| Branch | `implementation/16f-c-scientific-export` |
| Starting HEAD | `f4fe892044f8443594d7629e5b49a3d9f39b6297` |
| Implementation SHA | `3b802a5d066370af5ab696e8e0529d865a612002` |
| Documentation SHA | `1c902f52a604348b9da82e43e99fff00f611e72c` |

## Scope

16F-C implements only:

- Deterministic effective-state → `GoldAuthoringRun` projection (existing Slice-9 models)
- Preservation of 0/1/2 expert grades in projected `HumanReview`
- Existing `offline-rag-gold-v1` finalization via `run_gold_finalize(..., force=False)`
- Positive-only 1/2 GoldDataset output
- Derived projection artifact + `projection_sha256`
- Immutable canonical dataset storage + semantic-equivalent reuse
- Immutable campaign registration (`offline-rag-gold-registration-v1`)
- Idempotent re-registration and multi-campaign shared dataset
- Registration-backed Gold-finalized contribution (+15 sticky)

## Explicit non-scope

- HTTP/API, UI, 16F-D, 16G–16H games
- Retrieval/config promotion, `config/base.yaml`
- New Gold scientific schema / relevance scale
- Automatic training/fine-tuning, 9G
- Ledger append / adjudication mutations during export
- M7 pinned evidence revision

## Modules

Primary package: `src/offline_rag/app/gold_lab/`

| Module | Role |
|---|---|
| `projection.py` | Pure `project_authoring_run` + frozen `projection_text` |
| `datasets.py` | Candidate finalize + canonical publish/reuse |
| `registrations.py` | `GoldRegistration` persistence + contribution union |
| `scientific_export.py` | `GoldLabScientificExportService.export_and_register` |
| `leases.py` | `GoldLabDatasetLease` (project → campaign → dataset order) |
| `models.py` | `GoldRegistration` |
| `ids.py` / `paths.py` | `validate_dataset_id`, dataset/registration/projection paths |
| `mutations.py` | Contribution reads `valid_registered_case_ids_for_campaign` |

## Projection mapping

Authority = sealed baseline + folded 16F-B effective state (not raw ledger counting).

| Baseline case | Question Check | Grades | Projected `HumanReview.status` |
|---|---|---|---|
| Non-reviewable | n/a | pristine baseline | PENDING/pristine (unchanged) |
| Reviewable | none | none | PENDING |
| Reviewable | reject | none (history only) | REJECTED |
| Reviewable | accept | incomplete / all-zero | PENDING |
| Reviewable | accept | complete + ≥1 positive | ACCEPTED |
| Reviewable | edit | incomplete / all-zero / no content change | PENDING |
| Reviewable | edit | complete + ≥1 positive + content change | EDITED |

Rules:

- Current judgments only under current query fingerprint; sorted by `chunk_id`
- Full 0/1/2 map retained in projection; model/advisory grades never imported
- `grade_basis_query` = exact effective query when judgments nonempty
- All baseline cases preserved in baseline order; baseline file never mutated

## Projection serialization / hash

```
projection_text = projected_run.model_dump_json() + "\n"
projection_sha256 = SHA-256 hex of exact UTF-8 bytes written to
  campaigns/<campaign_id>/projection/authoring_run.json
```

Derived/rebuildable cache. Not a scientific dataset identity.

## Dataset publication / reuse

1. Finalize projection into `datasets/.candidate.<campaign_id>.<uuid>/` via existing `run_gold_finalize`
2. `load_gold_dataset` + `dataset_id` grammar `^gold_[0-9a-f]{64}$`
3. Under `GoldLabDatasetLease`:
   - Absent canonical → atomic `os.replace` to `datasets/<dataset_id>/`
   - Present same semantic `dataset_id` → reuse; delete candidate; do not rewrite bytes
   - Differing `meta.metadata.authoring_run_id` is not a conflict
4. No `--force`; no overwrite of occupied canonical path

## Registration schema / path

Schema: `offline-rag-gold-registration-v1`

Path: `registrations/<dataset_id>/<campaign_id>.json`

`dataset_path` = relative `datasets/<dataset_id>` (never absolute machine paths).

Provenance derived from campaign/project/projection/loaded dataset — caller supplies only `campaign_id`.

Idempotent retry: identical immutable fields → return existing; preserve `registered_at`; do not rewrite bytes. Conflict → fail closed.

## Multi-campaign reuse

Two campaigns may resolve to the same `dataset_id`:

- One canonical shared dataset directory (first publisher bytes retained)
- Distinct `registrations/<D>/<A>.json` and `registrations/<D>/<B>.json`
- Each registration keeps own `baseline_sha256` / `projection_sha256` / workspace provenance

## Crash recovery

| Crash point | Outcome |
|---|---|
| Before canonical publish | No registration; candidate may be leftover staging |
| After publish, before registration | Canonical dataset may exist unregistered; retry reuses + registers |
| During atomic registration write | No partially valid registration |

## Registration-backed contribution

`valid_registered_case_ids_for_campaign` = unique union of `exported_case_ids` across all **valid** immutable registrations for that campaign.

`GoldLabMutationService.contribution` passes that union into `project_contribution(..., finalized_case_ids=...)`.

- +15 once per baseline case appearing in ≥1 valid registration
- Sticky: later reject/correction does not erase Gold-finalized
- Malformed/mismatched authoritative registration → fail closed (no silent skip)

## Locks

```
GoldLabProjectLease → GoldLabCampaignLease → GoldLabDatasetLease
```

Export does **not** require campaign OPEN. Closed campaigns may export already-derived work. No ledger append; no reopen; no project status mutation.

## Tests

`tests/unit/app/test_slice16f_c_scientific_export.py`

Coverage includes projection matrix, deterministic hash, GoldDataset-v1 positive-only export, dataset publish/reuse, registration-v1 idempotency, multi-campaign share, crash-after-dataset, sticky +15, closed-campaign export, nonscope.

## Regression

| Suite | Result |
|---|---|
| 16F-C | PASS |
| 16F-B `test_slice16f_b_effective_state.py` | 24 PASS |
| 16F-A `test_slice16f_a_gold_lab_foundation.py` | 22 PASS |
| Slice-9E gold review (finalize-adjacent) | PASS |
| Ruff (gold_lab + 16F-A/B/C tests) | PASS |
| `git diff --check` | PASS |
