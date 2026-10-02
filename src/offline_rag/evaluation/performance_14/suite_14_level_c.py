"""Slice 14 Level-C frozen end-to-end warm suite (definition only).

Suite / scientific-config freezing ONLY. Authoritative Level-C execution is
NOT AUTHORIZED.

Level-C instrumentation authority:
    d25f5f85bd20aff18873dfd26fc8926da9a6dade

Generator pin (accepted human decision):
    RUNTIME MODEL-ID PIN — qwen3.6-35b-a3b

Endpoint ``http://192.168.2.140:8888/v1`` is freeze-artifact provenance /
security-preflight expectation only; excluded from ``gencfg_`` / ``perfcfg_``.

Population reuses the first five sorted query IDs from the accepted 14C Gold
population. No new Gold. Generation is included; retrieval recovery remains
disabled.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator

from offline_rag.chunking.pipeline import make_token_counter
from offline_rag.config.loader import load_settings
from offline_rag.config.models import (
    AppSettings,
    GenerationPromptSettings,
    GenerationSettings,
)
from offline_rag.context.config_hash import (
    build_context_config_hash,
    build_context_semantic_payload,
)
from offline_rag.core.ids import (
    BGE_RERANKER_MODEL_ID,
    BGE_RERANKER_PINNED_REVISION,
    QWEN3_EMBEDDING_MODEL_ID,
    QWEN3_EMBEDDING_PINNED_REVISION,
)
from offline_rag.evaluation.performance_14.contracts import (
    MEASUREMENT_PROTOCOL_VERSION_V1,
    STATISTICS_SEMANTICS_VERSION_V1,
    TIMING_BOUNDARY_VERSION_V1,
    Performance14Error,
    PerformanceBenchmarkSuiteV1,
    StrictModel,
)
from offline_rag.evaluation.performance_14.fixtures import (
    PerformanceCaseSpec,
    PerformanceSuitePlan,
    stable_case_id,
)
from offline_rag.evaluation.performance_14.identity import (
    compute_config_identity_hash,
    compute_suite_identity_hash,
)
from offline_rag.evaluation.performance_14.preflight import (
    assert_case_membership,
    assert_paired_comparison_invariant,
    assert_protocol_counts,
    assert_treatment_only_config_delta,
)
from offline_rag.evaluation.performance_14.suite_14c import (
    CHUNK_SET_ID_14C,
    CORPUS_ID_14C,
    DENSE_INDEX_ID_14C,
    EMBEDDING_CONFIG_HASH_14C,
    FUSION_CONFIG_HASH_14C,
    GOLD_DATASET_ID_14C,
    GOLD_RELATIVE_PATH_14C,
    GOLD_SCHEMA_VERSION_14C,
    INDEX_CONFIG_HASH_14C,
    LEXICAL_CONFIG_HASH_14C,
    LEXICAL_INDEX_ID_14C,
    QUERY_IDS_14C,
    RERANKER_CONFIG_HASH_14C,
    SUBSTRATE_PIN_14B,
    assert_gold_semantic_identity_14c,
)
from offline_rag.generation.config_hash import (
    build_generation_config_hash,
    build_generation_semantic_payload,
)
from offline_rag.sufficiency.contracts import ExactNonBlankStr

PERFORMANCE_FROZEN_SUITE_14_LEVEL_C_V1 = "performance-frozen-suite-14-level-c-v1"

INSTRUMENTATION_AUTHORITY_LEVEL_C = (
    "d25f5f85bd20aff18873dfd26fc8926da9a6dade"
)

SUITE_SLUG_LEVEL_C = "14_level_c_e2e_warm_v1"
POPULATION_IDENTITY_LEVEL_C = (
    "perfpop_14_level_c_ics_modules_gold_d3fc157c_first5_v1"
)

VARIANT_HYBRID_RERANK_CONTEXT_GENERATION = "hybrid_rerank_context_generation"
EXECUTION_ORDER_CONTRACT_LEVEL_C = "warmups_then_measured_round_robin_v1"
GENERATOR_PIN_STRENGTH_LEVEL_C = "runtime_model_id"

GENERATION_MODEL_LEVEL_C = "qwen3.6-35b-a3b"
GENERATION_PROVIDER_LEVEL_C = "openai_compatible"
GENERATION_TEMPERATURE_LEVEL_C = 0.0
GENERATION_MAX_OUTPUT_TOKENS_LEVEL_C = 1200
GENERATION_PROMPT_STRATEGY_LEVEL_C = "grounded"
GENERATION_PROMPT_CONTRACT_LEVEL_C = "prompt-grounded-v1"
EXPECTED_GENERATION_ENDPOINT_LEVEL_C = "http://192.168.2.140:8888/v1"
EXPECTED_TIMEOUT_SECONDS_LEVEL_C = 300

# Deterministic: first five of sorted QUERY_IDS_14C (already ascending).
QUERY_IDS_LEVEL_C: tuple[str, ...] = tuple(sorted(QUERY_IDS_14C)[:5])

WARMUP_COUNT_LEVEL_C = 1
MEASURED_REPETITIONS_LEVEL_C = 5
COLD_WARM_LEVEL_C = "warm"

FROZEN_SUITE_REL_LEVEL_C = Path(
    "eval/fixtures/performance_14/suites/14_level_c_e2e_warm_v1.json"
)

_BASE_YAML_REL = Path("config/base.yaml")


def _context_settings_for_freeze(*, repo_root: Path | None = None) -> AppSettings:
    """Load context/tokenizer settings from base.yaml without ambient env overrides."""
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return load_settings(
        yaml_paths=[(root / _BASE_YAML_REL).resolve()],
        environ={},
    )


def pinned_generation_settings_level_c() -> GenerationSettings:
    """Scientific generation pin for Level-C (no endpoint/api_key/allowlists)."""
    return GenerationSettings(
        enabled=True,
        provider=GENERATION_PROVIDER_LEVEL_C,
        model=GENERATION_MODEL_LEVEL_C,
        temperature=GENERATION_TEMPERATURE_LEVEL_C,
        max_output_tokens=GENERATION_MAX_OUTPUT_TOKENS_LEVEL_C,
        # base_url / allowlists / timeout are not scientific gencfg_ inputs;
        # keep Pydantic-valid placeholders that are never hashed.
        base_url="http://127.0.0.1:11434/v1",
        approved_endpoints=["http://127.0.0.1:11434/v1"],
        approved_models=[GENERATION_MODEL_LEVEL_C],
        timeout_seconds=120,
        api_key=None,
        prompt=GenerationPromptSettings(
            strategy=GENERATION_PROMPT_STRATEGY_LEVEL_C,
            contract_version=GENERATION_PROMPT_CONTRACT_LEVEL_C,
        ),
    )


def generation_semantic_payload_level_c() -> dict[str, Any]:
    return build_generation_semantic_payload(pinned_generation_settings_level_c())


def generation_config_hash_level_c() -> str:
    return build_generation_config_hash(pinned_generation_settings_level_c())


def context_semantic_payload_level_c(
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    settings = _context_settings_for_freeze(repo_root=repo_root)
    counter = make_token_counter(settings)
    return build_context_semantic_payload(settings, token_counter=counter)


def context_config_hash_level_c(*, repo_root: Path | None = None) -> str:
    settings = _context_settings_for_freeze(repo_root=repo_root)
    counter = make_token_counter(settings)
    return build_context_config_hash(settings, token_counter=counter)


def variant_config_level_c(*, repo_root: Path | None = None) -> dict[str, object]:
    ctx_payload = context_semantic_payload_level_c(repo_root=repo_root)
    gen_payload = generation_semantic_payload_level_c()
    return {
        "retrieval_mode": "hybrid",
        "stage_or_path": "end_to_end",
        "corpus_id": CORPUS_ID_14C,
        "chunk_set_id": CHUNK_SET_ID_14C,
        "gold_dataset_id": GOLD_DATASET_ID_14C,
        "gold_schema_version": GOLD_SCHEMA_VERSION_14C,
        "dense_index_id": DENSE_INDEX_ID_14C,
        "lexical_index_id": LEXICAL_INDEX_ID_14C,
        "embedding_model_id": QWEN3_EMBEDDING_MODEL_ID,
        "embedding_model_revision": QWEN3_EMBEDDING_PINNED_REVISION,
        "embedding_config_hash": EMBEDDING_CONFIG_HASH_14C,
        "index_config_hash": INDEX_CONFIG_HASH_14C,
        "lexical_config_hash": LEXICAL_CONFIG_HASH_14C,
        "fusion_config_hash": FUSION_CONFIG_HASH_14C,
        "fusion_method": "rrf",
        "fusion_contract_version": "rrf-v1",
        "rrf_k": 60,
        "dense_top_k": 30,
        "lexical_top_k": 30,
        "fusion_output_top_k": 10,
        "reranker_enabled": True,
        "reranker_configuration": {
            "model_id": BGE_RERANKER_MODEL_ID,
            "revision": BGE_RERANKER_PINNED_REVISION,
            "input_k": 30,
            "output_k": 10,
            "input_construction": "plain-pair-v1",
            "sequence_contract": "seq-trunc-1024-passage-right-v1",
            "max_length": 1024,
            "score_transform": "raw-logit-v1",
            "tie_break": "chunk-id-asc-v1",
            "batch_size": 16,
        },
        "reranker_config_hash": RERANKER_CONFIG_HASH_14C,
        "context_enabled": True,
        "context_strategy": "parent",
        "context_anchor_k": 5,
        "context_max_context_tokens": 6000,
        "context_neighbor_window": 0,
        "context_semantic_payload": ctx_payload,
        "context_config_hash": context_config_hash_level_c(repo_root=repo_root),
        "generation_enabled": True,
        "generation_excluded": False,
        "generation_streaming": False,
        "generation_semantic_payload": gen_payload,
        "generation_config_hash": generation_config_hash_level_c(),
        "retrieval_recovery_enabled": False,
    }


def variant_configs_level_c(
    *,
    repo_root: Path | None = None,
) -> dict[str, dict[str, object]]:
    return {
        VARIANT_HYBRID_RERANK_CONTEXT_GENERATION: variant_config_level_c(
            repo_root=repo_root
        )
    }


def case_specs_level_c() -> tuple[PerformanceCaseSpec, ...]:
    return tuple(
        PerformanceCaseSpec(
            case_kind="end_to_end_query",
            benchmark_level="C",
            stage_or_path="end_to_end",
            subject_identity=query_id,
            variant=VARIANT_HYBRID_RERANK_CONTEXT_GENERATION,
            cold_warm=COLD_WARM_LEVEL_C,  # type: ignore[arg-type]
            local_case_id=query_id,
        )
        for query_id in QUERY_IDS_LEVEL_C
    )


def case_ids_level_c() -> list[str]:
    return [stable_case_id(spec) for spec in case_specs_level_c()]


def build_suite_body_level_c() -> PerformanceBenchmarkSuiteV1:
    suite = PerformanceBenchmarkSuiteV1(
        benchmark_level="C",
        population_identity=POPULATION_IDENTITY_LEVEL_C,
        variants=[VARIANT_HYBRID_RERANK_CONTEXT_GENERATION],
        case_ids=case_ids_level_c(),
        measurement_protocol_version=MEASUREMENT_PROTOCOL_VERSION_V1,
        timing_boundary_version=TIMING_BOUNDARY_VERSION_V1,
        statistics_semantics_version=STATISTICS_SEMANTICS_VERSION_V1,
    )
    return suite.model_copy(
        update={"suite_identity_hash": compute_suite_identity_hash(suite)}
    )


def build_suite_plan_level_c(
    *,
    repo_root: Path | None = None,
) -> PerformanceSuitePlan:
    suite = build_suite_body_level_c()
    return PerformanceSuitePlan(
        suite=suite,
        cases=case_specs_level_c(),
        warmup_count=WARMUP_COUNT_LEVEL_C,
        measured_repetitions=MEASURED_REPETITIONS_LEVEL_C,
        baseline_variant=None,
        treatment_variant=None,
        treatment_delta=(),
        variant_configs=variant_configs_level_c(repo_root=repo_root),
        population_kind="level_c_e2e_frozen",
        diagnostic_only=True,
        authoritative=False,
    )


def scientific_config_payload_level_c(
    plan: PerformanceSuitePlan | None = None,
    *,
    repo_root: Path | None = None,
) -> dict[str, object]:
    """Scientific effective-config payload for ``perfcfg_`` (no authority flags).

    Endpoint, api_key, allowlists, timestamps, machine identity, run IDs, and
    authorization / evidence-class flags are intentionally excluded.
    """
    plan = (
        plan
        if plan is not None
        else build_suite_plan_level_c(repo_root=repo_root)
    )
    return {
        "benchmark_level": plan.suite.benchmark_level,
        "population_identity": plan.suite.population_identity,
        "query_ids": list(QUERY_IDS_LEVEL_C),
        "variants": sorted(plan.suite.variants),
        "warmup_count": plan.warmup_count,
        "measured_repetitions": plan.measured_repetitions,
        "cold_warm": COLD_WARM_LEVEL_C,
        "execution_order_contract": EXECUTION_ORDER_CONTRACT_LEVEL_C,
        "variant_configs": plan.variant_configs,
        "substrate_pin_14b": SUBSTRATE_PIN_14B,
        "level_c_instrumentation_authority": INSTRUMENTATION_AUTHORITY_LEVEL_C,
        "suite_kind": "level_c_e2e_warm",
        "generation_enabled": True,
        "generation_streaming": False,
        "retrieval_recovery_enabled": False,
        "generator_pin_strength": GENERATOR_PIN_STRENGTH_LEVEL_C,
    }


def effective_config_id_level_c(*, repo_root: Path | None = None) -> str:
    """Return ``perfcfg_`` over the frozen scientific Level-C configuration."""
    return compute_config_identity_hash(
        scientific_config_payload_level_c(repo_root=repo_root)
    )


class PerformanceFrozenSuite14LevelCV1(StrictModel):
    """Machine-readable frozen Level-C suite artifact (definition only)."""

    contract: ExactNonBlankStr = PERFORMANCE_FROZEN_SUITE_14_LEVEL_C_V1
    suite_slug: ExactNonBlankStr = SUITE_SLUG_LEVEL_C
    suite_kind: ExactNonBlankStr = "level_c_e2e_warm"
    benchmark_level: ExactNonBlankStr = "C"
    level_c_instrumentation_authority: ExactNonBlankStr = (
        INSTRUMENTATION_AUTHORITY_LEVEL_C
    )
    substrate_pin_14b: ExactNonBlankStr = SUBSTRATE_PIN_14B
    population_identity: ExactNonBlankStr = POPULATION_IDENTITY_LEVEL_C
    gold_dataset_id: ExactNonBlankStr = GOLD_DATASET_ID_14C
    gold_schema_version: ExactNonBlankStr = GOLD_SCHEMA_VERSION_14C
    gold_relative_path: ExactNonBlankStr = GOLD_RELATIVE_PATH_14C
    query_ids: list[ExactNonBlankStr] = Field(min_length=5, max_length=5)
    case_ids: list[ExactNonBlankStr] = Field(min_length=5, max_length=5)
    corpus_id: ExactNonBlankStr = CORPUS_ID_14C
    chunk_set_id: ExactNonBlankStr = CHUNK_SET_ID_14C
    dense_index_id: ExactNonBlankStr = DENSE_INDEX_ID_14C
    lexical_index_id: ExactNonBlankStr = LEXICAL_INDEX_ID_14C
    embedding_model_id: ExactNonBlankStr = QWEN3_EMBEDDING_MODEL_ID
    embedding_model_revision: ExactNonBlankStr = QWEN3_EMBEDDING_PINNED_REVISION
    embedding_config_hash: ExactNonBlankStr = EMBEDDING_CONFIG_HASH_14C
    index_config_hash: ExactNonBlankStr = INDEX_CONFIG_HASH_14C
    lexical_config_hash: ExactNonBlankStr = LEXICAL_CONFIG_HASH_14C
    fusion_config_hash: ExactNonBlankStr = FUSION_CONFIG_HASH_14C
    reranker_model_id: ExactNonBlankStr = BGE_RERANKER_MODEL_ID
    reranker_model_revision: ExactNonBlankStr = BGE_RERANKER_PINNED_REVISION
    reranker_config_hash: ExactNonBlankStr = RERANKER_CONFIG_HASH_14C
    context_config_hash: ExactNonBlankStr
    context_semantic_payload: dict[str, Any]
    generation_enabled: bool = True
    generation_excluded: bool = False
    generation_streaming: bool = False
    generation_model: ExactNonBlankStr = GENERATION_MODEL_LEVEL_C
    generation_provider: ExactNonBlankStr = GENERATION_PROVIDER_LEVEL_C
    generation_temperature: float = GENERATION_TEMPERATURE_LEVEL_C
    generation_max_output_tokens: int = Field(
        default=GENERATION_MAX_OUTPUT_TOKENS_LEVEL_C, ge=1
    )
    generation_prompt_strategy: ExactNonBlankStr = GENERATION_PROMPT_STRATEGY_LEVEL_C
    generation_prompt_contract: ExactNonBlankStr = GENERATION_PROMPT_CONTRACT_LEVEL_C
    generation_semantic_payload: dict[str, Any]
    generation_config_hash: ExactNonBlankStr
    generator_pin_strength: ExactNonBlankStr = GENERATOR_PIN_STRENGTH_LEVEL_C
    expected_generation_endpoint: ExactNonBlankStr = (
        EXPECTED_GENERATION_ENDPOINT_LEVEL_C
    )
    expected_approved_models: list[ExactNonBlankStr] = Field(min_length=1)
    expected_timeout_seconds: int = Field(
        default=EXPECTED_TIMEOUT_SECONDS_LEVEL_C, ge=1
    )
    retrieval_recovery_enabled: bool = False
    variants: list[ExactNonBlankStr] = Field(min_length=1, max_length=1)
    variant_configs: dict[str, dict[str, Any]]
    warmup_count: int = Field(ge=0)
    measured_repetitions: int = Field(ge=5)
    cold_warm: ExactNonBlankStr = COLD_WARM_LEVEL_C
    execution_order_contract: ExactNonBlankStr = EXECUTION_ORDER_CONTRACT_LEVEL_C
    execution_authorized: bool = False
    authoritative_results_authorized: bool = False
    suite_identity_hash: ExactNonBlankStr
    effective_config_id: ExactNonBlankStr
    measurement_protocol_version: ExactNonBlankStr = MEASUREMENT_PROTOCOL_VERSION_V1
    timing_boundary_version: ExactNonBlankStr = TIMING_BOUNDARY_VERSION_V1
    statistics_semantics_version: ExactNonBlankStr = STATISTICS_SEMANTICS_VERSION_V1

    @field_validator("query_ids", "case_ids", "variants", "expected_approved_models")
    @classmethod
    def _no_dupes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate membership ids are forbidden")
        return value

    @model_validator(mode="after")
    def _freeze_gates(self) -> PerformanceFrozenSuite14LevelCV1:
        if self.execution_authorized:
            raise ValueError(
                "Level-C suite freeze must set execution_authorized=False"
            )
        if self.authoritative_results_authorized:
            raise ValueError(
                "Level-C suite freeze must set "
                "authoritative_results_authorized=False"
            )
        if self.generation_excluded:
            raise ValueError("Level-C suite freeze includes generation")
        if not self.generation_enabled:
            raise ValueError("Level-C suite freeze requires generation_enabled=True")
        if self.generation_streaming:
            raise ValueError("Level-C suite freeze requires non-streaming generation")
        if self.retrieval_recovery_enabled:
            raise ValueError("Level-C suite freeze requires recovery disabled")
        if self.generation_model != GENERATION_MODEL_LEVEL_C:
            raise ValueError(
                f"Level-C generation_model must be {GENERATION_MODEL_LEVEL_C!r}"
            )
        if list(self.expected_approved_models) != [GENERATION_MODEL_LEVEL_C]:
            raise ValueError(
                "expected_approved_models must be exactly "
                f"[{GENERATION_MODEL_LEVEL_C!r}]"
            )
        if not self.generation_config_hash.startswith("gencfg_"):
            raise ValueError("generation_config_hash must be gencfg_…")
        if not self.context_config_hash.startswith("ctxcfg_"):
            raise ValueError("context_config_hash must be ctxcfg_…")
        if not self.suite_identity_hash.startswith("perfsuite_"):
            raise ValueError("suite_identity_hash must be perfsuite_…")
        if not self.effective_config_id.startswith("perfcfg_"):
            raise ValueError("effective_config_id must be perfcfg_…")
        if self.cold_warm != "warm":
            raise ValueError("Level-C frozen suite is warm-classified only")
        if self.variants != [VARIANT_HYBRID_RERANK_CONTEXT_GENERATION]:
            raise ValueError(
                "Level-C variants must be exactly "
                f"[{VARIANT_HYBRID_RERANK_CONTEXT_GENERATION!r}]"
            )
        if self.generator_pin_strength != GENERATOR_PIN_STRENGTH_LEVEL_C:
            raise ValueError(
                "generator_pin_strength must be runtime_model_id"
            )
        return self


def build_frozen_suite_artifact_level_c(
    *,
    repo_root: Path | None = None,
) -> PerformanceFrozenSuite14LevelCV1:
    suite = build_suite_body_level_c()
    assert suite.suite_identity_hash is not None
    ctx_payload = context_semantic_payload_level_c(repo_root=repo_root)
    gen_payload = generation_semantic_payload_level_c()
    return PerformanceFrozenSuite14LevelCV1(
        query_ids=list(QUERY_IDS_LEVEL_C),
        case_ids=case_ids_level_c(),
        variants=[VARIANT_HYBRID_RERANK_CONTEXT_GENERATION],
        variant_configs=variant_configs_level_c(repo_root=repo_root),
        warmup_count=WARMUP_COUNT_LEVEL_C,
        measured_repetitions=MEASURED_REPETITIONS_LEVEL_C,
        context_config_hash=context_config_hash_level_c(repo_root=repo_root),
        context_semantic_payload=ctx_payload,
        generation_semantic_payload=gen_payload,
        generation_config_hash=generation_config_hash_level_c(),
        expected_approved_models=[GENERATION_MODEL_LEVEL_C],
        suite_identity_hash=suite.suite_identity_hash,
        effective_config_id=effective_config_id_level_c(repo_root=repo_root),
    )


def _assert_level_c_population_rule() -> None:
    expected = tuple(sorted(QUERY_IDS_14C)[:5])
    if QUERY_IDS_LEVEL_C != expected:
        raise Performance14Error(
            "QUERY_IDS_LEVEL_C must equal first five sorted QUERY_IDS_14C"
        )
    if list(QUERY_IDS_LEVEL_C) != sorted(QUERY_IDS_LEVEL_C):
        raise Performance14Error("QUERY_IDS_LEVEL_C must be sorted ascending")
    if len(QUERY_IDS_LEVEL_C) != 5:
        raise Performance14Error("Level-C population must contain exactly 5 queries")


def _assert_gold_membership_on_disk(repo_root: Path) -> None:
    gold_dir = (repo_root / GOLD_RELATIVE_PATH_14C).resolve()
    assert_gold_semantic_identity_14c(gold_dir)
    # Level-C membership is a deterministic subset; full Gold must still match 14C.
    _assert_level_c_population_rule()


def validate_frozen_suite_level_c(
    artifact: PerformanceFrozenSuite14LevelCV1 | None = None,
    *,
    repo_root: Path | None = None,
) -> PerformanceFrozenSuite14LevelCV1:
    """Fail-closed validation of the frozen Level-C suite definition."""
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    locked = build_frozen_suite_artifact_level_c(repo_root=root)
    art = artifact if artifact is not None else locked
    plan = build_suite_plan_level_c(repo_root=root)
    assert_protocol_counts(
        level="C",
        warmup_count=plan.warmup_count,
        measured_repetitions=plan.measured_repetitions,
    )
    assert_case_membership(plan)
    assert_paired_comparison_invariant(plan)
    assert_treatment_only_config_delta(plan)
    _assert_level_c_population_rule()

    recomputed_suite = compute_suite_identity_hash(plan.suite)
    if art.suite_identity_hash != recomputed_suite:
        raise Performance14Error(
            "frozen suite_identity_hash mismatch: "
            f"{art.suite_identity_hash} != {recomputed_suite}"
        )
    if art.suite_identity_hash != plan.suite.suite_identity_hash:
        raise Performance14Error("suite plan hash diverges from frozen artifact")
    if art.suite_identity_hash != locked.suite_identity_hash:
        raise Performance14Error("artifact suite_identity_hash diverges from lock")
    if list(art.query_ids) != list(QUERY_IDS_LEVEL_C):
        raise Performance14Error("frozen query_ids diverge from locked membership")
    if len(art.query_ids) != 5:
        raise Performance14Error("Level-C population must contain exactly 5 queries")
    if list(art.case_ids) != case_ids_level_c():
        raise Performance14Error("frozen case_ids diverge from locked membership")
    if len(art.case_ids) != 5:
        raise Performance14Error("Level-C must freeze 5 queries × 1 variant = 5 cases")
    if art.effective_config_id != effective_config_id_level_c(repo_root=root):
        raise Performance14Error("effective_config_id diverges from locked payload")
    if art.effective_config_id != locked.effective_config_id:
        raise Performance14Error("artifact effective_config_id diverges from lock")
    if art.generation_config_hash != generation_config_hash_level_c():
        raise Performance14Error("generation_config_hash diverges from lock")
    if art.context_config_hash != context_config_hash_level_c(repo_root=root):
        raise Performance14Error("context_config_hash diverges from lock")
    # Provenance-only fields must not silently enter scientific identity.
    scientific = scientific_config_payload_level_c(plan, repo_root=root)
    for forbidden in (
        "expected_generation_endpoint",
        "expected_approved_models",
        "expected_timeout_seconds",
        "base_url",
        "api_key",
        "approved_endpoints",
        "approved_models",
        "execution_authorized",
        "authoritative_results_authorized",
        "diagnostic_only",
        "authoritative",
    ):
        if forbidden in scientific:
            raise Performance14Error(
                f"scientific Level-C config must not include {forbidden!r}"
            )
    if art.model_dump(mode="json") != locked.model_dump(mode="json"):
        raise Performance14Error(
            "frozen suite artifact diverges from locked builder output"
        )
    # Order independence of variant_configs must not flip perfcfg_.
    variant = VARIANT_HYBRID_RERANK_CONTEXT_GENERATION
    reordered = {
        variant: dict(reversed(list(plan.variant_configs[variant].items()))),
    }
    reordered_plan = replace(plan, variant_configs=reordered)
    if (
        compute_config_identity_hash(
            scientific_config_payload_level_c(reordered_plan, repo_root=root)
        )
        != art.effective_config_id
    ):
        raise Performance14Error(
            "effective_config_id is not stable under variant_configs key reordering"
        )
    _assert_gold_membership_on_disk(root)
    return art


def default_frozen_suite_path_level_c(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return (root / FROZEN_SUITE_REL_LEVEL_C).resolve()


def write_frozen_suite_artifact_level_c(
    path: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Write the deterministic frozen Level-C suite JSON (create-exclusive)."""
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    art = validate_frozen_suite_level_c(repo_root=root)
    target = path if path is not None else default_frozen_suite_path_level_c(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(art.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if existing != payload:
            raise Performance14Error(
                f"frozen suite artifact already exists with different content: {target}"
            )
        return target
    target.write_text(payload, encoding="utf-8")
    return target


def load_frozen_suite_artifact_level_c(
    path: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> PerformanceFrozenSuite14LevelCV1:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    target = path if path is not None else default_frozen_suite_path_level_c(root)
    raw = json.loads(target.read_text(encoding="utf-8"))
    art = PerformanceFrozenSuite14LevelCV1.model_validate(raw)
    return validate_frozen_suite_level_c(art, repo_root=root)
