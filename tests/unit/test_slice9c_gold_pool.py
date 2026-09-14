"""Slice 9C: candidate-pooling-v1 ensemble, CLI, historical preflight."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from offline_rag.cli import build_parser, main
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import EXCLUDE_HEADING_ONLY_V1, MODEL_QUERY_PROMPT_V1
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.gold_authoring.chunk_access import CorpusChunkSnapshot
from offline_rag.gold_authoring.contracts import (
    POOLING_CONTRACT,
    POOLING_DEPTHS,
    POOLING_RETRIEVER_IDS,
    RETRIEVER_DENSE_ARM_H_V1,
    RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1,
    RETRIEVER_DENSE_PLAIN_V1,
    RETRIEVER_HYBRID_RERANK_V1,
    RETRIEVER_HYBRID_RRF_V1,
    RETRIEVER_LEXICAL_PLAIN_V1,
)
from offline_rag.gold_authoring.models import (
    GoldAuthoringRun,
    HumanReviewStatus,
    SilverCase,
    SourceSeed,
)
from offline_rag.gold_authoring.persist import load_authoring_run, write_authoring_run
from offline_rag.gold_authoring.pool import PoolPreRunError, run_gold_pool
from offline_rag.gold_authoring.pool_arms import ArmExecutionError, ArmHit, HistoricalPoolArmExecutor
from offline_rag.gold_authoring.pool_preflight import (
    PoolPreflightError,
    ResolvedPoolingArtifacts,
    preflight_pooling_artifacts,
)
from offline_rag.gold_authoring.pool_union import order_pool_candidates, union_candidates
from offline_rag.gold_authoring.pooling_models import (
    PoolCandidate,
    PoolCaseStatus,
    PoolFailureReason,
    PoolingProvenance,
    RetrievalHit,
)
from offline_rag.rerank.fake import FakeReranker

BODY_MARKER = "UNIQUE_PRIVATE_CANDIDATE_BODY_9C_ZXCVBN"


def _chunk(
    chunk_id: str,
    *,
    document_id: str = "doc_a",
    text: str = "public body",
    section_path: list[str] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        kind=ChunkKind.CHILD,
        text=text,
        order=0,
        token_count=8,
        content_type="text",
        content_hash="hash",
        source_block_ids=["b1"],
        section_path=section_path or ["SECTION"],
    )


def _artifacts(*, chunk_set_id: str = "chunkset_A") -> ResolvedPoolingArtifacts:
    return ResolvedPoolingArtifacts(
        chunk_set_id=chunk_set_id,
        corpus_id="corpus_A",
        corpus_name="default",
        lexical_index_id="lex_A",
        dense_baseline_index_id="dense_A",
        dense_arm_h_index_id="dense_armh_A",
        provenance=PoolingProvenance(
            pooling_contract=POOLING_CONTRACT,
            source_chunk_set_id=chunk_set_id,
            artifact_ids={
                RETRIEVER_LEXICAL_PLAIN_V1: "lex_A",
                RETRIEVER_DENSE_PLAIN_V1: "dense_A",
                RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1: "dense_A",
                RETRIEVER_DENSE_ARM_H_V1: "dense_armh_A",
                RETRIEVER_HYBRID_RRF_V1: "hybrid(lex_A+dense_A)",
                RETRIEVER_HYBRID_RERANK_V1: "hybrid-rerank(lex_A+dense_A)",
            },
        ),
    )


def _snapshot(
    chunks: list[Chunk],
    *,
    chunk_set_id: str = "chunkset_A",
) -> CorpusChunkSnapshot:
    return CorpusChunkSnapshot(
        corpus_name="default",
        corpus_id="corpus_A",
        chunk_set_id=chunk_set_id,
        chunks=chunks,
        source_name_by_document_id={"doc_a": "Guide.pdf", "doc_b": "Other.md"},
    )


def _run(
    cases: list[SilverCase],
    *,
    chunk_set_id: str = "chunkset_A",
    authoring_run_id: str = "authorrun_test",
) -> GoldAuthoringRun:
    return GoldAuthoringRun(
        authoring_run_id=authoring_run_id,
        authorcfg_id="authorcfg_testhash",
        network_policy="localhost_only",
        corpus_id="corpus_A",
        corpus_name="default",
        chunk_set_id=chunk_set_id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        cases=cases,
    )


def _case(
    draft_id: str,
    query: str,
    *,
    candidates: list[PoolCandidate] | None = None,
) -> SilverCase:
    return SilverCase(
        draft_case_id=draft_id,
        human_status=HumanReviewStatus.PENDING,
        proposed_query=query,
        source_seed=SourceSeed(chunk_id="seed_1", document_id="doc_a"),
        candidates=list(candidates or []),
    )


def _hit(retriever: str, chunk_id: str, rank: int, score: float | None = 1.0) -> RetrievalHit:
    return RetrievalHit(retriever=retriever, chunk_id=chunk_id, rank=rank, score=score)


class RecordingExecutor:
    """Deterministic six-arm fake for unit tests."""

    def __init__(
        self,
        responses: dict[str, dict[str, list[RetrievalHit]]] | None = None,
        *,
        fail_arm: str | None = None,
        fail_reason: PoolFailureReason = PoolFailureReason.HYBRID_RERANK_FAILED,
        default_chunks: list[str] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.fail_arm = fail_arm
        self.fail_reason = fail_reason
        self.default_chunks = default_chunks or ["c1", "c2"]
        self.calls: list[str] = []
        self.queries: list[str] = []

    def execute_all(
        self,
        *,
        query: str,
        artifacts: ResolvedPoolingArtifacts,
    ) -> dict[str, list[RetrievalHit]]:
        self.calls.append(query)
        self.queries.append(query)
        if self.fail_arm is not None:
            raise ArmExecutionError(
                f"forced failure on {self.fail_arm}",
                reason=self.fail_reason,
                retriever=self.fail_arm,
            )
        if query in self.responses:
            return self.responses[query]
        out: dict[str, list[RetrievalHit]] = {}
        for arm in POOLING_RETRIEVER_IDS:
            depth = POOLING_DEPTHS[arm]
            hits = []
            for i, cid in enumerate(self.default_chunks[:depth], start=1):
                hits.append(_hit(arm, cid, i, score=100.0 - i))
            out[arm] = hits
        return out


def _patch_preflight_ok(artifacts: ResolvedPoolingArtifacts, snapshot: CorpusChunkSnapshot):
    return (
        patch(
            "offline_rag.gold_authoring.pool.preflight_pooling_artifacts",
            return_value=artifacts,
        ),
        patch(
            "offline_rag.gold_authoring.pool._load_historical_snapshot",
            return_value=snapshot,
        ),
    )


def test_pooling_depths_locked() -> None:
    assert POOLING_DEPTHS == {
        RETRIEVER_LEXICAL_PLAIN_V1: 50,
        RETRIEVER_DENSE_PLAIN_V1: 50,
        RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1: 50,
        RETRIEVER_DENSE_ARM_H_V1: 50,
        RETRIEVER_HYBRID_RRF_V1: 50,
        RETRIEVER_HYBRID_RERANK_V1: 20,
    }
    assert len(POOLING_RETRIEVER_IDS) == 6


def test_union_dedupes_and_preserves_hits() -> None:
    hits = {
        RETRIEVER_LEXICAL_PLAIN_V1: [_hit(RETRIEVER_LEXICAL_PLAIN_V1, "c1", 1, 9.0)],
        RETRIEVER_DENSE_PLAIN_V1: [_hit(RETRIEVER_DENSE_PLAIN_V1, "c1", 3, 0.9)],
        RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1: [],
        RETRIEVER_DENSE_ARM_H_V1: [],
        RETRIEVER_HYBRID_RRF_V1: [_hit(RETRIEVER_HYBRID_RRF_V1, "c2", 1, 0.5)],
        RETRIEVER_HYBRID_RERANK_V1: [],
    }
    candidates = union_candidates(hits)
    by_id = {c.chunk_id: c for c in candidates}
    assert set(by_id) == {"c1", "c2"}
    assert len(by_id["c1"].retrieval_hits) == 2
    retrievers = {h.retriever for h in by_id["c1"].retrieval_hits}
    assert retrievers == {RETRIEVER_LEXICAL_PLAIN_V1, RETRIEVER_DENSE_PLAIN_V1}


def test_ordering_min_rank_then_arm_count_then_chunk_id() -> None:
    a = PoolCandidate(
        chunk_id="z_chunk",
        retrieval_hits=[_hit("a", "z_chunk", 2, 99.0)],
    )
    b = PoolCandidate(
        chunk_id="m_chunk",
        retrieval_hits=[
            _hit("a", "m_chunk", 2, 0.1),
            _hit("b", "m_chunk", 5, 0.1),
        ],
    )
    c = PoolCandidate(
        chunk_id="a_chunk",
        retrieval_hits=[_hit("a", "a_chunk", 1, 0.01)],
    )
    ordered = order_pool_candidates([a, b, c])
    assert [x.chunk_id for x in ordered] == ["a_chunk", "m_chunk", "z_chunk"]


def test_ordering_independent_of_input_order() -> None:
    candidates = [
        PoolCandidate(chunk_id="b", retrieval_hits=[_hit("r", "b", 1)]),
        PoolCandidate(chunk_id="a", retrieval_hits=[_hit("r", "a", 1)]),
    ]
    assert [c.chunk_id for c in order_pool_candidates(candidates)] == ["a", "b"]
    assert [c.chunk_id for c in order_pool_candidates(list(reversed(candidates)))] == [
        "a",
        "b",
    ]


def test_depth_contribution_boundaries() -> None:
    lex = [_hit(RETRIEVER_LEXICAL_PLAIN_V1, f"L{i}", i) for i in range(1, 52)]
    lex50 = lex[:50]
    rerank = [_hit(RETRIEVER_HYBRID_RERANK_V1, f"R{i}", i) for i in range(1, 22)]
    rerank20 = rerank[:20]
    hits = {
        RETRIEVER_LEXICAL_PLAIN_V1: lex50,
        RETRIEVER_DENSE_PLAIN_V1: [],
        RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1: [],
        RETRIEVER_DENSE_ARM_H_V1: [],
        RETRIEVER_HYBRID_RRF_V1: [],
        RETRIEVER_HYBRID_RERANK_V1: rerank20,
    }
    pool = union_candidates(hits)
    ids = {c.chunk_id for c in pool}
    assert "L50" in ids
    assert "L51" not in ids
    assert "R20" in ids
    assert "R21" not in ids


def test_six_arms_execute_and_experimental_unpromoted(tmp_path: Path) -> None:
    settings = AppSettings()
    assert settings.dense.query_text.strategy == "raw"
    assert settings.dense.query_text.contract_version == "raw-query-v1"
    assert settings.indexing.searchable_units.strategy == "all_children"
    run_path = tmp_path / "run.json"
    chunks = [_chunk("c1", text=BODY_MARKER), _chunk("c2", text="other")]
    write_authoring_run(run_path, _run([_case("d1", "what is ndm?")]))
    executor = RecordingExecutor()
    arts = _artifacts()
    snap = _snapshot(chunks)
    p1, p2 = _patch_preflight_ok(arts, snap)
    with p1, p2:
        result = run_gold_pool(settings, run_path=run_path, executor=executor)
    assert result.exit_code == 0
    assert len(executor.calls) == 1
    enriched = load_authoring_run(run_path)
    assert enriched.pooling is not None
    assert enriched.pooling.retrievers == list(POOLING_RETRIEVER_IDS)
    # Experimental contracts remain candidate-only; production defaults unchanged.
    settings2 = AppSettings()
    assert settings2.dense.query_text.strategy == "raw"
    assert settings2.dense.query_text.contract_version == "raw-query-v1"
    assert settings2.indexing.searchable_units.strategy == "all_children"
    assert settings2.indexing.searchable_units.contract_version == "all-children-v1"
    assert MODEL_QUERY_PROMPT_V1 == "model-query-prompt-v1"
    assert EXCLUDE_HEADING_ONLY_V1 == "exclude-heading-only-v1"

def test_privacy_no_body_text_and_no_relevance(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, _run([_case("d1", "query one")]))
    executor = RecordingExecutor(default_chunks=["c1"])
    p1, p2 = _patch_preflight_ok(
        _artifacts(),
        _snapshot([_chunk("c1", text=BODY_MARKER)]),
    )
    with p1, p2:
        result = run_gold_pool(settings, run_path=run_path, executor=executor)
    assert result.exit_code == 0
    raw = run_path.read_text(encoding="utf-8")
    assert BODY_MARKER not in raw
    data = json.loads(raw)
    cand = data["cases"][0]["candidates"][0]
    assert cand["chunk_id"] == "c1"
    assert cand["document_title"] == "Guide"
    assert "retrieval_hits" in cand
    assert "relevance" not in cand
    assert "grade" not in cand
    assert "is_relevant" not in cand
    assert "confidence" not in cand
    assert data["cases"][0]["model_judgments"] == []
    assert "relevance_order" not in cand
    assert "judging_order" not in cand


def test_invalid_candidate_identity_fails_case(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, _run([_case("d1", "q")]))
    executor = RecordingExecutor(default_chunks=["missing_chunk"])
    p1, p2 = _patch_preflight_ok(_artifacts(), _snapshot([_chunk("c1")]))
    with p1, p2:
        result = run_gold_pool(settings, run_path=run_path, executor=executor)
    assert result.exit_code == 1
    enriched = load_authoring_run(run_path)
    assert enriched.cases[0].candidates == []
    assert enriched.pool_outcomes[0].failure_reason == (
        PoolFailureReason.CANDIDATE_IDENTITY_INVALID
    )


def test_case_failure_continues_and_exit_0_partial(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    write_authoring_run(
        run_path,
        _run(
            [
                _case("ok", "good query"),
                _case("bad", "fail query"),
                _case("ok2", "another good"),
            ]
        ),
    )

    class Selective(RecordingExecutor):
        def execute_all(self, *, query: str, artifacts: ResolvedPoolingArtifacts):
            if query == "fail query":
                self.calls.append(query)
                self.queries.append(query)
                raise ArmExecutionError(
                    "hybrid-rerank boom",
                    reason=PoolFailureReason.HYBRID_RERANK_FAILED,
                    retriever=RETRIEVER_HYBRID_RERANK_V1,
                )
            return super().execute_all(query=query, artifacts=artifacts)

    executor = Selective(default_chunks=["c1"])
    p1, p2 = _patch_preflight_ok(_artifacts(), _snapshot([_chunk("c1")]))
    with p1, p2:
        result = run_gold_pool(settings, run_path=run_path, executor=executor)
    assert result.exit_code == 0
    assert len(executor.calls) == 3
    enriched = load_authoring_run(run_path)
    assert enriched.pool_successful_case_count == 2
    assert enriched.pool_failed_case_count == 1
    by_id = {c.draft_case_id: c for c in enriched.cases}
    assert by_id["ok"].candidates
    assert by_id["ok2"].candidates
    assert by_id["bad"].candidates == []


def test_all_runtime_failures_exit_1(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, _run([_case("d1", "q1"), _case("d2", "q2")]))
    executor = RecordingExecutor(fail_arm=RETRIEVER_LEXICAL_PLAIN_V1)
    p1, p2 = _patch_preflight_ok(_artifacts(), _snapshot([_chunk("c1")]))
    with p1, p2:
        result = run_gold_pool(settings, run_path=run_path, executor=executor)
    assert result.exit_code == 1
    enriched = load_authoring_run(run_path)
    assert enriched.pool_successful_case_count == 0
    assert len(enriched.pool_outcomes) == 2


def test_force_replace_and_preserve_on_failure(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    old = [
        PoolCandidate(
            chunk_id="c_old",
            document_id="doc_a",
            document_title="Guide",
            section_path=["S"],
            retrieval_hits=[_hit(RETRIEVER_LEXICAL_PLAIN_V1, "c_old", 1)],
        )
    ]
    write_authoring_run(run_path, _run([_case("d1", "q", candidates=old)]))

    executor = RecordingExecutor(default_chunks=["c1"])
    p1, p2 = _patch_preflight_ok(
        _artifacts(),
        _snapshot([_chunk("c1"), _chunk("c_old")]),
    )
    with p1, p2:
        with pytest.raises(PoolPreRunError, match="--force"):
            run_gold_pool(settings, run_path=run_path, executor=executor)
    assert executor.calls == []
    assert load_authoring_run(run_path).cases[0].candidates[0].chunk_id == "c_old"

    with p1, p2:
        result = run_gold_pool(
            settings, run_path=run_path, executor=executor, force=True
        )
    assert result.exit_code == 0
    assert load_authoring_run(run_path).cases[0].candidates[0].chunk_id == "c1"

    fail_exec = RecordingExecutor(fail_arm=RETRIEVER_HYBRID_RRF_V1)
    with p1, p2:
        result = run_gold_pool(
            settings, run_path=run_path, executor=fail_exec, force=True
        )
    assert result.exit_code == 1
    preserved = load_authoring_run(run_path).cases[0].candidates
    assert preserved[0].chunk_id == "c1"
    assert load_authoring_run(run_path).pool_outcomes[0].status == PoolCaseStatus.FAILED


def test_output_copy_leaves_input_unchanged(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    out_path = tmp_path / "pooled.json"
    write_authoring_run(run_path, _run([_case("d1", "q")]))
    before = run_path.read_text(encoding="utf-8")
    executor = RecordingExecutor(default_chunks=["c1"])
    p1, p2 = _patch_preflight_ok(_artifacts(), _snapshot([_chunk("c1")]))
    with p1, p2:
        result = run_gold_pool(
            settings, run_path=run_path, output=out_path, executor=executor
        )
    assert result.exit_code == 0
    assert run_path.read_text(encoding="utf-8") == before
    pooled = load_authoring_run(out_path)
    assert pooled.authoring_run_id == "authorrun_test"
    assert pooled.cases[0].candidates


def test_existing_output_requires_force(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    out_path = tmp_path / "pooled.json"
    write_authoring_run(run_path, _run([_case("d1", "q")]))
    out_path.write_text("{}", encoding="utf-8")
    executor = RecordingExecutor()
    with pytest.raises(PoolPreRunError, match="output already exists"):
        run_gold_pool(
            settings, run_path=run_path, output=out_path, executor=executor
        )
    assert executor.calls == []


def test_preflight_failure_zero_retrieval(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, _run([_case("d1", "q")]))
    executor = RecordingExecutor()
    with patch(
        "offline_rag.gold_authoring.pool.preflight_pooling_artifacts",
        side_effect=PoolPreflightError("lexical artifact missing/mismatched"),
    ):
        with pytest.raises(PoolPreRunError, match="lexical"):
            run_gold_pool(settings, run_path=run_path, executor=executor)
    assert executor.calls == []
    assert json.loads(run_path.read_text())["cases"][0]["candidates"] == []


def test_zero_targeted_exit_2(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    case = _case("d1", "q")
    case.human_status = HumanReviewStatus.ACCEPTED
    write_authoring_run(run_path, _run([case]))
    executor = RecordingExecutor()
    with pytest.raises(PoolPreRunError, match="no poolable"):
        run_gold_pool(settings, run_path=run_path, executor=executor)
    assert executor.calls == []


def test_empty_union_is_case_failure(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, _run([_case("d1", "q")]))

    class EmptyArms(RecordingExecutor):
        def execute_all(self, *, query: str, artifacts: ResolvedPoolingArtifacts):
            self.calls.append(query)
            return {arm: [] for arm in POOLING_RETRIEVER_IDS}

    executor = EmptyArms()
    p1, p2 = _patch_preflight_ok(_artifacts(), _snapshot([_chunk("c1")]))
    with p1, p2:
        result = run_gold_pool(settings, run_path=run_path, executor=executor)
    assert result.exit_code == 1
    assert (
        load_authoring_run(run_path).pool_outcomes[0].failure_reason
        == PoolFailureReason.EMPTY_CANDIDATE_POOL
    )


def test_no_retry_on_arm_failure(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, _run([_case("d1", "q")]))
    executor = RecordingExecutor(fail_arm=RETRIEVER_DENSE_ARM_H_V1)
    p1, p2 = _patch_preflight_ok(_artifacts(), _snapshot([_chunk("c1")]))
    with p1, p2:
        run_gold_pool(settings, run_path=run_path, executor=executor)
    assert executor.calls == ["q"]


def test_preflight_rejects_missing_lexical(tmp_path: Path) -> None:
    settings = AppSettings(
        paths=AppSettings().paths.model_copy(
            update={
                "chunk_manifests": tmp_path / "cm",
                "lexical_index_manifests": tmp_path / "lim",
                "index_manifests": tmp_path / "im",
                "corpora": tmp_path / "corpora",
                "manifests": tmp_path / "manifests",
                "chunks": tmp_path / "chunks",
            }
        )
    )
    (tmp_path / "cm").mkdir()
    run = _run([_case("d1", "q")], chunk_set_id="chunkset_A")
    with patch(
        "offline_rag.gold_authoring.pool_preflight.load_chunk_set_snapshot",
        return_value=_snapshot([_chunk("c1")]),
    ):
        with pytest.raises(PoolPreflightError, match="lexical"):
            preflight_pooling_artifacts(settings, run)


def test_preflight_rejects_mismatched_dense_chunk_set(tmp_path: Path) -> None:
    settings = AppSettings(
        paths=AppSettings().paths.model_copy(
            update={
                "chunk_manifests": tmp_path / "cm",
                "lexical_index_manifests": tmp_path / "lim",
                "index_manifests": tmp_path / "im",
                "corpora": tmp_path / "corpora",
                "manifests": tmp_path / "manifests",
                "chunks": tmp_path / "chunks",
            }
        )
    )
    run = _run([_case("d1", "q")], chunk_set_id="chunkset_A")

    lex_manifest = MagicMock()
    lex_manifest.chunk_set_id = "chunkset_A"
    dense_manifest = MagicMock()
    dense_manifest.chunk_set_id = "chunkset_B"

    with (
        patch(
            "offline_rag.gold_authoring.pool_preflight.load_chunk_set_snapshot",
            return_value=_snapshot([_chunk("c1")]),
        ),
        patch(
            "offline_rag.gold_authoring.pool_preflight.try_load_lexical_index_manifest",
            return_value=lex_manifest,
        ),
        patch(
            "offline_rag.gold_authoring.pool_preflight.try_load_index_manifest",
            return_value=dense_manifest,
        ),
    ):
        with pytest.raises(PoolPreflightError, match="dense baseline"):
            preflight_pooling_artifacts(settings, run)


def test_preflight_rejects_missing_arm_h(tmp_path: Path) -> None:
    settings = AppSettings(
        paths=AppSettings().paths.model_copy(
            update={
                "chunk_manifests": tmp_path / "cm",
                "lexical_index_manifests": tmp_path / "lim",
                "index_manifests": tmp_path / "im",
                "corpora": tmp_path / "corpora",
                "manifests": tmp_path / "manifests",
                "chunks": tmp_path / "chunks",
            }
        )
    )
    run = _run([_case("d1", "q")], chunk_set_id="chunkset_A")
    lex_manifest = MagicMock()
    lex_manifest.chunk_set_id = "chunkset_A"
    baseline = MagicMock()
    baseline.chunk_set_id = "chunkset_A"
    calls = {"n": 0}

    def load_dense(_root: Any, index_id: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return baseline
        return None

    with (
        patch(
            "offline_rag.gold_authoring.pool_preflight.load_chunk_set_snapshot",
            return_value=_snapshot([_chunk("c1")]),
        ),
        patch(
            "offline_rag.gold_authoring.pool_preflight.try_load_lexical_index_manifest",
            return_value=lex_manifest,
        ),
        patch(
            "offline_rag.gold_authoring.pool_preflight.try_load_index_manifest",
            side_effect=load_dense,
        ),
    ):
        with pytest.raises(PoolPreflightError, match="Arm H"):
            preflight_pooling_artifacts(settings, run)


def test_force_does_not_bypass_historical_compatibility(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    old = [
        PoolCandidate(
            chunk_id="c_old",
            document_id="doc_a",
            document_title="Guide",
            retrieval_hits=[_hit(RETRIEVER_LEXICAL_PLAIN_V1, "c_old", 1)],
        )
    ]
    write_authoring_run(run_path, _run([_case("d1", "q", candidates=old)]))
    executor = RecordingExecutor()
    with patch(
        "offline_rag.gold_authoring.pool.preflight_pooling_artifacts",
        side_effect=PoolPreflightError("Arm H dense artifact missing/mismatched"),
    ):
        with pytest.raises(PoolPreRunError, match="Arm H"):
            run_gold_pool(settings, run_path=run_path, executor=executor, force=True)
    assert executor.calls == []


def test_cli_help_and_prohibited_knobs() -> None:
    parser = build_parser()
    gold = None
    for action in parser._subparsers._group_actions:  # noqa: SLF001
        if action.dest == "command":
            gold = action.choices["gold"]
    assert gold is not None
    pool = gold._subparsers._group_actions[0].choices["pool"]  # noqa: SLF001
    text = pool.format_help()
    assert "--run" in text
    assert "--output" in text
    assert "--force" in text
    for banned in (
        "--top-k",
        "--dense-top-k",
        "--rerank-top-k",
        "--corpus",
        "--chunk-set",
        "--retrievers",
        "--skip-arm",
        "--embedding-model",
        "--reranker-model",
    ):
        assert banned not in text


def test_cli_run_required() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["gold", "pool"])
    assert exc.value.code == 2


def test_cli_preflight_exit_2(tmp_path: Path) -> None:
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, _run([_case("d1", "q")]))
    with patch(
        "offline_rag.gold_authoring.pool.run_gold_pool",
        side_effect=PoolPreRunError("mismatch"),
    ):
        code = main(["gold", "pool", "--run", str(run_path)])
    assert code == 2


def test_no_index_build_on_missing_artifacts(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, _run([_case("d1", "q")]))
    with patch(
        "offline_rag.gold_authoring.pool.preflight_pooling_artifacts",
        side_effect=PoolPreflightError("missing historical artifacts"),
    ):
        with pytest.raises(PoolPreRunError):
            run_gold_pool(settings, run_path=run_path, executor=RecordingExecutor())


def test_query_is_proposed_query_only(tmp_path: Path) -> None:
    settings = AppSettings()
    run_path = tmp_path / "run.json"
    case = _case("d1", "exact proposed query")
    case.proposal_rationale = "do not inject"
    case.proposed_category = "factoid"
    case.source_seed = SourceSeed(
        chunk_id="seed_secret",
        document_id="doc_a",
        document_title="Guide",
        section_path=["Intro"],
    )
    write_authoring_run(run_path, _run([case]))
    executor = RecordingExecutor(default_chunks=["c1"])
    p1, p2 = _patch_preflight_ok(_artifacts(), _snapshot([_chunk("c1")]))
    with p1, p2:
        run_gold_pool(settings, run_path=run_path, executor=executor)
    assert executor.queries == ["exact proposed query"]


def test_historical_executor_uses_locked_depths() -> None:
    settings = AppSettings()
    executor = HistoricalPoolArmExecutor(settings, reranker=FakeReranker())
    arts = _artifacts()

    with (
        patch.object(executor, "_lexical_hits") as lex,
        patch.object(executor, "_dense_hits") as dense,
        patch(
            "offline_rag.gold_authoring.pool_arms.resolve_seed_text_from_chunk_set",
            return_value="passage",
        ),
    ):
        lex.return_value = [
            ArmHit(chunk_id=f"L{i}", rank=i, score=1.0) for i in range(1, 51)
        ]
        dense.return_value = [
            ArmHit(chunk_id=f"D{i}", rank=i, score=0.5) for i in range(1, 51)
        ]
        results = executor.execute_all(query="q", artifacts=arts)

    assert lex.call_args.kwargs["top_k"] == 50
    dense_ks = [c.kwargs["top_k"] for c in dense.call_args_list]
    assert dense_ks == [50, 50, 50]
    assert len(results[RETRIEVER_HYBRID_RRF_V1]) <= 50
    assert len(results[RETRIEVER_HYBRID_RERANK_V1]) <= 20
    assert set(results) == set(POOLING_RETRIEVER_IDS)