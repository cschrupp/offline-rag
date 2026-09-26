"""Recovery rewriter contracts (Slice 12B; OD-12-1/2)."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from offline_rag.domain.types import NonNegativeInt
from offline_rag.recovery.contracts import (
    RECOVERY_ATTEMPT_ROLE_INITIAL,
    RecoveryDiagnosticsV1,
    RecoverySufficiencyDecisionRefV1,
)
from offline_rag.sufficiency.contracts import ExactNonBlankStr

RECOVERY_REWRITE_PROMPT_V1 = "recovery-query-rewrite-v1"
RECOVERY_REWRITE_OUTPUT_V1 = "recovery-rewrite-output-v1"
RECOVERY_REWRITER_ADAPTER_V1 = "openai-compatible-recovery-rewriter-v1"


class RecoveryRewriteError(RuntimeError):
    """Fail-closed recovery rewriter / provider error (no repair, no retry)."""

    def __init__(self, message: str, *, failure_reason: str = "provider_error") -> None:
        super().__init__(message)
        self.failure_reason = failure_reason


class RecoveryRewriteInputV1(BaseModel):
    """Allowlisted rewriter input. No corpus-derived free text."""

    model_config = ConfigDict(extra="forbid")

    original_query: ExactNonBlankStr
    attempt_number: Literal[0] = 0
    attempt_role: Literal["initial"] = RECOVERY_ATTEMPT_ROLE_INITIAL
    sufficiency: RecoverySufficiencyDecisionRefV1
    diagnostics: RecoveryDiagnosticsV1


class RecoveryRewriteOutputV1(BaseModel):
    """Strict structured rewriter output. Exactly one retrieval query."""

    model_config = ConfigDict(extra="forbid")

    rewritten_query: ExactNonBlankStr


class RecoveryRewriteProvenanceV1(BaseModel):
    """Auditable rewrite call provenance (no secrets)."""

    model_config = ConfigDict(extra="forbid")

    prompt_contract: Literal["recovery-query-rewrite-v1"] = RECOVERY_REWRITE_PROMPT_V1
    output_contract: Literal["recovery-rewrite-output-v1"] = RECOVERY_REWRITE_OUTPUT_V1
    adapter_contract: ExactNonBlankStr
    rewriter_config_hash: ExactNonBlankStr
    provider: ExactNonBlankStr
    normalized_endpoint: ExactNonBlankStr
    model: ExactNonBlankStr
    rewrite_call_count: NonNegativeInt = 1
    rewritten_query: ExactNonBlankStr | None = None


class RecoveryRewriter(Protocol):
    """Project-owned rewriter protocol (provider-agnostic)."""

    def rewrite(
        self, rewrite_input: RecoveryRewriteInputV1
    ) -> tuple[RecoveryRewriteOutputV1, RecoveryRewriteProvenanceV1]:
        """Invoke the rewriter exactly once; fail closed on malformed output."""
        ...
