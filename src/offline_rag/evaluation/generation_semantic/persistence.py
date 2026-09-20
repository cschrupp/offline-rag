"""Evidence-set and semantic-eval result persistence (Slice 10B)."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.evaluation.generation_semantic.evidence import (
    compute_generation_evidence_set_id,
)
from offline_rag.evaluation.generation_semantic.models import (
    GenerationEvidenceSetV1,
    GenerationSemanticEvalResultV1,
)
from offline_rag.ingestion.io import atomic_write_text


class GenerationSemanticPersistenceError(RuntimeError):
    pass


def default_evidence_artifact_path(
    eval_results_root: Path, evidence_set_id: str
) -> Path:
    return (
        Path(eval_results_root)
        / "generation_semantic"
        / "evidence"
        / f"{evidence_set_id}.json"
    )


def default_result_artifact_path(eval_results_root: Path, run_id: str) -> Path:
    return (
        Path(eval_results_root) / "generation_semantic" / "results" / f"{run_id}.json"
    )


def persist_evidence_set(
    evidence_set: GenerationEvidenceSetV1,
    *,
    path: Path,
) -> Path:
    """Atomically persist evidence set; reuse if identical; fail on ID conflict."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    expected_id = compute_generation_evidence_set_id(
        evidence_contract=evidence_set.evidence_contract,
        source_gold_dataset_id=evidence_set.source_gold_dataset_id,
        chunk_set_id=evidence_set.chunk_set_id,
        corpus_id=evidence_set.corpus_id,
        corpus_name=evidence_set.corpus_name,
        cases=evidence_set.cases,
        source_name_by_document_id=evidence_set.source_name_by_document_id,
    )
    if evidence_set.evidence_set_id != expected_id:
        raise GenerationSemanticPersistenceError(
            "evidence_set_id does not match semantic payload: "
            f"artifact={evidence_set.evidence_set_id} expected={expected_id}"
        )

    if out.exists():
        try:
            existing = GenerationEvidenceSetV1.model_validate_json(
                out.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise GenerationSemanticPersistenceError(
                f"failed to load existing evidence artifact: {exc}"
            ) from exc
        if existing.evidence_set_id != evidence_set.evidence_set_id:
            raise GenerationSemanticPersistenceError(
                "existing evidence artifact ID mismatch at path"
            )
        if _semantic_evidence_equal(existing, evidence_set):
            return out
        raise GenerationSemanticPersistenceError(
            "evidence_set_id collision with differing semantic contents: "
            f"{evidence_set.evidence_set_id}"
        )

    atomic_write_text(out, evidence_set.model_dump_json())
    return out


def persist_eval_result(
    result: GenerationSemanticEvalResultV1,
    *,
    path: Path,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, result.model_dump_json())
    return out


def _semantic_evidence_equal(
    left: GenerationEvidenceSetV1, right: GenerationEvidenceSetV1
) -> bool:
    left_id = compute_generation_evidence_set_id(
        evidence_contract=left.evidence_contract,
        source_gold_dataset_id=left.source_gold_dataset_id,
        chunk_set_id=left.chunk_set_id,
        corpus_id=left.corpus_id,
        corpus_name=left.corpus_name,
        cases=left.cases,
        source_name_by_document_id=left.source_name_by_document_id,
    )
    right_id = compute_generation_evidence_set_id(
        evidence_contract=right.evidence_contract,
        source_gold_dataset_id=right.source_gold_dataset_id,
        chunk_set_id=right.chunk_set_id,
        corpus_id=right.corpus_id,
        corpus_name=right.corpus_name,
        cases=right.cases,
        source_name_by_document_id=right.source_name_by_document_id,
    )
    return left_id == right_id and left.evidence_set_id == right.evidence_set_id
