"""Fail-closed GoldDataset finalization from reviewed silver runs (Slice 9E)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.evaluation.gold import (
    GOLD_SCHEMA_V1,
    ChunkJudgment,
    GoldCase,
    GoldDatasetMeta,
    compute_gold_dataset_id,
    load_gold_dataset,
)
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase
from offline_rag.gold_authoring.persist import (
    default_authoring_gold_dir,
    load_authoring_run,
)
from offline_rag.gold_authoring.review_models import HumanReviewStatus
from offline_rag.ingestion.io import atomic_publish_directory


class FinalizePreRunError(RuntimeError):
    """Fail-closed pre-run / validation error for gold finalize."""


@dataclass
class FinalizeResult:
    exit_code: int
    message: str | None = None
    output_path: Path | None = None
    dataset_id: str | None = None
    exported_case_ids: list[str] = field(default_factory=list)
    status_counts: dict[str, int] = field(default_factory=dict)


def _status_counts(run: GoldAuthoringRun) -> dict[str, int]:
    counts = {
        HumanReviewStatus.PENDING.value: 0,
        HumanReviewStatus.ACCEPTED.value: 0,
        HumanReviewStatus.EDITED.value: 0,
        HumanReviewStatus.REJECTED.value: 0,
    }
    for case in run.cases:
        counts[case.human_status.value] += 1
    return counts


def _silver_to_gold_case(case: SilverCase) -> GoldCase:
    query = case.effective_query()
    if query is None:
        raise FinalizePreRunError(
            f"approved case {case.draft_case_id} has no effective query"
        )
    positives: list[ChunkJudgment] = []
    for judgment in sorted(
        case.human_review.judgments if case.human_review else [],
        key=lambda item: item.chunk_id,
    ):
        if judgment.relevance >= 1:
            positives.append(
                ChunkJudgment(
                    chunk_id=judgment.chunk_id,
                    relevance=judgment.relevance,  # type: ignore[arg-type]
                )
            )
    if not positives:
        raise FinalizePreRunError(
            f"approved case {case.draft_case_id} has no positive human judgments"
        )
    return GoldCase(
        id=case.draft_case_id,
        query=query,
        category=case.effective_category(),
        tags=case.effective_tags(),
        judgments=tuple(positives),
    )


def _validate_selected(case: SilverCase) -> None:
    """Re-validate accepted/edited invariants independently of status trust."""
    status = case.human_status
    if status not in (HumanReviewStatus.ACCEPTED, HumanReviewStatus.EDITED):
        raise FinalizePreRunError(
            f"case {case.draft_case_id} is not an approved status"
        )
    # SilverCase model validation already enforces accepted/edited invariants
    # when the artifact loaded. Re-check explicit finalize requirements.
    if case.human_review is None:
        raise FinalizePreRunError(
            f"approved case {case.draft_case_id} missing human_review"
        )
    if not case.review_complete():
        raise FinalizePreRunError(
            f"approved case {case.draft_case_id} has incomplete human grade map"
        )
    if case.human_positive_count() < 1:
        raise FinalizePreRunError(
            f"approved case {case.draft_case_id} has no positive human grade"
        )
    if case.human_review.grade_basis_query != case.effective_query():
        raise FinalizePreRunError(
            f"approved case {case.draft_case_id} has stale query-grade binding"
        )
    changed = case.proposal_content_changed()
    if status == HumanReviewStatus.ACCEPTED and changed:
        raise FinalizePreRunError(
            f"accepted case {case.draft_case_id} has proposal metadata changes"
        )
    if status == HumanReviewStatus.EDITED and not changed:
        raise FinalizePreRunError(
            f"edited case {case.draft_case_id} has no proposal metadata changes"
        )


def build_gold_cases(run: GoldAuthoringRun) -> list[GoldCase]:
    selected: list[SilverCase] = []
    for case in run.cases:
        if case.human_status in (
            HumanReviewStatus.ACCEPTED,
            HumanReviewStatus.EDITED,
        ):
            selected.append(case)

    if not selected:
        raise FinalizePreRunError(
            "no accepted or edited cases to finalize "
            "(pending/rejected only)"
        )

    gold_cases: list[GoldCase] = []
    seen_ids: set[str] = set()
    for case in selected:
        try:
            _validate_selected(case)
            gold_case = _silver_to_gold_case(case)
        except FinalizePreRunError:
            raise
        except Exception as exc:
            raise FinalizePreRunError(
                f"approved case {case.draft_case_id} failed validation: {exc}"
            ) from exc
        if gold_case.id in seen_ids:
            raise FinalizePreRunError(f"duplicate draft_case_id: {gold_case.id}")
        seen_ids.add(gold_case.id)
        gold_cases.append(gold_case)
    return gold_cases


def resolve_finalize_destination(
    settings: AppSettings,
    run: GoldAuthoringRun,
    *,
    output: Path | None,
) -> Path:
    if output is not None:
        return output
    corpus_name = (run.corpus_name or "").strip()
    if not corpus_name:
        raise FinalizePreRunError(
            "run.corpus_name is required to resolve the default gold destination"
        )
    return default_authoring_gold_dir(
        settings,
        corpus_name=corpus_name,
        authoring_run_id=run.authoring_run_id,
    )


def run_gold_finalize(
    settings: AppSettings,
    *,
    run_path: Path,
    output: Path | None = None,
    force: bool = False,
) -> FinalizeResult:
    path = run_path.resolve()
    if not path.exists():
        raise FinalizePreRunError(f"authoring run not found: {path}")

    try:
        run = load_authoring_run(path)
    except Exception as exc:
        raise FinalizePreRunError(f"failed to load authoring run: {exc}") from exc

    status_counts = _status_counts(run)

    chunk_set_id = (run.chunk_set_id or "").strip()
    if not chunk_set_id:
        raise FinalizePreRunError("run.chunk_set_id is required and must be non-blank")

    destination = resolve_finalize_destination(settings, run, output=output)
    if destination.exists() and not force:
        raise FinalizePreRunError(
            f"destination already exists (pass --force to overwrite): {destination}"
        )

    gold_cases = build_gold_cases(run)
    dataset_id = compute_gold_dataset_id(
        chunk_set_id=chunk_set_id,
        corpus_id=run.corpus_id,
        corpus_name=run.corpus_name,
        cases=gold_cases,
    )
    meta = GoldDatasetMeta(
        schema_version=GOLD_SCHEMA_V1,
        chunk_set_id=chunk_set_id,
        corpus_id=run.corpus_id,
        corpus_name=run.corpus_name,
        dataset_id=dataset_id,
        metadata={"authoring_run_id": run.authoring_run_id},
    )

    cases_lines: list[str] = []
    for case in gold_cases:
        payload = {
            "id": case.id,
            "query": case.query,
            "category": case.category,
            "tags": list(case.tags),
            "judgments": [
                {"chunk_id": j.chunk_id, "relevance": int(j.relevance)}
                for j in case.judgments
            ],
        }
        cases_lines.append(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    cases_text = "\n".join(cases_lines) + ("\n" if cases_lines else "")
    meta_text = meta.model_dump_json(indent=2) + "\n"

    def _validate_temp_dataset(temp_dir: Path) -> None:
        try:
            loaded = load_gold_dataset(temp_dir)
        except Exception as exc:
            raise FinalizePreRunError(
                f"GoldDataset failed validation before publication: {exc}"
            ) from exc
        if loaded.dataset_id != dataset_id:
            raise FinalizePreRunError(
                "GoldDataset dataset_id mismatch before publication"
            )

    atomic_publish_directory(
        destination,
        {
            "meta.json": meta_text,
            "cases.jsonl": cases_text,
        },
        validate=_validate_temp_dataset,
    )

    return FinalizeResult(
        exit_code=0,
        message="GoldDataset finalization completed.",
        output_path=destination,
        dataset_id=dataset_id,
        exported_case_ids=[c.id for c in gold_cases],
        status_counts=status_counts,
    )
