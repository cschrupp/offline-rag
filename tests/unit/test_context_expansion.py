"""Slice 7 hybrid-rerank-context unit tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config.models import AppSettings, ContextSettings
from offline_rag.context.assemble import (
    HybridRerankContextAssembler,
    HybridRerankContextError,
)
from offline_rag.context.clip import (
    clipped_evidence_unit_id,
    full_evidence_unit_id,
    locate_anchor_in_parent,
    try_emit_parent,
)
from offline_rag.context.config_hash import (
    build_context_config_hash,
    build_context_semantic_payload,
)
from offline_rag.context.contracts import (
    ASSEMBLY_CONTRACT,
    CLIP_CONTRACT,
    CONTAINMENT_CONTRACT,
    DEDUP_CONTRACT,
    NEIGHBOR_CONTRACT,
    RENDER_CONTRACT,
)
from offline_rag.context.expand import ContextExpander
from offline_rag.context.render import render_plain_evidence
from offline_rag.context.status import context_status_for_corpus
from offline_rag.context.store import ChunkStructureStore, ContextStructureError
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import (
    HybridRerankCandidate,
    HybridRerankProvenance,
    HybridRerankRetrievalResult,
)


def _chunk(
    chunk_id: str,
    text: str,
    *,
    kind: ChunkKind = ChunkKind.CHILD,
    document_id: str = "doc1",
    parent_chunk_id: str | None = None,
    previous_chunk_id: str | None = None,
    next_chunk_id: str | None = None,
    order: int = 0,
    metadata: dict[str, Any] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        kind=kind,
        parent_chunk_id=parent_chunk_id,
        text=text,
        order=order,
        token_count=max(len(text.split()), 1),
        content_hash=f"hash_{chunk_id}",
        source_block_ids=[f"block_{chunk_id}"],
        previous_chunk_id=previous_chunk_id,
        next_chunk_id=next_chunk_id,
        metadata=metadata or {},
    )


def _anchor(chunk_id: str, rank: int, text: str) -> HybridRerankCandidate:
    return HybridRerankCandidate(
        rank=rank,
        score=1.0 / rank,
        chunk_id=chunk_id,
        document_id="doc1",
        text=text,
        hybrid_rerank=HybridRerankProvenance(
            reranker_score=1.0 / rank,
            hybrid_rank=rank,
            rrf_score=0.01,
            dense_rank=rank,
            dense_score=0.9,
        ),
    )


def _store_parent_chain() -> ChunkStructureStore:
    # Parent contains LEFT ANCHOR RIGHT with unique anchor text.
    parent_text = "LEFT ANCHOR RIGHT EXTRA"
    parent = _chunk("parent_a", parent_text, kind=ChunkKind.PARENT, order=0)
    c0 = _chunk(
        "child_0",
        "LEFT",
        parent_chunk_id="parent_a",
        next_chunk_id="child_1",
        order=0,
    )
    c1 = _chunk(
        "child_1",
        "ANCHOR",
        parent_chunk_id="parent_a",
        previous_chunk_id="child_0",
        next_chunk_id="child_2",
        order=1,
    )
    c2 = _chunk(
        "child_2",
        "RIGHT",
        parent_chunk_id="parent_a",
        previous_chunk_id="child_1",
        next_chunk_id="child_3",
        order=2,
    )
    c3 = _chunk(
        "child_3",
        "EXTRA",
        parent_chunk_id="parent_a",
        previous_chunk_id="child_2",
        order=3,
    )
    # Second parent/doc for cross-parent neighbor tests.
    parent_b = _chunk(
        "parent_b",
        "OTHER CHILDX",
        kind=ChunkKind.PARENT,
        document_id="doc2",
        order=0,
    )
    cb = _chunk(
        "child_x",
        "CHILDX",
        document_id="doc2",
        parent_chunk_id="parent_b",
        order=0,
    )
    return ChunkStructureStore(
        children={
            c0.chunk_id: c0,
            c1.chunk_id: c1,
            c2.chunk_id: c2,
            c3.chunk_id: c3,
            cb.chunk_id: cb,
        },
        parents={parent.chunk_id: parent, parent_b.chunk_id: parent_b},
        chunk_set_id="chunkset_test",
        corpus_id="corpus_test",
    )


def test_context_settings_validation() -> None:
    ContextSettings()
    with pytest.raises(ValidationError):
        ContextSettings(strategy="parent", neighbor_window=1)
    with pytest.raises(ValidationError):
        ContextSettings(strategy="neighbors", neighbor_window=0)
    with pytest.raises(ValidationError):
        ContextSettings(strategy="nope")
    with pytest.raises(ValidationError):
        ContextSettings.model_validate(
            {
                "enabled": True,
                "strategy": "parent",
                "anchor_k": 5,
                "max_context_tokens": 6000,
                "neighbor_window": 0,
                "render_contract": "plain-evidence-v1",
            }
        )


def test_context_config_hash_parent_baseline_and_conditionals() -> None:
    settings = AppSettings()
    counter = FakeTokenCounter()
    payload = build_context_semantic_payload(settings, token_counter=counter)
    assert payload["strategy"] == "parent"
    assert payload["anchor_k"] == 5
    assert payload["assembly_contract"] == ASSEMBLY_CONTRACT
    assert payload["clip_contract"] == CLIP_CONTRACT
    assert payload["dedup_contract"] == DEDUP_CONTRACT
    assert payload["render_contract"] == RENDER_CONTRACT
    assert "neighbor_contract" not in payload
    assert "containment_contract" not in payload
    assert "neighbor_window" not in payload
    h1 = build_context_config_hash(settings, token_counter=counter)
    assert h1.startswith("ctxcfg_")

    disabled = settings.model_copy(
        update={"context": settings.context.model_copy(update={"enabled": False})}
    )
    assert build_context_config_hash(disabled, token_counter=counter) == h1

    deeper = settings.model_copy(
        update={"context": settings.context.model_copy(update={"anchor_k": 6})}
    )
    assert build_context_config_hash(deeper, token_counter=counter) != h1

    neighbors = settings.model_copy(
        update={
            "context": settings.context.model_copy(
                update={"strategy": "neighbors", "neighbor_window": 2}
            )
        }
    )
    n_payload = build_context_semantic_payload(neighbors, token_counter=counter)
    assert n_payload["neighbor_contract"] == NEIGHBOR_CONTRACT
    assert n_payload["neighbor_window"] == 2
    assert "clip_contract" not in n_payload

    both = settings.model_copy(
        update={
            "context": settings.context.model_copy(
                update={"strategy": "parent+neighbors", "neighbor_window": 1}
            )
        }
    )
    both_payload = build_context_semantic_payload(both, token_counter=counter)
    assert both_payload["containment_contract"] == CONTAINMENT_CONTRACT
    assert both_payload["clip_contract"] == CLIP_CONTRACT
    assert both_payload["neighbor_contract"] == NEIGHBOR_CONTRACT


def test_child_only_and_joiner_budget() -> None:
    store = _store_parent_chain()
    counter = FakeTokenCounter()
    # Fake counts whitespace tokens: "LEFT"=1, "ANCHOR"=1; with joiner still 2.
    ctx = ContextSettings(
        strategy="child-only",
        anchor_k=5,
        max_context_tokens=1,
        neighbor_window=0,
    )
    expander = ContextExpander(store=store, counter=counter, context=ctx)
    result = expander.expand([_anchor("child_1", 1, "ANCHOR"), _anchor("child_0", 2, "LEFT")])
    assert len(result.evidence_units) == 1
    assert result.evidence_units[0].source_chunk_id == "child_1"
    assert result.diagnostics is not None
    assert result.diagnostics.stop_reason == "child_would_not_fit"
    assert result.assembled_text == "ANCHOR"


def test_parent_full_and_reconstruction() -> None:
    store = _store_parent_chain()
    counter = FakeTokenCounter()
    ctx = ContextSettings(strategy="parent", anchor_k=5, max_context_tokens=100)
    expander = ContextExpander(store=store, counter=counter, context=ctx)
    result = expander.expand([_anchor("child_1", 1, "ANCHOR")])
    assert len(result.evidence_units) == 1
    unit = result.evidence_units[0]
    assert unit.kind == "parent"
    assert unit.clipped is False
    assert unit.text == store.parents["parent_a"].text
    assert unit.evidence_unit_id == full_evidence_unit_id("parent_a")
    assert "reranker_score" not in unit.model_dump()
    assert render_plain_evidence(result.evidence_units) == result.assembled_text


def test_first_anchor_owns_parent_dedup() -> None:
    store = _store_parent_chain()
    counter = FakeTokenCounter()
    ctx = ContextSettings(strategy="parent", anchor_k=5, max_context_tokens=100)
    expander = ContextExpander(store=store, counter=counter, context=ctx)
    result = expander.expand(
        [_anchor("child_1", 1, "ANCHOR"), _anchor("child_2", 2, "RIGHT")]
    )
    assert len(result.evidence_units) == 1
    unit = result.evidence_units[0]
    assert unit.primary_anchor_chunk_id == "child_1"
    assert unit.contributing_anchor_chunk_ids == ["child_1", "child_2"]
    assert result.diagnostics is not None
    assert result.diagnostics.dedup_hits == 1


def test_neighbors_document_order_and_window() -> None:
    store = _store_parent_chain()
    counter = FakeTokenCounter()
    ctx = ContextSettings(
        strategy="neighbors",
        anchor_k=5,
        max_context_tokens=100,
        neighbor_window=1,
    )
    expander = ContextExpander(store=store, counter=counter, context=ctx)
    result = expander.expand([_anchor("child_1", 1, "ANCHOR")])
    ids = [unit.source_chunk_id for unit in result.evidence_units]
    assert ids == ["child_0", "child_1", "child_2"]
    assert all(unit.kind == "child" for unit in result.evidence_units)


def test_parent_neighbors_containment_suppresses_same_parent_children() -> None:
    store = _store_parent_chain()
    counter = FakeTokenCounter()
    ctx = ContextSettings(
        strategy="parent+neighbors",
        anchor_k=5,
        max_context_tokens=100,
        neighbor_window=1,
    )
    expander = ContextExpander(store=store, counter=counter, context=ctx)
    result = expander.expand([_anchor("child_1", 1, "ANCHOR")])
    assert len(result.evidence_units) == 1
    assert result.evidence_units[0].kind == "parent"
    assert result.diagnostics is not None
    assert result.diagnostics.containment_suppressions >= 1


def test_balanced_clip_growth_and_unicode() -> None:
    counter = FakeTokenCounter()
    # Force clipping with tiny budget: FakeTokenCounter counts words.
    parent = _chunk(
        "parent_u",
        "aa bb ANCHOR cc dd",
        kind=ChunkKind.PARENT,
    )
    anchor = _chunk("child_u", "ANCHOR", parent_chunk_id="parent_u")
    decision = try_emit_parent(
        parent=parent,
        anchor=anchor,
        primary_anchor_chunk_id="child_u",
        contributing=["child_u"],
        existing_assembled="",
        max_context_tokens=3,
        counter=counter,
    )
    assert decision is not None
    assert decision.clipped is True
    assert "ANCHOR" in decision.text
    assert decision.text != parent.text
    # Balanced growth includes adjacent context on both sides when budget allows.
    assert "bb" in decision.text
    assert "cc" in decision.text
    assert "aa" not in decision.text or "dd" not in decision.text

    parent_uni = _chunk("parent_uni", "pré ANCHOR après", kind=ChunkKind.PARENT)
    anchor_uni = _chunk("child_uni", "ANCHOR", parent_chunk_id="parent_uni")
    start, end = locate_anchor_in_parent(parent_uni, anchor_uni)
    assert parent_uni.text[start:end] == "ANCHOR"
    # Non-ASCII left side uses Python str indices.
    assert parent_uni.text[0:3] == "pré"


def test_repeated_anchor_text_fails_closed() -> None:
    parent = _chunk("parent_dup", "ANCHOR middle ANCHOR", kind=ChunkKind.PARENT)
    anchor = _chunk("child_dup", "ANCHOR", parent_chunk_id="parent_dup")
    with pytest.raises(ContextStructureError, match="occurs 2 times"):
        locate_anchor_in_parent(parent, anchor)


def test_evidence_unit_id_full_vs_clipped() -> None:
    full_id = full_evidence_unit_id("parent_a")
    clipped_id = clipped_evidence_unit_id(
        source_chunk_id="parent_a",
        start_char=0,
        end_char=5,
        text="hello",
    )
    assert full_id.startswith("ev_")
    assert clipped_id.startswith("ev_")
    assert full_id != clipped_id
    assert clipped_evidence_unit_id(
        source_chunk_id="parent_a",
        start_char=0,
        end_char=5,
        text="hello",
    ) == clipped_id


def test_assembler_calls_hybrid_rerank_with_anchor_k() -> None:
    settings = AppSettings().model_copy(
        update={
            "chunking": AppSettings().chunking.model_copy(
                update={
                    "tokenizer": AppSettings().chunking.tokenizer.model_copy(
                        update={"implementation": "fake"}
                    )
                }
            ),
            "reranker": AppSettings().reranker.model_copy(update={"implementation": "fake"}),
            "context": ContextSettings(enabled=True, strategy="parent", anchor_k=5),
        }
    )
    store = _store_parent_chain()
    retriever = MagicMock()
    captured: dict[str, Any] = {}

    def _retrieve(**kwargs: Any) -> HybridRerankRetrievalResult:
        captured.update(kwargs)
        return HybridRerankRetrievalResult(
            query=kwargs["query"],
            top_k=kwargs["top_k"],
            candidates=[_anchor("child_1", 1, "ANCHOR")],
            dense_index_id="dense_x",
            lexical_index_id="lex_x",
            fusion_config_hash="fuscfg_x",
            reranker_config_hash="rrkcfg_x",
            metadata={
                "chunk_set_id": "chunkset_test",
                "corpus_id": "corpus_test",
                "latency_ms": {"total": 1},
                "input_pool_chunk_ids": ["child_1"],
                "input_pool_size": 1,
            },
        )

    retriever.retrieve.side_effect = _retrieve
    assembler = HybridRerankContextAssembler(
        settings,
        retriever=retriever,
        store=store,
        token_counter=FakeTokenCounter(),
    )
    assembler._require_ready = lambda _name: None  # type: ignore[method-assign]
    result = assembler.assemble(query="pressure", corpus_name="default")
    assert captured["top_k"] == 5
    assert result.method == "hybrid-rerank-context"
    assert result.context_config_hash.startswith("ctxcfg_")
    assert len(result.anchors) == 1
    assert result.evidence_units[0].kind == "parent"
    assert "hybrid_rerank" in result.metadata["latency_ms"]
    assert "context_expand" in result.metadata["latency_ms"]
    assert "total" in result.metadata["latency_ms"]


def test_disabled_context_hard_fails() -> None:
    settings = AppSettings().model_copy(
        update={"context": ContextSettings(enabled=False)}
    )
    assembler = HybridRerankContextAssembler(
        settings,
        retriever=MagicMock(),
        store=_store_parent_chain(),
        token_counter=FakeTokenCounter(),
    )
    # Bypass shared readiness to assert explicit enabled gate inside assemble path.
    assembler._require_ready = lambda _name: None  # type: ignore[method-assign]
    with pytest.raises(HybridRerankContextError, match="context.enabled is false"):
        assembler.assemble(query="q", corpus_name="default")


def test_context_status_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AppSettings().model_copy(
        update={"context": ContextSettings(enabled=False)}
    )
    monkeypatch.setattr(
        "offline_rag.context.status.hybrid_rerank_status_for_corpus",
        lambda _s, _n: "READY",
    )
    assert context_status_for_corpus(settings, "default") == "NOT_READY"


def test_empty_anchors() -> None:
    store = _store_parent_chain()
    ctx = ContextSettings(strategy="parent", max_context_tokens=100)
    expander = ContextExpander(store=store, counter=FakeTokenCounter(), context=ctx)
    result = expander.expand([])
    assert result.evidence_units == []
    assert result.assembled_text == ""
    assert result.context_token_count == 0
    assert result.diagnostics is not None
    assert result.diagnostics.stop_reason == "no_anchors"
