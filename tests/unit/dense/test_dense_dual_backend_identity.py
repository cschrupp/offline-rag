"""P1 identity preservation across qualified execution profiles."""

from __future__ import annotations

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    dense_collection_name,
    dense_index_id,
    embedding_id_from_parts,
)
from offline_rag.dense.config_hash import (
    build_dense_retrieval_config_hash,
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.execution_profile import resolve_qualified_embedding_profile


def _settings(*, device: str, precision: str) -> AppSettings:
    base = AppSettings()
    emb = base.indexing.embedding.model_copy(
        update={
            "implementation": "sentence_transformers",
            "device": device,
            "precision": precision,
            "model_id": "Qwen/Qwen3-Embedding-0.6B",
            "revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
            "dimension": 1024,
            "normalize": True,
            "query_instruction": None,
            "document_instruction": None,
        }
    )
    indexing = base.indexing.model_copy(update={"embedding": emb})
    return base.model_copy(update={"indexing": indexing})


def _identity_tuple(settings: AppSettings) -> tuple[str, ...]:
    emb_cfg = build_embedding_config_hash(settings)
    idx_cfg = build_index_config_hash(settings)
    dense_cfg = build_dense_retrieval_config_hash(settings)
    emb_id = embedding_id_from_parts(
        "chunk_fixture",
        embedding_text_digest="embtxt_fixture",
        emb_cfg_hash=emb_cfg,
    )
    didx = dense_index_id("chunkset_fixture", idx_cfg)
    coll = dense_collection_name(didx)
    return emb_cfg, idx_cfg, dense_cfg, emb_id, didx, coll


def test_identity_invariant_across_valid_profiles() -> None:
    variants = [
        ("cpu", "native", lambda: (True, "12.8", False)),
        ("cuda", "native", lambda: (True, "12.8", False)),
        ("cuda", "fp16", lambda: (True, "12.8", False)),
        ("auto", "native", lambda: (True, "12.8", False)),
        ("auto", "native", lambda: (False, "12.8", False)),
        ("auto", "fp16", lambda: (True, "12.8", False)),
    ]
    seen: set[tuple[str, ...]] = set()
    for device, precision, probe in variants:
        settings = _settings(device=device, precision=precision)
        resolve_qualified_embedding_profile(device, precision, probe=probe)
        seen.add(_identity_tuple(settings))
    assert len(seen) == 1


def test_device_precision_do_not_affect_hashes() -> None:
    assert build_embedding_config_hash(
        _settings(device="cpu", precision="native")
    ) == build_embedding_config_hash(_settings(device="cuda", precision="fp16"))
    assert build_index_config_hash(
        _settings(device="auto", precision="native")
    ) == build_index_config_hash(_settings(device="cpu", precision="native"))
