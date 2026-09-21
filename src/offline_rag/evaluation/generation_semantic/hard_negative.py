"""human-grade0-hard-negative-v1 evidence builder (Slice 10D).

Label-defined hard-negative fixture: original human-reviewed query plus N=5
human grade-0 candidates selected by stored hybrid-rerank-v1 ranks. Expected
behavior under the fixture contract is abstention. This is not a mathematical
proof that the combined text can never support an answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from offline_rag.chunking.access import CorpusChunkSnapshot
from offline_rag.chunking.tokenize import FakeTokenCounter, TokenCounter
from offline_rag.context.render import render_plain_evidence
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import EvidenceUnit
from offline_rag.evaluation.generation_semantic.evidence import (
    EVIDENCE_BUDGET_EXCEEDED,
    EvidenceBudgetExceeded,
    GoldEvidenceBuildError,
    _child_chunk_index,
    _frozen_source_names,
    child_chunk_to_evidence_unit,
    compute_generation_evidence_set_id,
)
from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_EVIDENCE_SET_V1,
    HARD_NEGATIVE_N_V1,
    HARD_NEGATIVE_RETRIEVER_V1,
    HUMAN_GRADE0_HARD_NEGATIVE_V1,
    GenerationEvidenceCaseV1,
    GenerationEvidenceSetV1,
    GenerationHardNegativeSelectedCandidateV1,
    GenerationHardNegativeSelectionV1,
    GoldEvidenceJudgmentV1,
    LabelCohort,
)
from offline_rag.evaluation.gold import GoldCase, LoadedGoldDataset
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase
from offline_rag.gold_authoring.review_models import HumanReviewStatus, tags_equal


class HardNegativeBuildError(GoldEvidenceBuildError):
    """Fail-closed human-grade0-hard-negative-v1 construction error."""


def build_human_grade0_hard_negative_set_v1(
    gold: LoadedGoldDataset,
    *,
    authoring_run: GoldAuthoringRun,
    chunk_snapshot: CorpusChunkSnapshot,
    label_cohort_by_case_id: Mapping[str, LabelCohort],
    max_evidence_tokens: int,
    token_counter: TokenCounter | None = None,
    created_at: datetime | None = None,
    metadata: Mapping[str, object] | None = None,
) -> GenerationEvidenceSetV1:
    """Build a deterministic ``human-grade0-hard-negative-v1`` evidence set.

    Uses only persisted Silver human maps and stored hybrid-rerank-v1 ranks.
    No retrieval is executed.
    """
    if max_evidence_tokens < 1:
        raise HardNegativeBuildError("max_evidence_tokens must be >= 1")

    _validate_authoring_lineage(gold, authoring_run, chunk_snapshot)

    meta = gold.meta
    corpus_id = meta.corpus_id or chunk_snapshot.corpus_id
    corpus_name = meta.corpus_name or chunk_snapshot.corpus_name
    if not corpus_id or not corpus_name:
        raise HardNegativeBuildError("corpus_id and corpus_name are required")

    missing_cohort = [
        case.id for case in gold.cases if case.id not in label_cohort_by_case_id
    ]
    if missing_cohort:
        raise HardNegativeBuildError(
            "label_cohort mapping missing case_id(s): "
            + ", ".join(sorted(missing_cohort))
        )
    unknown_cohort_keys = sorted(
        set(label_cohort_by_case_id) - {case.id for case in gold.cases}
    )
    if unknown_cohort_keys:
        raise HardNegativeBuildError(
            "label_cohort mapping has unknown case_id(s): "
            + ", ".join(unknown_cohort_keys)
        )

    silver_by_id = _index_silver_cases(authoring_run)
    children_by_id = _child_chunk_index(chunk_snapshot.chunks)
    counter = token_counter or FakeTokenCounter()

    eligible_gold = sorted(
        (
            case
            for case in gold.cases
            if label_cohort_by_case_id[case.id] == "human_reviewed"
        ),
        key=lambda item: item.id,
    )
    if not eligible_gold:
        raise HardNegativeBuildError(
            "no human_reviewed cases eligible for hard-negative fixture"
        )

    built_cases: list[GenerationEvidenceCaseV1] = []
    for gold_case in eligible_gold:
        silver = silver_by_id.get(gold_case.id)
        if silver is None:
            raise HardNegativeBuildError(
                f"Gold case {gold_case.id} absent from authoring-run Silver cases"
            )
        built_cases.append(
            _build_hard_negative_case(
                gold_case,
                silver,
                authoring_run_id=authoring_run.authoring_run_id,
                children_by_id=children_by_id,
                max_evidence_tokens=max_evidence_tokens,
                token_counter=counter,
            )
        )

    stamp = created_at or datetime.now(tz=UTC)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)

    source_name_by_document_id = _frozen_source_names(
        built_cases, chunk_snapshot.source_name_by_document_id
    )
    evidence_set_id = compute_generation_evidence_set_id(
        evidence_contract=HUMAN_GRADE0_HARD_NEGATIVE_V1,
        source_gold_dataset_id=gold.dataset_id,
        chunk_set_id=chunk_snapshot.chunk_set_id,
        corpus_id=corpus_id,
        corpus_name=corpus_name,
        cases=built_cases,
        source_name_by_document_id=source_name_by_document_id,
        expected_behavior="abstain",
    )
    return GenerationEvidenceSetV1(
        schema_version=GENERATION_EVIDENCE_SET_V1,
        evidence_set_id=evidence_set_id,
        evidence_contract=HUMAN_GRADE0_HARD_NEGATIVE_V1,
        expected_behavior="abstain",
        source_gold_dataset_id=gold.dataset_id,
        chunk_set_id=chunk_snapshot.chunk_set_id,
        corpus_id=corpus_id,
        corpus_name=corpus_name,
        source_name_by_document_id=source_name_by_document_id,
        cases=built_cases,
        created_at=stamp,
        metadata=dict(metadata or {}),
    )


def _validate_authoring_lineage(
    gold: LoadedGoldDataset,
    run: GoldAuthoringRun,
    chunk_snapshot: CorpusChunkSnapshot,
) -> None:
    if not gold.dataset_id or not str(gold.dataset_id).strip():
        raise HardNegativeBuildError("GoldDataset.dataset_id is required")

    meta = gold.meta
    recorded = meta.metadata.get("authoring_run_id") if meta.metadata else None
    if recorded is not None:
        recorded_text = str(recorded).strip()
        if recorded_text and recorded_text != run.authoring_run_id:
            raise HardNegativeBuildError(
                "authoring_run_id mismatch: "
                f"gold.metadata.authoring_run_id={recorded_text!r} "
                f"run={run.authoring_run_id!r}"
            )

    if meta.chunk_set_id != run.chunk_set_id:
        raise HardNegativeBuildError(
            "chunk_set_id mismatch: "
            f"gold={meta.chunk_set_id!r} authoring_run={run.chunk_set_id!r}"
        )
    if meta.chunk_set_id != chunk_snapshot.chunk_set_id:
        raise HardNegativeBuildError(
            "chunk_set_id mismatch: "
            f"gold={meta.chunk_set_id!r} snapshot={chunk_snapshot.chunk_set_id!r}"
        )
    if run.chunk_set_id != chunk_snapshot.chunk_set_id:
        raise HardNegativeBuildError(
            "chunk_set_id mismatch: "
            f"authoring_run={run.chunk_set_id!r} "
            f"snapshot={chunk_snapshot.chunk_set_id!r}"
        )

    if (
        meta.corpus_id is not None
        and run.corpus_id is not None
        and meta.corpus_id != run.corpus_id
    ):
        raise HardNegativeBuildError(
            "corpus_id mismatch: "
            f"gold={meta.corpus_id!r} authoring_run={run.corpus_id!r}"
        )
    if (
        meta.corpus_name is not None
        and run.corpus_name is not None
        and meta.corpus_name != run.corpus_name
    ):
        raise HardNegativeBuildError(
            "corpus_name mismatch: "
            f"gold={meta.corpus_name!r} authoring_run={run.corpus_name!r}"
        )
    if meta.corpus_id is not None and meta.corpus_id != chunk_snapshot.corpus_id:
        raise HardNegativeBuildError(
            "corpus_id mismatch: "
            f"gold={meta.corpus_id!r} snapshot={chunk_snapshot.corpus_id!r}"
        )
    if meta.corpus_name is not None and meta.corpus_name != chunk_snapshot.corpus_name:
        raise HardNegativeBuildError(
            "corpus_name mismatch: "
            f"gold={meta.corpus_name!r} snapshot={chunk_snapshot.corpus_name!r}"
        )


def _index_silver_cases(run: GoldAuthoringRun) -> dict[str, SilverCase]:
    by_id: dict[str, SilverCase] = {}
    for case in run.cases:
        if case.draft_case_id in by_id:
            raise HardNegativeBuildError(
                f"duplicate Silver case draft_case_id: {case.draft_case_id}"
            )
        by_id[case.draft_case_id] = case
    return by_id


def _build_hard_negative_case(
    gold_case: GoldCase,
    silver: SilverCase,
    *,
    authoring_run_id: str,
    children_by_id: dict[str, Chunk],
    max_evidence_tokens: int,
    token_counter: TokenCounter,
) -> GenerationEvidenceCaseV1:
    _validate_silver_review_integrity(gold_case, silver)
    _reconcile_positive_maps(gold_case, silver)

    selected, eligible_count = _select_hard_negatives(
        gold_case, silver, children_by_id=children_by_id
    )
    assert silver.human_review is not None
    grade_basis = silver.human_review.grade_basis_query
    if grade_basis is None or not str(grade_basis).strip():
        raise HardNegativeBuildError(
            f"case {gold_case.id}: grade_basis_query is required"
        )

    selection = GenerationHardNegativeSelectionV1(
        selection_contract=HUMAN_GRADE0_HARD_NEGATIVE_V1,
        authoring_run_id=authoring_run_id,
        source_silver_case_id=silver.draft_case_id,
        grade_basis_query=grade_basis,
        retriever=HARD_NEGATIVE_RETRIEVER_V1,
        requested_count=HARD_NEGATIVE_N_V1,
        selected_candidates=selected,
        candidate_pool_size=len(silver.candidates),
        eligible_grade0_hard_candidate_count=eligible_count,
    )

    # Presentation order: source-oriented, independent of retrieval rank.
    presentation_chunks = [children_by_id[item.chunk_id] for item in selected]
    presentation_chunks.sort(
        key=lambda chunk: (chunk.document_id, chunk.order, chunk.chunk_id)
    )

    units: list[EvidenceUnit] = []
    seen_evidence_ids: set[str] = set()
    for chunk in presentation_chunks:
        unit = child_chunk_to_evidence_unit(chunk)
        if unit.evidence_unit_id in seen_evidence_ids:
            raise HardNegativeBuildError(
                f"evidence identity collision in case {gold_case.id}: "
                f"{unit.evidence_unit_id}"
            )
        seen_evidence_ids.add(unit.evidence_unit_id)
        units.append(unit)

    assembled = render_plain_evidence(units)
    token_count = token_counter.count(assembled) if assembled else 0
    if token_count > max_evidence_tokens:
        raise EvidenceBudgetExceeded(
            f"{EVIDENCE_BUDGET_EXCEEDED}: case={gold_case.id} "
            f"tokens={token_count} max={max_evidence_tokens}",
            case_id=gold_case.id,
            token_count=token_count,
            max_tokens=max_evidence_tokens,
        )

    gold_judgments = [
        GoldEvidenceJudgmentV1(chunk_id=j.chunk_id, relevance=j.relevance)
        for j in sorted(gold_case.judgments, key=lambda item: item.chunk_id)
    ]

    evidence_ids = {unit.source_chunk_id for unit in units}
    gold_positive_ids = {j.chunk_id for j in gold_judgments}
    leaked = evidence_ids & gold_positive_ids
    if leaked:
        raise HardNegativeBuildError(
            f"case {gold_case.id}: positive gold chunk(s) leaked into "
            f"hard-negative evidence: {sorted(leaked)}"
        )
    selected_grades = {item.chunk_id: item.human_relevance for item in selected}
    for chunk_id in evidence_ids:
        if selected_grades.get(chunk_id) != 0:
            raise HardNegativeBuildError(
                f"case {gold_case.id}: presented chunk {chunk_id} is not "
                "human relevance 0"
            )

    return GenerationEvidenceCaseV1(
        case_id=gold_case.id,
        query=gold_case.query,
        category=gold_case.category,
        tags=list(gold_case.tags),
        label_cohort="human_reviewed",
        expected_behavior="abstain",
        evidence_units=units,
        gold_judgments=gold_judgments,
        hard_negative_selection=selection,
    )


def _validate_silver_review_integrity(gold_case: GoldCase, silver: SilverCase) -> None:
    status = silver.human_status
    if status not in (HumanReviewStatus.ACCEPTED, HumanReviewStatus.EDITED):
        raise HardNegativeBuildError(
            f"case {gold_case.id}: Silver human_status must be accepted/edited; "
            f"got {status.value}"
        )
    if silver.human_review is None:
        raise HardNegativeBuildError(
            f"case {gold_case.id}: Silver human_review is required"
        )
    if not silver.review_complete():
        raise HardNegativeBuildError(
            f"case {gold_case.id}: Silver human map is incomplete relative to "
            "9C candidate pool"
        )

    # Judgments must not reference candidates outside the pool.
    candidate_ids = {c.chunk_id for c in silver.candidates}
    judged_ids = {j.chunk_id for j in silver.human_review.judgments}
    unknown = judged_ids - candidate_ids
    if unknown:
        raise HardNegativeBuildError(
            f"case {gold_case.id}: human judgment for unknown candidate "
            f"chunk_id(s): {sorted(unknown)}"
        )

    effective_query = silver.effective_query()
    if effective_query is None or not str(effective_query).strip():
        raise HardNegativeBuildError(
            f"case {gold_case.id}: Silver effective_query is required"
        )
    if effective_query != gold_case.query:
        raise HardNegativeBuildError(
            f"case {gold_case.id}: effective_query mismatch: "
            f"silver={effective_query!r} gold={gold_case.query!r}"
        )
    if silver.human_review.grade_basis_query != effective_query:
        raise HardNegativeBuildError(
            f"case {gold_case.id}: grade_basis_query must equal effective_query"
        )
    if silver.effective_category() != gold_case.category:
        raise HardNegativeBuildError(
            f"case {gold_case.id}: category mismatch: "
            f"silver={silver.effective_category()!r} gold={gold_case.category!r}"
        )
    if not tags_equal(silver.effective_tags(), gold_case.tags):
        raise HardNegativeBuildError(
            f"case {gold_case.id}: tags mismatch between Silver and Gold"
        )


def _reconcile_positive_maps(gold_case: GoldCase, silver: SilverCase) -> None:
    assert silver.human_review is not None
    silver_positives = sorted(
        (
            (j.chunk_id, int(j.relevance))
            for j in silver.human_review.judgments
            if int(j.relevance) >= 1
        ),
        key=lambda item: item[0],
    )
    gold_positives = sorted(
        ((j.chunk_id, int(j.relevance)) for j in gold_case.judgments),
        key=lambda item: item[0],
    )
    if silver_positives != gold_positives:
        raise HardNegativeBuildError(
            f"case {gold_case.id}: Silver positive map != GoldDataset positives "
            f"(silver={silver_positives} gold={gold_positives})"
        )


def _select_hard_negatives(
    gold_case: GoldCase,
    silver: SilverCase,
    *,
    children_by_id: dict[str, Chunk],
) -> tuple[list[GenerationHardNegativeSelectedCandidateV1], int]:
    assert silver.human_review is not None
    grade_by_id = {j.chunk_id: int(j.relevance) for j in silver.human_review.judgments}
    gold_positive_ids = {j.chunk_id for j in gold_case.judgments}
    candidates_by_id = {c.chunk_id: c for c in silver.candidates}

    eligible: list[tuple[int, str]] = []
    for chunk_id, grade in grade_by_id.items():
        if grade != 0:
            continue
        if chunk_id in gold_positive_ids:
            raise HardNegativeBuildError(
                f"case {gold_case.id}: chunk {chunk_id} is human grade 0 but "
                "also a Gold positive (incoherent map)"
            )
        candidate = candidates_by_id.get(chunk_id)
        if candidate is None:
            raise HardNegativeBuildError(
                f"case {gold_case.id}: graded chunk {chunk_id} missing from "
                "candidate pool"
            )
        hits = [
            hit
            for hit in candidate.retrieval_hits
            if hit.retriever == HARD_NEGATIVE_RETRIEVER_V1
        ]
        if len(hits) > 1:
            raise HardNegativeBuildError(
                f"case {gold_case.id}: duplicate {HARD_NEGATIVE_RETRIEVER_V1} "
                f"hits for chunk_id={chunk_id}"
            )
        if not hits:
            continue
        hit = hits[0]
        chunk = children_by_id.get(chunk_id)
        if chunk is None:
            raise HardNegativeBuildError(
                f"case {gold_case.id}: hard-negative chunk_id absent from "
                f"historical chunk set: {chunk_id}"
            )
        if chunk.kind != ChunkKind.CHILD:
            raise HardNegativeBuildError(
                f"case {gold_case.id}: hard-negative chunk is not a child "
                f"(chunk_id={chunk_id}, kind={chunk.kind})"
            )
        eligible.append((int(hit.rank), chunk_id))

    eligible.sort(key=lambda item: (item[0], item[1]))
    if len(eligible) < HARD_NEGATIVE_N_V1:
        raise HardNegativeBuildError(
            f"case {gold_case.id}: fewer than {HARD_NEGATIVE_N_V1} eligible "
            f"grade-0 hybrid-rerank hard negatives "
            f"(eligible={len(eligible)})"
        )

    selected_rows = eligible[:HARD_NEGATIVE_N_V1]
    selected = [
        GenerationHardNegativeSelectedCandidateV1(
            chunk_id=chunk_id,
            human_relevance=0,
            retriever=HARD_NEGATIVE_RETRIEVER_V1,
            rank=rank,
        )
        for rank, chunk_id in selected_rows
    ]
    return selected, len(eligible)
