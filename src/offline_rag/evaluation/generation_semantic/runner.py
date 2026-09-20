"""GenerationSemanticEvaluator — Layer-1 fixed-evidence evaluation (Slice 10B)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from offline_rag.chunking.access import CorpusChunkSnapshot
from offline_rag.chunking.tokenize import FakeTokenCounter, TokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import new_execution_id
from offline_rag.evaluation.generation_semantic.cohort import (
    CohortMapError,
    load_cohort_map,
    validate_cohort_map_for_gold,
)
from offline_rag.evaluation.generation_semantic.evidence import (
    GOLD_EVIDENCE_V1,
    GoldEvidenceBuildError,
    build_gold_evidence_set_v1,
)
from offline_rag.evaluation.generation_semantic.historical import (
    HistoricalChunkSetError,
    load_gold_historical_chunk_snapshot,
)
from offline_rag.evaluation.generation_semantic.metrics import (
    build_deterministic_aggregates,
    build_population,
    compute_case_deterministic_metrics,
)
from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_SEMANTIC_DETERMINISTIC_V1,
    GenerationEvidenceSetV1,
    GenerationSemanticEvalCaseResultV1,
    GenerationSemanticEvalResultV1,
)
from offline_rag.evaluation.generation_semantic.persistence import (
    GenerationSemanticPersistenceError,
    default_evidence_artifact_path,
    default_result_artifact_path,
    persist_eval_result,
    persist_evidence_set,
)
from offline_rag.evaluation.gold import GoldDatasetError, load_gold_dataset
from offline_rag.generation.config_hash import (
    build_generation_config_hash,
    build_generation_semantic_payload,
)
from offline_rag.generation.executor import (
    GroundedGenerationError,
    GroundedGenerationExecutor,
)
from offline_rag.generation.status import (
    describe_generation_provider_status,
    generation_provider_status,
)


class GenerationSemanticEvaluationError(RuntimeError):
    """Fail-closed evaluator / infrastructure error."""


class GenerationSemanticEvaluator:
    """Execute fixed-evidence generation and Layer-1 deterministic diagnostics."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        executor: GroundedGenerationExecutor | None = None,
    ) -> None:
        self.settings = settings
        self._executor = executor or GroundedGenerationExecutor(settings)
        self._owned_executor = executor is None

    def close(self) -> None:
        if self._owned_executor:
            self._executor.close()

    def evaluate(
        self,
        evidence_set: GenerationEvidenceSetV1,
        *,
        corpus_name: str | None = None,
    ) -> GenerationSemanticEvalResultV1:
        name = corpus_name or evidence_set.corpus_name
        if generation_provider_status(self.settings) != "READY":
            details = describe_generation_provider_status(self.settings)
            reasons = details.get("reasons") or []
            reason_text = (
                "; ".join(str(item) for item in reasons) if reasons else "unknown"
            )
            raise GenerationSemanticEvaluationError(
                "Generation provider unavailable for eval generation.\n"
                f"Provider status: {details.get('status')}\n"
                f"Reasons:         {reason_text}"
            )

        started = datetime.now(tz=UTC)
        run_id = new_execution_id(prefix="genesem")
        gencfg = build_generation_config_hash(self.settings)
        semantics = build_generation_semantic_payload(self.settings)
        frozen_sources = dict(evidence_set.source_name_by_document_id)

        case_rows: list[GenerationSemanticEvalCaseResultV1] = []
        for case in evidence_set.cases:
            try:
                result = self._executor.execute(
                    query=case.query,
                    corpus_name=name,
                    evidence_units=list(case.evidence_units),
                    check_ready=False,
                    provider_only_ready=True,
                    source_name_by_document_id=frozen_sources,
                )
            except GroundedGenerationError as exc:
                raise GenerationSemanticEvaluationError(str(exc)) from exc
            except Exception as exc:
                raise GenerationSemanticEvaluationError(
                    f"unexpected generation failure for case {case.case_id}: {exc}"
                ) from exc

            latency = (result.diagnostics or {}).get("latency_ms") or {}
            total_ms = latency.get("total")
            gen_ms = latency.get("generation")
            metrics = compute_case_deterministic_metrics(case, result)
            case_rows.append(
                GenerationSemanticEvalCaseResultV1(
                    case_id=case.case_id,
                    query=case.query,
                    label_cohort=case.label_cohort,
                    category=case.category,
                    tags=list(case.tags),
                    status=result.status,
                    abstention_reason=result.abstention_reason,
                    generation_failure_reason=result.generation_failure_reason,
                    answer_text=result.answer_text,
                    citation_ids=list(result.evidence_unit_ids_used),
                    resolved_citation_source_chunk_ids=[
                        citation.source_chunk_id for citation in result.citations
                    ],
                    generator_invoked=result.generator_invoked,
                    attempt_count=result.attempt_count,
                    generation_config_hash=result.generation_config_hash,
                    prompt_contract=str(
                        (result.effective_generation_semantics or {}).get(
                            "prompt_contract"
                        )
                        or semantics.get("prompt_contract")
                    ),
                    deterministic_metrics=metrics,
                    latency_ms=int(total_ms) if total_ms is not None else None,
                    generation_latency_ms=int(gen_ms) if gen_ms is not None else None,
                    metadata={},
                )
            )

        completed = datetime.now(tz=UTC)
        return GenerationSemanticEvalResultV1(
            run_id=run_id,
            gold_dataset_id=evidence_set.source_gold_dataset_id,
            evidence_set_id=evidence_set.evidence_set_id,
            evidence_contract=evidence_set.evidence_contract,
            semantic_metric_contract=GENERATION_SEMANTIC_DETERMINISTIC_V1,
            corpus_id=evidence_set.corpus_id,
            chunk_set_id=evidence_set.chunk_set_id,
            generation_config_hash=gencfg,
            generation_semantic_provenance=semantics,
            judge_enabled=False,
            judge_provenance=None,
            population=build_population(case_rows),
            deterministic_aggregates=build_deterministic_aggregates(case_rows),
            semantic_aggregates=None,
            abstention_aggregates=None,
            cases=case_rows,
            started_at=started,
            completed_at=completed,
            metadata={},
        )


def run_generation_semantic_evaluation(
    settings: AppSettings,
    *,
    dataset_path: Path,
    cohort_map_path: Path,
    corpus_name: str = "default",
    evidence_mode: str = "gold",
    evidence_output: Path | None = None,
    output: Path | None = None,
    executor: GroundedGenerationExecutor | None = None,
    chunk_snapshot: CorpusChunkSnapshot | None = None,
    token_counter: TokenCounter | None = None,
) -> GenerationSemanticEvalResultV1:
    """Full offline-rag eval generation pipeline (fail-closed; no partial publish)."""
    if evidence_mode != "gold":
        raise GenerationSemanticEvaluationError(
            f"unsupported evidence mode for Slice 10B: {evidence_mode}"
        )

    try:
        gold = load_gold_dataset(Path(dataset_path))
    except GoldDatasetError as exc:
        raise GenerationSemanticEvaluationError(str(exc)) from exc

    try:
        cohort_map = load_cohort_map(Path(cohort_map_path))
        cohorts = validate_cohort_map_for_gold(cohort_map, gold)
    except CohortMapError as exc:
        raise GenerationSemanticEvaluationError(str(exc)) from exc

    if chunk_snapshot is None:
        try:
            snapshot = load_gold_historical_chunk_snapshot(
                settings, gold, corpus_name=corpus_name
            )
        except HistoricalChunkSetError as exc:
            raise GenerationSemanticEvaluationError(str(exc)) from exc
    else:
        snapshot = chunk_snapshot

    max_tokens = int(settings.context.max_context_tokens)
    try:
        evidence_set = build_gold_evidence_set_v1(
            gold,
            chunk_snapshot=snapshot,
            label_cohort_by_case_id=cohorts,
            max_evidence_tokens=max_tokens,
            token_counter=token_counter or FakeTokenCounter(),
        )
    except GoldEvidenceBuildError as exc:
        raise GenerationSemanticEvaluationError(str(exc)) from exc

    if evidence_set.evidence_contract != GOLD_EVIDENCE_V1:
        raise GenerationSemanticEvaluationError(
            f"unexpected evidence_contract: {evidence_set.evidence_contract}"
        )

    evidence_path = (
        Path(evidence_output)
        if evidence_output is not None
        else (
            default_evidence_artifact_path(
                Path(settings.paths.eval_results), evidence_set.evidence_set_id
            )
        )
    )
    try:
        persist_evidence_set(evidence_set, path=evidence_path)
    except GenerationSemanticPersistenceError as exc:
        raise GenerationSemanticEvaluationError(str(exc)) from exc

    evaluator = GenerationSemanticEvaluator(settings, executor=executor)
    try:
        result = evaluator.evaluate(evidence_set, corpus_name=corpus_name)
    finally:
        evaluator.close()

    result_path = (
        Path(output)
        if output is not None
        else (
            default_result_artifact_path(
                Path(settings.paths.eval_results), result.run_id
            )
        )
    )
    result.metadata = {
        **dict(result.metadata),
        "evidence_path": str(evidence_path),
        "result_path": str(result_path),
        "evidence_mode": evidence_mode,
    }
    try:
        persist_eval_result(result, path=result_path)
    except GenerationSemanticPersistenceError as exc:
        raise GenerationSemanticEvaluationError(str(exc)) from exc
    return result
