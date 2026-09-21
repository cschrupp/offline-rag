"""OpenAI-compatible generation-semantic judge adapter + Fake judge."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import DIRECT_OUTPUT_V1
from offline_rag.core.network_policy import (
    NetworkPolicyError,
    destination_satisfies_policy,
    endpoint_in_allowlist,
    http_follow_redirects_allowed,
    normalize_openai_compatible_endpoint,
)
from offline_rag.evaluation.generation_semantic.judge_contracts import (
    ADAPTER_CONTRACT,
    PROBE_TIMEOUT_SECONDS,
    REASONING_CONTRACT,
)
from offline_rag.evaluation.generation_semantic.judge_prompt import (
    JudgePromptBuildError,
    build_generation_semantic_judge_v1_messages,
)
from offline_rag.evaluation.generation_semantic.judge_protocol import (
    GenerationSemanticJudgeError,
    GenerationSemanticJudgeRequest,
    GenerationSemanticJudgeResponse,
)
from offline_rag.evaluation.generation_semantic.judge_schema import (
    parse_generation_semantic_judge_output_v1,
)


@dataclass(frozen=True, slots=True)
class JudgeProbeResult:
    ok: bool
    reason: str
    available_models: tuple[str, ...] = ()


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


class OpenAICompatibleGenerationSemanticJudge:
    """HTTP adapter for generation-semantic-judge-v1 Chat Completions."""

    contract = ADAPTER_CONTRACT

    def __init__(
        self,
        settings: AppSettings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self._owned_client = client is None
        judge = settings.evaluation.generation_semantic_judge
        timeout = float(judge.timeout_seconds)
        self._client = client or httpx.Client(
            timeout=timeout,
            headers=_auth_headers(judge.api_key),
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    @property
    def base_url(self) -> str:
        return normalize_openai_compatible_endpoint(
            self.settings.evaluation.generation_semantic_judge.base_url
        )

    def _chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _models_url(self) -> str:
        return f"{self.base_url}/models"

    def probe(self) -> JudgeProbeResult:
        judge = self.settings.evaluation.generation_semantic_judge
        try:
            normalize_openai_compatible_endpoint(judge.base_url)
        except NetworkPolicyError as exc:
            return JudgeProbeResult(ok=False, reason=str(exc))
        if not endpoint_in_allowlist(judge.base_url, list(judge.approved_endpoints)):
            return JudgeProbeResult(
                ok=False, reason="configured judge endpoint is not approved"
            )
        policy = destination_satisfies_policy(
            judge.base_url, network_policy=judge.network_policy
        )
        if policy is not None:
            return JudgeProbeResult(
                ok=False,
                reason=f"judge endpoint rejected by network_policy={judge.network_policy}",
            )
        if judge.model is None or judge.model not in judge.approved_models:
            return JudgeProbeResult(
                ok=False, reason="configured judge model is not approved"
            )
        try:
            response = self._client.get(
                self._models_url(),
                timeout=PROBE_TIMEOUT_SECONDS,
                headers=_auth_headers(judge.api_key),
            )
        except httpx.TimeoutException:
            return JudgeProbeResult(ok=False, reason="judge probe timeout/unreachable")
        except httpx.HTTPError as exc:
            return JudgeProbeResult(ok=False, reason=f"judge probe unreachable: {exc}")
        if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
            return JudgeProbeResult(ok=False, reason="judge redirect not allowed")
        if response.status_code >= 400:
            return JudgeProbeResult(
                ok=False, reason=f"judge /models HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return JudgeProbeResult(ok=False, reason="judge /models returned non-JSON")
        models: list[str] = []
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    models.append(item["id"])
        if judge.model not in models:
            return JudgeProbeResult(
                ok=False,
                reason=f"configured judge model not listed by /models: {judge.model}",
                available_models=tuple(models),
            )
        return JudgeProbeResult(ok=True, reason="ok", available_models=tuple(models))

    def judge(
        self, request: GenerationSemanticJudgeRequest
    ) -> GenerationSemanticJudgeResponse:
        if http_follow_redirects_allowed():
            raise GenerationSemanticJudgeError(
                "judge redirects must remain disabled",
                failure_reason="redirect_not_allowed",
            )
        judge = self.settings.evaluation.generation_semantic_judge
        if not endpoint_in_allowlist(judge.base_url, list(judge.approved_endpoints)):
            raise GenerationSemanticJudgeError(
                "configured judge endpoint is not approved",
                failure_reason="authentication_error",
            )
        policy = destination_satisfies_policy(
            judge.base_url, network_policy=judge.network_policy
        )
        if policy is not None:
            raise GenerationSemanticJudgeError(
                f"judge endpoint rejected by network_policy={judge.network_policy}",
                failure_reason="authentication_error",
            )

        try:
            messages = build_generation_semantic_judge_v1_messages(
                query=request.query,
                evidence_units=request.evidence_units,
                answer_text=request.answer_text,
                citation_ids=request.citation_ids,
                source_name_by_document_id=request.source_name_by_document_id,
            )
        except JudgePromptBuildError as exc:
            raise GenerationSemanticJudgeError(
                str(exc), failure_reason="prompt_build_error"
            ) from exc

        body: dict[str, Any] = {
            "model": judge.model,
            "temperature": 0.0,
            "max_tokens": int(judge.max_output_tokens),
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if REASONING_CONTRACT == DIRECT_OUTPUT_V1:
            body["chat_template_kwargs"] = {"enable_thinking": False}

        t0 = time.perf_counter()
        try:
            response = self._client.post(
                self._chat_url(),
                json=body,
                headers=_auth_headers(judge.api_key),
            )
        except httpx.TimeoutException as exc:
            raise GenerationSemanticJudgeError(
                f"judge request timed out: {exc}",
                failure_reason="timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise GenerationSemanticJudgeError(
                f"judge transport error: {exc}",
                failure_reason="transport_error",
            ) from exc
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
            raise GenerationSemanticJudgeError(
                f"judge redirect not allowed: HTTP {response.status_code}",
                failure_reason="redirect_not_allowed",
            )
        if response.status_code >= 400:
            raise GenerationSemanticJudgeError(
                f"judge HTTP error: {response.status_code}",
                failure_reason="http_error",
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise GenerationSemanticJudgeError(
                "judge response was not JSON",
                failure_reason="invalid_json",
            ) from exc

        content = _extract_message_content(payload)
        if content is None or not str(content).strip():
            raise GenerationSemanticJudgeError(
                "judge returned empty response",
                failure_reason="empty_response",
            )
        try:
            raw_obj = json.loads(content)
        except json.JSONDecodeError as exc:
            raise GenerationSemanticJudgeError(
                "judge content was not JSON",
                failure_reason="invalid_json",
            ) from exc
        try:
            parsed = parse_generation_semantic_judge_output_v1(
                raw_obj, allowed_citation_ids=list(request.citation_ids)
            )
        except Exception as exc:
            raise GenerationSemanticJudgeError(
                f"judge schema invalid: {exc}",
                failure_reason="schema_invalid",
            ) from exc
        return GenerationSemanticJudgeResponse(
            output=parsed,
            latency_ms=latency_ms,
            raw_content=content,
        )


def _extract_message_content(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


class FakeGenerationSemanticJudge:
    """Deterministic injectable judge for unit/CI tests."""

    contract = ADAPTER_CONTRACT

    def __init__(
        self,
        *,
        output: Mapping[str, Any] | None = None,
        output_fn: Callable[[GenerationSemanticJudgeRequest], Mapping[str, Any] | str]
        | None = None,
        raise_on_judge: Exception | None = None,
        probe_ok: bool = True,
        available_models: tuple[str, ...] = (),
        latency_ms: int = 1,
    ) -> None:
        self._output = dict(output) if output is not None else None
        self._output_fn = output_fn
        self._raise_on_judge = raise_on_judge
        self._probe_ok = probe_ok
        self._available_models = available_models
        self._latency_ms = latency_ms
        self.judge_calls = 0
        self.probe_calls = 0
        self.last_request: GenerationSemanticJudgeRequest | None = None
        self.last_messages: list[dict[str, str]] | None = None

    def close(self) -> None:
        return None

    def probe(self) -> JudgeProbeResult:
        self.probe_calls += 1
        if not self._probe_ok:
            return JudgeProbeResult(ok=False, reason="fake judge probe failed")
        return JudgeProbeResult(
            ok=True,
            reason="ok",
            available_models=self._available_models,
        )

    def judge(
        self, request: GenerationSemanticJudgeRequest
    ) -> GenerationSemanticJudgeResponse:
        self.judge_calls += 1
        self.last_request = request
        self.last_messages = build_generation_semantic_judge_v1_messages(
            query=request.query,
            evidence_units=request.evidence_units,
            answer_text=request.answer_text,
            citation_ids=request.citation_ids,
            source_name_by_document_id=request.source_name_by_document_id,
        )
        if self._raise_on_judge is not None:
            raise self._raise_on_judge
        if self._output_fn is not None:
            raw = self._output_fn(request)
            if isinstance(raw, str):
                raise GenerationSemanticJudgeError(raw, failure_reason="invalid_json")
            payload = dict(raw)
        elif self._output is not None:
            payload = dict(self._output)
        else:
            raise GenerationSemanticJudgeError(
                "no fake judge output configured",
                failure_reason="empty_response",
            )
        parsed = parse_generation_semantic_judge_output_v1(
            payload, allowed_citation_ids=list(request.citation_ids)
        )
        return GenerationSemanticJudgeResponse(
            output=parsed,
            latency_ms=self._latency_ms,
            raw_content=json.dumps(payload),
        )
