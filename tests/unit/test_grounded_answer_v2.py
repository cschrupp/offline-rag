"""16D-B2 grounded_answer_v2 schema, handles, projection, and product path tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import GROUNDED_ANSWER_V2
from offline_rag.domain.generation import GroundedAnswerBlock
from offline_rag.domain.indexing import (
    ContextAssemblyDiagnostics,
    EvidenceUnit,
    HybridRerankContextResult,
)
from offline_rag.generation.config_hash import (
    build_generation_config_hash,
    build_product_v2_generation_config_hash,
    build_product_v2_generation_semantic_payload,
)
from offline_rag.generation.evidence_handles import assign_evidence_handles
from offline_rag.generation.excerpts import EXCERPT_MAX_CHARS, build_citation_excerpt
from offline_rag.generation.fake import FakeGenerator
from offline_rag.generation.orchestrate import GroundedAnswerOrchestrator
from offline_rag.generation.prompt import (
    SYSTEM_PROMPT_GROUNDED_ANSWER_V2,
    build_prompt_grounded_answer_v2,
)
from offline_rag.generation.prompt_evidence import PromptEvidence
from offline_rag.generation.projection_v2 import (
    assign_public_citation_refs,
    project_plain_answer,
)
from offline_rag.generation.schema_v2 import parse_grounded_answer_v2


def _unit(ev_id: str, text: str) -> EvidenceUnit:
    return EvidenceUnit(
        evidence_unit_id=ev_id,
        source_chunk_id=f"chunk_{ev_id}",
        kind="child",
        text=text,
        clipped=False,
        token_count=len(text.split()),
        primary_anchor_chunk_id="anchor_1",
        contributing_anchor_chunk_ids=["anchor_1"],
        document_id="doc1",
        section_path=["Limits"],
        page_start=3,
        page_end=3,
    )


def _context(units: list[EvidenceUnit]) -> HybridRerankContextResult:
    assembled = "\n\n".join(unit.text for unit in units)
    return HybridRerankContextResult(
        query="pressure?",
        evidence_units=units,
        assembled_text=assembled,
        context_token_count=len(assembled.split()) if assembled else 0,
        max_context_tokens=6000,
        context_config_hash="ctxcfg_test",
        anchors=[],
        dense_index_id="dense_x",
        lexical_index_id="lex_x",
        fusion_config_hash="fuscfg_x",
        reranker_config_hash="rrkcfg_x",
        diagnostics=ContextAssemblyDiagnostics(
            requested_anchor_k=5,
            actual_anchor_count=0 if not units else 1,
            evidence_unit_count=len(units),
            context_token_count=len(assembled.split()) if assembled else 0,
            stop_reason="no_anchors" if not units else "completed",
        ),
        metadata={"chunk_set_id": "chunks_x", "latency_ms": {"total": 1}},
    )


def _settings() -> AppSettings:
    return AppSettings().model_copy(
        update={
            "generation": AppSettings().generation.model_copy(
                update={
                    "enabled": True,
                    "model": "test-model",
                    "approved_models": ["test-model"],
                    "approved_endpoints": ["http://127.0.0.1:11434/v1"],
                    "base_url": "http://127.0.0.1:11434/v1",
                }
            )
        }
    )


# --- schema ---


def test_v2_parse_one_block_one_handle() -> None:
    raw = json.dumps(
        {
            "abstain": False,
            "blocks": [{"text": "Claim A", "evidence_handles": ["E1"]}],
            "abstention_reason": None,
        }
    )
    out = parse_grounded_answer_v2(raw, allowed_handles={"E1", "E2"})
    assert out.ok and out.output is not None
    assert out.output.blocks[0].evidence_handles == ["E1"]


def test_v2_parse_multiple_blocks_and_repeated_handle_across_blocks() -> None:
    raw = json.dumps(
        {
            "abstain": False,
            "blocks": [
                {"text": "A", "evidence_handles": ["E2", "E1"]},
                {"text": "B", "evidence_handles": ["E1", "E3"]},
            ],
            "abstention_reason": None,
        }
    )
    out = parse_grounded_answer_v2(raw, allowed_handles={"E1", "E2", "E3"})
    assert out.ok and out.output is not None
    assert len(out.output.blocks) == 2


@pytest.mark.parametrize(
    "reason",
    ["insufficient_support", "conflicting_evidence", "model_declined"],
)
def test_v2_parse_model_abstention_reasons(reason: str) -> None:
    raw = json.dumps(
        {"abstain": True, "blocks": [], "abstention_reason": reason}
    )
    out = parse_grounded_answer_v2(raw, allowed_handles={"E1"})
    assert out.ok and out.output is not None
    assert out.output.abstention_reason == reason


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "```json\n{}\n```",
        json.dumps({"abstain": False, "blocks": [], "abstention_reason": None, "x": 1}),
        json.dumps(
            {
                "abstain": False,
                "blocks": [{"text": "A", "evidence_handles": ["E1"], "extra": 1}],
                "abstention_reason": None,
            }
        ),
        json.dumps({"abstain": False, "blocks": [], "abstention_reason": None}),
        json.dumps(
            {
                "abstain": False,
                "blocks": [{"text": "   ", "evidence_handles": ["E1"]}],
                "abstention_reason": None,
            }
        ),
        json.dumps(
            {
                "abstain": False,
                "blocks": [{"text": "A", "evidence_handles": []}],
                "abstention_reason": None,
            }
        ),
        json.dumps(
            {
                "abstain": False,
                "blocks": [{"text": "A", "evidence_handles": ["E1", "E1"]}],
                "abstention_reason": None,
            }
        ),
        json.dumps(
            {
                "abstain": False,
                "blocks": [{"text": "A", "evidence_handles": ["E0"]}],
                "abstention_reason": None,
            }
        ),
        json.dumps(
            {
                "abstain": False,
                "blocks": [{"text": "A", "evidence_handles": ["E1"]}],
                "abstention_reason": "insufficient_support",
            }
        ),
        json.dumps(
            {
                "abstain": True,
                "blocks": [{"text": "A", "evidence_handles": ["E1"]}],
                "abstention_reason": "insufficient_support",
            }
        ),
        json.dumps({"abstain": True, "blocks": [], "abstention_reason": None}),
        json.dumps(
            {"abstain": True, "blocks": [], "abstention_reason": "no_evidence"}
        ),
        json.dumps(
            {"abstain": True, "blocks": [], "abstention_reason": "ambiguous_request"}
        ),
        json.dumps({"abstain": True, "blocks": [], "abstention_reason": "other"}),
    ],
)
def test_v2_parse_failures(raw: str) -> None:
    out = parse_grounded_answer_v2(raw, allowed_handles={"E1"})
    assert not out.ok


def test_v2_nonexistent_handle_is_citation_invalid() -> None:
    raw = json.dumps(
        {
            "abstain": False,
            "blocks": [{"text": "A", "evidence_handles": ["E9"]}],
            "abstention_reason": None,
        }
    )
    out = parse_grounded_answer_v2(raw, allowed_handles={"E1"})
    assert not out.ok
    assert out.failure_reason == "citation_invalid"


# --- handles / prompt privacy ---


def test_v2_prompt_uses_e_handles_not_canonical_ids() -> None:
    units = [
        PromptEvidence(
            evidence_unit_id="ev_secret_abc",
            document_title="Doc",
            section_path=("S",),
            text="body",
        ),
        PromptEvidence(
            evidence_unit_id="ev_secret_xyz",
            document_title="Doc",
            section_path=("S",),
            text="body2",
        ),
    ]
    req = build_prompt_grounded_answer_v2(
        user_question="Q?",
        resolved_question="Q?",
        evidence=units,
        handle_by_evidence_unit_id={
            "ev_secret_abc": "E1",
            "ev_secret_xyz": "E2",
        },
        model="m",
        temperature=0.0,
        max_output_tokens=128,
    )
    user = req.messages[1].content
    system = req.messages[0].content
    assert "[EVIDENCE E1]" in user
    assert "[EVIDENCE E2]" in user
    assert "ev_secret_abc" not in user
    assert "ev_secret_xyz" not in user
    assert "ev_secret" not in system
    assert "CURRENT USER QUESTION:" in user
    assert "RESOLVED QUESTION:" in user
    assert req.metadata["prompt_contract"] == GROUNDED_ANSWER_V2
    assert "grounded_answer_v2" in SYSTEM_PROMPT_GROUNDED_ANSWER_V2


def test_security_instruction_looking_evidence_cannot_invent_handle() -> None:
    raw = json.dumps(
        {
            "abstain": False,
            "blocks": [
                {
                    "text": "From memory",
                    "evidence_handles": ["E999"],
                }
            ],
            "abstention_reason": None,
        }
    )
    out = parse_grounded_answer_v2(raw, allowed_handles={"E1"})
    assert not out.ok
    assert out.failure_reason == "citation_invalid"


# --- projection ---


def test_block_binding_and_citation_ref_order() -> None:
    blocks = [
        GroundedAnswerBlock(text="A", evidence_unit_ids=["ev_B", "ev_A"]),
        GroundedAnswerBlock(text="B", evidence_unit_ids=["ev_A", "ev_C"]),
    ]
    public, ordered = assign_public_citation_refs(blocks)
    assert ordered == ["ev_B", "ev_A", "ev_C"]
    assert public[0].citation_refs == ["c1", "c2"]
    assert public[1].citation_refs == ["c2", "c3"]
    assert project_plain_answer(blocks) == "A\n\nB"


def test_excerpt_rules() -> None:
    short, clipped = build_citation_excerpt("hello <b>world</b>")
    assert short == "hello world"
    assert clipped is False
    long_text = "x" * (EXCERPT_MAX_CHARS + 50)
    excerpt, clipped2 = build_citation_excerpt(long_text)
    assert len(excerpt) == EXCERPT_MAX_CHARS
    assert clipped2 is True


# --- executor / orchestrator product path ---


def test_product_v2_hash_differs_from_legacy_and_marks_v2() -> None:
    settings = AppSettings()
    legacy = build_generation_config_hash(settings)
    product = build_product_v2_generation_config_hash(settings)
    assert legacy != product
    payload = build_product_v2_generation_semantic_payload(settings)
    assert payload["prompt_contract"] == GROUNDED_ANSWER_V2
    assert payload["output_contract"] == GROUNDED_ANSWER_V2


def test_product_v2_answered_path_and_empty_evidence(tmp_path, monkeypatch) -> None:
    settings = _settings()
    units = [
        _unit("ev_A", "alpha evidence"),
        _unit("ev_B", "beta evidence"),
        _unit("ev_C", "gamma evidence"),
    ]
    handle_to_id, _ = assign_evidence_handles(units)
    assert handle_to_id == {"E1": "ev_A", "E2": "ev_B", "E3": "ev_C"}

    model_out = {
        "abstain": False,
        "blocks": [
            {"text": "A", "evidence_handles": ["E2", "E1"]},
            {"text": "B", "evidence_handles": ["E1", "E3"]},
        ],
        "abstention_reason": None,
    }
    generator = FakeGenerator(default_response=json.dumps(model_out))
    assembler = MagicMock()
    assembler.assemble.return_value = _context(units)
    orch = GroundedAnswerOrchestrator(
        settings, context_assembler=assembler, generator=generator
    )
    # Bypass ready checks via check_ready=False and monkeypatch provenance load
    from offline_rag.generation import executor as executor_mod

    monkeypatch.setattr(
        executor_mod.GroundedGenerationExecutor,
        "_adapt_prompt_evidence",
        lambda self, **kwargs: [
            PromptEvidence(
                evidence_unit_id=u.evidence_unit_id,
                document_title="Doc",
                section_path=tuple(u.section_path),
                text=u.text,
            )
            for u in kwargs["evidence_units"]
        ],
    )
    result = orch.answer(
        query="What?",
        corpus_name="default",
        check_ready=False,
        product_v2=True,
        allow_recovery=False,
    )
    assert result.status == "answered"
    assert result.answer_text == "A\n\nB"
    assert [b.evidence_unit_ids for b in result.answer_blocks] == [
        ["ev_B", "ev_A"],
        ["ev_A", "ev_C"],
    ]
    assert [c.evidence_unit_id for c in result.citations] == ["ev_B", "ev_A", "ev_C"]
    assert result.effective_generation_semantics["output_contract"] == GROUNDED_ANSWER_V2
    assert result.generation_config_hash == build_product_v2_generation_config_hash(
        settings
    )

    # Empty evidence → no_evidence, generator not invoked
    assembler.assemble.return_value = _context([])
    generator2 = FakeGenerator(default_response="should-not-run")
    orch2 = GroundedAnswerOrchestrator(
        settings, context_assembler=assembler, generator=generator2
    )
    empty = orch2.answer(
        query="What?",
        corpus_name="default",
        check_ready=False,
        product_v2=True,
        allow_recovery=False,
    )
    assert empty.status == "insufficient_evidence"
    assert empty.product_abstention_reason == "no_evidence"
    assert empty.generator_invoked is False


def test_product_v2_model_abstain_reason() -> None:
    settings = _settings()
    units = [_unit("ev_A", "alpha")]
    generator = FakeGenerator(
        default_response=json.dumps(
            {
                "abstain": True,
                "blocks": [],
                "abstention_reason": "conflicting_evidence",
            }
        )
    )
    assembler = MagicMock()
    assembler.assemble.return_value = _context(units)
    from offline_rag.generation import executor as executor_mod
    import offline_rag.generation.executor as ex

    # Use monkeypatch via setattr on instance method through class
    original = ex.GroundedGenerationExecutor._adapt_prompt_evidence

    def _adapt(self, **kwargs):
        return [
            PromptEvidence(
                evidence_unit_id=u.evidence_unit_id,
                document_title="Doc",
                section_path=tuple(u.section_path),
                text=u.text,
            )
            for u in kwargs["evidence_units"]
        ]

    ex.GroundedGenerationExecutor._adapt_prompt_evidence = _adapt  # type: ignore[method-assign]
    try:
        orch = GroundedAnswerOrchestrator(
            settings, context_assembler=assembler, generator=generator
        )
        result = orch.answer(
            query="What?",
            check_ready=False,
            product_v2=True,
            allow_recovery=False,
        )
    finally:
        ex.GroundedGenerationExecutor._adapt_prompt_evidence = original  # type: ignore[method-assign]
    assert result.abstention_reason == "model_abstain"
    assert result.product_abstention_reason == "conflicting_evidence"
