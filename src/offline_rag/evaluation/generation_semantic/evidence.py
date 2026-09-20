"""gold-evidence-v1 builder and evidence-set identity (Slice 10A)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from offline_rag.chunking.access import CorpusChunkSnapshot
from offline_rag.chunking.tokenize import FakeTokenCounter, TokenCounter
from offline_rag.context.clip import full_evidence_unit_id
from offline_rag.context.render import render_plain_evidence
from offline_rag.core.ids import generation_evidence_set_id_from_payload
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import EvidenceUnit
from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_EVIDENCE_SET_V1,
    GenerationEvidenceCaseV1,
    GenerationEvidenceSetV1,
    GoldEvidenceJudgmentV1,
    LabelCohort,
)
from offline_rag.evaluation.gold import GoldCase, LoadedGoldDataset

GOLD_EVIDENCE_V1 = "gold-evidence-v1"
EVIDENCE_BUDGET_EXCEEDED = "evidence_budget_exceeded"


class GoldEvidenceBuildError(ValueError):
    """Fail-closed gold-evidence-v1 construction error."""


class EvidenceBudgetExceeded(GoldEvidenceBuildError):
    """Ordered evidence exceeds the configured evidence token budget."""

    def __init__(
        self,
        message: str,
        *,
        case_id: str,
        token_count: int,
        max_tokens: int,
    ) -> None:
        super().__init__(message)
        self.reason = EVIDENCE_BUDGET_EXCEEDED
        self.case_id = case_id
        self.token_count = token_count
        self.max_tokens = max_tokens


def build_gold_evidence_set_v1(
    gold: LoadedGoldDataset,
    *,
    chunk_snapshot: CorpusChunkSnapshot,
    label_cohort_by_case_id: Mapping[str, LabelCohort],
    max_evidence_tokens: int,
    token_counter: TokenCounter | None = None,
    created_at: datetime | None = None,
    metadata: Mapping[str, object] | None = None,
) -> GenerationEvidenceSetV1:
    """Build a deterministic ``gold-evidence-v1`` evidence set.

    ``created_at`` is recorded on the artifact but excluded from
    ``evidence_set_id`` semantic identity.
    """
    if max_evidence_tokens < 1:
        raise GoldEvidenceBuildError("max_evidence_tokens must be >= 1")

    meta = gold.meta
    if meta.chunk_set_id != chunk_snapshot.chunk_set_id:
        raise GoldEvidenceBuildError(
            "chunk_set_id mismatch: "
            f"gold={meta.chunk_set_id} snapshot={chunk_snapshot.chunk_set_id}"
        )
    if meta.corpus_id is not None and meta.corpus_id != chunk_snapshot.corpus_id:
        raise GoldEvidenceBuildError(
            "corpus_id mismatch: "
            f"gold={meta.corpus_id} snapshot={chunk_snapshot.corpus_id}"
        )
    if meta.corpus_name is not None and meta.corpus_name != chunk_snapshot.corpus_name:
        raise GoldEvidenceBuildError(
            "corpus_name mismatch: "
            f"gold={meta.corpus_name} snapshot={chunk_snapshot.corpus_name}"
        )

    corpus_id = meta.corpus_id or chunk_snapshot.corpus_id
    corpus_name = meta.corpus_name or chunk_snapshot.corpus_name
    if not corpus_id or not corpus_name:
        raise GoldEvidenceBuildError("corpus_id and corpus_name are required")

    children_by_id = _child_chunk_index(chunk_snapshot.chunks)
    counter = token_counter or FakeTokenCounter()

    missing_cohort = [
        case.id for case in gold.cases if case.id not in label_cohort_by_case_id
    ]
    if missing_cohort:
        raise GoldEvidenceBuildError(
            "label_cohort mapping missing case_id(s): "
            + ", ".join(sorted(missing_cohort))
        )

    unknown_cohort_keys = sorted(
        set(label_cohort_by_case_id) - {case.id for case in gold.cases}
    )
    if unknown_cohort_keys:
        raise GoldEvidenceBuildError(
            "label_cohort mapping has unknown case_id(s): "
            + ", ".join(unknown_cohort_keys)
        )

    # Stable case order: GoldCase.id ascending (identity input order independent).
    ordered_cases = sorted(gold.cases, key=lambda item: item.id)
    built_cases: list[GenerationEvidenceCaseV1] = []
    for case in ordered_cases:
        built_cases.append(
            _build_case(
                case,
                children_by_id=children_by_id,
                label_cohort=label_cohort_by_case_id[case.id],
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
        evidence_contract=GOLD_EVIDENCE_V1,
        source_gold_dataset_id=gold.dataset_id,
        chunk_set_id=chunk_snapshot.chunk_set_id,
        corpus_id=corpus_id,
        corpus_name=corpus_name,
        cases=built_cases,
        source_name_by_document_id=source_name_by_document_id,
    )
    return GenerationEvidenceSetV1(
        schema_version=GENERATION_EVIDENCE_SET_V1,
        evidence_set_id=evidence_set_id,
        evidence_contract=GOLD_EVIDENCE_V1,
        source_gold_dataset_id=gold.dataset_id,
        chunk_set_id=chunk_snapshot.chunk_set_id,
        corpus_id=corpus_id,
        corpus_name=corpus_name,
        source_name_by_document_id=source_name_by_document_id,
        cases=built_cases,
        created_at=stamp,
        metadata=dict(metadata or {}),
    )


def compute_generation_evidence_set_id(
    *,
    evidence_contract: str,
    source_gold_dataset_id: str,
    chunk_set_id: str,
    corpus_id: str,
    corpus_name: str,
    cases: list[GenerationEvidenceCaseV1],
    source_name_by_document_id: Mapping[str, str],
) -> str:
    return generation_evidence_set_id_from_payload(
        generation_evidence_semantic_payload(
            evidence_contract=evidence_contract,
            source_gold_dataset_id=source_gold_dataset_id,
            chunk_set_id=chunk_set_id,
            corpus_id=corpus_id,
            corpus_name=corpus_name,
            cases=cases,
            source_name_by_document_id=source_name_by_document_id,
        )
    )


def generation_evidence_semantic_payload(
    *,
    evidence_contract: str,
    source_gold_dataset_id: str,
    chunk_set_id: str,
    corpus_id: str,
    corpus_name: str,
    cases: list[GenerationEvidenceCaseV1],
    source_name_by_document_id: Mapping[str, str],
) -> dict[str, object]:
    """Canonical semantic payload for ``genevidence_`` identity (no created_at)."""
    case_payloads: list[dict[str, object]] = []
    for case in cases:
        case_payloads.append(
            {
                "case_id": case.case_id,
                "query": case.query,
                "category": case.category,
                "tags": list(case.tags),
                "label_cohort": case.label_cohort,
                "evidence_units": [
                    _evidence_unit_semantic(unit) for unit in case.evidence_units
                ],
                "gold_judgments": [
                    {"chunk_id": j.chunk_id, "relevance": int(j.relevance)}
                    for j in case.gold_judgments
                ],
            }
        )
    source_rows = [
        {"document_id": doc_id, "source_name": source_name_by_document_id[doc_id]}
        for doc_id in sorted(source_name_by_document_id)
    ]
    return {
        "schema_version": GENERATION_EVIDENCE_SET_V1,
        "evidence_contract": evidence_contract,
        "source_gold_dataset_id": source_gold_dataset_id,
        "chunk_set_id": chunk_set_id,
        "corpus_id": corpus_id,
        "corpus_name": corpus_name,
        "source_name_by_document_id": source_rows,
        "cases": case_payloads,
    }


def _frozen_source_names(
    cases: list[GenerationEvidenceCaseV1],
    snapshot_sources: Mapping[str, str],
) -> dict[str, str]:
    doc_ids = sorted(
        {unit.document_id for case in cases for unit in case.evidence_units}
    )
    frozen: dict[str, str] = {}
    for doc_id in doc_ids:
        if doc_id not in snapshot_sources:
            raise GoldEvidenceBuildError(
                f"authoritative source_name missing for document_id={doc_id}"
            )
        source_name = snapshot_sources[doc_id]
        if source_name is None or not str(source_name).strip():
            raise GoldEvidenceBuildError(
                f"authoritative source_name blank for document_id={doc_id}"
            )
        frozen[doc_id] = str(source_name)
    return frozen


def _evidence_unit_semantic(unit: EvidenceUnit) -> dict[str, object]:
    return {
        "evidence_unit_id": unit.evidence_unit_id,
        "source_chunk_id": unit.source_chunk_id,
        "kind": unit.kind,
        "text": unit.text,
        "clipped": unit.clipped,
        "token_count": int(unit.token_count),
        "primary_anchor_chunk_id": unit.primary_anchor_chunk_id,
        "contributing_anchor_chunk_ids": list(unit.contributing_anchor_chunk_ids),
        "document_id": unit.document_id,
        "parent_chunk_id": unit.parent_chunk_id,
        "section_path": list(unit.section_path),
        "page_start": unit.page_start,
        "page_end": unit.page_end,
        "line_start": unit.line_start,
        "line_end": unit.line_end,
        "clip": None if unit.clip is None else unit.clip.model_dump(mode="json"),
        "relationship": unit.relationship,
        "distance": unit.distance,
        # Explicitly omit unit.metadata — never carry grade leakage.
    }


def _child_chunk_index(chunks: list[Chunk]) -> dict[str, Chunk]:
    by_id: dict[str, Chunk] = {}
    for chunk in chunks:
        if chunk.chunk_id in by_id:
            raise GoldEvidenceBuildError(
                f"duplicate chunk_id in chunk snapshot: {chunk.chunk_id}"
            )
        by_id[chunk.chunk_id] = chunk
    return by_id


def _build_case(
    case: GoldCase,
    *,
    children_by_id: dict[str, Chunk],
    label_cohort: LabelCohort,
    max_evidence_tokens: int,
    token_counter: TokenCounter,
) -> GenerationEvidenceCaseV1:
    if not case.judgments:
        raise GoldEvidenceBuildError(f"case {case.id} has no positive gold judgments")

    selected: list[tuple[Chunk, int]] = []
    seen_chunk_ids: set[str] = set()
    for judgment in case.judgments:
        if judgment.chunk_id in seen_chunk_ids:
            raise GoldEvidenceBuildError(
                f"duplicate gold chunk_id in case {case.id}: {judgment.chunk_id}"
            )
        seen_chunk_ids.add(judgment.chunk_id)
        chunk = children_by_id.get(judgment.chunk_id)
        if chunk is None:
            raise GoldEvidenceBuildError(
                f"gold chunk_id absent from historical chunk set "
                f"(case={case.id}, chunk_id={judgment.chunk_id})"
            )
        if chunk.kind != ChunkKind.CHILD:
            raise GoldEvidenceBuildError(
                f"gold chunk is not a child "
                f"(case={case.id}, chunk_id={judgment.chunk_id}, kind={chunk.kind})"
            )
        selected.append((chunk, int(judgment.relevance)))

    selected.sort(
        key=lambda item: (item[0].document_id, item[0].order, item[0].chunk_id)
    )

    units: list[EvidenceUnit] = []
    seen_evidence_ids: set[str] = set()
    judgments_meta: list[GoldEvidenceJudgmentV1] = []
    for chunk, relevance in selected:
        unit = _chunk_to_evidence_unit(chunk)
        if unit.evidence_unit_id in seen_evidence_ids:
            raise GoldEvidenceBuildError(
                f"evidence identity collision in case {case.id}: "
                f"{unit.evidence_unit_id}"
            )
        seen_evidence_ids.add(unit.evidence_unit_id)
        units.append(unit)
        judgments_meta.append(
            GoldEvidenceJudgmentV1(chunk_id=chunk.chunk_id, relevance=relevance)  # type: ignore[arg-type]
        )

    assembled = render_plain_evidence(units)
    token_count = token_counter.count(assembled) if assembled else 0
    if token_count > max_evidence_tokens:
        raise EvidenceBudgetExceeded(
            f"{EVIDENCE_BUDGET_EXCEEDED}: case={case.id} "
            f"tokens={token_count} max={max_evidence_tokens}",
            case_id=case.id,
            token_count=token_count,
            max_tokens=max_evidence_tokens,
        )

    return GenerationEvidenceCaseV1(
        case_id=case.id,
        query=case.query,
        category=case.category,
        tags=list(case.tags),
        label_cohort=label_cohort,
        evidence_units=units,
        gold_judgments=judgments_meta,
    )


def _chunk_to_evidence_unit(chunk: Chunk) -> EvidenceUnit:
    return EvidenceUnit(
        evidence_unit_id=full_evidence_unit_id(chunk.chunk_id),
        source_chunk_id=chunk.chunk_id,
        kind="child",
        text=chunk.text,
        clipped=False,
        token_count=int(chunk.token_count),
        primary_anchor_chunk_id=chunk.chunk_id,
        contributing_anchor_chunk_ids=[chunk.chunk_id],
        document_id=chunk.document_id,
        parent_chunk_id=chunk.parent_chunk_id,
        section_path=list(chunk.section_path),
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        line_start=chunk.line_start,
        line_end=chunk.line_end,
        clip=None,
        relationship=None,
        distance=None,
        metadata={},
    )
