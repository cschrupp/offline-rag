"""Unit tests for dense searchable-unit / heading-peer eligibility."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from offline_rag.config.models import AppSettings, DenseSearchableUnitsSettings
from offline_rag.core.ids import ALL_CHILDREN_V1, EXCLUDE_HEADING_ONLY_V1
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.searchable_units import (
    DenseSearchableUnitsError,
    filter_dense_searchable_children,
    is_heading_only_v1,
)
from offline_rag.domain.documents import Chunk, ChunkKind


def _child(*, content_type: str, text: str, chunk_id: str = "chunk_x") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="doc_x",
        kind=ChunkKind.CHILD,
        parent_chunk_id="chunk_parent",
        text=text,
        section_path=["SECTION"],
        order=0,
        token_count=len(text.split()),
        content_type=content_type,
        content_hash="hash_x",
        source_block_ids=["block_a"],
    )


def test_is_heading_only_uses_content_type() -> None:
    assert is_heading_only_v1(_child(content_type="heading", text="RESOURCE ALLOCATION"))
    assert not is_heading_only_v1(
        _child(content_type="mixed", text="INTRODUCTION\n\nThis unit explains...")
    )
    assert not is_heading_only_v1(_child(content_type="text", text="Short prose."))


def test_is_heading_only_rejects_blank_content_type() -> None:
    chunk = Chunk.model_construct(
        chunk_id="chunk_x",
        document_id="doc_x",
        kind=ChunkKind.CHILD,
        parent_chunk_id="chunk_parent",
        text="X",
        section_path=["SECTION"],
        order=0,
        token_count=1,
        content_type="   ",
        content_hash="hash_x",
        source_block_ids=["block_a"],
        metadata={},
    )
    with pytest.raises(DenseSearchableUnitsError):
        is_heading_only_v1(chunk)


def test_searchable_units_settings_pairs() -> None:
    DenseSearchableUnitsSettings(
        strategy="exclude_heading_only", contract_version=EXCLUDE_HEADING_ONLY_V1
    )
    with pytest.raises(ValidationError):
        DenseSearchableUnitsSettings(
            strategy="exclude_heading_only", contract_version=ALL_CHILDREN_V1
        )


def test_exclude_policy_changes_index_identity_not_embedding() -> None:
    base = AppSettings()
    experimental = base.model_copy(
        update={
            "indexing": base.indexing.model_copy(
                update={
                    "searchable_units": DenseSearchableUnitsSettings(
                        strategy="exclude_heading_only",
                        contract_version=EXCLUDE_HEADING_ONLY_V1,
                    )
                }
            )
        }
    )
    assert build_embedding_config_hash(base) == build_embedding_config_hash(experimental)
    assert build_index_config_hash(base) != build_index_config_hash(experimental)
    # Default all-children preserves historical index hash identity.
    assert build_index_config_hash(base) == build_index_config_hash(AppSettings())


def test_filter_exclude_heading_only() -> None:
    heading = _child(content_type="heading", text="TITLE", chunk_id="chunk_h")
    prose = _child(content_type="mixed", text="Body text.", chunk_id="chunk_p")
    settings = AppSettings().model_copy(
        update={
            "indexing": AppSettings().indexing.model_copy(
                update={
                    "searchable_units": DenseSearchableUnitsSettings(
                        strategy="exclude_heading_only",
                        contract_version=EXCLUDE_HEADING_ONLY_V1,
                    )
                }
            )
        }
    )
    eligible, excluded = filter_dense_searchable_children(
        [(heading, "art"), (prose, "art")], settings
    )
    assert [c.chunk_id for c, _ in eligible] == ["chunk_p"]
    assert [c.chunk_id for c, _ in excluded] == ["chunk_h"]


def test_filter_all_children_keeps_headings() -> None:
    heading = _child(content_type="heading", text="TITLE", chunk_id="chunk_h")
    settings = AppSettings()
    eligible, excluded = filter_dense_searchable_children([(heading, "art")], settings)
    assert len(eligible) == 1
    assert excluded == []
