"""Schema validation and JSON round-trip tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from offline_rag.domain import (
    Chunk,
    Citation,
    Document,
    EvaluationResult,
    ExperimentConfig,
    QueryTrace,
    RetrievalCandidate,
    RetrievalResult,
)
from offline_rag.domain.traces import TraceStatus


def _document() -> Document:
    return Document(
        document_id="doc_abc",
        source_uri="file://manual.txt",
        title="Manual",
        mime_type="text/plain",
        content_hash="hash_doc",
        ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
        parser_version="slice0",
        metadata={"lang": "en"},
    )


def test_document_roundtrip() -> None:
    doc = _document()
    restored = Document.model_validate_json(doc.model_dump_json())
    assert restored == doc


def test_chunk_rejects_inverted_pages() -> None:
    with pytest.raises(ValidationError):
        Chunk(
            chunk_id="chunk_1",
            document_id="doc_abc",
            text="hello",
            page_start=3,
            page_end=1,
            chunk_index=0,
            token_count=1,
            content_hash="hash_chunk",
        )


def test_chunk_rejects_empty_id() -> None:
    with pytest.raises(ValidationError):
        Chunk(
            chunk_id=" ",
            document_id="doc_abc",
            text="hello",
            chunk_index=0,
            token_count=1,
            content_hash="hash_chunk",
        )


def test_retrieval_candidate_requires_document_and_chunk() -> None:
    candidate = RetrievalCandidate(
        chunk_id="chunk_1",
        document_id="doc_abc",
        dense_rank=1,
        dense_score=0.9,
        retrieval_stage="dense",
    )
    result = RetrievalResult(query="what is torque?", candidates=[candidate])
    assert result.candidates[0].document_id == "doc_abc"
    restored = RetrievalResult.model_validate_json(result.model_dump_json())
    assert restored.candidates[0].chunk_id == "chunk_1"


def test_citation_requires_identities() -> None:
    citation = Citation(
        citation_id="c1",
        chunk_id="chunk_1",
        document_id="doc_abc",
        page=2,
        section_path=["Intro"],
    )
    assert citation.model_dump()["chunk_id"] == "chunk_1"
    with pytest.raises(ValidationError):
        Citation(citation_id="c1", chunk_id="", document_id="doc_abc")


def test_query_trace_roundtrip_without_generation() -> None:
    trace = QueryTrace(
        trace_id="run_123",
        query={"original": "how does hybrid retrieval help?"},
        status=TraceStatus.ABSTAINED,
        decision={"abstained": True, "reason": "insufficient evidence"},
        experiment_id="cfg_abc",
    )
    restored = QueryTrace.model_validate_json(trace.model_dump_json())
    assert restored.status == TraceStatus.ABSTAINED
    assert restored.decision.abstained is True
    assert restored.generation is None


def test_experiment_and_evaluation_roundtrip() -> None:
    experiment = ExperimentConfig(
        experiment_id="cfg_1",
        name="dense_baseline",
        config_hash="cfg_1",
        parameters={"dense": {"top_k": 10}},
    )
    result = EvaluationResult(
        evaluation_id="run_eval_1",
        experiment_id=experiment.experiment_id,
        dataset_id="gold.example",
        metrics={"recall@5": 0.5},
    )
    assert ExperimentConfig.model_validate_json(experiment.model_dump_json()) == experiment
    assert EvaluationResult.model_validate_json(result.model_dump_json()).metrics["recall@5"] == 0.5


def test_negative_token_count_rejected() -> None:
    with pytest.raises(ValidationError):
        Chunk(
            chunk_id="chunk_1",
            document_id="doc_abc",
            text="hello",
            chunk_index=0,
            token_count=-1,
            content_hash="hash_chunk",
        )
