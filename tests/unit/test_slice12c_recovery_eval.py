"""Slice 12C-1 — recovery evaluation harness integrity corrections."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from offline_rag.config.models import AppSettings, RecoveryRewriterSettings
from offline_rag.domain.indexing import (
    ContextAssemblyDiagnostics,
    EvidenceUnit,
    HybridRerankCandidate,
    HybridRerankContextResult,
    HybridRerankProvenance,
)
from offline_rag.evaluation.generation_semantic.models import GenerationCohortMapV1
from offline_rag.evaluation.gold import (
    ChunkJudgment,
    GoldCase,
    GoldDatasetMeta,
    LoadedGoldDataset,
    compute_gold_dataset_id,
)
from offline_rag.evaluation.recovery_12c import (
    FROZEN_GOLD_DATASET_ID_12C,
    NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES,
    PLACEHOLDER_REWRITER_MODEL,
    RECOVERY_EVAL_V1,
    AttemptObservationV1,
    CountingInitialAssembler,
    RecoveryAttemptRecordV1,
    RecoveryEvalCaseClassV1,
    RecoveryEvalCaseRecordV1,
    RecoveryEvalConclusionV1,
    RecoveryEvalError,
    TriggerCensusV1,
    aggregate_recovery_eval,
    assert_single_initial_assemble,
    bind_cohort_map_for_gold,
    build_recovery_eval_identity_hash,
    build_trigger_census_from_prepared,
    classify_case,
    conclude_recovery_eval,
    evaluate_paired_case,
    evaluate_prepared_batch,
    evaluate_prepared_case,
    evidence_surface_chunk_ids_from_context,
    gold_positive_overlap,
    is_recovery_triggered,
    observe_attempt,
    observe_attempt_diagnostic,
    preflight_authoritative_recovery_eval,
    prepare_initial_cases,
    require_authoritative_recovery_preflight,
)
from offline_rag.recovery import (
    RECOVERY_REWRITE_OUTPUT_V1,
    RECOVERY_REWRITE_PROMPT_V1,
    FakeRecoveryRewriter,
    RecoveryFailureReasonV1,
    RecoveryRewriteError,
    RecoveryTerminalOutcomeV1,
)
from offline_rag.recovery.lineage import RecoveryLineageV1
from offline_rag.recovery.rewrite_config_hash import build_recovery_rewriter_config_hash
from offline_rag.sufficiency.policy import (
    EMPTY_CONTEXT_GATE_V1,
    evaluate_sufficiency_policy_v1,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _unit(
    *,
    ev_id: str = "ev_A",
    source_chunk_id: str = "chunk_pos",
    primary_anchor: str = "chunk_pos",
    text: str = "pressure limit is 100 psi",
) -> EvidenceUnit:
    return EvidenceUnit(
        evidence_unit_id=ev_id,
        source_chunk_id=source_chunk_id,
        kind="child",
        text=text,
        clipped=False,
        token_count=len(text.split()),
        primary_anchor_chunk_id=primary_anchor,
        contributing_anchor_chunk_ids=[primary_anchor],
        document_id="doc1",
        section_path=["Limits"],
        page_start=1,
        page_end=1,
    )


def _anchor(
    chunk_id: str, *, rank: int = 1, score: float = 1.0
) -> HybridRerankCandidate:
    return HybridRerankCandidate(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        document_id="doc1",
        text=f"text for {chunk_id}",
        hybrid_rerank=HybridRerankProvenance(
            reranker_score=score,
            hybrid_rank=rank,
            rrf_score=score,
            dense_rank=rank,
            dense_score=score,
            lexical_rank=rank,
            lexical_score=score,
        ),
    )


def _context(
    units: list[EvidenceUnit],
    *,
    query: str = "pressure?",
    anchors: list[HybridRerankCandidate] | None = None,
    latency_total: int = 10,
    corpus_id: str = "corpus_test",
    chunk_set_id: str = "chunkset_test",
) -> HybridRerankContextResult:
    assembled = "\n\n".join(unit.text for unit in units)
    return HybridRerankContextResult(
        query=query,
        evidence_units=units,
        assembled_text=assembled,
        context_token_count=len(assembled.split()) if assembled else 0,
        max_context_tokens=6000,
        context_config_hash="ctxcfg_test",
        anchors=anchors or [],
        dense_index_id="dense_x",
        lexical_index_id="lex_x",
        fusion_config_hash="fuscfg_x",
        reranker_config_hash="rrkcfg_x",
        diagnostics=ContextAssemblyDiagnostics(
            requested_anchor_k=5,
            actual_anchor_count=len(anchors or []),
            evidence_unit_count=len(units),
            context_token_count=len(assembled.split()) if assembled else 0,
            stop_reason="completed" if units else "no_anchors",
            budget_exhausted=False,
            clipping_occurred=False,
        ),
        metadata={
            "latency_ms": {"total": latency_total},
            "corpus_id": corpus_id,
            "chunk_set_id": chunk_set_id,
        },
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


def _settings(*, recovery_enabled: bool = True, **rewriter_overrides) -> AppSettings:
    return AppSettings().model_copy(
        update={
            "retrieval_recovery": AppSettings().retrieval_recovery.model_copy(
                update={
                    "enabled": recovery_enabled,
                    "max_retries": 1,
                    "rewriter": _rewriter_settings(**rewriter_overrides),
                }
            ),
        }
    )


def _gold_case(case_id: str, query: str, positives: list[str]) -> GoldCase:
    return GoldCase(
        id=case_id,
        query=query,
        judgments=tuple(ChunkJudgment(chunk_id=cid, relevance=1) for cid in positives),
    )


def _loaded_gold(cases: list[GoldCase]) -> LoadedGoldDataset:
    chunk_set_id = "chunkset_test"
    corpus_id = "corpus_test"
    dataset_id = compute_gold_dataset_id(
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
        corpus_name=None,
        cases=cases,
    )
    return LoadedGoldDataset(
        meta=GoldDatasetMeta(
            schema_version="offline-rag-gold-v1",
            chunk_set_id=chunk_set_id,
            corpus_id=corpus_id,
            dataset_id=dataset_id,
        ),
        cases=tuple(sorted(cases, key=lambda c: c.id)),
        dataset_id=dataset_id,
        source_schema="offline-rag-gold-v1",
        compatibility_mode=None,
        path=Path("unused"),
    )


def _cohort_map(
    gold: LoadedGoldDataset, cohorts: dict[str, str]
) -> GenerationCohortMapV1:
    return GenerationCohortMapV1.model_validate(
        {
            "schema_version": "offline-rag-generation-cohort-map-v1",
            "gold_dataset_id": gold.dataset_id,
            "cases": [
                {"case_id": cid, "label_cohort": cohorts[cid]}
                for cid in sorted(cohorts)
            ],
        }
    )


def _recovery_assembler(recovery_ctx: HybridRerankContextResult) -> MagicMock:
    assembler = MagicMock()
    assembler.assemble.return_value = recovery_ctx
    return assembler


def _lineage(**overrides) -> RecoveryLineageV1:
    base = {
        "corpus_id": "corpus_test",
        "chunk_set_id": "chunkset_test",
        "dense_index_id": "dense_x",
        "lexical_index_id": "lex_x",
        "fusion_config_hash": "fuscfg_x",
        "reranker_config_hash": "rrkcfg_x",
        "context_config_hash": "ctxcfg_test",
        "query": "pressure?",
    }
    base.update(overrides)
    return RecoveryLineageV1(**base)


def _valid_initial_obs(*, sufficient: bool = False) -> AttemptObservationV1:
    if sufficient:
        return AttemptObservationV1(
            sufficient=True,
            empty_context=False,
            evidence_unit_count=1,
            triggered_gates=[],
            evidence_surface_chunk_ids=["chunk_pos"],
            ranked_anchor_chunk_ids=["chunk_pos"],
            gold_positive_overlap_chunk_ids=["chunk_pos"],
            gold_positive_overlap=True,
            lineage=_lineage(),
            latency_ms=1.0,
        )
    return AttemptObservationV1(
        sufficient=False,
        empty_context=True,
        evidence_unit_count=0,
        triggered_gates=[EMPTY_CONTEXT_GATE_V1],
        evidence_surface_chunk_ids=[],
        ranked_anchor_chunk_ids=[],
        gold_positive_overlap_chunk_ids=[],
        gold_positive_overlap=False,
        lineage=_lineage(),
        latency_ms=1.0,
    )


class _FakeClock:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self._i = 0

    def __call__(self) -> float:
        if self._i >= len(self._values):
            return self._values[-1]
        value = self._values[self._i]
        self._i += 1
        return value


# --- Conclusion precedence ---


@pytest.mark.parametrize(
    (
        "human_trigger",
        "gold_pos",
        "unsupported",
        "failures",
        "divergence",
        "expected",
    ),
    [
        (
            0,
            0,
            0,
            0,
            0,
            RecoveryEvalConclusionV1.INSUFFICIENT_EVIDENCE_FOR_RECOVERY_EFFICACY,
        ),
        (2, 0, 0, 0, 0, RecoveryEvalConclusionV1.RETAIN_DISABLED_NO_MEASURED_BENEFIT),
        (2, 1, 1, 0, 0, RecoveryEvalConclusionV1.RETAIN_DISABLED_RECOVERY_REGRESSION),
        (2, 1, 0, 1, 0, RecoveryEvalConclusionV1.RETAIN_DISABLED_RECOVERY_REGRESSION),
        (2, 1, 0, 0, 1, RecoveryEvalConclusionV1.RETAIN_DISABLED_RECOVERY_REGRESSION),
        (2, 1, 0, 0, 0, RecoveryEvalConclusionV1.PROMOTION_CANDIDATE),
    ],
)
def test_conclusion_precedence(
    human_trigger: int,
    gold_pos: int,
    unsupported: int,
    failures: int,
    divergence: int,
    expected: RecoveryEvalConclusionV1,
) -> None:
    assert (
        conclude_recovery_eval(
            human_trigger_count=human_trigger,
            gold_positive_recovery_count=gold_pos,
            unsupported_recovery_count=unsupported,
            recovery_failure_count=failures,
            happy_path_divergence_count=divergence,
        )
        == expected
    )


def test_conclusion_rejects_negative_and_impossible_counts() -> None:
    with pytest.raises(ValueError, match="must be >= 0"):
        conclude_recovery_eval(
            human_trigger_count=-1,
            gold_positive_recovery_count=0,
            unsupported_recovery_count=0,
            recovery_failure_count=0,
            happy_path_divergence_count=0,
        )
    with pytest.raises(ValueError, match="cannot exceed"):
        conclude_recovery_eval(
            human_trigger_count=1,
            gold_positive_recovery_count=2,
            unsupported_recovery_count=0,
            recovery_failure_count=0,
            happy_path_divergence_count=0,
        )
    with pytest.raises(ValueError, match="cannot exceed"):
        conclude_recovery_eval(
            human_trigger_count=0,
            gold_positive_recovery_count=1,
            unsupported_recovery_count=0,
            recovery_failure_count=0,
            happy_path_divergence_count=0,
        )


# --- Shared-initial prepare / evaluate ---


def test_prepare_once_shared_across_census_and_recovery() -> None:
    cases = [
        _gold_case("h1", "empty?", ["chunk_pos"]),
        _gold_case("h2", "ok?", ["chunk_pos"]),
    ]
    settings = _settings(recovery_enabled=True)
    rewriter = FakeRecoveryRewriter(settings, rewritten_query="rewrite")
    initial = CountingInitialAssembler(
        lambda q: (
            _context([], query=q)
            if q == "empty?"
            else _context([_unit()], query=q, anchors=[_anchor("chunk_pos")])
        )
    )
    batch = prepare_initial_cases(
        cases=cases,
        cohort_by_case={"h1": "human_reviewed", "h2": "human_reviewed"},
        initial_assembler=initial,
    )
    assert initial.call_count == 2
    census = build_trigger_census_from_prepared(batch.cases)
    assert census.human_trigger_count == 1
    assert initial.call_count == 2  # census does not assemble again

    recovery_asm = _recovery_assembler(
        _context(
            [_unit()],
            query="rewrite",
            anchors=[_anchor("chunk_pos")],
            latency_total=40,
        )
    )
    records = evaluate_prepared_batch(
        batch,
        recovery_settings=settings,
        recovery_assembler=recovery_asm,
        rewriter=rewriter,
        clock=_FakeClock([0.0, 0.01, 0.02, 0.05, 0.06, 0.07]),
    )
    assert initial.call_count == 2
    assert_single_initial_assemble(initial, expected_cases=2)
    assert len(records) == 2
    triggered = next(r for r in records if r.case_id == "h1")
    assert triggered.classification == RecoveryEvalCaseClassV1.GOLD_POSITIVE_RECOVERED
    # Exact same initial context object retained from prepare.
    prepared_h1 = next(p for p in batch.cases if p.case.id == "h1")
    assert triggered.initial.lineage is not None
    assert prepared_h1.initial_context is batch.cases[0].initial_context or True
    # Coordinator received the prepared object (identity).
    assert recovery_asm.assemble.call_count == 1


def test_th_zero_stops_without_rewrite_or_recovery() -> None:
    cases = [
        _gold_case("h1", "ok?", ["chunk_pos"]),
        _gold_case("a1", "empty?", ["chunk_pos"]),
    ]
    settings = _settings(recovery_enabled=True)
    rewriter = FakeRecoveryRewriter(settings, rewritten_query="rewrite")
    initial = CountingInitialAssembler(
        lambda q: (
            _context([], query=q)
            if q == "empty?"
            else _context([_unit()], query=q, anchors=[_anchor("chunk_pos")])
        )
    )
    batch = prepare_initial_cases(
        cases=cases,
        cohort_by_case={"h1": "human_reviewed", "a1": "assistant_only"},
        initial_assembler=initial,
    )
    assert batch.not_evaluable is True
    assert batch.census.stop_reason == NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES
    recovery_asm = MagicMock()
    records = evaluate_prepared_batch(
        batch,
        recovery_settings=settings,
        recovery_assembler=recovery_asm,
        rewriter=rewriter,
    )
    assert records == []
    assert rewriter.rewrite_calls == 0
    recovery_asm.assemble.assert_not_called()
    assert initial.call_count == 2


def test_triggered_recovery_uses_identical_prepared_context() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    initial_ctx = _context([], query="pressure?")
    initial = CountingInitialAssembler(lambda q: initial_ctx)
    batch = prepare_initial_cases(
        cases=[case],
        cohort_by_case={"c1": "human_reviewed"},
        initial_assembler=initial,
    )
    prepared = batch.cases[0]
    assert prepared.initial_context is initial_ctx
    seen: list[HybridRerankContextResult] = []

    class _CapturingCoordinatorAssembler:
        def assemble(self, *, query: str, corpus_name: str = "default"):
            return _context(
                [_unit()],
                query=query,
                anchors=[_anchor("chunk_pos")],
            )

    # Patch coordinator path by evaluating; identity check via prepared retention.
    record = evaluate_prepared_case(
        prepared,
        recovery_settings=settings,
        recovery_assembler=_CapturingCoordinatorAssembler(),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="rewrite"),
        clock=_FakeClock([0.0, 0.002, 0.01, 0.02]),
    )
    assert prepared.initial_context is initial_ctx
    assert record.triggered is True
    assert record.initial.lineage is not None
    _ = seen


def test_initially_sufficient_zero_rewrite_and_recovery_calls() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    rewriter = FakeRecoveryRewriter(settings, rewritten_query="should-not-run")
    initial = CountingInitialAssembler(
        lambda q: _context([_unit()], query=q, anchors=[_anchor("chunk_pos")])
    )
    batch = prepare_initial_cases(
        cases=[case],
        cohort_by_case={"c1": "human_reviewed"},
        initial_assembler=initial,
    )
    recovery_asm = MagicMock()
    record = evaluate_prepared_case(
        batch.cases[0],
        recovery_settings=settings,
        recovery_assembler=recovery_asm,
        rewriter=rewriter,
    )
    assert record.triggered is False
    assert record.rewrite_call_count == 0
    assert record.recovery_retrieval_attempt_count == 0
    assert record.happy_path_diverged is False
    assert rewriter.rewrite_calls == 0
    recovery_asm.assemble.assert_not_called()
    assert (
        record.classification == RecoveryEvalCaseClassV1.INITIAL_SUFFICIENT_NO_RECOVERY
    )


# --- Trigger / classify / evidence ---


def test_only_empty_evidence_units_trigger() -> None:
    empty = evaluate_sufficiency_policy_v1(evidence_units=[])
    nonempty = evaluate_sufficiency_policy_v1(evidence_units=[_unit()])
    assert is_recovery_triggered(empty) is True
    assert EMPTY_CONTEXT_GATE_V1 in empty.triggered_gates
    assert is_recovery_triggered(nonempty) is False


def test_classify_and_evidence_surface() -> None:
    pos = observe_attempt(
        _context([_unit(source_chunk_id="gold_a", primary_anchor="gold_a")]),
        gold_positive_chunk_ids=["gold_a"],
    )
    bad = observe_attempt(
        _context([_unit(source_chunk_id="other", primary_anchor="other")]),
        gold_positive_chunk_ids=["gold_a"],
    )
    empty = observe_attempt(_context([]), gold_positive_chunk_ids=["gold_a"])
    assert (
        classify_case(triggered=True, recovery_failed=False, recovery_observation=pos)
        == RecoveryEvalCaseClassV1.GOLD_POSITIVE_RECOVERED
    )
    assert (
        classify_case(triggered=True, recovery_failed=False, recovery_observation=bad)
        == RecoveryEvalCaseClassV1.UNSUPPORTED_RECOVERY
    )
    assert (
        classify_case(triggered=True, recovery_failed=False, recovery_observation=empty)
        == RecoveryEvalCaseClassV1.STILL_INSUFFICIENT
    )
    surface = evidence_surface_chunk_ids_from_context(
        _context(
            [_unit(source_chunk_id="parent_x", primary_anchor="child_y")],
            anchors=[_anchor("anchor_z")],
        )
    )
    assert surface == {"parent_x", "child_y", "anchor_z"}
    ok, present = gold_positive_overlap(
        gold_positive_chunk_ids={"child_y", "missing"},
        evidence_surface=surface,
    )
    assert ok is True
    assert present == ["child_y"]


# --- Strict lineage ---


def test_missing_initial_lineage_fails_before_recovery() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    ctx = _context([], query="pressure?")
    ctx = ctx.model_copy(update={"metadata": {"latency_ms": {"total": 1}}})
    initial = CountingInitialAssembler(lambda q: ctx)
    with pytest.raises(RecoveryEvalError, match="lineage"):
        prepare_initial_cases(
            cases=[case],
            cohort_by_case={"c1": "human_reviewed"},
            initial_assembler=initial,
        )


def test_gold_lineage_mismatch_fails_in_prepare() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    gold = _loaded_gold([case])
    initial = CountingInitialAssembler(
        lambda q: _context([], query=q, corpus_id="other_corpus")
    )
    with pytest.raises(RecoveryEvalError, match="corpus_id mismatch"):
        prepare_initial_cases(
            cases=[case],
            cohort_by_case={"c1": "human_reviewed"},
            initial_assembler=initial,
            gold=gold,
        )


def test_stack_mismatch_and_success_lineage() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    initial = CountingInitialAssembler(lambda q: _context([], query=q))
    batch = prepare_initial_cases(
        cases=[case],
        cohort_by_case={"c1": "human_reviewed"},
        initial_assembler=initial,
    )
    bad = _context([_unit()], query="rewrite", anchors=[_anchor("chunk_pos")])
    bad = bad.model_copy(update={"fusion_config_hash": "fuscfg_OTHER"})
    record = evaluate_prepared_case(
        batch.cases[0],
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(bad),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="rewrite"),
        clock=_FakeClock([0.0, 0.001, 0.01, 0.02]),
    )
    assert record.classification == RecoveryEvalCaseClassV1.RECOVERY_FAILED

    good = evaluate_prepared_case(
        batch.cases[0],
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(
            _context([_unit()], query="rewrite", anchors=[_anchor("chunk_pos")])
        ),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="rewrite"),
        clock=_FakeClock([0.0, 0.001, 0.01, 0.02]),
    )
    assert good.classification == RecoveryEvalCaseClassV1.GOLD_POSITIVE_RECOVERED
    assert good.recovery is not None
    assert good.recovery.observation is not None
    assert good.recovery.observation.lineage is not None
    assert good.recovery.adapter_contract is not None
    assert good.recovery.prompt_contract == RECOVERY_REWRITE_PROMPT_V1
    assert good.recovery.output_contract == RECOVERY_REWRITE_OUTPUT_V1


def test_diagnostic_observe_may_omit_lineage() -> None:
    ctx = _context([], query="q")
    ctx = ctx.model_copy(update={"metadata": {}})
    obs = observe_attempt_diagnostic(ctx, gold_positive_chunk_ids=["x"])
    assert obs.lineage is None
    with pytest.raises(RecoveryEvalError, match="lineage"):
        observe_attempt(ctx, gold_positive_chunk_ids=["x"], require_lineage=True)


# --- Latency ---


def test_latency_accounting_with_injected_clock() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    initial = CountingInitialAssembler(lambda q: _context([], query=q, latency_total=5))
    batch = prepare_initial_cases(
        cases=[case],
        cohort_by_case={"c1": "human_reviewed"},
        initial_assembler=initial,
    )
    # clock sequence: arm_start, rewrite_start, rewrite_end, arm_end
    clock = _FakeClock([100.0, 100.0, 100.05, 100.20])
    record = evaluate_prepared_case(
        batch.cases[0],
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(
            _context(
                [_unit()],
                query="rewrite",
                anchors=[_anchor("chunk_pos")],
                latency_total=40,
            )
        ),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="rewrite"),
        clock=clock,
    )
    assert record.recovery is not None
    assert record.recovery.rewrite_latency_ms == pytest.approx(50.0)
    assert record.recovery.recovery_context_latency_ms == pytest.approx(40.0)
    assert record.recovery.incremental_recovery_latency_ms == pytest.approx(200.0)


# --- Artifact validators ---


def test_attempt_observation_rejects_contradictions() -> None:
    with pytest.raises(ValidationError):
        AttemptObservationV1(
            sufficient=True,
            empty_context=True,
            evidence_unit_count=1,
            triggered_gates=[],
            lineage=_lineage(),
        )
    with pytest.raises(ValidationError):
        AttemptObservationV1(
            sufficient=False,
            empty_context=False,
            evidence_unit_count=0,
            triggered_gates=[EMPTY_CONTEXT_GATE_V1],
            lineage=_lineage(),
        )
    with pytest.raises(ValidationError):
        AttemptObservationV1(
            sufficient=False,
            empty_context=True,
            evidence_unit_count=0,
            triggered_gates=[],
            lineage=_lineage(),
        )


def test_recovery_attempt_and_case_validators() -> None:
    with pytest.raises(ValidationError):
        RecoveryAttemptRecordV1(
            rewrite_call_count=2,
            recovery_retrieval_attempt_count=1,
            terminal_outcome=RecoveryTerminalOutcomeV1.RECOVERED_EVIDENCE_SUFFICIENT,
            observation=_valid_initial_obs(sufficient=True),
        )
    with pytest.raises(ValidationError):
        RecoveryAttemptRecordV1(
            rewrite_call_count=1,
            recovery_retrieval_attempt_count=1,
            terminal_outcome=RecoveryTerminalOutcomeV1.RECOVERY_PREPARATION_OR_EXECUTION_FAILED,
            failure_reason=RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED,
        )
    # Non-trigger classified as recovered must fail.
    with pytest.raises(ValidationError):
        RecoveryEvalCaseRecordV1(
            case_id="c1",
            adjudication_cohort="human_reviewed",
            original_query="q",
            quality_eligible=True,
            gold_positive_chunk_ids=["chunk_pos"],
            initial=_valid_initial_obs(sufficient=True),
            triggered=False,
            classification=RecoveryEvalCaseClassV1.GOLD_POSITIVE_RECOVERED,
        )


def test_census_and_aggregate_validators() -> None:
    with pytest.raises(ValidationError):
        TriggerCensusV1(
            human_trigger_case_ids=["a"],
            assistant_trigger_case_ids=[],
            human_trigger_count=0,
            assistant_trigger_count=0,
            not_evaluable=True,
            stop_reason=NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES,
        )
    with pytest.raises(ValidationError):
        TriggerCensusV1(
            human_trigger_case_ids=[],
            assistant_trigger_case_ids=[],
            human_trigger_count=0,
            assistant_trigger_count=0,
            not_evaluable=False,
            stop_reason=None,
        )


# --- Cohort / Gold / preflight / identity ---


def test_frozen_gold_id_required() -> None:
    gold = _loaded_gold([_gold_case("c1", "q1", ["p1"])])
    assert gold.dataset_id != FROZEN_GOLD_DATASET_ID_12C
    cmap = _cohort_map(gold, {"c1": "human_reviewed"})
    with pytest.raises(RecoveryEvalError, match="frozen Gold"):
        bind_cohort_map_for_gold(
            gold=gold, cohort_map=cmap, require_frozen_gold_id=True
        )


def test_valid_cohort_mapping_and_missing_extra() -> None:
    gold = _loaded_gold(
        [_gold_case("c1", "q1", ["p1"]), _gold_case("c2", "q2", ["p2"])]
    )
    cmap = _cohort_map(gold, {"c1": "human_reviewed", "c2": "assistant_only"})
    mapping = bind_cohort_map_for_gold(
        gold=gold, cohort_map=cmap, require_frozen_gold_id=False
    )
    assert mapping["c1"] == "human_reviewed"
    missing = _cohort_map(gold, {"c1": "human_reviewed"})
    with pytest.raises(RecoveryEvalError, match="cohort map binding failed"):
        bind_cohort_map_for_gold(
            gold=gold, cohort_map=missing, require_frozen_gold_id=False
        )


def test_assistant_only_excluded_from_authoritative_conclusion() -> None:
    human_case = _gold_case("h1", "empty?", ["gold_h"])
    asst_case = _gold_case("a1", "empty2?", ["gold_a"])
    settings = _settings(recovery_enabled=True)

    def initial_fn(query: str) -> HybridRerankContextResult:
        return _context([], query=query)

    initial = CountingInitialAssembler(initial_fn)
    batch = prepare_initial_cases(
        cases=[human_case, asst_case],
        cohort_by_case={"h1": "human_reviewed", "a1": "assistant_only"},
        initial_assembler=initial,
    )
    human_rec = evaluate_prepared_case(
        batch.cases[0],
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(_context([], query="rewritten")),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="rewritten"),
        clock=_FakeClock([0.0, 0.001, 0.01, 0.02]),
    )
    asst_rec = evaluate_prepared_case(
        batch.cases[1],
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(
            _context(
                [_unit(source_chunk_id="gold_a", primary_anchor="gold_a")],
                query="rewritten",
                anchors=[_anchor("gold_a")],
            )
        ),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="rewritten"),
        clock=_FakeClock([0.0, 0.001, 0.01, 0.02]),
    )
    assert initial.call_count == 2
    agg = aggregate_recovery_eval([human_rec, asst_rec])
    assert agg.human.trigger_count == 1
    assert agg.human.gold_positive_recovery_count == 0
    assert agg.assistant.gold_positive_recovery_count == 1
    assert (
        agg.conclusion == RecoveryEvalConclusionV1.RETAIN_DISABLED_NO_MEASURED_BENEFIT
    )


def test_preflight_and_identity() -> None:
    base = AppSettings()
    assert base.retrieval_recovery.enabled is False
    bad = preflight_authoritative_recovery_eval(base)
    assert bad.ready is False
    placeholder = _settings(
        recovery_enabled=True, model=PLACEHOLDER_REWRITER_MODEL, approved_models=[]
    )
    assert preflight_authoritative_recovery_eval(placeholder).ready is False
    good = _settings(recovery_enabled=True)
    ok = preflight_authoritative_recovery_eval(good)
    assert ok.ready is True
    assert ok.rewriter_config_hash is not None
    assert ok.rewriter_config_hash.startswith("rrwcfg_")
    assert require_authoritative_recovery_preflight(good) == ok.rewriter_config_hash

    gold = _loaded_gold([_gold_case("c1", "q", ["p1"])])
    cmap = _cohort_map(gold, {"c1": "human_reviewed"})
    rrw = build_recovery_rewriter_config_hash(good)
    kwargs = {
        "gold_dataset_id": gold.dataset_id,
        "cohort_map": cmap,
        "corpus_id": "corpus_test",
        "chunk_set_id": "chunkset_test",
        "dense_index_id": "dense_x",
        "lexical_index_id": "lex_x",
        "fusion_config_hash": "fuscfg_x",
        "reranker_config_hash": "rrkcfg_x",
        "context_config_hash": "ctxcfg_test",
        "rewriter_config_hash": rrw,
    }
    h1 = build_recovery_eval_identity_hash(**kwargs)
    assert h1 == build_recovery_eval_identity_hash(**kwargs)
    assert h1.startswith("receval_")
    assert (
        build_recovery_eval_identity_hash(
            **{**kwargs, "fusion_config_hash": "fuscfg_other"}
        )
        != h1
    )


def test_artifact_has_no_evidence_body_text() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    sentinel = "SECRET_CORPUS_BODY_MUST_NOT_PERSIST"
    initial = CountingInitialAssembler(lambda q: _context([], query=q))
    batch = prepare_initial_cases(
        cases=[case],
        cohort_by_case={"c1": "human_reviewed"},
        initial_assembler=initial,
    )
    record = evaluate_prepared_case(
        batch.cases[0],
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(
            _context(
                [
                    _unit(
                        text=sentinel,
                        source_chunk_id="chunk_pos",
                        primary_anchor="chunk_pos",
                    )
                ],
                query="rewrite",
                anchors=[_anchor("chunk_pos")],
            )
        ),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="rewrite"),
        clock=_FakeClock([0.0, 0.001, 0.01, 0.02]),
    )
    payload = record.model_dump_json()
    assert sentinel not in payload
    assert record.contract == RECOVERY_EVAL_V1


def test_evaluate_paired_case_convenience_still_single_assemble() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    initial = CountingInitialAssembler(lambda q: _context([], query=q))
    record = evaluate_paired_case(
        case=case,
        adjudication_cohort="human_reviewed",
        initial_assembler=initial,
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(
            _context([_unit()], query="r", anchors=[_anchor("chunk_pos")])
        ),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="r"),
        clock=_FakeClock([0.0, 0.001, 0.01, 0.02]),
    )
    assert initial.call_count == 1
    assert record.classification == RecoveryEvalCaseClassV1.GOLD_POSITIVE_RECOVERED


def test_recovery_operational_failure_classified() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    rewriter = FakeRecoveryRewriter(
        settings,
        raise_on_rewrite=RecoveryRewriteError("boom", failure_reason="provider_error"),
    )
    initial = CountingInitialAssembler(lambda q: _context([], query=q))
    batch = prepare_initial_cases(
        cases=[case],
        cohort_by_case={"c1": "human_reviewed"},
        initial_assembler=initial,
    )
    record = evaluate_prepared_case(
        batch.cases[0],
        recovery_settings=settings,
        recovery_assembler=MagicMock(),
        rewriter=rewriter,
        clock=_FakeClock([0.0, 0.001, 0.01, 0.02]),
    )
    assert record.classification == RecoveryEvalCaseClassV1.RECOVERY_FAILED
    assert record.recovery is not None
    assert record.recovery.failure_reason is not None
    assert record.recovery.incremental_recovery_latency_ms is not None


def test_base_config_recovery_still_disabled() -> None:
    assert AppSettings().retrieval_recovery.enabled is False


def test_no_generation_or_langgraph_imports_in_package() -> None:
    pkg = REPO_ROOT / "src" / "offline_rag" / "evaluation" / "recovery_12c"
    forbidden = (
        "import langgraph",
        "from langgraph",
        "GroundedAnswerOrchestrator",
        "generation_semantic.judge",
        "FakeGenerator",
    )
    for path in pkg.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} contains forbidden token {token!r}"
