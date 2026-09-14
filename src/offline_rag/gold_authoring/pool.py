"""Candidate pooling orchestration (Slice 9C)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.core.document_metadata import (
    DocumentMetadataError,
    resolve_document_title_v1,
)
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.gold_authoring.chunk_access import (
    ChunkAccessError,
    CorpusChunkSnapshot,
    load_chunk_set_snapshot,
)
from offline_rag.gold_authoring.contracts import POOLING_RETRIEVER_IDS
from offline_rag.gold_authoring.models import (
    GoldAuthoringRun,
    HumanReviewStatus,
    SilverCase,
)
from offline_rag.gold_authoring.persist import load_authoring_run, write_authoring_run
from offline_rag.gold_authoring.pool_arms import (
    ArmExecutionError,
    HistoricalPoolArmExecutor,
    PoolArmExecutor,
)
from offline_rag.gold_authoring.pool_preflight import (
    PoolPreflightError,
    ResolvedPoolingArtifacts,
    preflight_pooling_artifacts,
)
from offline_rag.gold_authoring.pool_union import union_candidates
from offline_rag.gold_authoring.pooling_models import (
    PoolCandidate,
    PoolCaseOutcome,
    PoolCaseStatus,
    PoolFailureReason,
)
from offline_rag.ingestion.persistence import (
    corpus_state_path,
    load_corpus_manifest,
    load_corpus_state,
)


class PoolPreRunError(RuntimeError):
    """Valid pooling run could not start (CLI exit 2)."""


@dataclass
class PoolJobResult:
    exit_code: int
    run: GoldAuthoringRun | None = None
    output_path: Path | None = None
    message: str = ""
    failure_reason_counts: Counter[str] = field(default_factory=Counter)
    retrieval_call_count: int = 0


def _resolve_corpus_manifest_name(
    settings: AppSettings,
    *,
    corpus_name: str,
    corpus_id: str,
) -> str | None:
    """Best-effort historical corpus manifest name for document titles."""
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
    artifacts: ResolvedPoolingArtifacts,
) -> CorpusChunkSnapshot:
    manifest_name = _resolve_corpus_manifest_name(
        settings,
        corpus_name=artifacts.corpus_name,
        corpus_id=artifacts.corpus_id,
    )
    try:
        return load_chunk_set_snapshot(
            settings,
            corpus_name=artifacts.corpus_name,
            corpus_id=artifacts.corpus_id,
            chunk_set_id=artifacts.chunk_set_id,
            corpus_manifest_name=manifest_name,
        )
    except ChunkAccessError as exc:
        raise PoolPreflightError(str(exc)) from exc


def _child_lookup(snapshot: CorpusChunkSnapshot) -> dict[str, Chunk]:
    return {
        chunk.chunk_id: chunk
        for chunk in snapshot.chunks
        if chunk.kind == ChunkKind.CHILD
    }


def _enrich_candidates(
    candidates: list[PoolCandidate],
    *,
    children: dict[str, Chunk],
    source_name_by_document_id: dict[str, str],
) -> list[PoolCandidate]:
    enriched: list[PoolCandidate] = []
    for candidate in candidates:
        chunk = children.get(candidate.chunk_id)
        if chunk is None:
            raise ArmExecutionError(
                f"chunk_id {candidate.chunk_id} not in historical ChunkSet children",
                reason=PoolFailureReason.CANDIDATE_IDENTITY_INVALID,
            )
        source_name = source_name_by_document_id.get(chunk.document_id)
        title: str | None = None
        if source_name is not None and str(source_name).strip():
            try:
                title = resolve_document_title_v1(str(source_name))
            except DocumentMetadataError as exc:
                raise ArmExecutionError(
                    f"document title unavailable for {chunk.document_id}: {exc}",
                    reason=PoolFailureReason.CANDIDATE_PROVENANCE_UNAVAILABLE,
                ) from exc
        else:
            raise ArmExecutionError(
                f"authoritative source_name missing for document_id={chunk.document_id}",
                reason=PoolFailureReason.CANDIDATE_PROVENANCE_UNAVAILABLE,
            )
        enriched.append(
            PoolCandidate(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_title=title,
                section_path=list(chunk.section_path),
                retrieval_hits=list(candidate.retrieval_hits),
            )
        )
    return enriched


def _select_target_cases(run: GoldAuthoringRun) -> list[SilverCase]:
    return [
        case
        for case in run.cases
        if case.human_status == HumanReviewStatus.PENDING
        and case.proposed_query is not None
        and str(case.proposed_query).strip()
    ]


def _pool_one_case(
    case: SilverCase,
    *,
    executor: PoolArmExecutor,
    artifacts: ResolvedPoolingArtifacts,
    children: dict[str, Chunk],
    source_name_by_document_id: dict[str, str],
) -> tuple[list[PoolCandidate] | None, PoolCaseOutcome]:
    query = case.proposed_query
    if query is None or not str(query).strip():
        return None, PoolCaseOutcome(
            draft_case_id=case.draft_case_id,
            status=PoolCaseStatus.FAILED,
            failure_reason=PoolFailureReason.INVALID_CASE_QUERY,
            candidate_count=0,
        )

    try:
        hits_by_arm = executor.execute_all(query=str(query).strip(), artifacts=artifacts)
    except ArmExecutionError as exc:
        return None, PoolCaseOutcome(
            draft_case_id=case.draft_case_id,
            status=PoolCaseStatus.FAILED,
            failure_reason=exc.reason,
            candidate_count=0,
            failed_retriever=exc.retriever,
        )
    except Exception:  # noqa: BLE001
        return None, PoolCaseOutcome(
            draft_case_id=case.draft_case_id,
            status=PoolCaseStatus.FAILED,
            failure_reason=PoolFailureReason.RETRIEVER_ERROR,
            candidate_count=0,
        )

    missing_arms = [arm for arm in POOLING_RETRIEVER_IDS if arm not in hits_by_arm]
    if missing_arms:
        return None, PoolCaseOutcome(
            draft_case_id=case.draft_case_id,
            status=PoolCaseStatus.FAILED,
            failure_reason=PoolFailureReason.POOL_CONSTRUCTION_FAILED,
            candidate_count=0,
            failed_retriever=missing_arms[0],
        )

    try:
        shells = union_candidates(
            {arm: hits_by_arm[arm] for arm in POOLING_RETRIEVER_IDS}
        )
        if not shells:
            return None, PoolCaseOutcome(
                draft_case_id=case.draft_case_id,
                status=PoolCaseStatus.FAILED,
                failure_reason=PoolFailureReason.EMPTY_CANDIDATE_POOL,
                candidate_count=0,
            )
        candidates = _enrich_candidates(
            shells,
            children=children,
            source_name_by_document_id=source_name_by_document_id,
        )
    except ArmExecutionError as exc:
        return None, PoolCaseOutcome(
            draft_case_id=case.draft_case_id,
            status=PoolCaseStatus.FAILED,
            failure_reason=exc.reason,
            candidate_count=0,
            failed_retriever=exc.retriever,
        )
    except Exception:  # noqa: BLE001
        return None, PoolCaseOutcome(
            draft_case_id=case.draft_case_id,
            status=PoolCaseStatus.FAILED,
            failure_reason=PoolFailureReason.POOL_CONSTRUCTION_FAILED,
            candidate_count=0,
        )

    return candidates, PoolCaseOutcome(
        draft_case_id=case.draft_case_id,
        status=PoolCaseStatus.SUCCEEDED,
        failure_reason=None,
        candidate_count=len(candidates),
    )


def run_gold_pool(
    settings: AppSettings,
    *,
    run_path: Path,
    output: Path | None = None,
    force: bool = False,
    executor: PoolArmExecutor | None = None,
) -> PoolJobResult:
    """Enrich an existing authoring run with candidate-pooling-v1 pools."""
    path = Path(run_path)
    if not path.exists():
        raise PoolPreRunError(f"authoring run not found: {path}")

    try:
        run = load_authoring_run(path)
    except Exception as exc:  # noqa: BLE001
        raise PoolPreRunError(f"invalid authoring run: {exc}") from exc

    destination = Path(output) if output is not None else path
    if destination.exists() and destination.resolve() != path.resolve() and not force:
        raise PoolPreRunError(
            f"output already exists (pass --force to overwrite): {destination}"
        )

    targets = _select_target_cases(run)
    if not targets:
        raise PoolPreRunError(
            "no poolable pending SilverCases with valid proposed queries"
        )

    already_pooled = [c for c in targets if c.candidates]
    if already_pooled and not force:
        raise PoolPreRunError(
            "one or more targeted cases already have non-empty candidates[] "
            "(pass --force to re-pool)"
        )

    try:
        artifacts = preflight_pooling_artifacts(settings, run)
        snapshot = _load_historical_snapshot(settings, artifacts)
    except PoolPreflightError as exc:
        raise PoolPreRunError(str(exc)) from exc

    children = _child_lookup(snapshot)
    owned_executor = executor is None
    active: PoolArmExecutor = executor or HistoricalPoolArmExecutor(settings)
    retrieval_calls = 0

    # Work on a deep copy of cases so failed re-pools keep prior candidates.
    working = run.model_copy(deep=True)
    case_by_id = {case.draft_case_id: case for case in working.cases}
    outcomes: list[PoolCaseOutcome] = []
    reason_counts: Counter[str] = Counter()
    success_count = 0

    try:
        for target in targets:
            case = case_by_id[target.draft_case_id]
            prior_candidates = list(case.candidates)
            retrieval_calls += 1
            new_pool, outcome = _pool_one_case(
                case,
                executor=active,
                artifacts=artifacts,
                children=children,
                source_name_by_document_id=snapshot.source_name_by_document_id,
            )
            outcomes.append(outcome)
            if outcome.status == PoolCaseStatus.SUCCEEDED and new_pool is not None:
                case.candidates = new_pool
                success_count += 1
            else:
                # Preserve prior pool on failed re-pool / failed first pool.
                case.candidates = prior_candidates
                if outcome.failure_reason is not None:
                    reason_counts[str(outcome.failure_reason)] += 1
    finally:
        if owned_executor and hasattr(active, "close"):
            active.close()  # type: ignore[attr-defined]

    working.pooling = artifacts.provenance
    working.pool_outcomes = outcomes
    working.pool_targeted_case_count = len(targets)
    working.pool_successful_case_count = success_count
    working.pool_failed_case_count = len(targets) - success_count

    try:
        GoldAuthoringRun.model_validate(working.model_dump(mode="json"))
        write_authoring_run(destination, working)
    except Exception as exc:  # noqa: BLE001
        return PoolJobResult(
            exit_code=2,
            run=None,
            output_path=None,
            message=f"failed to persist enriched authoring run: {exc}",
            failure_reason_counts=reason_counts,
            retrieval_call_count=retrieval_calls,
        )

    exit_code = 0 if success_count >= 1 else 1
    return PoolJobResult(
        exit_code=exit_code,
        run=working,
        output_path=destination,
        message=(
            f"Candidate pooling completed: {success_count}/{len(targets)} "
            "cases pooled under candidate-pooling-v1"
        ),
        failure_reason_counts=reason_counts,
        retrieval_call_count=retrieval_calls,
    )
