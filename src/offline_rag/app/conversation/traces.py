"""Conversation orchestration traces — privacy-minimized (A2-D19)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.traces import (
    ProductTraceSourceScope,
    allocate_trace_id,
    is_valid_trace_id,
)
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import CONVERSATION_CONTEXT_RESOLVER_V1
from offline_rag.ingestion.io import atomic_write_text

CONVERSATION_TRACE_SCHEMA_VERSION = "offline-rag-conversation-trace-v2"
LEGACY_CONVERSATION_TRACE_SCHEMA_VERSION = "offline-rag-conversation-trace-v1"
MAX_RETAINED_CONVERSATION_TRACES = 1000
MAX_TRACE_AGE = timedelta(days=7)

ResolverOutcomeStatus = Literal[
    "resolved",
    "clarification_required",
    "bypassed",
]
ConversationTerminalStatus = Literal[
    "answered",
    "insufficient_evidence",
    "model_abstain",
    "clarification_required",
    "transformed",
]
ConversationIntentKind = Literal[
    "grounded_query", "conversation_transform", "clarification_required"
]
ConversationTransformSource = Literal[
    "current_message", "prior_user_turn", "prior_assistant_turn"
]


def allocate_conversation_trace_id() -> str:
    """Opaque orchestration identity (same format family as query traces)."""
    return allocate_trace_id()


class ConversationTraceRecord(BaseModel):
    """Allowlisted durable conversation-turn orchestration provenance."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = CONVERSATION_TRACE_SCHEMA_VERSION
    conversation_trace_id: str
    created_at: datetime
    workspace_id: str
    workspace_revision: int = Field(ge=0)
    snapshot_id: str
    product_mode_id: str
    source_scope: ProductTraceSourceScope
    question_sha256: str = Field(min_length=1)
    question_char_count: int = Field(ge=0)
    prior_turn_count: int = Field(ge=0)
    resolver_invoked: bool
    resolver_prompt_contract_id: str | None = CONVERSATION_CONTEXT_RESOLVER_V1
    resolver_outcome: ResolverOutcomeStatus | None
    retrieval_question_sha256: str | None = None
    retrieval_question_char_count: int | None = None
    context_used: bool
    status: ConversationTerminalStatus
    query_trace_id: str | None = None
    intent_kind: ConversationIntentKind | None = None
    intent_router_contract_id: str | None = None
    transform_prompt_contract_id: str | None = None
    transform_operation: (
        Literal["summarize", "rewrite", "simplify", "translate"] | None
    ) = None
    transform_source_kind: ConversationTransformSource | None = None
    transform_source_role: Literal["user", "assistant"] | None = None
    transform_source_turn_ordinal: int | None = Field(default=None, ge=1, le=12)
    transform_target_sha256: str | None = None
    transform_target_char_count: int | None = Field(default=None, ge=0)
    transform_output_sha256: str | None = None
    transform_output_char_count: int | None = Field(default=None, ge=0)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value not in {
            CONVERSATION_TRACE_SCHEMA_VERSION,
            LEGACY_CONVERSATION_TRACE_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported conversation trace schema version")
        return value

    @field_validator("conversation_trace_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not is_valid_trace_id(value):
            raise ValueError("invalid conversation_trace_id")
        return value

    @field_validator("query_trace_id")
    @classmethod
    def _validate_query_trace(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_trace_id(value):
            raise ValueError("invalid query_trace_id")
        return value

    @model_validator(mode="after")
    def _validate_transform_trace(self) -> ConversationTraceRecord:
        if self.schema_version == CONVERSATION_TRACE_SCHEMA_VERSION:
            if (
                self.intent_kind == "conversation_transform"
                and self.status != "transformed"
            ):
                raise ValueError("transform intent requires transformed status")
            if (
                self.intent_kind == "clarification_required"
                and self.status != "clarification_required"
            ):
                raise ValueError("clarification intent requires clarification status")
            if self.intent_kind != "conversation_transform" and any(
                value is not None
                for value in (
                    self.transform_prompt_contract_id,
                    self.transform_operation,
                    self.transform_source_kind,
                    self.transform_source_role,
                    self.transform_source_turn_ordinal,
                    self.transform_target_sha256,
                    self.transform_target_char_count,
                    self.transform_output_sha256,
                    self.transform_output_char_count,
                )
            ):
                raise ValueError("non-transform trace contains transform metadata")
        if self.status != "transformed":
            return self
        if (
            self.schema_version != CONVERSATION_TRACE_SCHEMA_VERSION
            or self.intent_kind != "conversation_transform"
            or self.intent_router_contract_id != "conversation_intent_router_v1"
            or self.transform_prompt_contract_id != "conversation_transform_v1"
            or self.transform_operation is None
            or self.transform_source_kind is None
            or self.transform_source_role is None
            or self.transform_target_sha256 is None
            or self.transform_target_char_count is None
            or self.transform_output_sha256 is None
            or self.transform_output_char_count is None
            or self.resolver_invoked
            or self.retrieval_question_sha256 is not None
            or self.retrieval_question_char_count is not None
            or self.query_trace_id is not None
        ):
            raise ValueError("invalid conversation transform trace")
        if self.transform_source_kind == "current_message":
            if (
                self.transform_source_role != "user"
                or self.transform_source_turn_ordinal is not None
            ):
                raise ValueError("current-message transform cannot name a prior turn")
        else:
            expected_role = (
                "user"
                if self.transform_source_kind == "prior_user_turn"
                else "assistant"
            )
            if (
                self.transform_source_role != expected_role
                or self.transform_source_turn_ordinal is None
            ):
                raise ValueError("prior-turn transform provenance is inconsistent")
        return self


class ConversationTraceStore:
    """Process-local durable store under ``traces/conversation/``."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._root = Path(settings.paths.traces) / "conversation"
        self._lock = threading.Lock()

    def _path(self, conversation_trace_id: str) -> Path:
        if not is_valid_trace_id(conversation_trace_id):
            raise AppError(ErrorCode.TRACE_UNKNOWN)
        return self._root / f"{conversation_trace_id}.json"

    def commit(self, record: ConversationTraceRecord) -> None:
        validated = ConversationTraceRecord.model_validate(
            record.model_dump(mode="python")
        )
        path = self._path(validated.conversation_trace_id)
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, validated.model_dump_json())
            self._enforce_retention_unlocked()

    def get(self, conversation_trace_id: str) -> ConversationTraceRecord | None:
        if not is_valid_trace_id(conversation_trace_id):
            return None
        path = self._path(conversation_trace_id)
        with self._lock:
            if not path.is_file():
                return None
            try:
                record = ConversationTraceRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except OSError, ValueError:
                return None
            created = record.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if datetime.now(tz=UTC) - created > MAX_TRACE_AGE:
                return None
            return record

    def public_projection(self, record: ConversationTraceRecord) -> dict[str, Any]:
        return record.model_dump(mode="json")

    def _enforce_retention_unlocked(self) -> None:
        now = datetime.now(tz=UTC)
        entries: list[tuple[datetime, Path]] = []
        for path in self._root.glob("trace_*.json"):
            name = path.stem
            if not is_valid_trace_id(name):
                continue
            try:
                record = ConversationTraceRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except OSError, ValueError:
                path.unlink(missing_ok=True)
                continue
            created = record.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if now - created > MAX_TRACE_AGE:
                path.unlink(missing_ok=True)
                continue
            entries.append((created, path))
        entries.sort(key=lambda item: item[0], reverse=True)
        for _, path in entries[MAX_RETAINED_CONVERSATION_TRACES:]:
            path.unlink(missing_ok=True)
