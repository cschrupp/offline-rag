"""GenerationSemanticJudge protocol and request/response types."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from offline_rag.domain.indexing import EvidenceUnit
from offline_rag.evaluation.generation_semantic.judge_schema import (
    GenerationSemanticJudgeOutputV1,
)


@dataclass(frozen=True, slots=True)
class GenerationSemanticJudgeRequest:
    query: str
    evidence_units: tuple[EvidenceUnit, ...]
    answer_text: str
    citation_ids: tuple[str, ...]
    source_name_by_document_id: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class GenerationSemanticJudgeResponse:
    output: GenerationSemanticJudgeOutputV1
    latency_ms: int
    raw_content: str | None = None


class GenerationSemanticJudgeError(RuntimeError):
    def __init__(self, message: str, *, failure_reason: str) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason


class GenerationSemanticJudge(Protocol):
    def judge(
        self, request: GenerationSemanticJudgeRequest
    ) -> GenerationSemanticJudgeResponse: ...

    def close(self) -> None: ...


def make_judge_request(
    *,
    query: str,
    evidence_units: Sequence[EvidenceUnit],
    answer_text: str,
    citation_ids: Sequence[str],
    source_name_by_document_id: Mapping[str, str],
) -> GenerationSemanticJudgeRequest:
    return GenerationSemanticJudgeRequest(
        query=query,
        evidence_units=tuple(evidence_units),
        answer_text=answer_text,
        citation_ids=tuple(citation_ids),
        source_name_by_document_id=dict(source_name_by_document_id),
    )
