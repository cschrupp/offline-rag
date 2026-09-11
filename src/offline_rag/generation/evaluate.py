"""Thin Slice 8 query evaluation — operational outcomes only."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import dataset_id_from_bytes, new_execution_id
from offline_rag.dense.evaluate import EvaluationError, load_retrieval_dataset
from offline_rag.domain.generation import (
    QueryEvaluationOutcomes,
    QueryEvaluationResult,
)
from offline_rag.generation.config_hash import build_generation_config_hash
from offline_rag.generation.orchestrate import GroundedAnswerOrchestrator
from offline_rag.generation.status import (
    describe_generation_status,
    generation_status_for_corpus,
)
from offline_rag.ingestion.io import atomic_write_text


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = low if low == len(ordered) - 1 else low + 1
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


class QueryEvaluator:
    """Evaluate grounded query outcomes via GroundedAnswerOrchestrator."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        orchestrator: GroundedAnswerOrchestrator | None = None,
    ) -> None:
        self.settings = settings
        self.orchestrator = orchestrator or GroundedAnswerOrchestrator(settings)

    def evaluate(
        self,
        dataset_path: Path,
        *,
        corpus_name: str = "default",
        output_path: Path | None = None,
        persist: bool = True,
    ) -> QueryEvaluationResult:
        started = datetime.now(tz=UTC)
        run_id = new_execution_id(prefix="evalquery")
        meta, cases, canonical = load_retrieval_dataset(Path(dataset_path))
        dataset_id = dataset_id_from_bytes(canonical)
        gencfg = build_generation_config_hash(self.settings)

        status = generation_status_for_corpus(self.settings, corpus_name)
        if status != "READY":
            details = describe_generation_status(self.settings, corpus_name)
            reasons = details.get("reasons") or []
            reason_text = "; ".join(str(item) for item in reasons) if reasons else "unknown"
            raise EvaluationError(
                "Generation unavailable for eval query.\n"
                f"Generation status: {details.get('status')}\n"
                f"Context status:    {details.get('context_status')}\n"
                f"Reasons:           {reason_text}"
            )

        outcomes = QueryEvaluationOutcomes()
        case_rows: list[dict] = []
        latencies: list[float] = []
        gen_latencies: list[float] = []
        invoked = 0
        not_invoked = 0
        attempts = 0
        dense_index_id = None
        lexical_index_id = None
        chunk_set_id = meta.chunk_set_id
        corpus_id = meta.corpus_id
        fusion_hash = None
        rerank_hash = None
        context_hash = None

        for case in cases:
            t0 = time.perf_counter()
            try:
                result = self.orchestrator.answer(query=case.query, corpus_name=corpus_name)
            except Exception as exc:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                case_rows.append(
                    {
                        "case_id": case.id,
                        "query": case.query,
                        "error": str(exc),
                        "latency_ms": latency_ms,
                    }
                )
                raise EvaluationError(str(exc)) from exc

            latency_ms = int((time.perf_counter() - t0) * 1000)
            latencies.append(float(latency_ms))
            dense_index_id = result.dense_index_id
            lexical_index_id = result.lexical_index_id
            fusion_hash = result.fusion_config_hash
            rerank_hash = result.reranker_config_hash
            context_hash = result.context_config_hash
            chunk_set_id = str(result.metadata.get("chunk_set_id") or chunk_set_id)

            if result.generator_invoked:
                invoked += 1
                attempts += int(result.attempt_count)
                gen_ms = (result.diagnostics.get("latency_ms") or {}).get("generation")
                if isinstance(gen_ms, (int, float)):
                    gen_latencies.append(float(gen_ms))
            else:
                not_invoked += 1

            if result.status == "answered":
                outcomes.answered += 1
            elif result.status == "insufficient_evidence":
                outcomes.insufficient_evidence += 1
                if result.abstention_reason == "empty_context":
                    outcomes.empty_context += 1
                elif result.abstention_reason == "model_abstain":
                    outcomes.model_abstain += 1
            elif result.status == "generation_failed":
                outcomes.generation_failed += 1
            elif result.status == "citation_invalid":
                outcomes.citation_invalid += 1

            case_rows.append(
                {
                    "case_id": case.id,
                    "query": case.query,
                    "status": result.status,
                    "abstention_reason": result.abstention_reason,
                    "generator_invoked": result.generator_invoked,
                    "attempt_count": result.attempt_count,
                    "generation_failure_reason": result.generation_failure_reason,
                    "citation_count": len(result.citations),
                    "latency_ms": latency_ms,
                }
            )

        completed = datetime.now(tz=UTC)
        case_count = len(cases)
        citation_invalid_rate = (
            outcomes.citation_invalid / invoked if invoked else 0.0
        )
        report = QueryEvaluationResult(
            run_id=run_id,
            dataset_id=dataset_id,
            case_count=case_count,
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            dense_index_id=dense_index_id,
            lexical_index_id=lexical_index_id,
            fusion_config_hash=fusion_hash,
            reranker_config_hash=rerank_hash,
            context_config_hash=context_hash,
            generation_config_hash=gencfg,
            outcomes=outcomes,
            answered_rate=(outcomes.answered / case_count) if case_count else 0.0,
            insufficient_evidence_rate=(
                outcomes.insufficient_evidence / case_count if case_count else 0.0
            ),
            empty_context_rate=(outcomes.empty_context / case_count) if case_count else 0.0,
            model_abstain_rate=(outcomes.model_abstain / case_count) if case_count else 0.0,
            generation_failed_rate=(
                outcomes.generation_failed / case_count if case_count else 0.0
            ),
            citation_invalid_rate=citation_invalid_rate,
            generator_invoked_case_count=invoked,
            generator_not_invoked_case_count=not_invoked,
            total_generator_attempts=attempts,
            latency_mean_ms=sum(latencies) / len(latencies) if latencies else 0.0,
            latency_p50_ms=_percentile(latencies, 0.50),
            latency_p95_ms=_percentile(latencies, 0.95),
            generation_latency_mean_ms=(
                sum(gen_latencies) / len(gen_latencies) if gen_latencies else 0.0
            ),
            cases=case_rows,
            started_at=started,
            completed_at=completed,
            metadata={},
        )
        if persist:
            out = Path(output_path) if output_path else (
                Path(self.settings.paths.eval_results) / "query" / f"{run_id}.json"
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(out, report.model_dump_json())
            report.metadata["result_path"] = str(out)
        return report
