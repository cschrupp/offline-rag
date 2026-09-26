"""Slice 12B — bounded recovery rewriter + one recovery retrieval attempt."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from offline_rag.config.models import AppSettings, RecoveryRewriterSettings
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
from offline_rag.recovery import (
    RECOVERY_REWRITE_OUTPUT_V1,
    RECOVERY_REWRITE_PROMPT_V1,
    FakeRecoveryRewriter,
    RecoveryDiagnosticsV1,
    RecoveryFailureReasonV1,
    RecoveryRewriteError,
    RecoveryRewriteInputV1,
    RecoveryRewriteOutputV1,
    RecoveryTerminalOutcomeV1,
    build_recovery_rewriter_config_hash,
    parse_recovery_rewrite_output,
    sufficiency_ref_from_decision,
)
from offline_rag.recovery.rewrite_prompt import build_recovery_rewrite_messages
from offline_rag.sufficiency.policy import EMPTY_CONTEXT_GATE_V1

REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "MALICIOUS_EVIDENCE_SENTINEL_DO_NOT_SEND_TO_REWRITER"


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


def _context(
    units: list[EvidenceUnit],
    *,
    query: str = "pressure?",
    stop_reason: str = "completed",
    latency_total: int = 1,
    corpus_id: str | None = "corpus_test",
    chunk_set_id: str | None = "chunkset_test",
) -> HybridRerankContextResult:
    assembled = "\n\n".join(unit.text for unit in units)
    metadata: dict = {
        "latency_ms": {"total": latency_total},
    }
    if corpus_id is not None:
        metadata["corpus_id"] = corpus_id
    if chunk_set_id is not None:
        metadata["chunk_set_id"] = chunk_set_id
    return HybridRerankContextResult(
        query=query,
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
            stop_reason=stop_reason if units else "no_anchors",
            budget_exhausted=False,
            clipping_occurred=False,
        ),
        metadata=metadata,
    )


def _rewriter_settings(**overrides) -> RecoveryRewriterSettings:
    base = {
        "provider": "openai_compatible",
        "adapter_contract": "openai-compatible-recovery-rewriter-v1",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "rewrite-model",
        "temperature": 0.0,
        "max_output_tokens": 256,
        "timeout_seconds": 60,
        "api_key": None,
        "approved_endpoints": ["http://127.0.0.1:11434/v1"],
        "approved_models": ["rewrite-model"],
        "prompt_contract": RECOVERY_REWRITE_PROMPT_V1,
        "output_contract": RECOVERY_REWRITE_OUTPUT_V1,
        "network_policy": "localhost_only",
    }
    base.update(overrides)
    return RecoveryRewriterSettings(**base)


def _settings(*, recovery_enabled: bool = False, **rewriter_overrides) -> AppSettings:
    return AppSettings().model_copy(
        update={
            "generation": AppSettings().generation.model_copy(
                update={
                    "enabled": True,
                    "model": "gen-model",
                    "approved_models": ["gen-model"],
                    "approved_endpoints": ["http://127.0.0.1:11434/v1"],
                    "base_url": "http://127.0.0.1:11434/v1",
                }
            ),
            "retrieval_recovery": AppSettings().retrieval_recovery.model_copy(
                update={
                    "enabled": recovery_enabled,
                    "max_retries": 1,
                    "rewriter": _rewriter_settings(**rewriter_overrides),
                }
            ),
        }
    )


def _orchestrator(
    settings: AppSettings,
    *,
    initial_units: list[EvidenceUnit],
    recovery_units: list[EvidenceUnit] | None = None,
    rewritten_query: str | None = None,
    raise_on_rewrite: Exception | None = None,
    raise_on_recovery_assemble: Exception | None = None,
    initial_latency_total: int = 11,
    recovery_latency_total: int = 77,
    fake: FakeGenerator | None = None,
) -> tuple[GroundedAnswerOrchestrator, FakeGenerator, FakeRecoveryRewriter, MagicMock]:
    generator = fake or FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "ok", "citation_ids": ["ev_A"]}
        )
    )
    rewriter = FakeRecoveryRewriter(
        settings,
        rewritten_query=rewritten_query,
        raise_on_rewrite=raise_on_rewrite,
    )
    assembler = MagicMock()
    calls: list[str] = []

    def _assemble(*, query: str, corpus_name: str = "default"):
        calls.append(query)
        if len(calls) == 1:
            return _context(
                initial_units, query=query, latency_total=initial_latency_total
            )
        if raise_on_recovery_assemble is not None:
            raise raise_on_recovery_assemble
        units = recovery_units if recovery_units is not None else initial_units
        return _context(units, query=query, latency_total=recovery_latency_total)

    assembler.assemble.side_effect = _assemble
    orch = GroundedAnswerOrchestrator(
        settings,
        context_assembler=assembler,
        generator=generator,
        recovery_rewriter=rewriter,
    )
    orch._require_ready = lambda _name: None  # type: ignore[method-assign]
    return orch, generator, rewriter, assembler


def test_recovery_disabled_by_default() -> None:
    settings = AppSettings()
    assert settings.retrieval_recovery.enabled is False
    assert settings.retrieval_recovery.max_retries == 1


def test_max_retries_must_be_one() -> None:
    with pytest.raises(ValidationError):
        from offline_rag.config.models import RetrievalRecoverySettings

        RetrievalRecoverySettings(enabled=False, max_retries=2)  # type: ignore[arg-type]


def test_rewriter_settings_independent_of_generation() -> None:
    settings = _settings(
        recovery_enabled=False,
        model="rewrite-only",
        approved_models=["rewrite-only"],
    )
    assert settings.generation.model == "gen-model"
    assert settings.retrieval_recovery.rewriter.model == "rewrite-only"
    assert settings.retrieval_recovery.rewriter.model != settings.generation.model


def test_rewriter_config_hash_deterministic_and_excludes_api_key() -> None:
    left = _rewriter_settings(api_key="secret-a")
    right = _rewriter_settings(api_key="secret-b")
    assert build_recovery_rewriter_config_hash(
        left
    ) == build_recovery_rewriter_config_hash(right)
    changed = _rewriter_settings(model="other-model", approved_models=["other-model"])
    assert build_recovery_rewriter_config_hash(
        left
    ) != build_recovery_rewriter_config_hash(changed)
    assert build_recovery_rewriter_config_hash(left).startswith("rrwcfg_")


def test_unapproved_endpoint_and_model_fail_closed() -> None:
    from offline_rag.recovery.rewrite_provider import OpenAICompatibleRecoveryRewriter

    bad_endpoint = _settings(
        recovery_enabled=True,
        base_url="http://evil.example/v1",
        approved_endpoints=["http://127.0.0.1:11434/v1"],
    )
    rewriter = OpenAICompatibleRecoveryRewriter(bad_endpoint)
    with pytest.raises(RecoveryRewriteError) as exc:
        rewriter.rewrite(
            RecoveryRewriteInputV1(
                original_query="q",
                sufficiency=sufficiency_ref_from_decision(sufficient=False),
                diagnostics=RecoveryDiagnosticsV1(evidence_unit_count=0),
            )
        )
    assert exc.value.failure_reason == "authorization_error"
    assert exc.value.provenance is not None
    assert exc.value.provenance.rewriter_config_hash.startswith("rrwcfg_")

    bad_model = _settings(
        recovery_enabled=True,
        model="not-approved",
        approved_models=["rewrite-model"],
    )
    rewriter2 = OpenAICompatibleRecoveryRewriter(bad_model)
    with pytest.raises(RecoveryRewriteError) as exc2:
        rewriter2.rewrite(
            RecoveryRewriteInputV1(
                original_query="q",
                sufficiency=sufficiency_ref_from_decision(sufficient=False),
                diagnostics=RecoveryDiagnosticsV1(evidence_unit_count=0),
            )
        )
    assert exc2.value.failure_reason == "authorization_error"


def test_network_policy_enforced_independently_of_allowlist() -> None:
    from offline_rag.recovery.rewrite_provider import OpenAICompatibleRecoveryRewriter

    # Public host present in allowlist must still fail localhost_only.
    settings = _settings(
        recovery_enabled=True,
        base_url="https://api.openai.com/v1",
        approved_endpoints=["https://api.openai.com/v1"],
        network_policy="localhost_only",
    )
    rewriter = OpenAICompatibleRecoveryRewriter(settings)
    with pytest.raises(RecoveryRewriteError) as exc:
        rewriter.rewrite(
            RecoveryRewriteInputV1(
                original_query="q",
                sufficiency=sufficiency_ref_from_decision(sufficient=False),
                diagnostics=RecoveryDiagnosticsV1(evidence_unit_count=0),
            )
        )
    assert exc.value.failure_reason == "authorization_error"
    assert "network_policy" in str(exc.value)

    local = _settings(
        recovery_enabled=True,
        base_url="http://127.0.0.1:11434/v1",
        approved_endpoints=["http://127.0.0.1:11434/v1"],
        network_policy="localhost_only",
    )
    # Authorization passes; transport may fail — only assert authorization itself.
    OpenAICompatibleRecoveryRewriter(local)._assert_authorized()

    docker_host = _settings(
        recovery_enabled=True,
        base_url="http://host.docker.internal:11434/v1",
        approved_endpoints=["http://host.docker.internal:11434/v1"],
        network_policy="localhost_only",
    )
    OpenAICompatibleRecoveryRewriter(docker_host)._assert_authorized()

    left = _rewriter_settings(network_policy="localhost_only")
    right = _rewriter_settings(network_policy="private_network")
    assert build_recovery_rewriter_config_hash(
        left
    ) != build_recovery_rewriter_config_hash(right)


def test_rewrite_output_contract_fail_closed() -> None:
    with pytest.raises(RecoveryRewriteError):
        parse_recovery_rewrite_output("not-json")
    with pytest.raises(RecoveryRewriteError):
        parse_recovery_rewrite_output(json.dumps({"rewritten_query": ""}))
    with pytest.raises(RecoveryRewriteError):
        parse_recovery_rewrite_output(
            json.dumps({"rewritten_query": "ok", "extra": "nope"})
        )
    with pytest.raises(RecoveryRewriteError):
        parse_recovery_rewrite_output(json.dumps({"query": "wrong-key"}))
    ok = parse_recovery_rewrite_output(json.dumps({"rewritten_query": "same"}))
    assert ok.rewritten_query == "same"


def test_prompt_excludes_corpus_text_and_includes_diagnostics() -> None:
    diagnostics = RecoveryDiagnosticsV1(
        evidence_unit_count=0,
        anchor_count=0,
        stop_reason="no_anchors",
    )
    rewrite_input = RecoveryRewriteInputV1(
        original_query="what is max pressure?",
        sufficiency=sufficiency_ref_from_decision(sufficient=False),
        diagnostics=diagnostics,
    )
    messages = build_recovery_rewrite_messages(rewrite_input)
    blob = json.dumps(messages)
    assert "what is max pressure?" in blob
    assert "empty_context_v1" in blob or EMPTY_CONTEXT_GATE_V1 in blob
    assert SENTINEL not in blob
    assert "evidence_unit_count" in blob
    with pytest.raises(ValidationError):
        RecoveryDiagnosticsV1.model_validate({"chunk_text": SENTINEL})


def test_non_empty_initial_skips_rewrite_and_second_retrieval() -> None:
    settings = _settings(recovery_enabled=True)
    orch, fake, rewriter, assembler = _orchestrator(
        settings, initial_units=[_unit()], rewritten_query="should-not-run"
    )
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.status == "answered"
    assert rewriter.rewrite_calls == 0
    assert assembler.assemble.call_count == 1
    assert fake.generate_calls == 1
    assert "retrieval_recovery" not in result.diagnostics


def test_disabled_recovery_skips_rewrite_on_empty() -> None:
    settings = _settings(recovery_enabled=False)
    orch, fake, rewriter, assembler = _orchestrator(
        settings, initial_units=[], rewritten_query="x"
    )
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.status == "insufficient_evidence"
    assert rewriter.rewrite_calls == 0
    assert assembler.assemble.call_count == 1
    assert fake.generate_calls == 0


def test_enabled_empty_recovers_and_generates_with_original_query() -> None:
    settings = _settings(recovery_enabled=True)
    orch, fake, rewriter, assembler = _orchestrator(
        settings,
        initial_units=[],
        recovery_units=[_unit(text=SENTINEL)],
        rewritten_query="max operating pressure limit",
    )
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.status == "answered"
    assert rewriter.rewrite_calls == 1
    assert assembler.assemble.call_count == 2
    assert fake.generate_calls == 1
    assert result.query == "pressure?"
    assert result.diagnostics["retrieval_recovery"]["terminal_outcome"] == (
        RecoveryTerminalOutcomeV1.RECOVERED_EVIDENCE_SUFFICIENT.value
    )
    assert result.diagnostics["retrieval_recovery"]["rewrite_call_count"] == 1
    assert (
        result.diagnostics["retrieval_recovery"]["recovery_retrieval_attempt_count"]
        == 1
    )
    assert "api_key" not in json.dumps(result.diagnostics["retrieval_recovery"])
    # Sentinel evidence may be in generation path, but never in rewriter prompt.
    assert rewriter.last_messages is not None
    assert SENTINEL not in json.dumps(rewriter.last_messages)
    assert rewriter.last_input is not None
    assert rewriter.last_input.original_query == "pressure?"


def test_noop_rewrite_accepted() -> None:
    settings = _settings(recovery_enabled=True)
    orch, fake, rewriter, assembler = _orchestrator(
        settings,
        initial_units=[],
        recovery_units=[_unit()],
        rewritten_query="pressure?",
    )
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.status == "answered"
    assert rewriter.rewrite_calls == 1
    assert assembler.assemble.call_count == 2
    assert fake.generate_calls == 1


def test_persistent_insufficiency_after_recovery() -> None:
    settings = _settings(recovery_enabled=True)
    orch, fake, rewriter, assembler = _orchestrator(
        settings,
        initial_units=[],
        recovery_units=[],
        rewritten_query="broader query",
    )
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.status == "insufficient_evidence"
    assert result.abstention_reason == "empty_context"
    assert result.generator_invoked is False
    assert result.attempt_count == 0
    assert fake.generate_calls == 0
    assert rewriter.rewrite_calls == 1
    assert assembler.assemble.call_count == 2
    assert result.diagnostics["retrieval_recovery"]["terminal_outcome"] == (
        RecoveryTerminalOutcomeV1.INSUFFICIENT_AFTER_BOUNDED_RECOVERY.value
    )


def test_rewrite_failure_no_recovery_retrieval() -> None:
    settings = _settings(recovery_enabled=True)
    orch, fake, rewriter, assembler = _orchestrator(
        settings,
        initial_units=[],
        raise_on_rewrite=RecoveryRewriteError(
            "boom", failure_reason="malformed_output"
        ),
    )
    with pytest.raises(GroundedAnswerError) as exc:
        orch.answer(query="pressure?", corpus_name="default")
    assert "retrieval recovery failed" in str(exc.value)
    assert exc.value.recovery_trace is not None
    trace = exc.value.recovery_trace
    assert trace["terminal_outcome"] == (
        RecoveryTerminalOutcomeV1.RECOVERY_PREPARATION_OR_EXECUTION_FAILED.value
    )
    assert trace["failure_reason"] == (
        RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED.value
    )
    assert trace["rewriter_config_hash"]
    assert trace["provider"]
    assert trace["model"]
    assert trace["normalized_endpoint"]
    assert trace["recovery_retrieval_attempt_count"] == 0
    assert "api_key" not in json.dumps(trace)
    assert rewriter.rewrite_calls == 1
    assert assembler.assemble.call_count == 1
    assert fake.generate_calls == 0


def test_missing_initial_lineage_terminals_as_rewrite_preparation_failed() -> None:
    settings = _settings(recovery_enabled=True)
    generator = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "ok", "citation_ids": ["ev_A"]}
        )
    )
    rewriter = FakeRecoveryRewriter(settings, rewritten_query="r1")
    assembler = MagicMock()
    assembler.assemble.return_value = _context([], corpus_id=None)
    orch = GroundedAnswerOrchestrator(
        settings,
        context_assembler=assembler,
        generator=generator,
        recovery_rewriter=rewriter,
    )
    orch._require_ready = lambda _name: None  # type: ignore[method-assign]
    with pytest.raises(GroundedAnswerError) as exc:
        orch.answer(query="pressure?", corpus_name="default")
    assert exc.value.recovery_trace is not None
    trace = exc.value.recovery_trace
    assert trace["terminal_outcome"] == (
        RecoveryTerminalOutcomeV1.RECOVERY_PREPARATION_OR_EXECUTION_FAILED.value
    )
    assert trace["failure_reason"] == (
        RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED.value
    )
    assert rewriter.rewrite_calls == 0
    assert generator.generate_calls == 0


def test_recovered_context_latency_used_in_generation_provenance() -> None:
    settings = _settings(recovery_enabled=True)
    orch, fake, rewriter, assembler = _orchestrator(
        settings,
        initial_units=[],
        recovery_units=[_unit()],
        rewritten_query="r1",
        initial_latency_total=11,
        recovery_latency_total=77,
    )
    result = orch.answer(query="pressure?", corpus_name="default")
    assert result.status == "answered"
    assert result.diagnostics["latency_ms"]["context"] == 77
    assert result.diagnostics["latency_ms"]["context_breakdown"]["total"] == 77
    assert fake.generate_calls == 1
    assert rewriter.rewrite_calls == 1
    assert assembler.assemble.call_count == 2


def test_recovery_execution_failure_no_retry() -> None:
    from offline_rag.context.assemble import HybridRerankContextError

    settings = _settings(recovery_enabled=True)
    orch, fake, rewriter, assembler = _orchestrator(
        settings,
        initial_units=[],
        rewritten_query="r1",
        raise_on_recovery_assemble=HybridRerankContextError("assemble failed"),
    )
    with pytest.raises(GroundedAnswerError) as exc:
        orch.answer(query="pressure?", corpus_name="default")
    assert exc.value.recovery_trace is not None
    assert exc.value.recovery_trace["failure_reason"] == (
        RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED.value
    )
    assert rewriter.rewrite_calls == 1
    assert assembler.assemble.call_count == 2
    assert fake.generate_calls == 0


def test_lineage_mismatch_fails_closed() -> None:
    settings = _settings(recovery_enabled=True)
    generator = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "ok", "citation_ids": ["ev_A"]}
        )
    )
    rewriter = FakeRecoveryRewriter(settings, rewritten_query="r1")
    assembler = MagicMock()
    calls = {"n": 0}

    def _assemble(*, query: str, corpus_name: str = "default"):
        calls["n"] += 1
        if calls["n"] == 1:
            return _context([], query=query)
        bad = _context([_unit()], query=query)
        return bad.model_copy(update={"dense_index_id": "dense_OTHER"})

    assembler.assemble.side_effect = _assemble
    orch = GroundedAnswerOrchestrator(
        settings,
        context_assembler=assembler,
        generator=generator,
        recovery_rewriter=rewriter,
    )
    orch._require_ready = lambda _name: None  # type: ignore[method-assign]
    with pytest.raises(GroundedAnswerError) as exc:
        orch.answer(query="pressure?", corpus_name="default")
    assert exc.value.recovery_trace is not None
    assert exc.value.recovery_trace["failure_reason"] == (
        RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED.value
    )
    assert generator.generate_calls == 0


def test_no_langgraph_dependency() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "langgraph" not in pyproject.lower()
    recovery_src = REPO_ROOT / "src" / "offline_rag" / "recovery"
    for path in recovery_src.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "import langgraph" not in text
        assert "from langgraph" not in text


def test_extra_diagnostic_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        RecoveryRewriteInputV1.model_validate(
            {
                "original_query": "q",
                "sufficiency": sufficiency_ref_from_decision(
                    sufficient=False
                ).model_dump(mode="json"),
                "diagnostics": {"evidence_unit_count": 0},
                "metadata": {"anything": "no"},
            }
        )


def test_structured_output_model_forbids_extra_keys() -> None:
    with pytest.raises(ValidationError):
        RecoveryRewriteOutputV1.model_validate(
            {"rewritten_query": "ok", "note": "extra"}
        )
