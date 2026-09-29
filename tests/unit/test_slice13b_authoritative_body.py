"""Slice 13B authoritative one-shot body tests (simulated roots only)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from offline_rag.evaluation.security_13 import (
    ACCEPTED_CAMPAIGN_GIT_BLOB_SHA,
    DESIGN_AUTHORITY_SHA_13B,
    FROZEN_ADVERSARIAL_FIXTURE_IDS_13B,
    FROZEN_BENIGN_CONTROL_IDS_13B,
    FROZEN_SECCAMP_13B,
    FROZEN_SECINV_13B,
    MEASURE_ONCE_AUTHORITY_BASELINE_SHA,
    SLICE13B_BASELINE_SHA,
    SecurityEvalError,
    authoritative_results_root,
    run_security_13b_authoritative,
    validate_authoritative_artifact_set,
)
from offline_rag.evaluation.security_13.provenance import (
    Q1_EXECUTABLE_PIN_REF,
    assert_executable_harness_pin,
    mark_authorization_consumed,
    read_sealed_q1_executable_pin,
    resolve_verified_head_sha,
    seal_q1_executable_pin_from_verified_head,
)

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "eval" / "fixtures" / "security"
CAMPAIGN = FIX / "campaigns" / "13b_query_path_adversarial_v1.json"


def _init_git_repo(root: Path) -> str:
    (root / "src" / "offline_rag").mkdir(parents=True)
    (root / "src" / "offline_rag" / "x.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    subprocess.run(["git", "add", "src/offline_rag/x.py"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True
    )
    return resolve_verified_head_sha(root)


@pytest.fixture
def simulated_auth_fs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect Q3 / authz / staging under tmp_path; seal Q1 via monkeypatched read."""
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.assert_execution_affecting_paths_clean",
        lambda _repo: None,
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

    head = resolve_verified_head_sha(REPO)
    # Do not create the real Q1 Git ref; simulate sealed pin for REPO runs.
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.read_sealed_q1_executable_pin",
        lambda _repo: head,
    )

    real_q3 = authoritative_results_root(REPO)
    before = list(real_q3.rglob("*")) if real_q3.exists() else []
    yield {
        "q3": q3_parent / FROZEN_SECCAMP_13B,
        "authz": authz_root / FROZEN_SECCAMP_13B / "authorization_consumed",
        "head": head,
        "real_q3": real_q3,
        "real_q3_before": before,
    }
    after = list(real_q3.rglob("*")) if real_q3.exists() else []
    assert after == before


def test_preflight_failure_not_consumed_zero_auth_writes(
    simulated_auth_fs: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.read_sealed_q1_executable_pin",
        lambda _repo: "0" * 40,
    )
    result = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="pf",
    )
    assert result.run_status == "failed_preflight"
    assert result.authorization_consumed is False
    assert not simulated_auth_fs["q3"].exists()
    assert not simulated_auth_fs["authz"].exists()


def test_missing_q1_pin_fails_preflight(
    simulated_auth_fs: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _absent(_repo: Path) -> str:
        raise SecurityEvalError(
            f"Q1 executable pin is not sealed at {Q1_EXECUTABLE_PIN_REF}"
        )

    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.read_sealed_q1_executable_pin",
        _absent,
    )
    result = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="nopin",
    )
    assert result.run_status == "failed_preflight"
    assert result.authorization_consumed is False
    assert "Q1 executable pin is not sealed" in (result.error or "")


def test_successful_simulated_run_publishes_once(simulated_auth_fs: dict) -> None:
    result = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="ok",
    )
    assert result.run_status == "completed"
    assert result.authorization_consumed is True
    assert result.aggregate.campaign_outcome == "fail"
    q3 = simulated_auth_fs["q3"]
    assert q3.is_dir()
    assert len(list((q3 / "cases" / "adversarial").glob("*.json"))) == 7
    assert len(list((q3 / "cases" / "benign").glob("*.json"))) == 5


def test_staging_failure_before_claim_does_not_consume(
    simulated_auth_fs: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_repo: Path) -> Path:
        raise SecurityEvalError("staging allocation failed")

    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.harness._allocate_authoritative_staging",
        _boom,
    )
    result = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="stage_fail",
    )
    assert result.run_status == "failed_preflight"
    assert result.authorization_consumed is False
    assert not simulated_auth_fs["authz"].exists()


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
    second = run_security_13b_authoritative(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        repo_root=REPO,
        run_id="fail_mid_2",
    )
    assert second.run_status == "failed_preflight"
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


def test_atomic_claim_rejects_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = (
        tmp_path
        / "eval"
        / "results"
        / "security_13b_authz"
        / FROZEN_SECCAMP_13B
        / "authorization_consumed"
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.authorization_consumed_marker",
        lambda _repo: marker,
    )
    mark_authorization_consumed(tmp_path)
    with pytest.raises(SecurityEvalError, match="already consumed"):
        mark_authorization_consumed(tmp_path)


def test_q1_git_ref_seal_detached_head_and_no_worktree_file(tmp_path: Path) -> None:
    head = _init_git_repo(tmp_path)
    # Detach HEAD.
    subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=tmp_path, check=True, capture_output=True)
    assert resolve_verified_head_sha(tmp_path) == head
    with pytest.raises(SecurityEvalError, match="not sealed"):
        read_sealed_q1_executable_pin(tmp_path)
    sealed = seal_q1_executable_pin_from_verified_head(tmp_path)
    assert sealed == head
    assert read_sealed_q1_executable_pin(tmp_path) == head
    assert_executable_harness_pin(tmp_path, head)
    # No worktree file dependency.
    assert not (tmp_path / "eval" / "authority" / "security_13b" / "q1_executable_pin").exists()
    with pytest.raises(SecurityEvalError, match="already sealed"):
        seal_q1_executable_pin_from_verified_head(tmp_path)


def test_q1_git_ref_mismatch_fails_pin_check(tmp_path: Path) -> None:
    first = _init_git_repo(tmp_path)
    seal_q1_executable_pin_from_verified_head(tmp_path)
    (tmp_path / "src" / "offline_rag" / "y.py").write_text("y=1\n", encoding="utf-8")
    subprocess.run(["git", "add", "src/offline_rag/y.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "second"], cwd=tmp_path, check=True, capture_output=True
    )
    second = resolve_verified_head_sha(tmp_path)
    assert second != first
    with pytest.raises(SecurityEvalError, match="mismatch vs sealed Q1 pin"):
        assert_executable_harness_pin(tmp_path, second)


def test_validate_authoritative_artifact_set_requires_complete_tree(
    tmp_path: Path,
) -> None:
    with pytest.raises(SecurityEvalError, match="not a directory|exactly OD-13-11|missing"):
        validate_authoritative_artifact_set(
            tmp_path,
            expected_adversarial_ids=list(FROZEN_ADVERSARIAL_FIXTURE_IDS_13B),
            expected_benign_ids=list(FROZEN_BENIGN_CONTROL_IDS_13B),
            expected_seccamp=FROZEN_SECCAMP_13B,
            expected_secinv=FROZEN_SECINV_13B,
            expected_authority_baseline=MEASURE_ONCE_AUTHORITY_BASELINE_SHA,
            expected_executable_sha="a" * 40,
            expected_campaign_blob=ACCEPTED_CAMPAIGN_GIT_BLOB_SHA,
            expected_design_authority=DESIGN_AUTHORITY_SHA_13B,
            expected_slice13b_baseline=SLICE13B_BASELINE_SHA,
            expected_output_root="/tmp/q3",
            expected_campaign_path=str(CAMPAIGN),
        )


def test_validate_rejects_extra_case_file(tmp_path: Path) -> None:
    (tmp_path / "run_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "aggregate.json").write_text("{}", encoding="utf-8")
    (tmp_path / "report.md").write_text("x\n", encoding="utf-8")
    adv = tmp_path / "cases" / "adversarial"
    ben = tmp_path / "cases" / "benign"
    adv.mkdir(parents=True)
    ben.mkdir(parents=True)
    for fid in FROZEN_ADVERSARIAL_FIXTURE_IDS_13B:
        (adv / f"{fid}.json").write_text("{}", encoding="utf-8")
    (adv / "extra.json").write_text("{}", encoding="utf-8")
    for cid in FROZEN_BENIGN_CONTROL_IDS_13B:
        (ben / f"{cid}.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SecurityEvalError, match="match frozen membership exactly"):
        validate_authoritative_artifact_set(
            tmp_path,
            expected_adversarial_ids=list(FROZEN_ADVERSARIAL_FIXTURE_IDS_13B),
            expected_benign_ids=list(FROZEN_BENIGN_CONTROL_IDS_13B),
            expected_seccamp=FROZEN_SECCAMP_13B,
            expected_secinv=FROZEN_SECINV_13B,
            expected_authority_baseline=MEASURE_ONCE_AUTHORITY_BASELINE_SHA,
            expected_executable_sha="a" * 40,
            expected_campaign_blob=ACCEPTED_CAMPAIGN_GIT_BLOB_SHA,
            expected_design_authority=DESIGN_AUTHORITY_SHA_13B,
            expected_slice13b_baseline=SLICE13B_BASELINE_SHA,
            expected_output_root="/tmp/q3",
            expected_campaign_path=str(CAMPAIGN),
        )
