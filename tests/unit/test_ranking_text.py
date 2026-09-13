"""Unit tests for document-title-v1 and title-section-text-v1 ranking text."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.config.loader import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import DOCUMENT_TITLE_V1, TITLE_SECTION_TEXT_V1
from offline_rag.dense.config_hash import build_embedding_config_hash, build_index_config_hash
from offline_rag.dense.text import PlainEmbeddingTextBuilder, TitleSectionEmbeddingTextBuilder
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.text import PlainLexicalTextBuilder, TitleSectionLexicalTextBuilder
from offline_rag.retrieval.ranking_text import (
    RankingTextError,
    RankingTextInputs,
    ranking_inputs_for_chunk,
    render_title_section_text_v1,
    resolve_document_title_v1,
    resolve_document_titles_from_source_names,
)


def test_document_title_v1_standard_pdf() -> None:
    assert (
        resolve_document_title_v1("Module 1 Incident Scene Decision Making SM.pdf")
        == "Module 1 Incident Scene Decision Making SM"
    )


def test_document_title_v1_case_insensitive_extension() -> None:
    assert resolve_document_title_v1("Module 1.PDF") == "Module 1"


def test_document_title_v1_whitespace() -> None:
    assert (
        resolve_document_title_v1("  Module   1   Incident   Scene.pdf  ")
        == "Module 1 Incident Scene"
    )


def test_document_title_v1_path_removal() -> None:
    assert (
        resolve_document_title_v1("/private/corpus/Module 1 Incident Scene.pdf")
        == "Module 1 Incident Scene"
    )
    assert (
        resolve_document_title_v1(r"C:\documents\Module 1 Incident Scene.pdf")
        == "Module 1 Incident Scene"
    )


def test_document_title_v1_punctuation_preserved() -> None:
    assert (
        resolve_document_title_v1("Module 1 - Decision-Making (SM).pdf")
        == "Module 1 - Decision-Making (SM)"
    )


def test_document_title_v1_multi_dot_filename() -> None:
    assert resolve_document_title_v1("Module.1.final.pdf") == "Module.1.final"


def test_document_title_v1_unsupported_extension() -> None:
    assert resolve_document_title_v1("Module 1.backup") == "Module 1.backup"


def test_document_title_v1_empty_fails() -> None:
    with pytest.raises(RankingTextError):
        resolve_document_title_v1("   ")
    with pytest.raises(RankingTextError):
        resolve_document_title_v1(".pdf")


def test_source_name_authoritative_over_document_title_divergence() -> None:
    # Document.title would be "Module 1" via path.stem; ranking must keep .backup.
    title = resolve_document_title_v1("Module 1.backup")
    assert title == "Module 1.backup"
    conflicting = resolve_document_title_v1("Actual Training Module.pdf")
    assert conflicting == "Actual Training Module"


def test_resolve_titles_missing_source_fail_closed() -> None:
    with pytest.raises(RankingTextError, match="not found"):
        resolve_document_titles_from_source_names(
            document_ids={"doc_missing"},
            source_name_by_document_id={},
            require=True,
        )
    with pytest.raises(RankingTextError, match="blank"):
        resolve_document_titles_from_source_names(
            document_ids={"doc_a"},
            source_name_by_document_id={"doc_a": "  "},
            require=True,
        )


def test_resolve_titles_plain_does_not_require_source() -> None:
    titles = resolve_document_titles_from_source_names(
        document_ids={"doc_a"},
        source_name_by_document_id={},
        require=False,
    )
    assert titles == {"doc_a": None}


def test_title_section_exact_format_with_section() -> None:
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


def test_title_section_empty_section_omitted() -> None:
    body = "body text"
    out = render_title_section_text_v1(
        RankingTextInputs(
            document_title="Module 1 Incident Scene Decision Making SM",
            section_path=(),
            chunk_text=body,
        )
    )
    assert out == (
        "DOCUMENT: Module 1 Incident Scene Decision Making SM\n\nbody text"
    )
    assert "SECTION:" not in out


def test_title_section_empty_components_filtered() -> None:
    out = render_title_section_text_v1(
        RankingTextInputs(
            document_title="Title",
            section_path=(" INCIDENT SCENE DECISION MAKING ", "", "  INTRODUCTION  "),
            chunk_text="x",
        )
    )
    assert "SECTION: INCIDENT SCENE DECISION MAKING / INTRODUCTION\n\n" in out


def test_chunk_text_whitespace_preserved() -> None:
    body = "INTRODUCTION\n\nThis  unit explains   classical"
    out = render_title_section_text_v1(
        RankingTextInputs(
            document_title="Module 1",
            section_path=("INTRODUCTION",),
            chunk_text=body,
        )
    )
    assert out.endswith(body)
    assert "This  unit explains   classical" in out


def test_title_section_missing_title_fails() -> None:
    with pytest.raises(RankingTextError):
        render_title_section_text_v1(
            RankingTextInputs(document_title=None, section_path=(), chunk_text="x")
        )
    with pytest.raises(RankingTextError):
        render_title_section_text_v1(
            RankingTextInputs(document_title="  ", section_path=(), chunk_text="x")
        )


def test_plain_v1_compatibility_exact_chunk_text() -> None:
    body = "Exact  text\nwith\tspaces"
    inputs = RankingTextInputs(
        document_title=None,
        section_path=("ignored",),
        chunk_text=body,
    )
    assert PlainEmbeddingTextBuilder().build(inputs) == body
    assert PlainLexicalTextBuilder().build(inputs) == body


def test_dense_lexical_identical_envelope() -> None:
    inputs = RankingTextInputs(
        document_title="Module 1 Incident Scene Decision Making SM",
        section_path=("INCIDENT SCENE DECISION MAKING", "INTRODUCTION"),
        chunk_text="INTRODUCTION\nThis unit explains...",
    )
    dense = TitleSectionEmbeddingTextBuilder().build(inputs)
    lexical = TitleSectionLexicalTextBuilder().build(inputs)
    assert dense == lexical


def test_ranking_inputs_helper_deterministic() -> None:
    a = ranking_inputs_for_chunk(
        chunk_text="t",
        section_path=["A", "B"],
        document_title="Title",
    )
    b = ranking_inputs_for_chunk(
        chunk_text="t",
        section_path=["A", "B"],
        document_title="Title",
    )
    assert a == b


def test_resolve_once_same_title_for_siblings() -> None:
    titles = resolve_document_titles_from_source_names(
        document_ids={"doc_a"},
        source_name_by_document_id={
            "doc_a": "Module 1 Incident Scene Decision Making SM.pdf"
        },
        require=True,
    )
    assert titles["doc_a"] == "Module 1 Incident Scene Decision Making SM"
    child_a = ranking_inputs_for_chunk(
        chunk_text="a", section_path=["S"], document_title=titles["doc_a"]
    )
    child_b = ranking_inputs_for_chunk(
        chunk_text="b", section_path=["T"], document_title=titles["doc_a"]
    )
    assert child_a.document_title == child_b.document_title


def test_metadata_changes_index_identity_plain_stable() -> None:
    plain = AppSettings()
    meta = plain.model_copy(
        update={
            "indexing": plain.indexing.model_copy(
                update={
                    "embedding_text": plain.indexing.embedding_text.model_copy(
                        update={
                            "strategy": "title_section",
                            "contract_version": TITLE_SECTION_TEXT_V1,
                        }
                    )
                }
            ),
            "lexical": plain.lexical.model_copy(
                update={
                    "text": plain.lexical.text.model_copy(
                        update={
                            "strategy": "title_section",
                            "contract_version": TITLE_SECTION_TEXT_V1,
                        }
                    )
                }
            ),
        }
    )
    assert build_embedding_config_hash(plain) != build_embedding_config_hash(meta)
    assert build_index_config_hash(plain) != build_index_config_hash(meta)
    assert build_lexical_config_hash(plain) != build_lexical_config_hash(meta)
    # Recompute plain twice for stability.
    assert build_embedding_config_hash(plain) == build_embedding_config_hash(AppSettings())
    assert build_lexical_config_hash(plain) == build_lexical_config_hash(AppSettings())


def test_base_config_remains_plain() -> None:
    settings = load_settings(yaml_paths=[Path("config/base.yaml")], environ={})
    assert settings.indexing.embedding_text.strategy == "plain"
    assert settings.indexing.embedding_text.contract_version == "plain-v1"
    assert settings.lexical.text.strategy == "plain"
    assert settings.lexical.text.contract_version == "plain-v1"
    assert settings.generation.prompt.strategy == "grounded"
    assert settings.generation.prompt.contract_version == "prompt-grounded-v1"


def test_experiment_config_selects_both_branches() -> None:
    settings = load_settings(
        yaml_paths=[
            Path("config/base.yaml"),
            Path("config/experiments/title_section_ranking.yaml"),
        ],
        environ={},
    )
    assert settings.indexing.embedding_text.strategy == "title_section"
    assert settings.indexing.embedding_text.contract_version == TITLE_SECTION_TEXT_V1
    assert settings.lexical.text.strategy == "title_section"
    assert settings.lexical.text.contract_version == TITLE_SECTION_TEXT_V1
    assert settings.reranker.input_construction == "plain-pair-v1"
    assert DOCUMENT_TITLE_V1 == "document-title-v1"


def test_chunk_schema_unchanged() -> None:
    chunk = Chunk(
        chunk_id="chunk_1",
        document_id="doc_1",
        kind=ChunkKind.CHILD,
        text="Exact text",
        order=0,
        token_count=2,
        content_hash="h",
        source_block_ids=["b1"],
        section_path=["Ops"],
    )
    dumped = chunk.model_dump()
    assert "document_title" not in dumped
    assert dumped["text"] == "Exact text"
