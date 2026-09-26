"""Pure rewriter/experiment preflight for authoritative 12C runs (no model calls)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from offline_rag.config.models import AppSettings
from offline_rag.core.network_policy import destination_satisfies_policy_no_dns
from offline_rag.evaluation.recovery_12c.contracts import (
    PLACEHOLDER_REWRITER_MODEL,
    RecoveryEvalError,
)
from offline_rag.generation.openai_compatible import endpoint_authorized
from offline_rag.recovery.rewrite_config_hash import build_recovery_rewriter_config_hash


@dataclass(frozen=True, slots=True)
class RecoveryEvalPreflightResult:
    ready: bool
    status: Literal["READY", "NOT_READY"]
    reasons: tuple[str, ...]
    rewriter_config_hash: str | None


def _is_placeholder_model(model: str) -> bool:
    text = model.strip()
    if not text:
        return True
    if text == PLACEHOLDER_REWRITER_MODEL:
        return True
    return text.upper().startswith("REPLACE_WITH_")


def preflight_authoritative_recovery_eval(
    settings: AppSettings,
) -> RecoveryEvalPreflightResult:
    """Validate experiment recovery block before any rewrite/provider call.

    Does not call the model. Does not mutate ``base.yaml``.
    """
    reasons: list[str] = []
    recovery = settings.retrieval_recovery
    rewriter = recovery.rewriter

    if not recovery.enabled:
        reasons.append("retrieval_recovery.enabled must be true for authoritative 12C")
    if recovery.max_retries != 1:
        reasons.append("retrieval_recovery.max_retries must be exactly 1")

    if _is_placeholder_model(rewriter.model):
        reasons.append(
            "retrieval_recovery.rewriter.model must be a concrete approved model "
            f"(placeholder {PLACEHOLDER_REWRITER_MODEL!r} forbidden)"
        )
    if not rewriter.approved_models:
        reasons.append("retrieval_recovery.rewriter.approved_models must be non-empty")
    elif rewriter.model not in rewriter.approved_models:
        reasons.append(
            "retrieval_recovery.rewriter.model must appear in approved_models"
        )

    if not rewriter.approved_endpoints:
        reasons.append(
            "retrieval_recovery.rewriter.approved_endpoints must be non-empty"
        )
    else:
        policy_failure = destination_satisfies_policy_no_dns(
            rewriter.base_url, network_policy=rewriter.network_policy
        )
        if policy_failure is not None:
            reasons.append(
                "retrieval_recovery.rewriter.base_url rejected by "
                f"network_policy={rewriter.network_policy} ({policy_failure})"
            )
        if not endpoint_authorized(
            rewriter.base_url, list(rewriter.approved_endpoints)
        ):
            reasons.append(
                "retrieval_recovery.rewriter.base_url is not in approved_endpoints"
            )

    rewriter_hash: str | None = None
    try:
        rewriter_hash = build_recovery_rewriter_config_hash(settings)
    except Exception as exc:  # noqa: BLE001 — surface as preflight failure
        reasons.append(f"unable to compute rewriter_config_hash: {exc}")

    if reasons:
        return RecoveryEvalPreflightResult(
            ready=False,
            status="NOT_READY",
            reasons=tuple(reasons),
            rewriter_config_hash=rewriter_hash,
        )
    return RecoveryEvalPreflightResult(
        ready=True,
        status="READY",
        reasons=(),
        rewriter_config_hash=rewriter_hash,
    )


def require_authoritative_recovery_preflight(settings: AppSettings) -> str:
    """Fail closed unless preflight is READY; return ``rrwcfg_`` hash."""
    result = preflight_authoritative_recovery_eval(settings)
    if not result.ready or result.rewriter_config_hash is None:
        joined = "; ".join(result.reasons) or "preflight incomplete"
        raise RecoveryEvalError(f"12C authoritative preflight failed: {joined}")
    return result.rewriter_config_hash
