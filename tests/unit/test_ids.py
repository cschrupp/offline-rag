"""Deterministic ID policy tests."""

from __future__ import annotations

import pytest

from offline_rag.core.ids import (
    canonical_config_hash,
    chunk_id_from_parts,
    document_id_from_bytes,
    new_execution_id,
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
