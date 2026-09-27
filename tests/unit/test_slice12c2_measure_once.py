"""Slice 12C-2 measure-once orchestration / persistence tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from offline_rag.config.loader import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.evaluation.generation_semantic.models import GenerationCohortMapV1
from offline_rag.evaluation.gold import (
    ChunkJudgment,
    GoldCase,
)
from offline_rag.evaluation.recovery_12c.binding import cohort_map_semantic_hash
from offline_rag.evaluation.recovery_12c.contracts import (
    FROZEN_ADJUDICATION_COHORT_MAP_HASH_12C,
    FROZEN_GOLD_DATASET_ID_12C,
    AttemptObservationV1,
    RecoveryEvalError,
    TriggerCensusV1,
)
from offline_rag.evaluation.recovery_12c.harness import (
    PreparedRecoveryEvalBatch,
    PreparedRecoveryEvalCase,
)
from offline_rag.evaluation.recovery_12c.measure_once import (
    SharedInitialAssemblerAdapter,
    build_census_stop_aggregate,
    inject_recovery_rewriter_api_key_from_environ,
    prepared_case_from_runtime,
)
from offline_rag.evaluation.recovery_12c.measure_once_contracts import (
    ACCEPTED_HARNESS_SHA_12C,
    AUTHORITY_BASELINE_SHA_12C,
    RecoveryEvalCensusStopAggregateV1,
    RetrievalStackIdentityV1,
)
from offline_rag.recovery.lineage import RecoveryLineageV1
from offline_rag.recovery.rewrite_config_hash import build_recovery_rewriter_config_hash
from offline_rag.sufficiency.policy import EMPTY_CONTEXT_GATE_V1

REPO_ROOT = Path(__file__).resolve().parents[2]


def _settings_recovery(**rewriter_overrides) -> AppSettings:
    base = AppSettings()
    rewriter = base.retrieval_recovery.rewriter.model_copy(
        update={
            "base_url": "http://192.168.2.142:8888/v1",
            "model": "qwen3.6-35b-a3b",
            "approved_endpoints": ["http://192.168.2.142:8888/v1"],
            "approved_models": ["qwen3.6-35b-a3b"],
            "network_policy": "private_network",
            "api_key": None,
            **rewriter_overrides,
        }
    )
    recovery = base.retrieval_recovery.model_copy(
        update={"enabled": True, "max_retries": 1, "rewriter": rewriter}
    )
    return base.model_copy(update={"retrieval_recovery": recovery})


def test_recovery_only_overlay_preserves_baseline_retrieval_stack() -> None:
    base = load_settings(yaml_paths=[REPO_ROOT / "config" / "base.yaml"])
    overlay_path = (
        REPO_ROOT / "config" / "experiments" / "recovery_12c_measure_once.yaml"
    )
    merged = load_settings(
        yaml_paths=[REPO_ROOT / "config" / "base.yaml", overlay_path]
    )
    assert merged.retrieval_recovery.enabled is True
    assert merged.retrieval_recovery.rewriter.model == "qwen3.6-35b-a3b"
    assert merged.retrieval_recovery.rewriter.api_key is None
    assert merged.dense.model_dump() == base.dense.model_dump()
    assert merged.lexical.model_dump() == base.lexical.model_dump()
    assert merged.fusion.model_dump() == base.fusion.model_dump()
    assert merged.reranker.model_dump() == base.reranker.model_dump()
    assert merged.context.model_dump() == base.context.model_dump()
    raw = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    assert set(raw.keys()) == {"retrieval_recovery"}


def test_api_key_injection_runtime_only_and_hash_neutral() -> None:
    settings = _settings_recovery()
    left = build_recovery_rewriter_config_hash(settings)
    with pytest.raises(RecoveryEvalError, match="OFFLINE_RAG_LLM_API_KEY"):
        inject_recovery_rewriter_api_key_from_environ(settings, environ={})
    injected = inject_recovery_rewriter_api_key_from_environ(
        settings, environ={"OFFLINE_RAG_LLM_API_KEY": "secret-token"}
    )
    assert injected.retrieval_recovery.rewriter.api_key == "secret-token"
    assert settings.retrieval_recovery.rewriter.api_key is None
    right = build_recovery_rewriter_config_hash(injected)
    assert left == right
    assert "secret-token" not in left


def test_shared_initial_adapter_calls_assemble_with_corpus() -> None:
    inner = MagicMock()
    inner.assemble.return_value = MagicMock(query="q?")
    adapter = SharedInitialAssemblerAdapter(inner, corpus_name="ics_modules")
    adapter.assemble_initial("q?")
    inner.assemble.assert_called_once_with(query="q?", corpus_name="ics_modules")


def test_prepared_case_excludes_evidence_text_and_orders_fields() -> None:
    case = GoldCase(
        id="c1",
        query="pressure?",
        judgments=(ChunkJudgment(chunk_id="p1", relevance=1),),
    )
    obs = AttemptObservationV1(
        sufficient=True,
        empty_context=False,
        evidence_unit_count=1,
        triggered_gates=[],
        evidence_surface_chunk_ids=["p1"],
        ranked_anchor_chunk_ids=["p1"],
        gold_positive_overlap_chunk_ids=["p1"],
        gold_positive_overlap=True,
        lineage=RecoveryLineageV1(
            corpus_id="corpus_x",
            chunk_set_id="chunkset_x",
            dense_index_id="dense_x",
            lexical_index_id="lex_x",
            fusion_config_hash="fuscfg_x",
            reranker_config_hash="rrkcfg_x",
            context_config_hash="ctxcfg_x",
            query="pressure?",
        ),
        latency_ms=1.0,
    )
    prepared = PreparedRecoveryEvalCase(
        case=case,
        adjudication_cohort="human_reviewed",
        original_query="pressure?",
        initial_context=MagicMock(),
        initial_sufficiency=MagicMock(sufficient=True),
        initial_observation=obs,
        triggered=False,
    )
    row = prepared_case_from_runtime(prepared)
    payload = row.model_dump_json()
    assert "SECRET" not in payload
    assert "evidence_units" not in payload
    assert "assembled_text" not in payload
    assert row.contract == "recovery-eval-prepared-case-v1"
    assert row.initial_ranking is not None


def test_census_stop_aggregate_preserves_true_t_a() -> None:
    stack = RetrievalStackIdentityV1(
        corpus_id="corpus_x",
        chunk_set_id="chunkset_x",
        dense_index_id="dense_x",
        lexical_index_id="lex_x",
        fusion_config_hash="fuscfg_x",
        reranker_config_hash="rrkcfg_x",
        context_config_hash="ctxcfg_x",
    )
    cases = []
    for cid, cohort, triggered in (
        ("h1", "human_reviewed", False),
        ("h2", "human_reviewed", False),
        ("a1", "assistant_only", True),
        ("a2", "assistant_only", False),
    ):
        obs = AttemptObservationV1(
            sufficient=not triggered,
            empty_context=triggered,
            evidence_unit_count=0 if triggered else 1,
            triggered_gates=[EMPTY_CONTEXT_GATE_V1] if triggered else [],
            evidence_surface_chunk_ids=[] if triggered else ["p1"],
            ranked_anchor_chunk_ids=[] if triggered else ["p1"],
            gold_positive_overlap_chunk_ids=[],
            gold_positive_overlap=False,
            lineage=RecoveryLineageV1(
                corpus_id="corpus_x",
                chunk_set_id="chunkset_x",
                dense_index_id="dense_x",
                lexical_index_id="lex_x",
                fusion_config_hash="fuscfg_x",
                reranker_config_hash="rrkcfg_x",
                context_config_hash="ctxcfg_x",
                query=f"q-{cid}",
            ),
        )
        cases.append(
            PreparedRecoveryEvalCase(
                case=GoldCase(
                    id=cid,
                    query=f"q-{cid}",
                    judgments=(ChunkJudgment(chunk_id="p1", relevance=1),),
                ),
                adjudication_cohort=cohort,  # type: ignore[arg-type]
                original_query=f"q-{cid}",
                initial_context=MagicMock(),
                initial_sufficiency=MagicMock(sufficient=not triggered),
                initial_observation=obs,
                triggered=triggered,
            )
        )
    census = TriggerCensusV1(
        human_trigger_case_ids=[],
        assistant_trigger_case_ids=["a1"],
        human_trigger_count=0,
        assistant_trigger_count=1,
        not_evaluable=True,
        stop_reason="not_evaluable_no_human_recovery_opportunities",
    )
    batch = PreparedRecoveryEvalBatch(
        cases=tuple(cases),
        census=census,
        authoritative=True,
        gold_dataset_id=FROZEN_GOLD_DATASET_ID_12C,
        cohort_map_identity_hash=FROZEN_ADJUDICATION_COHORT_MAP_HASH_12C,
        prepared_case_set_hash="receval_prepared_test",
    )
    agg = build_census_stop_aggregate(
        batch=batch,
        census=census,
        rewriter_config_hash="rrwcfg_test",
        evaluation_identity_hash="receval_test",
        retrieval_lineage=stack,
    )
    assert isinstance(agg, RecoveryEvalCensusStopAggregateV1)
    assert agg.human_stage_a_trigger_count == 0
    assert agg.assistant_stage_a_trigger_count == 1
    assert agg.measured_recovery_case_count == 0
    assert agg.stage_b_executed is False
    assert agg.conclusion.value == "insufficient_evidence_for_recovery_efficacy"


def test_manifest_authority_shas_are_frozen() -> None:
    assert AUTHORITY_BASELINE_SHA_12C.startswith("47656d1")
    assert ACCEPTED_HARNESS_SHA_12C.startswith("c4f8734")


def test_tracked_cohort_fixture_hash_still_matches() -> None:
    from offline_rag.evaluation.generation_semantic.cohort import load_cohort_map

    path = (
        REPO_ROOT / "eval/fixtures/sufficiency/"
        "gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172"
        "_adjudication_cohort_map_v1.json"
    )
    cmap = load_cohort_map(path)
    assert cohort_map_semantic_hash(cmap) == FROZEN_ADJUDICATION_COHORT_MAP_HASH_12C
    assert isinstance(cmap, GenerationCohortMapV1)
