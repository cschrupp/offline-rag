"""Discovery and corpus-root unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.ingestion.discovery import (
    DiscoveryError,
    discover_sources,
    validate_corpus_name,
)


def test_corpus_name_validation() -> None:
    assert validate_corpus_name("default") == "default"
    assert validate_corpus_name("Engineering") == "Engineering"
    with pytest.raises(DiscoveryError):
        validate_corpus_name("../x")
    with pytest.raises(DiscoveryError):
        validate_corpus_name("foo/bar")
    with pytest.raises(DiscoveryError):
        validate_corpus_name("")


def test_directory_discovery_and_root(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    nested = docs / "nested"
    nested.mkdir(parents=True)
    (docs / "a.txt").write_text("a", encoding="utf-8")
    (docs / "image.png").write_bytes(b"png")
    (nested / "b.md").write_text("# B\n", encoding="utf-8")

    sources, skipped = discover_sources([docs], recursive=False)
    assert [s.source_path for s in sources] == ["a.txt"]
    assert skipped >= 1

    sources, _ = discover_sources([docs], recursive=True)
    assert [s.source_path for s in sources] == ["a.txt", "nested/b.md"]

    with pytest.raises(DiscoveryError):
        discover_sources([docs / "image.png"])


def test_duplicate_physical_paths_deduped(tmp_path: Path) -> None:
    file_path = tmp_path / "manual.txt"
    file_path.write_text("hello", encoding="utf-8")
    sources, _ = discover_sources([file_path, tmp_path])
    assert len(sources) == 1


def test_multiple_roots_require_explicit_root(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.txt").write_text("a", encoding="utf-8")
    (right / "b.txt").write_text("b", encoding="utf-8")
    # Same parent tmp_path is a meaningful common ancestor.
    sources, _ = discover_sources([left, right])
    assert sorted(s.source_path for s in sources) == ["left/a.txt", "right/b.txt"]
