"""Authoritative Slice 14C hybrid vs hybrid+reranker benchmark execution.

Requires explicit Q25-style human authorization via
``confirm_execution_authorization=True``. Does not mutate the frozen suite
artifact's ``execution_authorized`` gate; scientific ``perfsuite_`` /
``perfcfg_`` identities remain unchanged.

Harness rework (post-audit): quality evidence + semantic stage envelopes.
Does not overwrite prior terminal ``perfrun_`` artifacts.
"""

from __future__ import annotations

import platform
import sys
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from offline_rag.core.ids import (
    BGE_RERANKER_MODEL_ID,
    QWEN3_EMBEDDING_MODEL_ID,
)
from offline_rag.evaluation.gold import GoldCase, load_gold_dataset
from offline_rag.evaluation.performance_14.aggregate import build_run_aggregate
from offline_rag.evaluation.performance_14.artifacts import write_run_artifacts
from offline_rag.evaluation.performance_14.contracts import (
    Performance14Error,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkObservationV1,
    PerformanceBenchmarkRunManifestV1,
    PerformanceMachineProfileV1,
    PerformancePathSampleV1,
    PerformancePreflightRecordV1,
    PerformanceResourceObservationV1,
    PerformanceRunAggregateV1,
    RunStatusV1,
)
from offline_rag.evaluation.performance_14.evidence_14c import (
    RESOURCE_NOTE_PRE_PATH,
    RESOURCE_SCOPE_RETRIEVAL_PATH,
    assert_not_end_to_end_stage,
    assert_paired_quality_coverage,
    macro_quality_by_variant,
    path_latency_rollups,
    quality_from_ranking,
    resource_summary_by_variant,
    semantic_observations_from_hybrid_metadata,
    semantic_observations_from_hybrid_rerank_metadata,
)
from offline_rag.evaluation.performance_14.fixtures import (
    VARIANT_HYBRID,
    VARIANT_HYBRID_RERANK,
    PerformanceCaseSpec,
    stable_case_id,
)
from offline_rag.evaluation.performance_14.harness import _ordered_case_specs
from offline_rag.evaluation.performance_14.identity import (
    compute_case_identity_hash,
    compute_run_identity_hash,
)
from offline_rag.evaluation.performance_14.paths import allocate_authoritative_run_dir
from offline_rag.evaluation.performance_14.preflight import PreflightAccumulator
from offline_rag.evaluation.performance_14.preflight_14c import (
    CORPUS_NAME_14C,
    SUITE_FREEZE_AUTHORITY_14C,
    Authoritative14CPreflightContext,
    run_authoritative_14c_preflight,
)
from offline_rag.evaluation.performance_14.resources import capture_resource_observation
from offline_rag.evaluation.performance_14.statistics import derive_latency_stats
from offline_rag.evaluation.performance_14.suite_14c import (
    CORPUS_ID_14C,
    GOLD_RELATIVE_PATH_14C,
    SUBSTRATE_PIN_14B,
    build_suite_plan_14c,
    effective_config_id_14c,
)
from offline_rag.hybrid.retrieve import HybridRetriever
from offline_rag.rerank.retrieve import HybridRerankRetriever

EXECUTION_AUTHORIZATION_STATEMENT_14C = (
    "Q25_SLICE_14C_AUTHORITATIVE_BENCHMARK_EXECUTION"
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class Authoritative14CResult:
    run_id: str
    output_dir: Path
    run_status: RunStatusV1
    suite_id: str
    scientific_config_id: str
    manifest: PerformanceBenchmarkRunManifestV1
    aggregate: PerformanceRunAggregateV1
    cases: list[PerformanceBenchmarkCaseV1] = field(default_factory=list)
    preflight: PerformancePreflightRecordV1 | None = None
    run_label: str | None = None
    error: str | None = None
    diagnostic_only: bool = False
    authoritative: bool = True


@dataclass
class _RetrieveOutcome:
    ranked_chunk_ids: list[str]
    metadata: dict[str, Any]
    variant: str


class _14CStageEngine:
    """Shared hybrid / hybrid-rerank engines for the full campaign.

    A single HybridRetriever is shared so local Qdrant storage is opened once.
    """

    def __init__(
        self,
        *,
        hybrid: HybridRetriever,
        hybrid_rerank: HybridRerankRetriever,
        query_by_id: dict[str, str],
        fusion_output_top_k: int,
        rerank_output_top_k: int,
    ) -> None:
        self._hybrid = hybrid
        self._hybrid_rerank = hybrid_rerank
        self._query_by_id = query_by_id
        self._fusion_output_top_k = fusion_output_top_k
        self._rerank_output_top_k = rerank_output_top_k

    def close(self) -> None:
        # hybrid_rerank may borrow hybrid; close wrapper first, then owned hybrid.
        self._hybrid_rerank.close()
        self._hybrid.close()

    def prepare_engines(self) -> None:
        """Load models/indexes outside timed observations (one probe each)."""
        probe_qid = next(iter(self._query_by_id))
        probe_query = self._query_by_id[probe_qid]
        self._hybrid.retrieve(
            query=probe_query,
            corpus_name=CORPUS_NAME_14C,
            top_k=self._fusion_output_top_k,
        )
        self._hybrid_rerank.retrieve(
            query=probe_query,
            corpus_name=CORPUS_NAME_14C,
            top_k=self._rerank_output_top_k,
        )

    def retrieve(self, spec: PerformanceCaseSpec) -> _RetrieveOutcome:
        """Execute the variant retrieve path and return ranked evidence + metadata."""
        query = self._query_by_id.get(spec.subject_identity)
        if query is None:
            raise Performance14Error(
                f"frozen subject {spec.subject_identity!r} missing from Gold queries"
            )
        if spec.variant == VARIANT_HYBRID:
            result = self._hybrid.retrieve(
                query=query,
                corpus_name=CORPUS_NAME_14C,
                top_k=self._fusion_output_top_k,
            )
            return _RetrieveOutcome(
                ranked_chunk_ids=[c.chunk_id for c in result.candidates],
                metadata=dict(result.metadata),
                variant=VARIANT_HYBRID,
            )
        if spec.variant == VARIANT_HYBRID_RERANK:
            result = self._hybrid_rerank.retrieve(
                query=query,
                corpus_name=CORPUS_NAME_14C,
                top_k=self._rerank_output_top_k,
            )
            return _RetrieveOutcome(
                ranked_chunk_ids=[c.chunk_id for c in result.candidates],
                metadata=dict(result.metadata),
                variant=VARIANT_HYBRID_RERANK,
            )
        raise Performance14Error(f"unsupported 14C variant: {spec.variant!r}")

    @property
    def requested_depth(self) -> dict[str, int]:
        return {
            VARIANT_HYBRID: self._fusion_output_top_k,
            VARIANT_HYBRID_RERANK: self._rerank_output_top_k,
        }


def _build_query_map(repo_root: Path) -> dict[str, str]:
    loaded = load_gold_dataset(repo_root / GOLD_RELATIVE_PATH_14C)
    return {case.id: case.query for case in loaded.cases}


def _build_gold_map(repo_root: Path) -> dict[str, GoldCase]:
    loaded = load_gold_dataset(repo_root / GOLD_RELATIVE_PATH_14C)
    return {case.id: case for case in loaded.cases}


def _observe_14c_once(
    engine: _14CStageEngine,
    spec: PerformanceCaseSpec,
    *,
    is_warmup: bool,
) -> tuple[
    list[PerformanceBenchmarkObservationV1],
    list[PerformancePathSampleV1],
    list[str] | None,
    PerformanceResourceObservationV1 | None,
    str | None,
]:
    """One retrieve: semantic stage obs + path samples (never end_to_end)."""
    assert_not_end_to_end_stage(spec.stage_or_path)
    resource: PerformanceResourceObservationV1 | None = None
    try:
        resource = capture_resource_observation(
            RESOURCE_SCOPE_RETRIEVAL_PATH,
            note=RESOURCE_NOTE_PRE_PATH,
            is_warmup=is_warmup,
        )
    except Exception:  # noqa: BLE001 — telemetry must not fail the observation
        resource = None

    try:
        outcome = engine.retrieve(spec)
        if outcome.variant == VARIANT_HYBRID:
            observations, path_samples = semantic_observations_from_hybrid_metadata(
                outcome.metadata,
                is_warmup=is_warmup,
                resource=resource,
            )
        else:
            observations, path_samples = (
                semantic_observations_from_hybrid_rerank_metadata(
                    outcome.metadata,
                    is_warmup=is_warmup,
                    resource=resource,
                )
            )
        for obs in observations:
            assert_not_end_to_end_stage(obs.stage_id)
        for sample in path_samples:
            assert_not_end_to_end_stage(sample.path)
        return (
            observations,
            path_samples,
            list(outcome.ranked_chunk_ids),
            resource,
            None,
        )
    except Exception as exc:  # noqa: BLE001 — observation fail-closed
        failed = PerformanceBenchmarkObservationV1(
            observation_status="failed",
            stage_id=spec.stage_or_path,
            is_warmup=is_warmup,
            failure_reason=f"{type(exc).__name__}: {exc}",
            resource=resource,
        )
        return [failed], [], None, resource, f"{type(exc).__name__}: {exc}"


def _execute_14c_case(
    spec: PerformanceCaseSpec,
    *,
    engine: _14CStageEngine,
    gold_by_id: dict[str, GoldCase],
    warmup_count: int,
    measured_repetitions: int,
) -> PerformanceBenchmarkCaseV1:
    """Execute one frozen case with quality evidence and semantic timing envelopes."""
    case_id = stable_case_id(spec)
    warmups: list[PerformanceBenchmarkObservationV1] = []
    measured: list[PerformanceBenchmarkObservationV1] = []
    path_samples: list[PerformancePathSampleV1] = []
    resources: list[PerformanceResourceObservationV1] = []
    ranked_chunk_ids: list[str] | None = None
    failure_reasons: list[str] = []

    for _ in range(warmup_count):
        obs_list, paths, _ranked, resource, failure = _observe_14c_once(
            engine, spec, is_warmup=True
        )
        warmups.extend(obs_list)
        path_samples.extend(paths)
        if resource is not None:
            resources.append(resource)

    for _ in range(measured_repetitions):
        obs_list, paths, ranked, resource, failure = _observe_14c_once(
            engine, spec, is_warmup=False
        )
        measured.extend(obs_list)
        path_samples.extend(paths)
        if resource is not None:
            resources.append(resource)
        if failure is not None:
            failure_reasons.append(failure)
            continue
        if ranked is not None:
            ranked_chunk_ids = ranked

    quality = None
    gold = gold_by_id.get(spec.subject_identity)
    if ranked_chunk_ids is not None and gold is not None:
        quality = quality_from_ranking(
            gold,
            ranked_chunk_ids,
            requested_depth=engine.requested_depth[spec.variant],
        )

    case_status = "failed" if failure_reasons else "completed"
    # Case-level derived stats use the frozen semantic stage only (not path totals).
    semantic_for_derived = [
        obs
        for obs in [*warmups, *measured]
        if obs.stage_id == spec.stage_or_path
    ]
    case = PerformanceBenchmarkCaseV1(
        case_id=case_id,
        case_kind=spec.case_kind,
        benchmark_level=spec.benchmark_level,
        stage_or_path=spec.stage_or_path,
        subject_identity=spec.subject_identity,
        variant=spec.variant,
        cold_warm=spec.cold_warm,
        case_status=case_status,
        warmup_count=len([o for o in warmups if o.stage_id == spec.stage_or_path]),
        warmup_observations=warmups,
        measured_observations=measured,
        failures=failure_reasons,
        resource_samples=resources,
        ranked_chunk_ids=ranked_chunk_ids,
        quality=quality,
        path_samples=path_samples,
    )
    derived = derive_latency_stats(
        semantic_for_derived,
        warmup_count=len([o for o in warmups if o.stage_id == spec.stage_or_path]),
    )
    case_hash = compute_case_identity_hash(case)
    return case.model_copy(update={"derived": derived, "case_identity_hash": case_hash})


def _build_manifest(
    *,
    preflight: Authoritative14CPreflightContext,
    run_nonce: str,
    run_label: str | None,
    scientific_config_id: str,
) -> PerformanceBenchmarkRunManifestV1:
    assert isinstance(preflight.machine_profile, PerformanceMachineProfileV1)
    env = {
        "os": platform.system() or "unknown",
        "dry_run": "false",
        "evidence_class": "AUTHORITATIVE",
        "suite_freeze_authority": SUITE_FREEZE_AUTHORITY_14C,
        "substrate_pin_14b": SUBSTRATE_PIN_14B,
        "execution_authorization": EXECUTION_AUTHORIZATION_STATEMENT_14C,
        "preflight_status": preflight.record.preflight_status,
        "working_tree_state": "clean",
        "generation_excluded": "true",
        "harness_evidence": "quality_and_semantic_timing_v1",
    }
    plan = build_suite_plan_14c()
    manifest = PerformanceBenchmarkRunManifestV1(
        suite_id=preflight.suite_id,
        executing_sha=preflight.executing_sha,
        machine_profile_id=preflight.machine_profile_id,
        machine_profile=preflight.machine_profile,
        config_id=scientific_config_id,
        corpus_id=CORPUS_ID_14C,
        model_ids={
            "embedding": QWEN3_EMBEDDING_MODEL_ID,
            "reranker": BGE_RERANKER_MODEL_ID,
        },
        warmup_policy=f"warmup={plan.warmup_count}",
        repetition_counts={
            "measured": plan.measured_repetitions,
            "warmup": plan.warmup_count,
        },
        start_timestamp=_utc_now_iso(),
        environment=env,
        runtime_versions={"python": sys.version.split()[0]},
        execution_mode="authoritative_14c_quality_vs_cost",
        run_status=None,
        run_nonce=run_nonce,
        run_label=run_label,
    )
    return manifest.model_copy(
        update={"run_identity_hash": compute_run_identity_hash(manifest)}
    )


def _failed_preflight_manifest(
    *,
    suite_id: str,
    run_nonce: str,
    run_label: str | None,
    record: PerformancePreflightRecordV1,
    partial: PreflightAccumulator | None,
    scientific_config_id: str,
) -> PerformanceBenchmarkRunManifestV1:
    executing_sha = (
        (partial.executing_sha if partial is not None else None)
        or record.executing_sha
        or "unresolved"
    )
    machine_profile_id = (
        (partial.machine_profile_id if partial is not None else None)
        or record.machine_profile_id
        or "perfhost_unresolved"
    )
    machine_profile = partial.machine_profile if partial is not None else None
    env = {
        "dry_run": "false",
        "evidence_class": "AUTHORITATIVE",
        "preflight_status": "failed",
        "suite_freeze_authority": SUITE_FREEZE_AUTHORITY_14C,
        "substrate_pin_14b": SUBSTRATE_PIN_14B,
        "execution_authorization": EXECUTION_AUTHORIZATION_STATEMENT_14C,
        "working_tree_state": record.working_tree_state,
        "harness_evidence": "quality_and_semantic_timing_v1",
    }
    if record.failing_check:
        env["failing_check"] = record.failing_check
    plan = build_suite_plan_14c()
    manifest = PerformanceBenchmarkRunManifestV1(
        suite_id=suite_id,
        executing_sha=executing_sha,
        machine_profile_id=machine_profile_id,
        machine_profile=machine_profile,
        config_id=scientific_config_id,
        corpus_id=CORPUS_ID_14C,
        model_ids={
            "embedding": QWEN3_EMBEDDING_MODEL_ID,
            "reranker": BGE_RERANKER_MODEL_ID,
        },
        warmup_policy=f"warmup={plan.warmup_count}",
        repetition_counts={
            "measured": plan.measured_repetitions,
            "warmup": plan.warmup_count,
        },
        start_timestamp=_utc_now_iso(),
        environment=env,
        runtime_versions={"python": sys.version.split()[0]},
        execution_mode="authoritative_14c_quality_vs_cost",
        run_status="failed_preflight",
        run_nonce=run_nonce,
        run_label=run_label,
    )
    return manifest.model_copy(
        update={"run_identity_hash": compute_run_identity_hash(manifest)}
    )


def _fmt_metric(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6g}"


def _render_authoritative_report(
    *,
    run_id: str,
    manifest: PerformanceBenchmarkRunManifestV1,
    aggregate: PerformanceRunAggregateV1,
    cases: list[PerformanceBenchmarkCaseV1],
    error: str | None = None,
) -> str:
    lines = [
        f"# Slice 14C authoritative quality-vs-cost report ({run_id})",
        "",
        "Evidence class: **AUTHORITATIVE**",
        "",
        "Raw observations are authoritative. Aggregates/report are deterministic",
        "derivations / presentation only. No winner, promotion, or portfolio claim",
        "is authorized by this artifact alone.",
        "",
        f"- suite_id: `{manifest.suite_id}`",
        f"- run_identity_hash: `{manifest.run_identity_hash}`",
        f"- executing_sha: `{manifest.executing_sha}`",
        f"- machine_profile_id: `{manifest.machine_profile_id}`",
        f"- scientific_config_id: `{manifest.config_id}`",
        f"- corpus_id: `{manifest.corpus_id}`",
        f"- execution_mode: `{manifest.execution_mode}`",
        f"- run_status: `{aggregate.run_status}`",
        f"- benchmark_level: `{aggregate.benchmark_level}`",
        f"- case_count: `{len(cases)}`",
        f"- diagnostic_only: `{aggregate.diagnostic_only}`",
        f"- authoritative: `{aggregate.authoritative}`",
        f"- suite_freeze_authority: `{SUITE_FREEZE_AUTHORITY_14C}`",
        f"- vram_availability: `{aggregate.vram_availability}`",
    ]
    if aggregate.overall is not None:
        overall = aggregate.overall
        lines.extend(
            [
                "",
                "## Overall measured accounting (total retrieval path)",
                "",
                f"- attempted_count: `{overall.attempted_count}`",
                f"- valid_count: `{overall.valid_count}`",
                f"- failure_count: `{overall.failure_count}`",
                (
                    f"- instrumentation_exclusion_count: "
                    f"`{overall.instrumentation_exclusion_count}`"
                ),
                f"- warmup_count: `{overall.warmup_count}`",
                f"- n: `{overall.n}`",
                f"- min: `{overall.min}`",
                f"- p50: `{overall.p50}`",
                f"- p95: `{overall.p95}`",
                f"- max: `{overall.max}`",
            ]
        )
    if aggregate.by_variant:
        lines.extend(["", "## By variant (total retrieval path)", ""])
        for item in aggregate.by_variant:
            lines.append(
                f"- `{item.variant}`: n={item.stats.n} "
                f"p50={item.stats.p50} p95={item.stats.p95} "
                f"failures={item.stats.failure_count}"
            )
    if aggregate.by_stage_or_path:
        lines.extend(["", "## By semantic stage / path", ""])
        for item in aggregate.by_stage_or_path:
            lines.append(
                f"- `{item.stage_or_path}`: n={item.stats.n} "
                f"p50={item.stats.p50} p95={item.stats.p95}"
            )
    if aggregate.path_latency:
        lines.extend(["", "## Path latency rollups", ""])
        for item in aggregate.path_latency:
            lines.append(
                f"- `{item.path}`: n={item.stats.n} "
                f"p50={item.stats.p50} p95={item.stats.p95}"
            )
    if aggregate.quality_by_variant:
        lines.extend(["", "## Quality by variant (macro; frozen IR semantics)", ""])
        for item in aggregate.quality_by_variant:
            lines.append(f"- `{item.variant}` (eligible={item.eligible_case_count}):")
            lines.append(
                f"  - Recall@1/5/10: {_fmt_metric(item.recall_at_1)} / "
                f"{_fmt_metric(item.recall_at_5)} / {_fmt_metric(item.recall_at_10)}"
            )
            lines.append(
                f"  - Precision@1/5/10: {_fmt_metric(item.precision_at_1)} / "
                f"{_fmt_metric(item.precision_at_5)} / "
                f"{_fmt_metric(item.precision_at_10)}"
            )
            lines.append(
                f"  - HitRate@1/5/10: {_fmt_metric(item.hit_rate_at_1)} / "
                f"{_fmt_metric(item.hit_rate_at_5)} / "
                f"{_fmt_metric(item.hit_rate_at_10)}"
            )
            lines.append(f"  - MRR: {_fmt_metric(item.mrr)}")
            lines.append(
                f"  - nDCG@1/5/10: {_fmt_metric(item.ndcg_at_1)} / "
                f"{_fmt_metric(item.ndcg_at_5)} / {_fmt_metric(item.ndcg_at_10)}"
            )
    if aggregate.resource_by_variant:
        lines.extend(["", "## Resource summary (RAM)", ""])
        for item in aggregate.resource_by_variant:
            if item.ram_availability != "available":
                lines.append(
                    f"- `{item.variant}`: RAM `{item.ram_availability}` "
                    f"(samples={item.sample_count})"
                )
                continue
            lines.append(
                f"- `{item.variant}`: RAM available samples={item.sample_count} "
                f"rss_min={item.ram_rss_bytes_min} "
                f"rss_p50={item.ram_rss_bytes_p50} "
                f"rss_p95={item.ram_rss_bytes_p95} "
                f"rss_max={item.ram_rss_bytes_max}"
            )
        lines.append(f"- VRAM: `{aggregate.vram_availability}`")
    if error:
        lines.extend(["", f"- error: `{error}`"])
    lines.append("")
    return "\n".join(lines)


def run_authoritative_14c(
    *,
    confirm_execution_authorization: bool,
    run_label: str | None = None,
    repo_root: Path | None = None,
) -> Authoritative14CResult:
    """Execute the frozen 14C suite and persist an authoritative terminal run."""
    if not confirm_execution_authorization:
        raise Performance14Error(
            "refusing authoritative 14C execution without "
            "confirm_execution_authorization=True "
            f"({EXECUTION_AUTHORIZATION_STATEMENT_14C})"
        )

    plan = build_suite_plan_14c()
    # Authoritative campaign sets evidence-class flags on the in-memory plan only.
    # Frozen suite artifact gates remain execution_authorized=false.
    plan = replace(plan, diagnostic_only=False, authoritative=True)
    scientific_config_id = effective_config_id_14c()
    run_nonce = uuid.uuid4().hex
    suite_id = plan.suite.suite_identity_hash
    assert suite_id is not None

    try:
        preflight = run_authoritative_14c_preflight(plan, repo_root=repo_root)
    except Performance14Error as exc:
        record = getattr(exc, "preflight_record", None)
        partial = getattr(exc, "preflight_partial", None)
        if record is None:
            raise
        manifest = _failed_preflight_manifest(
            suite_id=suite_id,
            run_nonce=run_nonce,
            run_label=run_label,
            record=record,
            partial=partial,
            scientific_config_id=scientific_config_id,
        )
        run_id = manifest.run_identity_hash
        assert run_id is not None
        output_dir = allocate_authoritative_run_dir(
            suite_id=suite_id,
            run_id=run_id,
            repo_root=repo_root,
        )
        output_dir.mkdir(parents=True, exist_ok=False)
        aggregate = build_run_aggregate(
            suite_id=suite_id,
            run_id=run_id,
            run_status="failed_preflight",
            benchmark_level="B",
            cases=[],
            diagnostic_only=False,
            authoritative=True,
            evidence_class="AUTHORITATIVE",
            vram_availability="unavailable",
        )
        report = _render_authoritative_report(
            run_id=run_id,
            manifest=manifest,
            aggregate=aggregate,
            cases=[],
            error=str(exc),
        )
        write_run_artifacts(
            output_dir,
            manifest=manifest,
            aggregate=aggregate,
            cases=[],
            report_markdown=report,
            preflight=record,
        )
        return Authoritative14CResult(
            run_id=run_id,
            output_dir=output_dir,
            run_status="failed_preflight",
            suite_id=suite_id,
            scientific_config_id=scientific_config_id,
            manifest=manifest,
            aggregate=aggregate,
            cases=[],
            preflight=record,
            run_label=run_label,
            error=str(exc),
        )

    if preflight.scientific_config_id != scientific_config_id:
        raise Performance14Error("preflight scientific_config_id diverged from lock")

    manifest = _build_manifest(
        preflight=preflight,
        run_nonce=run_nonce,
        run_label=run_label,
        scientific_config_id=scientific_config_id,
    )
    run_id = manifest.run_identity_hash
    assert run_id is not None
    output_dir = allocate_authoritative_run_dir(
        suite_id=suite_id,
        run_id=run_id,
        repo_root=preflight.repo_root,
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    query_by_id = _build_query_map(preflight.repo_root)
    gold_by_id = _build_gold_map(preflight.repo_root)
    hybrid_cfg = plan.variant_configs[VARIANT_HYBRID]
    rerank_cfg = plan.variant_configs[VARIANT_HYBRID_RERANK]
    rerank_configuration = rerank_cfg["reranker_configuration"]
    if not isinstance(rerank_configuration, dict):
        raise Performance14Error("treatment reranker_configuration must be a mapping")
    hybrid = HybridRetriever(preflight.hybrid_settings)
    hybrid_rerank = HybridRerankRetriever(preflight.rerank_settings, hybrid=hybrid)
    engine = _14CStageEngine(
        hybrid=hybrid,
        hybrid_rerank=hybrid_rerank,
        query_by_id=query_by_id,
        fusion_output_top_k=int(hybrid_cfg["fusion_output_top_k"]),
        rerank_output_top_k=int(rerank_configuration["output_k"]),
    )
    cases: list[PerformanceBenchmarkCaseV1] = []
    run_status: RunStatusV1 = "completed"
    error: str | None = None
    try:
        engine.prepare_engines()
        ordered = _ordered_case_specs(plan)
        for spec in ordered:
            cases.append(
                _execute_14c_case(
                    spec,
                    engine=engine,
                    gold_by_id=gold_by_id,
                    warmup_count=plan.warmup_count,
                    measured_repetitions=plan.measured_repetitions,
                )
            )
        if any(case.case_status == "failed" for case in cases):
            run_status = "failed_during_execution"
            error = "one or more cases recorded failed measured observations"
        else:
            assert_paired_quality_coverage(
                cases,
                expected_query_ids=sorted(gold_by_id),
            )
    except Exception as exc:  # noqa: BLE001 — preserve partial run
        run_status = "failed_during_execution"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        engine.close()

    sealed_manifest = manifest.model_copy(update={"run_status": run_status})
    # run_status is excluded from perfrun_ identity; hash stays stable.
    quality_by_variant = macro_quality_by_variant(cases)
    resource_by_variant = resource_summary_by_variant(cases)
    path_latency = path_latency_rollups(cases)
    aggregate = build_run_aggregate(
        suite_id=suite_id,
        run_id=run_id,
        run_status=run_status,
        benchmark_level="B",
        cases=cases,
        diagnostic_only=False,
        authoritative=True,
        evidence_class="AUTHORITATIVE",
        path_latency=path_latency,
        quality_by_variant=quality_by_variant,
        resource_by_variant=resource_by_variant,
        vram_availability="unavailable",
    )
    report = _render_authoritative_report(
        run_id=run_id,
        manifest=sealed_manifest,
        aggregate=aggregate,
        cases=cases,
        error=error,
    )
    write_run_artifacts(
        output_dir,
        manifest=sealed_manifest,
        aggregate=aggregate,
        cases=cases,
        report_markdown=report,
        preflight=preflight.record,
    )
    return Authoritative14CResult(
        run_id=run_id,
        output_dir=output_dir,
        run_status=run_status,
        suite_id=suite_id,
        scientific_config_id=scientific_config_id,
        manifest=sealed_manifest,
        aggregate=aggregate,
        cases=cases,
        preflight=preflight.record,
        run_label=run_label,
        error=error,
    )


def main(argv: list[str] | None = None) -> int:
    del argv  # reserved for future CLI flags
    result = run_authoritative_14c(confirm_execution_authorization=True)
    print(
        f"status={result.run_status} run_id={result.run_id} output={result.output_dir}"
    )
    if result.error:
        print(f"error={result.error}")
    return 0 if result.run_status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
