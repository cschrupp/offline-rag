"""OpenAI-compatible generation adapter (Ollama and peers)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from offline_rag.config.deployment_profile import (
    OPENROUTER_BASE_URL,
    PORTFOLIO_OPENROUTER_PROFILE,
)
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import DIRECT_OUTPUT_V1
from offline_rag.generation.contracts import (
    ADAPTER_CONTRACT,
    PROBE_TIMEOUT_SECONDS,
    REASONING_CONTRACT,
)
from offline_rag.generation.protocol import (
    GeneratorProbeResult,
    GeneratorRequest,
    GeneratorResponse,
)


class OpenAICompatibleGeneratorError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure_reason: str = "provider_error",
        http_status: int | None = None,
        provider_error_type: str | None = None,
        provider_error_code: str | None = None,
        safe_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason
        self.http_status = http_status
        self.provider_error_type = provider_error_type
        self.provider_error_code = provider_error_code
        self.safe_detail = safe_detail


def normalize_endpoint(base_url: str) -> str:
    """Normalize OpenAI-compatible base URL for allowlist comparison."""
    parsed = urlparse(base_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise OpenAICompatibleGeneratorError(
            f"unsupported endpoint scheme: {parsed.scheme}",
            failure_reason="provider_error",
        )
    if not parsed.netloc:
        raise OpenAICompatibleGeneratorError(
            "endpoint missing host",
            failure_reason="provider_error",
        )
    path = parsed.path.rstrip("/")
    if path in {"", "/"}:
        path = "/v1"
    elif not path.endswith("/v1"):
        # Accept .../v1 or append /v1 when only host root was given.
        if path.endswith("/v1/"):
            path = path.rstrip("/")
        elif not path.endswith("/v1"):
            path = f"{path}/v1" if path else "/v1"
    normalized = urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))
    return normalized


def endpoint_authorized(base_url: str, approved: list[str]) -> bool:
    try:
        selected = normalize_endpoint(base_url)
    except OpenAICompatibleGeneratorError:
        return False
    approved_norm = []
    for item in approved:
        try:
            approved_norm.append(normalize_endpoint(item))
        except OpenAICompatibleGeneratorError:
            continue
    return selected in approved_norm


class OpenAICompatibleGenerator:
    """HTTP adapter for OpenAI-compatible chat completions + models probe."""

    contract = ADAPTER_CONTRACT

    def __init__(
        self,
        settings: AppSettings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self._owned_client = client is None
        timeout = float(settings.generation.timeout_seconds)
        headers = _auth_headers(settings.generation.api_key)
        self._client = client or httpx.Client(timeout=timeout, headers=headers)

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    @property
    def base_url(self) -> str:
        return normalize_endpoint(self.settings.generation.base_url)

    def _chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _models_url(self) -> str:
        return f"{self.base_url}/models"

    def _request_headers(self) -> dict[str, str]:
        """Merge auth headers for injected clients that lack default headers."""
        return _auth_headers(self.settings.generation.api_key)

    def _assert_authorized(self) -> None:
        gen = self.settings.generation
        if self.settings.deployment.profile == PORTFOLIO_OPENROUTER_PROFILE and (
            normalize_endpoint(gen.base_url) != OPENROUTER_BASE_URL
            or list(gen.approved_endpoints) != [OPENROUTER_BASE_URL]
            or list(gen.approved_models) != [gen.model]
        ):
            raise OpenAICompatibleGeneratorError(
                "portfolio inference profile configuration is not exact",
                failure_reason="provider_error",
            )
        from offline_rag.app.endpoint_policy import (
            EndpointPolicyError,
            validate_endpoint_network_policy,
        )

        try:
            validate_endpoint_network_policy(
                gen.base_url,
                strict_offline=bool(self.settings.project.strict_offline),
            )
        except EndpointPolicyError as exc:
            raise OpenAICompatibleGeneratorError(
                f"configured endpoint rejected by network policy: {exc.reason}",
                failure_reason="provider_error",
            ) from exc
        if (
            self.settings.security.reject_unapproved_generation_endpoint
            and not endpoint_authorized(gen.base_url, list(gen.approved_endpoints))
        ):
            raise OpenAICompatibleGeneratorError(
                "configured endpoint is not approved",
                failure_reason="provider_error",
            )
        if self.settings.security.reject_unapproved_generation_model and (
            gen.model not in gen.approved_models
        ):
            raise OpenAICompatibleGeneratorError(
                "configured model is not approved",
                failure_reason="provider_error",
            )

    def probe(self) -> GeneratorProbeResult:
        try:
            self._assert_authorized()
        except OpenAICompatibleGeneratorError as exc:
            return GeneratorProbeResult(ok=False, reason=str(exc))
        try:
            response = self._client.get(
                self._models_url(),
                headers=self._request_headers() or None,
                timeout=PROBE_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException:
            return GeneratorProbeResult(ok=False, reason="endpoint probe timed out")
        except httpx.HTTPError as exc:
            return GeneratorProbeResult(
                ok=False,
                reason=_redact_secret(
                    f"endpoint unreachable: {exc}",
                    self.settings.generation.api_key,
                ),
            )
        if response.status_code >= 400:
            return GeneratorProbeResult(
                ok=False,
                reason=f"endpoint probe HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            return GeneratorProbeResult(
                ok=False, reason="endpoint probe returned non-JSON"
            )
        models = _extract_model_ids(payload)
        api_key = self.settings.generation.api_key
        if api_key and any(api_key in model_id for model_id in models):
            return GeneratorProbeResult(
                ok=False,
                reason="endpoint probe returned sensitive data",
            )
        selected = self.settings.generation.model
        if selected not in models:
            return GeneratorProbeResult(
                ok=False,
                reason="configured model is not available at the selected endpoint",
                available_models=tuple(models),
            )
        return GeneratorProbeResult(
            ok=True,
            reason="ok",
            available_models=tuple(models),
        )

    def generate(self, request: GeneratorRequest) -> GeneratorResponse:
        self._assert_authorized()
        body: dict[str, Any] = {
            "model": request.model,
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
        }
        if request.response_format is not None:
            body["response_format"] = request.response_format
        _apply_reasoning_contract(
            body,
            deployment_profile=self.settings.deployment.profile,
            base_url=self.base_url,
        )
        try:
            response = self._client.post(
                self._chat_url(),
                json=body,
                headers=self._request_headers() or None,
            )
        except httpx.TimeoutException as exc:
            raise OpenAICompatibleGeneratorError(
                _redact_secret(
                    f"generator request timed out: {exc}",
                    self.settings.generation.api_key,
                ),
                failure_reason="timeout",
                safe_detail="request_timeout",
            ) from None
        except httpx.HTTPError as exc:
            raise OpenAICompatibleGeneratorError(
                _redact_secret(
                    f"generator transport error: {exc}",
                    self.settings.generation.api_key,
                ),
                failure_reason="transport_error",
                safe_detail=type(exc).__name__,
            ) from None
        if response.status_code >= 400:
            if response.status_code in {401, 403}:
                reason = "unavailable"
            else:
                reason = "provider_error"
                text = response.text.lower()
                if "context" in text and (
                    "length" in text or "window" in text or "too long" in text
                ):
                    reason = "context_window_exceeded"
            provider_type, provider_code = _provider_error_identity(response)
            raise OpenAICompatibleGeneratorError(
                _redact_secret(
                    f"generator HTTP {response.status_code}",
                    self.settings.generation.api_key,
                ),
                failure_reason=reason,
                http_status=response.status_code,
                provider_error_type=provider_type,
                provider_error_code=provider_code,
                safe_detail=_safe_provider_error_detail(
                    response, self.settings.generation.api_key
                ),
            )
        try:
            payload = response.json()
        except ValueError:
            raise OpenAICompatibleGeneratorError(
                "generator returned non-JSON",
                failure_reason="provider_error",
                http_status=response.status_code,
                safe_detail="response_not_json",
            ) from None
        content = _extract_message_content(payload)
        api_key = self.settings.generation.api_key
        if api_key and api_key in content:
            raise OpenAICompatibleGeneratorError(
                "provider response contained configured credential",
                failure_reason="provider_error",
                http_status=response.status_code,
                safe_detail="credential_in_response",
            )
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        choices = payload.get("choices")
        finish_reason = None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            value = choices[0].get("finish_reason")
            finish_reason = value if isinstance(value, str) else None
        return GeneratorResponse(
            content=content,
            usage=_redact_payload(dict(usage), api_key),
            raw=_redact_payload(payload, api_key),
            finish_reason=(
                _redact_secret(finish_reason, api_key)
                if finish_reason is not None
                else None
            ),
            http_status=response.status_code,
        )


_SAFE_PROVIDER_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def _provider_error_identity(response: httpx.Response) -> tuple[str | None, str | None]:
    try:
        payload = response.json()
    except ValueError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None, None
    error_type = error.get("type")
    error_code = error.get("code")
    safe_type = (
        error_type
        if isinstance(error_type, str) and _SAFE_PROVIDER_TOKEN.fullmatch(error_type)
        else None
    )
    safe_code = (
        error_code
        if isinstance(error_code, str) and _SAFE_PROVIDER_TOKEN.fullmatch(error_code)
        else None
    )
    return safe_type, safe_code


def _safe_provider_error_detail(
    response: httpx.Response,
    api_key: str | None,
) -> str:
    """Return only bounded machine identifiers, never provider prose/body text."""
    provider_type, provider_code = _provider_error_identity(response)
    parts = ["provider_rejected_request"]
    if provider_type:
        parts.append(f"type={provider_type}")
    if provider_code:
        parts.append(f"code={provider_code}")
    return _redact_secret(" ".join(parts)[:256], api_key)


def bounded_rejected_response_excerpt(content: str, api_key: str | None) -> str:
    """Sanitize and cap an explicitly opted-in rejected model response."""
    text = re.sub(r"(?i)\bbearer\s+[^\s\"']+", "Bearer [redacted]", content)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[redacted]", text)
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text[:2048]


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def _apply_reasoning_contract(
    body: dict[str, Any], *, deployment_profile: str, base_url: str
) -> None:
    """Request direct output using the configured endpoint's request format."""
    mode = reasoning_request_mode(deployment_profile, base_url)
    if mode == "provider_default":
        return
    if mode == "reasoning_effort_none":
        body["reasoning_effort"] = "none"
    else:
        body["chat_template_kwargs"] = {"enable_thinking": False}


def reasoning_request_mode(deployment_profile: str, base_url: str) -> str:
    """Describe the actual provider reasoning request shape, without secrets."""
    if (
        deployment_profile == PORTFOLIO_OPENROUTER_PROFILE
        or REASONING_CONTRACT != DIRECT_OUTPUT_V1
    ):
        return "provider_default"
    endpoint = urlparse(base_url)
    if (
        endpoint.scheme == "http"
        and endpoint.hostname
        in {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
        and endpoint.port == 11434
        and endpoint.path == "/v1"
    ):
        return "reasoning_effort_none"
    return "chat_template_thinking_disabled"


def _redact_secret(message: str, api_key: str | None) -> str:
    """Remove an active Bearer key from provider-controlled error text."""
    if not api_key:
        return message
    return message.replace(api_key, "[redacted]")


def _redact_payload(value: Any, api_key: str | None) -> Any:
    """Return provider data with the configured credential removed recursively."""
    if not api_key:
        return value
    if isinstance(value, str):
        return _redact_secret(value, api_key)
    if isinstance(value, list):
        return [_redact_payload(item, api_key) for item in value]
    if isinstance(value, dict):
        return {key: _redact_payload(item, api_key) for key, item in value.items()}
    return value


def _extract_model_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    models: list[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            models.append(item["id"])
    return models


def _extract_message_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise OpenAICompatibleGeneratorError(
            "invalid completion payload",
            failure_reason="provider_error",
        )
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenAICompatibleGeneratorError(
            "completion missing choices",
            failure_reason="provider_error",
        )
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise OpenAICompatibleGeneratorError(
            "completion missing message",
            failure_reason="provider_error",
        )
    content = message.get("content")
    if not isinstance(content, str):
        raise OpenAICompatibleGeneratorError(
            "completion missing content",
            failure_reason="provider_error",
        )
    return content
