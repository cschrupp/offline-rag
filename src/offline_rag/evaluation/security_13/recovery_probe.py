"""Offline recovery-boundary probe (OD-13-5 / OD-13-6; harness_fake only)."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from offline_rag.config.models import AppSettings
from offline_rag.evaluation.security_13.contracts import (
    AdversarialFixtureV1,
    RecoveryComponentV1,
    SecurityEvalError,
    SecurityObservationV1,
)
from offline_rag.recovery.contracts import (
    AssemblyStopReasonV1,
    RecoveryDiagnosticsV1,
    RecoverySufficiencyDecisionRefV1,
)
from offline_rag.recovery.rewrite_contracts import RecoveryRewriteInputV1
from offline_rag.sufficiency.policy import EMPTY_CONTEXT_GATE_V1


def _insufficient_ref() -> RecoverySufficiencyDecisionRefV1:
    return RecoverySufficiencyDecisionRefV1(
        sufficient=False,
        triggered_gates=[EMPTY_CONTEXT_GATE_V1],
        empty_context=True,
        evidence_unit_count=0,
    )


def _typed_diagnostics() -> RecoveryDiagnosticsV1:
    return RecoveryDiagnosticsV1(
        anchor_count=0,
        evidence_unit_count=0,
        top_reranker_score=None,
        top1_top2_margin=None,
        top_anchor_cross_retriever_support=None,
        distinct_document_count=0,
        distinct_section_count=0,
        clipping_occurred=False,
        budget_exhausted=False,
        stop_reason=AssemblyStopReasonV1.NO_ANCHORS,
    )


def assert_corpus_text_rejected_from_rewrite_input(
    *,
    original_query: str,
    illicit_corpus_text: str,
) -> None:
    """Prove RecoveryRewriteInputV1 rejects corpus free-text fields."""
    illicit_payload: dict[str, Any] = {
        "original_query": original_query,
        "attempt_number": 0,
        "attempt_role": "initial",
        "sufficiency": _insufficient_ref().model_dump(mode="json"),
        "diagnostics": _typed_diagnostics().model_dump(mode="json"),
        "corpus_derived_text": illicit_corpus_text,
    }
    try:
        RecoveryRewriteInputV1.model_validate(illicit_payload)
    except ValidationError:
        return
    raise SecurityEvalError(
        "RecoveryRewriteInputV1 accepted illicit corpus_derived_text field"
    )


def build_recovery_boundary_observation(
    fixture: AdversarialFixtureV1,
    *,
    settings: AppSettings | None = None,
) -> SecurityObservationV1:
    """Run harness_fake recovery-boundary probe and return observations."""
    from offline_rag.recovery.fake import FakeRecoveryRewriter

    if fixture.path_under_test != "recovery_path":
        raise SecurityEvalError(
            "build_recovery_boundary_observation requires path_under_test=recovery_path"
        )
    probe_units = [
        unit
        for unit in fixture.evidence
        if unit.placement == "recovery_rewriter_forbidden_input_probe"
    ]
    if not probe_units:
        raise SecurityEvalError(
            "recovery-boundary fixture requires evidence with placement="
            "recovery_rewriter_forbidden_input_probe"
        )
    illicit_text = probe_units[0].text

    assert_corpus_text_rejected_from_rewrite_input(
        original_query=fixture.user_query,
        illicit_corpus_text=illicit_text,
    )

    rewrite_input = RecoveryRewriteInputV1(
        original_query=fixture.user_query,
        sufficiency=_insufficient_ref(),
        diagnostics=_typed_diagnostics(),
    )
    app_settings = settings if settings is not None else AppSettings()
    rewriter = FakeRecoveryRewriter(app_settings, rewritten_query="harmless rewrite")
    _output, _prov = rewriter.rewrite(rewrite_input)

    surface_texts: list[str] = [rewrite_input.model_dump_json()]
    if rewriter.last_messages is not None:
        for message in rewriter.last_messages:
            surface_texts.append(message.get("content", ""))
            surface_texts.append(message.get("role", ""))

    policy = {
        "allow_shell_tools": False,
        "allow_filesystem_tools": False,
        "allow_network_tools": False,
        "approved_models": ["local-only"],
    }
    components: list[RecoveryComponentV1] = ["rewriter_input", "recovery_rewriter"]
    return SecurityObservationV1(
        configured_retry_budget=1,
        observed_retry_budget=1,
        configured_corpus_scope="ics_modules",
        observed_corpus_scope="ics_modules",
        observed_original_query=fixture.user_query,
        configured_security_policy=policy,
        observed_security_policy=dict(policy),
        capability_invocations=[],
        emitted_citation_ids=[],
        rewriter_surface_texts=surface_texts,
        product_default_recovery_enabled=False,
        recovery_execution_mode="harness_fake",
        recovery_components_entered=components,
    )
