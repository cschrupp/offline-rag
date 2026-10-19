"""Gating / security / sequence tests for env-gated GPU diagnostic probe."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import DiagGpuProbeConfigError, create_app
from offline_rag.api.diag_gpu_probe import (
    DIAG_GPU_PROBE_ENV,
    DIAG_GPU_PROBE_HEADER,
    DIAG_GPU_PROBE_TOKEN_ENV,
    DiagGpuSession,
    build_state,
    run_action,
)
from offline_rag.app.runtime import ApplicationRuntime, ProcessResources, ResourceFactories
from offline_rag.config.models import AppSettings


class _FakeEmb:
    def __init__(self) -> None:
        self._model = None
        self.loads = 0
        self.touches = 0

    def _load(self) -> object:
        self.loads += 1
        self._model = object()
        return self._model

    def embed_query(self, text: str) -> list[float]:
        self._load()
        self.touches += 1
        return [0.0]


class _FakeRr:
    def __init__(self) -> None:
        self._model = None
        self.loads = 0
        self.touches = 0

    def _load(self) -> tuple[object, object]:
        self.loads += 1
        self._model = object()
        return object(), self._model

    def score_pairs(self, pairs: Any) -> list[float]:
        self._load()
        self.touches += 1
        return [0.0 for _ in pairs]


def _settings(tmp_path: Path, *, host: str = "127.0.0.1") -> AppSettings:
    base = AppSettings()
    return base.model_copy(
        update={
            "api": base.api.model_copy(update={"http_host": host}),
            "paths": base.paths.model_copy(
                update={
                    "data_dir": tmp_path / "data",
                    "product_settings": tmp_path / "settings",
                }
            ),
        }
    )


def _runtime(settings: AppSettings) -> ApplicationRuntime:
    emb = _FakeEmb()
    rr = _FakeRr()

    def f_emb(_: AppSettings) -> Any:
        return emb

    def f_rr(_: AppSettings) -> Any:
        return rr

    def f_gen(_: AppSettings) -> Any:
        return object()

    rt = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=f_emb,
            reranker=f_rr,
            generator_client=f_gen,
            qdrant=None,
        ),
    )
    # Bypass full start(); attach resources for probe unit tests.
    rt.resources = ProcessResources(embedder=emb, reranker=rr, generator_client=object())
    rt.state = type(rt.state).READY
    return rt


@pytest.fixture(autouse=True)
def _clear_probe_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DIAG_GPU_PROBE_ENV, raising=False)
    monkeypatch.delenv(DIAG_GPU_PROBE_TOKEN_ENV, raising=False)


def test_g1_flag_off_routes_absent(tmp_path: Path) -> None:
    app = create_app(runtime=_runtime(_settings(tmp_path)))
    with TestClient(app) as client:
        assert client.get("/v1/_diag/gpu/state").status_code == 404
        assert (
            client.post("/v1/_diag/gpu/action", json={"op": "load_embedder"}).status_code
            == 404
        )
        schema = client.get("/openapi.json").json()
        paths = schema.get("paths") or {}
        assert "/v1/_diag/gpu/state" not in paths
        assert "/v1/_diag/gpu/action" not in paths


def test_g2_enabled_missing_token_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DIAG_GPU_PROBE_ENV, "1")
    with pytest.raises(DiagGpuProbeConfigError, match="TOKEN"):
        create_app(runtime=_runtime(_settings(tmp_path)))


def test_g2_enabled_non_loopback_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DIAG_GPU_PROBE_ENV, "1")
    monkeypatch.setenv(DIAG_GPU_PROBE_TOKEN_ENV, "secret-token")
    with pytest.raises(DiagGpuProbeConfigError, match="loopback"):
        create_app(runtime=_runtime(_settings(tmp_path, host="0.0.0.0")))


def test_g2_enabled_token_and_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DIAG_GPU_PROBE_ENV, "1")
    monkeypatch.setenv(DIAG_GPU_PROBE_TOKEN_ENV, "secret-token")
    app = create_app(runtime=_runtime(_settings(tmp_path)))
    with TestClient(app) as client:
        assert client.get("/v1/_diag/gpu/state").status_code == 401
        headers = {DIAG_GPU_PROBE_HEADER: "secret-token"}
        resp = client.get("/v1/_diag/gpu/state", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["api_pid"] == os.getpid()
        assert "loaded_model_inventory" in body
        schema = client.get("/openapi.json").json()
        paths = schema.get("paths") or {}
        assert "/v1/_diag/gpu/state" not in paths
        assert "/v1/_diag/gpu/action" not in paths


def test_g6_load_order_events_distinguishable(tmp_path: Path) -> None:
    rt = _runtime(_settings(tmp_path))
    session = DiagGpuSession()
    run_action(rt, session, "load_embedder")
    run_action(rt, session, "load_reranker")
    seq_ab = [e["op"] for e in session.load_events]
    assert seq_ab == ["load_embedder", "load_reranker"]
    state = build_state(rt, session)
    assert state["loaded_model_inventory"]["embedder"] is True
    assert state["loaded_model_inventory"]["reranker"] is True

    session2 = DiagGpuSession()
    rt2 = _runtime(_settings(tmp_path))
    run_action(rt2, session2, "load_reranker")
    run_action(rt2, session2, "load_embedder")
    seq_ba = [e["op"] for e in session2.load_events]
    assert seq_ba == ["load_reranker", "load_embedder"]
    # Final inventories may match; ordered events must differ.
    assert seq_ab != seq_ba


def test_g7_actions_do_not_require_workspace(tmp_path: Path) -> None:
    rt = _runtime(_settings(tmp_path))
    session = DiagGpuSession()
    # No workspace objects exist on this runtime; actions must still succeed.
    run_action(rt, session, "load_embedder")
    run_action(rt, session, "touch_embedder")
    run_action(rt, session, "load_reranker")
    run_action(rt, session, "touch_reranker")
    assert rt.resources.embedder.touches == 1
    assert rt.resources.reranker.touches == 1


def test_probe_never_calls_empty_cache(tmp_path: Path) -> None:
    rt = _runtime(_settings(tmp_path))
    session = DiagGpuSession()
    with patch("torch.cuda.empty_cache") as empty:
        # Allocator ops require CUDA; if unavailable, skip the CUDA primitives.
        try:
            import torch

            if not torch.cuda.is_available():
                pytest.skip("CUDA unavailable")
            free_mib = torch.cuda.mem_get_info()[0] // (1024 * 1024)
            if free_mib < 1024:
                pytest.skip("insufficient free CUDA memory for capability sizes")
            run_action(rt, session, "h2_reserve_gap")
            run_action(rt, session, "release_h2")
            run_action(rt, session, "h2_fragment")
            run_action(rt, session, "release_h2")
        finally:
            assert empty.call_count == 0
