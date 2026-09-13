"""Unit tests for core document-title-v1 and section-path primitives."""

from __future__ import annotations

import pytest

from offline_rag.core.document_metadata import (
    DocumentMetadataError,
    render_section_path_v1,
    resolve_document_title_v1,
)
from offline_rag.retrieval.ranking_text import (
    RankingTextInputs,
    render_title_section_text_v1,
)


def test_document_title_v1_standard_pdf() -> None:
    assert (
        resolve_document_title_v1("Module 1 Incident Scene Decision Making SM.pdf")
        == "Module 1 Incident Scene Decision Making SM"
    )


def test_section_path_normalization() -> None:
    assert (
        render_section_path_v1(
            [" INCIDENT SCENE DECISION MAKING ", "", "  INTRODUCTION  "]
        )
        == "INCIDENT SCENE DECISION MAKING / INTRODUCTION"
    )


def test_section_path_empty() -> None:
    assert render_section_path_v1([]) is None
    assert render_section_path_v1(["", "  "]) is None


def test_empty_title_fails() -> None:
    with pytest.raises(DocumentMetadataError):
        resolve_document_title_v1("   ")


def test_ranking_envelope_unchanged_after_relocation() -> None:
    body = "INTRODUCTION\nThis unit explains..."
    inputs = RankingTextInputs(
        document_title="Module 1 Incident Scene Decision Making SM",
        section_path=("INCIDENT SCENE DECISION MAKING", "INTRODUCTION"),
        chunk_text=body,
    )
    expected = (
        "DOCUMENT: Module 1 Incident Scene Decision Making SM\n"
        "SECTION: INCIDENT SCENE DECISION MAKING / INTRODUCTION\n"
        "\n"
        "INTRODUCTION\nThis unit explains..."
    )
    assert render_title_section_text_v1(inputs) == expected
