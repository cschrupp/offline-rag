"""Token counting abstractions for deterministic chunk budgeting."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

_IGNORE_NAMES = {".gitkeep", "README.md", "offline-rag-tokenizer.json"}


class TokenCounter(Protocol):
    name: str
    version: str
    encoding: str

    def count(self, text: str) -> int:
        """Return token count for canonical text."""


class FakeTokenCounter:
    """Deterministic whitespace-token counter for structural unit tests."""

    name = "fake"
    version = "fake-whitespace-v1"
    encoding = "whitespace"

    def count(self, text: str) -> int:
        parts = [part for part in text.split() if part]
        return max(len(parts), 1 if text.strip() else 0)


class TokenizerArtifactsUnavailableError(RuntimeError):
    def __init__(self, *, artifacts_path: Path, encoding: str, reason: str) -> None:
        self.artifacts_path = artifacts_path
        self.encoding = encoding
        self.reason = reason
        super().__init__(
            "Tokenizer artifacts unavailable for offline token counting.\n"
            f"Resolved path: {artifacts_path}\n"
            f"Encoding: {encoding}\n"
            f"Reason: {reason}\n"
            "Runtime downloading is intentionally disabled.\n"
            "Action: uv run python scripts/provision_tiktoken.py"
        )


def _cache_blobs(artifacts_path: Path) -> list[Path]:
    if not artifacts_path.is_dir():
        return []
    return [
        path
        for path in artifacts_path.iterdir()
        if path.is_file() and path.name not in _IGNORE_NAMES and not path.name.startswith(".")
    ]


def require_tiktoken_artifacts(artifacts_path: Path, *, encoding: str) -> Path:
    """Validate local tokenizer cache without attempting network download."""
    path = Path(artifacts_path).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise TokenizerArtifactsUnavailableError(
            artifacts_path=path,
            encoding=encoding,
            reason="directory missing",
        )
    marker = path / "offline-rag-tokenizer.json"
    if not marker.exists():
        raise TokenizerArtifactsUnavailableError(
            artifacts_path=path,
            encoding=encoding,
            reason="missing offline-rag-tokenizer.json (run provision_tiktoken.py)",
        )
    if not _cache_blobs(path):
        raise TokenizerArtifactsUnavailableError(
            artifacts_path=path,
            encoding=encoding,
            reason="tokenizer cache blobs missing (run provision_tiktoken.py)",
        )
    return path


class TiktokenTokenCounter:
    """Tiktoken adapter using an explicit local cache directory."""

    name = "tiktoken"
    version = "tiktoken-cl100k-v1"

    def __init__(self, *, encoding: str = "cl100k_base", artifacts_path: Path) -> None:
        self.encoding = encoding
        self.artifacts_path = Path(artifacts_path).expanduser().resolve()
        self._enc = None

    def _load(self):
        if self._enc is not None:
            return self._enc
        import os

        import tiktoken

        require_tiktoken_artifacts(self.artifacts_path, encoding=self.encoding)
        os.environ["TIKTOKEN_CACHE_DIR"] = str(self.artifacts_path)
        try:
            self._enc = tiktoken.get_encoding(self.encoding)
        except Exception as exc:
            raise TokenizerArtifactsUnavailableError(
                artifacts_path=self.artifacts_path,
                encoding=self.encoding,
                reason=str(exc),
            ) from exc
        return self._enc

    def count(self, text: str) -> int:
        return len(self._load().encode(text))


def validate_tiktoken_artifacts(artifacts_path: Path, *, encoding: str = "cl100k_base") -> tuple[bool, str]:
    try:
        require_tiktoken_artifacts(artifacts_path, encoding=encoding)
        counter = TiktokenTokenCounter(encoding=encoding, artifacts_path=artifacts_path)
        count = counter.count("OfflineRAG tokenizer probe")
        if count <= 0:
            return False, "encoding initialized but returned non-positive count"
        return True, "ok"
    except TokenizerArtifactsUnavailableError as exc:
        return False, exc.reason
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
