"""Slice 12C-1 — recovery evaluation harness contracts (no measure-once)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
    CountingInitialAssembler,
    RecoveryEvalCaseClassV1,
    RecoveryEvalConclusionV1,
    RecoveryEvalError,
    aggregate_recovery_eval,
    assert_single_initial_assemble,
    bind_cohort_map_for_gold,
    build_recovery_eval_identity_hash,
    build_trigger_census,
    census_from_initial_attempts,
    classify_case,
    conclude_recovery_eval,
    evaluate_paired_case,
    evidence_surface_chunk_ids_from_context,
    gold_positive_overlap,
    is_recovery_triggered,
    observe_attempt,
    preflight_authoritative_recovery_eval,
    require_authoritative_recovery_preflight,
)
from offline_rag.recovery import (
    RECOVERY_REWRITE_OUTPUT_V1,
    RECOVERY_REWRITE_PROMPT_V1,
    FakeRecoveryRewriter,
    RecoveryRewriteError,
)
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


def _gold_case(
    case_id: str,
    query: str,
    positives: list[str],
) -> GoldCase:
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
        (
            0,
            1,
            0,
            0,
            0,
            RecoveryEvalConclusionV1.INSUFFICIENT_EVIDENCE_FOR_RECOVERY_EFFICACY,
        ),
        (2, 0, 0, 0, 0, RecoveryEvalConclusionV1.RETAIN_DISABLED_NO_MEASURED_BENEFIT),
        (2, 1, 1, 0, 0, RecoveryEvalConclusionV1.RETAIN_DISABLED_RECOVERY_REGRESSION),
        (2, 1, 0, 1, 0, RecoveryEvalConclusionV1.RETAIN_DISABLED_RECOVERY_REGRESSION),
        (2, 1, 0, 0, 1, RecoveryEvalConclusionV1.RETAIN_DISABLED_RECOVERY_REGRESSION),
        (2, 0, 1, 0, 0, RecoveryEvalConclusionV1.RETAIN_DISABLED_RECOVERY_REGRESSION),
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


# --- Trigger / classify ---


def test_only_empty_evidence_units_trigger() -> None:
    empty = evaluate_sufficiency_policy_v1(evidence_units=[])
    nonempty = evaluate_sufficiency_policy_v1(evidence_units=[_unit()])
    assert is_recovery_triggered(empty) is True
    assert EMPTY_CONTEXT_GATE_V1 in empty.triggered_gates
    assert is_recovery_triggered(nonempty) is False


def test_classify_gold_positive_and_unsupported() -> None:
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
    assert (
        classify_case(triggered=True, recovery_failed=True, recovery_observation=None)
        == RecoveryEvalCaseClassV1.RECOVERY_FAILED
    )
    assert (
        classify_case(triggered=False, recovery_failed=False, recovery_observation=None)
        == RecoveryEvalCaseClassV1.INITIAL_SUFFICIENT_NO_RECOVERY
    )


def test_evidence_surface_exact_chunk_ids_no_text_similarity() -> None:
    ctx = _context(
        [_unit(source_chunk_id="parent_x", primary_anchor="child_y")],
        anchors=[_anchor("anchor_z")],
    )
    surface = evidence_surface_chunk_ids_from_context(ctx)
    assert surface == {"parent_x", "child_y", "anchor_z"}
    ok, present = gold_positive_overlap(
        gold_positive_chunk_ids={"child_y", "missing"},
        evidence_surface=surface,
    )
    assert ok is True
    assert present == ["child_y"]


# --- Cohort / Gold binding ---


def test_frozen_gold_id_required() -> None:
    gold = _loaded_gold([_gold_case("c1", "q1", ["p1"])])
    assert gold.dataset_id != FROZEN_GOLD_DATASET_ID_12C
    cmap = _cohort_map(gold, {"c1": "human_reviewed"})
    with pytest.raises(RecoveryEvalError, match="frozen Gold"):
        bind_cohort_map_for_gold(
            gold=gold, cohort_map=cmap, require_frozen_gold_id=True
        )


def test_valid_cohort_mapping_accepted() -> None:
    cases = [
        _gold_case("h1", "q1", ["p1"]),
        _gold_case("a1", "q2", ["p2"]),
    ]
    # pad to 16/6 shape is not required for unit binding; exact set match is.
    gold = _loaded_gold(cases)
    cmap = _cohort_map(gold, {"h1": "human_reviewed", "a1": "assistant_only"})
    mapping = bind_cohort_map_for_gold(
        gold=gold, cohort_map=cmap, require_frozen_gold_id=False
    )
    assert mapping == {"h1": "human_reviewed", "a1": "assistant_only"}


def test_missing_and_extra_case_fail() -> None:
    gold = _loaded_gold(
        [_gold_case("c1", "q1", ["p1"]), _gold_case("c2", "q2", ["p2"])]
    )
    missing = _cohort_map(gold, {"c1": "human_reviewed"})
    with pytest.raises(RecoveryEvalError, match="cohort map binding failed"):
        bind_cohort_map_for_gold(
            gold=gold, cohort_map=missing, require_frozen_gold_id=False
        )
    extra = GenerationCohortMapV1.model_validate(
        {
            "schema_version": "offline-rag-generation-cohort-map-v1",
            "gold_dataset_id": gold.dataset_id,
            "cases": [
                {"case_id": "c1", "label_cohort": "human_reviewed"},
                {"case_id": "c2", "label_cohort": "human_reviewed"},
                {"case_id": "c3", "label_cohort": "assistant_only"},
            ],
        }
    )
    with pytest.raises(RecoveryEvalError, match="cohort map binding failed"):
        bind_cohort_map_for_gold(
            gold=gold, cohort_map=extra, require_frozen_gold_id=False
        )


def test_assistant_only_excluded_from_authoritative_conclusion() -> None:
    human_case = _gold_case("h1", "empty?", ["gold_h"])
    asst_case = _gold_case("a1", "empty2?", ["gold_a"])
    settings = _settings(recovery_enabled=True)
    rewriter = FakeRecoveryRewriter(settings, rewritten_query="rewritten empty")

    def initial_fn(query: str) -> HybridRerankContextResult:
        return _context([], query=query)

    initial = CountingInitialAssembler(initial_fn)
    recovery_ctx = _context(
        [_unit(source_chunk_id="gold_a", primary_anchor="gold_a")],
        query="rewritten empty",
        anchors=[_anchor("gold_a")],
    )
    assembler = _recovery_assembler(recovery_ctx)

    human_rec = evaluate_paired_case(
        case=human_case,
        adjudication_cohort="human_reviewed",
        initial_assembler=initial,
        recovery_settings=settings,
        recovery_assembler=assembler,
        rewriter=rewriter,
    )
    asst_rec = evaluate_paired_case(
        case=asst_case,
        adjudication_cohort="assistant_only",
        initial_assembler=initial,
        recovery_settings=settings,
        recovery_assembler=assembler,
        rewriter=rewriter,
    )
    # Human still insufficient (recovery returned assistant gold id only once —
    # force human recovery empty via second assemble empty).
    # Rebuild with empty recovery for human path clarity:
    empty_asm = _recovery_assembler(_context([], query="rewritten empty"))
    initial2 = CountingInitialAssembler(initial_fn)
    human_rec = evaluate_paired_case(
        case=human_case,
        adjudication_cohort="human_reviewed",
        initial_assembler=initial2,
        recovery_settings=settings,
        recovery_assembler=empty_asm,
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="rewritten empty"),
    )
    asst_rec = evaluate_paired_case(
        case=asst_case,
        adjudication_cohort="assistant_only",
        initial_assembler=initial2,
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(
            _context(
                [_unit(source_chunk_id="gold_a", primary_anchor="gold_a")],
                query="rewritten empty",
                anchors=[_anchor("gold_a")],
            )
        ),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="rewritten empty"),
    )
    agg = aggregate_recovery_eval([human_rec, asst_rec])
    assert agg.human.trigger_count == 1
    assert agg.human.gold_positive_recovery_count == 0
    assert agg.assistant.gold_positive_recovery_count == 1
    assert (
        agg.conclusion == RecoveryEvalConclusionV1.RETAIN_DISABLED_NO_MEASURED_BENEFIT
    )


# --- Shared initial / happy path ---


def test_one_initial_assemble_shared_by_arms() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    rewriter = FakeRecoveryRewriter(settings, rewritten_query="rewrite")
    calls: list[str] = []

    def initial_fn(query: str) -> HybridRerankContextResult:
        calls.append(f"initial:{query}")
        return _context([], query=query)

    initial = CountingInitialAssembler(initial_fn)
    recovery_asm = _recovery_assembler(
        _context(
            [_unit()],
            query="rewrite",
            anchors=[_anchor("chunk_pos")],
        )
    )
    record = evaluate_paired_case(
        case=case,
        adjudication_cohort="human_reviewed",
        initial_assembler=initial,
        recovery_settings=settings,
        recovery_assembler=recovery_asm,
        rewriter=rewriter,
    )
    assert initial.call_count == 1
    assert calls == ["initial:pressure?"]
    assert recovery_asm.assemble.call_count == 1
    assert record.triggered is True
    assert record.classification == RecoveryEvalCaseClassV1.GOLD_POSITIVE_RECOVERED
    assert_single_initial_assemble(initial, expected_cases=1)


def test_initially_sufficient_zero_rewrite_and_recovery_calls() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    rewriter = FakeRecoveryRewriter(settings, rewritten_query="should-not-run")
    initial = CountingInitialAssembler(
        lambda q: _context(
            [_unit()],
            query=q,
            anchors=[_anchor("chunk_pos")],
        )
    )
    recovery_asm = MagicMock()
    record = evaluate_paired_case(
        case=case,
        adjudication_cohort="human_reviewed",
        initial_assembler=initial,
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


def test_recovery_operational_failure_classified() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    rewriter = FakeRecoveryRewriter(
        settings,
        raise_on_rewrite=RecoveryRewriteError("boom", failure_reason="provider_error"),
    )
    initial = CountingInitialAssembler(lambda q: _context([], query=q))
    record = evaluate_paired_case(
        case=case,
        adjudication_cohort="human_reviewed",
        initial_assembler=initial,
        recovery_settings=settings,
        recovery_assembler=MagicMock(),
        rewriter=rewriter,
    )
    assert record.classification == RecoveryEvalCaseClassV1.RECOVERY_FAILED
    assert record.recovery is not None
    assert record.recovery.failure_reason is not None


# --- Trigger census ---


def test_trigger_census_stops_when_no_human_triggers() -> None:
    cases = [
        _gold_case("h1", "ok?", ["p1"]),
        _gold_case("a1", "empty?", ["p2"]),
    ]
    cohort = {"h1": "human_reviewed", "a1": "assistant_only"}

    def initial_fn(query: str) -> HybridRerankContextResult:
        if query == "empty?":
            return _context([], query=query)
        return _context([_unit()], query=query, anchors=[_anchor("p1")])

    census = census_from_initial_attempts(
        cases=cases,
        cohort_by_case=cohort,  # type: ignore[arg-type]
        initial_assembler=CountingInitialAssembler(initial_fn),
    )
    assert census.human_trigger_count == 0
    assert census.assistant_trigger_count == 1
    assert census.not_evaluable is True
    assert census.stop_reason == NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES


def test_build_trigger_census_from_records() -> None:
    case = _gold_case("h1", "empty?", ["p1"])
    settings = _settings(recovery_enabled=True)
    initial = CountingInitialAssembler(lambda q: _context([], query=q))
    record = evaluate_paired_case(
        case=case,
        adjudication_cohort="human_reviewed",
        initial_assembler=initial,
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(_context([], query="r")),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="r"),
    )
    census = build_trigger_census([record])
    assert census.human_trigger_count == 1
    assert census.not_evaluable is False


# --- Preflight / identity ---


def test_preflight_rejects_placeholder_and_disabled() -> None:
    base = AppSettings()
    assert base.retrieval_recovery.enabled is False
    bad = preflight_authoritative_recovery_eval(base)
    assert bad.ready is False
    assert any("enabled" in r for r in bad.reasons)

    placeholder = _settings(
        recovery_enabled=True, model=PLACEHOLDER_REWRITER_MODEL, approved_models=[]
    )
    pref = preflight_authoritative_recovery_eval(placeholder)
    assert pref.ready is False
    assert any("placeholder" in r or "approved_models" in r for r in pref.reasons)

    unapproved_model = _settings(
        recovery_enabled=True, model="other", approved_models=["rewrite-model"]
    )
    pref2 = preflight_authoritative_recovery_eval(unapproved_model)
    assert pref2.ready is False

    unapproved_endpoint = _settings(
        recovery_enabled=True,
        base_url="http://127.0.0.1:9999/v1",
        approved_endpoints=["http://127.0.0.1:11434/v1"],
    )
    pref3 = preflight_authoritative_recovery_eval(unapproved_endpoint)
    assert pref3.ready is False

    good = _settings(recovery_enabled=True)
    ok = preflight_authoritative_recovery_eval(good)
    assert ok.ready is True
    assert ok.rewriter_config_hash is not None
    assert ok.rewriter_config_hash.startswith("rrwcfg_")
    assert require_authoritative_recovery_preflight(good) == ok.rewriter_config_hash


def test_identity_hash_stable_excludes_secrets_and_latency() -> None:
    gold = _loaded_gold([_gold_case("c1", "q", ["p1"])])
    cmap = _cohort_map(gold, {"c1": "human_reviewed"})
    rrw = build_recovery_rewriter_config_hash(_settings(recovery_enabled=True))
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
    h2 = build_recovery_eval_identity_hash(**kwargs)
    assert h1 == h2
    assert h1.startswith("receval_")
    changed = build_recovery_eval_identity_hash(
        **{**kwargs, "fusion_config_hash": "fuscfg_other"}
    )
    assert changed != h1


def test_stack_mismatch_fails_closed() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    rewriter = FakeRecoveryRewriter(settings, rewritten_query="rewrite")
    initial = CountingInitialAssembler(lambda q: _context([], query=q))
    bad_recovery = _context(
        [_unit()],
        query="rewrite",
        anchors=[_anchor("chunk_pos")],
    )
    # Different fusion hash ⇒ stack mismatch (coordinator fail-closed).
    bad_recovery = bad_recovery.model_copy(
        update={"fusion_config_hash": "fuscfg_OTHER"}
    )
    record = evaluate_paired_case(
        case=case,
        adjudication_cohort="human_reviewed",
        initial_assembler=initial,
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(bad_recovery),
        rewriter=rewriter,
    )
    assert record.classification == RecoveryEvalCaseClassV1.RECOVERY_FAILED
    assert record.recovery is not None
    assert record.recovery.failure_reason is not None


def test_artifact_has_no_evidence_body_text() -> None:
    case = _gold_case("c1", "pressure?", ["chunk_pos"])
    settings = _settings(recovery_enabled=True)
    sentinel = "SECRET_CORPUS_BODY_MUST_NOT_PERSIST"
    initial = CountingInitialAssembler(lambda q: _context([], query=q))
    recovery = _context(
        [_unit(text=sentinel, source_chunk_id="chunk_pos", primary_anchor="chunk_pos")],
        query="rewrite",
        anchors=[_anchor("chunk_pos")],
    )
    record = evaluate_paired_case(
        case=case,
        adjudication_cohort="human_reviewed",
        initial_assembler=initial,
        recovery_settings=settings,
        recovery_assembler=_recovery_assembler(recovery),
        rewriter=FakeRecoveryRewriter(settings, rewritten_query="rewrite"),
    )
    payload = record.model_dump_json()
    assert sentinel not in payload
    assert "SECRET_CORPUS" not in payload
    assert record.contract == RECOVERY_EVAL_V1


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
