"""Token counter tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.chunking.tokenize import (
    FakeTokenCounter,
    TiktokenTokenCounter,
    TokenizerArtifactsUnavailableError,
    validate_tiktoken_artifacts,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TIKTOKEN_DIR = REPO_ROOT / "models" / "tokenizers" / "tiktoken"


def test_fake_counter_is_whitespace_deterministic() -> None:
    counter = FakeTokenCounter()
    assert counter.count("one two three") == 3
    assert counter.count("one two three") == 3
    assert counter.count("  ") == 0


def test_tiktoken_offline_missing_artifacts(tmp_path: Path) -> None:
    empty = tmp_path / "tok"
    empty.mkdir()
    ok, reason = validate_tiktoken_artifacts(empty)
    assert ok is False
    assert "offline-rag-tokenizer.json" in reason
    with pytest.raises(TokenizerArtifactsUnavailableError):
        TiktokenTokenCounter(artifacts_path=empty).count("hello")


@pytest.mark.integration
def test_tiktoken_frozen_reference_counts() -> None:
    ok, reason = validate_tiktoken_artifacts(TIKTOKEN_DIR)
    assert ok, reason
    counter = TiktokenTokenCounter(artifacts_path=TIKTOKEN_DIR)
    # Frozen probe used by provisioning / doctor.
    assert counter.count("OfflineRAG tokenizer probe") == 5
    assert counter.count("hello world") == 2
