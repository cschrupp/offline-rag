"""Slice 14C unit tests — frozen suite identity stability and fail-closed gates."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from offline_rag.evaluation.performance_14.fixtures import (
    VARIANT_HYBRID,
    VARIANT_HYBRID_RERANK,
)
from offline_rag.evaluation.performance_14.identity import (
    compute_config_identity_hash,
    compute_suite_identity_hash,
)
from offline_rag.evaluation.performance_14.preflight import (
    assert_paired_comparison_invariant,
    assert_treatment_only_config_delta,
)
from offline_rag.evaluation.performance_14.suite_14c import (
    COLD_WARM_14C,
    CORPUS_ID_14C,
    FROZEN_SUITE_REL,
    GOLD_DATASET_ID_14C,
    GOLD_RELATIVE_PATH_14C,
    MEASURED_REPETITIONS_14C,
    POPULATION_IDENTITY_14C,
    QUERY_IDS_14C,
    SUBSTRATE_PIN_14B,
    TREATMENT_DELTA_14C,
    WARMUP_COUNT_14C,
    Performance14Error,
    PerformanceFrozenSuite14CV1,
    assert_gold_semantic_identity_14c,
    build_frozen_suite_artifact_14c,
    build_suite_plan_14c,
    effective_config_id_14c,
    load_frozen_suite_artifact,
    scientific_config_payload_14c,
    validate_frozen_suite_14c,
    write_frozen_suite_artifact,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Locked identities for this freeze (must not drift without a new suite).
LOCKED_PERFSUITE = (
    "perfsuite_5248892df382995ac96ec2b09aea61bf27510673b93e0d816d6a255a2f4305ba"
)
LOCKED_PERFCFG = (
    "perfcfg_aae1ea9b048e414338f0a38b13cb31132505920c406293e1e9f8e35595faa42d"
)
# Pre-rework diagnostic-authority perfcfg_ must not reappear.
LEGACY_DIAGNOSTIC_PERFCFG = (
    "perfcfg_62b39058443c152c0ae7edfe5bee0288e00c857f8e8c9d27b0bc1aaba7c9a7f6"
)


def test_substrate_and_population_pins() -> None:
    assert SUBSTRATE_PIN_14B == "97d38031b99029c2e9b3fd028eadc3a60efef6c0"
    assert GOLD_DATASET_ID_14C.startswith("gold_d3fc157c")
    assert CORPUS_ID_14C.startswith("corpus_040e49a1")
    assert POPULATION_IDENTITY_14C.startswith("perfpop_14c_")
    assert len(QUERY_IDS_14C) == 22
    assert WARMUP_COUNT_14C == 2
    assert MEASURED_REPETITIONS_14C == 10
    assert COLD_WARM_14C == "warm"
    assert TREATMENT_DELTA_14C == (
        "reranker_enabled",
        "reranker_configuration",
        "reranker_config_hash",
        "stage_or_path",
    )


def test_frozen_identities_are_stable() -> None:
    art = validate_frozen_suite_14c(repo_root=REPO_ROOT)
    assert art.suite_identity_hash == LOCKED_PERFSUITE
    assert art.effective_config_id == LOCKED_PERFCFG
    assert art.effective_config_id != LEGACY_DIAGNOSTIC_PERFCFG
    assert art.execution_authorized is False
    assert art.authoritative_results_authorized is False
    assert art.generation_excluded is True
    assert art.baseline_variant == VARIANT_HYBRID
    assert art.treatment_variant == VARIANT_HYBRID_RERANK
    assert len(art.case_ids) == 44


def test_on_disk_artifact_roundtrip_preserves_identity() -> None:
    path = REPO_ROOT / FROZEN_SUITE_REL
    assert path.is_file()
    loaded = load_frozen_suite_artifact(repo_root=REPO_ROOT)
    rebuilt = build_frozen_suite_artifact_14c()
    assert loaded.suite_identity_hash == rebuilt.suite_identity_hash == LOCKED_PERFSUITE
    assert loaded.effective_config_id == rebuilt.effective_config_id == LOCKED_PERFCFG
    assert loaded.model_dump(mode="json") == rebuilt.model_dump(mode="json")


def test_write_is_create_exclusive_and_deterministic(tmp_path: Path) -> None:
    target = tmp_path / "suite.json"
    first = write_frozen_suite_artifact(path=target, repo_root=REPO_ROOT)
    second = write_frozen_suite_artifact(path=target, repo_root=REPO_ROOT)
    assert first == second == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["suite_identity_hash"] == LOCKED_PERFSUITE
    assert payload["effective_config_id"] == LOCKED_PERFCFG
    # Divergent content must fail closed.
    target.write_text('{"contract":"tampered"}\n', encoding="utf-8")
    with pytest.raises(Performance14Error, match="different content"):
        write_frozen_suite_artifact(path=target, repo_root=REPO_ROOT)


def test_suite_hash_stable_under_case_id_and_variant_reordering() -> None:
    plan = build_suite_plan_14c()
    assert plan.suite.suite_identity_hash == LOCKED_PERFSUITE
    reordered_cases = list(reversed(plan.suite.case_ids))
    reordered_variants = list(reversed(plan.suite.variants))
    flipped = plan.suite.model_copy(
        update={
            "case_ids": reordered_cases,
            "variants": reordered_variants,
            "suite_identity_hash": None,
        }
    )
    assert compute_suite_identity_hash(flipped) == LOCKED_PERFSUITE


def test_perfcfg_stable_under_variant_config_key_reordering() -> None:
    plan = build_suite_plan_14c()
    reordered = {
        VARIANT_HYBRID_RERANK: dict(
            reversed(list(plan.variant_configs[VARIANT_HYBRID_RERANK].items()))
        ),
        VARIANT_HYBRID: dict(
            reversed(list(plan.variant_configs[VARIANT_HYBRID].items()))
        ),
    }
    reordered_plan = replace(plan, variant_configs=reordered)
    assert (
        compute_config_identity_hash(scientific_config_payload_14c(reordered_plan))
        == effective_config_id_14c()
        == LOCKED_PERFCFG
    )


def test_perfcfg_excludes_authorization_and_evidence_class_flags() -> None:
    payload = scientific_config_payload_14c()
    assert "diagnostic_only" not in payload
    assert "authoritative" not in payload
    assert "execution_authorized" not in payload
    assert "authoritative_results_authorized" not in payload
    # Injecting those flags into a payload must not be how the frozen id is built.
    polluted = dict(payload)
    polluted["diagnostic_only"] = True
    polluted["authoritative"] = False
    assert compute_config_identity_hash(polluted) != LOCKED_PERFCFG
    assert compute_config_identity_hash(polluted) == LEGACY_DIAGNOSTIC_PERFCFG


def test_membership_change_flips_perfsuite() -> None:
    plan = build_suite_plan_14c()
    mutated = plan.suite.model_copy(
        update={
            "case_ids": plan.suite.case_ids[:-1],
            "suite_identity_hash": None,
        }
    )
    assert compute_suite_identity_hash(mutated) != LOCKED_PERFSUITE


def test_treatment_config_change_flips_perfcfg() -> None:
    plan = build_suite_plan_14c()
    configs = {
        VARIANT_HYBRID: dict(plan.variant_configs[VARIANT_HYBRID]),
        VARIANT_HYBRID_RERANK: dict(plan.variant_configs[VARIANT_HYBRID_RERANK]),
    }
    configs[VARIANT_HYBRID_RERANK]["dense_top_k"] = 99
    mutated_plan = replace(plan, variant_configs=configs)
    assert (
        compute_config_identity_hash(scientific_config_payload_14c(mutated_plan))
        != LOCKED_PERFCFG
    )


def test_undeclared_shared_config_delta_fails_closed() -> None:
    plan = build_suite_plan_14c()
    assert_treatment_only_config_delta(plan)
    configs = {
        VARIANT_HYBRID: dict(plan.variant_configs[VARIANT_HYBRID]),
        VARIANT_HYBRID_RERANK: dict(plan.variant_configs[VARIANT_HYBRID_RERANK]),
    }
    configs[VARIANT_HYBRID_RERANK]["rrf_k"] = 99
    broken = replace(plan, variant_configs=configs)
    with pytest.raises(Performance14Error, match="undeclared treatment"):
        assert_treatment_only_config_delta(broken)


def test_missing_paired_subject_fails_closed() -> None:
    plan = build_suite_plan_14c()
    assert_paired_comparison_invariant(plan)
    broken_cases = tuple(
        spec
        for spec in plan.cases
        if not (
            spec.subject_identity == QUERY_IDS_14C[0]
            and spec.variant == VARIANT_HYBRID_RERANK
        )
    )
    broken = replace(plan, cases=broken_cases)
    with pytest.raises(Performance14Error, match="paired coverage missing"):
        assert_paired_comparison_invariant(broken)


def test_execution_authorization_flags_rejected() -> None:
    art = build_frozen_suite_artifact_14c()
    payload = art.model_dump(mode="json")
    with pytest.raises(ValidationError, match="execution_authorized"):
        PerformanceFrozenSuite14CV1.model_validate(
            {**payload, "execution_authorized": True}
        )
    with pytest.raises(ValidationError, match="authoritative_results_authorized"):
        PerformanceFrozenSuite14CV1.model_validate(
            {**payload, "authoritative_results_authorized": True}
        )


def test_tampered_on_disk_hash_fails_closed(tmp_path: Path) -> None:
    src = REPO_ROOT / FROZEN_SUITE_REL
    raw = json.loads(src.read_text(encoding="utf-8"))
    raw["suite_identity_hash"] = "perfsuite_" + ("0" * 64)
    target = tmp_path / "tampered.json"
    target.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(Performance14Error, match="suite_identity_hash mismatch"):
        load_frozen_suite_artifact(path=target, repo_root=REPO_ROOT)


def test_tampered_query_membership_fails_closed(tmp_path: Path) -> None:
    src = REPO_ROOT / FROZEN_SUITE_REL
    raw = json.loads(src.read_text(encoding="utf-8"))
    raw["query_ids"] = list(raw["query_ids"])[:-1]
    # Keep hashes so the failure is membership / dump divergence, not hash format.
    target = tmp_path / "tampered_queries.json"
    target.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(Performance14Error):
        load_frozen_suite_artifact(path=target, repo_root=REPO_ROOT)


def test_gold_semantic_identity_accepts_locked_materialization() -> None:
    gold_dir = REPO_ROOT / GOLD_RELATIVE_PATH_14C
    assert_gold_semantic_identity_14c(gold_dir)


def test_gold_query_text_drift_fails_closed_despite_stale_meta_id(
    tmp_path: Path,
) -> None:
    """Mutating query text while retaining meta.dataset_id must fail closed."""
    src = REPO_ROOT / GOLD_RELATIVE_PATH_14C
    dst = tmp_path / "spoofed_gold"
    shutil.copytree(src, dst)
    cases_path = dst / "cases.jsonl"
    meta = json.loads((dst / "meta.json").read_text(encoding="utf-8"))
    assert meta["dataset_id"] == GOLD_DATASET_ID_14C

    lines = cases_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["query"] = first["query"] + " [SEMANTIC DRIFT]"
    lines[0] = json.dumps(first, ensure_ascii=False, separators=(",", ":"))
    cases_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # meta.dataset_id left unchanged — metadata-only trust would falsely accept.
    with pytest.raises(Performance14Error, match="canonical Gold semantic load failed"):
        assert_gold_semantic_identity_14c(dst)


def test_gold_judgment_drift_fails_closed_despite_stale_meta_id(
    tmp_path: Path,
) -> None:
    """Mutating a relevance judgment while retaining meta.dataset_id must fail."""
    src = REPO_ROOT / GOLD_RELATIVE_PATH_14C
    dst = tmp_path / "spoofed_gold_judgments"
    shutil.copytree(src, dst)
    cases_path = dst / "cases.jsonl"
    lines = cases_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first["judgments"], "expected at least one judgment to mutate"
    first["judgments"][0]["relevance"] = (
        0 if int(first["judgments"][0]["relevance"]) != 0 else 1
    )
    lines[0] = json.dumps(first, ensure_ascii=False, separators=(",", ":"))
    cases_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(Performance14Error, match="canonical Gold semantic load failed"):
        assert_gold_semantic_identity_14c(dst)


def test_frozen_artifact_model_contract() -> None:
    art = PerformanceFrozenSuite14CV1.model_validate(
        build_frozen_suite_artifact_14c().model_dump(mode="json")
    )
    assert art.contract == "performance-frozen-suite-14c-v1"
    assert art.design_authority_sha.startswith("89a395ae")
    assert art.substrate_pin_14b == SUBSTRATE_PIN_14B
