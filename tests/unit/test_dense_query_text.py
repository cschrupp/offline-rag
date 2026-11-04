"""Unit tests for dense query-text contracts (raw-query-v1 / model-query-prompt-v1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from offline_rag.config.models import AppSettings, DenseQueryTextSettings
from offline_rag.core.ids import MODEL_QUERY_PROMPT_V1, RAW_QUERY_V1
from offline_rag.dense.config_hash import (
    build_dense_retrieval_config_hash,
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import (
    EmbedderError,
    FakeEmbedder,
    SentenceTransformersEmbedder,
    make_embedder,
)
from offline_rag.dense.embedding_artifacts import (
    RepresentationInspection,
    RepresentationReadiness,
    RepresentationReasonCode,
)
from offline_rag.dense.embedding_runtime import QualifiedEmbeddingRuntime
from offline_rag.dense.execution_profile import (
    CPU_ONNX_FP32_V1,
    CUDA_FP16_V1,
    EmbeddingProfileResolution,
)
from offline_rag.dense.query_text import MODEL_QUERY_PROMPT_NAME


def test_dense_query_text_defaults_raw_query_v1() -> None:
    settings = AppSettings()
    assert settings.dense.query_text.strategy == "raw"
    assert settings.dense.query_text.contract_version == RAW_QUERY_V1


def test_dense_query_text_rejects_mismatched_pairs() -> None:
    with pytest.raises(ValidationError):
        DenseQueryTextSettings(strategy="raw", contract_version=MODEL_QUERY_PROMPT_V1)
    with pytest.raises(ValidationError):
        DenseQueryTextSettings(
            strategy="model_query_prompt", contract_version=RAW_QUERY_V1
        )


def test_query_contract_does_not_change_index_identity() -> None:
    base = AppSettings()
    prompted = base.model_copy(
        update={
            "dense": base.dense.model_copy(
                update={
                    "query_text": DenseQueryTextSettings(
                        strategy="model_query_prompt",
                        contract_version=MODEL_QUERY_PROMPT_V1,
                    )
                }
            )
        }
    )
    assert build_embedding_config_hash(base) == build_embedding_config_hash(prompted)
    assert build_index_config_hash(base) == build_index_config_hash(prompted)
    assert build_dense_retrieval_config_hash(base) != build_dense_retrieval_config_hash(
        prompted
    )


@pytest.mark.parametrize(
    ("profile", "configured_device", "configured_precision", "cuda_available"),
    [
        (CPU_ONNX_FP32_V1, "cpu", "native", False),
        (CUDA_FP16_V1, "cuda", "fp16", True),
    ],
)
def test_make_embedder_factory_accepts_prompt_contract_for_qualified_profiles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    profile,
    configured_device: str,
    configured_precision: str,
    cuda_available: bool,
) -> None:
    from offline_rag.dense.embedding_artifacts import load_package_qualification_spec
    from offline_rag.dense.onnx_embedder import SentenceTransformersOnnxEmbedder

    settings = AppSettings()
    settings = settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={"embedding_artifacts": tmp_path / "artifacts"}
            ),
            "indexing": settings.indexing.model_copy(
                update={
                    "embedding": settings.indexing.embedding.model_copy(
                        update={
                            "implementation": "sentence_transformers",
                            "device": configured_device,
                            "precision": configured_precision,
                        }
                    )
                }
            ),
            "dense": settings.dense.model_copy(
                update={
                    "query_text": DenseQueryTextSettings(
                        strategy="model_query_prompt",
                        contract_version=MODEL_QUERY_PROMPT_V1,
                    )
                }
            ),
        }
    )
    representation = RepresentationInspection(
        representation_id=profile.representation_id,
        readiness=RepresentationReadiness.READY,
        reason_code=RepresentationReasonCode.OK,
        reason="ready",
        root=tmp_path,
        instance_path=tmp_path,
        qualification_spec=(
            load_package_qualification_spec("onnx_fp32_v1")
            if profile is CPU_ONNX_FP32_V1
            else None
        ),
    )
    resolution = EmbeddingProfileResolution(
        configured_device=configured_device,
        configured_precision=configured_precision,
        profile=profile,
        selection_reason=(
            "explicit_cpu_onnx_fp32"
            if profile is CPU_ONNX_FP32_V1
            else "explicit_cuda_fp16"
        ),
        cuda_available=cuda_available,
        torch_cuda_build="test-cuda" if cuda_available else None,
    )
    monkeypatch.setattr(
        "offline_rag.dense.execution_profile.resolve_qualified_embedding_profile",
        lambda *args, **kwargs: resolution,
    )
    monkeypatch.setattr(
        "offline_rag.dense.embedder.resolve_embedding_model_dir",
        lambda **kwargs: tmp_path,
    )
    monkeypatch.setattr(
        "offline_rag.dense.embedding_artifacts.inspect_selected_representation",
        lambda *args, **kwargs: representation,
    )
    monkeypatch.setattr(
        "offline_rag.dense.embedder.require_embedding_artifacts",
        lambda *args, **kwargs: None,
    )

    runtime = make_embedder(settings)

    assert isinstance(runtime, QualifiedEmbeddingRuntime)
    assert runtime.query_text_contract == MODEL_QUERY_PROMPT_V1
    backend = runtime._default_construct_backend()
    assert backend.query_text_contract == MODEL_QUERY_PROMPT_V1
    if profile is CPU_ONNX_FP32_V1:
        assert isinstance(backend, SentenceTransformersOnnxEmbedder)
    else:
        assert isinstance(backend, SentenceTransformersEmbedder)


def test_fake_embedder_rejects_model_query_prompt() -> None:
    with pytest.raises(EmbedderError):
        FakeEmbedder(query_text_contract=MODEL_QUERY_PROMPT_V1)


def test_make_embedder_fake_rejects_model_query_prompt(tmp_path: Path) -> None:
    settings = AppSettings().model_copy(
        update={
            "paths": AppSettings().paths.model_copy(
                update={"embedding_artifacts": tmp_path / "emb"}
            ),
            "indexing": AppSettings().indexing.model_copy(
                update={
                    "embedding": AppSettings().indexing.embedding.model_copy(
                        update={
                            "implementation": "fake",
                            "model_id": "fake",
                            "revision": "fake-v1",
                            "dimension": 8,
                            "adapter_contract": "fake-embedder-v1",
                        }
                    )
                }
            ),
            "dense": AppSettings().dense.model_copy(
                update={
                    "query_text": DenseQueryTextSettings(
                        strategy="model_query_prompt",
                        contract_version=MODEL_QUERY_PROMPT_V1,
                    )
                }
            ),
        }
    )
    with pytest.raises(EmbedderError, match="model-query-prompt-v1"):
        make_embedder(settings)


class _FakeSTModel:
    def __init__(self, *, prompts: dict[str, Any] | None) -> None:
        self.prompts = prompts
        self.calls: list[dict[str, Any]] = []

    def encode(self, texts: Any, **kwargs: Any) -> Any:
        import numpy as np

        self.calls.append({"texts": texts, **kwargs})
        if isinstance(texts, str):
            return np.ones(4, dtype=float)
        return np.ones((len(list(texts)), 4), dtype=float)


def test_model_query_prompt_uses_prompt_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model = _FakeSTModel(prompts={MODEL_QUERY_PROMPT_NAME: "Instruct: ...\nQuery:"})
    emb = SentenceTransformersEmbedder.__new__(SentenceTransformersEmbedder)
    emb.model_path = tmp_path
    emb.model_id = "fake-st"
    emb.model_revision = "rev"
    emb.dimension = 4
    emb.normalize = True
    emb.device = "cpu"
    emb.batch_size = 8
    emb.query_instruction = None
    emb.document_instruction = None
    emb.query_text_contract = MODEL_QUERY_PROMPT_V1
    emb._model = model

    vector = SentenceTransformersEmbedder.embed_query(emb, "What is Module 1?")
    assert len(vector) == 4
    assert model.calls[-1]["prompt_name"] == MODEL_QUERY_PROMPT_NAME
    assert model.calls[-1]["texts"] == "What is Module 1?"


def test_model_query_prompt_fails_closed_without_query_prompt(
    tmp_path: Path,
) -> None:
    model = _FakeSTModel(prompts={})
    emb = SentenceTransformersEmbedder.__new__(SentenceTransformersEmbedder)
    emb.model_path = tmp_path
    emb.model_id = "fake-st"
    emb.model_revision = "rev"
    emb.dimension = 4
    emb.normalize = True
    emb.device = "cpu"
    emb.batch_size = 8
    emb.query_instruction = None
    emb.document_instruction = None
    emb.query_text_contract = MODEL_QUERY_PROMPT_V1
    emb._model = model

    with pytest.raises(EmbedderError, match="prompts\\['query'\\]"):
        SentenceTransformersEmbedder.embed_query(emb, "q")


@pytest.mark.parametrize("prompt_value", ["", "  ", 7, None])
def test_model_query_prompt_rejects_invalid_registered_prompt(
    tmp_path: Path, prompt_value: Any
) -> None:
    model = _FakeSTModel(prompts={MODEL_QUERY_PROMPT_NAME: prompt_value})
    emb = SentenceTransformersEmbedder.__new__(SentenceTransformersEmbedder)
    emb.model_path = tmp_path
    emb.model_id = "fake-st"
    emb.model_revision = "rev"
    emb.dimension = 4
    emb.normalize = True
    emb.device = "cpu"
    emb.batch_size = 8
    emb.query_instruction = None
    emb.document_instruction = None
    emb.query_text_contract = MODEL_QUERY_PROMPT_V1
    emb._model = model

    with pytest.raises(EmbedderError, match="non-empty prompts\\['query'\\]"):
        SentenceTransformersEmbedder.embed_query(emb, "private query")
    assert model.calls == []


def test_model_query_prompt_rejects_legacy_query_instruction(tmp_path: Path) -> None:
    with pytest.raises(EmbedderError, match="query_instruction"):
        SentenceTransformersEmbedder(
            model_path=tmp_path,
            model_id="x",
            model_revision="y",
            dimension=4,
            query_instruction="Instruct: ",
            query_text_contract=MODEL_QUERY_PROMPT_V1,
            expected_dimension=4,
        )


def test_sentence_transformers_rejects_unknown_query_contract(tmp_path: Path) -> None:
    with pytest.raises(EmbedderError, match="unsupported dense query-text contract"):
        SentenceTransformersEmbedder(
            model_path=tmp_path,
            model_id="x",
            model_revision="y",
            dimension=4,
            query_text_contract="unknown-query-v99",
            expected_dimension=4,
        )


def test_raw_query_does_not_pass_prompt_name(tmp_path: Path) -> None:
    model = _FakeSTModel(prompts={MODEL_QUERY_PROMPT_NAME: "unused"})
    emb = SentenceTransformersEmbedder.__new__(SentenceTransformersEmbedder)
    emb.model_path = tmp_path
    emb.model_id = "fake-st"
    emb.model_revision = "rev"
    emb.dimension = 4
    emb.normalize = True
    emb.device = "cpu"
    emb.batch_size = 8
    emb.query_instruction = None
    emb.document_instruction = None
    emb.query_text_contract = RAW_QUERY_V1
    emb._model = model

    SentenceTransformersEmbedder.embed_query(emb, "raw query")
    assert "prompt_name" not in model.calls[-1]
