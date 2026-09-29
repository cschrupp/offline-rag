"""Slice 13B authoritative one-shot body tests (simulated roots only)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from offline_rag.evaluation.security_13 import (
    FROZEN_SECCAMP_13B,
    SecurityEvalError,
    authoritative_results_root,
    run_security_13b_authoritative,
    validate_authoritative_artifact_set,
)
from offline_rag.evaluation.security_13.harness import (
    _allocate_authoritative_staging,
    _publish_authoritative_root,
    _write_campaign_artifacts,
)
from offline_rag.evaluation.security_13.provenance import (
    authorization_consumed_marker,
    resolve_verified_head_sha,
)

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "eval" / "fixtures" / "security"
CAMPAIGN = FIX / "campaigns" / "13b_query_path_adversarial_v1.json"


@pytest.fixture
def simulated_auth_fs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect Q3 / authz / staging under tmp_path; never touch real Q3."""
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.assert_execution_affecting_paths_clean",
        lambda _repo: None,
    )
    head = resolve_verified_head_sha(REPO)
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.REQUIRED_EXECUTABLE_HARNESS_SHA",
        head,
    )

    q3_parent = tmp_path / "eval" / "results" / "security_13b"
    q3_parent.mkdir(parents=True)
    authz_root = tmp_path / "eval" / "results" / "security_13b_authz"
    staging_parent = tmp_path / "eval" / "results" / "security_13b_staging"
    staging_parent.mkdir(parents=True)

    def _lexical(_repo: Path) -> Path:
        return q3_parent / FROZEN_SECCAMP_13B

    def _marker(_repo: Path) -> Path:
        return authz_root / FROZEN_SECCAMP_13B / "authorization_consumed"

    def _allocate(_repo: Path) -> Path:
        return Path(tempfile.mkdtemp(prefix="sec13b_auth_", dir=str(staging_parent)))

    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.authoritative_campaign_result_root_lexical",
        _lexical,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.harness.authoritative_campaign_result_root_lexical",
        _lexical,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.authoritative_campaign_result_root",
        lambda repo: _lexical(repo).resolve(strict=False),
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.harness.authoritative_campaign_result_root",
        lambda repo: _lexical(repo).resolve(strict=False),
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.authorization_consumed_marker",
        _marker,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.harness._allocate_authoritative_staging",
        _allocate,
    )
    real_q3 = authoritative_results_root(REPO)
    before = list(real_q3.rglob("*")) if real_q3.exists() else []
    yield {
        "q3": q3_parent / FROZEN_SECCAMP_13B,
        "q3_parent": q3_parent,
        "authz": authz_root / FROZEN_SECCAMP_13B / "authorization_consumed",
        "staging_parent": staging_parent,
        "real_q3": real_q3,
        "real_q3_before": before,
    }
    after = list(real_q3.rglob("*")) if real_q3.exists() else []
    assert after == before


def test_preflight_failure_not_consumed_zero_auth_writes(
    simulated_auth_fs: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.REQUIRED_EXECUTABLE_HARNESS_SHA",
        "0" * 40,
    )
    result = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="pf",
    )
    assert result.run_status == "failed_preflight"
    assert result.authorization_consumed is False
    assert result.aggregate.campaign_outcome is None
    assert not simulated_auth_fs["q3"].exists()
    assert not simulated_auth_fs["authz"].exists()


def test_successful_simulated_run_publishes_once(simulated_auth_fs: dict) -> None:
    result = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="ok",
    )
    assert result.run_status == "completed"
    assert result.authorization_consumed is True
    assert result.aggregate.campaign_outcome == "fail"  # UNEVALUABLE science
    q3 = simulated_auth_fs["q3"]
    assert q3.is_dir()
    assert (q3 / "run_manifest.json").is_file()
    assert (q3 / "aggregate.json").is_file()
    assert (q3 / "report.md").is_file()
    assert len(list((q3 / "cases" / "adversarial").glob("*.json"))) == 7
    assert len(list((q3 / "cases" / "benign").glob("*.json"))) == 5
    assert simulated_auth_fs["authz"].is_file()


def test_failure_after_first_case_consumes_no_second_run(
    simulated_auth_fs: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}
    real = __import__(
        "offline_rag.evaluation.security_13.harness", fromlist=["run_case_on_query_path"]
    ).run_case_on_query_path

    def _boom(case, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            return real(case, **kwargs)
        raise RuntimeError("injected failure after first case")

    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.harness.run_case_on_query_path",
        _boom,
    )
    result = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="fail_mid",
    )
    assert result.run_status == "failed_during_execution"
    assert result.authorization_consumed is True
    assert result.aggregate.campaign_outcome is None
    assert not simulated_auth_fs["q3"].exists()
    assert simulated_auth_fs["authz"].is_file()

    second = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="fail_mid_2",
    )
    assert second.run_status == "failed_preflight"
    assert second.authorization_consumed is False
    assert "already consumed" in (second.error or "")


def test_artifact_validation_failure_consumes_no_publish(
    simulated_auth_fs: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _bad_validate(*_a, **_k):  # type: ignore[no-untyped-def]
        raise SecurityEvalError("authoritative artifact missing or empty before publish")

    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.harness.validate_authoritative_artifact_set",
        _bad_validate,
    )
    result = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="bad_art",
    )
    assert result.run_status == "failed_during_execution"
    assert result.authorization_consumed is True
    assert not simulated_auth_fs["q3"].exists()


def test_publish_failure_consumes_no_retry(
    simulated_auth_fs: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _bad_publish(_staging: Path, _q3: Path) -> None:
        raise SecurityEvalError("authoritative publish failed (authorization consumed)")

    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.harness._publish_authoritative_root",
        _bad_publish,
    )
    result = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="bad_pub",
    )
    assert result.run_status == "failed_during_execution"
    assert result.authorization_consumed is True
    assert not simulated_auth_fs["q3"].exists()
    second = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="bad_pub_2",
    )
    assert second.run_status == "failed_preflight"
    assert "already consumed" in (second.error or "")


def test_existing_q3_root_failed_preflight_not_consumed(
    simulated_auth_fs: dict,
) -> None:
    simulated_auth_fs["q3"].mkdir(parents=True)
    result = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="exists",
    )
    assert result.run_status == "failed_preflight"
    assert result.authorization_consumed is False
    assert not simulated_auth_fs["authz"].exists()


def test_validate_authoritative_artifact_set_requires_complete_tree(
    tmp_path: Path,
) -> None:
    with pytest.raises(SecurityEvalError, match="missing or empty"):
        validate_authoritative_artifact_set(
            tmp_path, adversarial_ids=["a"], benign_ids=["b"]
        )
