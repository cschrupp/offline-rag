"""Deterministic fake recovery rewriter for unit tests."""

from __future__ import annotations

from collections.abc import Callable

from offline_rag.config.models import AppSettings
from offline_rag.recovery.rewrite_contracts import (
    RecoveryRewriteError,
    RecoveryRewriteInputV1,
    RecoveryRewriteOutputV1,
    RecoveryRewriteProvenanceV1,
)
from offline_rag.recovery.rewrite_prompt import build_recovery_rewrite_messages
from offline_rag.recovery.rewrite_provenance import (
    build_recovery_rewrite_attempt_provenance,
)


class FakeRecoveryRewriter:
    """Injectable rewriter that never calls a network provider."""

    contract = "fake-recovery-rewriter-v1"

    def __init__(
        self,
        settings: AppSettings,
        *,
        rewritten_query: str | None = None,
        rewrite_fn: Callable[[RecoveryRewriteInputV1], str] | None = None,
        raise_on_rewrite: Exception | None = None,
        capture_prompts: bool = True,
    ) -> None:
        self.settings = settings
        self._rewritten_query = rewritten_query
        self._rewrite_fn = rewrite_fn
        self._raise_on_rewrite = raise_on_rewrite
        self.capture_prompts = capture_prompts
        self.rewrite_calls = 0
        self.last_input: RecoveryRewriteInputV1 | None = None
        self.last_messages: list[dict[str, str]] | None = None

    def rewrite(
        self, rewrite_input: RecoveryRewriteInputV1
    ) -> tuple[RecoveryRewriteOutputV1, RecoveryRewriteProvenanceV1]:
        self.rewrite_calls += 1
        self.last_input = rewrite_input
        if self.capture_prompts:
            self.last_messages = build_recovery_rewrite_messages(rewrite_input)
        attempt = build_recovery_rewrite_attempt_provenance(
            self.settings, rewrite_call_count=1
        )
        if self._raise_on_rewrite is not None:
            exc = self._raise_on_rewrite
            if isinstance(exc, RecoveryRewriteError) and exc.provenance is None:
                raise RecoveryRewriteError(
                    str(exc),
                    failure_reason=exc.failure_reason,
                    provenance=attempt,
                ) from exc
            raise exc
        if self._rewrite_fn is not None:
            query = self._rewrite_fn(rewrite_input)
        elif self._rewritten_query is not None:
            query = self._rewritten_query
        else:
            query = rewrite_input.original_query
        try:
            output = RecoveryRewriteOutputV1(rewritten_query=query)
        except Exception as exc:
            raise RecoveryRewriteError(
                f"fake rewriter produced invalid output: {exc}",
                failure_reason="malformed_output",
                provenance=attempt,
            ) from exc
        provenance = attempt.model_copy(
            update={"rewritten_query": output.rewritten_query}
        )
        return output, provenance
