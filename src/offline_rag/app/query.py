"""Product grounded query use case (15E / D06–D08 / D21)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from offline_rag.app.corpus import validate_product_corpus_name
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.operations import OperationHandle
from offline_rag.app.query_binding import (
    SnapshotQueryBinding,
    build_snapshot_query_binding,
)
from offline_rag.app.query_runtime import SnapshotQueryRuntimeHandle
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.app.snapshot import PRODUCT_MODE_GROUNDED_V1, CorpusReadSnapshot
from offline_rag.app.traces import (
    ProductQueryTrace,
    ProductTraceExecutionSummary,
    ProductTraceIdentitySummary,
    ProductTraceRequestSummary,
    ProductTraceSourceScope,
    ProductTraceStore,
    allocate_trace_id,
)
from offline_rag.app.workspace.models import (
    SourceVersionRecord,
    WorkspaceRecord,
    WorkspaceRevision,
    WorkspaceStatus,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.domain.generation import GroundedAnswerResult, ResolvedCitation
from offline_rag.generation.config_hash import build_generation_config_hash
from offline_rag.generation.orchestrate import GroundedAnswerError

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


@dataclass(frozen=True, slots=True)
class BoundSnapshotQueryOutcome:
    """Result of executing a query against one already-resolved snapshot."""

    snapshot: CorpusReadSnapshot
    binding: SnapshotQueryBinding
    trace_id: str
    status: ProductSuccessStatus
    answer: str | None
    citations: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class WorkspaceQueryResponse:
    """Workspace-scoped projection of a grounded answer (S16-D08)."""

    workspace_id: str
    workspace_revision: WorkspaceRevision
    snapshot_id: str
    product_mode_id: str
    trace_id: str
    status: ProductSuccessStatus
    answer: str | None
    citations: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_revision": self.workspace_revision,
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
    document_ids: frozenset[str] | None = None,
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
        if document_ids is not None and citation.document_id not in document_ids:
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
    document_ids: frozenset[str] | None = None,
) -> tuple[ProductSuccessStatus, str | None, list[dict[str, Any]]]:
    if result.status == "answered":
        answer = result.answer_text
        if not answer or not str(answer).strip():
            raise AppError(ErrorCode.INTERNAL_ERROR)
        # D21: answered requires non-empty validated citations.
        if not result.citations:
            raise AppError(ErrorCode.CITATION_INVALID)
        citations = _project_citations(
            list(result.citations),
            snapshot=snapshot,
            binding=binding,
            result=result,
            document_ids=document_ids,
        )
        if not citations:
            raise AppError(ErrorCode.CITATION_INVALID)
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


def _execute_snapshot_query(
    handle: SnapshotQueryRuntimeHandle,
    question: str,
    control: OperationHandle | None = None,
    *,
    document_ids: frozenset[str] | None = None,
) -> GroundedAnswerResult:
    """Execute grounded query against an already-bound snapshot runtime."""
    checkpoint = None if control is None else control.checkpoint
    return handle.answer(
        question, checkpoint=checkpoint, document_ids=document_ids
    )


def _execution_summary(
    result: GroundedAnswerResult | None,
) -> ProductTraceExecutionSummary:
    if result is None:
        return ProductTraceExecutionSummary()
    citations = list(result.citations)
    diagnostics = result.diagnostics if isinstance(result.diagnostics, dict) else {}
    return ProductTraceExecutionSummary(
        citation_evidence_unit_ids=[c.evidence_unit_id for c in citations],
        citation_document_ids=[c.document_id for c in citations],
        citation_chunk_ids=[c.source_chunk_id for c in citations],
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


def run_bound_snapshot_query(
    runtime: ApplicationRuntime,
    *,
    snapshot: CorpusReadSnapshot,
    question: str,
    control: OperationHandle | None = None,
    document_ids: frozenset[str] | None = None,
    source_scope: ProductTraceSourceScope | None = None,
) -> BoundSnapshotQueryOutcome:
    """Execute the canonical grounded query against an already-resolved snapshot.

    This is the single execution path for every product read surface. The caller
    owns snapshot *resolution*, which is what distinguishes the product path
    (``current.json``) from the workspace path (``workspace.current_snapshot_id``);
    execution, tracing, and citation validation must not differ between them.
    """
    normalized = normalize_product_question(question)
    binding = build_snapshot_query_binding(runtime.settings, snapshot)
    if binding.product_mode_id != PRODUCT_MODE_GROUNDED_V1:
        raise AppError(
            ErrorCode.SNAPSHOT_UNAVAILABLE,
            details=SafeErrorDetails(reason="unsupported_product_mode"),
        )

    if control is not None:
        control.checkpoint("pre_bind")
    handle = runtime.query_runtimes.acquire(binding)
    try:
        if control is not None:
            control.checkpoint("pre_trace")
        # Execution begins — allocate durable trace identity (D11).
        trace_id = allocate_trace_id()
        store = ProductTraceStore(runtime.settings)
        created_at = datetime.now(tz=UTC)
        gencfg = build_generation_config_hash(runtime.settings)
        request_summary = ProductTraceRequestSummary(
            question_sha256=_question_sha256(normalized),
            question_char_count=len(normalized),
            source_scope=source_scope,
        )
        identity = _identity_summary(binding, generation_config_hash=gencfg)

        result: GroundedAnswerResult | None = None
        mapped_error: AppError | None = None
        try:
            if control is not None:
                control.checkpoint("pre_execute")
            result = _execute_snapshot_query(
                handle,
                normalized,
                control=control,
                document_ids=document_ids,
            )
            if control is not None:
                control.checkpoint("post_execute")
            if control is not None:
                control.checkpoint("pre_project")
            status, answer, citations = _project_success(
                result,
                snapshot=snapshot,
                binding=binding,
                document_ids=document_ids,
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
        except Exception as exc:  # noqa: BLE001 - map unexpected defects to D08
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
        return BoundSnapshotQueryOutcome(
            snapshot=snapshot,
            binding=binding,
            trace_id=trace_id,
            status=status,
            answer=answer,
            citations=citations,
        )
    finally:
        runtime.query_runtimes.release(handle)


def run_product_query(
    runtime: ApplicationRuntime,
    *,
    corpus: str,
    question: str,
    control: OperationHandle | None = None,
) -> ProductQueryResponse:
    """Canonical app-layer product query (snapshot-bound, traced).

    Resolves the corpus current publication, then delegates to the shared bound
    execution path.
    """
    runtime.require_ready()
    if control is not None:
        control.checkpoint("pre_validate")
    name = validate_product_corpus_name(corpus)
    normalized = normalize_product_question(question)

    # Pre-execution: resolve snapshot + bind/validate cached query runtime.
    # No trace yet — backing failures are snapshot_unavailable (D08/D11).
    if control is not None:
        control.checkpoint("pre_resolve")
    snapshot = runtime.publication.resolve(name)
    outcome = run_bound_snapshot_query(
        runtime, snapshot=snapshot, question=normalized, control=control
    )
    return ProductQueryResponse(
        corpus=outcome.binding.corpus_name,
        snapshot_id=outcome.binding.snapshot_id,
        product_mode_id=outcome.binding.product_mode_id,
        trace_id=outcome.trace_id,
        status=outcome.status,
        answer=outcome.answer,
        citations=outcome.citations,
    )


def _active_source_index(
    record: WorkspaceRecord,
    *,
    selected_source_ids: frozenset[str] | None = None,
) -> dict[str, list[SourceVersionRecord]]:
    index: dict[str, list[SourceVersionRecord]] = {}
    for source in record.sources:
        if not source.active or source.document_id is None:
            continue
        if (
            selected_source_ids is not None
            and source.source_id not in selected_source_ids
        ):
            continue
        index.setdefault(source.document_id, []).append(source)
    return index


def _enrich_workspace_citations(
    citations: list[dict[str, Any]],
    *,
    record: WorkspaceRecord,
    require_mapping: bool,
    selected_source_ids: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Attach workspace source identity to snapshot-level citations.

    Citations are scientific (``document_id``); the UI needs the logical source
    the user actually uploaded. Mapping must be unambiguous: if an answered
    citation cannot be attributed to exactly one active source, the workspace
    view of that answer would be wrong, so fail closed rather than emit a
    citation the user cannot trace back (S16-D12).
    """
    index = _active_source_index(record, selected_source_ids=selected_source_ids)
    enriched: list[dict[str, Any]] = []
    for citation in citations:
        row = dict(citation)
        matches = index.get(str(citation.get("document_id")), [])
        if len(matches) == 1:
            source = matches[0]
            row["source_id"] = source.source_id
            row["source_version"] = source.version
            row["source_display_name"] = source.display_name
        elif require_mapping:
            raise AppError(
                ErrorCode.CITATION_INVALID,
                details=SafeErrorDetails(
                    workspace_id=record.workspace_id,
                    reason="citation_source_unmappable"
                    if not matches
                    else "citation_source_ambiguous",
                ),
            )
        else:
            row["source_id"] = None
            row["source_version"] = None
            row["source_display_name"] = None
        enriched.append(row)
    return enriched


def _resolve_workspace_source_scope(
    record: WorkspaceRecord,
    *,
    source_ids: list[str] | None,
) -> tuple[ProductTraceSourceScope, frozenset[str], frozenset[str]]:
    """Resolve logical source_ids to document scope for a bound workspace record."""
    active_by_id = {
        source.source_id: source
        for source in record.sources
        if source.active and source.document_id
    }
    if source_ids is not None and len(source_ids) == 0:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(
                workspace_id=record.workspace_id, reason="empty_source_scope"
            ),
        )
    if source_ids is None:
        selected = list(active_by_id.values())
        mode: Literal["all_active", "selected"] = "all_active"
    else:
        if len(source_ids) != len(set(source_ids)):
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(
                    workspace_id=record.workspace_id, reason="duplicate_source_ids"
                ),
            )
        selected = []
        for source_id in source_ids:
            source = active_by_id.get(source_id)
            if source is None:
                raise AppError(
                    ErrorCode.SOURCE_UNKNOWN,
                    details=SafeErrorDetails(
                        workspace_id=record.workspace_id, source_id=source_id
                    ),
                )
            selected.append(source)
        mode = "selected"

    logical_ids = sorted({source.source_id for source in selected})
    document_ids = sorted(
        {str(source.document_id) for source in selected if source.document_id}
    )
    scope = ProductTraceSourceScope(
        workspace_id=record.workspace_id,
        workspace_revision=int(record.revision),
        mode=mode,
        source_ids=logical_ids,
        document_ids=document_ids,
    )
    return scope, frozenset(logical_ids), frozenset(document_ids)


def run_workspace_query(
    runtime: ApplicationRuntime,
    *,
    workspace_id: str,
    question: str,
    source_ids: list[str] | None = None,
    control: OperationHandle | None = None,
) -> WorkspaceQueryResponse:
    """Workspace-scoped grounded query bound to the workspace's own snapshot.

    The workspace record — not ``current.json`` — is the authority for which
    snapshot a workspace reads. Re-resolving the corpus current publication here
    would let an unrelated concurrent publication (or a retired-then-republished
    corpus) silently answer from a snapshot this workspace never claimed.

    EMPTY fails closed and never falls back to the previously current snapshot
    (S16-D08 / S16-D13).
    """
    runtime.require_ready()
    if control is not None:
        control.checkpoint("pre_validate")
    store = WorkspaceStore(runtime.settings)
    record = store.get(workspace_id)
    if record.status is not WorkspaceStatus.ACTIVE or record.current_snapshot_id is None:
        raise AppError(
            ErrorCode.WORKSPACE_NOT_READY,
            details=SafeErrorDetails(
                workspace_id=workspace_id,
                reason="workspace_empty"
                if record.status is WorkspaceStatus.EMPTY
                else "workspace_no_current_publication",
            ),
        )
    normalized = normalize_product_question(question)

    bound_revision = record.revision
    bound_snapshot_id = record.current_snapshot_id
    source_scope, selected_logical, document_scope = _resolve_workspace_source_scope(
        record, source_ids=source_ids
    )
    if control is not None:
        control.checkpoint("pre_resolve")
    snapshot = runtime.publication.resolve_snapshot(
        record.backing_corpus_name, bound_snapshot_id
    )

    # Torn read: a mutation committed between reading the record and binding its
    # snapshot. The binding is no longer the workspace's current state, so refuse
    # rather than answer from a revision the client cannot name.
    recheck = store.get(workspace_id)
    if (
        recheck.revision != bound_revision
        or recheck.current_snapshot_id != bound_snapshot_id
    ):
        raise AppError(
            ErrorCode.WORKSPACE_CONFLICT,
            details=SafeErrorDetails(
                workspace_id=workspace_id, reason="workspace_revision_changed"
            ),
        )

    outcome = run_bound_snapshot_query(
        runtime,
        snapshot=snapshot,
        question=normalized,
        control=control,
        document_ids=document_scope,
        source_scope=source_scope,
    )
    citations = _enrich_workspace_citations(
        outcome.citations,
        record=record,
        require_mapping=outcome.status == "answered",
        selected_source_ids=selected_logical,
    )
    return WorkspaceQueryResponse(
        workspace_id=workspace_id,
        workspace_revision=bound_revision,
        snapshot_id=outcome.binding.snapshot_id,
        product_mode_id=outcome.binding.product_mode_id,
        trace_id=outcome.trace_id,
        status=outcome.status,
        answer=outcome.answer,
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
