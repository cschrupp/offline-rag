"""Slice 13B security harness tests (OD-13-7…13; dry-run only)."""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from urllib import request as urllib_request

import pytest

from offline_rag.evaluation.security_13 import (
    DESIGN_AUTHORITY_SHA_13B,
    GENERATOR_PROBE_POLICY_13B_V1,
    SLICE13B_BASELINE_SHA,
    InvariantStatusV1,
    SecurityEvalError,
    assert_outside_authoritative_root,
    authoritative_results_root,
    compute_benign_control_identity_hash,
    compute_campaign_identity_hash,
    evaluate_benign_control,
    load_benign_control,
    load_security_campaign,
    run_case_on_query_path,
    run_security_13b_dryrun,
)
from offline_rag.evaluation.security_13.capability_probe import (
    CapabilityBlockedError,
    install_capability_probe,
)
from offline_rag.evaluation.security_13.contracts import SECURITY_EVAL_CANARY_TOKEN
from offline_rag.evaluation.security_13.harness import resolve_campaign_population
from offline_rag.evaluation.security_13.loader import assert_population_policy
from offline_rag.evaluation.security_13.paths import allocate_dryrun_run_dir

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "eval" / "fixtures" / "security"
CAMPAIGN = FIX / "campaigns" / "13b_query_path_adversarial_v1.json"


def _status(result, invariant_id: str) -> InvariantStatusV1:
    return next(
        row.status
        for row in result.invariant_outcomes
        if row.invariant_id == invariant_id
    )


def test_frozen_campaign_loads_and_population_resolves() -> None:
    campaign = load_security_campaign(CAMPAIGN)
    assert campaign.campaign_identity_hash.startswith("seccamp_")
    assert campaign.campaign_identity_hash == compute_campaign_identity_hash(campaign)
    assert campaign.slice13b_baseline_sha == SLICE13B_BASELINE_SHA
    assert campaign.design_authority_sha == DESIGN_AUTHORITY_SHA_13B
    assert campaign.population_policy.minimum_per_attack_class == 1
    assert campaign.population_policy.minimum_benign_controls == 5
    adv, ben = resolve_campaign_population(campaign, security_fixture_dir=FIX)
    assert len(adv) == 7
    assert len(ben) == 5
    assert {f.attack_class for f in adv} == set(
        campaign.population_policy.required_attack_classes
    )
    assert all(f.path_under_test == "query_path" for f in adv)
    assert (FIX / "secfx_rewrite_isolation_001_recovery.json").is_file()
    assert all(f.fixture_id != "secfx_rewrite_isolation_001_recovery" for f in adv)


def test_benign_identity_excludes_audit_fields() -> None:
    control = load_benign_control(FIX / "benign" / "benign_procedural_document_001.json")
    digest = compute_benign_control_identity_hash(control)
    assert digest == control.control_identity_hash
    mutated = control.model_copy(
        update={"design_authority_sha": "0" * 40, "slice13b_baseline_sha": "1" * 40}
    )
    assert compute_benign_control_identity_hash(mutated) == digest


def test_population_policy_rejects_non_frozen_minima() -> None:
    campaign = load_security_campaign(CAMPAIGN)
    bad = campaign.model_copy(
        update={
            "population_policy": campaign.population_policy.model_copy(
                update={"minimum_benign_controls": 4}
            )
        }
    )
    with pytest.raises(SecurityEvalError, match="minimum_benign_controls must be 5"):
        assert_population_policy(
            bad,
            attack_class_counts={c: 1 for c in campaign.population_policy.required_attack_classes},
        )


def test_authoritative_root_hard_reject_direct_and_traversal(
    tmp_path: Path,
) -> None:
    auth = authoritative_results_root(REPO)
    with pytest.raises(SecurityEvalError, match="reserved authoritative"):
        assert_outside_authoritative_root(auth, repo_root=REPO)
    with pytest.raises(SecurityEvalError, match="reserved authoritative"):
        assert_outside_authoritative_root(auth / "child", repo_root=REPO)
    sneaky = auth / ".." / "security_13b" / "attempt"
    with pytest.raises(SecurityEvalError, match="reserved authoritative"):
        assert_outside_authoritative_root(sneaky, repo_root=REPO)
    ok = assert_outside_authoritative_root(tmp_path / "dry", repo_root=REPO)
    assert ok == (tmp_path / "dry").resolve()


def test_authoritative_root_hard_reject_symlink(tmp_path: Path) -> None:
    auth = authoritative_results_root(REPO)
    auth.mkdir(parents=True, exist_ok=True)
    link = tmp_path / "alias_auth"
    try:
        link.symlink_to(auth)
    except OSError:
        pytest.skip("symlink unavailable")
    with pytest.raises(SecurityEvalError, match="reserved authoritative"):
        assert_outside_authoritative_root(link / "run1", repo_root=REPO)


def test_dryrun_dir_immutable(tmp_path: Path) -> None:
    first = allocate_dryrun_run_dir(
        run_id="r1", output_dir=tmp_path / "r1", repo_root=REPO
    )
    first.mkdir()
    with pytest.raises(SecurityEvalError, match="already exists"):
        allocate_dryrun_run_dir(run_id="r1", output_dir=tmp_path / "r1", repo_root=REPO)


def test_observations_from_executed_surfaces_not_synthesized_policy() -> None:
    campaign = load_security_campaign(CAMPAIGN)
    adv, _ben = resolve_campaign_population(campaign, security_fixture_dir=FIX)
    obs, _trace = run_case_on_query_path(adv[0], repo_root=REPO)
    assert obs.product_default_recovery_enabled is False
    assert obs.recovery_execution_mode == "disabled"
    assert obs.recovery_components_entered == []
    assert obs.capability_invocations == []
    assert obs.observed_original_query == adv[0].user_query
    assert obs.observed_corpus_scope == "ics_modules"
    # No security-policy control surface on the generation path.
    assert obs.configured_security_policy is None
    assert obs.observed_security_policy is None
    result = __import__(
        "offline_rag.evaluation.security_13", fromlist=["evaluate_adversarial_fixture"]
    ).evaluate_adversarial_fixture(adv[0], obs)
    assert _status(result, "security_policy_immutable_v1") == InvariantStatusV1.UNEVALUABLE
    assert _status(result, "citation_scope_v1") == InvariantStatusV1.HOLDS
    assert _status(result, "original_query_immutable_v1") == InvariantStatusV1.HOLDS
    assert _status(result, "corpus_scope_immutable_v1") == InvariantStatusV1.HOLDS


def test_canary_install_and_programmed_leak_violation() -> None:
    control = load_benign_control(
        FIX / "benign" / "benign_system_word_literal_001.json"
    )
    obs, trace = run_case_on_query_path(control, repo_root=REPO)
    assert trace.canary_seen_in_request is True
    assert obs.protected_prompt_canary == SECURITY_EVAL_CANARY_TOKEN
    assert (
        _status(
            evaluate_benign_control(control, obs),
            "protected_prompt_canary_non_disclosure_v1",
        )
        == InvariantStatusV1.HOLDS
    )

    leak = json.dumps(
        {
            "abstain": False,
            "answer": f"token {SECURITY_EVAL_CANARY_TOKEN}",
            "citation_ids": list(control.allowed_citation_evidence_ids),
        }
    )
    obs_bad, _ = run_case_on_query_path(
        control, repo_root=REPO, response_override=leak
    )
    bad = evaluate_benign_control(control, obs_bad)
    assert (
        _status(bad, "protected_prompt_canary_non_disclosure_v1")
        == InvariantStatusV1.VIOLATED
    )


def test_illegal_fake_citation_blocked_by_executor_not_control_plane_violation() -> None:
    """Raw fake may emit illicit IDs; application must not emit them."""
    control = load_benign_control(
        FIX / "benign" / "benign_citation_dense_001.json"
    )
    bad_json = json.dumps(
        {
            "abstain": False,
            "answer": "Deterministic security harness response.",
            "citation_ids": ["ev_not_allowed"],
        }
    )
    obs, _ = run_case_on_query_path(
        control, repo_root=REPO, response_override=bad_json
    )
    assert obs.emitted_citation_ids == []
    result = evaluate_benign_control(control, obs)
    assert _status(result, "citation_scope_v1") == InvariantStatusV1.HOLDS


def test_capability_probe_blocks_subprocess_without_side_effect() -> None:
    marker = {"ran": False}
    real_run = subprocess.run

    def _sentinel(*args, **kwargs):  # type: ignore[no-untyped-def]
        marker["ran"] = True
        return real_run(*args, **kwargs)

    subprocess.run = _sentinel  # type: ignore[assignment]
    try:
        with install_capability_probe(repo_root=REPO) as probe:
            assert probe.complete
            with pytest.raises(CapabilityBlockedError, match="subprocess.run"):
                subprocess.run(["true"], check=False, capture_output=True)
        assert "subprocess.run" in probe.invocations
        assert marker["ran"] is False
    finally:
        subprocess.run = real_run  # type: ignore[assignment]


def test_capability_probe_blocks_pathlib_os_open_and_network(tmp_path: Path) -> None:
    """Active-probe filesystem coverage must include pathlib and os.open."""
    import os

    repo_target = (
        REPO
        / "eval"
        / "fixtures"
        / "security"
        / "benign"
        / "benign_procedural_document_001.json"
    )
    assert repo_target.is_file()
    # Temp paths are NOT wholesale-allowlisted.
    temp_target = tmp_path / "probe_secret.txt"
    temp_target.write_text("before", encoding="utf-8")

    with install_capability_probe(repo_root=REPO) as probe:
        assert probe.complete
        with pytest.raises(CapabilityBlockedError, match="open:"):
            open(repo_target, encoding="utf-8")  # noqa: SIM115
        with pytest.raises(CapabilityBlockedError, match="open:"):
            repo_target.read_text(encoding="utf-8")
        with pytest.raises(CapabilityBlockedError, match="open:"):
            temp_target.write_text("after", encoding="utf-8")
        with pytest.raises(CapabilityBlockedError, match="os.open:"):
            os.open(str(temp_target), os.O_RDONLY)
        with pytest.raises(CapabilityBlockedError, match="socket.socket"):
            socket.socket()
        with pytest.raises(CapabilityBlockedError, match="urlopen"):
            urllib_request.urlopen("http://127.0.0.1:9/")

    assert any(item.startswith("open:") for item in probe.invocations)
    assert any(item.startswith("os.open:") for item in probe.invocations)
    assert "socket.socket" in probe.invocations
    assert "urllib.request.urlopen" in probe.invocations
    # Side effects never occurred under the active probe.
    assert temp_target.read_text(encoding="utf-8") == "before"
    assert "benign_procedural_document_001" in repo_target.read_text(encoding="utf-8")


def test_campaign_preflight_rejects_bad_hash(tmp_path: Path) -> None:
    payload = json.loads(CAMPAIGN.read_text(encoding="utf-8"))
    payload["adversarial_cases"][0]["advfx_hash"] = "advfx_" + ("0" * 64)
    bad = tmp_path / "bad_campaign.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    result = run_security_13b_dryrun(
        campaign_path=bad,
        security_fixture_dir=FIX,
        output_dir=tmp_path / "out_bad",
        run_id="bad",
        repo_root=REPO,
    )
    assert result.run_status == "failed_preflight"
    assert result.aggregate.campaign_outcome is None


def test_full_dryrun_nested_aggregate_and_honest_fail(tmp_path: Path) -> None:
    """Campaign completes but fails closed: security_policy is UNEVALUABLE."""
    result = run_security_13b_dryrun(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        output_dir=tmp_path / "dry_full",
        run_id="full",
        repo_root=REPO,
    )
    assert result.run_status == "completed"
    assert result.error is None
    assert result.campaign is not None
    assert result.aggregate.campaign_outcome == "fail"
    assert result.aggregate.population.adversarial_total == 7
    assert result.aggregate.population.benign_total == 5
    assert result.aggregate.benign.false_positive_count == 0
    assert "security_policy_immutable_v1" in result.aggregate.per_invariant.adversarial
    assert (
        result.aggregate.per_invariant.adversarial[
            "security_policy_immutable_v1"
        ].unevaluable
        == 7
    )
    assert result.aggregate.product_default_recovery_enabled is False
    assert result.aggregate.recovery_execution_mode == "disabled"
    assert result.manifest.generator_probe_policy == GENERATOR_PROBE_POLICY_13B_V1
    dumped = json.loads((result.output_dir / "aggregate.json").read_text(encoding="utf-8"))
    assert "population" in dumped
    assert "adversarial" in dumped and "pass" in dumped["adversarial"]
    assert "benign" in dumped and "false_positive_count" in dumped["benign"]
    assert "per_invariant" in dumped
    assert (result.output_dir / "run_manifest.json").is_file()
    assert (result.output_dir / "report.md").is_file()
    assert len(list((result.output_dir / "cases" / "adversarial").glob("*.json"))) == 7
    assert len(list((result.output_dir / "cases" / "benign").glob("*.json"))) == 5


def test_fp_accounting_on_benign_violation(tmp_path: Path) -> None:
    control = load_benign_control(
        FIX / "benign" / "benign_system_word_literal_001.json"
    )
    leak = json.dumps(
        {
            "abstain": False,
            "answer": f"leaked {SECURITY_EVAL_CANARY_TOKEN}",
            "citation_ids": list(control.allowed_citation_evidence_ids),
        }
    )

    def _override(case_id: str) -> str | None:
        if case_id == control.control_id:
            return leak
        return None

    result = run_security_13b_dryrun(
        campaign_path=CAMPAIGN,
        security_fixture_dir=FIX,
        output_dir=tmp_path / "dry_fp",
        run_id="fp",
        repo_root=REPO,
        response_override_for_case=_override,
    )
    assert result.run_status == "completed"
    assert result.aggregate.campaign_outcome == "fail"
    assert result.aggregate.benign.false_positive_count == 1
    assert result.aggregate.benign.violation_case_count == 1
    assert result.aggregate.benign.false_positive_rate == pytest.approx(0.2)
