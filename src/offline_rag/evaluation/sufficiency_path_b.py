"""OD-11-5 Path-B measure-once sufficiency observation capture.

Captures gold-free ``suffctx_`` / ``suffctxrun_`` artifacts via one coherent
hybrid-rerank-context attempt per frozen case. No labeling, thresholds,
retries, recovery, or generation.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.config.loader import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.context.sufficiency_adapter import (
    SufficiencyAdapterError,
    adapt_hybrid_rerank_context_to_provenance,
)
from offline_rag.domain.indexing import HybridRerankContextResult
from offline_rag.evaluation.gold import LoadedGoldDataset, load_gold_dataset
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.sufficiency import (
    SUFFICIENCY_OBSERVATION_V1,
    SufficiencyArtifactError,
    SufficiencyDerivationError,
    SufficiencyError,
    SufficiencyErrorCodeV1,
    SufficiencyEvalContextManifestV1,
    SufficiencyEvalContextSnapshotV1,
    SufficiencyFailureRecordV1,
    SufficiencyManifestAuditV1,
    SufficiencySharedLineageV1,
    SufficiencySnapshotAuditV1,
    build_failure_record,
    build_sufficiency_manifest,
    build_sufficiency_snapshot,
    default_manifest_artifact_path,
    default_snapshot_artifact_path,
    persist_sufficiency_manifest,
    persist_sufficiency_snapshot,
)
from offline_rag.sufficiency.config_hash import authoritative_observation_config_hash
from offline_rag.sufficiency.contracts import ExactNonBlankStr


class PathBMeasureOnceError(RuntimeError):
    """Fail-closed Path-B orchestration error (before/around the run)."""


@dataclass(frozen=True, slots=True)
class FrozenCaseBinding:
    """Gold-free case/query binding used to drive measure-once execution."""

    case_id: str
    original_query: str


class PathBCaptureSummaryV1(BaseModel):
    """Gold-free observation capture diagnostics (not threshold selection)."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["sufficiency-path-b-capture-summary-v1"] = (
        "sufficiency-path-b-capture-summary-v1"
    )
    empty_context_count: int = 0
    anchor_count_min: int | None = None
    anchor_count_median: float | None = None
    anchor_count_max: int | None = None
    evidence_unit_count_min: int | None = None
    evidence_unit_count_median: float | None = None
    evidence_unit_count_max: int | None = None
    top_reranker_score_min: float | None = None
    top_reranker_score_median: float | None = None
    top_reranker_score_max: float | None = None
    top1_top2_margin_min: float | None = None
    top1_top2_margin_median: float | None = None
    top1_top2_margin_max: float | None = None
    cross_retriever_support_true: int = 0
    cross_retriever_support_false: int = 0
    cross_retriever_support_null: int = 0
    distinct_document_count_distribution: dict[str, int] = Field(default_factory=dict)
    distinct_section_count_distribution: dict[str, int] = Field(default_factory=dict)
    clipping_count: int = 0
    budget_exhausted_count: int = 0
    stop_reason_counts: dict[str, int] = Field(default_factory=dict)


class PathBMeasureOnceReportV1(BaseModel):
    """Deterministic Path-B run report for independent review."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["sufficiency-path-b-measure-once-report-v1"] = (
        "sufficiency-path-b-measure-once-report-v1"
    )
    corpus_name: ExactNonBlankStr
    population_source_dataset_id: ExactNonBlankStr | None = None
    intended_case_ids: list[ExactNonBlankStr]
    intended_case_queries: dict[str, str]
    suffctxrun_id: ExactNonBlankStr
    expected_case_count: int
    successful_case_count: int
    failed_case_count: int
    authoritative_for_11b: bool
    case_to_suffctx_id: dict[str, str] = Field(default_factory=dict)
    shared_lineage: dict[str, str] | None = None
    snapshot_paths: dict[str, str] = Field(default_factory=dict)
    manifest_path: ExactNonBlankStr
    summary_path: ExactNonBlankStr
    report_path: ExactNonBlankStr
    capture_summary: PathBCaptureSummaryV1
    failure_case_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class PathBMeasureOnceResult:
    report: PathBMeasureOnceReportV1
    manifest: SufficiencyEvalContextManifestV1
    snapshots: list[SufficiencyEvalContextSnapshotV1] = field(default_factory=list)
    failures: list[SufficiencyFailureRecordV1] = field(default_factory=list)


def load_frozen_case_bindings(
    dataset_path: Path,
) -> tuple[
    list[FrozenCaseBinding],
    str,
]:
    """Load only case_id/query bindings from the frozen GoldDataset.

    Gold judgments/labels are intentionally not returned.
    """
    gold = load_gold_dataset(Path(dataset_path))
    return frozen_bindings_from_gold(gold), gold.dataset_id


def frozen_bindings_from_gold(gold: LoadedGoldDataset) -> list[FrozenCaseBinding]:
    bindings = [
        FrozenCaseBinding(case_id=case.id, original_query=case.query)
        for case in gold.cases
    ]
    validate_frozen_case_bindings(bindings)
    return bindings


def validate_frozen_case_bindings(
    bindings: Sequence[FrozenCaseBinding],
) -> dict[str, str]:
    """Require unique nonblank case_id → exact original_query mapping."""
    if not bindings:
        raise PathBMeasureOnceError("frozen population must be non-empty")
    mapping: dict[str, str] = {}
    for item in bindings:
        if not isinstance(item.case_id, str) or item.case_id == "":
            raise PathBMeasureOnceError("frozen case_id must be a non-empty string")
        if item.case_id.strip() == "":
            raise PathBMeasureOnceError("frozen case_id must not be whitespace-only")
        if not isinstance(item.original_query, str) or item.original_query == "":
            raise PathBMeasureOnceError(
                f"frozen original_query for case_id={item.case_id!r} must be non-empty"
            )
        if item.case_id in mapping:
            raise PathBMeasureOnceError(f"duplicate frozen case_id: {item.case_id}")
        mapping[item.case_id] = item.original_query
    return mapping


def _lineage_from_context_result(
    result: HybridRerankContextResult,
) -> SufficiencySharedLineageV1:
    metadata = dict(result.metadata or {})
    corpus_id = metadata.get("corpus_id")
    chunk_set_id = metadata.get("chunk_set_id")
    if not isinstance(corpus_id, str) or corpus_id == "":
        raise PathBMeasureOnceError(
            "assembled context result missing metadata.corpus_id for shared lineage"
        )
    if not isinstance(chunk_set_id, str) or chunk_set_id == "":
        raise PathBMeasureOnceError(
            "assembled context result missing metadata.chunk_set_id for shared lineage"
        )
    return SufficiencySharedLineageV1(
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        dense_index_id=result.dense_index_id,
        lexical_index_id=result.lexical_index_id,
        fusion_config_hash=result.fusion_config_hash,
        reranker_config_hash=result.reranker_config_hash,
        context_config_hash=result.context_config_hash,
        observation_contract=SUFFICIENCY_OBSERVATION_V1,
        observation_config_hash=authoritative_observation_config_hash(),
    )


def _wrap_case_error(exc: BaseException) -> SufficiencyError | SufficiencyArtifactError:
    if isinstance(exc, (SufficiencyError, SufficiencyArtifactError)):
        return exc
    return SufficiencyDerivationError(
        SufficiencyErrorCodeV1.MISSING_REQUIRED_PROVENANCE,
        f"path-b measure-once case failure: {exc}",
    )


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def build_path_b_capture_summary(
    snapshots: Sequence[SufficiencyEvalContextSnapshotV1],
) -> PathBCaptureSummaryV1:
    if not snapshots:
        return PathBCaptureSummaryV1()

    empty = 0
    anchors: list[float] = []
    units: list[float] = []
    top_scores: list[float] = []
    margins: list[float] = []
    cross_true = cross_false = cross_null = 0
    doc_dist: Counter[str] = Counter()
    sec_dist: Counter[str] = Counter()
    clipping = 0
    budget = 0
    stop_reasons: Counter[str] = Counter()

    for snap in snapshots:
        obs = snap.observation
        diag = snap.provenance.diagnostics
        if obs.empty_context:
            empty += 1
        anchors.append(float(obs.anchor_count))
        units.append(float(diag.evidence_unit_count))
        if obs.top_reranker_score is not None:
            top_scores.append(float(obs.top_reranker_score))
        if obs.top1_top2_margin is not None:
            margins.append(float(obs.top1_top2_margin))
        if obs.top_anchor_cross_retriever_support is True:
            cross_true += 1
        elif obs.top_anchor_cross_retriever_support is False:
            cross_false += 1
        else:
            cross_null += 1
        doc_dist[str(obs.distinct_document_count)] += 1
        sec_dist[str(obs.distinct_section_count)] += 1
        if diag.clipping_occurred:
            clipping += 1
        if diag.budget_exhausted:
            budget += 1
        stop_reasons[diag.stop_reason] += 1

    return PathBCaptureSummaryV1(
        empty_context_count=empty,
        anchor_count_min=int(min(anchors)) if anchors else None,
        anchor_count_median=_median(anchors),
        anchor_count_max=int(max(anchors)) if anchors else None,
        evidence_unit_count_min=int(min(units)) if units else None,
        evidence_unit_count_median=_median(units),
        evidence_unit_count_max=int(max(units)) if units else None,
        top_reranker_score_min=min(top_scores) if top_scores else None,
        top_reranker_score_median=_median(top_scores),
        top_reranker_score_max=max(top_scores) if top_scores else None,
        top1_top2_margin_min=min(margins) if margins else None,
        top1_top2_margin_median=_median(margins),
        top1_top2_margin_max=max(margins) if margins else None,
        cross_retriever_support_true=cross_true,
        cross_retriever_support_false=cross_false,
        cross_retriever_support_null=cross_null,
        distinct_document_count_distribution=dict(sorted(doc_dist.items())),
        distinct_section_count_distribution=dict(sorted(sec_dist.items())),
        clipping_count=clipping,
        budget_exhausted_count=budget,
        stop_reason_counts=dict(sorted(stop_reasons.items())),
    )


def run_path_b_measure_once(
    *,
    settings: AppSettings,
    bindings: Sequence[FrozenCaseBinding],
    corpus_name: str,
    artifacts_root: Path,
    assembler: HybridRerankContextAssembler | None = None,
    population_source_dataset_id: str | None = None,
) -> PathBMeasureOnceResult:
    """Execute one hybrid-rerank-context attempt per frozen case; persist artifacts.

    Never retries a failed case. Never mixes historical values. Never writes Gold
    truth into sufficiency artifacts.
    """
    intended = validate_frozen_case_bindings(bindings)
    ordered_bindings = list(bindings)
    out_root = Path(artifacts_root)
    out_root.mkdir(parents=True, exist_ok=True)

    owned_assembler = assembler is None
    active = assembler or HybridRerankContextAssembler(settings)
    snapshots: list[SufficiencyEvalContextSnapshotV1] = []
    failures: list[SufficiencyFailureRecordV1] = []
    snapshot_paths: dict[str, str] = {}
    case_to_suffctx: dict[str, str] = {}
    observed_lineage: SufficiencySharedLineageV1 | None = None
    notes: list[str] = [
        "path-b measure-once: one assembler call per intended case; no retries",
        "gold judgments/labels are excluded from sufficiency artifact payloads",
    ]

    try:
        for binding in ordered_bindings:
            case_id = binding.case_id
            query = binding.original_query
            if intended[case_id] != query:
                raise PathBMeasureOnceError(
                    f"internal binding mismatch for case_id={case_id!r}"
                )
            stage = "assemble"
            try:
                context_result = active.assemble(query=query, corpus_name=corpus_name)
                lineage_sample = _lineage_from_context_result(context_result)
                if observed_lineage is None:
                    observed_lineage = lineage_sample
                elif observed_lineage.model_dump(
                    mode="json"
                ) != lineage_sample.model_dump(mode="json"):
                    raise PathBMeasureOnceError(
                        "mixed shared lineage across path-b measure-once cases"
                    )
                if context_result.query != query:
                    raise SufficiencyAdapterError(
                        SufficiencyErrorCodeV1.INVALID_QUERY_FIELDS,
                        "assembler query does not exactly equal frozen original_query",
                    )
                stage = "adapt"
                provenance = adapt_hybrid_rerank_context_to_provenance(
                    context_result, case_id=case_id
                )
                if (
                    provenance.case_id != case_id
                    or provenance.original_query != query
                    or provenance.active_retrieval_query != query
                ):
                    raise SufficiencyAdapterError(
                        SufficiencyErrorCodeV1.INVALID_QUERY_FIELDS,
                        "adapted provenance case/query binding mismatch",
                    )
                stage = "snapshot"
                snapshot = build_sufficiency_snapshot(
                    provenance,
                    audit=SufficiencySnapshotAuditV1(
                        created_at=datetime.now(tz=UTC),
                    ),
                )
                stage = "persist"
                snap_path = default_snapshot_artifact_path(
                    out_root, snapshot.suffctx_id
                )
                persist_sufficiency_snapshot(snapshot, path=snap_path)
                snapshots.append(snapshot)
                snapshot_paths[case_id] = str(snap_path)
                case_to_suffctx[case_id] = snapshot.suffctx_id
            except PathBMeasureOnceError:
                raise
            except Exception as exc:  # noqa: BLE001 - per-case fail-closed, no retry
                error = _wrap_case_error(exc)
                failures.append(
                    build_failure_record(
                        case_id=case_id,
                        failure_stage=stage,
                        error=error,
                        original_query=query,
                    )
                )
                notes.append(
                    f"case_id={case_id} failed at stage={stage}: {error.message}"
                )
    finally:
        if owned_assembler:
            active.close()

    try:
        manifest = build_sufficiency_manifest(
            snapshots=snapshots,
            failures=failures,
            expected_case_ids=list(intended.keys()),
            shared_lineage=None if snapshots else observed_lineage,
            audit=SufficiencyManifestAuditV1(
                created_at=datetime.now(tz=UTC),
                output_path=str(out_root),
            ),
        )
    except SufficiencyArtifactError as exc:
        raise PathBMeasureOnceError(
            f"manifest construction failed (mixed lineage or invalid run): {exc}"
        ) from exc

    manifest_path = default_manifest_artifact_path(out_root, manifest.suffctxrun_id)
    persist_sufficiency_manifest(manifest, path=manifest_path)

    summary = build_path_b_capture_summary(snapshots)
    summary_path = out_root / f"{manifest.suffctxrun_id}.capture_summary.json"
    atomic_write_text(summary_path, summary.model_dump_json())
    report_path = out_root / f"{manifest.suffctxrun_id}.measure_once_report.json"

    shared_lineage = {
        "corpus_id": manifest.shared_lineage.corpus_id,
        "chunk_set_id": manifest.shared_lineage.chunk_set_id,
        "dense_index_id": manifest.shared_lineage.dense_index_id,
        "lexical_index_id": manifest.shared_lineage.lexical_index_id,
        "fusion_config_hash": manifest.shared_lineage.fusion_config_hash,
        "reranker_config_hash": manifest.shared_lineage.reranker_config_hash,
        "context_config_hash": manifest.shared_lineage.context_config_hash,
        "observation_contract": manifest.shared_lineage.observation_contract,
        "observation_config_hash": manifest.shared_lineage.observation_config_hash,
    }

    if not manifest.authoritative_for_11b:
        notes.append(
            "authoritative_for_11b=false: incomplete coverage or failures present; "
            "do not patch with additional runs"
        )
    else:
        notes.append("authoritative_for_11b=true: 100% successful coherent coverage")

    report = PathBMeasureOnceReportV1(
        corpus_name=corpus_name,
        population_source_dataset_id=population_source_dataset_id,
        intended_case_ids=list(intended.keys()),
        intended_case_queries=dict(intended),
        suffctxrun_id=manifest.suffctxrun_id,
        expected_case_count=manifest.expected_case_count,
        successful_case_count=manifest.successful_case_count,
        failed_case_count=manifest.failed_case_count,
        authoritative_for_11b=manifest.authoritative_for_11b,
        case_to_suffctx_id=case_to_suffctx,
        shared_lineage=shared_lineage,
        snapshot_paths=snapshot_paths,
        manifest_path=str(manifest_path),
        summary_path=str(summary_path),
        report_path=str(report_path),
        capture_summary=summary,
        failure_case_ids=[item.case_id for item in failures],
        notes=notes,
    )
    atomic_write_text(report_path, report.model_dump_json())

    return PathBMeasureOnceResult(
        report=report,
        manifest=manifest,
        snapshots=snapshots,
        failures=failures,
    )


DEFAULT_FROZEN_DATASET = Path(
    "data/corpora/ics_modules/gold_authoring/gold/"
    "authorrun_b28d88f64054491a837cb4a144cbe056"
)
DEFAULT_CORPUS_NAME = "ics_modules"


def main(argv: Sequence[str] | None = None) -> int:
    """Thin internal entry point for the authorized local Path-B run."""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Path-B measure-once sufficiency observation capture "
            "(internal; not a general user CLI)."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_FROZEN_DATASET,
        help="Frozen GoldDataset directory used only for case_id/query membership",
    )
    parser.add_argument("--corpus", default=DEFAULT_CORPUS_NAME)
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=None,
        help="Output root for suffctx_/suffctxrun_ artifacts",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    settings = load_settings()
    bindings, dataset_id = load_frozen_case_bindings(args.dataset)
    if len(bindings) != 22:
        raise PathBMeasureOnceError(
            f"expected frozen full-22 population, found {len(bindings)} cases"
        )

    artifacts_root = args.artifacts_root
    if artifacts_root is None:
        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        artifacts_root = (
            Path(settings.paths.eval_results) / "sufficiency" / f"path_b_{stamp}"
        )

    result = run_path_b_measure_once(
        settings=settings,
        bindings=bindings,
        corpus_name=args.corpus,
        artifacts_root=artifacts_root,
        population_source_dataset_id=dataset_id,
    )
    report = result.report
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0 if report.authoritative_for_11b else 2


if __name__ == "__main__":
    raise SystemExit(main())
