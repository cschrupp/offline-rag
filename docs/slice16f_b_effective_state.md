# Slice 16F-B — Gold Lab Effective State / Tasks / Scoring

## Authority

| Item | Value |
|---|---|
| Frozen 16F design authority | `4fde40da2458d69f9249b8334210fc84e9f3239c` |
| Accepted 16F-A authority | `2e4d51b06763ed04bce8b6e2d60337f61082bc64` |
| Branch | `implementation/16f-b-effective-state` |
| Starting HEAD | `2e4d51b06763ed04bce8b6e2d60337f61082bc64` |
| Implementation SHA | `10520c1625f63e347116055124c181df3a446df1` |
| Documentation SHA | `65e86ead38794a93a3961db6640fcaaf616e8fc7` |
| Rework 1 starting HEAD | `d6da49309f863955f65148d166dab8b770284c34` |
| Rework 1 implementation SHA | `5416d536d7aff641ce81348a46ba2e750e710871` |
| Rework 1 documentation SHA | `60b5c795df76fa0ab5d2d9b95b67b0e576794ae9` |
| Rework 2 starting HEAD | `5b0fca3b675debf3b96b4b595a2cec0640b83327` |
| Rework 2 implementation SHA | `f2118986e40e2058a89c3053b8456eaa69271eca` |
| Rework 2 documentation SHA | `_FILL_AFTER_DOCS_COMMIT_` |

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

## Rework 1 — Idempotency / lifecycle / audit-canonicality closure

Hardening only (no redesign; no 16F-C entry):

- **Effective-state gate before PENDING reservation:** for a new key, build and validate the complete append intent (including absolute QC-active / same-basis supersedes resolution) before writing the idempotency catalog PENDING entry. Invalid/inactive commands leave no reservation and no ledger row.
- **Genuine PENDING recovery preserved:** PENDING+no ledger revalidates lifecycle/effective-state and resumes with the same reserved IDs; PENDING+matching ledger finalizes COMMITTED without duplicate append.
- **Duplicate durable idempotency keys fail closed** on every supported path: committed replay, pending recovery, new-key mutation, `load_effective_state` / task projection / contribution.
- **Catalog command-kind integrity:** `command_kind` is exactly `question_check` | `absolute_relevance` | `auxiliary_preference`; must match invoked command and reserved ledger `record_type`.
- **Project-archive commit serialization:** supported mutations hold `GoldLabProjectLease` then `GoldLabCampaignLease` through lookup → lifecycle → fold → PENDING → append → COMMITTED. Replay of exact COMMITTED requests still succeeds after archive/close; new/uncommitted keys are rejected.
- **Exact durable Question Check replay shape:** accept/reject payloads must be exactly `{decision}`; edit must contain exactly the four canonical keys with already-canonical values (no whitespace/unsorted tags accepted on fold). Shared helpers: command-input canonicalize vs ledger-replay validate-already-canonical.

## Rework 2 — Complete pre-reservation command validation

Narrow closure so PENDING means interrupted valid commit, never deterministic caller error:

- **Complete deterministic command preflight before PENDING:** all supported-command shape/type/domain failures (including optional provenance) occur before request fingerprint commit identity is durable-reserved.
- **Strict `str | null` optional provenance:** `game_id` and `presentation_id` accept only Python `str` or `None` (no coercion of int/bool/list/dict/bytes/etc.).
- **Invalid supported command leaves no crash-recovery reservation:** no idempotency catalog entry and no ledger row; a later retry with the same key and valid inputs is treated as a fresh request.

## Modules

Primary package: `src/offline_rag/app/gold_lab/`

| Module | Role |
|---|---|
| `effective_state.py` | Fail-closed fold; QC + absolute supersession / event-time audit; duplicate-key check |
| `tasks.py` | Task pending/completed/active projection; blind DTO |
| `idempotency.py` | Campaign-local `offline-rag-gold-idempotency-v1` catalog |
| `mutations.py` | `GoldLabMutationService` under project+campaign leases |
| `contribution.py` | Pure `gold-contribution-v1` projector |
| `question_check.py` | QC command canonicalize + durable replay validator |
| `ledger.py` | `append_under_lease` (held lease; no second lock) |
| `models.py` | `QuestionCheckPayload`, `IdempotencyEntry`, `IdempotencyCommandKind` |
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
- New-key PENDING write occurs only after validated append intent

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
