"""Slice 14 Level-C unit tests — frozen suite identity stability and gates."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from offline_rag.evaluation.performance_14.identity import (
    compute_config_identity_hash,
    compute_suite_identity_hash,
)
from offline_rag.evaluation.performance_14.suite_14_level_c import (
    COLD_WARM_LEVEL_C,
    EXECUTION_ORDER_CONTRACT_LEVEL_C,
    EXPECTED_GENERATION_ENDPOINT_LEVEL_C,
    FROZEN_SUITE_REL_LEVEL_C,
    GENERATION_MODEL_LEVEL_C,
    INSTRUMENTATION_AUTHORITY_LEVEL_C,
    MEASURED_REPETITIONS_LEVEL_C,
    POPULATION_IDENTITY_LEVEL_C,
    QUERY_IDS_LEVEL_C,
    VARIANT_HYBRID_RERANK_CONTEXT_GENERATION,
    WARMUP_COUNT_LEVEL_C,
    Performance14Error,
    PerformanceFrozenSuite14LevelCV1,
    build_frozen_suite_artifact_level_c,
    build_suite_plan_level_c,
    effective_config_id_level_c,
    generation_config_hash_level_c,
    load_frozen_suite_artifact_level_c,
    scientific_config_payload_level_c,
    validate_frozen_suite_level_c,
    write_frozen_suite_artifact_level_c,
)
from offline_rag.evaluation.performance_14.suite_14c import QUERY_IDS_14C

REPO_ROOT = Path(__file__).resolve().parents[2]

LOCKED_PERFSUITE = (
    "perfsuite_d9241ed2cad9473e399ae30d875729c8d2b1faf65580457fe2a872d75ca924b0"
)
LOCKED_PERFCFG = (
    "perfcfg_a26a0fb336905dfa681c6cfe96721cf1fd446da64004336156f0336420025a25"
)
LOCKED_GENCFG = (
    "gencfg_d6b98a84f20887142dbb56a20e1b7533f6006304442efc017bb80a8fa2feb4d3"
)
LOCKED_CTXCFG = (
    "ctxcfg_b1742f41ecc03defbcf7c4e270fe22b4aa72db4a1af2c02a70d5560cd2ac8876"
)


def test_population_and_protocol_pins() -> None:
    assert INSTRUMENTATION_AUTHORITY_LEVEL_C == (
        "d25f5f85bd20aff18873dfd26fc8926da9a6dade"
    )
    assert POPULATION_IDENTITY_LEVEL_C.startswith("perfpop_14_level_c_")
    assert QUERY_IDS_LEVEL_C == tuple(sorted(QUERY_IDS_14C)[:5])
    assert len(QUERY_IDS_LEVEL_C) == 5
    assert WARMUP_COUNT_LEVEL_C == 1
    assert MEASURED_REPETITIONS_LEVEL_C == 5
    assert COLD_WARM_LEVEL_C == "warm"
    assert EXECUTION_ORDER_CONTRACT_LEVEL_C == (
        "warmups_then_measured_round_robin_v1"
    )
    assert GENERATION_MODEL_LEVEL_C == "qwen3.6-35b-a3b"
    assert EXPECTED_GENERATION_ENDPOINT_LEVEL_C == (
        "http://192.168.2.140:8888/v1"
    )


def test_frozen_identities_are_stable() -> None:
    art = validate_frozen_suite_level_c(repo_root=REPO_ROOT)
    assert art.suite_identity_hash == LOCKED_PERFSUITE
    assert art.effective_config_id == LOCKED_PERFCFG
    assert art.generation_config_hash == LOCKED_GENCFG
    assert art.context_config_hash == LOCKED_CTXCFG
    assert art.execution_authorized is False
    assert art.authoritative_results_authorized is False
    assert art.generation_excluded is False
    assert art.generation_enabled is True
    assert art.generation_streaming is False
    assert art.retrieval_recovery_enabled is False
    assert art.generation_model == GENERATION_MODEL_LEVEL_C
    assert art.variants == [VARIANT_HYBRID_RERANK_CONTEXT_GENERATION]
    assert len(art.case_ids) == 5
    assert len(art.query_ids) == 5


def test_on_disk_artifact_roundtrip_preserves_identity() -> None:
    path = REPO_ROOT / FROZEN_SUITE_REL_LEVEL_C
    assert path.is_file()
    loaded = load_frozen_suite_artifact_level_c(repo_root=REPO_ROOT)
    rebuilt = build_frozen_suite_artifact_level_c(repo_root=REPO_ROOT)
    assert loaded.suite_identity_hash == rebuilt.suite_identity_hash == LOCKED_PERFSUITE
    assert loaded.effective_config_id == rebuilt.effective_config_id == LOCKED_PERFCFG
    assert loaded.model_dump(mode="json") == rebuilt.model_dump(mode="json")


def test_write_is_create_exclusive_and_deterministic(tmp_path: Path) -> None:
    target = tmp_path / "suite.json"
    first = write_frozen_suite_artifact_level_c(path=target, repo_root=REPO_ROOT)
    second = write_frozen_suite_artifact_level_c(path=target, repo_root=REPO_ROOT)
    assert first == second == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["suite_identity_hash"] == LOCKED_PERFSUITE
    assert payload["effective_config_id"] == LOCKED_PERFCFG
    target.write_text('{"contract":"tampered"}\n', encoding="utf-8")
    with pytest.raises(Performance14Error, match="different content"):
        write_frozen_suite_artifact_level_c(path=target, repo_root=REPO_ROOT)


def test_suite_hash_stable_under_case_id_and_variant_reordering() -> None:
    plan = build_suite_plan_level_c(repo_root=REPO_ROOT)
    assert plan.suite.suite_identity_hash == LOCKED_PERFSUITE
    flipped = plan.suite.model_copy(
        update={
            "case_ids": list(reversed(plan.suite.case_ids)),
            "variants": list(reversed(plan.suite.variants)),
            "suite_identity_hash": None,
        }
    )
    assert compute_suite_identity_hash(flipped) == LOCKED_PERFSUITE


def test_perfcfg_stable_under_variant_config_key_reordering() -> None:
    plan = build_suite_plan_level_c(repo_root=REPO_ROOT)
    variant = VARIANT_HYBRID_RERANK_CONTEXT_GENERATION
    reordered = {
        variant: dict(reversed(list(plan.variant_configs[variant].items()))),
    }
    reordered_plan = replace(plan, variant_configs=reordered)
    assert (
        compute_config_identity_hash(
            scientific_config_payload_level_c(reordered_plan, repo_root=REPO_ROOT)
        )
        == effective_config_id_level_c(repo_root=REPO_ROOT)
        == LOCKED_PERFCFG
    )


def test_perfcfg_excludes_endpoint_allowlists_and_authorization_flags() -> None:
    payload = scientific_config_payload_level_c(repo_root=REPO_ROOT)
    for forbidden in (
        "expected_generation_endpoint",
        "expected_approved_models",
        "expected_timeout_seconds",
        "base_url",
        "api_key",
        "approved_endpoints",
        "approved_models",
        "diagnostic_only",
        "authoritative",
        "execution_authorized",
        "authoritative_results_authorized",
    ):
        assert forbidden not in payload
    # Endpoint must not be embeddable into scientific identity via pollution alone
    # without flipping the locked id (pollution changes hash).
    polluted = dict(payload)
    polluted["expected_generation_endpoint"] = EXPECTED_GENERATION_ENDPOINT_LEVEL_C
    assert compute_config_identity_hash(polluted) != LOCKED_PERFCFG


def test_membership_change_flips_perfsuite() -> None:
    plan = build_suite_plan_level_c(repo_root=REPO_ROOT)
    mutated = plan.suite.model_copy(
        update={
            "case_ids": plan.suite.case_ids[:-1],
            "suite_identity_hash": None,
        }
    )
    assert compute_suite_identity_hash(mutated) != LOCKED_PERFSUITE


def test_generation_model_change_flips_gencfg_and_perfcfg() -> None:
    assert generation_config_hash_level_c() == LOCKED_GENCFG
    plan = build_suite_plan_level_c(repo_root=REPO_ROOT)
    variant = VARIANT_HYBRID_RERANK_CONTEXT_GENERATION
    configs = {variant: dict(plan.variant_configs[variant])}
    gen_payload = dict(configs[variant]["generation_semantic_payload"])  # type: ignore[arg-type]
    gen_payload["model"] = "NOT_THE_PINNED_MODEL"
    configs[variant]["generation_semantic_payload"] = gen_payload
    configs[variant]["generation_config_hash"] = "gencfg_" + ("0" * 64)
    mutated_plan = replace(plan, variant_configs=configs)
    assert (
        compute_config_identity_hash(
            scientific_config_payload_level_c(mutated_plan, repo_root=REPO_ROOT)
        )
        != LOCKED_PERFCFG
    )


def test_execution_authorization_flags_rejected() -> None:
    art = build_frozen_suite_artifact_level_c(repo_root=REPO_ROOT)
    payload = art.model_dump(mode="json")
    with pytest.raises(ValidationError, match="execution_authorized"):
        PerformanceFrozenSuite14LevelCV1.model_validate(
            {**payload, "execution_authorized": True}
        )
    with pytest.raises(ValidationError, match="authoritative_results_authorized"):
        PerformanceFrozenSuite14LevelCV1.model_validate(
            {**payload, "authoritative_results_authorized": True}
        )


def test_wrong_generation_model_rejected() -> None:
    art = build_frozen_suite_artifact_level_c(repo_root=REPO_ROOT)
    payload = art.model_dump(mode="json")
    with pytest.raises(ValidationError, match="generation_model"):
        PerformanceFrozenSuite14LevelCV1.model_validate(
            {**payload, "generation_model": "other-model"}
        )


def test_tampered_on_disk_hash_fails_closed(tmp_path: Path) -> None:
    src = REPO_ROOT / FROZEN_SUITE_REL_LEVEL_C
    raw = json.loads(src.read_text(encoding="utf-8"))
    raw["suite_identity_hash"] = "perfsuite_" + ("0" * 64)
    target = tmp_path / "tampered.json"
    target.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(Performance14Error, match="suite_identity_hash mismatch"):
        load_frozen_suite_artifact_level_c(path=target, repo_root=REPO_ROOT)


def test_tampered_query_membership_fails_closed(tmp_path: Path) -> None:
    src = REPO_ROOT / FROZEN_SUITE_REL_LEVEL_C
    raw = json.loads(src.read_text(encoding="utf-8"))
    # Keep length=5 for model constraints; swap one ID out of locked membership.
    raw["query_ids"] = list(raw["query_ids"])
    raw["query_ids"][0] = "draft_deadbeefdeadbeefdeadbeefdeadbeef"
    target = tmp_path / "tampered_queries.json"
    target.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(Performance14Error):
        load_frozen_suite_artifact_level_c(path=target, repo_root=REPO_ROOT)


def test_frozen_artifact_model_contract() -> None:
    art = PerformanceFrozenSuite14LevelCV1.model_validate(
        build_frozen_suite_artifact_level_c(repo_root=REPO_ROOT).model_dump(
            mode="json"
        )
    )
    assert art.contract == "performance-frozen-suite-14-level-c-v1"
    assert art.level_c_instrumentation_authority == INSTRUMENTATION_AUTHORITY_LEVEL_C
    assert art.expected_generation_endpoint == EXPECTED_GENERATION_ENDPOINT_LEVEL_C
    assert art.generator_pin_strength == "runtime_model_id"
    assert art.expected_timeout_seconds == 300
