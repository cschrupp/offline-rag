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
