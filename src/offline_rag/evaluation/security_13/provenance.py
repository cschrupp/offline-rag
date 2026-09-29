"""Slice 13B shared provenance / Git preflight (WQ1–WQ6; no measure-once body)."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from offline_rag.evaluation.security_13.contracts import (
    ACCEPTED_CAMPAIGN_GIT_BLOB_SHA,
    FROZEN_SECCAMP_13B,
    FROZEN_SECINV_13B,
    MEASURE_ONCE_AUTHORITY_BASELINE_SHA,
    SecurityCampaignV1,
    SecurityEvalError,
)

_SHA1_40_RE = re.compile(r"^[0-9a-f]{40}$")

LOCKED_CAMPAIGN_REL = Path(
    "eval/fixtures/security/campaigns/13b_query_path_adversarial_v1.json"
)

LOCKED_ADVERSARIAL_FIXTURE_RELS: tuple[Path, ...] = (
    Path("eval/fixtures/security/secfx_citation_001_query.json"),
    Path("eval/fixtures/security/secfx_fake_system_001_query.json"),
    Path("eval/fixtures/security/secfx_file_001_query.json"),
    Path("eval/fixtures/security/secfx_ignore_001_query.json"),
    Path("eval/fixtures/security/secfx_prompt_extract_001_query.json"),
    Path("eval/fixtures/security/secfx_shell_001_query.json"),
    Path("eval/fixtures/security/secfx_suppress_001_query.json"),
)

LOCKED_BENIGN_CONTROL_RELS: tuple[Path, ...] = (
    Path("eval/fixtures/security/benign/benign_citation_dense_001.json"),
    Path("eval/fixtures/security/benign/benign_metadata_noise_001.json"),
    Path("eval/fixtures/security/benign/benign_procedural_document_001.json"),
    Path("eval/fixtures/security/benign/benign_quoted_imperative_001.json"),
    Path("eval/fixtures/security/benign/benign_system_word_literal_001.json"),
)

# WQ4: entire project Python package + exact Q2 campaign population files.
SECURITY_13B_EXECUTION_AFFECTING_PATHS: tuple[str, ...] = (
    "src/offline_rag/",
    str(LOCKED_CAMPAIGN_REL),
    *(str(path) for path in LOCKED_ADVERSARIAL_FIXTURE_RELS),
    *(str(path) for path in LOCKED_BENIGN_CONTROL_RELS),
)

AUTHORITATIVE_NOT_AUTHORIZED_MSG = (
    "authoritative measure-once execution is not authorized"
)


@dataclass(frozen=True)
class ProvenanceContext:
    """Verified Git + campaign-byte provenance for a 13B run."""

    repo_root: Path
    executable_harness_sha: str
    authority_baseline_sha: str
    campaign_blob_sha: str
    campaign_path: Path


def git_blob_sha1(content: bytes) -> str:
    """Return the Git blob object ID for ``content`` (``git hash-object`` semantics)."""
    header = b"blob " + str(len(content)).encode("ascii") + b"\0"
    return hashlib.sha1(header + content).hexdigest()


def _run_git(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise SecurityEvalError(f"git invocation failed: {exc}") from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise SecurityEvalError(f"git {' '.join(args)} failed: {err}")
    return completed.stdout.strip()


def resolve_git_repo_root(repo_root: Path) -> Path:
    """Resolve and verify the Git toplevel for this offline-rag worktree."""
    root = Path(repo_root).resolve()
    toplevel = Path(_run_git(root, "rev-parse", "--show-toplevel")).resolve()
    if toplevel != root:
        raise SecurityEvalError(
            f"repo_root {root} is not the git toplevel {toplevel}"
        )
    marker = toplevel / "src" / "offline_rag"
    if not marker.is_dir():
        raise SecurityEvalError(
            f"git toplevel {toplevel} is not an offline-rag project worktree"
        )
    return toplevel


def resolve_verified_head_sha(repo_root: Path) -> str:
    """Return the full 40-char HEAD commit SHA (detached HEAD allowed)."""
    root = resolve_git_repo_root(repo_root)
    sha = _run_git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if not _SHA1_40_RE.fullmatch(sha):
        raise SecurityEvalError(
            f"HEAD commit SHA must be 40 lowercase hex characters; got {sha!r}"
        )
    return sha


def assert_execution_affecting_paths_clean(repo_root: Path) -> None:
    """Fail closed on staged, unstaged, or untracked drift in the locked path set."""
    root = resolve_git_repo_root(repo_root)
    porcelain = _run_git(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *SECURITY_13B_EXECUTION_AFFECTING_PATHS,
    )
    if porcelain:
        raise SecurityEvalError(
            "execution-affecting paths are dirty (staged/unstaged/untracked); "
            f"refusing to run:\n{porcelain}"
        )


def locked_campaign_path(repo_root: Path) -> Path:
    return (Path(repo_root).resolve() / LOCKED_CAMPAIGN_REL).resolve()


def verify_locked_campaign_blob(repo_root: Path, campaign_path: Path) -> str:
    """Require campaign_path is the locked file and bytes match the accepted blob."""
    root = Path(repo_root).resolve()
    expected = locked_campaign_path(root)
    actual = Path(campaign_path).expanduser().resolve()
    if actual != expected:
        raise SecurityEvalError(
            "campaign_path must be the locked 13B campaign file "
            f"{expected}; got {actual}"
        )
    content = actual.read_bytes()
    blob = git_blob_sha1(content)
    if blob != ACCEPTED_CAMPAIGN_GIT_BLOB_SHA:
        raise SecurityEvalError(
            "campaign Git blob SHA mismatch: "
            f"expected {ACCEPTED_CAMPAIGN_GIT_BLOB_SHA}, got {blob}"
        )
    return blob


def assert_frozen_campaign_identities(campaign: SecurityCampaignV1) -> None:
    """Require frozen seccamp_ / secinv_ identities (Q2)."""
    if campaign.campaign_identity_hash != FROZEN_SECCAMP_13B:
        raise SecurityEvalError(
            "seccamp_ mismatch: "
            f"expected {FROZEN_SECCAMP_13B}, got {campaign.campaign_identity_hash}"
        )
    if campaign.registry_hash != FROZEN_SECINV_13B:
        raise SecurityEvalError(
            "secinv_ mismatch: "
            f"expected {FROZEN_SECINV_13B}, got {campaign.registry_hash}"
        )


def collect_git_and_campaign_provenance(
    *,
    repo_root: Path,
    campaign_path: Path,
) -> ProvenanceContext:
    """Shared Git + campaign-byte provenance (both run modes)."""
    root = resolve_git_repo_root(repo_root)
    executable = resolve_verified_head_sha(root)
    assert_execution_affecting_paths_clean(root)
    blob = verify_locked_campaign_blob(root, campaign_path)
    return ProvenanceContext(
        repo_root=root,
        executable_harness_sha=executable,
        authority_baseline_sha=MEASURE_ONCE_AUTHORITY_BASELINE_SHA,
        campaign_blob_sha=blob,
        campaign_path=locked_campaign_path(root),
    )


def assert_authority_baseline(value: str) -> None:
    if value != MEASURE_ONCE_AUTHORITY_BASELINE_SHA:
        raise SecurityEvalError(
            "authority_baseline_sha mismatch: "
            f"expected {MEASURE_ONCE_AUTHORITY_BASELINE_SHA}, got {value}"
        )


def authoritative_campaign_result_root(repo_root: Path) -> Path:
    """Exact Q3 authoritative root for the frozen seccamp_."""
    from offline_rag.evaluation.security_13.paths import authoritative_results_root

    return (authoritative_results_root(repo_root) / FROZEN_SECCAMP_13B).resolve()


def assert_authoritative_root_absent(repo_root: Path) -> None:
    """Fail closed if the Q3 root exists as file, directory, or symlink."""
    target = authoritative_campaign_result_root(repo_root)
    if target.exists() or target.is_symlink():
        raise SecurityEvalError(
            "authoritative result root already exists "
            f"(no overwrite): {target}"
        )
