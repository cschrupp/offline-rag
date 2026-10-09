"""Deterministic task projection and blind pre-commit views (16F-B)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from offline_rag.app.gold_lab.effective_state import EffectiveCampaignState
from offline_rag.app.gold_lab.ids import (
    absolute_relevance_task_id,
    question_check_task_id,
)
from offline_rag.app.gold_lab.models import QuestionCheckDecision
from offline_rag.app.gold_lab.reviewable import is_reviewable_case


class TaskKind(StrEnum):
    QUESTION_CHECK = "question_check"
    ABSOLUTE_RELEVANCE = "absolute_relevance"


class TaskState(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


@dataclass(frozen=True)
class ProjectedTask:
    task_id: str
    task_kind: TaskKind
    campaign_id: str
    case_id: str
    active: bool
    state: TaskState
    candidate_chunk_id: str | None = None


@dataclass(frozen=True)
class BlindTaskView:
    """Safe pre-commit task DTO — no retrieval/model/Hard Call leakage."""

    task_id: str
    task_kind: str
    campaign_id: str
    case_id: str
    active: bool
    state: str
    candidate_chunk_id: str | None = None
    effective_query: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_kind": self.task_kind,
            "campaign_id": self.campaign_id,
            "case_id": self.case_id,
            "active": self.active,
            "state": self.state,
            "candidate_chunk_id": self.candidate_chunk_id,
            "effective_query": self.effective_query,
        }


_FORBIDDEN_BLIND_KEYS = frozenset(
    {
        "retrieval_hits",
        "rank",
        "score",
        "model_judgments",
        "prelabel_summary",
        "prelabel_provenance",
        "reason_code",
        "model_confidence",
        "model_agreement",
        "confidence",
        "agreement",
        "hard_call_reason_code",
        "retrieval_method",
        "retrieval_rank",
        "retrieval_score",
    }
)


def project_tasks(state: EffectiveCampaignState) -> list[ProjectedTask]:
    """Deterministic task list for REVIEWABLE cases only."""
    tasks: list[ProjectedTask] = []
    for case in state.baseline.cases:
        if not is_reviewable_case(case):
            continue
        case_id = case.draft_case_id
        qc_task_id = question_check_task_id(
            campaign_id=state.campaign_id, case_id=case_id
        )
        qc = state.question_by_task.get(qc_task_id)
        qc_completed = qc is not None
        tasks.append(
            ProjectedTask(
                task_id=qc_task_id,
                task_kind=TaskKind.QUESTION_CHECK,
                campaign_id=state.campaign_id,
                case_id=case_id,
                active=True,
                state=TaskState.COMPLETED if qc_completed else TaskState.PENDING,
            )
        )

        qc_accept_edit = (
            qc is not None and qc.decision is not QuestionCheckDecision.REJECT
        )
        current_fp = qc.query_fingerprint if qc_accept_edit else None

        for candidate in case.candidates:
            abs_task_id = absolute_relevance_task_id(
                campaign_id=state.campaign_id,
                case_id=case_id,
                candidate_chunk_id=candidate.chunk_id,
            )
            if not qc_accept_edit or current_fp is None:
                tasks.append(
                    ProjectedTask(
                        task_id=abs_task_id,
                        task_kind=TaskKind.ABSOLUTE_RELEVANCE,
                        campaign_id=state.campaign_id,
                        case_id=case_id,
                        active=False,
                        state=TaskState.PENDING,
                        candidate_chunk_id=candidate.chunk_id,
                    )
                )
                continue
            current_abs = state.absolute_by_basis.get((abs_task_id, current_fp))
            tasks.append(
                ProjectedTask(
                    task_id=abs_task_id,
                    task_kind=TaskKind.ABSOLUTE_RELEVANCE,
                    campaign_id=state.campaign_id,
                    case_id=case_id,
                    active=True,
                    state=(
                        TaskState.COMPLETED
                        if current_abs is not None
                        else TaskState.PENDING
                    ),
                    candidate_chunk_id=candidate.chunk_id,
                )
            )
    return tasks


def blind_task_views(state: EffectiveCampaignState) -> list[BlindTaskView]:
    """Internal pre-commit views without model/retrieval/Hard Call leakage."""
    views: list[BlindTaskView] = []
    for task in project_tasks(state):
        effective_query: str | None = None
        if task.task_kind is TaskKind.QUESTION_CHECK:
            qc = state.question_by_task.get(task.task_id)
            if qc is not None and qc.decision is not QuestionCheckDecision.REJECT:
                effective_query = qc.effective_query
        elif task.active:
            qc = state.current_question_for_case(task.case_id)
            if qc is not None:
                effective_query = qc.effective_query
        view = BlindTaskView(
            task_id=task.task_id,
            task_kind=task.task_kind.value,
            campaign_id=task.campaign_id,
            case_id=task.case_id,
            active=task.active,
            state=task.state.value,
            candidate_chunk_id=task.candidate_chunk_id,
            effective_query=effective_query,
        )
        payload = view.to_dict()
        leaked = _FORBIDDEN_BLIND_KEYS.intersection(payload)
        if leaked:
            raise RuntimeError(f"blind view leaked forbidden keys: {sorted(leaked)}")
        views.append(view)
    return views
