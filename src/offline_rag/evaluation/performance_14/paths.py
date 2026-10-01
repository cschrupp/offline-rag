"""Immutable dry-run result paths for Slice 14B.

14B writes only under ``eval/results/performance_14_dryrun/``.
``eval/results/performance_14/`` is reserved and not writable by this harness
(authoritative / frozen-campaign evidence production remains NOT AUTHORIZED).
"""

from __future__ import annotations

from pathlib import Path

from offline_rag.evaluation.performance_14.contracts import Performance14Error

RESERVED_RESULTS_REL = Path("eval/results/performance_14")
DRYRUN_RESULTS_REL = Path("eval/results/performance_14_dryrun")


def reserved_results_root(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return (root / RESERVED_RESULTS_REL).resolve()


def default_dryrun_parent(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return (root / DRYRUN_RESULTS_REL).resolve()


def assert_outside_reserved_root(
    candidate: Path,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Fail closed if ``candidate`` lands under the reserved authoritative root."""
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
            f"{reserved}; dry-run output must stay under "
            f"{default_dryrun_parent(repo_root)}"
        )
    return resolved


def allocate_dryrun_run_dir(
    *,
    suite_id: str,
    run_id: str,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Allocate ``.../performance_14_dryrun/<suite_id>/<run_id>/``.

    Fail closed if the target already exists (completed/failed runs are
    immutable; reruns require a new run_id).
    """
    if not suite_id or not suite_id.strip():
        raise Performance14Error("suite_id must be non-blank")
    if not run_id or not run_id.strip():
        raise Performance14Error("run_id must be non-blank")
    if output_dir is None:
        target = (
            default_dryrun_parent(repo_root) / suite_id.strip() / run_id.strip()
        )
    else:
        target = Path(output_dir)
    resolved = assert_outside_reserved_root(target, repo_root=repo_root)
    if resolved.exists():
        raise Performance14Error(
            f"run result directory already exists (immutable): {resolved}"
        )
    return resolved
