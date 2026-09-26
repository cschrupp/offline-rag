"""OpenAI-compatible recovery rewriter provider (independent of generation)."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import DIRECT_OUTPUT_V1
from offline_rag.core.network_policy import destination_satisfies_policy_no_dns
from offline_rag.generation.openai_compatible import (
    endpoint_authorized,
    normalize_endpoint,
)
from offline_rag.recovery.rewrite_contracts import (
    RECOVERY_REWRITE_OUTPUT_V1,
    RECOVERY_REWRITE_PROMPT_V1,
    RECOVERY_REWRITER_ADAPTER_V1,
    RecoveryRewriteError,
    RecoveryRewriteInputV1,
    RecoveryRewriteOutputV1,
    RecoveryRewriteProvenanceV1,
)
from offline_rag.recovery.rewrite_prompt import build_recovery_rewrite_messages
from offline_rag.recovery.rewrite_provenance import (
    build_recovery_rewrite_attempt_provenance,
)


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def parse_recovery_rewrite_output(raw: str) -> RecoveryRewriteOutputV1:
    """Strict JSON parse of recovery-rewrite-output-v1. No repair."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RecoveryRewriteError(
            "recovery rewriter returned malformed JSON",
            failure_reason="malformed_output",
        ) from exc
    if not isinstance(payload, dict):
        raise RecoveryRewriteError(
            "recovery rewriter output must be a JSON object",
            failure_reason="malformed_output",
        )
    try:
        return RecoveryRewriteOutputV1.model_validate(payload)
    except ValidationError as exc:
        raise RecoveryRewriteError(
            f"recovery rewriter output failed contract validation: {exc}",
            failure_reason="malformed_output",
        ) from exc


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RecoveryRewriteError(
            "recovery rewriter response missing choices",
            failure_reason="provider_error",
        )
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise RecoveryRewriteError(
            "recovery rewriter response missing message",
            failure_reason="provider_error",
        )
    content = message.get("content")
    if not isinstance(content, str):
        raise RecoveryRewriteError(
            "recovery rewriter response content must be a string",
            failure_reason="provider_error",
        )
    return content


def _with_provenance(
    exc: RecoveryRewriteError,
    provenance: RecoveryRewriteProvenanceV1,
) -> RecoveryRewriteError:
    if exc.provenance is not None:
        return exc
    return RecoveryRewriteError(
        str(exc),
        failure_reason=exc.failure_reason,
        provenance=provenance,
    )


class OpenAICompatibleRecoveryRewriter:
    """Independently configured OpenAI-compatible recovery rewriter."""

    contract = RECOVERY_REWRITER_ADAPTER_V1

    def __init__(
        self,
        settings: AppSettings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        rewriter = settings.retrieval_recovery.rewriter
        if rewriter.provider != "openai_compatible":
            raise RecoveryRewriteError(
                f"unsupported recovery rewriter provider: {rewriter.provider}",
                failure_reason="provider_error",
            )
        if rewriter.adapter_contract != RECOVERY_REWRITER_ADAPTER_V1:
            raise RecoveryRewriteError(
                f"unsupported recovery rewriter adapter_contract: "
                f"{rewriter.adapter_contract}",
                failure_reason="provider_error",
            )
        if rewriter.prompt_contract != RECOVERY_REWRITE_PROMPT_V1:
            raise RecoveryRewriteError(
                f"unsupported recovery rewriter prompt_contract: "
                f"{rewriter.prompt_contract}",
                failure_reason="provider_error",
            )
        if rewriter.output_contract != RECOVERY_REWRITE_OUTPUT_V1:
            raise RecoveryRewriteError(
                f"unsupported recovery rewriter output_contract: "
                f"{rewriter.output_contract}",
                failure_reason="provider_error",
            )
        self._owned_client = client is None
        timeout = float(rewriter.timeout_seconds)
        headers = _auth_headers(rewriter.api_key)
        self._client = client or httpx.Client(timeout=timeout, headers=headers)
        self.rewrite_calls = 0

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    @property
    def base_url(self) -> str:
        return normalize_endpoint(self.settings.retrieval_recovery.rewriter.base_url)

    def _assert_authorized(self) -> None:
        rewriter = self.settings.retrieval_recovery.rewriter
        # Dual gate: network_policy AND approved_endpoints (allowlist cannot
        # override the network boundary).
        policy_failure = destination_satisfies_policy_no_dns(
            rewriter.base_url, network_policy=rewriter.network_policy
        )
        if policy_failure is not None:
            raise RecoveryRewriteError(
                f"configured recovery rewriter endpoint rejected by "
                f"network_policy={rewriter.network_policy}",
                failure_reason="authorization_error",
            )
        if not endpoint_authorized(
            rewriter.base_url, list(rewriter.approved_endpoints)
        ):
            raise RecoveryRewriteError(
                "configured recovery rewriter endpoint is not approved",
                failure_reason="authorization_error",
            )
        if rewriter.model not in rewriter.approved_models:
            raise RecoveryRewriteError(
                "configured recovery rewriter model is not approved",
                failure_reason="authorization_error",
            )

    def rewrite(
        self, rewrite_input: RecoveryRewriteInputV1
    ) -> tuple[RecoveryRewriteOutputV1, RecoveryRewriteProvenanceV1]:
        attempt = build_recovery_rewrite_attempt_provenance(
            self.settings, rewrite_call_count=1
        )
        try:
            self._assert_authorized()
            self.rewrite_calls += 1
            rewriter = self.settings.retrieval_recovery.rewriter
            messages = build_recovery_rewrite_messages(rewrite_input)
            body: dict[str, Any] = {
                "model": rewriter.model,
                "temperature": float(rewriter.temperature),
                "max_tokens": int(rewriter.max_output_tokens),
                "messages": messages,
                "response_format": {"type": "json_object"},
                "chat_template_kwargs": {"enable_thinking": False},
            }
            _ = DIRECT_OUTPUT_V1
            url = f"{self.base_url}/chat/completions"
            try:
                response = self._client.post(
                    url, json=body, headers=_auth_headers(rewriter.api_key)
                )
            except httpx.TimeoutException as exc:
                raise RecoveryRewriteError(
                    "recovery rewriter timed out",
                    failure_reason="timeout",
                    provenance=attempt,
                ) from exc
            except httpx.HTTPError as exc:
                raise RecoveryRewriteError(
                    f"recovery rewriter transport error: {exc}",
                    failure_reason="transport_error",
                    provenance=attempt,
                ) from exc
            if response.status_code >= 400:
                raise RecoveryRewriteError(
                    f"recovery rewriter provider error: HTTP {response.status_code}",
                    failure_reason="provider_error",
                    provenance=attempt,
                )
            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise RecoveryRewriteError(
                    "recovery rewriter returned non-JSON HTTP body",
                    failure_reason="provider_error",
                    provenance=attempt,
                ) from exc
            if not isinstance(payload, dict):
                raise RecoveryRewriteError(
                    "recovery rewriter HTTP JSON must be an object",
                    failure_reason="provider_error",
                    provenance=attempt,
                )
            raw = _extract_message_content(payload)
            parsed = parse_recovery_rewrite_output(raw)
        except RecoveryRewriteError as exc:
            raise _with_provenance(exc, attempt) from exc

        success = attempt.model_copy(update={"rewritten_query": parsed.rewritten_query})
        return parsed, success
