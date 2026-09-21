"""GenerationSemanticEvaluator — Layer-1 + optional Layer-2 judge (Slice 10C)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from offline_rag.chunking.access import CorpusChunkSnapshot
from offline_rag.chunking.tokenize import FakeTokenCounter, TokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import new_execution_id
from offline_rag.core.network_policy import (
    NetworkPolicyError,
    normalize_openai_compatible_endpoint,
)
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
from offline_rag.evaluation.generation_semantic.hard_negative import (
    HardNegativeBuildError,
    build_human_grade0_hard_negative_set_v1,
)
from offline_rag.evaluation.generation_semantic.historical import (
    HistoricalChunkSetError,
    load_gold_historical_chunk_snapshot,
)
from offline_rag.evaluation.generation_semantic.judge_adapter import (
    OpenAICompatibleGenerationSemanticJudge,
)
from offline_rag.evaluation.generation_semantic.judge_config_hash import (
    build_judge_config_hash,
    build_judge_semantic_payload,
)
from offline_rag.evaluation.generation_semantic.judge_metrics import (
    build_semantic_aggregates,
    failed_judge_result,
    not_applicable_judge_result,
    unavailable_judge_result,
)
from offline_rag.evaluation.generation_semantic.judge_protocol import (
    GenerationSemanticJudge,
    GenerationSemanticJudgeError,
    make_judge_request,
)
from offline_rag.evaluation.generation_semantic.judge_readiness import (
    JudgePreflightKind,
    evaluate_judge_preflight,
)
from offline_rag.evaluation.generation_semantic.metrics import (
    build_abstention_aggregates,
    build_deterministic_aggregates,
    build_population,
    compute_case_deterministic_metrics,
)
from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_SEMANTIC_DETERMINISTIC_V1,
    HUMAN_GRADE0_HARD_NEGATIVE_V1,
    GenerationEvidenceSetV1,
    GenerationSemanticEvalCaseResultV1,
    GenerationSemanticEvalResultV1,
    GenerationSemanticJudgeCaseResultV1,
    GenerationSemanticJudgeProvenanceV1,
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
from offline_rag.generation.openai_compatible import normalize_endpoint
from offline_rag.generation.status import (
    describe_generation_provider_status,
    generation_provider_status,
)
from offline_rag.gold_authoring.persist import load_authoring_run


class GenerationSemanticEvaluationError(RuntimeError):
    """Fail-closed evaluator / infrastructure error."""


class GenerationSemanticEvaluator:
    """Execute fixed-evidence generation and optional Layer-2 semantic judging."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        executor: GroundedGenerationExecutor | None = None,
        judge: GenerationSemanticJudge | None = None,
    ) -> None:
        self.settings = settings
        self._executor = executor or GroundedGenerationExecutor(settings)
        self._owned_executor = executor is None
        self._judge = judge
        self._owned_judge = False

    def close(self) -> None:
        if self._owned_executor:
            self._executor.close()
        if self._owned_judge and self._judge is not None:
            self._judge.close()

    def evaluate(
        self,
        evidence_set: GenerationEvidenceSetV1,
        *,
        corpus_name: str | None = None,
        judge_requested: bool = False,
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

        judge_provenance: GenerationSemanticJudgeProvenanceV1 | None = None
        judge_available = False
        active_judge: GenerationSemanticJudge | None = None

        if judge_requested:
            if not self.settings.evaluation.generation_semantic_judge.enabled:
                raise GenerationSemanticEvaluationError(
                    "eval generation --judge requested but "
                    "evaluation.generation_semantic_judge.enabled is false"
                )
            preflight = evaluate_judge_preflight(self.settings)
            if preflight.kind == JudgePreflightKind.CONFIG_INVALID:
                raise GenerationSemanticEvaluationError(
                    "Generation semantic judge configuration is invalid.\n"
                    f"Reasons: {'; '.join(preflight.reasons)}"
                )
            judge_available = preflight.kind == JudgePreflightKind.READY
            judge_provenance = _build_judge_provenance(
                self.settings,
                judge_requested=True,
                judge_available=judge_available,
                preflight_status=preflight.status,
                preflight_kind=preflight.kind.value,
                preflight_reason=(
                    "; ".join(preflight.reasons) if preflight.reasons else None
                ),
            )
            if judge_available:
                if self._judge is None:
                    self._judge = OpenAICompatibleGenerationSemanticJudge(self.settings)
                    self._owned_judge = True
                active_judge = self._judge

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
            citation_ids = list(result.evidence_unit_ids_used)
            judge_result = _judge_case(
                case_status=result.status,
                judge_requested=judge_requested,
                judge_available=judge_available,
                judge=active_judge,
                query=case.query,
                evidence_units=list(case.evidence_units),
                answer_text=result.answer_text,
                citation_ids=citation_ids,
                source_name_by_document_id=frozen_sources,
            )
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
                    citation_ids=citation_ids,
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
                    judge_result=judge_result,
                    latency_ms=int(total_ms) if total_ms is not None else None,
                    generation_latency_ms=int(gen_ms) if gen_ms is not None else None,
                    metadata={},
                )
            )

        completed = datetime.now(tz=UTC)
        semantic_aggregates = (
            build_semantic_aggregates(case_rows) if judge_requested else None
        )
        expected_behavior = evidence_set.expected_behavior
        abstention_aggregates = (
            build_abstention_aggregates(case_rows)
            if expected_behavior == "abstain"
            else None
        )
        return GenerationSemanticEvalResultV1(
            run_id=run_id,
            gold_dataset_id=evidence_set.source_gold_dataset_id,
            evidence_set_id=evidence_set.evidence_set_id,
            evidence_contract=evidence_set.evidence_contract,
            expected_behavior=expected_behavior,
            semantic_metric_contract=GENERATION_SEMANTIC_DETERMINISTIC_V1,
            corpus_id=evidence_set.corpus_id,
            chunk_set_id=evidence_set.chunk_set_id,
            generation_config_hash=gencfg,
            generation_semantic_provenance=semantics,
            judge_enabled=judge_requested,
            judge_provenance=judge_provenance,
            population=build_population(case_rows),
            deterministic_aggregates=build_deterministic_aggregates(case_rows),
            semantic_aggregates=semantic_aggregates,
            abstention_aggregates=abstention_aggregates,
            cases=case_rows,
            started_at=started,
            completed_at=completed,
            metadata={},
        )


def _judge_case(
    *,
    case_status: str | None,
    judge_requested: bool,
    judge_available: bool,
    judge: GenerationSemanticJudge | None,
    query: str,
    evidence_units: list,
    answer_text: str | None,
    citation_ids: list[str],
    source_name_by_document_id: dict[str, str],
) -> GenerationSemanticJudgeCaseResultV1 | None:
    if not judge_requested:
        return None
    if case_status != "answered":
        return not_applicable_judge_result()
    if not judge_available or judge is None:
        return unavailable_judge_result()
    if answer_text is None or not str(answer_text).strip():
        return failed_judge_result("empty_response")
    try:
        response = judge.judge(
            make_judge_request(
                query=query,
                evidence_units=evidence_units,
                answer_text=answer_text,
                citation_ids=citation_ids,
                source_name_by_document_id=source_name_by_document_id,
            )
        )
    except GenerationSemanticJudgeError as exc:
        return failed_judge_result(exc.failure_reason)
    except Exception:  # noqa: BLE001 - never mutate Layer-1
        return failed_judge_result("provider_error")

    out = response.output
    return GenerationSemanticJudgeCaseResultV1(
        judge_status="succeeded",
        answer_correctness=out.answer_correctness,
        faithfulness=out.faithfulness,
        completeness=out.completeness,
        citation_coverage=out.citation_coverage,
        citation_usefulness=out.citation_usefulness,
        unsupported_claims=list(out.unsupported_claims),
        missing_key_points=list(out.missing_key_points),
        irrelevant_citation_ids=list(out.irrelevant_citation_ids),
        rationale=out.rationale,
        judge_latency_ms=response.latency_ms,
    )


def _build_judge_provenance(
    settings: AppSettings,
    *,
    judge_requested: bool,
    judge_available: bool,
    preflight_status: str,
    preflight_kind: str,
    preflight_reason: str | None,
) -> GenerationSemanticJudgeProvenanceV1:
    judge = settings.evaluation.generation_semantic_judge
    payload = build_judge_semantic_payload(settings)
    try:
        judge_endpoint = normalize_openai_compatible_endpoint(judge.base_url)
    except NetworkPolicyError:
        judge_endpoint = judge.base_url.strip()
    try:
        gen_endpoint = normalize_endpoint(settings.generation.base_url)
    except Exception:  # noqa: BLE001
        gen_endpoint = settings.generation.base_url.strip()
    return GenerationSemanticJudgeProvenanceV1(
        judge_requested=judge_requested,
        judge_available=judge_available,
        judge_config_hash=build_judge_config_hash(settings),
        provider=str(payload["provider"]),
        normalized_endpoint=judge_endpoint,
        model=judge.model,
        adapter_contract=str(payload["adapter_contract"]),
        prompt_contract=str(payload["prompt_contract"]),
        output_contract=str(payload["output_contract"]),
        reasoning_contract=str(payload["reasoning_contract"]),
        network_policy=judge.network_policy,
        same_model_self_judge=(
            judge.model is not None and judge.model == settings.generation.model
        ),
        same_endpoint_as_generator=(judge_endpoint == gen_endpoint),
        preflight_status=preflight_status,
        preflight_kind=preflight_kind,
        preflight_reason=preflight_reason,
    )


def run_generation_semantic_evaluation(
    settings: AppSettings,
    *,
    dataset_path: Path,
    cohort_map_path: Path,
    corpus_name: str = "default",
    evidence_mode: str = "gold",
    authoring_run_path: Path | None = None,
    evidence_output: Path | None = None,
    output: Path | None = None,
    executor: GroundedGenerationExecutor | None = None,
    judge: GenerationSemanticJudge | None = None,
    judge_requested: bool = False,
    chunk_snapshot: CorpusChunkSnapshot | None = None,
    token_counter: TokenCounter | None = None,
) -> GenerationSemanticEvalResultV1:
    """Full offline-rag eval generation pipeline (fail-closed; no partial publish)."""
    if evidence_mode not in ("gold", "human-hard-negative"):
        raise GenerationSemanticEvaluationError(
            f"unsupported evidence mode: {evidence_mode}"
        )
    if evidence_mode == "gold" and authoring_run_path is not None:
        raise GenerationSemanticEvaluationError(
            "--authoring-run is incompatible with --evidence-mode gold"
        )
    if evidence_mode == "human-hard-negative" and authoring_run_path is None:
        raise GenerationSemanticEvaluationError(
            "--authoring-run is required for --evidence-mode human-hard-negative"
        )
    if judge_requested and not settings.evaluation.generation_semantic_judge.enabled:
        raise GenerationSemanticEvaluationError(
            "eval generation --judge requested but "
            "evaluation.generation_semantic_judge.enabled is false"
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
        if evidence_mode == "gold":
            evidence_set = build_gold_evidence_set_v1(
                gold,
                chunk_snapshot=snapshot,
                label_cohort_by_case_id=cohorts,
                max_evidence_tokens=max_tokens,
                token_counter=token_counter or FakeTokenCounter(),
            )
            if evidence_set.evidence_contract != GOLD_EVIDENCE_V1:
                raise GenerationSemanticEvaluationError(
                    f"unexpected evidence_contract: {evidence_set.evidence_contract}"
                )
        else:
            assert authoring_run_path is not None
            try:
                authoring_run = load_authoring_run(Path(authoring_run_path))
            except Exception as exc:
                raise GenerationSemanticEvaluationError(
                    f"failed to load authoring run: {exc}"
                ) from exc
            evidence_set = build_human_grade0_hard_negative_set_v1(
                gold,
                authoring_run=authoring_run,
                chunk_snapshot=snapshot,
                label_cohort_by_case_id=cohorts,
                max_evidence_tokens=max_tokens,
                token_counter=token_counter or FakeTokenCounter(),
            )
            if evidence_set.evidence_contract != HUMAN_GRADE0_HARD_NEGATIVE_V1:
                raise GenerationSemanticEvaluationError(
                    f"unexpected evidence_contract: {evidence_set.evidence_contract}"
                )
    except (GoldEvidenceBuildError, HardNegativeBuildError) as exc:
        raise GenerationSemanticEvaluationError(str(exc)) from exc

    evidence_path = (
        Path(evidence_output)
        if evidence_output is not None
        else default_evidence_artifact_path(
            Path(settings.paths.eval_results), evidence_set.evidence_set_id
        )
    )
    try:
        persist_evidence_set(evidence_set, path=evidence_path)
    except GenerationSemanticPersistenceError as exc:
        raise GenerationSemanticEvaluationError(str(exc)) from exc

    evaluator = GenerationSemanticEvaluator(settings, executor=executor, judge=judge)
    try:
        result = evaluator.evaluate(
            evidence_set,
            corpus_name=corpus_name,
            judge_requested=judge_requested,
        )
    finally:
        evaluator.close()

    result_path = (
        Path(output)
        if output is not None
        else default_result_artifact_path(
            Path(settings.paths.eval_results), result.run_id
        )
    )
    result.metadata = {
        **dict(result.metadata),
        "evidence_path": str(evidence_path),
        "result_path": str(result_path),
        "evidence_mode": evidence_mode,
        "judge_requested": judge_requested,
    }
    if authoring_run_path is not None:
        result.metadata["authoring_run_path"] = str(authoring_run_path)
    try:
        persist_eval_result(result, path=result_path)
    except GenerationSemanticPersistenceError as exc:
        raise GenerationSemanticEvaluationError(str(exc)) from exc
    return result
