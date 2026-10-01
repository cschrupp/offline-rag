"""Unit tests for Slice 14C authoritative execution helpers (no full campaign)."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.evaluation.performance_14.aggregate import build_run_aggregate
from offline_rag.evaluation.performance_14.contracts import Performance14Error
from offline_rag.evaluation.performance_14.paths import (
    allocate_authoritative_run_dir,
    allocate_dryrun_run_dir,
    assert_under_authoritative_root,
)
from offline_rag.evaluation.performance_14.run_authoritative_14c import (
    EXECUTION_AUTHORIZATION_STATEMENT_14C,
    run_authoritative_14c,
)
from offline_rag.evaluation.performance_14.suite_14c import (
    effective_config_id_14c,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCKED_PERFCFG = (
    "perfcfg_aae1ea9b048e414338f0a38b13cb31132505920c406293e1e9f8e35595faa42d"
)
LOCKED_PERFSUITE = (
    "perfsuite_5248892df382995ac96ec2b09aea61bf27510673b93e0d816d6a255a2f4305ba"
)


def test_scientific_config_id_unchanged_by_execution_module() -> None:
    assert effective_config_id_14c() == LOCKED_PERFCFG


def test_authoritative_path_allocator_is_create_exclusive(tmp_path: Path) -> None:
    # Use a fake repo_root layout with performance_14 under eval/results.
    repo = tmp_path / "repo"
    target_parent = repo / "eval" / "results" / "performance_14"
    target_parent.mkdir(parents=True)
    # Monkey via absolute path: allocate uses Path.cwd-relative reserved root.
    # Call assert helper directly with constructed candidate under reserved root.
    suite = LOCKED_PERFSUITE
    run = "perfrun_" + ("a" * 64)
    candidate = target_parent / suite / run
    # Patch by writing under real reserved root in tmp via repo_root argument.
    allocated = allocate_authoritative_run_dir(
        suite_id=suite, run_id=run, repo_root=repo
    )
    assert allocated == candidate.resolve()
    allocated.mkdir(parents=True)
    with pytest.raises(Performance14Error, match="already exists"):
        allocate_authoritative_run_dir(suite_id=suite, run_id=run, repo_root=repo)


def test_dryrun_allocator_still_rejects_authoritative_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "eval" / "results" / "performance_14_dryrun").mkdir(parents=True)
    with pytest.raises(Performance14Error, match="dryrun_parent must be named"):
        allocate_dryrun_run_dir(
            suite_id=LOCKED_PERFSUITE,
            run_id="perfrun_" + ("b" * 64),
            repo_root=repo,
            dryrun_parent=repo / "eval" / "results" / "performance_14",
        )


def test_authoritative_aggregate_flags_accepted() -> None:
    agg = build_run_aggregate(
        suite_id=LOCKED_PERFSUITE,
        run_id="perfrun_" + ("c" * 64),
        run_status="failed_preflight",
        benchmark_level="B",
        cases=[],
        diagnostic_only=False,
        authoritative=True,
        evidence_class="AUTHORITATIVE",
    )
    assert agg.authoritative is True
    assert agg.diagnostic_only is False
    assert agg.evidence_class == "AUTHORITATIVE"


def test_execution_requires_explicit_authorization() -> None:
    with pytest.raises(Performance14Error, match=EXECUTION_AUTHORIZATION_STATEMENT_14C):
        run_authoritative_14c(confirm_execution_authorization=False)


def test_assert_under_authoritative_root_rejects_dryrun(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    dry = repo / "eval" / "results" / "performance_14_dryrun" / "x"
    dry.mkdir(parents=True)
    with pytest.raises(Performance14Error, match="dry-run root"):
        assert_under_authoritative_root(dry, repo_root=repo)
