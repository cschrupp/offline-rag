"""Deterministic ID policy tests."""

from __future__ import annotations

import pytest

from offline_rag.core.ids import (
    STRUCTURE_AWARE_CHUNKER_VERSION,
    canonical_config_hash,
    child_chunk_id_from_parts,
    chunk_artifact_id,
    chunk_config_hash,
    chunk_id_from_parts,
    document_id_from_bytes,
    new_execution_id,
    parent_chunk_id_from_parts,
)


def test_document_id_is_deterministic() -> None:
    payload = b"same-bytes"
    assert document_id_from_bytes(payload) == document_id_from_bytes(payload)
    assert document_id_from_bytes(payload).startswith("doc_")


def test_document_id_changes_with_content() -> None:
    assert document_id_from_bytes(b"a") != document_id_from_bytes(b"b")


def test_document_id_rejects_empty_bytes() -> None:
    with pytest.raises(ValueError):
        document_id_from_bytes(b"")


def test_chunk_id_deterministic_and_sensitive() -> None:
    base = chunk_id_from_parts("doc_1", 0, "hello world", chunker_version="v1")
    same = chunk_id_from_parts("doc_1", 0, "hello world", chunker_version="v1")
    assert base == same
    assert base.startswith("chunk_")
    assert base != chunk_id_from_parts("doc_1", 1, "hello world", chunker_version="v1")
    assert base != chunk_id_from_parts("doc_1", 0, "hello worlds", chunker_version="v1")
    assert base != chunk_id_from_parts("doc_2", 0, "hello world", chunker_version="v1")
    assert base != chunk_id_from_parts("doc_1", 0, "hello world", chunker_version="v2")


def test_config_hash_ignores_key_order() -> None:
    left = canonical_config_hash({"b": 1, "a": {"y": 2, "x": 3}})
    right = canonical_config_hash({"a": {"x": 3, "y": 2}, "b": 1})
    assert left == right
    assert left.startswith("cfg_")
    assert left != canonical_config_hash({"a": {"x": 3, "y": 9}, "b": 1})


def test_execution_id_is_prefixed_and_unique() -> None:
    first = new_execution_id(prefix="trace")
    second = new_execution_id(prefix="trace")
    assert first.startswith("trace_")
    assert first != second


def test_chunk_artifact_and_parent_child_ids() -> None:
    cfg = chunk_config_hash({"strategy": "structure_aware", "child": {"max_tokens": 512}})
    assert cfg.startswith("chunkcfg_")
    art = chunk_artifact_id("parsed_1", cfg, chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION)
    assert art.startswith("chunkartifact_")
    assert art == chunk_artifact_id("parsed_1", cfg)
    parent = parent_chunk_id_from_parts(
        "doc_1",
        chunk_cfg_hash=cfg,
        source_block_ids=["b1", "b2"],
        text="hello",
    )
    child = child_chunk_id_from_parts(
        "doc_1",
        parent_chunk_id=parent,
        chunk_cfg_hash=cfg,
        source_block_ids=["b1"],
        text="hello",
    )
    assert parent.startswith("parent_")
    assert child.startswith("chunk_")
    assert child != child_chunk_id_from_parts(
        "doc_1",
        parent_chunk_id=parent,
        chunk_cfg_hash=cfg,
        source_block_ids=["b1"],
        text="hello!",
    )
