"""Slice 14C frozen hybrid vs hybrid+reranker quality-vs-cost suite.

Suite freezing ONLY. Authoritative benchmark execution is NOT AUTHORIZED.

Design authority: 89a395ae4df7aff23c2da2c8c44fd6fe405459a6
14B substrate:     97d38031b99029c2e9b3fd028eadc3a60efef6c0

Population reuses the established ics_modules GoldDataset and the same corpus /
index / fusion identities exercised by the 9H-P hybrid vs hybrid-rerank arms.
Generation is excluded from this comparison.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator

from offline_rag.core.ids import (
    BGE_RERANKER_MODEL_ID,
    BGE_RERANKER_PINNED_REVISION,
    QWEN3_EMBEDDING_MODEL_ID,
    QWEN3_EMBEDDING_PINNED_REVISION,
)
from offline_rag.evaluation.gold import GoldDatasetError, load_gold_dataset
from offline_rag.evaluation.performance_14.contracts import (
    DESIGN_AUTHORITY_SHA_14,
    MEASUREMENT_PROTOCOL_VERSION_V1,
    STATISTICS_SEMANTICS_VERSION_V1,
    TIMING_BOUNDARY_VERSION_V1,
    Performance14Error,
    PerformanceBenchmarkSuiteV1,
    StrictModel,
)
from offline_rag.evaluation.performance_14.fixtures import (
    VARIANT_HYBRID,
    VARIANT_HYBRID_RERANK,
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
from offline_rag.sufficiency.contracts import ExactNonBlankStr

PERFORMANCE_FROZEN_SUITE_14C_V1 = "performance-frozen-suite-14c-v1"
SUBSTRATE_PIN_14B = "97d38031b99029c2e9b3fd028eadc3a60efef6c0"

SUITE_SLUG_14C = "14c_hybrid_vs_hybrid_rerank_v1"
POPULATION_IDENTITY_14C = "perfpop_14c_hybrid_vs_rerank_ics_modules_gold_d3fc157c_v1"

GOLD_DATASET_ID_14C = (
    "gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172"
)
GOLD_SCHEMA_VERSION_14C = "offline-rag-gold-v1"
GOLD_RELATIVE_PATH_14C = (
    "data/corpora/ics_modules/gold_authoring/gold/"
    "authorrun_b28d88f64054491a837cb4a144cbe056"
)

CORPUS_ID_14C = (
    "corpus_040e49a1d261dba4e853939b36348dc40109551d6fdb49b38c7a9d896409eadb"
)
CHUNK_SET_ID_14C = (
    "chunkset_6d4925ea8d66e7dc599a884e96bc5f6b094e4288d565372d15e6002086c41da2"
)
DENSE_INDEX_ID_14C = (
    "denseindex_80f7da5c50c6de0a00502e169c75198af3f7f2f48d56dcae8ca961d3e42710e9"
)
LEXICAL_INDEX_ID_14C = (
    "lexical_9c43385ecf20cacbbe31e1243d37afca3ce88520e30be39f1aa2017a2bb1c337"
)

EMBEDDING_CONFIG_HASH_14C = (
    "embcfg_e7861b5986785eba0fb6725a3d1e40f2d461f33e2dcd66d2c75ad3875f9a5d3f"
)
INDEX_CONFIG_HASH_14C = (
    "idxcfg_45b7b17026e085b4f721de7031819b3b72d99db3966e1b77fc9dcc8203d41862"
)
LEXICAL_CONFIG_HASH_14C = (
    "lexcfg_c92796c8f355a967e4f04143732a371bae405323c58c9cac39d5e97ed4f21cad"
)
FUSION_CONFIG_HASH_14C = (
    "fuscfg_fa8a567966bfa7676166b2689fec631d8a9cee0fd0739cdb1688854df92755a9"
)
RERANKER_CONFIG_HASH_14C = (
    "rrkcfg_68c77803ed7dc09ef0b5df50b3c09b6ee1c388bdccd0b8c29ca4c2161d57bb3e"
)

# Exact Gold membership (sorted). Reused from ics_modules GoldDataset /
# 9H-P hybrid vs hybrid-rerank population — no new Gold labels.
QUERY_IDS_14C: tuple[str, ...] = (
    "draft_08f83eaef198495d92ff557eda974bf4",
    "draft_127ac342012d47fc9720a0c13a577550",
    "draft_2083433ad52e4e00ad4214d3fec27464",
    "draft_29389bdab2f84345b596e45fcf2e2bcc",
    "draft_296be0251d6f4ad2baadedfb506eba4b",
    "draft_4c185aa9607b42688627ef26323f3367",
    "draft_53be6e34cbb745c18d11ed233897fcb3",
    "draft_54115e36a58442e0a1574bc8017248c9",
    "draft_559331559a1a4a3eaf6f667db0727850",
    "draft_5cc85e4fade84aab9369d0a129f913c4",
    "draft_7cb38254d8ab4c2084bb9e328da73b1e",
    "draft_7df2ca731edf4daaa794ee20507205ca",
    "draft_85741ff7269e40bb8ce8992f24a6f3c7",
    "draft_94722ca912bd46ada6b9689f388d1b17",
    "draft_959387c7d1fc48f0a7ac4b38166d1fb1",
    "draft_a597e472c3e141c3bf4a5539d2bcb5dd",
    "draft_aad45b4a4bd940459793788e716aa580",
    "draft_ac3bfbaa86b4458ea1137742dc3829de",
    "draft_b88e163517ec47e29240171af181566d",
    "draft_bc0aa8c3e7e44e20bae3af071f3eab68",
    "draft_cc9a054620e040a5adee66a1f4dc3540",
    "draft_e8bd3467bc52419e95d19a19dde839e2",
)

WARMUP_COUNT_14C = 2
MEASURED_REPETITIONS_14C = 10
COLD_WARM_14C = "warm"

TREATMENT_DELTA_14C: tuple[str, ...] = (
    "reranker_enabled",
    "reranker_configuration",
    "reranker_config_hash",
    "stage_or_path",
)

FROZEN_SUITE_REL = Path(
    "eval/fixtures/performance_14/suites/14c_hybrid_vs_hybrid_rerank_v1.json"
)


def _shared_non_treatment_config() -> dict[str, object]:
    return {
        "retrieval_mode": "hybrid",
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
        "generation_enabled": False,
        "generation_excluded": True,
    }


def variant_configs_14c() -> dict[str, dict[str, object]]:
    shared = _shared_non_treatment_config()
    return {
        VARIANT_HYBRID: {
            **shared,
            "reranker_enabled": False,
            "reranker_configuration": None,
            "reranker_config_hash": None,
            "stage_or_path": "fusion",
        },
        VARIANT_HYBRID_RERANK: {
            **shared,
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
            "stage_or_path": "rerank",
        },
    }


def case_specs_14c() -> tuple[PerformanceCaseSpec, ...]:
    cases: list[PerformanceCaseSpec] = []
    for query_id in QUERY_IDS_14C:
        for variant in (VARIANT_HYBRID, VARIANT_HYBRID_RERANK):
            cases.append(
                PerformanceCaseSpec(
                    case_kind="pipeline_query",
                    benchmark_level="B",
                    stage_or_path=("fusion" if variant == VARIANT_HYBRID else "rerank"),
                    subject_identity=query_id,
                    variant=variant,
                    cold_warm=COLD_WARM_14C,  # type: ignore[arg-type]
                    local_case_id=query_id,
                )
            )
    return tuple(cases)


def case_ids_14c() -> list[str]:
    return [stable_case_id(spec) for spec in case_specs_14c()]


def build_suite_body_14c() -> PerformanceBenchmarkSuiteV1:
    suite = PerformanceBenchmarkSuiteV1(
        benchmark_level="B",
        population_identity=POPULATION_IDENTITY_14C,
        variants=[VARIANT_HYBRID, VARIANT_HYBRID_RERANK],
        case_ids=case_ids_14c(),
        measurement_protocol_version=MEASUREMENT_PROTOCOL_VERSION_V1,
        timing_boundary_version=TIMING_BOUNDARY_VERSION_V1,
        statistics_semantics_version=STATISTICS_SEMANTICS_VERSION_V1,
    )
    return suite.model_copy(
        update={"suite_identity_hash": compute_suite_identity_hash(suite)}
    )


def build_suite_plan_14c() -> PerformanceSuitePlan:
    suite = build_suite_body_14c()
    return PerformanceSuitePlan(
        suite=suite,
        cases=case_specs_14c(),
        warmup_count=WARMUP_COUNT_14C,
        measured_repetitions=MEASURED_REPETITIONS_14C,
        baseline_variant=VARIANT_HYBRID,
        treatment_variant=VARIANT_HYBRID_RERANK,
        treatment_delta=TREATMENT_DELTA_14C,
        variant_configs=variant_configs_14c(),
        population_kind="quality_vs_cost_frozen",
        diagnostic_only=True,
        authoritative=False,
    )


def scientific_config_payload_14c(
    plan: PerformanceSuitePlan | None = None,
) -> dict[str, object]:
    """Scientific effective-config payload for ``perfcfg_`` (no authority flags).

    Authorization / evidence-class state (``diagnostic_only``, ``authoritative``,
    ``execution_authorized``) is intentionally excluded so a later separately
    authorized authoritative run can reuse this frozen scientific identity.
    """
    plan = plan if plan is not None else build_suite_plan_14c()
    return {
        "benchmark_level": plan.suite.benchmark_level,
        "population_identity": plan.suite.population_identity,
        "variants": sorted(plan.suite.variants),
        "warmup_count": plan.warmup_count,
        "measured_repetitions": plan.measured_repetitions,
        "baseline_variant": plan.baseline_variant,
        "treatment_variant": plan.treatment_variant,
        "treatment_delta": list(plan.treatment_delta),
        "variant_configs": plan.variant_configs,
        "substrate_pin_14b": SUBSTRATE_PIN_14B,
        "suite_kind": "quality_vs_cost_14c",
    }


def effective_config_id_14c() -> str:
    """Return ``perfcfg_`` over the frozen scientific variant configuration."""
    return compute_config_identity_hash(scientific_config_payload_14c())


class PerformanceFrozenSuite14CV1(StrictModel):
    """Machine-readable frozen 14C suite artifact (definition only)."""

    contract: ExactNonBlankStr = PERFORMANCE_FROZEN_SUITE_14C_V1
    suite_slug: ExactNonBlankStr = SUITE_SLUG_14C
    suite_kind: ExactNonBlankStr = "quality_vs_cost"
    benchmark_level: ExactNonBlankStr = "B"
    design_authority_sha: ExactNonBlankStr = DESIGN_AUTHORITY_SHA_14
    substrate_pin_14b: ExactNonBlankStr = SUBSTRATE_PIN_14B
    population_identity: ExactNonBlankStr = POPULATION_IDENTITY_14C
    gold_dataset_id: ExactNonBlankStr = GOLD_DATASET_ID_14C
    gold_schema_version: ExactNonBlankStr = GOLD_SCHEMA_VERSION_14C
    gold_relative_path: ExactNonBlankStr = GOLD_RELATIVE_PATH_14C
    query_ids: list[ExactNonBlankStr] = Field(min_length=1)
    case_ids: list[ExactNonBlankStr] = Field(min_length=1)
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
    variants: list[ExactNonBlankStr] = Field(min_length=2)
    baseline_variant: ExactNonBlankStr = VARIANT_HYBRID
    treatment_variant: ExactNonBlankStr = VARIANT_HYBRID_RERANK
    treatment_delta: list[ExactNonBlankStr] = Field(min_length=1)
    variant_configs: dict[str, dict[str, Any]]
    warmup_count: int = Field(ge=0)
    measured_repetitions: int = Field(ge=10)
    cold_warm: ExactNonBlankStr = COLD_WARM_14C
    generation_excluded: bool = True
    execution_authorized: bool = False
    authoritative_results_authorized: bool = False
    suite_identity_hash: ExactNonBlankStr
    effective_config_id: ExactNonBlankStr
    measurement_protocol_version: ExactNonBlankStr = MEASUREMENT_PROTOCOL_VERSION_V1
    timing_boundary_version: ExactNonBlankStr = TIMING_BOUNDARY_VERSION_V1
    statistics_semantics_version: ExactNonBlankStr = STATISTICS_SEMANTICS_VERSION_V1

    @field_validator("query_ids", "case_ids", "variants", "treatment_delta")
    @classmethod
    def _no_dupes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate membership ids are forbidden")
        return value

    @model_validator(mode="after")
    def _freeze_gates(self) -> PerformanceFrozenSuite14CV1:
        if self.execution_authorized:
            raise ValueError("14C suite freeze must set execution_authorized=False")
        if self.authoritative_results_authorized:
            raise ValueError(
                "14C suite freeze must set authoritative_results_authorized=False"
            )
        if not self.generation_excluded:
            raise ValueError("14C first comparison excludes generation")
        if not self.suite_identity_hash.startswith("perfsuite_"):
            raise ValueError("suite_identity_hash must be perfsuite_…")
        if not self.effective_config_id.startswith("perfcfg_"):
            raise ValueError("effective_config_id must be perfcfg_…")
        if self.cold_warm != "warm":
            raise ValueError("14C frozen suite is warm-classified only")
        if self.baseline_variant != VARIANT_HYBRID:
            raise ValueError("14C baseline_variant must be hybrid")
        if self.treatment_variant != VARIANT_HYBRID_RERANK:
            raise ValueError("14C treatment_variant must be hybrid_rerank")
        return self


def build_frozen_suite_artifact_14c() -> PerformanceFrozenSuite14CV1:
    suite = build_suite_body_14c()
    assert suite.suite_identity_hash is not None
    return PerformanceFrozenSuite14CV1(
        query_ids=list(QUERY_IDS_14C),
        case_ids=case_ids_14c(),
        variants=[VARIANT_HYBRID, VARIANT_HYBRID_RERANK],
        treatment_delta=list(TREATMENT_DELTA_14C),
        variant_configs=variant_configs_14c(),
        warmup_count=WARMUP_COUNT_14C,
        measured_repetitions=MEASURED_REPETITIONS_14C,
        suite_identity_hash=suite.suite_identity_hash,
        effective_config_id=effective_config_id_14c(),
    )


def assert_gold_semantic_identity_14c(gold_dir: Path) -> None:
    """Fail closed unless local Gold recomputes to the locked semantic identity.

    Uses the canonical Gold loader so query text, judgments, tags/category, and
    chunk_set/corpus pins are content-addressed. Persisted ``meta.dataset_id``
    alone is not trusted.
    """
    if not gold_dir.is_dir():
        raise Performance14Error(f"locked Gold directory missing: {gold_dir}")
    try:
        loaded = load_gold_dataset(gold_dir)
    except GoldDatasetError as exc:
        raise Performance14Error(
            f"canonical Gold semantic load failed for {gold_dir}: {exc}"
        ) from exc
    if loaded.dataset_id != GOLD_DATASET_ID_14C:
        raise Performance14Error(
            "recomputed Gold dataset_id diverges from locked gold_dataset_id: "
            f"{loaded.dataset_id} != {GOLD_DATASET_ID_14C}"
        )
    if loaded.source_schema != GOLD_SCHEMA_VERSION_14C:
        raise Performance14Error(
            "Gold source_schema diverges from locked gold_schema_version"
        )
    if loaded.meta.corpus_id != CORPUS_ID_14C:
        raise Performance14Error("Gold corpus_id diverges from lock")
    if loaded.meta.chunk_set_id != CHUNK_SET_ID_14C:
        raise Performance14Error("Gold chunk_set_id diverges from lock")
    on_disk_ids = [case.id for case in loaded.cases]
    if sorted(on_disk_ids) != sorted(QUERY_IDS_14C):
        raise Performance14Error(
            "Gold case membership diverges from locked QUERY_IDS_14C"
        )
    if len(on_disk_ids) != len(QUERY_IDS_14C):
        raise Performance14Error("Gold case count diverges from locked QUERY_IDS_14C")


def _assert_gold_membership_on_disk(repo_root: Path) -> None:
    """Fail closed if locked Gold path is absent or semantically drifted."""
    gold_dir = (repo_root / GOLD_RELATIVE_PATH_14C).resolve()
    assert_gold_semantic_identity_14c(gold_dir)


def validate_frozen_suite_14c(
    artifact: PerformanceFrozenSuite14CV1 | None = None,
    *,
    repo_root: Path | None = None,
) -> PerformanceFrozenSuite14CV1:
    """Fail-closed validation of the frozen suite definition."""
    locked = build_frozen_suite_artifact_14c()
    art = artifact if artifact is not None else locked
    plan = build_suite_plan_14c()
    assert_protocol_counts(
        level="B",
        warmup_count=plan.warmup_count,
        measured_repetitions=plan.measured_repetitions,
    )
    assert_case_membership(plan)
    assert_paired_comparison_invariant(plan)
    assert_treatment_only_config_delta(plan)

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
    if list(art.query_ids) != list(QUERY_IDS_14C):
        raise Performance14Error("frozen query_ids diverge from locked membership")
    if len(art.query_ids) != 22:
        raise Performance14Error("14C population must contain exactly 22 queries")
    if list(art.case_ids) != case_ids_14c():
        raise Performance14Error("frozen case_ids diverge from locked membership")
    if len(art.case_ids) != 44:
        raise Performance14Error("14C must freeze 22 queries × 2 variants = 44 cases")
    if art.effective_config_id != effective_config_id_14c():
        raise Performance14Error("effective_config_id diverges from locked payload")
    if art.effective_config_id != locked.effective_config_id:
        raise Performance14Error("artifact effective_config_id diverges from lock")
    if art.model_dump(mode="json") != locked.model_dump(mode="json"):
        raise Performance14Error(
            "frozen suite artifact diverges from locked builder output"
        )
    # Order independence of variant_configs must not flip perfcfg_.
    reordered = {
        VARIANT_HYBRID_RERANK: dict(
            reversed(list(plan.variant_configs[VARIANT_HYBRID_RERANK].items()))
        ),
        VARIANT_HYBRID: dict(
            reversed(list(plan.variant_configs[VARIANT_HYBRID].items()))
        ),
    }
    reordered_plan = replace(plan, variant_configs=reordered)
    if (
        compute_config_identity_hash(scientific_config_payload_14c(reordered_plan))
        != art.effective_config_id
    ):
        raise Performance14Error(
            "effective_config_id is not stable under variant_configs key reordering"
        )
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    _assert_gold_membership_on_disk(root)
    return art


def default_frozen_suite_path(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return (root / FROZEN_SUITE_REL).resolve()


def write_frozen_suite_artifact(
    path: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Write the deterministic frozen suite JSON (create-exclusive)."""
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    art = validate_frozen_suite_14c(repo_root=root)
    target = path if path is not None else default_frozen_suite_path(root)
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


def load_frozen_suite_artifact(
    path: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> PerformanceFrozenSuite14CV1:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    target = path if path is not None else default_frozen_suite_path(root)
    raw = json.loads(target.read_text(encoding="utf-8"))
    art = PerformanceFrozenSuite14CV1.model_validate(raw)
    return validate_frozen_suite_14c(art, repo_root=root)
