"""Embedding precision execution policy + identity hash exclusion."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings, EmbeddingModelSettings
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import EmbedderError, FakeEmbedder, make_embedder
from offline_rag.dense.precision import resolve_embedding_precision

REPO = Path(__file__).resolve().parents[3]


def test_base_yaml_default_precision_is_native() -> None:
    settings = load_settings(yaml_paths=[REPO / "config" / "base.yaml"], environ={})
    assert settings.indexing.embedding.precision == "native"


def test_precision_validation() -> None:
    for value in ("native", "fp16"):
        assert EmbeddingModelSettings(precision=value).precision == value
    for bad in ("bf16", "fp32", "auto", ""):
        with pytest.raises(ValidationError):
            EmbeddingModelSettings(precision=bad)  # type: ignore[arg-type]


def test_env_precision_override() -> None:
    settings = load_settings(
        yaml_paths=[REPO / "config" / "base.yaml"],
        environ={"OFFLINE_RAG_EMBEDDING_PRECISION": "fp16"},
    )
    assert settings.indexing.embedding.precision == "fp16"


def test_env_batch_size_override() -> None:
    settings = load_settings(
        yaml_paths=[REPO / "config" / "base.yaml"],
        environ={"OFFLINE_RAG_EMBEDDING_BATCH_SIZE": "16"},
    )
    assert settings.indexing.embedding.batch_size == 16


def test_hash_invariance_native_vs_fp16() -> None:
    base = AppSettings()
    hashes_emb = []
    hashes_idx = []
    for precision in ("native", "fp16"):
        emb = base.indexing.embedding.model_copy(update={"precision": precision})
        settings = base.model_copy(
            update={"indexing": base.indexing.model_copy(update={"embedding": emb})}
        )
        hashes_emb.append(build_embedding_config_hash(settings))
        hashes_idx.append(build_index_config_hash(settings))
    assert hashes_emb[0] == hashes_emb[1]
    assert hashes_idx[0] == hashes_idx[1]


def test_hash_invariance_batch_size_still_excluded() -> None:
    base = AppSettings()
    a = base.indexing.embedding.model_copy(update={"batch_size": 32})
    b = base.indexing.embedding.model_copy(update={"batch_size": 16})
    sa = base.model_copy(
        update={"indexing": base.indexing.model_copy(update={"embedding": a})}
    )
    sb = base.model_copy(
        update={"indexing": base.indexing.model_copy(update={"embedding": b})}
    )
    assert build_embedding_config_hash(sa) == build_embedding_config_hash(sb)
    assert build_index_config_hash(sa) == build_index_config_hash(sb)


def test_fake_embedder_rejects_fp16() -> None:
    with pytest.raises(EmbedderError, match="native"):
        FakeEmbedder(configured_precision="fp16")


def test_make_embedder_fake_native_ok() -> None:
    settings = AppSettings().model_copy(
        update={
            "indexing": AppSettings().indexing.model_copy(
                update={
                    "embedding": AppSettings().indexing.embedding.model_copy(
                        update={"implementation": "fake", "precision": "native"}
                    )
                }
            )
        }
    )
    emb = make_embedder(settings)
    assert isinstance(emb, FakeEmbedder)
    assert emb.resolved_precision == "native"


def test_make_embedder_fake_fp16_fails_closed() -> None:
    settings = AppSettings().model_copy(
        update={
            "indexing": AppSettings().indexing.model_copy(
                update={
                    "embedding": AppSettings().indexing.embedding.model_copy(
                        update={"implementation": "fake", "precision": "fp16"}
                    )
                }
            )
        }
    )
    with pytest.raises(EmbedderError, match="native"):
        make_embedder(settings)


def test_resolve_native_on_cpu() -> None:
    res = resolve_embedding_precision("native", resolved_device="cpu")
    assert res.resolved_precision == "native"
