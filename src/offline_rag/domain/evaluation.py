"""Experiment and evaluation result contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.types import NonEmptyStr, Score


class EvaluationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExperimentConfig(BaseModel):
    """Material experiment identity and parameters.

    Application runtime settings live in ``offline_rag.config``. This model
    captures the experiment contract used by evaluation and traces.
    """

    model_config = ConfigDict(extra="forbid")

    experiment_id: NonEmptyStr
    name: NonEmptyStr
    config_hash: NonEmptyStr
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """One evaluation run result. Execution IDs may be random; corpus IDs must not."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: NonEmptyStr
    experiment_id: NonEmptyStr
    dataset_id: NonEmptyStr
    status: EvaluationStatus = EvaluationStatus.COMPLETED
    metrics: dict[str, Score] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
