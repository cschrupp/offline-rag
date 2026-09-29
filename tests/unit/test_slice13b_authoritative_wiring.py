"""Slice 13B pre-authoritative wiring tests (WQ1–WQ7; no measure-once)."""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from offline_rag.core.ids import PROMPT_GROUNDED_V1
from offline_rag.evaluation.security_13 import (
    ACCEPTED_CAMPAIGN_GIT_BLOB_SHA,
    AUTHORITATIVE_NOT_AUTHORIZED_MSG,
    DESIGN_AUTHORITY_SHA_13B,
    FROZEN_SECCAMP_13B,
    FROZEN_SECINV_13B,
    GENERATOR_PROBE_POLICY_13B_V1,
    MEASURE_ONCE_AUTHORITY_BASELINE_SHA,
    SLICE13B_BASELINE_SHA,
    SecurityEvalError,
    authoritative_results_root,
    collect_git_and_campaign_provenance,
    git_blob_sha1,
    run_security_13b_authoritative,
    run_security_13b_dryrun,
)
from offline_rag.evaluation.security_13.contracts import SecurityCampaignRunManifestV1
from offline_rag.evaluation.security_13.harness import (
    run_security_13b_authoritative as authoritative_fn,
)
from offline_rag.evaluation.security_13.harness import run_security_13b_dryrun as dryrun_fn
from offline_rag.evaluation.security_13.provenance import (
    assert_authority_baseline,
    assert_execution_affecting_paths_clean,
    authoritative_campaign_result_root,
    resolve_verified_head_sha,
    verify_locked_campaign_blob,
)

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "eval" / "fixtures" / "security"
CAMPAIGN = FIX / "campaigns" / "13b_query_path_adversarial_v1.json"


def _manifest_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "seccamp_": FROZEN_SECCAMP_13B,
        "secinv_": FROZEN_SECINV_13B,
        "run_id": "t1",
        "run_mode": "dry_run",
        "prompt_contract": PROMPT_GROUNDED_V1,
        "generator_probe_policy": GENERATOR_PROBE_POLICY_13B_V1,
        "product_default_recovery_enabled": False,
        "recovery_execution_mode": "disabled",
        "output_root": "/tmp/dry",
        "campaign_path": str(CAMPAIGN),
        "design_authority_sha": DESIGN_AUTHORITY_SHA_13B,
        "slice13b_baseline_sha": SLICE13B_BASELINE_SHA,
        "authority_baseline_sha": MEASURE_ONCE_AUTHORITY_BASELINE_SHA,
        "executable_harness_sha": "a" * 40,
        "campaign_blob_sha": ACCEPTED_CAMPAIGN_GIT_BLOB_SHA,
    }
    base.update(overrides)
    return base


def test_manifest_accepts_dry_run_and_authoritative_modes() -> None:
    dry = SecurityCampaignRunManifestV1.model_validate(_manifest_kwargs(run_mode="dry_run"))
    auth = SecurityCampaignRunManifestV1.model_validate(
        _manifest_kwargs(run_mode="authoritative")
    )
    assert dry.run_mode == "dry_run"
    assert auth.run_mode == "authoritative"


def test_manifest_rejects_unknown_run_mode_and_missing_provenance() -> None:
    with pytest.raises(ValidationError):
        SecurityCampaignRunManifestV1.model_validate(
            _manifest_kwargs(run_mode="measure_once")
        )
    for field in (
        "authority_baseline_sha",
        "executable_harness_sha",
        "campaign_blob_sha",
    ):
        payload = _manifest_kwargs()
        del payload[field]
        with pytest.raises(ValidationError):
            SecurityCampaignRunManifestV1.model_validate(payload)


def test_git_blob_sha_matches_accepted_campaign_bytes() -> None:
    content = CAMPAIGN.read_bytes()
    assert git_blob_sha1(content) == ACCEPTED_CAMPAIGN_GIT_BLOB_SHA
    assert verify_locked_campaign_blob(REPO, CAMPAIGN) == ACCEPTED_CAMPAIGN_GIT_BLOB_SHA


def test_authority_baseline_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SecurityEvalError, match="authority_baseline_sha mismatch"):
        assert_authority_baseline("0" * 40)

    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.assert_execution_affecting_paths_clean",
        lambda _repo: None,
    )
    good = collect_git_and_campaign_provenance(
        repo_root=REPO, campaign_path=CAMPAIGN
    )
    from offline_rag.evaluation.security_13.provenance import ProvenanceContext

    bad = ProvenanceContext(
        repo_root=good.repo_root,
        executable_harness_sha=good.executable_harness_sha,
        authority_baseline_sha="0" * 40,
        campaign_blob_sha=good.campaign_blob_sha,
        campaign_path=good.campaign_path,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.harness.collect_git_and_campaign_provenance",
        lambda **_kwargs: bad,
    )
    with pytest.raises(SecurityEvalError, match="authority_baseline_sha mismatch"):
        run_security_13b_dryrun(
            campaign_path=CAMPAIGN,
            security_fixture_dir=FIX,
            output_dir=tmp_path / "should_not_allocate",
            run_id="bad_base",
            repo_root=REPO,
        )
    assert not (tmp_path / "should_not_allocate").exists()


def test_campaign_byte_drift_fails_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.assert_execution_affecting_paths_clean",
        lambda _repo: None,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.ACCEPTED_CAMPAIGN_GIT_BLOB_SHA",
        "0" * 40,
    )
    with pytest.raises(SecurityEvalError, match="campaign Git blob SHA mismatch"):
        collect_git_and_campaign_provenance(repo_root=REPO, campaign_path=CAMPAIGN)


@pytest.mark.parametrize("drift_kind", ["unstaged", "staged", "untracked"])
def test_dirty_execution_affecting_paths_fail_preflight(
    tmp_path: Path, drift_kind: str
) -> None:
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    (repo / "src" / "offline_rag").mkdir(parents=True)
    (repo / "src" / "offline_rag" / "marker.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    subprocess.run(["git", "add", "src/offline_rag/marker.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    target = repo / "src" / "offline_rag" / "marker.py"
    if drift_kind == "unstaged":
        target.write_text("x = 2\n", encoding="utf-8")
    elif drift_kind == "staged":
        target.write_text("x = 2\n", encoding="utf-8")
        subprocess.run(["git", "add", "src/offline_rag/marker.py"], cwd=repo, check=True)
    else:
        (repo / "src" / "offline_rag" / "extra.py").write_text("y = 1\n", encoding="utf-8")
    with pytest.raises(SecurityEvalError, match="execution-affecting paths are dirty"):
        assert_execution_affecting_paths_clean(repo)


def test_runners_reject_caller_supplied_executable_sha_kwargs() -> None:
    for fn in (dryrun_fn, authoritative_fn):
        params = inspect.signature(fn).parameters
        assert "executable_harness_sha" not in params
        assert "assume_sha" not in params
        assert "override_sha" not in params
        with pytest.raises(TypeError):
            fn(  # type: ignore[misc]
                campaign_path=CAMPAIGN,
                security_fixture_dir=FIX,
                repo_root=REPO,
                executable_harness_sha="0" * 40,
            )


def test_dryrun_provenance_complete_and_excludes_q3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.assert_execution_affecting_paths_clean",
        lambda _repo: None,
    )
    expected_head = resolve_verified_head_sha(REPO)
    auth_root = authoritative_results_root(REPO)
    before = list(auth_root.rglob("*")) if auth_root.exists() else []
    result = run_security_13b_dryrun(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        output_dir=tmp_path / "dry_prov",
        run_id="prov",
        repo_root=REPO,
    )
    assert result.run_status == "completed"
    assert result.aggregate.campaign_outcome == "fail"
    m = result.manifest
    assert m.run_mode == "dry_run"
    assert m.authority_baseline_sha == MEASURE_ONCE_AUTHORITY_BASELINE_SHA
    assert m.executable_harness_sha == expected_head
    assert m.campaign_blob_sha == ACCEPTED_CAMPAIGN_GIT_BLOB_SHA
    assert m.design_authority_sha == DESIGN_AUTHORITY_SHA_13B
    assert m.slice13b_baseline_sha == SLICE13B_BASELINE_SHA
    assert m.seccamp_ == FROZEN_SECCAMP_13B
    assert m.secinv_ == FROZEN_SECINV_13B
    assert m.product_default_recovery_enabled is False
    assert m.recovery_execution_mode == "disabled"
    after = list(auth_root.rglob("*")) if auth_root.exists() else []
    assert after == before
    assert not str(result.output_dir.resolve()).startswith(str(auth_root.resolve()))


def test_authoritative_gate_stub_rejects_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.assert_execution_affecting_paths_clean",
        lambda _repo: None,
    )
    q3 = authoritative_campaign_result_root(REPO)
    assert not q3.exists()
    with pytest.raises(SecurityEvalError, match=AUTHORITATIVE_NOT_AUTHORIZED_MSG):
        run_security_13b_authoritative(
            campaign_path=CAMPAIGN,
            security_fixture_dir=FIX,
            repo_root=REPO,
            run_id="gate",
        )
    assert not q3.exists()
    # No staging under tmp or auth parent keyed by this run.
    auth_parent = authoritative_results_root(REPO)
    if auth_parent.exists():
        assert FROZEN_SECCAMP_13B not in {
            p.name for p in auth_parent.iterdir()
        }


def test_authoritative_fails_if_q3_root_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.assert_execution_affecting_paths_clean",
        lambda _repo: None,
    )
    fake_q3 = tmp_path / "seccamp_already"
    fake_q3.mkdir()
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.provenance.authoritative_campaign_result_root",
        lambda _repo: fake_q3,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.security_13.harness.authoritative_campaign_result_root",
        lambda _repo: fake_q3,
    )
    with pytest.raises(SecurityEvalError, match="already exists"):
        run_security_13b_authoritative(
            campaign_path=CAMPAIGN,
            security_fixture_dir=FIX,
            repo_root=REPO,
        )
