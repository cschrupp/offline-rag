"""Pristine baseline admission and historical identity validation (16F-A)."""

from __future__ import annotations

import hashlib

from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import (
    absolute_relevance_task_id,
    auxiliary_preference_task_id,
    question_check_task_id,
)
from offline_rag.app.gold_lab.paths import baseline_authoring_run_path
from offline_rag.app.gold_lab.reviewable import is_reviewable_case
from offline_rag.chunking.access import ChunkAccessError, load_chunk_set_snapshot
from offline_rag.config.models import AppSettings
from offline_rag.gold_authoring.contracts import AUTHORING_ARTIFACT_CONTRACT
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase
from offline_rag.gold_authoring.review_models import HumanReviewStatus


def _nonblank(value: str | None, *, field: str) -> str:
    if value is None or not str(value).strip():
        raise GoldLabError(
            "baseline_identity_missing",
            f"baseline missing required nonblank field: {field}",
        )
    return str(value).strip()


def assert_pristine_baseline(run: GoldAuthoringRun) -> None:
    """Fail closed when baseline carries substantive human-review state."""
    if run.schema_version != AUTHORING_ARTIFACT_CONTRACT:
        raise GoldLabError(
            "baseline_schema_invalid",
            f"expected {AUTHORING_ARTIFACT_CONTRACT}",
        )
    _nonblank(run.corpus_name, field="corpus_name")
    _nonblank(run.corpus_id, field="corpus_id")
    _nonblank(run.chunk_set_id, field="chunk_set_id")

    for case in run.cases:
        _assert_case_pristine(case)


def _assert_case_pristine(case: SilverCase) -> None:
    review = case.human_review
    if review is None:
        return
    if review.status is not HumanReviewStatus.PENDING:
        raise GoldLabError(
            "baseline_human_state_present",
            f"case {case.draft_case_id} has non-pending human status",
        )
    if review.judgments:
        raise GoldLabError(
            "baseline_human_state_present",
            f"case {case.draft_case_id} has human judgments",
        )
    if review.query_override is not None:
        raise GoldLabError(
            "baseline_human_state_present",
            f"case {case.draft_case_id} has query_override",
        )
    if review.category_override.is_overridden or review.category_override.value is not None:
        raise GoldLabError(
            "baseline_human_state_present",
            f"case {case.draft_case_id} has category_override",
        )
    if review.tags_override is not None:
        raise GoldLabError(
            "baseline_human_state_present",
            f"case {case.draft_case_id} has tags_override",
        )
    if review.grade_basis_query is not None:
        raise GoldLabError(
            "baseline_human_state_present",
            f"case {case.draft_case_id} has grade_basis_query",
        )


def validate_historical_chunk_identities(
    settings: AppSettings,
    run: GoldAuthoringRun,
    *,
    corpus_name: str,
    corpus_id: str,
    chunk_set_id: str,
    corpus_manifest_name: str,
) -> dict[str, str]:
    """Resolve every candidate/source_seed against the bound historical chunk set.

    Returns mapping chunk_id -> document_id for resolved chunks.
    """
    try:
        snapshot = load_chunk_set_snapshot(
            settings,
            corpus_name=corpus_name,
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            corpus_manifest_name=corpus_manifest_name,
        )
    except ChunkAccessError as exc:
        raise GoldLabError(
            "chunk_set_unavailable",
            str(exc),
        ) from exc

    by_id = {chunk.chunk_id: chunk for chunk in snapshot.chunks}

    for case in run.cases:
        for candidate in case.candidates:
            chunk = by_id.get(candidate.chunk_id)
            if chunk is None:
                raise GoldLabError(
                    "candidate_chunk_unresolved",
                    f"candidate {candidate.chunk_id} missing from {chunk_set_id}",
                )
        seed = case.source_seed
        if seed is None:
            continue
        chunk = by_id.get(seed.chunk_id)
        if chunk is None:
            raise GoldLabError(
                "source_seed_chunk_unresolved",
                f"source_seed {seed.chunk_id} missing from {chunk_set_id}",
            )
        if seed.document_id is not None and seed.document_id != chunk.document_id:
            raise GoldLabError(
                "source_seed_document_mismatch",
                f"source_seed document_id mismatch for {seed.chunk_id}",
            )

    return {chunk_id: chunk.document_id for chunk_id, chunk in by_id.items()}


def validate_hard_call_targets(
    *,
    campaign_id: str,
    run: GoldAuthoringRun,
    target_task_ids: list[str],
) -> None:
    """Ensure each Hard Call target is a valid absolute_relevance task id."""
    valid: set[str] = set()
    for case in run.cases:
        if not is_reviewable_case(case):
            continue
        for candidate in case.candidates:
            valid.add(
                absolute_relevance_task_id(
                    campaign_id=campaign_id,
                    case_id=case.draft_case_id,
                    candidate_chunk_id=candidate.chunk_id,
                )
            )
    for task_id in target_task_ids:
        if task_id not in valid:
            raise GoldLabError(
                "hard_call_target_invalid",
                f"Hard Call target is not a reviewable absolute task: {task_id}",
            )


def load_sealed_baseline_run(
    settings: AppSettings,
    *,
    campaign_id: str,
    baseline_authoring_run_id: str,
    baseline_sha256: str,
) -> GoldAuthoringRun:
    """Load and verify the immutable baseline sealed into a campaign package."""
    path = baseline_authoring_run_path(settings, campaign_id)
    if not path.is_file():
        raise GoldLabError(
            "baseline_missing",
            f"sealed baseline missing for campaign: {campaign_id}",
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GoldLabError(
            "baseline_unreadable",
            f"sealed baseline unreadable for campaign: {campaign_id}",
        ) from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != baseline_sha256:
        raise GoldLabError(
            "baseline_hash_mismatch",
            "sealed baseline bytes do not match campaign.baseline_sha256",
        )
    try:
        run = GoldAuthoringRun.model_validate_json(raw.decode("utf-8"))
    except Exception as exc:
        raise GoldLabError(
            "baseline_corrupt",
            f"sealed baseline corrupt for campaign: {campaign_id}",
        ) from exc
    if run.authoring_run_id != baseline_authoring_run_id:
        raise GoldLabError(
            "baseline_authoring_run_id_mismatch",
            "sealed baseline authoring_run_id does not match campaign",
        )
    return run


def resolve_ledger_task_id(
    *,
    campaign_id: str,
    record_type: str,
    case_id: str,
    baseline: GoldAuthoringRun,
    candidate_chunk_id: str | None = None,
    preferred_chunk_id: str | None = None,
    other_chunk_id: str | None = None,
) -> str:
    """Validate case/task membership against the sealed baseline candidate pools."""
    cases = {case.draft_case_id: case for case in baseline.cases}
    case = cases.get(case_id)
    if case is None:
        raise GoldLabError(
            "ledger_case_not_found",
            f"case_id not present in sealed baseline: {case_id}",
        )
    if not is_reviewable_case(case):
        raise GoldLabError(
            "ledger_case_not_reviewable",
            f"case is not reviewable for ledger append: {case_id}",
        )
    candidate_ids = {c.chunk_id for c in case.candidates}

    if record_type == "question_check":
        return question_check_task_id(campaign_id=campaign_id, case_id=case_id)

    if record_type == "absolute_relevance":
        if not candidate_chunk_id:
            raise GoldLabError(
                "candidate_chunk_required",
                "absolute_relevance requires candidate_chunk_id",
            )
        if candidate_chunk_id not in candidate_ids:
            raise GoldLabError(
                "ledger_candidate_not_in_case",
                f"candidate {candidate_chunk_id} not in case {case_id} pool",
            )
        return absolute_relevance_task_id(
            campaign_id=campaign_id,
            case_id=case_id,
            candidate_chunk_id=candidate_chunk_id,
        )

    if record_type == "auxiliary_preference":
        if not isinstance(preferred_chunk_id, str) or not isinstance(other_chunk_id, str):
            raise GoldLabError(
                "auxiliary_pair_required",
                "auxiliary_preference requires preferred/other chunk ids",
            )
        if preferred_chunk_id not in candidate_ids or other_chunk_id not in candidate_ids:
            raise GoldLabError(
                "ledger_candidate_not_in_case",
                f"auxiliary pair not in case {case_id} pool",
            )
        return auxiliary_preference_task_id(
            campaign_id=campaign_id,
            case_id=case_id,
            candidate_a=preferred_chunk_id,
            candidate_b=other_chunk_id,
        )

    raise GoldLabError(
        "ledger_record_type_invalid",
        f"unsupported ledger record_type: {record_type}",
    )
