"""Source discovery, corpus-root resolution, and corpus-name validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from offline_rag.ingestion.base import SUPPORTED_EXTENSIONS, media_type_for_path

CORPUS_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class DiscoveryError(ValueError):
    """Preflight discovery/root errors."""


@dataclass(frozen=True)
class DiscoveredSource:
    absolute_path: Path
    source_path: str  # portable relative POSIX path
    source_name: str
    media_type: str


def validate_corpus_name(name: str) -> str:
    if not name or not name.strip():
        raise DiscoveryError("corpus name must be non-empty")
    if not CORPUS_NAME_RE.fullmatch(name):
        raise DiscoveryError(
            "invalid corpus name; use [A-Za-z0-9][A-Za-z0-9._-]{0,63} "
            "without path separators or traversal"
        )
    return name


def _is_under(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _portable_relpath(root: Path, path: Path) -> str:
    rel = path.resolve().relative_to(root.resolve())
    return rel.as_posix()


def _nearest_common_ancestor(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    resolved = [p.resolve() for p in paths]
    try:
        common = Path(*resolved[0].parts)
        for path in resolved[1:]:
            parts = common.parts
            other = path.parts
            i = 0
            while i < len(parts) and i < len(other) and parts[i] == other[i]:
                i += 1
            if i == 0:
                return None
            common = Path(*parts[:i])
        # Reject filesystem/drive roots as meaningless.
        if common == common.anchor or str(common) in {"/", "C:\\", "C:/"}:
            return None
        if len(common.parts) <= 1 and common.is_absolute() and common.parent == common:
            return None
        return common
    except (OSError, RuntimeError, ValueError):
        return None


def discover_sources(
    inputs: list[Path],
    *,
    recursive: bool = False,
    root: Path | None = None,
) -> tuple[list[DiscoveredSource], int]:
    """Discover supported sources with deterministic ordering.

    Returns (sources, unsupported_files_skipped).
    """
    if not inputs:
        raise DiscoveryError("at least one source path is required")

    for raw in inputs:
        if not raw.exists():
            raise DiscoveryError(f"path does not exist: {raw}")

    skipped = 0
    candidates: list[Path] = []

    for raw in inputs:
        path = raw
        if path.is_symlink() and path.is_dir():
            raise DiscoveryError(f"refusing to traverse symlinked directory: {path}")
        if path.is_file():
            if path.is_symlink():
                path = path.resolve()
            media = media_type_for_path(path)
            if media is None:
                raise DiscoveryError(
                    f"unsupported file type: {path.name} "
                    f"(supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))})"
                )
            candidates.append(path.resolve())
            continue

        if not path.is_dir():
            raise DiscoveryError(f"unsupported path type: {path}")

        iterator = path.rglob("*") if recursive else path.iterdir()
        for child in iterator:
            if child.is_dir():
                if recursive and child.is_symlink():
                    continue
                continue
            if not child.is_file():
                continue
            resolved = child.resolve()
            if media_type_for_path(resolved) is None:
                skipped += 1
                continue
            candidates.append(resolved)

    # Deduplicate by resolved path.
    unique: dict[Path, Path] = {}
    for candidate in candidates:
        unique[candidate.resolve()] = candidate.resolve()
    files = list(unique.values())
    if not files:
        raise DiscoveryError(
            "no supported documents found. "
            f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if root is not None:
        corpus_root = root.resolve()
        if not corpus_root.exists() or not corpus_root.is_dir():
            raise DiscoveryError(f"--root must be an existing directory: {root}")
        for file_path in files:
            if not _is_under(corpus_root, file_path):
                raise DiscoveryError(
                    f"source is outside --root: {file_path} (root={corpus_root})"
                )
    elif len(inputs) == 1 and inputs[0].is_dir():
        corpus_root = inputs[0].resolve()
    elif len(files) == 1 and len(inputs) == 1 and inputs[0].is_file():
        corpus_root = files[0].parent
    else:
        corpus_root = _nearest_common_ancestor(files)
        if corpus_root is None:
            raise DiscoveryError(
                "could not infer a meaningful corpus root for multiple inputs; "
                "provide --root <path>"
            )

    discovered = [
        DiscoveredSource(
            absolute_path=file_path,
            source_path=_portable_relpath(corpus_root, file_path),
            source_name=file_path.name,
            media_type=media_type_for_path(file_path) or "application/octet-stream",
        )
        for file_path in files
    ]
    discovered.sort(key=lambda item: item.source_path)
    return discovered, skipped
