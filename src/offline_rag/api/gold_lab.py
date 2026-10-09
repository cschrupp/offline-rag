"""Gold Lab HTTP adapters (16F-D application / API data plane)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, Strict, field_validator

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.gold_lab.application import GoldLabApplicationService
from offline_rag.app.runtime import ApplicationRuntime

router = APIRouter(prefix="/v1/gold-lab", tags=["gold-lab"])


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise TypeError("application runtime is not configured")
    return runtime


def _gold(request: Request) -> GoldLabApplicationService:
    runtime = _runtime(request)
    runtime.require_ready()
    return runtime.gold_lab


def _require_idempotency_key(raw: str | None) -> str:
    if raw is None or not str(raw).strip():
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="idempotency_key_required"),
        )
    key = str(raw).strip()
    if len(key) > 256:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="idempotency_key_invalid"),
        )
    return key


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    project_type: Literal["benchmark", "improvement"]


class HardCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    candidate_chunk_id: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)


class CampaignCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_authoring_run_id: str = Field(min_length=1)
    selection_policy_id: str = Field(min_length=1)
    selection_policy_parameters: dict[str, Any] = Field(default_factory=dict)
    hard_calls: list[HardCallRequest] = Field(default_factory=list)


class QuestionCheckAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept"]
    game_id: str | None = None
    presentation_id: str | None = None


class QuestionCheckRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["reject"]
    game_id: str | None = None
    presentation_id: str | None = None


class QuestionCheckEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["edit"]
    effective_query: str = Field(min_length=1)
    effective_category: str | None
    effective_tags: list[str]
    game_id: str | None = None
    presentation_id: str | None = None


QuestionCheckRequest = Annotated[
    QuestionCheckAcceptRequest
    | QuestionCheckRejectRequest
    | QuestionCheckEditRequest,
    Field(discriminator="decision"),
]


class RelevanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance: Annotated[int, Strict()]
    game_id: str | None = None
    presentation_id: str | None = None

    @field_validator("relevance")
    @classmethod
    def _strict_relevance(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("relevance must be integer 0, 1, or 2")
        if value not in (0, 1, 2):
            raise ValueError("relevance must be integer 0, 1, or 2")
        return value


class PreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    preferred_chunk_id: str = Field(min_length=1)
    other_chunk_id: str = Field(min_length=1)
    game_id: str | None = None
    presentation_id: str | None = None


@router.get("/projects")
def list_projects(
    request: Request, workspace_id: str | None = None
) -> dict[str, Any]:
    return _gold(request).list_projects(workspace_id=workspace_id)


@router.post("/projects", status_code=201)
def create_project(request: Request, body: ProjectCreateRequest) -> dict[str, Any]:
    return _gold(request).create_project(
        workspace_id=body.workspace_id,
        title=body.title,
        description=body.description,
        project_type=body.project_type,
    )


@router.get("/projects/{project_id}")
def get_project(request: Request, project_id: str) -> dict[str, Any]:
    return _gold(request).get_project(project_id)


@router.post("/projects/{project_id}/archive")
def archive_project(request: Request, project_id: str) -> dict[str, Any]:
    return _gold(request).archive_project(project_id)


@router.get("/projects/{project_id}/baselines")
def list_baselines(request: Request, project_id: str) -> dict[str, Any]:
    return _gold(request).list_baselines(project_id)


@router.get("/projects/{project_id}/campaigns")
def list_campaigns(request: Request, project_id: str) -> dict[str, Any]:
    return _gold(request).list_campaigns(project_id)


@router.post("/projects/{project_id}/campaigns", status_code=201)
def create_campaign(
    request: Request, project_id: str, body: CampaignCreateRequest
) -> dict[str, Any]:
    return _gold(request).create_campaign(
        project_id=project_id,
        baseline_authoring_run_id=body.baseline_authoring_run_id,
        selection_policy_id=body.selection_policy_id,
        selection_policy_parameters=body.selection_policy_parameters,
        hard_calls=[item.model_dump() for item in body.hard_calls],
    )


@router.get("/campaigns/{campaign_id}")
def get_campaign(request: Request, campaign_id: str) -> dict[str, Any]:
    return _gold(request).get_campaign(campaign_id)


@router.post("/campaigns/{campaign_id}/close")
def close_campaign(request: Request, campaign_id: str) -> dict[str, Any]:
    return _gold(request).close_campaign(campaign_id)


@router.get("/campaigns/{campaign_id}/tasks")
def list_tasks(
    request: Request,
    campaign_id: str,
    kind: Literal["question_check", "absolute_relevance"] | None = None,
    state: Literal["pending", "completed"] | None = None,
    active: bool | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    return _gold(request).list_tasks(
        campaign_id,
        kind=kind,
        state=state,
        active=active,
        case_id=case_id,
    )


@router.get("/campaigns/{campaign_id}/tasks/{task_id}")
def get_task(request: Request, campaign_id: str, task_id: str) -> dict[str, Any]:
    return _gold(request).get_task(campaign_id, task_id)


@router.post("/campaigns/{campaign_id}/tasks/{task_id}/question-check")
def submit_question_check(
    request: Request,
    campaign_id: str,
    task_id: str,
    body: QuestionCheckRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    if isinstance(body, QuestionCheckEditRequest):
        payload: dict[str, Any] = {
            "decision": "edit",
            "effective_query": body.effective_query,
            "effective_category": body.effective_category,
            "effective_tags": body.effective_tags,
        }
    else:
        payload = {"decision": body.decision}
    return _gold(request).submit_question_check(
        campaign_id=campaign_id,
        task_id=task_id,
        idempotency_key=key,
        payload=payload,
        game_id=body.game_id,
        presentation_id=body.presentation_id,
    )


@router.post("/campaigns/{campaign_id}/tasks/{task_id}/relevance")
def submit_relevance(
    request: Request,
    campaign_id: str,
    task_id: str,
    body: RelevanceRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    return _gold(request).submit_relevance(
        campaign_id=campaign_id,
        task_id=task_id,
        idempotency_key=key,
        relevance=body.relevance,
        game_id=body.game_id,
        presentation_id=body.presentation_id,
    )


@router.post("/campaigns/{campaign_id}/preferences")
def submit_preference(
    request: Request,
    campaign_id: str,
    body: PreferenceRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    return _gold(request).submit_preference(
        campaign_id=campaign_id,
        idempotency_key=key,
        case_id=body.case_id,
        preferred_chunk_id=body.preferred_chunk_id,
        other_chunk_id=body.other_chunk_id,
        game_id=body.game_id,
        presentation_id=body.presentation_id,
    )


@router.get("/campaigns/{campaign_id}/contribution")
def contribution(request: Request, campaign_id: str) -> dict[str, Any]:
    return _gold(request).contribution(campaign_id)


@router.post("/campaigns/{campaign_id}/export")
def export_campaign(request: Request, campaign_id: str) -> JSONResponse:
    body, status = _gold(request).export_campaign(campaign_id)
    return JSONResponse(content=body, status_code=status)


@router.get("/campaigns/{campaign_id}/registrations")
def list_registrations(request: Request, campaign_id: str) -> dict[str, Any]:
    return _gold(request).list_registrations(campaign_id)
