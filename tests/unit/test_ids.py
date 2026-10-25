"""Deterministic ID policy tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.core.ids import (
    STRUCTURE_AWARE_CHUNKER_VERSION,
    canonical_config_hash,
    child_chunk_id_from_parts,
    chunk_artifact_id,
    chunk_config_hash,
    chunk_id_from_parts,
    content_hash_from_bytes,
    content_hash_from_path,
    document_id_from_bytes,
    document_id_from_path,
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


@pytest.mark.parametrize("size", [1, 8, 17, 32])
def test_path_identity_matches_byte_identity(tmp_path: Path, size: int) -> None:
    payload = bytes(range(256)) * ((size + 255) // 256)
    payload = payload[:size]
    path = tmp_path / "source.bin"
    path.write_bytes(payload)
    assert content_hash_from_path(path, chunk_size=8) == content_hash_from_bytes(payload)
    assert document_id_from_path(path, chunk_size=8) == document_id_from_bytes(payload)


def test_path_identity_rejects_empty_and_invalid_chunk_size(tmp_path: Path) -> None:
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")
    with pytest.raises(ValueError):
        content_hash_from_path(path)
    with pytest.raises(ValueError):
        content_hash_from_path(path, chunk_size=0)
    path.write_bytes(b"x")
    with pytest.raises(ValueError):
        document_id_from_path(path, chunk_size=-1)


def test_path_identity_does_not_read_entire_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "streamed.bin"
    payload = b"streamed" * 16
    path.write_bytes(payload)

    def fail_read_bytes(_path: Path) -> bytes:
        raise AssertionError("path identity must stream through open/read")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    assert content_hash_from_path(path, chunk_size=3) == content_hash_from_bytes(payload)


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


def test_child_chunk_id_occurrence_zero_matches_legacy_payload() -> None:
    """occurrence=0 must retain the exact pre-remediation child ID."""
    cfg = chunk_config_hash({"strategy": "structure_aware", "child": {"max_tokens": 512}})
    parent = "parent_abc"
    kwargs = {
        "document_id": "doc_1",
        "parent_chunk_id": parent,
        "chunk_cfg_hash": cfg,
        "source_block_ids": ["b1"],
        "text": "!",
    }
    legacy = child_chunk_id_from_parts(**kwargs)
    assert child_chunk_id_from_parts(**kwargs, occurrence=0) == legacy
    # Default argument is occurrence=0.
    assert child_chunk_id_from_parts(**kwargs) == legacy


def test_child_chunk_id_occurrence_disambiguates_deterministically() -> None:
    cfg = chunk_config_hash({"strategy": "structure_aware", "child": {"max_tokens": 512}})
    parent = "parent_abc"
    base = child_chunk_id_from_parts(
        "doc_1",
        parent_chunk_id=parent,
        chunk_cfg_hash=cfg,
        source_block_ids=["b1"],
        text="!",
        occurrence=0,
    )
    second = child_chunk_id_from_parts(
        "doc_1",
        parent_chunk_id=parent,
        chunk_cfg_hash=cfg,
        source_block_ids=["b1"],
        text="!",
        occurrence=1,
    )
    third = child_chunk_id_from_parts(
        "doc_1",
        parent_chunk_id=parent,
        chunk_cfg_hash=cfg,
        source_block_ids=["b1"],
        text="!",
        occurrence=2,
    )
    assert len({base, second, third}) == 3
    assert second == child_chunk_id_from_parts(
        "doc_1",
        parent_chunk_id=parent,
        chunk_cfg_hash=cfg,
        source_block_ids=["b1"],
        text="!",
        occurrence=1,
    )
    with pytest.raises(ValueError):
        child_chunk_id_from_parts(
            "doc_1",
            parent_chunk_id=parent,
            chunk_cfg_hash=cfg,
            source_block_ids=["b1"],
            text="!",
            occurrence=-1,
        )
