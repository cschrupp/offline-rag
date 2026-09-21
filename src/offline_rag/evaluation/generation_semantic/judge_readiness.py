"""Judge-only readiness (independent of generation/authoring/context)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import ValidationError

from offline_rag.config.models import (
    AppSettings,
    GenerationSemanticJudgeSettings,
)
from offline_rag.core.network_policy import (
    NetworkPolicyError,
    NetworkPolicyReason,
    destination_satisfies_policy,
    endpoint_in_allowlist,
    normalize_openai_compatible_endpoint,
)
from offline_rag.evaluation.generation_semantic.judge_contracts import (
    ADAPTER_CONTRACT,
    OUTPUT_CONTRACT,
    PROMPT_CONTRACT,
    SUPPORTED_PROVIDER,
)


class JudgePreflightKind(StrEnum):
    READY = "ready"
    CONFIG_INVALID = "config_invalid"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class JudgePreflightResult:
    kind: JudgePreflightKind
    status: Literal["READY", "NOT_READY"]
    reasons: tuple[str, ...]
    details: dict[str, Any]


def _judge_settings(settings: AppSettings) -> GenerationSemanticJudgeSettings:
    return settings.evaluation.generation_semantic_judge


def _config_shape_ok(
    judge: GenerationSemanticJudgeSettings,
) -> tuple[bool, str | None]:
    try:
        GenerationSemanticJudgeSettings.model_validate(judge.model_dump())
    except ValidationError as exc:
        return False, f"invalid judge configuration: {exc.errors()[0]['msg']}"
    if judge.provider != SUPPORTED_PROVIDER:
        return False, f"unsupported judge provider: {judge.provider}"
    if judge.temperature != 0.0:
        return False, "judge temperature must be 0.0"
    if judge.model is None or not str(judge.model).strip():
        return False, "judge model must be non-empty"
    if judge.max_output_tokens < 1:
        return False, "judge max_output_tokens must be >= 1"
    if judge.timeout_seconds <= 0:
        return False, "judge timeout_seconds must be > 0"
    if judge.adapter_contract != ADAPTER_CONTRACT:
        return False, f"unsupported judge adapter_contract: {judge.adapter_contract}"
    if judge.prompt_contract != PROMPT_CONTRACT:
        return False, f"unsupported judge prompt_contract: {judge.prompt_contract}"
    if judge.output_contract != OUTPUT_CONTRACT:
        return False, f"unsupported judge output_contract: {judge.output_contract}"
    try:
        normalize_openai_compatible_endpoint(judge.base_url)
    except NetworkPolicyError as exc:
        return False, str(exc)
    return True, None


def _probe_judge(settings: AppSettings) -> tuple[bool, bool, str | None]:
    """Return (endpoint_reachable, model_available, failure_reason)."""
    from offline_rag.evaluation.generation_semantic.judge_adapter import (
        GenerationSemanticJudgeError,
        OpenAICompatibleGenerationSemanticJudge,
    )

    adapter = OpenAICompatibleGenerationSemanticJudge(settings)
    try:
        probe = adapter.probe()
    except GenerationSemanticJudgeError as exc:
        return False, False, str(exc)
    finally:
        adapter.close()
    endpoint_reachable = probe.ok or "unreachable" not in (probe.reason or "")
    return endpoint_reachable, probe.ok, (None if probe.ok else probe.reason)


def evaluate_judge_preflight(settings: AppSettings) -> JudgePreflightResult:
    """Classify judge readiness for --judge runs."""
    judge = _judge_settings(settings)
    if not judge.enabled:
        return JudgePreflightResult(
            kind=JudgePreflightKind.DISABLED,
            status="NOT_READY",
            reasons=("evaluation.generation_semantic_judge.enabled is false",),
            details={"enabled": False},
        )

    ok, reason = _config_shape_ok(judge)
    if not ok:
        return JudgePreflightResult(
            kind=JudgePreflightKind.CONFIG_INVALID,
            status="NOT_READY",
            reasons=(reason or "invalid judge configuration",),
            details={"enabled": True, "config_ok": False},
        )

    reasons: list[str] = []
    if not endpoint_in_allowlist(judge.base_url, list(judge.approved_endpoints)):
        reasons.append("configured judge endpoint is not approved")
    policy = destination_satisfies_policy(
        judge.base_url, network_policy=judge.network_policy
    )
    if policy is not None:
        if policy == NetworkPolicyReason.PUBLIC_ADDRESS_NOT_ALLOWED:
            reasons.append("judge endpoint is not a private/localhost destination")
        else:
            reasons.append(
                f"judge endpoint rejected by network_policy={judge.network_policy}"
            )
    if judge.model not in judge.approved_models:
        reasons.append("configured judge model is not approved")

    if reasons:
        return JudgePreflightResult(
            kind=JudgePreflightKind.UNAVAILABLE,
            status="NOT_READY",
            reasons=tuple(reasons),
            details={
                "enabled": True,
                "config_ok": True,
                "endpoint_authorized": endpoint_in_allowlist(
                    judge.base_url, list(judge.approved_endpoints)
                ),
                "model_authorized": judge.model in judge.approved_models,
            },
        )

    endpoint_reachable, model_available, fail = _probe_judge(settings)
    if not model_available:
        return JudgePreflightResult(
            kind=JudgePreflightKind.UNAVAILABLE,
            status="NOT_READY",
            reasons=(fail or "judge model unavailable",),
            details={
                "enabled": True,
                "config_ok": True,
                "endpoint_reachable": endpoint_reachable,
                "model_available": False,
                "probed": True,
            },
        )

    return JudgePreflightResult(
        kind=JudgePreflightKind.READY,
        status="READY",
        reasons=(),
        details={
            "enabled": True,
            "config_ok": True,
            "endpoint_authorized": True,
            "model_authorized": True,
            "endpoint_reachable": True,
            "model_available": True,
            "probed": True,
        },
    )


def generation_semantic_judge_status(settings: AppSettings) -> str:
    return evaluate_judge_preflight(settings).status


def describe_generation_semantic_judge_status(
    settings: AppSettings,
) -> dict[str, object]:
    result = evaluate_judge_preflight(settings)
    judge = _judge_settings(settings)
    return {
        "status": result.status,
        "preflight_kind": result.kind.value,
        "enabled": judge.enabled,
        "provider": judge.provider,
        "model": judge.model,
        "network_policy": judge.network_policy,
        "api_key_configured": bool(judge.api_key),
        "reasons": list(result.reasons),
        **result.details,
    }
