"""Slice 11C sufficiency-v1 runtime policy tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from offline_rag.config.models import AbstentionSettings, AppSettings
from offline_rag.domain.indexing import (
    ContextAssemblyDiagnostics,
    EvidenceUnit,
    HybridRerankContextResult,
)
from offline_rag.generation.fake import FakeGenerator
from offline_rag.generation.orchestrate import (
    GroundedAnswerError,
    GroundedAnswerOrchestrator,
)
from offline_rag.sufficiency.policy import (
    EMPTY_CONTEXT_GATE_V1,
    SUFFICIENCY_POLICY_V1,
    evaluate_runtime_sufficiency,
    evaluate_sufficiency_policy_v1,
    require_runtime_sufficiency_policy,
)


def _unit(ev_id: str = "ev_A", text: str = "max pressure is 100 psi") -> EvidenceUnit:
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
        metadata={"chunk_set_id": "chunkset_test", "latency_ms": {"total": 1}},
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


def _orchestrator(
    settings: AppSettings,
    *,
    units: list[EvidenceUnit] | None = None,
    fake: FakeGenerator | None = None,
) -> tuple[GroundedAnswerOrchestrator, FakeGenerator]:
    generator = fake or FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "ok", "citation_ids": ["ev_A"]}
        )
    )
    assembler = MagicMock()
    assembler.assemble.return_value = _context(
        units if units is not None else [_unit()]
    )
    orch = GroundedAnswerOrchestrator(
        settings, context_assembler=assembler, generator=generator
    )
    orch._require_ready = lambda _name: None  # type: ignore[method-assign]
    return orch, generator


def test_empty_units_trigger_empty_context_gate() -> None:
    decision = evaluate_sufficiency_policy_v1(evidence_units=[])
    assert decision.sufficient is False
    assert decision.empty_context is True
    assert decision.triggered_gates == [EMPTY_CONTEXT_GATE_V1]
    assert decision.triggered_gates == ["empty_context_v1"]
    assert decision.policy_contract == SUFFICIENCY_POLICY_V1


def test_empty_context_deterministic_insufficient_result() -> None:
    orch, fake = _orchestrator(_settings(), units=[])
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.status == "insufficient_evidence"
    assert result.abstention_reason == "empty_context"
    assert result.generator_invoked is False
    assert result.attempt_count == 0
    assert result.citations == []
    assert result.answer_text is None
    assert fake.generate_calls == 0
    assert result.diagnostics["sufficiency_policy_contract"] == SUFFICIENCY_POLICY_V1
    assert result.diagnostics["sufficient"] is False
    assert result.diagnostics["triggered_gates"] == [EMPTY_CONTEXT_GATE_V1]
    assert result.diagnostics["triggered_gates"] == ["empty_context_v1"]
    assert result.diagnostics["empty_context"] is True
    # User-facing reason stays unversioned; formal gate ID is versioned.
    assert result.abstention_reason != result.diagnostics["triggered_gates"][0]


def test_policy_decision_is_deterministic() -> None:
    units = [_unit()]
    left = evaluate_sufficiency_policy_v1(evidence_units=units)
    right = evaluate_sufficiency_policy_v1(evidence_units=units)
    assert left.model_dump() == right.model_dump()
    empty_a = evaluate_sufficiency_policy_v1(evidence_units=[])
    empty_b = evaluate_sufficiency_policy_v1(evidence_units=[])
    assert empty_a.model_dump() == empty_b.model_dump()


def test_non_empty_context_is_sufficient_and_invokes_generation() -> None:
    orch, fake = _orchestrator(_settings(), units=[_unit()])
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.status == "answered"
    assert result.generator_invoked is True
    assert result.attempt_count == 1
    assert fake.generate_calls == 1
    assert result.diagnostics["sufficient"] is True
    assert result.diagnostics["triggered_gates"] == []
    assert result.diagnostics["empty_context"] is False
    assert result.abstention_reason is None


def test_negative_reranker_score_does_not_gate_non_empty_context() -> None:
    """11B non-promoted feature must not become a runtime gate."""
    decision = evaluate_sufficiency_policy_v1(evidence_units=[_unit()])
    assert decision.sufficient is True
    # No score feature is consulted by the policy surface.
    assert "top_reranker_score" not in decision.model_dump_json()
    orch, fake = _orchestrator(_settings(), units=[_unit()])
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.status == "answered"
    assert fake.generate_calls == 1


def test_tiny_margin_does_not_gate_non_empty_context() -> None:
    decision = evaluate_sufficiency_policy_v1(evidence_units=[_unit()])
    assert decision.sufficient is True
    assert "top1_top2_margin" not in decision.model_dump_json()


def test_missing_cross_retriever_support_does_not_gate() -> None:
    decision = evaluate_sufficiency_policy_v1(evidence_units=[_unit()])
    assert decision.sufficient is True
    assert "cross_retriever" not in decision.model_dump_json()


def test_low_diversity_does_not_gate() -> None:
    decision = evaluate_sufficiency_policy_v1(evidence_units=[_unit()])
    assert decision.sufficient is True
    dumped = decision.model_dump_json()
    assert "distinct_document_count" not in dumped
    assert "distinct_section_count" not in dumped
    assert "anchor_count" not in dumped


def test_unsupported_policy_config_fails_closed() -> None:
    with pytest.raises(ValidationError, match="sufficiency-v1"):
        AbstentionSettings(policy="score_threshold", threshold=None)
    with pytest.raises(ValidationError, match="sufficiency-v1"):
        AbstentionSettings(policy="mystery-policy")
    with pytest.raises(ValidationError, match="threshold"):
        AbstentionSettings(policy="sufficiency-v1", threshold=0.5)
    with pytest.raises(ValidationError, match="enabled"):
        AbstentionSettings(policy="sufficiency-v1", enabled=False)


def test_runtime_resolve_rejects_unsupported_policy_object() -> None:
    settings = _settings()
    # Bypass pydantic constructor validation via object.__setattr__ on a copy.
    bad = settings.model_copy(deep=True)
    object.__setattr__(bad.abstention, "policy", "score_threshold")
    with pytest.raises(Exception, match="unsupported abstention.policy"):
        require_runtime_sufficiency_policy(bad)
    with pytest.raises(GroundedAnswerError, match="unsupported abstention.policy"):
        orch, _ = _orchestrator(bad, units=[_unit()])
        orch.answer(query="pressure?", corpus_name="default")


def test_model_abstain_distinct_from_empty_context() -> None:
    fake = FakeGenerator(
        default_response=json.dumps(
            {"abstain": True, "answer": None, "citation_ids": []}
        )
    )
    orch, _ = _orchestrator(_settings(), units=[_unit()], fake=fake)
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.status == "insufficient_evidence"
    assert result.abstention_reason == "model_abstain"
    assert result.generator_invoked is True
    assert result.attempt_count == 1
    assert result.diagnostics["sufficient"] is True
    assert result.diagnostics["empty_context"] is False
    assert result.diagnostics["triggered_gates"] == []


def test_no_recovery_rewrite_or_retry_on_empty_context() -> None:
    settings = _settings().model_copy(
        update={
            "retrieval_recovery": _settings().retrieval_recovery.model_copy(
                update={"enabled": True, "max_retries": 1}
            )
        }
    )
    orch, fake = _orchestrator(settings, units=[])
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.attempt_count == 0
    assert fake.generate_calls == 0
    assert result.abstention_reason == "empty_context"
    # Assembler called once; no rewrite loop.
    assert orch._assembler.assemble.call_count == 1


def test_default_settings_resolve_to_sufficiency_v1() -> None:
    settings = AppSettings()
    assert settings.abstention.policy == SUFFICIENCY_POLICY_V1
    assert settings.abstention.threshold is None
    assert require_runtime_sufficiency_policy(settings) == SUFFICIENCY_POLICY_V1
    decision = evaluate_runtime_sufficiency(settings, evidence_units=[_unit()])
    assert decision.sufficient is True
