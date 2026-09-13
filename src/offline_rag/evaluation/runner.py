"""Shared retrieval evaluation runner helpers (Slice 9)."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from offline_rag.core.ids import new_execution_id
from offline_rag.evaluation.gold import (
    DIAGNOSTIC_HIT_RATE_CUTOFF,
    GOLD_SCHEMA_V1,
    GoldCase,
    GoldDatasetError,
    LoadedGoldDataset,
    load_gold_dataset,
)
from offline_rag.evaluation.metrics import score_ranking
from offline_rag.evaluation.result import (
    CaseEvaluationResult,
    PopulationCounts,
    RetrievalEvaluationResultV1,
    RetrievalMethod,
    build_aggregate_metrics,
    build_category_aggregates,
    build_latency_summary,
    case_metrics_from_score,
    metric_config_for_depth,
)
from offline_rag.ingestion.io import atomic_write_text


class EvaluationError(RuntimeError):
    pass


RetrieveFn = Callable[[GoldCase], tuple[list[str], dict[str, Any]]]


def load_gold_or_raise(path: Path) -> LoadedGoldDataset:
    try:
        return load_gold_dataset(path)
    except GoldDatasetError as exc:
        raise EvaluationError(str(exc)) from exc


def run_retrieval_evaluation(
    *,
    dataset: LoadedGoldDataset,
    method: RetrievalMethod,
    run_prefix: str,
    requested_depth: int,
    retrieve_fn: RetrieveFn,
    warmup_query: str | None,
    semantic_provenance: dict[str, Any],
    corpus_id: str | None,
    corpus_name: str | None,
    metadata: dict[str, Any] | None = None,
    fail_on_empty_eligible: bool = True,
) -> RetrievalEvaluationResultV1:
    """Execute retrieve_fn per case and build a common v1 result artifact."""
    if fail_on_empty_eligible and dataset.quality_eligible_count == 0:
        raise EvaluationError(
            "Gold dataset contains no positive retrieval judgments; "
            "retrieval-quality evaluation cannot be computed"
        )

    started = datetime.now(tz=UTC)
    run_id = new_execution_id(prefix=run_prefix)
    hit30 = requested_depth >= DIAGNOSTIC_HIT_RATE_CUTOFF

    if warmup_query and dataset.cases:
        try:
            retrieve_fn(dataset.cases[0])
        except Exception:  # noqa: BLE001 - warmup is best-effort
            pass

    cases_out: list[CaseEvaluationResult] = []
    for case in dataset.cases:
        t0 = time.perf_counter()
        try:
            retrieved, diagnostics = retrieve_fn(case)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            score = score_ranking(
                case,
                retrieved,
                requested_depth=requested_depth,
                hit_rate_30_applicable=hit30,
            )
            cases_out.append(
                CaseEvaluationResult(
                    case_id=case.id,
                    query=case.query,
                    category=case.category,
                    tags=list(case.tags),
                    quality_eligible=case.quality_eligible,
                    positive_judgment_count=len(case.judgments),
                    grade_2_count=sum(1 for j in case.judgments if j.relevance == 2),
                    grade_1_count=sum(1 for j in case.judgments if j.relevance == 1),
                    relevant_chunk_ids=sorted(case.positive_chunk_ids()),
                    retrieved_chunk_ids=list(retrieved),
                    requested_depth=score.requested_depth,
                    returned_count=score.returned_count,
                    first_relevant_rank=score.first_relevant_rank,
                    metrics=case_metrics_from_score(score),
                    latency_ms=latency_ms,
                    diagnostics=dict(diagnostics),
                )
            )
        except Exception as exc:  # noqa: BLE001 - capture then fail closed
            latency_ms = int((time.perf_counter() - t0) * 1000)
            cases_out.append(
                CaseEvaluationResult(
                    case_id=case.id,
                    query=case.query,
                    category=case.category,
                    tags=list(case.tags),
                    quality_eligible=case.quality_eligible,
                    positive_judgment_count=len(case.judgments),
                    grade_2_count=sum(1 for j in case.judgments if j.relevance == 2),
                    grade_1_count=sum(1 for j in case.judgments if j.relevance == 1),
                    relevant_chunk_ids=sorted(case.positive_chunk_ids()),
                    requested_depth=requested_depth,
                    returned_count=0,
                    latency_ms=latency_ms,
                    error=str(exc),
                )
            )
            raise EvaluationError(str(exc)) from exc

    completed = datetime.now(tz=UTC)
    executed = [c for c in cases_out if c.error is None]
    eligible = [c for c in cases_out if c.quality_eligible]
    return RetrievalEvaluationResultV1(
        run_id=run_id,
        method=method,
        gold_schema_version=GOLD_SCHEMA_V1,
        gold_dataset_id=dataset.dataset_id,
        gold_source_schema=dataset.source_schema,
        gold_compatibility_mode=dataset.compatibility_mode,
        chunk_set_id=dataset.meta.chunk_set_id,
        corpus_id=corpus_id if corpus_id is not None else dataset.meta.corpus_id,
        corpus_name=corpus_name if corpus_name is not None else dataset.meta.corpus_name,
        semantic_provenance=dict(semantic_provenance),
        metric_config=metric_config_for_depth(requested_depth),
        population=PopulationCounts(
            total_cases=len(cases_out),
            executed_cases=len(executed),
            quality_eligible_cases=len(eligible),
        ),
        aggregates=build_aggregate_metrics(cases_out),
        category_aggregates=build_category_aggregates(cases_out),
        latency=build_latency_summary(cases_out),
        cases=cases_out,
        started_at=started,
        completed_at=completed,
        metadata=dict(metadata or {}),
    )


def persist_result(
    result: RetrievalEvaluationResultV1,
    *,
    eval_results_root: Path,
    subdirectory: str,
    output_path: Path | None,
) -> RetrievalEvaluationResultV1:
    if output_path is None:
        out_dir = Path(eval_results_root) / subdirectory
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{result.run_id}.json"
    else:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
    result = result.model_copy(
        update={"metadata": {**result.metadata, "result_path": str(out)}}
    )
    atomic_write_text(out, result.model_dump_json())
    return result
