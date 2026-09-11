"""OpenAI-compatible generation adapter (Ollama and peers)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from offline_rag.config.models import AppSettings
from offline_rag.generation.contracts import ADAPTER_CONTRACT, PROBE_TIMEOUT_SECONDS
from offline_rag.generation.protocol import (
    GeneratorProbeResult,
    GeneratorRequest,
    GeneratorResponse,
)


class OpenAICompatibleGeneratorError(RuntimeError):
    def __init__(self, message: str, *, failure_reason: str = "provider_error") -> None:
        super().__init__(message)
        self.failure_reason = failure_reason


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
        self._client = client or httpx.Client(timeout=timeout)

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

    def _assert_authorized(self) -> None:
        gen = self.settings.generation
        if self.settings.security.reject_unapproved_generation_endpoint and not endpoint_authorized(
            gen.base_url, list(gen.approved_endpoints)
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
            response = self._client.get(self._models_url(), timeout=PROBE_TIMEOUT_SECONDS)
        except httpx.TimeoutException:
            return GeneratorProbeResult(ok=False, reason="endpoint probe timed out")
        except httpx.HTTPError as exc:
            return GeneratorProbeResult(ok=False, reason=f"endpoint unreachable: {exc}")
        if response.status_code >= 400:
            return GeneratorProbeResult(
                ok=False,
                reason=f"endpoint probe HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            return GeneratorProbeResult(ok=False, reason="endpoint probe returned non-JSON")
        models = _extract_model_ids(payload)
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
        try:
            response = self._client.post(self._chat_url(), json=body)
        except httpx.TimeoutException as exc:
            raise OpenAICompatibleGeneratorError(
                "generator request timed out",
                failure_reason="timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenAICompatibleGeneratorError(
                f"generator transport error: {exc}",
                failure_reason="transport_error",
            ) from exc
        if response.status_code >= 400:
            reason = "provider_error"
            text = response.text.lower()
            if "context" in text and ("length" in text or "window" in text or "too long" in text):
                reason = "context_window_exceeded"
            raise OpenAICompatibleGeneratorError(
                f"generator HTTP {response.status_code}: {response.text[:300]}",
                failure_reason=reason,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenAICompatibleGeneratorError(
                "generator returned non-JSON",
                failure_reason="provider_error",
            ) from exc
        content = _extract_message_content(payload)
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return GeneratorResponse(content=content, usage=dict(usage), raw=payload)


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
