"""Product grounded query use case (15E / D06–D08 / D21)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from offline_rag.app.corpus import validate_product_corpus_name
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.query_binding import (
    SnapshotQueryBinding,
    build_snapshot_query_binding,
)
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.app.snapshot import PRODUCT_MODE_GROUNDED_V1, CorpusReadSnapshot
from offline_rag.app.traces import (
    ProductQueryTrace,
    ProductTraceExecutionSummary,
    ProductTraceIdentitySummary,
    ProductTraceRequestSummary,
    ProductTraceStore,
    allocate_trace_id,
)
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.context.store import load_structure_store_for_chunk_manifest
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.domain.generation import GroundedAnswerResult, ResolvedCitation
from offline_rag.generation.config_hash import build_generation_config_hash
from offline_rag.generation.orchestrate import (
    GroundedAnswerError,
    GroundedAnswerOrchestrator,
)
from offline_rag.hybrid.retrieve import HybridRetriever
from offline_rag.lexical.retrieve import LexicalRetriever
from offline_rag.rerank.retrieve import HybridRerankRetriever

MAX_QUESTION_CHARS = 8000

ProductSuccessStatus = Literal["answered", "insufficient_evidence", "model_abstain"]

_CITATION_PUBLIC_FIELDS = (
    "evidence_unit_id",
    "document_id",
    "source_chunk_id",
    "kind",
    "section_path",
    "page_start",
    "page_end",
    "line_start",
    "line_end",
    "clipped",
)


@dataclass(frozen=True, slots=True)
class ProductQueryResponse:
    corpus: str
    snapshot_id: str
    product_mode_id: str
    trace_id: str
    status: ProductSuccessStatus
    answer: str | None
    citations: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "corpus": self.corpus,
            "snapshot_id": self.snapshot_id,
            "product_mode_id": self.product_mode_id,
            "trace_id": self.trace_id,
            "status": self.status,
            "answer": self.answer,
            "citations": self.citations,
        }


def normalize_product_question(question: str) -> str:
    """Trim outer whitespace only; enforce non-empty and max length."""
    if not isinstance(question, str):
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="question_invalid"),
        )
    trimmed = question.strip()
    if not trimmed:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="question_empty"),
        )
    if len(trimmed) > MAX_QUESTION_CHARS:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="question_too_long"),
        )
    return trimmed


def _question_sha256(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def _latency_int(diagnostics: dict[str, Any] | None, key: str) -> int | None:
    if not diagnostics:
        return None
    latency = diagnostics.get("latency_ms")
    if not isinstance(latency, dict):
        return None
    value = latency.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _project_citations(
    citations: list[ResolvedCitation],
    *,
    snapshot: CorpusReadSnapshot,
    binding: SnapshotQueryBinding,
    result: GroundedAnswerResult,
) -> list[dict[str, Any]]:
    inventory = {entry.document_id for entry in snapshot.corpus_manifest.documents}
    if result.dense_index_id not in (None, binding.dense_index_id):
        raise AppError(ErrorCode.CITATION_INVALID)
    if result.lexical_index_id not in (None, binding.lexical_index_id):
        raise AppError(ErrorCode.CITATION_INVALID)
    if result.context_config_hash not in (None, binding.context_config_hash):
        raise AppError(ErrorCode.CITATION_INVALID)

    projected: list[dict[str, Any]] = []
    for citation in citations:
        if citation.document_id not in inventory:
            raise AppError(ErrorCode.CITATION_INVALID)
        row = {field: getattr(citation, field) for field in _CITATION_PUBLIC_FIELDS}
        projected.append(row)
    return projected


def _map_generation_failure(result: GroundedAnswerResult) -> AppError:
    if result.status == "citation_invalid":
        return AppError(ErrorCode.CITATION_INVALID)
    reason = result.generation_failure_reason or ""
    if reason == "timeout":
        return AppError(ErrorCode.GENERATION_TIMEOUT)
    if reason in {"transport_error", "unavailable"}:
        return AppError(ErrorCode.GENERATION_UNAVAILABLE)
    if reason in {"response_parse_error", "output_schema_invalid"}:
        return AppError(ErrorCode.RESPONSE_PARSE_ERROR)
    return AppError(ErrorCode.GENERATION_FAILED)


def _project_success(
    result: GroundedAnswerResult,
    *,
    snapshot: CorpusReadSnapshot,
    binding: SnapshotQueryBinding,
) -> tuple[ProductSuccessStatus, str | None, list[dict[str, Any]]]:
    if result.status == "answered":
        answer = result.answer_text
        if not answer or not str(answer).strip():
            raise AppError(ErrorCode.INTERNAL_ERROR)
        citations = _project_citations(
            list(result.citations),
            snapshot=snapshot,
            binding=binding,
            result=result,
        )
        return "answered", str(answer), citations

    if result.status == "insufficient_evidence":
        if result.abstention_reason == "model_abstain":
            return "model_abstain", None, []
        if result.abstention_reason == "empty_context":
            return "insufficient_evidence", None, []
        raise AppError(ErrorCode.INTERNAL_ERROR)

    if result.status in {"generation_failed", "citation_invalid"}:
        raise _map_generation_failure(result)

    raise AppError(ErrorCode.INTERNAL_ERROR)


def _build_orchestrator(
    runtime: ApplicationRuntime, binding: SnapshotQueryBinding
) -> GroundedAnswerOrchestrator:
    resources = runtime.resources
    if resources is None:
        raise AppError(ErrorCode.RUNTIME_NOT_READY)
    settings = runtime.settings

    dense = DenseRetriever(
        settings,
        embedder=resources.embedder,
        backend=resources.qdrant,
    )
    lexical = LexicalRetriever(settings)
    hybrid = HybridRetriever(settings, dense=dense, lexical=lexical)
    rerank = HybridRerankRetriever(
        settings,
        hybrid=hybrid,
        reranker=resources.reranker,
    )
    store = load_structure_store_for_chunk_manifest(
        settings, binding.chunk_manifest_name
    )
    assembler = HybridRerankContextAssembler(
        settings,
        retriever=rerank,
        store=store,
    )
    return GroundedAnswerOrchestrator(
        settings,
        context_assembler=assembler,
        generator=resources.generator_client,
    )


def _execute_bound(
    runtime: ApplicationRuntime,
    binding: SnapshotQueryBinding,
    question: str,
) -> GroundedAnswerResult:
    orchestrator = _build_orchestrator(runtime, binding)
    try:
        return orchestrator.answer(
            query=question,
            corpus_name=binding.corpus_name,
            check_ready=False,
            allow_recovery=False,
            source_name_by_document_id=binding.source_name_by_document_id(),
            dense_index_id=binding.dense_index_id,
            dense_collection_name=binding.dense_collection_name,
            lexical_index_id=binding.lexical_index_id,
            chunk_set_id=binding.chunk_set_id,
            corpus_id=binding.corpus_id,
        )
    finally:
        orchestrator.close()


def _execution_summary(
    result: GroundedAnswerResult | None,
) -> ProductTraceExecutionSummary:
    if result is None:
        return ProductTraceExecutionSummary()
    citations = list(result.citations)
    units = [c.evidence_unit_id for c in citations]
    diagnostics = result.diagnostics if isinstance(result.diagnostics, dict) else {}
    return ProductTraceExecutionSummary(
        evidence_unit_ids=list(units),
        citation_evidence_unit_ids=[c.evidence_unit_id for c in citations],
        citation_document_ids=[c.document_id for c in citations],
        citation_chunk_ids=[c.source_chunk_id for c in citations],
        evidence_count=len(units),
        citation_count=len(citations),
        generator_invoked=bool(result.generator_invoked),
        attempt_count=int(result.attempt_count),
        context_latency_ms=_latency_int(diagnostics, "context"),
        generation_latency_ms=_latency_int(diagnostics, "generation"),
        total_latency_ms=_latency_int(diagnostics, "total"),
    )


def _identity_summary(
    binding: SnapshotQueryBinding, *, generation_config_hash: str
) -> ProductTraceIdentitySummary:
    return ProductTraceIdentitySummary(
        corpus_id=binding.corpus_id,
        chunk_set_id=binding.chunk_set_id,
        dense_index_id=binding.dense_index_id,
        lexical_index_id=binding.lexical_index_id,
        fusion_config_hash=binding.fusion_config_hash,
        reranker_config_hash=binding.reranker_config_hash,
        context_config_hash=binding.context_config_hash,
        generation_config_hash=generation_config_hash,
    )


def _commit_terminal_trace(store: ProductTraceStore, record: ProductQueryTrace) -> None:
    """Persist terminal trace. Failure → internal_error without dangling trace_id."""
    try:
        store.commit(record)
    except AppError:
        raise AppError(ErrorCode.INTERNAL_ERROR)
    except Exception as exc:
        raise AppError(ErrorCode.INTERNAL_ERROR) from exc


def run_product_query(
    runtime: ApplicationRuntime,
    *,
    corpus: str,
    question: str,
) -> ProductQueryResponse:
    """Canonical app-layer product query (snapshot-bound, traced)."""
    runtime.require_ready()
    name = validate_product_corpus_name(corpus)
    normalized = normalize_product_question(question)

    # Pre-execution validation / snapshot resolution — no trace yet (D11).
    snapshot = runtime.publication.resolve(name)
    binding = build_snapshot_query_binding(runtime.settings, snapshot)
    if binding.product_mode_id != PRODUCT_MODE_GROUNDED_V1:
        raise AppError(
            ErrorCode.SNAPSHOT_UNAVAILABLE,
            details=SafeErrorDetails(reason="unsupported_product_mode"),
        )

    trace_id = allocate_trace_id()
    store = ProductTraceStore(runtime.settings)
    created_at = datetime.now(tz=UTC)
    gencfg = build_generation_config_hash(runtime.settings)
    request_summary = ProductTraceRequestSummary(
        question_sha256=_question_sha256(normalized),
        question_char_count=len(normalized),
    )
    identity = _identity_summary(binding, generation_config_hash=gencfg)

    result: GroundedAnswerResult | None = None
    mapped_error: AppError | None = None
    try:
        result = _execute_bound(runtime, binding, normalized)
        status, answer, citations = _project_success(
            result, snapshot=snapshot, binding=binding
        )
    except AppError as exc:
        mapped_error = exc
        status = None
        answer = None
        citations = []
    except GroundedAnswerError as exc:
        mapped_error = AppError(
            ErrorCode.INTERNAL_ERROR,
            details=SafeErrorDetails(reason="orchestration_fault"),
        )
        mapped_error.__cause__ = exc
        status = None
        answer = None
        citations = []
    except Exception as exc:  # noqa: BLE001 — unexpected defect
        mapped_error = AppError(ErrorCode.INTERNAL_ERROR)
        mapped_error.__cause__ = exc
        status = None
        answer = None
        citations = []

    if mapped_error is not None:
        record = ProductQueryTrace(
            trace_id=trace_id,
            created_at=created_at,
            corpus=binding.corpus_name,
            snapshot_id=binding.snapshot_id,
            product_mode_id=binding.product_mode_id,
            request=request_summary,
            identity=identity,
            status=None,
            error_code=str(mapped_error.code),
            execution=_execution_summary(result),
        )
        _commit_terminal_trace(store, record)
        raise AppError(
            mapped_error.code,
            message=mapped_error.message,
            trace_id=trace_id,
        ) from mapped_error

    assert status is not None
    record = ProductQueryTrace(
        trace_id=trace_id,
        created_at=created_at,
        corpus=binding.corpus_name,
        snapshot_id=binding.snapshot_id,
        product_mode_id=binding.product_mode_id,
        request=request_summary,
        identity=identity,
        status=status,
        error_code=None,
        execution=_execution_summary(result),
    )
    _commit_terminal_trace(store, record)
    return ProductQueryResponse(
        corpus=binding.corpus_name,
        snapshot_id=binding.snapshot_id,
        product_mode_id=binding.product_mode_id,
        trace_id=trace_id,
        status=status,
        answer=answer,
        citations=citations,
    )


def get_product_trace(
    runtime: ApplicationRuntime, trace_id: str
) -> dict[str, Any]:
    """Cheap durable trace read — unknown/expired/malformed → trace_unknown."""
    runtime.require_ready()
    store = ProductTraceStore(runtime.settings)
    record = store.get(trace_id)
    if record is None:
        raise AppError(ErrorCode.TRACE_UNKNOWN)
    return store.public_projection(record)
