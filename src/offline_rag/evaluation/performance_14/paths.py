"""Immutable result paths for Slice 14 performance runs.

14B dry-run writes only under ``eval/results/performance_14_dryrun/``.
Authoritative frozen-campaign evidence writes under
``eval/results/performance_14/`` and must never share a dry-run root.
"""

from __future__ import annotations

import re
from pathlib import Path

from offline_rag.evaluation.performance_14.contracts import Performance14Error

RESERVED_RESULTS_REL = Path("eval/results/performance_14")
DRYRUN_RESULTS_REL = Path("eval/results/performance_14_dryrun")

# Single path segment: identity prefixes or safe labels; no separators / traversal.
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,255}$")


def reserved_results_root(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return (root / RESERVED_RESULTS_REL).resolve()


def default_dryrun_parent(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return (root / DRYRUN_RESULTS_REL).resolve()


def validate_path_segment(segment: str, *, field_name: str) -> str:
    """Reject blank, separators, and ``..`` traversal in identity path segments."""
    if not segment or not segment.strip():
        raise Performance14Error(f"{field_name} must be non-blank")
    cleaned = segment.strip()
    if cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned:
        raise Performance14Error(
            f"{field_name} must be a single path segment without separators "
            f"or traversal; got {segment!r}"
        )
    if not _SAFE_SEGMENT_RE.fullmatch(cleaned):
        raise Performance14Error(
            f"{field_name} has unsafe characters for a result-path segment: {segment!r}"
        )
    return cleaned


def assert_under_dryrun_root(
    candidate: Path,
    *,
    repo_root: Path | None = None,
    dryrun_parent: Path | None = None,
) -> Path:
    """Require ``candidate`` to resolve strictly under the dry-run root."""
    parent = (
        Path(dryrun_parent).expanduser().resolve(strict=False)
        if dryrun_parent is not None
        else default_dryrun_parent(repo_root)
    )
    reserved = reserved_results_root(repo_root)
    try:
        resolved = candidate.expanduser().resolve(strict=False)
    except OSError as exc:
        raise Performance14Error(
            f"failed to resolve output path {candidate}: {exc}"
        ) from exc
    if resolved == reserved or reserved in resolved.parents:
        raise Performance14Error(
            "refusing to write under reserved performance_14 result root "
            f"{reserved}; dry-run output must stay under {parent}"
        )
    if resolved != parent and parent not in resolved.parents:
        raise Performance14Error(
            f"dry-run output path {resolved} is not under dry-run root {parent}"
        )
    return resolved


def assert_outside_reserved_root(
    candidate: Path,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Compatibility wrapper: also requires confinement under the dry-run root."""
    return assert_under_dryrun_root(candidate, repo_root=repo_root)


def assert_under_authoritative_root(
    candidate: Path,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Require ``candidate`` to resolve strictly under ``performance_14/``."""
    parent = reserved_results_root(repo_root)
    dryrun = default_dryrun_parent(repo_root)
    try:
        resolved = candidate.expanduser().resolve(strict=False)
    except OSError as exc:
        raise Performance14Error(
            f"failed to resolve authoritative output path {candidate}: {exc}"
        ) from exc
    if resolved == dryrun or dryrun in resolved.parents:
        raise Performance14Error(
            "refusing to write authoritative evidence under dry-run root "
            f"{dryrun}; authoritative output must stay under {parent}"
        )
    if resolved != parent and parent not in resolved.parents:
        raise Performance14Error(
            f"authoritative output path {resolved} is not under "
            f"performance_14 root {parent}"
        )
    return resolved


def allocate_dryrun_run_dir(
    *,
    suite_id: str,
    run_id: str,
    repo_root: Path | None = None,
    dryrun_parent: Path | None = None,
) -> Path:
    """Allocate ``.../performance_14_dryrun/<suite_id>/<run_id>/``.

    ``run_id`` must be the canonical ``perfrun_<sha256>`` identity.
    Fail closed if the target already exists (immutable runs; reruns need a new
    perfrun_ identity / nonce).
    """
    suite_seg = validate_path_segment(suite_id, field_name="suite_id")
    run_seg = validate_path_segment(run_id, field_name="run_id")
    if not run_seg.startswith("perfrun_"):
        raise Performance14Error(
            f"run_id must be the canonical perfrun_ identity; got {run_id!r}"
        )
    parent = (
        Path(dryrun_parent).expanduser().resolve(strict=False)
        if dryrun_parent is not None
        else default_dryrun_parent(repo_root)
    )
    # Custom dryrun_parent must itself be (or resolve as) a dry-run root leaf.
    if dryrun_parent is not None and parent.name != DRYRUN_RESULTS_REL.name:
        raise Performance14Error(
            f"dryrun_parent must be named {DRYRUN_RESULTS_REL.name!s}; got {parent}"
        )
    target = parent / suite_seg / run_seg
    resolved = assert_under_dryrun_root(
        target, repo_root=repo_root, dryrun_parent=parent
    )
    if resolved.exists():
        raise Performance14Error(
            f"run result directory already exists (immutable): {resolved}"
        )
    return resolved


def allocate_authoritative_run_dir(
    *,
    suite_id: str,
    run_id: str,
    repo_root: Path | None = None,
) -> Path:
    """Allocate ``.../performance_14/<suite_id>/<run_id>/`` (create-exclusive)."""
    suite_seg = validate_path_segment(suite_id, field_name="suite_id")
    run_seg = validate_path_segment(run_id, field_name="run_id")
    if not run_seg.startswith("perfrun_"):
        raise Performance14Error(
            f"run_id must be the canonical perfrun_ identity; got {run_id!r}"
        )
    parent = reserved_results_root(repo_root)
    target = parent / suite_seg / run_seg
    resolved = assert_under_authoritative_root(target, repo_root=repo_root)
    if resolved.exists():
        raise Performance14Error(
            f"authoritative run directory already exists (immutable): {resolved}"
        )
    return resolved
