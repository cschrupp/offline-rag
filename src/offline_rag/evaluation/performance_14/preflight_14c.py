"""Fail-closed preflight for authoritative Slice 14C execution."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from offline_rag.config.loader import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.persistence import index_state_path, try_load_index_state
from offline_rag.evaluation.performance_14.contracts import (
    DESIGN_AUTHORITY_SHA_14,
    Performance14Error,
    PerformanceMachineProfileV1,
    PerformancePreflightRecordV1,
)
from offline_rag.evaluation.performance_14.fixtures import PerformanceSuitePlan
from offline_rag.evaluation.performance_14.machine import (
    capture_machine_profile_with_id,
)
from offline_rag.evaluation.performance_14.paths import reserved_results_root
from offline_rag.evaluation.performance_14.preflight import (
    PreflightAccumulator,
    assert_case_membership,
    assert_paired_comparison_invariant,
    assert_protocol_counts,
    assert_suite_identity,
    assert_treatment_only_config_delta,
    capture_working_tree_state,
    resolve_executing_sha,
    resolve_repo_root,
)
from offline_rag.evaluation.performance_14.resources import (
    observe_ram_rss_bytes,
    observe_vram,
)
from offline_rag.evaluation.performance_14.suite_14c import (
    CHUNK_SET_ID_14C,
    CORPUS_ID_14C,
    DENSE_INDEX_ID_14C,
    EMBEDDING_CONFIG_HASH_14C,
    FUSION_CONFIG_HASH_14C,
    GOLD_DATASET_ID_14C,
    GOLD_RELATIVE_PATH_14C,
    INDEX_CONFIG_HASH_14C,
    LEXICAL_CONFIG_HASH_14C,
    LEXICAL_INDEX_ID_14C,
    RERANKER_CONFIG_HASH_14C,
    SUBSTRATE_PIN_14B,
    assert_gold_semantic_identity_14c,
    effective_config_id_14c,
    load_frozen_suite_artifact,
)
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.rerank.config_hash import build_reranker_config_hash

SUITE_FREEZE_AUTHORITY_14C = "a662efc50d712bd6a986da05809dc864342139df"
CORPUS_NAME_14C = "ics_modules"

HYBRID_SETTINGS_YAMLS = (
    Path("config/base.yaml"),
    Path("config/experiments/hybrid_rrf.yaml"),
)
HYBRID_RERANK_SETTINGS_YAMLS = (
    Path("config/base.yaml"),
    Path("config/experiments/hybrid_rerank.yaml"),
)


def assert_suite_freeze_authority_reachable(repo_root: Path) -> None:
    probe = subprocess.run(
        ["git", "merge-base", "--is-ancestor", SUITE_FREEZE_AUTHORITY_14C, "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise Performance14Error(
            f"accepted 14C suite-freeze authority {SUITE_FREEZE_AUTHORITY_14C} "
            "is not an ancestor of HEAD"
        )


def assert_working_tree_clean_for_authoritative(repo_root: Path) -> None:
    state, detail = capture_working_tree_state(repo_root)
    if state != "clean":
        raise Performance14Error(
            "authoritative 14C execution requires a clean working tree; "
            f"got {state}: {detail}"
        )


def load_hybrid_settings(repo_root: Path) -> AppSettings:
    paths = [repo_root / rel for rel in HYBRID_SETTINGS_YAMLS]
    return load_settings(yaml_paths=paths, environ={})


def load_hybrid_rerank_settings(repo_root: Path) -> AppSettings:
    paths = [repo_root / rel for rel in HYBRID_RERANK_SETTINGS_YAMLS]
    return load_settings(yaml_paths=paths, environ={})


def assert_index_and_config_pins(
    *,
    hybrid_settings: AppSettings,
    rerank_settings: AppSettings,
) -> None:
    dense_state = try_load_index_state(
        index_state_path(hybrid_settings.paths.corpora, CORPUS_NAME_14C)
    )
    if dense_state is None:
        raise Performance14Error("dense CURRENT index state missing for ics_modules")
    if dense_state.current_index_id != DENSE_INDEX_ID_14C:
        raise Performance14Error(
            "CURRENT dense index_id diverges from frozen 14C pin: "
            f"{dense_state.current_index_id} != {DENSE_INDEX_ID_14C}"
        )
    if dense_state.source_corpus_id != CORPUS_ID_14C:
        raise Performance14Error("dense source_corpus_id diverges from frozen pin")
    if dense_state.source_chunk_set_id != CHUNK_SET_ID_14C:
        raise Performance14Error("dense source_chunk_set_id diverges from frozen pin")

    lexical_state_path = (
        Path(hybrid_settings.paths.corpora) / CORPUS_NAME_14C / "lexical" / "state.json"
    )
    if not lexical_state_path.is_file():
        raise Performance14Error(f"lexical CURRENT state missing: {lexical_state_path}")
    lexical_state = json.loads(lexical_state_path.read_text(encoding="utf-8"))
    if lexical_state.get("current_lexical_index_id") != LEXICAL_INDEX_ID_14C:
        raise Performance14Error(
            "CURRENT lexical index_id diverges from frozen 14C pin: "
            f"{lexical_state.get('current_lexical_index_id')} != {LEXICAL_INDEX_ID_14C}"
        )
    if lexical_state.get("source_corpus_id") != CORPUS_ID_14C:
        raise Performance14Error("lexical source_corpus_id diverges from frozen pin")
    if lexical_state.get("source_chunk_set_id") != CHUNK_SET_ID_14C:
        raise Performance14Error("lexical source_chunk_set_id diverges from frozen pin")

    if build_embedding_config_hash(hybrid_settings) != EMBEDDING_CONFIG_HASH_14C:
        raise Performance14Error("embedding_config_hash diverges from frozen 14C pin")
    if build_index_config_hash(hybrid_settings) != INDEX_CONFIG_HASH_14C:
        raise Performance14Error("index_config_hash diverges from frozen 14C pin")
    if build_lexical_config_hash(hybrid_settings) != LEXICAL_CONFIG_HASH_14C:
        raise Performance14Error("lexical_config_hash diverges from frozen 14C pin")
    if build_fusion_config_hash(hybrid_settings) != FUSION_CONFIG_HASH_14C:
        raise Performance14Error("fusion_config_hash diverges from frozen 14C pin")
    if build_reranker_config_hash(rerank_settings) != RERANKER_CONFIG_HASH_14C:
        raise Performance14Error("reranker_config_hash diverges from frozen 14C pin")
    if not rerank_settings.reranker.enabled:
        raise Performance14Error("hybrid_rerank settings must enable the reranker")
    model_path = Path(rerank_settings.reranker.model.model_path)
    if not model_path.exists():
        raise Performance14Error(f"reranker model path missing: {model_path}")


def assert_frozen_suite_identities(plan: PerformanceSuitePlan, repo_root: Path) -> str:
    frozen = load_frozen_suite_artifact(repo_root=repo_root)
    if plan.suite.suite_identity_hash != frozen.suite_identity_hash:
        raise Performance14Error(
            "suite plan identity diverges from frozen 14C suite artifact"
        )
    recomputed_cfg = effective_config_id_14c()
    if recomputed_cfg != frozen.effective_config_id:
        raise Performance14Error(
            "scientific perfcfg_ diverges from frozen 14C suite artifact"
        )
    if frozen.gold_dataset_id != GOLD_DATASET_ID_14C:
        raise Performance14Error("frozen artifact gold_dataset_id drifted")
    return recomputed_cfg


@dataclass(frozen=True, slots=True)
class Authoritative14CPreflightContext:
    repo_root: Path
    executing_sha: str
    suite_id: str
    machine_profile_id: str
    machine_profile: PerformanceMachineProfileV1
    design_authority_sha: str
    suite_freeze_authority: str
    substrate_pin_14b: str
    results_parent: Path
    record: PerformancePreflightRecordV1
    hybrid_settings: AppSettings
    rerank_settings: AppSettings
    scientific_config_id: str


def run_authoritative_14c_preflight(
    plan: PerformanceSuitePlan,
    *,
    repo_root: Path | None = None,
) -> Authoritative14CPreflightContext:
    """Fail-closed preflight before authoritative 14C measurement."""
    acc = PreflightAccumulator()
    try:
        root = acc.run_check("repository_root", lambda: resolve_repo_root(repo_root))
        acc.repo_root = root
        acc.add("repository_root", "passed")

        executing_sha = acc.run_check(
            "executing_sha", lambda: resolve_executing_sha(root)
        )
        acc.executing_sha = executing_sha
        acc.add("executing_sha", "passed", executing_sha)

        acc.run_check(
            "working_tree_clean",
            lambda: assert_working_tree_clean_for_authoritative(root),
        )
        acc.working_tree_state = "clean"
        acc.add("working_tree_clean", "passed", "clean")

        acc.run_check(
            "suite_freeze_authority",
            lambda: assert_suite_freeze_authority_reachable(root),
        )
        acc.add("suite_freeze_authority", "passed", SUITE_FREEZE_AUTHORITY_14C)

        suite_id = acc.run_check(
            "suite_identity", lambda: assert_suite_identity(plan.suite)
        )
        acc.suite_id = suite_id
        acc.add("suite_identity", "passed", suite_id)

        scientific_config_id = acc.run_check(
            "frozen_suite_identities",
            lambda: assert_frozen_suite_identities(plan, root),
        )
        acc.add("frozen_suite_identities", "passed", scientific_config_id)

        acc.run_check("case_membership", lambda: assert_case_membership(plan))
        acc.add("case_membership", "passed")

        acc.run_check(
            "protocol_counts",
            lambda: assert_protocol_counts(
                level=plan.suite.benchmark_level,
                warmup_count=plan.warmup_count,
                measured_repetitions=plan.measured_repetitions,
            ),
        )
        acc.add(
            "protocol_counts",
            "passed",
            f"warmup={plan.warmup_count}; measured={plan.measured_repetitions}",
        )

        acc.run_check(
            "paired_comparison_invariant",
            lambda: assert_paired_comparison_invariant(plan),
        )
        acc.add("paired_comparison_invariant", "passed")

        acc.run_check(
            "treatment_config_delta",
            lambda: assert_treatment_only_config_delta(plan),
        )
        acc.add("treatment_config_delta", "passed")

        gold_dir = root / GOLD_RELATIVE_PATH_14C
        acc.run_check(
            "gold_semantic_identity",
            lambda: assert_gold_semantic_identity_14c(gold_dir),
        )
        acc.add("gold_semantic_identity", "passed", GOLD_DATASET_ID_14C)

        hybrid_settings = acc.run_check(
            "hybrid_settings", lambda: load_hybrid_settings(root)
        )
        rerank_settings = acc.run_check(
            "hybrid_rerank_settings", lambda: load_hybrid_rerank_settings(root)
        )
        acc.add("hybrid_settings", "passed", "hybrid_rrf")
        acc.add("hybrid_rerank_settings", "passed", "hybrid_rerank")

        acc.run_check(
            "index_and_config_pins",
            lambda: assert_index_and_config_pins(
                hybrid_settings=hybrid_settings,
                rerank_settings=rerank_settings,
            ),
        )
        acc.add(
            "index_and_config_pins",
            "passed",
            f"dense={DENSE_INDEX_ID_14C}; lexical={LEXICAL_INDEX_ID_14C}",
        )

        results_parent = reserved_results_root(root)

        def _prepare_output() -> Path:
            results_parent.mkdir(parents=True, exist_ok=True)
            probe = results_parent / f".perf14_auth_write_probe_{executing_sha[:8]}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return results_parent

        parent = acc.run_check("output_writable", _prepare_output)
        acc.add("output_writable", "passed", str(parent))

        usage = shutil.disk_usage(parent)
        if usage.free < 256 * 1024 * 1024:
            raise Performance14Error(
                f"insufficient disk capacity under {parent}: free={usage.free}"
            )
        acc.disk_capacity_sufficient = True
        acc.disk_free_bytes = int(usage.free)
        acc.add("disk_capacity", "passed", f"free_bytes={usage.free}")

        machine_profile, machine_profile_id = acc.run_check(
            "machine_profile",
            lambda: capture_machine_profile_with_id(
                offline_rag_commit_sha=executing_sha
            ),
        )
        acc.machine_profile = machine_profile
        acc.machine_profile_id = machine_profile_id
        acc.add("machine_profile", "passed", machine_profile_id)

        ram_av, _rss = observe_ram_rss_bytes()
        vram_av, _, _, _ = observe_vram()
        acc.telemetry_ram = ram_av
        acc.telemetry_vram = vram_av
        acc.add("telemetry_ram", "passed", ram_av)
        acc.add("telemetry_vram", "passed", vram_av)

        record = acc.to_record(status="passed")
        return Authoritative14CPreflightContext(
            repo_root=root,
            executing_sha=executing_sha,
            suite_id=suite_id,
            machine_profile_id=machine_profile_id,
            machine_profile=machine_profile,
            design_authority_sha=DESIGN_AUTHORITY_SHA_14,
            suite_freeze_authority=SUITE_FREEZE_AUTHORITY_14C,
            substrate_pin_14b=SUBSTRATE_PIN_14B,
            results_parent=parent,
            record=record,
            hybrid_settings=hybrid_settings,
            rerank_settings=rerank_settings,
            scientific_config_id=scientific_config_id,
        )
    except Performance14Error as exc:
        if acc.failing_check is None:
            acc.fail("preflight", str(exc))
        record = acc.to_record(status="failed")
        exc.preflight_record = record  # type: ignore[attr-defined]
        exc.preflight_partial = acc  # type: ignore[attr-defined]
        raise
