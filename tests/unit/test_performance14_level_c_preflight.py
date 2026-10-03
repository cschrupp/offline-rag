"""Unit tests for Level-C execution-readiness preflight (no live provider)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from offline_rag.config.models import AppSettings
from offline_rag.evaluation.performance_14.contracts import Performance14Error
from offline_rag.evaluation.performance_14.preflight_14_level_c import (
    FREEZE_AUTHORITY_LEVEL_C,
    LOCKED_CTXCFG_LEVEL_C,
    LOCKED_GENCFG_LEVEL_C,
    LOCKED_PERFCFG_LEVEL_C,
    LOCKED_PERFSUITE_LEVEL_C,
    assert_embedding_artifacts_ready,
    assert_freeze_authority_reachable,
    assert_frozen_suite_protocol_and_identities,
    assert_recovery_disabled,
    assert_runtime_context_matches_freeze,
    assert_runtime_generation_matches_freeze,
    assert_working_tree_clean_for_level_c,
    load_level_c_runtime_settings,
    run_level_c_execution_preflight,
)
from offline_rag.evaluation.performance_14.suite_14_level_c import (
    EXPECTED_GENERATION_ENDPOINT_LEVEL_C,
    GENERATION_MODEL_LEVEL_C,
    INSTRUMENTATION_AUTHORITY_LEVEL_C,
    effective_config_id_level_c,
    generation_config_hash_level_c,
    load_frozen_suite_artifact_level_c,
)
from offline_rag.evaluation.performance_14.suite_14c import QUERY_IDS_14C
from offline_rag.generation.protocol import GeneratorProbeResult

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET_API_KEY = "test-secret-api-key-do-not-leak-9f3c2a1b"


def _llm_env(**overrides: str) -> dict[str, str]:
    env = {
        "OFFLINE_RAG_LLM_MODEL": GENERATION_MODEL_LEVEL_C,
        "OFFLINE_RAG_APPROVED_LLM_MODELS": GENERATION_MODEL_LEVEL_C,
        "OFFLINE_RAG_LLM_BASE_URL": EXPECTED_GENERATION_ENDPOINT_LEVEL_C,
        "OFFLINE_RAG_APPROVED_LLM_ENDPOINTS": EXPECTED_GENERATION_ENDPOINT_LEVEL_C,
        "OFFLINE_RAG_LLM_TIMEOUT_SECONDS": "300",
    }
    env.update(overrides)
    return env


def _load_runtime(
    tmp_path: Path,
    *,
    environ: dict[str, str] | None = None,
    dotenv_text: str | None = None,
) -> AppSettings:
    if dotenv_text is not None:
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text(dotenv_text, encoding="utf-8")
    else:
        dotenv_path = tmp_path / "missing.env"
    return load_level_c_runtime_settings(
        REPO_ROOT,
        environ=environ if environ is not None else _llm_env(),
        dotenv_path=dotenv_path,
    )


def _frozen():
    return load_frozen_suite_artifact_level_c(repo_root=REPO_ROOT)


# ---------------------------------------------------------------------------
# Scientific identity regression
# ---------------------------------------------------------------------------


def test_scientific_identities_unchanged() -> None:
    frozen = _frozen()
    assert frozen.suite_identity_hash == LOCKED_PERFSUITE_LEVEL_C
    assert frozen.effective_config_id == LOCKED_PERFCFG_LEVEL_C
    assert frozen.generation_config_hash == LOCKED_GENCFG_LEVEL_C
    assert frozen.context_config_hash == LOCKED_CTXCFG_LEVEL_C
    assert generation_config_hash_level_c() == LOCKED_GENCFG_LEVEL_C
    assert effective_config_id_level_c(repo_root=REPO_ROOT) == LOCKED_PERFCFG_LEVEL_C
    assert frozen.level_c_instrumentation_authority == INSTRUMENTATION_AUTHORITY_LEVEL_C
    assert FREEZE_AUTHORITY_LEVEL_C.startswith("f3ff6de")


def test_accepted_frozen_suite_static_identity_checks() -> None:
    suite_id, cfg_id = assert_frozen_suite_protocol_and_identities(REPO_ROOT)
    assert suite_id == LOCKED_PERFSUITE_LEVEL_C
    assert cfg_id == LOCKED_PERFCFG_LEVEL_C


def test_freeze_authority_must_be_ancestor() -> None:
    assert_freeze_authority_reachable(REPO_ROOT)


def test_freeze_authority_not_ancestor_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.subprocess.run",
        lambda *a, **k: MagicMock(returncode=1),
    )
    with pytest.raises(Performance14Error, match="not an ancestor"):
        assert_freeze_authority_reachable(REPO_ROOT)


# ---------------------------------------------------------------------------
# Runtime settings / dotenv
# ---------------------------------------------------------------------------


def test_dotenv_applied_to_copied_environment(tmp_path: Path) -> None:
    settings = _load_runtime(
        tmp_path,
        environ={},
        dotenv_text=(
            f"OFFLINE_RAG_LLM_MODEL={GENERATION_MODEL_LEVEL_C}\n"
            f"OFFLINE_RAG_APPROVED_LLM_MODELS={GENERATION_MODEL_LEVEL_C}\n"
            f"OFFLINE_RAG_LLM_BASE_URL={EXPECTED_GENERATION_ENDPOINT_LEVEL_C}\n"
            f"OFFLINE_RAG_APPROVED_LLM_ENDPOINTS={EXPECTED_GENERATION_ENDPOINT_LEVEL_C}\n"
            "OFFLINE_RAG_LLM_TIMEOUT_SECONDS=300\n"
        ),
    )
    assert settings.generation.model == GENERATION_MODEL_LEVEL_C
    assert settings.generation.timeout_seconds == 300


def test_supplied_environment_wins_over_dotenv(tmp_path: Path) -> None:
    settings = _load_runtime(
        tmp_path,
        environ=_llm_env(OFFLINE_RAG_LLM_TIMEOUT_SECONDS="300"),
        dotenv_text="OFFLINE_RAG_LLM_TIMEOUT_SECONDS=120\n",
    )
    assert settings.generation.timeout_seconds == 300


def test_global_os_environ_not_mutated(tmp_path: Path) -> None:
    marker = "OFFLINE_RAG_LEVEL_C_PREFLIGHT_MUTATION_PROBE"
    assert marker not in os.environ
    _load_runtime(
        tmp_path,
        environ={},
        dotenv_text=f"{marker}=should_not_escape\n" + "\n".join(
            f"{k}={v}" for k, v in _llm_env().items()
        ),
    )
    assert marker not in os.environ


# ---------------------------------------------------------------------------
# Generation runtime pin
# ---------------------------------------------------------------------------


def test_exact_model_and_endpoint_and_timeout_accepted(tmp_path: Path) -> None:
    settings = _load_runtime(tmp_path, environ=_llm_env())
    frozen = _frozen()
    gencfg = assert_runtime_generation_matches_freeze(
        settings,
        frozen_generation_semantic_payload=frozen.generation_semantic_payload,
    )
    assert gencfg == LOCKED_GENCFG_LEVEL_C


def test_wrong_model_fails(tmp_path: Path) -> None:
    settings = _load_runtime(
        tmp_path,
        environ=_llm_env(
            OFFLINE_RAG_LLM_MODEL="other-model",
            OFFLINE_RAG_APPROVED_LLM_MODELS="other-model",
        ),
    )
    with pytest.raises(Performance14Error, match="generation.model"):
        assert_runtime_generation_matches_freeze(
            settings,
            frozen_generation_semantic_payload=_frozen().generation_semantic_payload,
        )


def test_approved_model_list_drift_fails(tmp_path: Path) -> None:
    settings = _load_runtime(
        tmp_path,
        environ=_llm_env(
            OFFLINE_RAG_APPROVED_LLM_MODELS=f"{GENERATION_MODEL_LEVEL_C},extra-model"
        ),
    )
    with pytest.raises(Performance14Error, match="approved_models"):
        assert_runtime_generation_matches_freeze(
            settings,
            frozen_generation_semantic_payload=_frozen().generation_semantic_payload,
        )


def test_wrong_selected_endpoint_fails(tmp_path: Path) -> None:
    settings = _load_runtime(
        tmp_path,
        environ=_llm_env(
            OFFLINE_RAG_LLM_BASE_URL="http://127.0.0.1:9999/v1",
            OFFLINE_RAG_APPROVED_LLM_ENDPOINTS="http://127.0.0.1:9999/v1",
        ),
    )
    with pytest.raises(Performance14Error, match="expected endpoint"):
        assert_runtime_generation_matches_freeze(
            settings,
            frozen_generation_semantic_payload=_frozen().generation_semantic_payload,
        )


def test_selected_endpoint_not_authorized_fails(tmp_path: Path) -> None:
    settings = _load_runtime(
        tmp_path,
        environ=_llm_env(
            OFFLINE_RAG_LLM_BASE_URL=EXPECTED_GENERATION_ENDPOINT_LEVEL_C,
            OFFLINE_RAG_APPROVED_LLM_ENDPOINTS="http://127.0.0.1:11434/v1",
        ),
    )
    with pytest.raises(Performance14Error, match="not authorized"):
        assert_runtime_generation_matches_freeze(
            settings,
            frozen_generation_semantic_payload=_frozen().generation_semantic_payload,
        )


def test_timeout_120_fails(tmp_path: Path) -> None:
    settings = _load_runtime(
        tmp_path,
        environ=_llm_env(OFFLINE_RAG_LLM_TIMEOUT_SECONDS="120"),
    )
    with pytest.raises(Performance14Error, match="timeout_seconds"):
        assert_runtime_generation_matches_freeze(
            settings,
            frozen_generation_semantic_payload=_frozen().generation_semantic_payload,
        )


def test_reject_unapproved_endpoint_false_fails(tmp_path: Path) -> None:
    settings = _load_runtime(tmp_path, environ=_llm_env())
    settings = settings.model_copy(
        update={
            "security": settings.security.model_copy(
                update={"reject_unapproved_generation_endpoint": False}
            )
        }
    )
    with pytest.raises(
        Performance14Error, match="reject_unapproved_generation_endpoint"
    ):
        assert_runtime_generation_matches_freeze(
            settings,
            frozen_generation_semantic_payload=_frozen().generation_semantic_payload,
        )


def test_reject_unapproved_model_false_fails(tmp_path: Path) -> None:
    settings = _load_runtime(tmp_path, environ=_llm_env())
    settings = settings.model_copy(
        update={
            "security": settings.security.model_copy(
                update={"reject_unapproved_generation_model": False}
            )
        }
    )
    with pytest.raises(Performance14Error, match="reject_unapproved_generation_model"):
        assert_runtime_generation_matches_freeze(
            settings,
            frozen_generation_semantic_payload=_frozen().generation_semantic_payload,
        )


def test_locked_gencfg_equality(tmp_path: Path) -> None:
    settings = _load_runtime(tmp_path, environ=_llm_env())
    assert (
        assert_runtime_generation_matches_freeze(
            settings,
            frozen_generation_semantic_payload=_frozen().generation_semantic_payload,
        )
        == LOCKED_GENCFG_LEVEL_C
    )


def test_generation_semantic_drift_fails(tmp_path: Path) -> None:
    settings = _load_runtime(tmp_path, environ=_llm_env())
    drifted = dict(_frozen().generation_semantic_payload)
    drifted["temperature"] = 0.5
    with pytest.raises(Performance14Error, match="generation_semantic_payload"):
        assert_runtime_generation_matches_freeze(
            settings,
            frozen_generation_semantic_payload=drifted,
        )


# ---------------------------------------------------------------------------
# Context / recovery
# ---------------------------------------------------------------------------


def test_locked_ctxcfg_equality(tmp_path: Path) -> None:
    settings = _load_runtime(tmp_path, environ=_llm_env())
    assert (
        assert_runtime_context_matches_freeze(
            settings,
            frozen_context_semantic_payload=_frozen().context_semantic_payload,
        )
        == LOCKED_CTXCFG_LEVEL_C
    )


def test_context_semantic_drift_fails(tmp_path: Path) -> None:
    settings = _load_runtime(tmp_path, environ=_llm_env())
    drifted = dict(_frozen().context_semantic_payload)
    drifted["anchor_k"] = 99
    with pytest.raises(Performance14Error, match="context_semantic_payload"):
        assert_runtime_context_matches_freeze(
            settings,
            frozen_context_semantic_payload=drifted,
        )


def test_recovery_true_fails(tmp_path: Path) -> None:
    settings = _load_runtime(tmp_path, environ=_llm_env())
    settings = settings.model_copy(
        update={
            "retrieval_recovery": settings.retrieval_recovery.model_copy(
                update={"enabled": True}
            )
        }
    )
    with pytest.raises(Performance14Error, match="retrieval_recovery.enabled"):
        assert_recovery_disabled(settings)


# ---------------------------------------------------------------------------
# Dirty tree / gold / index / artifacts (via monkeypatch or direct assert)
# ---------------------------------------------------------------------------


def test_dirty_tree_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.capture_working_tree_state",
        lambda _root: ("dirty", "1 dirty path(s)"),
    )
    with pytest.raises(Performance14Error, match="clean working tree"):
        assert_working_tree_clean_for_level_c(REPO_ROOT)


def test_gold_membership_drift_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_gold_dir: Path) -> None:
        raise Performance14Error("Gold case membership diverges from locked QUERY_IDS_14C")

    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.assert_gold_semantic_identity_14c",
        _boom,
    )
    with pytest.raises(Performance14Error, match="Gold case membership"):
        from offline_rag.evaluation.performance_14.preflight_14_level_c import (
            assert_gold_semantic_identity_14c,
        )

        assert_gold_semantic_identity_14c(REPO_ROOT)


def test_dense_index_drift_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )

    def _boom(**_kwargs: Any) -> None:
        raise Performance14Error("CURRENT dense index_id diverges from frozen 14C pin")

    # Override the OK stub from _patch_local_checks_ok with a failing pin check.
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.assert_index_and_config_pins",
        _boom,
    )
    with pytest.raises(Performance14Error, match="dense index_id"):
        run_level_c_execution_preflight(
            repo_root=REPO_ROOT,
            environ=_llm_env(),
            dotenv_path=tmp_path / "no.env",
            provider_probe="skip",
        )


def test_lexical_index_drift_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )

    def _boom(**_kwargs: Any) -> None:
        raise Performance14Error(
            "CURRENT lexical index_id diverges from frozen 14C pin"
        )

    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.assert_index_and_config_pins",
        _boom,
    )
    with pytest.raises(Performance14Error, match="lexical index_id"):
        run_level_c_execution_preflight(
            repo_root=REPO_ROOT,
            environ=_llm_env(),
            dotenv_path=tmp_path / "no.env",
            provider_probe="skip",
        )


def test_reranker_model_path_missing_fails(tmp_path: Path) -> None:
    from offline_rag.evaluation.performance_14.preflight_14c import (
        assert_index_and_config_pins,
        load_hybrid_settings,
    )

    hybrid = load_hybrid_settings(REPO_ROOT)
    missing = tmp_path / "missing-reranker"
    rerank = load_level_c_runtime_settings(
        REPO_ROOT,
        environ=_llm_env(),
        dotenv_path=tmp_path / "no.env",
    )
    # Force hybrid_rerank-like settings with missing path.
    rerank = rerank.model_copy(
        update={
            "reranker": rerank.reranker.model_copy(
                update={
                    "enabled": True,
                    "model": rerank.reranker.model.model_copy(
                        update={"model_path": missing}
                    ),
                }
            )
        }
    )
    with pytest.raises(Performance14Error, match="reranker model path missing"):
        assert_index_and_config_pins(hybrid_settings=hybrid, rerank_settings=rerank)


def test_embedding_artifact_absence_fails(tmp_path: Path) -> None:
    settings = _load_runtime(tmp_path, environ=_llm_env())
    missing = tmp_path / "no-embedding"
    settings = settings.model_copy(
        update={
            "dense": settings.dense.model_copy(update={"model_path": missing}),
            "paths": settings.paths.model_copy(
                update={"embedding_artifacts": tmp_path / "emb"}
            ),
        }
    )
    with pytest.raises(Performance14Error, match="embedding model artifacts"):
        assert_embedding_artifacts_ready(settings)


# ---------------------------------------------------------------------------
# Orchestrator helpers
# ---------------------------------------------------------------------------


def _patch_local_checks_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.assert_working_tree_clean_for_level_c",
        lambda _root: None,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.assert_index_and_config_pins",
        lambda **_k: None,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.assert_embedding_artifacts_ready",
        lambda _settings: Path("/tmp/fake-embedding"),
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.observe_ram_rss_bytes",
        lambda: ("unavailable", None),
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.observe_vram",
        lambda: ("unavailable", None, None, None),
    )


def test_output_write_failure_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )

    def _deny_write(self: Path, *_a: Any, **_k: Any) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(Path, "write_text", _deny_write)
    with pytest.raises(Performance14Error):
        run_level_c_execution_preflight(
            repo_root=REPO_ROOT,
            environ=_llm_env(),
            dotenv_path=tmp_path / "no.env",
            provider_probe="skip",
        )


def test_insufficient_disk_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.shutil.disk_usage",
        lambda _p: MagicMock(free=1),
    )
    with pytest.raises(Performance14Error, match="insufficient disk"):
        run_level_c_execution_preflight(
            repo_root=REPO_ROOT,
            environ=_llm_env(),
            dotenv_path=tmp_path / "no.env",
            provider_probe="skip",
        )


def test_provider_probe_skip_zero_calls_and_not_execution_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )
    calls: list[str] = []

    def _probe(_settings: AppSettings) -> GeneratorProbeResult:
        calls.append("probe")
        return GeneratorProbeResult(ok=True, reason="ok")

    ctx = run_level_c_execution_preflight(
        repo_root=REPO_ROOT,
        environ=_llm_env(),
        dotenv_path=tmp_path / "no.env",
        provider_probe="skip",
        provider_probe_fn=_probe,
    )
    assert calls == []
    assert ctx.provider_probe_performed is False
    assert ctx.provider_probe_ok is None
    assert ctx.execution_ready is False
    assert ctx.suite_id == LOCKED_PERFSUITE_LEVEL_C
    assert ctx.scientific_config_id == LOCKED_PERFCFG_LEVEL_C
    assert ctx.generation_config_id == LOCKED_GENCFG_LEVEL_C
    assert ctx.context_config_id == LOCKED_CTXCFG_LEVEL_C
    assert ctx.machine_profile_id.startswith("perfhost_")
    assert ctx.preflight_record.telemetry_ram == "unavailable"
    assert ctx.preflight_record.telemetry_vram == "unavailable"


def test_required_fake_probe_success_sets_execution_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )
    calls: list[str] = []

    def _probe(_settings: AppSettings) -> GeneratorProbeResult:
        calls.append("probe")
        return GeneratorProbeResult(ok=True, reason="ok")

    ctx = run_level_c_execution_preflight(
        repo_root=REPO_ROOT,
        environ=_llm_env(),
        dotenv_path=tmp_path / "no.env",
        provider_probe="require",
        provider_probe_fn=_probe,
    )
    assert calls == ["probe"]
    assert ctx.provider_probe_performed is True
    assert ctx.provider_probe_ok is True
    assert ctx.execution_ready is True


def test_required_fake_probe_failure_fails_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )

    def _probe(_settings: AppSettings) -> GeneratorProbeResult:
        return GeneratorProbeResult(ok=False, reason="configured model is not available")

    with pytest.raises(Performance14Error, match="provider readiness probe failed"):
        run_level_c_execution_preflight(
            repo_root=REPO_ROOT,
            environ=_llm_env(),
            dotenv_path=tmp_path / "no.env",
            provider_probe="require",
            provider_probe_fn=_probe,
        )


def test_required_mode_invokes_probe_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )
    calls = {"n": 0}

    def _probe(_settings: AppSettings) -> GeneratorProbeResult:
        calls["n"] += 1
        return GeneratorProbeResult(ok=True, reason="ok")

    run_level_c_execution_preflight(
        repo_root=REPO_ROOT,
        environ=_llm_env(),
        dotenv_path=tmp_path / "no.env",
        provider_probe="require",
        provider_probe_fn=_probe,
    )
    assert calls["n"] == 1


def test_api_key_does_not_leak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )
    env = _llm_env(OFFLINE_RAG_LLM_API_KEY=SECRET_API_KEY)
    ctx = run_level_c_execution_preflight(
        repo_root=REPO_ROOT,
        environ=env,
        dotenv_path=tmp_path / "no.env",
        provider_probe="skip",
    )
    assert ctx.runtime_settings.generation.api_key is None
    assert ctx.api_key_configured is True
    dumped = str(ctx.preflight_record.model_dump(mode="json"))
    assert SECRET_API_KEY not in dumped
    assert SECRET_API_KEY not in str(ctx.preflight_record)
    assert SECRET_API_KEY not in str(ctx.runtime_settings.model_dump(mode="json"))
    assert SECRET_API_KEY not in repr(ctx)

    def _probe(_settings: AppSettings) -> GeneratorProbeResult:
        return GeneratorProbeResult(
            ok=False,
            reason=f"auth failed for key {SECRET_API_KEY}",
        )

    with pytest.raises(Performance14Error) as excinfo:
        run_level_c_execution_preflight(
            repo_root=REPO_ROOT,
            environ=env,
            dotenv_path=tmp_path / "no.env",
            provider_probe="require",
            provider_probe_fn=_probe,
        )
    assert SECRET_API_KEY not in str(excinfo.value)
    record = excinfo.value.preflight_record  # type: ignore[attr-defined]
    assert SECRET_API_KEY not in str(record.model_dump(mode="json"))


def test_secret_bearing_probe_receives_transient_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )
    seen: dict[str, str | None] = {}

    def _probe(settings: AppSettings) -> GeneratorProbeResult:
        seen["api_key"] = settings.generation.api_key
        return GeneratorProbeResult(ok=True, reason="ok")

    ctx = run_level_c_execution_preflight(
        repo_root=REPO_ROOT,
        environ=_llm_env(OFFLINE_RAG_LLM_API_KEY=SECRET_API_KEY),
        dotenv_path=tmp_path / "no.env",
        provider_probe="require",
        provider_probe_fn=_probe,
    )
    assert seen["api_key"] == SECRET_API_KEY
    assert ctx.runtime_settings.generation.api_key is None
    assert ctx.api_key_configured is True
    assert SECRET_API_KEY not in str(ctx.runtime_settings.model_dump(mode="json"))


def test_runtime_data_dir_override_reaches_substrate_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    alt_data = tmp_path / "alt_data"
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )
    captured: dict[str, Path] = {}

    def _capture(*, hybrid_settings: AppSettings, rerank_settings: AppSettings) -> None:
        captured["hybrid_corpora"] = Path(hybrid_settings.paths.corpora)
        captured["hybrid_qdrant"] = Path(hybrid_settings.paths.qdrant_storage)
        captured["rerank_corpora"] = Path(rerank_settings.paths.corpora)
        raise Performance14Error("stop-after-capture")

    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.assert_index_and_config_pins",
        _capture,
    )
    with pytest.raises(Performance14Error, match="stop-after-capture"):
        run_level_c_execution_preflight(
            repo_root=REPO_ROOT,
            environ=_llm_env(OFFLINE_RAG_DATA_DIR=str(alt_data)),
            dotenv_path=tmp_path / "no.env",
            provider_probe="skip",
        )
    expected_corpora = (alt_data / "corpora").resolve()
    expected_qdrant = (alt_data / "qdrant").resolve()
    assert captured["hybrid_corpora"].resolve() == expected_corpora
    assert captured["rerank_corpora"].resolve() == expected_corpora
    assert captured["hybrid_qdrant"].resolve() == expected_qdrant
    default_corpora = (REPO_ROOT / "data" / "corpora").resolve()
    assert captured["hybrid_corpora"].resolve() != default_corpora


def test_malformed_runtime_env_becomes_performance14_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.assert_working_tree_clean_for_level_c",
        lambda _root: None,
    )
    with pytest.raises(Performance14Error) as excinfo:
        run_level_c_execution_preflight(
            repo_root=REPO_ROOT,
            environ=_llm_env(
                OFFLINE_RAG_LLM_TIMEOUT_SECONDS="not-an-integer",
                OFFLINE_RAG_LLM_API_KEY=SECRET_API_KEY,
            ),
            dotenv_path=tmp_path / "no.env",
            provider_probe="skip",
        )
    assert SECRET_API_KEY not in str(excinfo.value)
    partial = excinfo.value.preflight_partial  # type: ignore[attr-defined]
    record = excinfo.value.preflight_record  # type: ignore[attr-defined]
    assert partial.failing_check == "runtime_settings"
    assert record is not None
    assert SECRET_API_KEY not in str(record.model_dump(mode="json"))


def test_provider_probe_unexpected_exception_normalized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_local_checks_ok(monkeypatch)
    parent = tmp_path / "results"
    parent.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.preflight_14_level_c.reserved_results_root",
        lambda _root: parent,
    )

    def _probe(_settings: AppSettings) -> GeneratorProbeResult:
        raise RuntimeError(f"unexpected probe failure {SECRET_API_KEY}")

    with pytest.raises(Performance14Error) as excinfo:
        run_level_c_execution_preflight(
            repo_root=REPO_ROOT,
            environ=_llm_env(OFFLINE_RAG_LLM_API_KEY=SECRET_API_KEY),
            dotenv_path=tmp_path / "no.env",
            provider_probe="require",
            provider_probe_fn=_probe,
        )
    assert SECRET_API_KEY not in str(excinfo.value)
    partial = excinfo.value.preflight_partial  # type: ignore[attr-defined]
    record = excinfo.value.preflight_record  # type: ignore[attr-defined]
    assert partial.failing_check == "provider_probe"
    assert record is not None
    assert SECRET_API_KEY not in str(record.model_dump(mode="json"))
    assert "RuntimeError" in str(excinfo.value)


def test_level_c_population_is_first_five_of_14c() -> None:
    from offline_rag.evaluation.performance_14.suite_14_level_c import QUERY_IDS_LEVEL_C

    assert QUERY_IDS_LEVEL_C == tuple(sorted(QUERY_IDS_14C)[:5])
