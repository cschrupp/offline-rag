"""Slice 9A: authoring config, privacy, authorcfg_, silver models, doctor."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from offline_rag.config.loader import load_settings
from offline_rag.config.models import AppSettings, AuthoringSettings
from offline_rag.evaluation.gold import GoldDatasetError, load_gold_dataset
from offline_rag.generation.config_hash import build_generation_config_hash
from offline_rag.gold_authoring.config_hash import (
    build_authoring_config_hash,
    build_authoring_semantic_payload,
)
from offline_rag.gold_authoring.contracts import (
    ADAPTER_CONTRACT,
    AUTHORING_ARTIFACT_CONTRACT,
)
from offline_rag.gold_authoring.models import (
    GoldAuthoringRun,
    HumanReviewStatus,
    SilverCase,
)
from offline_rag.gold_authoring.privacy import (
    AuthoringAuthReason,
    AuthoringPrivacyError,
    authorize_authoring_endpoint,
    authoring_follow_redirects,
    destination_satisfies_policy,
)
from offline_rag.gold_authoring.readiness import (
    authoring_status_label,
    evaluate_authoring_readiness,
)
from offline_rag.gold_authoring.transport import invoke_authorized_authoring_transport

REPO = Path(__file__).resolve().parents[2]
BASE_YAML = REPO / "config" / "base.yaml"


def _authoring(**overrides) -> AuthoringSettings:
    return AuthoringSettings(**overrides)


def _settings(**authoring_overrides) -> AppSettings:
    return AppSettings(authoring=_authoring(**authoring_overrides))


def test_code_defaults_match_base_yaml() -> None:
    from_code = AuthoringSettings()
    loaded = load_settings(yaml_paths=[BASE_YAML], environ={})
    assert loaded.authoring.model_dump(mode="json") == from_code.model_dump(mode="json")


def test_fresh_defaults_not_ready_informational() -> None:
    readiness = evaluate_authoring_readiness(
        load_settings(yaml_paths=[BASE_YAML], environ={})
    )
    assert readiness.ready is False
    assert "disabled" in readiness.reason_codes
    assert readiness.connectivity_checked is False
    assert authoring_status_label(readiness) == "NOT_READY"
    # Disabled authoring must not be treated as a hard doctor error.
    assert not (readiness.enabled and not readiness.ready)


def test_authorcfg_semantic_fields_change_hash() -> None:
    base = _settings(model="m1", approved_models=["m1"], approved_endpoints=["http://127.0.0.1:11434/v1"])
    h0 = build_authoring_config_hash(base)
    assert h0.startswith("authorcfg_")
    payload = build_authoring_semantic_payload(base)
    assert payload["model"] == "m1"
    assert payload["adapter_contract"] == ADAPTER_CONTRACT

    changed_model = _settings(
        model="m2",
        approved_models=["m2"],
        approved_endpoints=["http://127.0.0.1:11434/v1"],
    )
    assert build_authoring_config_hash(changed_model) != h0

    changed_temp = _settings(
        model="m1",
        temperature=0.2,
        approved_models=["m1"],
        approved_endpoints=["http://127.0.0.1:11434/v1"],
    )
    assert build_authoring_config_hash(changed_temp) != h0


def test_authorcfg_excludes_operational_and_privacy_fields() -> None:
    base = _settings(model="m1")
    h0 = build_authoring_config_hash(base)
    assert build_authoring_config_hash(
        _settings(model="m1", enabled=True, network_policy="private_network")
    ) == h0
    assert build_authoring_config_hash(
        _settings(model="m1", base_url="http://127.0.0.1:8888/v1")
    ) == h0
    assert build_authoring_config_hash(
        _settings(
            model="m1",
            approved_endpoints=["http://127.0.0.1:11434/v1", "http://127.0.0.1:9/v1"],
            approved_models=["m1", "extra"],
            timeout_seconds=30,
            api_key="secret",
        )
    ) == h0


def test_null_model_hash_stable() -> None:
    a = build_authoring_config_hash(_settings())
    b = build_authoring_config_hash(_settings(model=None))
    assert a == b
    assert build_authoring_semantic_payload(_settings())["model"] is None


def test_authorcfg_independent_of_gencfg() -> None:
    settings = AppSettings()
    g0 = build_generation_config_hash(settings)
    a0 = build_authoring_config_hash(settings)
    only_authoring = settings.model_copy(
        update={"authoring": settings.authoring.model_copy(update={"temperature": 0.5})}
    )
    assert build_generation_config_hash(only_authoring) == g0
    assert build_authoring_config_hash(only_authoring) != a0
    only_generation = settings.model_copy(
        update={"generation": settings.generation.model_copy(update={"temperature": 0.7})}
    )
    assert build_authoring_config_hash(only_generation) == a0
    assert build_generation_config_hash(only_generation) != g0


def test_privacy_localhost_and_private_network() -> None:
    loop = _settings(
        enabled=True,
        model="m",
        approved_models=["m"],
        approved_endpoints=["http://127.0.0.1:11434/v1"],
        network_policy="localhost_only",
        base_url="http://127.0.0.1:11434/v1",
    )
    assert authorize_authoring_endpoint(loop).endpoint.endswith("/v1")

    lan = _settings(
        enabled=True,
        model="m",
        approved_models=["m"],
        approved_endpoints=["http://192.168.1.10:8080/v1"],
        network_policy="localhost_only",
        base_url="http://192.168.1.10:8080/v1",
    )
    with pytest.raises(AuthoringPrivacyError) as exc:
        authorize_authoring_endpoint(lan)
    assert exc.value.reason == AuthoringAuthReason.NETWORK_POLICY_VIOLATION

    lan_ok = lan.model_copy(
        update={"authoring": lan.authoring.model_copy(update={"network_policy": "private_network"})}
    )
    assert authorize_authoring_endpoint(lan_ok).network_policy == "private_network"

    public = _settings(
        enabled=True,
        model="m",
        approved_models=["m"],
        approved_endpoints=["https://api.openai.com/v1"],
        network_policy="private_network",
        base_url="https://api.openai.com/v1",
    )
    with pytest.raises(AuthoringPrivacyError) as exc2:
        authorize_authoring_endpoint(public)
    assert exc2.value.reason == AuthoringAuthReason.PUBLIC_ADDRESS_NOT_ALLOWED


def test_privacy_requires_authoring_allowlist_not_generation() -> None:
    settings = AppSettings(
        generation=AppSettings().generation.model_copy(
            update={"approved_endpoints": ["http://127.0.0.1:11434/v1"]}
        ),
        authoring=_authoring(
            enabled=True,
            model="m",
            approved_models=["m"],
            approved_endpoints=[],
            base_url="http://127.0.0.1:11434/v1",
        ),
    )
    with pytest.raises(AuthoringPrivacyError) as exc:
        authorize_authoring_endpoint(settings)
    assert exc.value.reason == AuthoringAuthReason.ENDPOINT_NOT_APPROVED


def test_no_redirects_and_fail_before_transport() -> None:
    assert authoring_follow_redirects() is False
    transport = MagicMock(return_value="sent")
    unauthorized = _settings(enabled=True, model="m", approved_models=["m"])
    with pytest.raises(RuntimeError):
        invoke_authorized_authoring_transport(unauthorized, transport)
    transport.assert_not_called()

    authorized = _settings(
        enabled=True,
        model="m",
        approved_models=["m"],
        approved_endpoints=["http://127.0.0.1:11434/v1"],
        base_url="http://127.0.0.1:11434/v1",
    )
    assert invoke_authorized_authoring_transport(authorized, transport) == "sent"
    transport.assert_called_once()


def test_readiness_gates() -> None:
    disabled = evaluate_authoring_readiness(_settings())
    assert disabled.ready is False
    assert authoring_status_label(disabled) == "NOT_READY"
    assert "disabled" in disabled.reason_codes

    ready = evaluate_authoring_readiness(
        _settings(
            enabled=True,
            model="m",
            approved_models=["m"],
            approved_endpoints=["http://127.0.0.1:11434/v1"],
            base_url="http://127.0.0.1:11434/v1",
        )
    )
    assert ready.ready is True
    assert ready.connectivity_checked is False

    missing_model = evaluate_authoring_readiness(
        _settings(
            enabled=True,
            approved_endpoints=["http://127.0.0.1:11434/v1"],
            base_url="http://127.0.0.1:11434/v1",
        )
    )
    assert missing_model.ready is False
    assert "model_unset" in missing_model.reason_codes


def test_doctor_severity_enabled_not_ready_is_hard_error() -> None:
    readiness = evaluate_authoring_readiness(
        _settings(enabled=True, model="qwen-local")
    )
    assert readiness.ready is False
    assert readiness.enabled is True
    # Mirrors cmd_doctor: enabled ∧ NOT READY → hard errors.
    hard_errors = [f"Authoring NOT READY: {r}" for r in readiness.reason_codes]
    assert hard_errors
    assert any("endpoint_not_approved" in e or "model_not_approved" in e for e in hard_errors)


def test_doctor_severity_enabled_ready_has_no_hard_error() -> None:
    readiness = evaluate_authoring_readiness(
        _settings(
            enabled=True,
            model="qwen-local",
            base_url="http://127.0.0.1:11434/v1",
            network_policy="localhost_only",
            approved_endpoints=["http://127.0.0.1:11434/v1"],
            approved_models=["qwen-local"],
        )
    )
    assert readiness.ready is True
    assert readiness.connectivity_checked is False
    hard_errors = (
        [f"Authoring NOT READY: {r}" for r in readiness.reason_codes]
        if readiness.enabled and not readiness.ready
        else []
    )
    assert hard_errors == []


def test_api_key_env_isolation_and_redaction() -> None:
    settings = load_settings(
        yaml_paths=[BASE_YAML],
        environ={
            "OFFLINE_RAG_AUTHORING_API_KEY": "author-secret",
            "OFFLINE_RAG_LLM_API_KEY": "gen-secret",
            "OFFLINE_RAG_AUTHORING_MODEL": "author-model",
            "OFFLINE_RAG_LLM_MODEL": "gen-model",
        },
    )
    assert settings.authoring.api_key == "author-secret"
    assert settings.generation.api_key == "gen-secret"
    assert settings.authoring.model == "author-model"
    assert settings.generation.model == "gen-model"
    assert "author-secret" not in repr(settings.authoring)
    assert "********" in repr(settings.authoring)
    h0 = build_authoring_config_hash(settings)
    rotated = settings.model_copy(
        update={
            "authoring": settings.authoring.model_copy(update={"api_key": "other-secret"})
        }
    )
    assert build_authoring_config_hash(rotated) == h0


def test_no_generation_api_key_inheritance() -> None:
    settings = AppSettings(
        generation=AppSettings().generation.model_copy(update={"api_key": "prod"}),
        authoring=_authoring(api_key=None),
    )
    assert settings.authoring.api_key is None


def test_gold_authoring_run_roundtrip() -> None:
    run = GoldAuthoringRun(
        authoring_run_id="authorrun_test",
        authorcfg_id="authorcfg_" + ("a" * 64),
        network_policy="localhost_only",
        effective_endpoint=None,
        corpus_id=None,
        chunk_set_id=None,
        created_at=datetime(2026, 9, 13, tzinfo=UTC),
        cases=[
            SilverCase(draft_case_id="draft_001", human_status=HumanReviewStatus.PENDING)
        ],
    )
    restored = GoldAuthoringRun.model_validate_json(run.model_dump_json())
    assert restored.schema_version == AUTHORING_ARTIFACT_CONTRACT
    assert restored.cases[0].human_status == HumanReviewStatus.PENDING
    assert restored.cases[0].candidates == []
    assert "api_key" not in run.model_dump()


def test_unknown_human_status_rejected() -> None:
    with pytest.raises(Exception):
        SilverCase.model_validate({"draft_case_id": "d1", "human_status": "maybe"})


def test_gold_loader_rejects_authoring_schema(tmp_path: Path) -> None:
    dataset = tmp_path / "bad"
    dataset.mkdir()
    (dataset / "meta.json").write_text(
        '{"schema_version":"offline-rag-gold-authoring-v1","authoring_run_id":"x"}\n',
        encoding="utf-8",
    )
    (dataset / "cases.jsonl").write_text("\n", encoding="utf-8")
    with pytest.raises(GoldDatasetError, match="silver authoring artifact is not gold"):
        load_gold_dataset(dataset)


def test_accepted_silver_still_not_gold(tmp_path: Path) -> None:
    # Even an accepted silver case cannot be fed as gold meta/cases.
    dataset = tmp_path / "silver"
    dataset.mkdir()
    (dataset / "meta.json").write_text(
        '{"schema_version":"offline-rag-gold-authoring-v1"}\n',
        encoding="utf-8",
    )
    (dataset / "cases.jsonl").write_text(
        '{"draft_case_id":"d1","human_status":"accepted","proposed_query":"q"}\n',
        encoding="utf-8",
    )
    with pytest.raises(GoldDatasetError, match="offline-rag-gold-authoring-v1"):
        load_gold_dataset(dataset)


def test_literal_loopback_ipv6_localhost_only() -> None:
    assert (
        destination_satisfies_policy(
            "http://[::1]:11434/v1", network_policy="localhost_only"
        )
        is None
    )
