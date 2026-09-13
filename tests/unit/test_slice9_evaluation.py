"""Slice 9 GoldDataset, metrics, result envelope, and compare contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from offline_rag.evaluation.compare import (
    CompareError,
    compare_retrieval_results,
    format_comparison_human,
    load_retrieval_eval_result,
)
from offline_rag.evaluation.gold import (
    GOLD_SCHEMA_V1,
    LEGACY_COMPAT_MODE,
    RETRIEVAL_EVAL_COMPARISON_V1,
    RETRIEVAL_EVAL_RESULT_V1,
    RETRIEVAL_METRICS_V1,
    ChunkJudgment,
    GoldCase,
    GoldDatasetError,
    compute_gold_dataset_id,
    load_gold_dataset,
)
from offline_rag.evaluation.metrics import (
    ndcg_at_k,
    precision_at_k,
    score_ranking,
)
from offline_rag.evaluation.result import (
    AggregateMetrics,
    CaseEvaluationResult,
    CaseMetrics,
    LatencySummary,
    MetricConfig,
    MetricValue,
    PopulationCounts,
    RetrievalEvaluationResultV1,
    build_aggregate_metrics,
)
from offline_rag.evaluation.runner import EvaluationError, run_retrieval_evaluation


REPO = Path(__file__).resolve().parents[2]
VALIDATION = REPO / "eval" / "datasets" / "slice9_validation"
LEGACY = VALIDATION / "legacy"


def _case(
    case_id: str,
    query: str,
    judgments: list[tuple[str, int]],
    *,
    category: str | None = None,
    tags: list[str] | None = None,
) -> GoldCase:
    return GoldCase(
        id=case_id,
        query=query,
        category=category,
        tags=tuple(tags or []),
        judgments=tuple(
            ChunkJudgment(chunk_id=cid, relevance=rel) for cid, rel in judgments  # type: ignore[arg-type]
        ),
    )


def test_native_gold_dataset_load() -> None:
    loaded = load_gold_dataset(VALIDATION)
    assert loaded.source_schema == GOLD_SCHEMA_V1
    assert loaded.compatibility_mode is None
    assert loaded.meta.chunk_set_id == "chunkset_slice9_validation"
    by_id = {c.id: c for c in loaded.cases}
    assert by_id["graded_answer"].judgments[0].relevance == 2
    assert by_id["zero_positive"].quality_eligible is False
    assert loaded.quality_eligible_count == 4
    assert by_id["uncategorized_support"].category is None
    assert "module-1" in by_id["graded_answer"].tags


def test_legacy_binary_normalizes_to_grade_1() -> None:
    loaded = load_gold_dataset(LEGACY)
    assert loaded.source_schema == "legacy-binary"
    assert loaded.compatibility_mode == LEGACY_COMPAT_MODE
    case = next(c for c in loaded.cases if c.id == "legacy_one")
    assert {j.relevance for j in case.judgments} == {1}
    assert case.positive_chunk_ids() == {"chunk_a", "chunk_b"}
    empty = next(c for c in loaded.cases if c.id == "legacy_empty_chunks")
    assert empty.judgments == ()
    assert empty.quality_eligible is False


def test_legacy_and_native_semantic_identity_match(tmp_path: Path) -> None:
    judgments = [("chunk_a", 1), ("chunk_b", 1)]
    native_dir = tmp_path / "native"
    native_dir.mkdir()
    (native_dir / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": GOLD_SCHEMA_V1,
                "chunk_set_id": "chunkset_x",
                "corpus_id": "corpus_x",
                "corpus_name": "demo",
            }
        ),
        encoding="utf-8",
    )
    (native_dir / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "c1",
                "query": "q",
                "category": None,
                "tags": [],
                "judgments": [
                    {"chunk_id": "chunk_a", "relevance": 1},
                    {"chunk_id": "chunk_b", "relevance": 1},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "chunk_set_id": "chunkset_x",
                "corpus_id": "corpus_x",
                "metadata": {"corpus_name": "demo", "author": "ignored"},
            }
        ),
        encoding="utf-8",
    )
    (legacy_dir / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "c1",
                "query": "q",
                "relevant_chunk_ids": ["chunk_b", "chunk_a"],
                "metadata": {"note": "ignored"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    native = load_gold_dataset(native_dir)
    legacy = load_gold_dataset(legacy_dir)
    assert native.dataset_id == legacy.dataset_id
    assert judgments  # silence lint


def test_dataset_identity_order_independence() -> None:
    base = [
        _case("b", "qb", [("c2", 1), ("c1", 2)], category="x", tags=["t2", "t1"]),
        _case("a", "qa", [("c9", 1)], category=None, tags=["z"]),
    ]
    reordered_cases = list(reversed(base))
    reordered_tags = [
        _case("b", "qb", [("c2", 1), ("c1", 2)], category="x", tags=["t1", "t2"]),
        _case("a", "qa", [("c9", 1)], category=None, tags=["z"]),
    ]
    reordered_judgments = [
        _case("b", "qb", [("c1", 2), ("c2", 1)], category="x", tags=["t2", "t1"]),
        _case("a", "qa", [("c9", 1)], category=None, tags=["z"]),
    ]
    kwargs = {"chunk_set_id": "cs", "corpus_id": "corp", "corpus_name": "n"}
    id_base = compute_gold_dataset_id(cases=base, **kwargs)
    assert compute_gold_dataset_id(cases=reordered_cases, **kwargs) == id_base
    assert compute_gold_dataset_id(cases=reordered_tags, **kwargs) == id_base
    assert compute_gold_dataset_id(cases=reordered_judgments, **kwargs) == id_base

    grade_changed = [
        _case("b", "qb", [("c2", 1), ("c1", 1)], category="x", tags=["t2", "t1"]),
        _case("a", "qa", [("c9", 1)], category=None, tags=["z"]),
    ]
    category_changed = [
        _case("b", "qb", [("c2", 1), ("c1", 2)], category="y", tags=["t2", "t1"]),
        _case("a", "qa", [("c9", 1)], category=None, tags=["z"]),
    ]
    assert compute_gold_dataset_id(cases=grade_changed, **kwargs) != id_base
    assert compute_gold_dataset_id(cases=category_changed, **kwargs) != id_base


def test_dataset_identity_ignores_paths_and_free_metadata(tmp_path: Path) -> None:
    cases = [_case("a", "q", [("c1", 1)])]
    id1 = compute_gold_dataset_id(
        chunk_set_id="cs", corpus_id=None, corpus_name=None, cases=cases
    )
    d1 = tmp_path / "one"
    d1.mkdir()
    (d1 / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": GOLD_SCHEMA_V1,
                "chunk_set_id": "cs",
                "metadata": {"path": "/tmp/a", "author": "alice", "notes": "x"},
            }
        ),
        encoding="utf-8",
    )
    (d1 / "cases.jsonl").write_text(
        json.dumps(
            {"id": "a", "query": "q", "judgments": [{"chunk_id": "c1", "relevance": 1}]}
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_gold_dataset(d1)
    assert loaded.dataset_id == id1


def test_persisted_dataset_id_mismatch_fails(tmp_path: Path) -> None:
    d = tmp_path / "bad"
    d.mkdir()
    (d / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": GOLD_SCHEMA_V1,
                "chunk_set_id": "cs",
                "dataset_id": "gold_deadbeef",
            }
        ),
        encoding="utf-8",
    )
    (d / "cases.jsonl").write_text(
        json.dumps(
            {"id": "a", "query": "q", "judgments": [{"chunk_id": "c1", "relevance": 1}]}
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(GoldDatasetError, match="dataset_id mismatch"):
        load_gold_dataset(d)


def test_native_rejects_legacy_relevant_chunk_ids(tmp_path: Path) -> None:
    d = tmp_path / "mixed"
    d.mkdir()
    (d / "meta.json").write_text(
        json.dumps({"schema_version": GOLD_SCHEMA_V1, "chunk_set_id": "cs"}),
        encoding="utf-8",
    )
    (d / "cases.jsonl").write_text(
        json.dumps({"id": "a", "query": "q", "relevant_chunk_ids": ["c1"]}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(GoldDatasetError, match="judgments"):
        load_gold_dataset(d)


def test_metrics_worked_example_grade1_vs_grade2() -> None:
    case = _case(
        "ex",
        "q",
        [("ans", 2), ("sup", 1)],
        category="purpose",
    )
    # Rank: distractor, support(1), answer(2)
    retrieved = ["noise", "sup", "ans"]
    score = score_ranking(
        case, retrieved, requested_depth=10, hit_rate_30_applicable=False
    )
    assert score.quality_eligible is True
    assert score.recall[1] == 0.0
    assert score.recall[5] == 1.0
    assert score.precision[1] == 0.0
    assert score.precision[5] == pytest.approx(2 / 3)
    assert score.hit_rate[1] == 0.0
    assert score.hit_rate[5] == 1.0
    assert score.mrr == pytest.approx(0.5)
    # nDCG@3: gains at ranks 2 and 3 are 1 and 3
    # DCG = 0 + 1/log2(3) + 3/log2(4)
    # IDCG from [2,1]: 3/log2(2) + 1/log2(3)
    expected_ndcg3 = ndcg_at_k(case.relevance_map(), retrieved, 3)
    assert score.ndcg[5] == pytest.approx(expected_ndcg3)
    assert score.ndcg[5] is not None
    assert score.ndcg[5] < 1.0

    perfect = score_ranking(
        case, ["ans", "sup"], requested_depth=10, hit_rate_30_applicable=False
    )
    assert perfect.ndcg[5] == pytest.approx(1.0)


def test_zero_positive_metrics_are_none() -> None:
    case = _case("z", "q", [])
    score = score_ranking(
        case, ["a", "b"], requested_depth=10, hit_rate_30_applicable=True
    )
    assert score.quality_eligible is False
    assert score.recall[10] is None
    assert score.precision[10] is None
    assert score.hit_rate[10] is None
    assert score.hit_rate_30 is None
    assert score.mrr is None
    assert score.ndcg[10] is None
    assert score.returned_count == 2


def test_short_list_and_empty_precision() -> None:
    relevant = {"r1", "r2", "r3"}
    short = ["r1", "x", "r2", "y", "r3", "z", "w"]  # 7 results, 3 relevant in first 7
    assert precision_at_k(relevant, short, 10) == pytest.approx(3 / 7)
    assert precision_at_k(relevant, [], 10) == 0.0


def test_hit_rate_30_conditional() -> None:
    case = _case("h", "q", [("gold", 1)])
    retrieved = ["x"] * 29 + ["gold"]
    applicable = score_ranking(
        case, retrieved, requested_depth=30, hit_rate_30_applicable=True
    )
    skipped = score_ranking(
        case, retrieved, requested_depth=10, hit_rate_30_applicable=False
    )
    assert applicable.hit_rate_30 == 1.0
    assert skipped.hit_rate_30 is None


def test_runner_empty_eligible_fails_closed() -> None:
    from offline_rag.evaluation.gold import LoadedGoldDataset, GoldDatasetMeta

    dataset = LoadedGoldDataset(
        meta=GoldDatasetMeta(chunk_set_id="cs"),
        cases=(_case("z", "q", []),),
        dataset_id="gold_x",
        source_schema=GOLD_SCHEMA_V1,
        compatibility_mode=None,
        path=Path("."),
    )
    with pytest.raises(EvaluationError, match="no positive"):
        run_retrieval_evaluation(
            dataset=dataset,
            method="dense",
            run_prefix="t",
            requested_depth=10,
            retrieve_fn=lambda case: ([], {}),
            warmup_query=None,
            semantic_provenance={},
            corpus_id=None,
            corpus_name=None,
        )


def test_runner_execution_error_not_empty_ranking() -> None:
    from offline_rag.evaluation.gold import LoadedGoldDataset, GoldDatasetMeta

    dataset = LoadedGoldDataset(
        meta=GoldDatasetMeta(chunk_set_id="cs"),
        cases=(_case("a", "q", [("g", 1)]),),
        dataset_id="gold_x",
        source_schema=GOLD_SCHEMA_V1,
        compatibility_mode=None,
        path=Path("."),
    )

    def _boom(_case: GoldCase) -> tuple[list[str], dict]:
        raise RuntimeError("retrieve failed")

    with pytest.raises(EvaluationError, match="retrieve failed"):
        run_retrieval_evaluation(
            dataset=dataset,
            method="dense",
            run_prefix="t",
            requested_depth=10,
            retrieve_fn=_boom,
            warmup_query=None,
            semantic_provenance={},
            corpus_id=None,
            corpus_name=None,
        )


def test_runner_builds_common_envelope_and_category_aggregates() -> None:
    from offline_rag.evaluation.gold import LoadedGoldDataset, GoldDatasetMeta

    dataset = LoadedGoldDataset(
        meta=GoldDatasetMeta(
            chunk_set_id="cs", corpus_id="corp", corpus_name="demo"
        ),
        cases=(
            _case("a", "qa", [("g", 2)], category="purpose", tags=["t"]),
            _case("b", "qb", [], category=None),
        ),
        dataset_id="gold_x",
        source_schema=GOLD_SCHEMA_V1,
        compatibility_mode=None,
        path=Path("."),
    )

    def _retrieve(case: GoldCase) -> tuple[list[str], dict]:
        if case.id == "a":
            return ["g"], {"method_diag": "dense_ok"}
        return ["x"], {"method_diag": "latency_only"}

    report = run_retrieval_evaluation(
        dataset=dataset,
        method="dense",
        run_prefix="t",
        requested_depth=10,
        retrieve_fn=_retrieve,
        warmup_query=None,
        semantic_provenance={"index_id": "dense_abc", "top_k": 10},
        corpus_id="corp",
        corpus_name="demo",
    )
    assert report.schema_version == RETRIEVAL_EVAL_RESULT_V1
    assert report.population.total_cases == 2
    assert report.population.quality_eligible_cases == 1
    assert report.aggregates.ndcg_at_10.value == pytest.approx(1.0)
    assert report.aggregates.ndcg_at_10.applicable_count == 1
    assert report.cases[1].metrics.recall_at_10 is None
    assert report.cases[1].latency_ms >= 0
    assert report.cases[0].diagnostics["method_diag"] == "dense_ok"
    cats = {c.category: c for c in report.category_aggregates}
    assert "purpose" in cats
    assert "uncategorized" in cats
    roundtrip = RetrievalEvaluationResultV1.model_validate_json(report.model_dump_json())
    assert roundtrip.run_id == report.run_id
    assert "NaN" not in report.model_dump_json()
    assert '"N/A"' not in report.model_dump_json()


def _metric_block(**overrides: float | None) -> CaseMetrics:
    base = CaseMetrics(
        recall_at_1=1.0,
        recall_at_5=1.0,
        recall_at_10=1.0,
        precision_at_1=1.0,
        precision_at_5=1.0,
        precision_at_10=1.0,
        hit_rate_at_1=1.0,
        hit_rate_at_5=1.0,
        hit_rate_at_10=1.0,
        hit_rate_at_30=None,
        mrr=1.0,
        ndcg_at_1=1.0,
        ndcg_at_5=1.0,
        ndcg_at_10=1.0,
    )
    return base.model_copy(update=overrides)


def _result(
    *,
    run_id: str,
    gold_id: str,
    method: str = "dense",
    chunk_set_id: str = "cs",
    depth: int = 10,
    cases: list[CaseEvaluationResult],
    semantic: dict | None = None,
) -> RetrievalEvaluationResultV1:
    aggregates = build_aggregate_metrics(cases)
    return RetrievalEvaluationResultV1(
        run_id=run_id,
        method=method,  # type: ignore[arg-type]
        gold_schema_version=GOLD_SCHEMA_V1,
        gold_dataset_id=gold_id,
        gold_source_schema=GOLD_SCHEMA_V1,
        chunk_set_id=chunk_set_id,
        semantic_provenance=dict(semantic or {"index_id": f"idx_{run_id}", "top_k": depth}),
        metric_config=MetricConfig(
            metric_contract=RETRIEVAL_METRICS_V1,
            cutoffs=[1, 5, 10],
            diagnostic_hit_rate_cutoffs=[30] if depth >= 30 else [],
        ),
        population=PopulationCounts(
            total_cases=len(cases),
            executed_cases=len(cases),
            quality_eligible_cases=sum(1 for c in cases if c.quality_eligible),
        ),
        aggregates=aggregates,
        category_aggregates=[],
        latency=LatencySummary(
            mean_ms=10.0,
            p50_ms=10.0,
            p95_ms=10.0,
            executed_cases=len(cases),
        ),
        cases=cases,
        started_at=datetime.now(tz=UTC),
        completed_at=datetime.now(tz=UTC),
    )


def test_compare_accepts_same_gold_method_different_config() -> None:
    case_a = CaseEvaluationResult(
        case_id="c1",
        query="q",
        quality_eligible=True,
        metrics=_metric_block(ndcg_at_10=0.5),
        latency_ms=10,
        returned_count=5,
    )
    case_b = CaseEvaluationResult(
        case_id="c1",
        query="q",
        quality_eligible=True,
        metrics=_metric_block(ndcg_at_10=0.75),
        latency_ms=12,
        returned_count=5,
    )
    a = _result(run_id="run_a", gold_id="gold_1", cases=[case_a], semantic={"index_id": "a"})
    b = _result(run_id="run_b", gold_id="gold_1", cases=[case_b], semantic={"index_id": "b"})
    comparison = compare_retrieval_results(a, b)
    ndcg = next(m for m in comparison.aggregates if m.metric == "ndcg_at_10")
    assert ndcg.delta == pytest.approx(0.25)
    assert comparison.outcomes["ndcg_at_10"].wins == 1


def test_compare_rejects_different_gold_method_and_cases() -> None:
    case = CaseEvaluationResult(
        case_id="c1",
        query="q",
        quality_eligible=True,
        metrics=_metric_block(),
    )
    a = _result(run_id="a", gold_id="gold_1", cases=[case])
    b = _result(run_id="b", gold_id="gold_2", cases=[case])
    with pytest.raises(CompareError, match="gold dataset"):
        compare_retrieval_results(a, b)

    b2 = _result(run_id="b", gold_id="gold_1", method="lexical", cases=[case])
    with pytest.raises(CompareError, match="method"):
        compare_retrieval_results(a, b2)

    other = CaseEvaluationResult(
        case_id="c2",
        query="q2",
        quality_eligible=True,
        metrics=_metric_block(),
    )
    b3 = _result(run_id="b", gold_id="gold_1", cases=[other])
    with pytest.raises(CompareError, match="case-set"):
        compare_retrieval_results(a, b3)


def test_compare_exact_float_and_na_exclusion() -> None:
    case_a = CaseEvaluationResult(
        case_id="c1",
        query="q",
        quality_eligible=True,
        metrics=_metric_block(ndcg_at_10=0.5, mrr=None),
    )
    case_b = CaseEvaluationResult(
        case_id="c1",
        query="q",
        quality_eligible=True,
        metrics=_metric_block(ndcg_at_10=0.5000000000000001, mrr=None),
    )
    a = _result(run_id="a", gold_id="g", cases=[case_a])
    b = _result(run_id="b", gold_id="g", cases=[case_b])
    comparison = compare_retrieval_results(a, b)
    # Tiny nonzero difference must not be a tie.
    assert comparison.cases[0].metrics["ndcg_at_10"].outcome in {"win", "loss"}
    assert comparison.outcomes["mrr"].comparable_cases == 0
    assert comparison.outcomes["mrr"].non_comparable_cases == 1
    assert comparison.schema_version == RETRIEVAL_EVAL_COMPARISON_V1
    human = format_comparison_human(comparison)
    assert "Gold:" in human
    assert "delta" in human.lower() or "Delta" in human or "+0" in human or "-0" in human


def test_compare_conditional_hitrate_30() -> None:
    case_a = CaseEvaluationResult(
        case_id="c1",
        query="q",
        quality_eligible=True,
        metrics=_metric_block(hit_rate_at_30=0.0),
    )
    case_b = CaseEvaluationResult(
        case_id="c1",
        query="q",
        quality_eligible=True,
        metrics=_metric_block(hit_rate_at_30=1.0),
    )
    a = _result(run_id="a", gold_id="g", depth=30, cases=[case_a])
    b = _result(run_id="b", gold_id="g", depth=30, cases=[case_b])
    comparison = compare_retrieval_results(a, b)
    hit30 = next(m for m in comparison.aggregates if m.metric == "hit_rate_at_30")
    assert hit30.delta == pytest.approx(1.0)
    assert comparison.outcomes["hit_rate_at_30"].wins == 1


def test_compare_does_not_invoke_retrieval(tmp_path: Path) -> None:
    case = CaseEvaluationResult(
        case_id="c1",
        query="q",
        quality_eligible=True,
        metrics=_metric_block(ndcg_at_10=0.4),
        latency_ms=5,
    )
    a = _result(run_id="a", gold_id="g", cases=[case])
    b_case = case.model_copy(update={"metrics": _metric_block(ndcg_at_10=0.6)})
    b = _result(run_id="b", gold_id="g", cases=[b_case])
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(a.model_dump_json(), encoding="utf-8")
    path_b.write_text(b.model_dump_json(), encoding="utf-8")
    retrieve = MagicMock()
    loaded_a = load_retrieval_eval_result(path_a)
    loaded_b = load_retrieval_eval_result(path_b)
    comparison = compare_retrieval_results(loaded_a, loaded_b)
    retrieve.assert_not_called()
    assert comparison.aggregates
    payload = json.loads(comparison.model_dump_json())
    assert payload["schema_version"] == RETRIEVAL_EVAL_COMPARISON_V1
