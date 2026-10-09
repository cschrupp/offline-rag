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
| Documentation SHA fill | `36916216615981017013cb5e6e5ee822ade804b5` |
| Pre-Rework-1 tip | `ca5d605e21820d0a5cb53a0ddd8c7e7ebfffa701` |
| Rework 1 starting HEAD | `ca5d605e21820d0a5cb53a0ddd8c7e7ebfffa701` |
| Rework 1 implementation SHA | `09a25122311fc554504683f513e505e6a8891d88` |
| Rework 1 documentation SHA | `REWORK1_DOCUMENTATION_SHA_PENDING` |

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
   - Absent canonical **and** no existing `registrations/<dataset_id>/*.json` → atomic `os.replace`
   - Absent canonical **but** registrations already exist → `registered_dataset_missing` fail-closed (no silent repair)
   - Present same semantic `dataset_id` → reuse; delete candidate; do not rewrite bytes
   - Present but corrupt/wrong schema/identity → fail-closed; candidate cleaned; canonical untouched
   - Differing `meta.metadata.authoring_run_id` is not a conflict
4. No `--force`; no overwrite of occupied canonical path
5. Normal handled failures clean unpromoted `.candidate.<campaign_id>.*` staging

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
GoldLabProjectLease(captured_project_id) → GoldLabCampaignLease → GoldLabDatasetLease
```

Before lock acquisition, capture `campaign_probe.project_id`. After both project and campaign leases are held, re-read the campaign and require `campaign.project_id == captured_project_id`, then load the project by the captured id. Mismatch → fail-closed (`export_project_lock_mismatch`).

Export does **not** require campaign OPEN. Closed campaigns may export already-derived work. No ledger append; no reopen; no project status mutation.

## Rework 1 — Registration scientific-binding / fail-closed recovery

Hardening only (no redesign; no 16F-D entry):

- **Dataset ↔ registration ↔ campaign scientific binding:** authoritative validation requires loaded GoldDataset `source_schema`, `dataset_id`, `chunk_set_id`, `corpus_id`, and `corpus_name` to match the registration (which already matches campaign authority). Dataset-id equality alone is insufficient.
- **Project / selection-policy coherence:** `project.project_id == campaign.project_id` and `project.project_type == campaign.selection_policy.project_type`.
- **Baseline exported-case membership on read:** every `exported_case_ids` entry must exist in the sealed campaign baseline (`load_sealed_baseline_run`); enforced by the same validator used for create, replay, and contribution scans.
- **Strict `load_registration` path identity:** parsed `dataset_id` / `campaign_id` must equal the requested path identity.
- **No silent repair of missing registered dataset:** if `datasets/<D>/` is absent but `registrations/<D>/*.json` exists, promotion is refused (`registered_dataset_missing`).
- **Candidate cleanup:** unpromoted candidates are removed on lease-held, corrupt/reuse failure, and publication reject paths. Crash may still leave hidden staging (non-authoritative).
- **Crash-after-dataset recovery preserved:** dataset present + registration absent → retry reuses dataset and creates registration without rewrite.
- **Single authoritative validator:** `validate_registration_against_authority` is shared across first registration, exact replay, and contribution registration scans.

## Tests

`tests/unit/app/test_slice16f_c_scientific_export.py`

Coverage includes projection matrix, deterministic hash, GoldDataset-v1 positive-only export, dataset publish/reuse, registration-v1 idempotency, multi-campaign share, crash-after-dataset, sticky +15, closed-campaign export, nonscope, plus Rework 1 binding / baseline membership / path identity / missing-registered-dataset / candidate cleanup / project-lock identity.

## Regression

| Suite | Result |
|---|---|
| 16F-C `test_slice16f_c_scientific_export.py` | 20 PASS |
| 16F-B `test_slice16f_b_effective_state.py` | 24 PASS |
| 16F-A `test_slice16f_a_gold_lab_foundation.py` | 22 PASS |
| Slice-9E gold review (finalize-adjacent) | 34 PASS |
| Ruff (gold_lab + 16F-A/B/C tests) | PASS |
| `git diff --check` | PASS |
