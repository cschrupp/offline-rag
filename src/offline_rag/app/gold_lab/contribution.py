"""gold-contribution-v1 deterministic scoring projection (16F-B)."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from offline_rag.app.gold_lab.effective_state import EffectiveCampaignState
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import (
    CONTRIBUTION_CONTRACT,
    absolute_relevance_task_id,
)
from offline_rag.app.gold_lab.models import HardCallsArtifact, QuestionCheckDecision
from offline_rag.app.gold_lab.reviewable import is_reviewable_case
from offline_rag.app.gold_lab.tasks import TaskKind, TaskState, project_tasks


@dataclass(frozen=True)
class ContributionProjection:
    contract: str
    campaign_id: str
    total_score: int
    expert_judgments: int
    questions_reviewed: int
    cases_completed: int
    gold_finalized: int
    hard_calls_resolved: int
    completed_active_absolute_tasks: int
    total_active_absolute_tasks: int
    coverage_fraction: float | None
    total_question_tasks: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "campaign_id": self.campaign_id,
            "total_score": self.total_score,
            "expert_judgments": self.expert_judgments,
            "questions_reviewed": self.questions_reviewed,
            "cases_completed": self.cases_completed,
            "gold_finalized": self.gold_finalized,
            "hard_calls_resolved": self.hard_calls_resolved,
            "completed_active_absolute_tasks": self.completed_active_absolute_tasks,
            "total_active_absolute_tasks": self.total_active_absolute_tasks,
            "coverage_fraction": self.coverage_fraction,
            "total_question_tasks": self.total_question_tasks,
        }


def project_contribution(
    state: EffectiveCampaignState,
    *,
    hard_calls: HardCallsArtifact,
    finalized_case_ids: Collection[str] = (),
) -> ContributionProjection:
    """Pure deterministic contribution projector.

    Live 16F-B application code MUST pass an empty ``finalized_case_ids``.
    Unit tests may inject baseline case IDs to verify +15 sticky semantics.
    """
    if hard_calls.campaign_id != state.campaign_id:
        raise GoldLabError(
            "hard_calls_campaign_mismatch",
            "hard_calls.json campaign_id mismatch",
        )

    baseline_case_ids = {c.draft_case_id for c in state.baseline.cases}
    finalized_unique: list[str] = []
    seen_finalized: set[str] = set()
    for case_id in finalized_case_ids:
        if case_id not in baseline_case_ids:
            raise GoldLabError(
                "contribution_unknown_finalized_case",
                f"finalized case_id not in baseline: {case_id}",
            )
        if case_id in seen_finalized:
            continue
        seen_finalized.add(case_id)
        finalized_unique.append(case_id)

    tasks = project_tasks(state)
    question_tasks = [t for t in tasks if t.task_kind is TaskKind.QUESTION_CHECK]
    absolute_tasks = [t for t in tasks if t.task_kind is TaskKind.ABSOLUTE_RELEVANCE]
    active_absolute = [t for t in absolute_tasks if t.active]
    completed_active = [
        t for t in active_absolute if t.state is TaskState.COMPLETED
    ]

    expert_judgments = len(completed_active)
    questions_reviewed = sum(
        1 for t in question_tasks if t.state is TaskState.COMPLETED
    )
    total_question_tasks = len(question_tasks)
    total_active_absolute_tasks = len(active_absolute)
    completed_active_absolute_tasks = len(completed_active)

    cases_completed = 0
    for case in state.baseline.cases:
        if not is_reviewable_case(case):
            continue
        qc = state.current_question_for_case(case.draft_case_id)
        if qc is None or qc.decision is QuestionCheckDecision.REJECT:
            continue
        case_abs = [
            t
            for t in active_absolute
            if t.case_id == case.draft_case_id
        ]
        if not case_abs:
            continue
        if all(t.state is TaskState.COMPLETED for t in case_abs):
            cases_completed += 1

    gold_finalized = len(finalized_unique)

    # Hard Call: one bonus per designation when target task has current effective judgment
    hard_calls_resolved = 0
    baseline_absolute_tasks: set[str] = set()
    for case in state.baseline.cases:
        if not is_reviewable_case(case):
            continue
        for candidate in case.candidates:
            baseline_absolute_tasks.add(
                absolute_relevance_task_id(
                    campaign_id=state.campaign_id,
                    case_id=case.draft_case_id,
                    candidate_chunk_id=candidate.chunk_id,
                )
            )
    for designation in hard_calls.designations:
        if designation.target_task_id not in baseline_absolute_tasks:
            raise GoldLabError(
                "hard_call_target_unknown",
                f"Hard Call target not in baseline: {designation.target_task_id}",
            )
        current = state.absolute_current_by_task.get(designation.target_task_id)
        if current is not None:
            hard_calls_resolved += 1

    if total_active_absolute_tasks > 0:
        coverage_fraction = (
            completed_active_absolute_tasks / total_active_absolute_tasks
        )
    else:
        coverage_fraction = None

    total_score = (
        expert_judgments * 1
        + questions_reviewed * 5
        + cases_completed * 10
        + gold_finalized * 15
        + hard_calls_resolved * 5
    )

    return ContributionProjection(
        contract=CONTRIBUTION_CONTRACT,
        campaign_id=state.campaign_id,
        total_score=total_score,
        expert_judgments=expert_judgments,
        questions_reviewed=questions_reviewed,
        cases_completed=cases_completed,
        gold_finalized=gold_finalized,
        hard_calls_resolved=hard_calls_resolved,
        completed_active_absolute_tasks=completed_active_absolute_tasks,
        total_active_absolute_tasks=total_active_absolute_tasks,
        coverage_fraction=coverage_fraction,
        total_question_tasks=total_question_tasks,
    )
