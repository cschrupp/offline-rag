"""Relevance prelabel orchestration (Slice 9D)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from offline_rag.config.models import AppSettings
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.gold_authoring.adapter import (
    AuthoringAdapterError,
    OpenAICompatibleAuthoringAdapter,
)
from offline_rag.gold_authoring.agreement import AgreementError, derive_prelabel_summary
from offline_rag.gold_authoring.blind_order import BlindOrderError, derive_blind_orders
from offline_rag.gold_authoring.chunk_access import (
    ChunkAccessError,
    CorpusChunkSnapshot,
    load_chunk_set_snapshot,
)
from offline_rag.gold_authoring.config_hash import build_authoring_config_hash
from offline_rag.gold_authoring.contracts import PASS_1, PASS_2
from offline_rag.gold_authoring.judge_context import (
    JudgeContextError,
    build_relevance_judge_context,
)
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase
from offline_rag.gold_authoring.persist import load_authoring_run, write_authoring_run
from offline_rag.gold_authoring.prelabel_models import (
    CasePrelabelProvenance,
    ModelJudgment,
    PrelabelCaseOutcome,
    PrelabelCaseStatus,
    PrelabelFailureReason,
    PrelabelPassOrder,
    PrelabelingProvenance,
    PrelabelingStage,
)
from offline_rag.gold_authoring.prelabel_schema import (
    RelevancePrelabelParseError,
    parse_relevance_prelabel_v1,
)
from offline_rag.gold_authoring.privacy import (
    AuthoringPrivacyError,
    authorize_authoring_endpoint,
)
from offline_rag.gold_authoring.prompt import relevance_prelabel_system_prompt
from offline_rag.gold_authoring.readiness import evaluate_authoring_readiness
from offline_rag.ingestion.persistence import (
    corpus_state_path,
    load_corpus_manifest,
    load_corpus_state,
)


class PrelabelPreRunError(RuntimeError):
    """Valid prelabel run could not start (CLI exit 2)."""


class PrelabelCaseError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        reason: PrelabelFailureReason,
        pass_id: str | None = None,
        chunk_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.pass_id = pass_id
        self.chunk_id = chunk_id


@dataclass
class PrelabelJobResult:
    exit_code: int
    run: GoldAuthoringRun | None = None
    output_path: Path | None = None
    message: str = ""
    failure_reason_counts: Counter[str] = field(default_factory=Counter)
    model_request_count: int = 0


class PrelabelModelClient(Protocol):
    def prelabel(self, *, system_prompt: str, user_content: str) -> str: ...

    def close(self) -> None: ...


def _resolve_corpus_manifest_name(
    settings: AppSettings,
    *,
    corpus_name: str,
    corpus_id: str,
) -> str | None:
    state_path = corpus_state_path(settings.paths.corpora, corpus_name)
    if state_path.exists():
        try:
            state = load_corpus_state(state_path)
        except Exception:  # noqa: BLE001
            state = None
        if state is not None and state.current_corpus_id == corpus_id:
            return Path(state.current_manifest).name
    manifests_root = settings.paths.manifests
    if not manifests_root.exists():
        return None
    for path in sorted(manifests_root.glob("*.json")):
        try:
            manifest = load_corpus_manifest(path)
        except Exception:  # noqa: BLE001
            continue
        if manifest.corpus_id == corpus_id:
            return path.name
    return None


def _load_historical_snapshot(
    settings: AppSettings,
    *,
    corpus_name: str,
    corpus_id: str,
    chunk_set_id: str,
) -> CorpusChunkSnapshot:
    manifest_name = _resolve_corpus_manifest_name(
        settings, corpus_name=corpus_name, corpus_id=corpus_id
    )
    return load_chunk_set_snapshot(
        settings,
        corpus_name=corpus_name,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        corpus_manifest_name=manifest_name,
    )


def _child_lookup(snapshot: CorpusChunkSnapshot) -> dict[str, Chunk]:
    return {
        chunk.chunk_id: chunk
        for chunk in snapshot.chunks
        if chunk.kind == ChunkKind.CHILD
    }


def _select_eligible_cases(run: GoldAuthoringRun) -> list[SilverCase]:
    out: list[SilverCase] = []
    for case in run.cases:
        if case.proposed_query is None or not str(case.proposed_query).strip():
            continue
        if not case.candidates:
            continue
        out.append(case)
    return out


def _validate_case_envelopes(
    case: SilverCase,
    *,
    children: dict[str, Chunk],
    source_name_by_document_id: dict[str, str],
) -> dict[str, str]:
    """Return chunk_id -> rendered user message; fail closed before LLM calls."""
    query = str(case.proposed_query).strip()
    rendered: dict[str, str] = {}
    seen: set[str] = set()
    for candidate in case.candidates:
        if candidate.chunk_id in seen:
            raise PrelabelCaseError(
                f"duplicate candidate chunk_id {candidate.chunk_id}",
                reason=PrelabelFailureReason.CANDIDATE_IDENTITY_INVALID,
                chunk_id=candidate.chunk_id,
            )
        seen.add(candidate.chunk_id)
        chunk = children.get(candidate.chunk_id)
        if chunk is None:
            raise PrelabelCaseError(
                f"chunk_id {candidate.chunk_id} not in historical ChunkSet",
                reason=PrelabelFailureReason.HISTORICAL_CANDIDATE_UNAVAILABLE,
                chunk_id=candidate.chunk_id,
            )
        try:
            context = build_relevance_judge_context(
                query=query,
                chunk=chunk,
                source_name=source_name_by_document_id.get(chunk.document_id),
            )
        except JudgeContextError as exc:
            raise PrelabelCaseError(
                str(exc),
                reason=PrelabelFailureReason.CANDIDATE_PROVENANCE_UNAVAILABLE,
                chunk_id=candidate.chunk_id,
            ) from exc
        rendered[candidate.chunk_id] = context.render_user_message()
    return rendered


def _map_adapter_reason(reason: str) -> PrelabelFailureReason:
    if reason in {
        "timeout",
        "transport_error",
        "http_error",
        "authentication_error",
        "redirect_not_allowed",
        "empty_response",
    }:
        return PrelabelFailureReason.AUTHORING_TRANSPORT_FAILED
    return PrelabelFailureReason.INTERNAL_PRELABEL_FAILURE


def _judge_case(
    case: SilverCase,
    *,
    run: GoldAuthoringRun,
    authorcfg_id: str,
    children: dict[str, Chunk],
    source_name_by_document_id: dict[str, str],
    client: PrelabelModelClient,
    system_prompt: str,
) -> tuple[list[ModelJudgment], CasePrelabelProvenance, object, int]:
    """Return judgments, provenance, summary, and model request count."""
    from offline_rag.gold_authoring.prelabel_models import PrelabelSummary

    candidate_ids = [c.chunk_id for c in case.candidates]
    if not candidate_ids:
        raise PrelabelCaseError(
            "empty candidate pool",
            reason=PrelabelFailureReason.CANDIDATE_IDENTITY_INVALID,
        )
    rendered = _validate_case_envelopes(
        case,
        children=children,
        source_name_by_document_id=source_name_by_document_id,
    )
    try:
        order1, order2 = derive_blind_orders(
            authoring_run_id=run.authoring_run_id,
            draft_case_id=case.draft_case_id,
            candidate_ids=candidate_ids,
        )
    except BlindOrderError as exc:
        raise PrelabelCaseError(
            str(exc),
            reason=PrelabelFailureReason.INTERNAL_PRELABEL_FAILURE,
        ) from exc

    judgments: list[ModelJudgment] = []
    calls = 0
    for pass_id, order in ((PASS_1, order1), (PASS_2, order2)):
        for position, chunk_id in enumerate(order, start=1):
            user_content = rendered[chunk_id]
            try:
                content = client.prelabel(
                    system_prompt=system_prompt,
                    user_content=user_content,
                )
            except AuthoringAdapterError as exc:
                raise PrelabelCaseError(
                    str(exc),
                    reason=_map_adapter_reason(exc.failure_reason),
                    pass_id=pass_id,
                    chunk_id=chunk_id,
                ) from exc
            calls += 1
            try:
                parsed = parse_relevance_prelabel_v1(content)
            except RelevancePrelabelParseError as exc:
                raise PrelabelCaseError(
                    str(exc),
                    reason=PrelabelFailureReason.MODEL_RESPONSE_INVALID,
                    pass_id=pass_id,
                    chunk_id=chunk_id,
                ) from exc
            judgments.append(
                ModelJudgment(
                    pass_id=pass_id,  # type: ignore[arg-type]
                    chunk_id=chunk_id,
                    blind_position=position,
                    grade=parsed.grade,
                    rationale=parsed.rationale,
                )
            )

    seed_id = case.source_seed.chunk_id if case.source_seed is not None else None
    try:
        summary: PrelabelSummary = derive_prelabel_summary(
            judgments,
            candidate_ids=candidate_ids,
            source_seed_chunk_id=seed_id,
        )
    except AgreementError as exc:
        raise PrelabelCaseError(
            str(exc),
            reason=PrelabelFailureReason.AGREEMENT_DERIVATION_FAILED,
        ) from exc

    provenance = CasePrelabelProvenance(
        authorcfg_id=authorcfg_id,
        source_chunk_set_id=str(run.chunk_set_id),
        passes=[
            PrelabelPassOrder(pass_id=PASS_1, candidate_order=order1),
            PrelabelPassOrder(pass_id=PASS_2, candidate_order=order2),
        ],
    )
    return judgments, provenance, summary, calls


def run_gold_prelabel(
    settings: AppSettings,
    *,
    run_path: Path,
    output: Path | None = None,
    force: bool = False,
    adapter: PrelabelModelClient | None = None,
) -> PrelabelJobResult:
    path = Path(run_path)
    if not path.exists():
        raise PrelabelPreRunError(f"authoring run not found: {path}")

    readiness = evaluate_authoring_readiness(settings)
    if not readiness.ready:
        raise PrelabelPreRunError(
            f"Authoring NOT READY: {', '.join(readiness.reason_codes) or 'unknown'}"
        )
    try:
        authorize_authoring_endpoint(settings)
    except AuthoringPrivacyError as exc:
        raise PrelabelPreRunError(f"authoring endpoint unauthorized: {exc}") from exc

    try:
        run = load_authoring_run(path)
    except Exception as exc:  # noqa: BLE001
        raise PrelabelPreRunError(f"invalid authoring run: {exc}") from exc

    destination = Path(output) if output is not None else path
    if destination.exists() and destination.resolve() != path.resolve() and not force:
        raise PrelabelPreRunError(
            f"output already exists (pass --force to overwrite): {destination}"
        )

    targets = _select_eligible_cases(run)
    if not targets:
        raise PrelabelPreRunError(
            "no eligible pooled SilverCases with valid proposed queries"
        )

    already = [c for c in targets if c.has_complete_durable_prelabel()]
    if already and not force:
        raise PrelabelPreRunError(
            "one or more targeted cases already have complete durable prelabels "
            "(pass --force to re-prelabel)"
        )

    if run.chunk_set_id is None or not str(run.chunk_set_id).strip():
        raise PrelabelPreRunError("authoring run missing chunk_set_id")
    if run.corpus_id is None or not str(run.corpus_id).strip():
        raise PrelabelPreRunError("authoring run missing corpus_id")

    try:
        snapshot = _load_historical_snapshot(
            settings,
            corpus_name=str(run.corpus_name or "default"),
            corpus_id=str(run.corpus_id),
            chunk_set_id=str(run.chunk_set_id),
        )
    except ChunkAccessError as exc:
        raise PrelabelPreRunError(str(exc)) from exc

    children = _child_lookup(snapshot)
    authorcfg_id = build_authoring_config_hash(settings)
    system_prompt = relevance_prelabel_system_prompt()

    owned = adapter is None
    active: PrelabelModelClient = adapter or OpenAICompatibleAuthoringAdapter(settings)

    working = run.model_copy(deep=True)
    case_by_id = {c.draft_case_id: c for c in working.cases}
    outcomes: list[PrelabelCaseOutcome] = []
    reason_counts: Counter[str] = Counter()
    success_count = 0
    model_calls = 0

    try:
        for target in targets:
            case = case_by_id[target.draft_case_id]
            prior_judgments = list(case.model_judgments)
            prior_summary = (
                case.prelabel_summary.model_copy(deep=True)
                if case.prelabel_summary is not None
                else None
            )
            prior_provenance = (
                case.prelabel_provenance.model_copy(deep=True)
                if case.prelabel_provenance is not None
                else None
            )
            try:
                judgments, provenance, summary, calls = _judge_case(
                    case,
                    run=working,
                    authorcfg_id=authorcfg_id,
                    children=children,
                    source_name_by_document_id=snapshot.source_name_by_document_id,
                    client=active,
                    system_prompt=system_prompt,
                )
                model_calls += calls
                case.model_judgments = judgments
                case.prelabel_provenance = provenance
                case.prelabel_summary = summary  # type: ignore[assignment]
                # Re-validate coherence.
                SilverCase.model_validate(case.model_dump(mode="json"))
                success_count += 1
                outcomes.append(
                    PrelabelCaseOutcome(
                        draft_case_id=case.draft_case_id,
                        status=PrelabelCaseStatus.SUCCEEDED,
                    )
                )
            except PrelabelCaseError as exc:
                case.model_judgments = prior_judgments
                case.prelabel_summary = prior_summary
                case.prelabel_provenance = prior_provenance
                reason_counts[str(exc.reason)] += 1
                outcomes.append(
                    PrelabelCaseOutcome(
                        draft_case_id=case.draft_case_id,
                        status=PrelabelCaseStatus.FAILED,
                        failure_reason=exc.reason,
                        pass_id=exc.pass_id,  # type: ignore[arg-type]
                        chunk_id=exc.chunk_id,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                case.model_judgments = prior_judgments
                case.prelabel_summary = prior_summary
                case.prelabel_provenance = prior_provenance
                reason_counts[str(PrelabelFailureReason.INTERNAL_PRELABEL_FAILURE)] += 1
                outcomes.append(
                    PrelabelCaseOutcome(
                        draft_case_id=case.draft_case_id,
                        status=PrelabelCaseStatus.FAILED,
                        failure_reason=PrelabelFailureReason.INTERNAL_PRELABEL_FAILURE,
                    )
                )
                _ = exc
    finally:
        if owned and hasattr(active, "close"):
            active.close()

    working.prelabeling = PrelabelingStage(
        provenance=PrelabelingProvenance(
            authorcfg_id=authorcfg_id,
            source_chunk_set_id=str(working.chunk_set_id),
        ),
        outcomes=outcomes,
        targeted_case_count=len(targets),
        successful_case_count=success_count,
        failed_case_count=len(targets) - success_count,
    )

    try:
        GoldAuthoringRun.model_validate(working.model_dump(mode="json"))
        write_authoring_run(destination, working)
    except Exception as exc:  # noqa: BLE001
        return PrelabelJobResult(
            exit_code=2,
            run=None,
            output_path=None,
            message=f"failed to persist enriched authoring run: {exc}",
            failure_reason_counts=reason_counts,
            model_request_count=model_calls,
        )

    exit_code = 0 if success_count >= 1 else 1
    return PrelabelJobResult(
        exit_code=exit_code,
        run=working,
        output_path=destination,
        message=(
            f"Relevance prelabeling completed: {success_count}/{len(targets)} "
            "cases prelabelled under relevance-prelabel-v1"
        ),
        failure_reason_counts=reason_counts,
        model_request_count=model_calls,
    )
