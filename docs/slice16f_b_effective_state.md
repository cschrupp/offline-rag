# Slice 16F-B — Gold Lab Effective State / Tasks / Scoring

## Authority

| Item | Value |
|---|---|
| Frozen 16F design authority | `4fde40da2458d69f9249b8334210fc84e9f3239c` |
| Accepted 16F-A authority | `2e4d51b06763ed04bce8b6e2d60337f61082bc64` |
| Branch | `implementation/16f-b-effective-state` |
| Starting HEAD | `2e4d51b06763ed04bce8b6e2d60337f61082bc64` |
| Implementation SHA | `10520c1625f63e347116055124c181df3a446df1` |
| Documentation SHA | `_FILL_AFTER_DOCS_COMMIT_` |

## Scope

16F-B implements only:

- Deterministic effective-state fold over immutable baseline + append-only ledger
- Question Check durable semantics (`accept` / `edit` / `reject`)
- Question / absolute task activation and pending/completed projection
- Durable idempotent `GoldLabMutationService` (internal; no HTTP)
- Exact canonical request fingerprints via existing `canonical_request_fingerprint`
- Lifecycle gates after idempotency replay resolution
- Append-only correction / supersession + query-basis invalidation
- Current effective canonical absolute judgments
- `gold-contribution-v1` score/counters, Hard Call resolution scoring, zero-denominator coverage
- Safe pre-commit blind task projection (no model/retrieval leakage)

## Modules

Primary package: `src/offline_rag/app/gold_lab/`

| Module | Role |
|---|---|
| `effective_state.py` | Fail-closed fold; QC + absolute supersession / event-time audit |
| `tasks.py` | Task pending/completed/active projection; blind DTO |
| `idempotency.py` | Campaign-local `offline-rag-gold-idempotency-v1` catalog |
| `mutations.py` | `GoldLabMutationService` commands under campaign lease |
| `contribution.py` | Pure `gold-contribution-v1` projector |
| `question_check.py` | QC payload canonicalize / fingerprint helpers |
| `ledger.py` | `append_under_lease` (held lease; no second lock) |
| `models.py` | `QuestionCheckPayload`, `IdempotencyEntry` |
| `paths.py` | `idempotency/` path helpers |
| `ids.py` | `IDEMPOTENCY_SCHEMA`, `CONTRIBUTION_CONTRACT` |

## Supported internal mutation commands

- `submit_question_check(...)`
- `submit_absolute_relevance(...)`
- `submit_auxiliary_preference(...)`

Service owns: `task_id`, `query_fingerprint`, `supersedes_judgment_id`, `record_id`, `judgment_id`, sequence.

Caller supplies: scientific decision, idempotency key, optional game/presentation provenance.

## Idempotency catalog

- Contract: `offline-rag-gold-idempotency-v1`
- Path: `campaigns/<campaign_id>/idempotency/idem_<sha256(UTF-8 normalized key)>.json`
- Status: `pending` → `committed`
- Replay-first ordering; conflict beats lifecycle; crash recovery for PENDING+ledger and PENDING-only

## Effective-state / tasks (summary)

- QC fold per stable task; corrections append-only and must supersede current
- Absolute chains scoped by `task_id + query_fingerprint`
- Absolute event-time validity: QC accept/edit active and fingerprint match at ledger sequence
- Query change leaves old absolute historical; new basis starts with `supersedes=null`
- Metadata-only QC edit (same query) keeps matching absolute judgments effective
- REVIEWABLE only: one QC task (always active); one absolute task per candidate
- Absolute inactive before accept/edit and after reject

## Contribution-v1

Weights: judgments×1 + questions×5 + cases×10 + gold_finalized×15 + hard_calls×5.

Live application service always passes empty `finalized_case_ids` → `gold_finalized = 0` until 16F-C.

Coverage: `null` when `total_active_absolute_tasks == 0` (never fabricate 0.0/1.0 for 0/0).

## Tests / validation

- `tests/unit/app/test_slice16f_b_effective_state.py`
- 16F-A regression: `tests/unit/app/test_slice16f_a_gold_lab_foundation.py`
- `uv run ruff check` on gold_lab + both test files
- `git diff --check`

## Non-scope (explicit)

- HumanReview / `projection/authoring_run.json` materialization
- GoldDataset export / registration / datasets storage
- HTTP / FastAPI / UI / games
- 16F-C / 16F-D / 16G–16H / 9G
- Scientific contract changes (`evaluation/gold.py`, gold_authoring finalize)
- GoldDataset-v1 / M7 pinned evidence edits
