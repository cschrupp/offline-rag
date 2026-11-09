from __future__ import annotations

import json
import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Self

import httpx
import pytest

from offline_rag.app.authoring_product_settings import authoring_field_locks
from offline_rag.app.conversation.actions import run_conversation_action
from offline_rag.app.product_settings import generation_field_locks
from offline_rag.app.workspace.models import WorkspaceStatus
from offline_rag.config.deployment_profile import (
    EXTERNAL_API_KEY_ENV,
    EXTERNAL_MODEL_ENV,
    OPENROUTER_BASE_URL,
    PORTFOLIO_OPENROUTER_PROFILE,
)
from offline_rag.config.loader import ConfigError, load_settings
from offline_rag.config.models import AppSettings
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.generation.config_hash import build_generation_config_hash
from offline_rag.generation.openai_compatible import (
    OpenAICompatibleGenerator,
    OpenAICompatibleGeneratorError,
)
from offline_rag.generation.protocol import ChatMessage, GeneratorRequest
from offline_rag.gold_authoring.adapter import (
    AuthoringAdapterError,
    OpenAICompatibleAuthoringAdapter,
)
from offline_rag.gold_authoring.chunk_access import CorpusChunkSnapshot
from offline_rag.gold_authoring.config_hash import build_authoring_config_hash
from offline_rag.gold_authoring.privacy import (
    AuthoringPrivacyError,
    authorize_authoring_endpoint,
)
from offline_rag.gold_authoring.propose import run_gold_propose_on_snapshot

MODEL = "~deepseek/deepseek-flash-latest"
API_KEY = "sk-rel03-test-sentinel-do-not-leak"


class _LiveOpenRouterResolutionBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _block_live_openrouter_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    original_getaddrinfo = socket.getaddrinfo

    def guarded_getaddrinfo(host: object, *args: object, **kwargs: object):
        hostname = str(host).rstrip(".").lower()
        if hostname == "openrouter.ai" or hostname.endswith(".openrouter.ai"):
            raise _LiveOpenRouterResolutionBlocked(
                "REL-03 profile tests must use mocked HTTP transports"
            )
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)


def test_live_openrouter_dns_is_blocked_in_profile_suite() -> None:
    with pytest.raises(_LiveOpenRouterResolutionBlocked):
        socket.getaddrinfo("openrouter.ai", 443)


def _profile_settings(**updates: object) -> AppSettings:
    values: dict[str, object] = {
        "deployment": {"profile": PORTFOLIO_OPENROUTER_PROFILE},
        "generation": {
            "enabled": True,
            "provider": "openai_compatible",
            "base_url": OPENROUTER_BASE_URL,
            "model": MODEL,
            "api_key": API_KEY,
            "approved_endpoints": [OPENROUTER_BASE_URL],
            "approved_models": [MODEL],
        },
        "authoring": {
            "enabled": True,
            "provider": "openai_compatible",
            "base_url": OPENROUTER_BASE_URL,
            "model": MODEL,
            "api_key": API_KEY,
            "approved_endpoints": [OPENROUTER_BASE_URL],
            "approved_models": [MODEL],
            "network_policy": "localhost_only",
        },
        "project": {"strict_offline": False},
    }
    values.update(updates)
    return AppSettings.model_validate(values)


def _load_profile(tmp_path: Path, **extra_env: str) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_DEPLOYMENT_PROFILE": PORTFOLIO_OPENROUTER_PROFILE,
        EXTERNAL_MODEL_ENV: MODEL,
        EXTERNAL_API_KEY_ENV: API_KEY,
        "OFFLINE_RAG_GENERATION_SETTINGS_MODE": "user",
        "OFFLINE_RAG_AUTHORING_SETTINGS_MODE": "user",
        **extra_env,
    }
    return load_settings(yaml_paths=[], environ=environ)


def _completion(content: str, *, model: str = MODEL) -> dict[str, object]:
    return {
        "id": "completion_test",
        "model": model,
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
    }


def test_default_profile_remains_strict_offline_and_local(tmp_path: Path) -> None:
    settings = load_settings(
        yaml_paths=[], environ={"OFFLINE_RAG_DATA_DIR": str(tmp_path / "data")}
    )

    assert settings.project.strict_offline is True
    assert settings.generation.base_url == "http://127.0.0.1:11434/v1"
    assert settings.authoring.base_url == "http://127.0.0.1:11434/v1"
    assert settings.deployment.profile == "standalone_ollama"
    with pytest.raises(AuthoringPrivacyError):
        authorize_authoring_endpoint(settings)


def test_profile_overlay_is_final_and_settings_are_operator_locked(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    settings_dir = data_dir / "settings"
    settings_dir.mkdir(parents=True)
    (settings_dir / "seneca-generation.json").write_text(
        json.dumps(
            {
                "schema_version": "seneca-generation-settings-v1",
                "generation": {
                    "enabled": True,
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "persisted-local-model",
                    "timeout_seconds": 20,
                },
            }
        ),
        encoding="utf-8",
    )
    (settings_dir / "seneca-authoring.json").write_text(
        json.dumps(
            {
                "schema_version": "seneca-authoring-settings-v1",
                "authoring": {
                    "enabled": True,
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "persisted-local-model",
                    "timeout_seconds": 20,
                    "network_policy": "localhost_only",
                },
            }
        ),
        encoding="utf-8",
    )
    yaml_path = tmp_path / "base.yaml"
    yaml_path.write_text(
        "project:\n  strict_offline: true\n"
        "generation:\n  model: yaml-local\n"
        "authoring:\n  model: yaml-local\n",
        encoding="utf-8",
    )
    env = {
        "OFFLINE_RAG_DATA_DIR": str(data_dir),
        "OFFLINE_RAG_DEPLOYMENT_PROFILE": PORTFOLIO_OPENROUTER_PROFILE,
        EXTERNAL_MODEL_ENV: MODEL,
        EXTERNAL_API_KEY_ENV: API_KEY,
        "OFFLINE_RAG_LLM_MODEL": "environment-local",
        "OFFLINE_RAG_AUTHORING_MODEL": "environment-local",
        "OFFLINE_RAG_GENERATION_SETTINGS_MODE": "user",
        "OFFLINE_RAG_AUTHORING_SETTINGS_MODE": "user",
    }
    settings = load_settings(
        yaml_paths=[yaml_path],
        environ=env,
        overrides={
            "generation": {"model": "programmatic-local"},
            "authoring": {"model": "programmatic-local"},
        },
    )

    assert settings.project.strict_offline is False
    assert settings.generation.model == settings.authoring.model == MODEL
    assert (
        settings.generation.base_url
        == settings.authoring.base_url
        == OPENROUTER_BASE_URL
    )
    assert settings.generation.api_key == settings.authoring.api_key == API_KEY
    assert settings.generation.approved_endpoints == [OPENROUTER_BASE_URL]
    assert settings.authoring.approved_endpoints == [OPENROUTER_BASE_URL]
    assert settings.generation.approved_models == [MODEL]
    assert settings.authoring.approved_models == [MODEL]
    assert settings.security.reject_unapproved_generation_endpoint is True
    assert settings.security.reject_unapproved_generation_model is True
    assert all(
        generation_field_locks(deployment_profile=settings.deployment.profile).values()
    )
    assert all(
        authoring_field_locks(deployment_profile=settings.deployment.profile).values()
    )
    assert API_KEY not in repr(settings)
    assert API_KEY not in str(settings.model_dump(mode="json"))
    assert API_KEY not in settings.to_canonical_dict().__repr__()
    assert API_KEY not in build_generation_config_hash(settings)
    assert API_KEY not in build_authoring_config_hash(settings)

    from offline_rag.api.authoring_settings import (
        _authoring_locks,
        _public_authoring_view,
        _readiness_view,
    )
    from offline_rag.api.settings import _generation_locks, _public_generation_view

    assert all(_generation_locks(settings).values())
    assert all(_authoring_locks(settings).values())
    public_views = (
        _public_generation_view(settings.generation),
        _public_authoring_view(settings.authoring),
        _readiness_view(settings),
    )
    assert all(API_KEY not in str(view) for view in public_views)


def test_profile_does_not_redirect_independent_local_subsystems(
    tmp_path: Path,
) -> None:
    yaml_path = tmp_path / "independent-subsystems.yaml"
    yaml_path.write_text(
        """
evaluation:
  generation_semantic_judge:
    enabled: false
    provider: openai_compatible
    base_url: http://127.0.0.1:11436/v1
    model: local-semantic-judge
    network_policy: private_network
    approved_endpoints:
      - http://127.0.0.1:11436/v1
    approved_models:
      - local-semantic-judge
retrieval_recovery:
  enabled: false
  max_retries: 1
  rewriter:
    provider: openai_compatible
    base_url: http://127.0.0.1:11435/v1
    model: local-recovery-rewriter
    approved_endpoints:
      - http://127.0.0.1:11435/v1
    approved_models:
      - local-recovery-rewriter
    network_policy: private_network
""",
        encoding="utf-8",
    )

    settings = load_settings(
        yaml_paths=[yaml_path],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
            "OFFLINE_RAG_DEPLOYMENT_PROFILE": PORTFOLIO_OPENROUTER_PROFILE,
            EXTERNAL_MODEL_ENV: MODEL,
            EXTERNAL_API_KEY_ENV: API_KEY,
        },
    )

    assert settings.generation.base_url == OPENROUTER_BASE_URL
    assert settings.generation.model == MODEL
    assert settings.authoring.base_url == OPENROUTER_BASE_URL
    assert settings.authoring.model == MODEL

    recovery = settings.retrieval_recovery
    assert recovery.enabled is False
    assert recovery.max_retries == 1
    assert recovery.rewriter.base_url == "http://127.0.0.1:11435/v1"
    assert recovery.rewriter.model == "local-recovery-rewriter"
    assert recovery.rewriter.approved_endpoints == [
        "http://127.0.0.1:11435/v1"
    ]
    assert recovery.rewriter.approved_models == ["local-recovery-rewriter"]
    assert recovery.rewriter.network_policy == "private_network"

    judge = settings.evaluation.generation_semantic_judge
    assert judge.enabled is False
    assert judge.base_url == "http://127.0.0.1:11436/v1"
    assert judge.model == "local-semantic-judge"
    assert judge.approved_endpoints == ["http://127.0.0.1:11436/v1"]
    assert judge.approved_models == ["local-semantic-judge"]
    assert judge.network_policy == "private_network"


@pytest.mark.parametrize(
    ("profile", "model", "api_key", "extra"),
    [
        (None, MODEL, API_KEY, {}),
        (PORTFOLIO_OPENROUTER_PROFILE, None, API_KEY, {}),
        (PORTFOLIO_OPENROUTER_PROFILE, MODEL, None, {}),
        (PORTFOLIO_OPENROUTER_PROFILE, MODEL, API_KEY, {EXTERNAL_MODEL_ENV: ""}),
        (PORTFOLIO_OPENROUTER_PROFILE, MODEL, API_KEY, {EXTERNAL_API_KEY_ENV: ""}),
    ],
)
def test_profile_inputs_fail_closed_without_secret_echo(
    tmp_path: Path,
    profile: str | None,
    model: str | None,
    api_key: str | None,
    extra: dict[str, str],
) -> None:
    env = {"OFFLINE_RAG_DATA_DIR": str(tmp_path / "data")}
    if profile is not None:
        env["OFFLINE_RAG_DEPLOYMENT_PROFILE"] = profile
    if model is not None:
        env[EXTERNAL_MODEL_ENV] = model
    if api_key is not None:
        env[EXTERNAL_API_KEY_ENV] = api_key
    env.update(extra)

    with pytest.raises(ConfigError) as exc_info:
        load_settings(yaml_paths=[], environ=env)
    assert API_KEY not in str(exc_info.value)


def test_authoring_profile_exception_is_exact_and_conjunctive() -> None:
    settings = _profile_settings()
    assert authorize_authoring_endpoint(settings).endpoint == OPENROUTER_BASE_URL

    for endpoint in (
        "https://api.openai.com/v1",
        "https://example.com/v1",
        "https://openrouter.ai.example.com/api/v1",
    ):
        candidate = _profile_settings(
            authoring={
                **settings.authoring.model_dump(),
                "base_url": endpoint,
                "approved_endpoints": [endpoint],
            }
        )
        with pytest.raises(AuthoringPrivacyError):
            authorize_authoring_endpoint(candidate)

    for changed in (
        {"approved_endpoints": ["https://example.com/v1"]},
        {
            "approved_endpoints": [
                OPENROUTER_BASE_URL,
                "https://example.com/v1",
            ]
        },
        {"approved_models": ["other-model"]},
        {"api_key": None},
    ):
        authoring = settings.authoring.model_dump()
        authoring.update(changed)
        with pytest.raises(AuthoringPrivacyError):
            authorize_authoring_endpoint(_profile_settings(authoring=authoring))


def test_generator_uses_external_profile_and_preserves_structured_output() -> None:
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json=_completion("A grounded answer."))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    generator = OpenAICompatibleGenerator(_profile_settings(), client=client)
    request = GeneratorRequest(
        messages=(ChatMessage(role="user", content="Question?"),),
        model=MODEL,
        temperature=0,
        max_output_tokens=80,
        response_format={"type": "json_schema", "json_schema": {"name": "answer"}},
    )
    try:
        result = generator.generate(request)
        probe = generator.probe()
    finally:
        client.close()

    assert result.content == "A grounded answer."
    assert result.raw["choices"][0]["message"]["content"] == "A grounded answer."
    assert probe.ok is False  # Mock response is a completion, not /models.
    post_request = observed[0]
    assert str(post_request.url) == f"{OPENROUTER_BASE_URL}/chat/completions"
    assert post_request.headers["Authorization"] == f"Bearer {API_KEY}"
    body = json.loads(post_request.content)
    assert body["model"] == MODEL
    assert body["response_format"]["type"] == "json_schema"
    assert "chat_template_kwargs" not in body
    assert API_KEY not in json.dumps(result.raw)


def test_generator_default_keeps_local_reasoning_field() -> None:
    settings = AppSettings(
        generation={
            "enabled": True,
            "model": "local-model",
            "approved_models": ["local-model"],
        }
    )
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200, json=_completion("local output", model="local-model")
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    generator = OpenAICompatibleGenerator(settings, client=client)
    try:
        generator.generate(
            GeneratorRequest(
                messages=(ChatMessage(role="user", content="Q"),),
                model="local-model",
                temperature=0,
                max_output_tokens=10,
            )
        )
    finally:
        client.close()
    assert captured[0]["chat_template_kwargs"] == {"enable_thinking": False}


def test_authoring_adapter_keeps_local_reasoning_field() -> None:
    settings = AppSettings(
        authoring={
            "enabled": True,
            "model": "local-model",
            "approved_models": ["local-model"],
            "approved_endpoints": ["http://127.0.0.1:11434/v1"],
            "base_url": "http://127.0.0.1:11434/v1",
            "network_policy": "localhost_only",
        }
    )
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=_completion(
                json.dumps(
                    {
                        "query": "What does this synthetic source describe?",
                        "category": "fact",
                        "tags": [],
                        "rationale": None,
                    }
                ),
                model="local-model",
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAuthoringAdapter(settings, client=client)
    try:
        adapter.propose(system_prompt="system", user_content="synthetic context")
    finally:
        client.close()
    assert captured[0]["chat_template_kwargs"] == {"enable_thinking": False}


def test_generator_rejects_secret_echo_and_redacts_provider_error() -> None:
    settings = _profile_settings()
    request = GeneratorRequest(
        messages=(ChatMessage(role="user", content="Question?"),),
        model=MODEL,
        temperature=0,
        max_output_tokens=20,
    )

    echo_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=_completion(API_KEY))
        )
    )
    try:
        with pytest.raises(OpenAICompatibleGeneratorError) as exc_info:
            OpenAICompatibleGenerator(settings, client=echo_client).generate(request)
    finally:
        echo_client.close()
    assert API_KEY not in str(exc_info.value)

    error_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(400, text=f"provider echoed {API_KEY}")
        )
    )
    try:
        with pytest.raises(OpenAICompatibleGeneratorError) as exc_info:
            OpenAICompatibleGenerator(settings, client=error_client).generate(request)
    finally:
        error_client.close()
    assert API_KEY not in str(exc_info.value)

    broadened = _profile_settings(
        generation={
            **_profile_settings().generation.model_dump(),
            "approved_endpoints": [OPENROUTER_BASE_URL, "https://example.com/v1"],
        }
    )
    error_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=_completion("should not send"))
        )
    )
    try:
        with pytest.raises(OpenAICompatibleGeneratorError):
            OpenAICompatibleGenerator(broadened, client=error_client).generate(request)
    finally:
        error_client.close()


def test_probe_accepts_exact_registered_alias() -> None:
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"data": [{"id": MODEL}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    generator = OpenAICompatibleGenerator(_profile_settings(), client=client)
    try:
        result = generator.probe()
    finally:
        client.close()
    assert result.ok is True
    assert result.available_models == (MODEL,)
    assert str(observed[0].url) == f"{OPENROUTER_BASE_URL}/models"
    assert observed[0].headers["Authorization"] == f"Bearer {API_KEY}"


def test_models_probe_rejects_provider_echo_of_secret() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [{"id": API_KEY}]})
        )
    )
    generator = OpenAICompatibleGenerator(_profile_settings(), client=client)
    try:
        result = generator.probe()
    finally:
        client.close()
    assert result.ok is False
    assert result.reason == "endpoint probe returned sensitive data"
    assert API_KEY not in str(result)


def test_authoring_settings_probe_accepts_profile_alias_without_exposing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from offline_rag.api import authoring_settings

    observed: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            observed["client_kwargs"] = kwargs

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, url: str) -> SimpleNamespace:
            observed["url"] = url
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"data": [{"id": MODEL}]},
            )

    monkeypatch.setattr(authoring_settings.httpx, "Client", FakeClient)
    result = authoring_settings._probe_models(
        base_url=OPENROUTER_BASE_URL,
        model=MODEL,
        api_key=API_KEY,
        timeout_seconds=20,
        network_policy="localhost_only",
        approved_endpoints=[OPENROUTER_BASE_URL],
        approved_models=[MODEL],
        deployment_profile=PORTFOLIO_OPENROUTER_PROFILE,
    )

    assert result == {"ok": True, "reason": "ok", "available_models": [MODEL]}
    assert observed["url"] == f"{OPENROUTER_BASE_URL}/models"
    assert API_KEY not in str(result)
    client_kwargs = observed["client_kwargs"]
    assert isinstance(client_kwargs, dict)
    assert client_kwargs["headers"] == {"Authorization": f"Bearer {API_KEY}"}
    assert client_kwargs["follow_redirects"] is False

    class EchoingClient(FakeClient):
        def get(self, url: str) -> SimpleNamespace:
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"data": [{"id": API_KEY}]},
            )

    monkeypatch.setattr(authoring_settings.httpx, "Client", EchoingClient)
    invalid = authoring_settings._probe_models(
        base_url=OPENROUTER_BASE_URL,
        model=MODEL,
        api_key=API_KEY,
        timeout_seconds=20,
        network_policy="localhost_only",
        approved_endpoints=[OPENROUTER_BASE_URL],
        approved_models=[MODEL],
        deployment_profile=PORTFOLIO_OPENROUTER_PROFILE,
    )
    assert invalid == {
        "ok": False,
        "reason": "invalid_response",
        "available_models": [],
    }
    assert API_KEY not in str(invalid)


def test_conversation_action_uses_profile_generator_without_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from offline_rag.app.conversation import actions

    settings = _profile_settings()
    observed: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(json.loads(request.content))
        return httpx.Response(200, json=_completion("Short summary."))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    generator = OpenAICompatibleGenerator(settings, client=client)
    trace_records: list[object] = []
    monkeypatch.setattr(
        actions,
        "WorkspaceStore",
        lambda _: SimpleNamespace(
            get=lambda __: SimpleNamespace(
                status=WorkspaceStatus.ACTIVE,
                current_snapshot_id="snapshot_1",
                revision=3,
            )
        ),
    )
    monkeypatch.setattr(
        actions,
        "ConversationTraceStore",
        lambda _: SimpleNamespace(commit=trace_records.append),
    )
    runtime = SimpleNamespace(
        settings=settings,
        resources=SimpleNamespace(generator_client=generator),
        require_ready=lambda: None,
    )
    try:
        response = run_conversation_action(
            runtime,  # type: ignore[arg-type]
            workspace_id="workspace_1",
            operation="summarize_answer",
            prior_turns=[
                {"role": "user", "text": "Question?"},
                {"role": "assistant", "text": "A detailed answer."},
            ],
            target_assistant_index=1,
            target_language=None,
        )
    finally:
        client.close()

    assert response.answer == "Short summary."
    assert response.answer_origin == "conversation"
    assert response.citations == []
    assert response.query_trace_id is None
    assert len(trace_records) == 1
    trace = trace_records[0]
    assert trace.answer_origin == "conversation"
    assert trace.query_trace_id is None
    assert trace_records[0].resolver_invoked is False
    assert "chat_template_kwargs" not in observed[0]


def test_gold_proposal_application_flow_uses_profile_and_structured_output(
    tmp_path: Path,
) -> None:
    settings = _profile_settings()
    chunk = Chunk(
        chunk_id="chunk_01",
        document_id="doc_01",
        kind=ChunkKind.CHILD,
        text="The cooling loop opens at 82 degrees and closes at 71 degrees.",
        order=0,
        token_count=12,
        content_type="text",
        content_hash="hash_01",
        source_block_ids=["block_01"],
        section_path=["Cooling"],
    )
    snapshot = CorpusChunkSnapshot(
        corpus_name="synthetic",
        corpus_id="corpus_synthetic",
        chunk_set_id="chunkset_synthetic",
        chunks=[chunk],
        source_name_by_document_id={"doc_01": "Synthetic Manual"},
    )
    proposal = json.dumps(
        {
            "query": "At what temperature does the cooling loop open?",
            "category": "fact",
            "tags": ["cooling"],
            "rationale": None,
        }
    )
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json=_completion(proposal))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAuthoringAdapter(settings, client=client)
    try:
        result = run_gold_propose_on_snapshot(
            settings,
            snapshot=snapshot,
            authoring_run_id="authorrun_rel03_test",
            count=1,
            seed=0,
            output=tmp_path / "authoring_run.json",
            adapter=adapter,
        )
    finally:
        client.close()

    assert result.exit_code == 0
    assert result.run is not None
    assert result.run.successful_count == 1
    assert (
        result.run.cases[0].proposed_query
        == "At what temperature does the cooling loop open?"
    )
    request = observed[0]
    assert str(request.url) == f"{OPENROUTER_BASE_URL}/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    body = json.loads(request.content)
    assert body["model"] == MODEL
    assert body["response_format"] == {"type": "json_object"}
    assert "chat_template_kwargs" not in body
    persisted = (tmp_path / "authoring_run.json").read_text(encoding="utf-8")
    assert API_KEY not in persisted


def test_authoring_adapter_fails_closed_if_provider_echoes_secret() -> None:
    settings = _profile_settings()
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=_completion(API_KEY))
        )
    )
    adapter = OpenAICompatibleAuthoringAdapter(settings, client=client)
    try:
        with pytest.raises(AuthoringAdapterError) as exc_info:
            adapter.propose(system_prompt="system", user_content="synthetic")
    finally:
        client.close()
    assert API_KEY not in str(exc_info.value)
