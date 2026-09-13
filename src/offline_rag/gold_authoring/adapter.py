"""OpenAI-compatible authoring adapter (openai-compatible-authoring-v1)."""

from __future__ import annotations

from typing import Any

import httpx

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import DIRECT_OUTPUT_V1
from offline_rag.gold_authoring.contracts import ADAPTER_CONTRACT
from offline_rag.gold_authoring.privacy import (
    AuthoringPrivacyError,
    authorize_authoring_endpoint,
    authoring_follow_redirects,
    normalize_authoring_endpoint,
)
from offline_rag.gold_authoring.readiness import evaluate_authoring_readiness


class AuthoringAdapterError(RuntimeError):
    def __init__(self, message: str, *, failure_reason: str) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


class OpenAICompatibleAuthoringAdapter:
    """Authoring Chat Completions adapter (independent of generation)."""

    contract = ADAPTER_CONTRACT

    def __init__(
        self,
        settings: AppSettings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self._owned_client = client is None
        timeout = float(settings.authoring.timeout_seconds)
        # follow_redirects=False is required by authoring privacy contract.
        self._client = client or httpx.Client(
            timeout=timeout,
            headers=_auth_headers(settings.authoring.api_key),
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    @property
    def base_url(self) -> str:
        return normalize_authoring_endpoint(self.settings.authoring.base_url)

    def _chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def propose(
        self,
        *,
        system_prompt: str,
        user_content: str,
    ) -> str:
        readiness = evaluate_authoring_readiness(self.settings)
        if not readiness.ready:
            raise AuthoringAdapterError(
                f"authoring is not READY: {', '.join(readiness.reason_codes)}",
                failure_reason="authentication_error",
            )
        if authoring_follow_redirects():
            raise AuthoringAdapterError(
                "authoring redirects must remain disabled",
                failure_reason="redirect_not_allowed",
            )
        try:
            authorize_authoring_endpoint(self.settings)
        except AuthoringPrivacyError as exc:
            raise AuthoringAdapterError(
                str(exc),
                failure_reason="authentication_error",
            ) from exc

        auth = self.settings.authoring
        body: dict[str, Any] = {
            "model": auth.model,
            "temperature": float(auth.temperature),
            "max_tokens": int(auth.max_output_tokens),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
        }
        # Explicit direct-output capability for the supported local stack.
        body["chat_template_kwargs"] = {"enable_thinking": False}
        _ = DIRECT_OUTPUT_V1  # documents alignment with direct-output-v1 semantics

        headers = _auth_headers(auth.api_key)
        try:
            response = self._client.post(
                self._chat_url(),
                json=body,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise AuthoringAdapterError(
                f"authoring request timed out: {exc}",
                failure_reason="timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise AuthoringAdapterError(
                f"authoring transport error: {exc}",
                failure_reason="transport_error",
            ) from exc

        if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
            raise AuthoringAdapterError(
                f"authoring redirect not allowed: HTTP {response.status_code}",
                failure_reason="redirect_not_allowed",
            )
        if response.status_code == 401 or response.status_code == 403:
            raise AuthoringAdapterError(
                f"authoring authentication failed: HTTP {response.status_code}",
                failure_reason="authentication_error",
            )
        if response.status_code >= 400:
            raise AuthoringAdapterError(
                f"authoring HTTP error: {response.status_code}",
                failure_reason="http_error",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AuthoringAdapterError(
                "authoring response was not JSON",
                failure_reason="empty_response",
            ) from exc
        return _extract_message_content(payload)


def _extract_message_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise AuthoringAdapterError(
            "invalid completion payload",
            failure_reason="empty_response",
        )
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AuthoringAdapterError(
            "completion missing choices",
            failure_reason="empty_response",
        )
    first = choices[0]
    if not isinstance(first, dict):
        raise AuthoringAdapterError(
            "completion choice invalid",
            failure_reason="empty_response",
        )
    message = first.get("message")
    if not isinstance(message, dict):
        raise AuthoringAdapterError(
            "completion missing message",
            failure_reason="empty_response",
        )
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AuthoringAdapterError(
            "completion missing content",
            failure_reason="empty_response",
        )
    return content
