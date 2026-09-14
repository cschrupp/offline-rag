"""Slice 9D: blind double-pass relevance prelabeling."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from offline_rag.cli import build_parser, main
from offline_rag.config.models import AppSettings, AuthoringSettings
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.gold_authoring.agreement import derive_prelabel_summary
from offline_rag.gold_authoring.blind_order import derive_blind_orders
from offline_rag.gold_authoring.chunk_access import CorpusChunkSnapshot
from offline_rag.gold_authoring.contracts import (
    BLIND_ORDER_CONTRACT,
    JUDGE_CONTEXT_CONTRACT,
    PRELABEL_AGREEMENT_CONTRACT,
    RATIONALE_MAX_CHARS,
    RELEVANCE_PRELABEL_CONTRACT,
)
from offline_rag.gold_authoring.judge_context import build_relevance_judge_context
from offline_rag.gold_authoring.models import (
    GoldAuthoringRun,
    HumanReviewStatus,
    SilverCase,
    SourceSeed,
)
from offline_rag.gold_authoring.persist import load_authoring_run, write_authoring_run
from offline_rag.gold_authoring.pooling_models import PoolCandidate, RetrievalHit
from offline_rag.gold_authoring.prelabel import PrelabelPreRunError, run_gold_prelabel
from offline_rag.gold_authoring.prelabel_models import (
    AgreementLabel,
    DisagreementSeverity,
    ModelJudgment,
    ReviewPriority,
)
from offline_rag.gold_authoring.prelabel_schema import (
    RelevancePrelabelParseError,
    parse_relevance_prelabel_v1,
)
from offline_rag.gold_authoring.prompt import relevance_prelabel_system_prompt

BODY_A = "UNIQUE_PRIVATE_BODY_A_9D_QWERTY"
BODY_B = "UNIQUE_PRIVATE_BODY_B_9D_ASDFGH"


def _ready_settings(**overrides) -> AppSettings:
    auth = {
        "enabled": True,
        "model": "test-model",
        "approved_models": ["test-model"],
        "approved_endpoints": ["http://127.0.0.1:11434/v1"],
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "author-secret",
        "network_policy": "localhost_only",
    }
    auth.update(overrides)
    return AppSettings(authoring=AuthoringSettings(**auth))


def _chunk(chunk_id: str, *, text: str, document_id: str = "doc_a") -> Chunk:
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
        section_path=["SECTION"],
    )


def _candidate(chunk_id: str, *, rank: int = 1) -> PoolCandidate:
    return PoolCandidate(
        chunk_id=chunk_id,
        document_id="doc_a",
        document_title="Guide",
        section_path=["SECTION"],
        retrieval_hits=[
            RetrievalHit(
                retriever="lexical-plain-v1",
                chunk_id=chunk_id,
                rank=rank,
                score=1.0,
            )
        ],
    )


def _case(
    draft_id: str,
    query: str,
    candidates: list[PoolCandidate],
    *,
    seed_id: str = "seed_1",
) -> SilverCase:
    return SilverCase(
        draft_case_id=draft_id,
        human_status=HumanReviewStatus.PENDING,
        proposed_query=query,
        source_seed=SourceSeed(chunk_id=seed_id, document_id="doc_a"),
        candidates=candidates,
    )


def _run(cases: list[SilverCase]) -> GoldAuthoringRun:
    return GoldAuthoringRun(
        authoring_run_id="authorrun_test",
        authorcfg_id="authorcfg_testhash",
        network_policy="localhost_only",
        corpus_id="corpus_A",
        corpus_name="default",
        chunk_set_id="chunkset_A",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        cases=cases,
    )


def _snapshot(chunks: list[Chunk]) -> CorpusChunkSnapshot:
    return CorpusChunkSnapshot(
        corpus_name="default",
        corpus_id="corpus_A",
        chunk_set_id="chunkset_A",
        chunks=chunks,
        source_name_by_document_id={"doc_a": "Guide.pdf"},
    )


class ScriptedClient:
    def __init__(
        self,
        *,
        fail_on_call: int | None = None,
        grade_by_body: dict[str, int] | None = None,
        always_invalid: bool = False,
    ) -> None:
        self.fail_on_call = fail_on_call
        self.grade_by_body = grade_by_body or {}
        self.always_invalid = always_invalid
        self.calls: list[str] = []
        self.user_messages: list[str] = []

    def prelabel(self, *, system_prompt: str, user_content: str) -> str:
        _ = system_prompt
        self.user_messages.append(user_content)
        n = len(self.calls) + 1
        self.calls.append(user_content)
        if self.always_invalid or (
            self.fail_on_call is not None and n == self.fail_on_call
        ):
            return "not-json"
        body = user_content.split("CANDIDATE:\n", 1)[-1]
        grade = 0
        for marker, g in self.grade_by_body.items():
            if marker in body:
                grade = g
                break
        return json.dumps(
            {"grade": grade, "rationale": f"Grade {grade} for candidate."}
        )

    def close(self) -> None:
        return None


def _patch_ready(snapshot: CorpusChunkSnapshot):
    return patch(
        "offline_rag.gold_authoring.prelabel._load_historical_snapshot",
        return_value=snapshot,
    )


def test_prelabel_schema_valid_and_rejects() -> None:
    assert (
        parse_relevance_prelabel_v1(
            '{"grade":2,"rationale":"Directly answers."}'
        ).grade
        == 2
    )
    with pytest.raises(RelevancePrelabelParseError):
        parse_relevance_prelabel_v1('{"grade":"2","rationale":"x"}')
    with pytest.raises(RelevancePrelabelParseError):
        parse_relevance_prelabel_v1('{"grade":2.0,"rationale":"x"}')
    with pytest.raises(RelevancePrelabelParseError):
        parse_relevance_prelabel_v1('{"grade":true,"rationale":"x"}')
    with pytest.raises(RelevancePrelabelParseError):
        parse_relevance_prelabel_v1(
            '{"grade":2,"rationale":"x","confidence":0.9}'
        )
    with pytest.raises(RelevancePrelabelParseError):
        parse_relevance_prelabel_v1('{"grade":2,"rationale":"   "}')
    ok = "a" * RATIONALE_MAX_CHARS
    assert (
        len(
            parse_relevance_prelabel_v1(
                json.dumps({"grade": 1, "rationale": ok})
            ).rationale
        )
        == RATIONALE_MAX_CHARS
    )
    with pytest.raises(RelevancePrelabelParseError):
        parse_relevance_prelabel_v1(
            json.dumps({"grade": 1, "rationale": "a" * (RATIONALE_MAX_CHARS + 1)})
        )


def test_agreement_and_priority() -> None:
    def j(pass_id: str, chunk: str, grade: int) -> ModelJudgment:
        return ModelJudgment(
            pass_id=pass_id,  # type: ignore[arg-type]
            chunk_id=chunk,
            blind_position=1,
            grade=grade,  # type: ignore[arg-type]
            rationale="ok",
        )

    s = derive_prelabel_summary(
        [j("pass_1", "a", 2), j("pass_2", "a", 2)],
        candidate_ids=["a"],
        source_seed_chunk_id=None,
    )
    assert s.candidate_summaries[0].agreement == AgreementLabel.AGREE
    assert s.review_priority == ReviewPriority.LOW

    s = derive_prelabel_summary(
        [j("pass_1", "a", 2), j("pass_2", "a", 1)],
        candidate_ids=["a"],
        source_seed_chunk_id=None,
    )
    assert s.candidate_summaries[0].disagreement_severity == (
        DisagreementSeverity.ADJACENT
    )
    assert s.review_priority == ReviewPriority.MEDIUM

    s = derive_prelabel_summary(
        [j("pass_1", "a", 2), j("pass_2", "a", 0)],
        candidate_ids=["a"],
        source_seed_chunk_id=None,
    )
    assert s.case_has_polar_disagreement
    assert s.review_priority == ReviewPriority.HIGH

    s = derive_prelabel_summary(
        [
            j("pass_1", "a", 0),
            j("pass_2", "a", 0),
            j("pass_1", "b", 0),
            j("pass_2", "b", 0),
        ],
        candidate_ids=["a", "b"],
        source_seed_chunk_id=None,
    )
    assert s.case_has_no_positive_prelabel
    assert s.review_priority == ReviewPriority.MEDIUM


def test_blind_orders_independent_of_input_order() -> None:
    o1a, o2a = derive_blind_orders(
        authoring_run_id="run",
        draft_case_id="d1",
        candidate_ids=["c2", "c1", "c3"],
    )
    o1b, o2b = derive_blind_orders(
        authoring_run_id="run",
        draft_case_id="d1",
        candidate_ids=["c3", "c1", "c2"],
    )
    assert o1a == o1b
    assert o2a == o2b
    assert set(o1a) == {"c1", "c2", "c3"}
    assert o1a != o2a


def test_blind_order_singleton() -> None:
    o1, o2 = derive_blind_orders(
        authoring_run_id="run",
        draft_case_id="d1",
        candidate_ids=["only"],
    )
    assert o1 == o2 == ["only"]


def test_judge_context_envelope() -> None:
    ctx = build_relevance_judge_context(
        query="What is Module 1?",
        chunk=_chunk("c1", text=BODY_A),
        source_name="Guide.pdf",
    )
    msg = ctx.render_user_message()
    assert "QUERY:\nWhat is Module 1?" in msg
    assert "DOCUMENT:\nGuide" in msg
    assert "SECTION:\nSECTION" in msg
    assert f"CANDIDATE:\n{BODY_A}" in msg
    assert "chunk_id" not in msg
    assert "pass_" not in msg
    assert "rank" not in msg


def test_successful_prelabel_2n_and_privacy(tmp_path: Path) -> None:
    settings = _ready_settings()
    run_path = tmp_path / "run.json"
    case = _case(
        "d1",
        "What is NDM?",
        [_candidate("c_a", rank=1), _candidate("c_b", rank=2)],
        seed_id="c_a",
    )
    write_authoring_run(run_path, _run([case]))
    client = ScriptedClient(grade_by_body={BODY_A: 2, BODY_B: 0})
    snap = _snapshot([_chunk("c_a", text=BODY_A), _chunk("c_b", text=BODY_B)])
    with _patch_ready(snap):
        result = run_gold_prelabel(
            settings, run_path=run_path, adapter=client  # type: ignore[arg-type]
        )
    assert result.exit_code == 0
    assert result.model_request_count == 4
    assert len(client.calls) == 4
    for msg in client.user_messages:
        assert (BODY_A in msg) + (BODY_B in msg) == 1
        assert "lexical-plain-v1" not in msg
        assert "pass_1" not in msg
        assert "SOURCE SEED" not in msg
    enriched = load_authoring_run(run_path)
    raw = run_path.read_text(encoding="utf-8")
    assert BODY_A not in raw
    assert BODY_B not in raw
    sc = enriched.cases[0]
    assert len(sc.model_judgments) == 4
    assert sc.prelabel_summary is not None
    assert sc.prelabel_provenance is not None
    assert sc.prelabel_provenance.relevance_contract == RELEVANCE_PRELABEL_CONTRACT
    assert sc.prelabel_provenance.judge_context_contract == JUDGE_CONTEXT_CONTRACT
    assert sc.prelabel_provenance.blind_order_contract == BLIND_ORDER_CONTRACT
    assert sc.prelabel_provenance.agreement_contract == PRELABEL_AGREEMENT_CONTRACT
    assert sc.human_status == HumanReviewStatus.PENDING
    assert [c.chunk_id for c in sc.candidates] == ["c_a", "c_b"]
    assert sc.candidates[0].retrieval_hits[0].rank == 1


def test_fail_fast_and_continue(tmp_path: Path) -> None:
    settings = _ready_settings()
    run_path = tmp_path / "run.json"
    cases = [
        _case("ok1", "q1", [_candidate("c_a")]),
        _case("bad", "q2", [_candidate("c_a"), _candidate("c_b")]),
        _case("ok2", "q3", [_candidate("c_a")]),
    ]
    write_authoring_run(run_path, _run(cases))
    client = ScriptedClient(
        fail_on_call=3, grade_by_body={BODY_A: 1, BODY_B: 0}
    )
    snap = _snapshot([_chunk("c_a", text=BODY_A), _chunk("c_b", text=BODY_B)])
    with _patch_ready(snap):
        result = run_gold_prelabel(
            settings, run_path=run_path, adapter=client  # type: ignore[arg-type]
        )
    assert result.exit_code == 0
    enriched = load_authoring_run(run_path)
    by_id = {c.draft_case_id: c for c in enriched.cases}
    assert by_id["ok1"].has_complete_durable_prelabel()
    assert by_id["ok2"].has_complete_durable_prelabel()
    assert by_id["bad"].model_judgments == []
    assert by_id["bad"].prelabel_summary is None
    assert len(client.calls) < 8
    assert enriched.prelabeling is not None
    assert enriched.prelabeling.successful_case_count == 2
    assert enriched.prelabeling.failed_case_count == 1


def test_force_preserve_and_replace(tmp_path: Path) -> None:
    settings = _ready_settings()
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, _run([_case("d1", "q", [_candidate("c_a")])]))
    client = ScriptedClient(grade_by_body={BODY_A: 2})
    snap = _snapshot([_chunk("c_a", text=BODY_A)])
    with _patch_ready(snap):
        assert (
            run_gold_prelabel(
                settings, run_path=run_path, adapter=client  # type: ignore[arg-type]
            ).exit_code
            == 0
        )
    first = load_authoring_run(run_path)
    old_cfg = first.cases[0].prelabel_provenance.authorcfg_id  # type: ignore[union-attr]
    assert first.cases[0].model_judgments[0].grade == 2

    with _patch_ready(snap):
        with pytest.raises(PrelabelPreRunError, match="--force"):
            run_gold_prelabel(
                settings, run_path=run_path, adapter=client  # type: ignore[arg-type]
            )

    fail_client = ScriptedClient(fail_on_call=1, grade_by_body={BODY_A: 0})
    with _patch_ready(snap):
        result = run_gold_prelabel(
            settings,
            run_path=run_path,
            adapter=fail_client,  # type: ignore[arg-type]
            force=True,
        )
    assert result.exit_code == 1
    preserved = load_authoring_run(run_path)
    assert preserved.cases[0].model_judgments[0].grade == 2
    assert preserved.cases[0].prelabel_provenance.authorcfg_id == old_cfg  # type: ignore[union-attr]
    assert preserved.prelabeling is not None
    assert preserved.prelabeling.outcomes[0].status.value == "failed"

    repl = ScriptedClient(grade_by_body={BODY_A: 1})
    with _patch_ready(snap):
        result = run_gold_prelabel(
            settings,
            run_path=run_path,
            adapter=repl,  # type: ignore[arg-type]
            force=True,
        )
    assert result.exit_code == 0
    replaced = load_authoring_run(run_path)
    grades = {j.grade for j in replaced.cases[0].model_judgments}
    assert grades == {1}


def test_output_copy_leaves_input(tmp_path: Path) -> None:
    settings = _ready_settings()
    run_path = tmp_path / "run.json"
    out_path = tmp_path / "out.json"
    write_authoring_run(run_path, _run([_case("d1", "q", [_candidate("c_a")])]))
    before = run_path.read_text(encoding="utf-8")
    client = ScriptedClient(grade_by_body={BODY_A: 2})
    snap = _snapshot([_chunk("c_a", text=BODY_A)])
    with _patch_ready(snap):
        result = run_gold_prelabel(
            settings,
            run_path=run_path,
            output=out_path,
            adapter=client,  # type: ignore[arg-type]
        )
    assert result.exit_code == 0
    assert run_path.read_text(encoding="utf-8") == before
    assert load_authoring_run(out_path).cases[0].has_complete_durable_prelabel()


def test_all_runtime_failures_exit_1(tmp_path: Path) -> None:
    settings = _ready_settings()
    run_path = tmp_path / "run.json"
    write_authoring_run(
        run_path,
        _run(
            [
                _case("d1", "q1", [_candidate("c_a")]),
                _case("d2", "q2", [_candidate("c_a")]),
            ]
        ),
    )
    with _patch_ready(_snapshot([_chunk("c_a", text=BODY_A)])):
        result = run_gold_prelabel(
            settings,
            run_path=run_path,
            adapter=ScriptedClient(always_invalid=True),  # type: ignore[arg-type]
        )
    assert result.exit_code == 1


def test_cli_help_and_prohibited_knobs() -> None:
    parser = build_parser()
    gold = None
    for action in parser._subparsers._group_actions:  # noqa: SLF001
        if action.dest == "command":
            gold = action.choices["gold"]
    assert gold is not None
    prelabel = gold._subparsers._group_actions[0].choices["prelabel"]  # noqa: SLF001
    text = prelabel.format_help()
    assert "--run" in text
    assert "--force" in text
    for banned in (
        "--seed",
        "--top-k",
        "--max-candidates",
        "--model",
        "--temperature",
        "--pass",
        "--corpus",
        "--chunk-set",
        "--skip-case",
    ):
        assert banned not in text


def test_cli_run_required() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["gold", "prelabel"])
    assert exc.value.code == 2


def test_prompt_mentions_contracts() -> None:
    prompt = relevance_prelabel_system_prompt()
    assert "relevance-prelabel-v1" in prompt
    assert "0" in prompt and "2" in prompt


def test_zero_eligible_exit_2(tmp_path: Path) -> None:
    settings = _ready_settings()
    run_path = tmp_path / "run.json"
    case = _case("d1", "q", [])
    write_authoring_run(run_path, _run([case]))
    with pytest.raises(PrelabelPreRunError, match="no eligible"):
        run_gold_prelabel(
            settings,
            run_path=run_path,
            adapter=ScriptedClient(),  # type: ignore[arg-type]
        )
