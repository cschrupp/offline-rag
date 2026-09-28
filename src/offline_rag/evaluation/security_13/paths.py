"""Authoritative vs dry-run result-path safeguards for Slice 13B."""

from __future__ import annotations

from pathlib import Path

from offline_rag.evaluation.security_13.contracts import SecurityEvalError

AUTHORITATIVE_RESULTS_REL = Path("eval/results/security_13b")
DRYRUN_RESULTS_REL = Path("eval/results/security_13b_dryrun")


def authoritative_results_root(repo_root: Path | None = None) -> Path:
    """Return the reserved authoritative result root (never writable by harness)."""
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return (root / AUTHORITATIVE_RESULTS_REL).resolve()


def default_dryrun_parent(repo_root: Path | None = None) -> Path:
    """Return the default dry-run parent directory."""
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return (root / DRYRUN_RESULTS_REL).resolve()


def assert_outside_authoritative_root(
    candidate: Path,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Resolve ``candidate`` and fail closed if it is the authoritative root.

    Rejects equality, descendants, and paths that normalize/symlink into
    ``eval/results/security_13b/``.
    """
    auth = authoritative_results_root(repo_root)
    # Resolve without requiring the path to exist yet: resolve parent when needed.
    try:
        resolved = candidate.expanduser().resolve(strict=False)
    except OSError as exc:
        raise SecurityEvalError(
            f"failed to resolve output path {candidate}: {exc}"
        ) from exc

    if resolved == auth or auth in resolved.parents:
        raise SecurityEvalError(
            "refusing to write under reserved authoritative result root "
            f"{auth}; dry-run output must be outside eval/results/security_13b/"
        )
    return resolved


def allocate_dryrun_run_dir(
    *,
    run_id: str,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Allocate ``.../security_13b_dryrun/<run_id>/`` or a validated custom dir.

    Fail closed if the target already exists (immutability) or lands under the
    authoritative root.
    """
    if not run_id or not run_id.strip():
        raise SecurityEvalError("run_id must be non-blank")
    if output_dir is None:
        target = default_dryrun_parent(repo_root) / run_id.strip()
    else:
        target = Path(output_dir)
    resolved = assert_outside_authoritative_root(target, repo_root=repo_root)
    if resolved.exists():
        raise SecurityEvalError(
            f"dry-run result directory already exists (immutable): {resolved}"
        )
    return resolved
