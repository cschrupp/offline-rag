"""Slice 9E: human review domain, finalize, loopback server."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from http.client import HTTPConnection
from pathlib import Path

import pytest

from offline_rag.cli import build_parser, main
from offline_rag.config.models import AppSettings
from offline_rag.evaluation.gold import ChunkJudgment, load_gold_dataset
from offline_rag.gold_authoring.finalize import FinalizePreRunError, run_gold_finalize
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase, SourceSeed
from offline_rag.gold_authoring.persist import (
    default_authoring_gold_dir,
    load_authoring_run,
    write_authoring_run,
)
from offline_rag.gold_authoring.pooling_models import PoolCandidate, RetrievalHit
from offline_rag.gold_authoring.review_models import HumanReviewStatus, ReviewError
from offline_rag.gold_authoring.review_ops import (
    accept_case,
    approve_edited_case,
    reject_case,
    reopen_case,
    set_human_grade,
    set_reviewed_category,
    set_reviewed_query,
    set_reviewed_tags,
)
from offline_rag.gold_authoring.review_server import (
    create_review_server,
    normalize_review_host,
)
from offline_rag.gold_authoring.review_view import build_case_list_payload


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        paths=AppSettings().paths.model_copy(
            update={
                "corpora": tmp_path / "corpora",
                "chunks": tmp_path / "chunks",
                "chunk_manifests": tmp_path / "chunk-manifests",
            }
        )
    )


def _candidate(chunk_id: str, *, rank: int = 1) -> PoolCandidate:
    return PoolCandidate(
        chunk_id=chunk_id,
        document_id="doc_a",
        document_title="Module 1",
        section_path=["INTRODUCTION"],
        retrieval_hits=[
            RetrievalHit(
                retriever="dense-plain-v1",
                chunk_id=chunk_id,
                rank=rank,
                score=0.9,
            )
        ],
    )


def _case(
    draft_id: str,
    query: str,
    candidates: list[PoolCandidate],
) -> SilverCase:
    return SilverCase(
        draft_case_id=draft_id,
        proposed_query=query,
        proposed_category="ops",
        proposed_tags=["module-1"],
        source_seed=SourceSeed(chunk_id=candidates[0].chunk_id),
        candidates=candidates,
    )


def _run(cases: list[SilverCase], *, corpus_name: str = "default") -> GoldAuthoringRun:
    return GoldAuthoringRun(
        authoring_run_id="authorrun_test",
        authorcfg_id="authorcfg_testhash",
        network_policy="localhost_only",
        corpus_id="corpus_A",
        corpus_name=corpus_name,
        chunk_set_id="chunkset_A",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        cases=cases,
    )


def _grade_all(run: GoldAuthoringRun, draft_id: str, grades: list[int]) -> GoldAuthoringRun:
    case = next(c for c in run.cases if c.draft_case_id == draft_id)
    working = run
    for cand, grade in zip(case.candidates, grades, strict=True):
        working = set_human_grade(
            working,
            draft_case_id=draft_id,
            chunk_id=cand.chunk_id,
            relevance=grade,
        )
    return working


def test_pre9e_absent_human_review_is_pending() -> None:
    case = SilverCase(draft_case_id="d1", proposed_query="What is X?")
    assert case.human_review is None
    assert case.human_status == HumanReviewStatus.PENDING
    assert case.effective_query() == "What is X?"


def test_legacy_pending_human_status_migrates() -> None:
    case = SilverCase.model_validate(
        {"draft_case_id": "d1", "human_status": "pending", "proposed_query": "q"}
    )
    assert case.human_review is None
    assert case.human_status == HumanReviewStatus.PENDING


def test_category_override_tri_state() -> None:
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = _run([case])
    run = set_human_grade(run, draft_case_id="d1", chunk_id="c1", relevance=2)
    run = set_human_grade(run, draft_case_id="d1", chunk_id="c2", relevance=0)
    run = set_reviewed_category(run, draft_case_id="d1", category=None, clear=True)
    case = run.cases[0]
    assert case.effective_category() is None
    assert case.human_review is not None
    assert case.human_review.category_override.is_overridden is True
    assert case.proposal_content_changed() is True


def test_tags_null_vs_empty() -> None:
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = _run([case])
    run = _grade_all(run, "d1", [2, 0])
    run = set_reviewed_tags(run, draft_case_id="d1", tags=[])
    assert run.cases[0].effective_tags() == ()
    assert run.cases[0].human_review is not None
    assert run.cases[0].human_review.tags_override == []
    run = set_reviewed_tags(run, draft_case_id="d1", tags=None, clear_override=True)
    assert run.cases[0].human_review.tags_override is None
    assert run.cases[0].effective_tags() == ("module-1",)


def test_partial_pending_valid_complete_accept() -> None:
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = _run([case])
    run = set_human_grade(run, draft_case_id="d1", chunk_id="c1", relevance=2)
    assert run.cases[0].human_status == HumanReviewStatus.PENDING
    with pytest.raises(ReviewError):
        accept_case(run, draft_case_id="d1")
    run = set_human_grade(run, draft_case_id="d1", chunk_id="c2", relevance=0)
    run = accept_case(run, draft_case_id="d1")
    assert run.cases[0].human_status == HumanReviewStatus.ACCEPTED


def test_all_zero_cannot_accept() -> None:
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = _grade_all(_run([case]), "d1", [0, 0])
    with pytest.raises(ReviewError):
        accept_case(run, draft_case_id="d1")
    run = reject_case(run, draft_case_id="d1")
    assert run.cases[0].human_status == HumanReviewStatus.REJECTED


def test_query_change_clears_grades() -> None:
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = _grade_all(_run([case]), "d1", [2, 0])
    run = accept_case(run, draft_case_id="d1")
    run = set_reviewed_query(
        run, draft_case_id="d1", query="What decision-making approaches exist?"
    )
    case = run.cases[0]
    assert case.human_status == HumanReviewStatus.PENDING
    assert case.human_review is not None
    assert case.human_review.judgments == []
    assert case.human_review.grade_basis_query is None
    # Restoring original query does not resurrect grades.
    run = set_reviewed_query(run, draft_case_id="d1", query="What is X?")
    assert run.cases[0].human_review is not None
    assert run.cases[0].human_review.judgments == []


def test_category_edit_preserves_grades_demotes_accepted() -> None:
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = accept_case(_grade_all(_run([case]), "d1", [2, 0]), draft_case_id="d1")
    run = set_reviewed_category(run, draft_case_id="d1", category="decision")
    case = run.cases[0]
    assert case.human_status == HumanReviewStatus.PENDING
    assert len(case.human_judgment_map()) == 2


def test_edited_requires_metadata_change() -> None:
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = _grade_all(_run([case]), "d1", [2, 0])
    with pytest.raises(ReviewError):
        approve_edited_case(run, draft_case_id="d1")
    run = set_reviewed_tags(run, draft_case_id="d1", tags=["decision-making"])
    run = approve_edited_case(run, draft_case_id="d1")
    assert run.cases[0].human_status == HumanReviewStatus.EDITED


def test_reopen_preserves_grades() -> None:
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = accept_case(_grade_all(_run([case]), "d1", [2, 0]), draft_case_id="d1")
    run = reopen_case(run, draft_case_id="d1")
    assert run.cases[0].human_status == HumanReviewStatus.PENDING
    assert run.cases[0].review_complete()


def test_unknown_candidate_rejected() -> None:
    case = _case("d1", "What is X?", [_candidate("c1")])
    run = _run([case])
    with pytest.raises(ReviewError, match="not in 9C"):
        set_human_grade(run, draft_case_id="d1", chunk_id="missing", relevance=1)


def test_strict_relevance_type() -> None:
    case = _case("d1", "What is X?", [_candidate("c1")])
    run = _run([case])
    with pytest.raises(ReviewError):
        set_human_grade(run, draft_case_id="d1", chunk_id="c1", relevance=True)  # type: ignore[arg-type]
    with pytest.raises(ReviewError):
        set_human_grade(run, draft_case_id="d1", chunk_id="c1", relevance=2.0)  # type: ignore[arg-type]


def test_case_list_preserves_run_order() -> None:
    cases = [
        _case("d", "qd", [_candidate("c1")]),
        _case("b", "qb", [_candidate("c2")]),
        _case("a", "qa", [_candidate("c3")]),
    ]
    payload = build_case_list_payload(_run(cases))
    assert [row["draft_case_id"] for row in payload] == ["d", "b", "a"]
    assert [row["ordinal"] for row in payload] == [1, 2, 3]


def test_normalize_review_host() -> None:
    assert normalize_review_host("localhost") == "127.0.0.1"
    assert normalize_review_host("127.0.0.1") == "127.0.0.1"
    assert normalize_review_host("::1") == "::1"
    with pytest.raises(Exception, match="loopback"):
        normalize_review_host("0.0.0.0")
    with pytest.raises(Exception, match="loopback"):
        normalize_review_host("192.168.1.20")


def test_review_server_grade_and_security(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    run_path = tmp_path / "run.json"
    write_authoring_run(
        run_path,
        _run([_case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])]),
    )

    monkeypatch.setattr(
        "offline_rag.gold_authoring.review_view.resolve_seed_text_from_chunk_set",
        lambda settings, *, chunk_set_id, chunk_id: f"text:{chunk_id}",
    )

    server, _session, url = create_review_server(
        settings=settings,
        run_path=run_path,
        host="127.0.0.1",
        port=0,
    )
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/", headers={"Host": f"127.0.0.1:{port}"})
        res = conn.getresponse()
        body = res.read()
        assert res.status == 200
        assert b"Gold Review" in body

        conn.request("GET", "/api/run", headers={"Host": "evil.example"})
        res = conn.getresponse()
        res.read()
        assert res.status == 400

        payload = json.dumps({"chunk_id": "c1", "relevance": 2}).encode()
        headers = {
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "Content-Length": str(len(payload)),
        }
        conn.request("POST", "/api/cases/d1/grade", body=payload, headers=headers)
        res = conn.getresponse()
        data = json.loads(res.read().decode())
        assert res.status == 200
        assert data["ok"] is True
        assert data["case"]["judged_count"] == 1

        conn.request(
            "POST",
            "/api/cases/d1/grade",
            body=payload,
            headers={**headers, "Origin": "https://evil.example"},
        )
        res = conn.getresponse()
        res.read()
        assert res.status == 403

        conn.request("GET", "/api/cases/d1/accept", headers={"Host": f"127.0.0.1:{port}"})
        res = conn.getresponse()
        res.read()
        assert res.status != 200

        loaded = load_authoring_run(run_path)
        assert loaded.cases[0].human_judgment_map()["c1"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert url.startswith("http://127.0.0.1:")


def test_finalize_fail_closed_and_positive_only(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    corpus_name = "manuals"
    (settings.paths.corpora / corpus_name).mkdir(parents=True, exist_ok=True)

    good = _case("d_good", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    pending = _case("d_pending", "Pending?", [_candidate("c3")])
    rejected = _case("d_rej", "Reject?", [_candidate("c4")])
    run = _run([good, pending, rejected], corpus_name=corpus_name)
    run = _grade_all(run, "d_good", [0, 2])
    run = accept_case(run, draft_case_id="d_good")
    run = reject_case(run, draft_case_id="d_rej")

    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, run)

    result = run_gold_finalize(settings, run_path=run_path)
    assert result.exit_code == 0
    assert result.exported_case_ids == ["d_good"]
    assert result.output_path is not None
    expected = default_authoring_gold_dir(
        settings, corpus_name=corpus_name, authoring_run_id="authorrun_test"
    )
    assert result.output_path == expected
    loaded = load_gold_dataset(result.output_path)
    assert loaded.cases[0].id == "d_good"
    assert loaded.cases[0].judgments == (ChunkJudgment(chunk_id="c2", relevance=2),)
    assert loaded.meta.chunk_set_id == "chunkset_A"
    assert loaded.meta.metadata.get("authoring_run_id") == "authorrun_test"
    assert loaded.meta.corpus_name == corpus_name

    with pytest.raises(FinalizePreRunError, match="already exists"):
        run_gold_finalize(settings, run_path=run_path)

    bad_payload = json.loads(run.model_dump_json())
    bad_payload["cases"].append(
        {
            "draft_case_id": "d_bad",
            "proposed_query": "Bad?",
            "proposed_category": "ops",
            "proposed_tags": ["module-1"],
            "candidates": [
                {"chunk_id": "c5", "retrieval_hits": []},
                {"chunk_id": "c6", "retrieval_hits": []},
            ],
            "human_review": {
                "status": "accepted",
                "judgments": [{"chunk_id": "c5", "relevance": 2}],
                "query_override": None,
                "category_override": {"is_overridden": False, "value": None},
                "tags_override": None,
                "grade_basis_query": "Bad?",
            },
        }
    )
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GoldAuthoringRun.model_validate(bad_payload)

    only_pending = _run([pending], corpus_name=corpus_name).model_copy(
        update={"authoring_run_id": "authorrun_pending_only"}
    )
    pend_path = tmp_path / "pending_only.json"
    write_authoring_run(pend_path, only_pending)
    with pytest.raises(FinalizePreRunError, match="no accepted"):
        run_gold_finalize(settings, run_path=pend_path)


def test_finalize_edited_exports_effective_query(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    corpus_name = "manuals"
    (settings.paths.corpora / corpus_name).mkdir(parents=True, exist_ok=True)
    case = _case("d1", "Original?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = _run([case], corpus_name=corpus_name)
    run = set_reviewed_query(run, draft_case_id="d1", query="Corrected question?")
    run = _grade_all(run, "d1", [1, 0])
    run = approve_edited_case(run, draft_case_id="d1")
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, run)
    out = tmp_path / "gold_out"
    result = run_gold_finalize(settings, run_path=run_path, output=out)
    loaded = load_gold_dataset(result.output_path)
    assert loaded.cases[0].query == "Corrected question?"
    assert loaded.cases[0].judgments[0].relevance == 1
    silver = load_authoring_run(run_path)
    assert silver.cases[0].proposed_query == "Original?"
    assert silver.cases[0].human_status == HumanReviewStatus.EDITED


def test_finalize_force_preserves_old_on_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    corpus_name = "manuals"
    (settings.paths.corpora / corpus_name).mkdir(parents=True, exist_ok=True)
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = accept_case(
        _grade_all(_run([case], corpus_name=corpus_name), "d1", [2, 0]),
        draft_case_id="d1",
    )
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, run)
    out = tmp_path / "gold"
    first = run_gold_finalize(settings, run_path=run_path, output=out)
    old_id = first.dataset_id
    assert (out / "meta.json").exists()

    run2 = reopen_case(run, draft_case_id="d1")
    write_authoring_run(run_path, run2)
    with pytest.raises(FinalizePreRunError, match="no accepted"):
        run_gold_finalize(settings, run_path=run_path, output=out, force=True)
    still = load_gold_dataset(out)
    assert still.dataset_id == old_id


def test_cli_help_surfaces() -> None:
    parser = build_parser()
    review = None
    finalize = None
    for action in parser._subparsers._group_actions:
        for name, sub in action.choices.items():
            if name != "gold":
                continue
            for gold_action in sub._subparsers._group_actions:
                review = gold_action.choices.get("review")
                finalize = gold_action.choices.get("finalize")
    assert review is not None
    assert finalize is not None
    review_opts = {a.dest for a in review._actions}
    finalize_opts = {a.dest for a in finalize._actions}
    assert "run" in review_opts
    assert "host" in review_opts
    assert "port" in review_opts
    assert "output" not in review_opts
    assert "force" not in review_opts
    assert "model" not in review_opts
    assert "corpus" not in review_opts
    assert "output" in finalize_opts
    assert "force" in finalize_opts
    assert "corpus" not in finalize_opts


def test_cli_finalize_missing_run_fails() -> None:
    with pytest.raises(SystemExit):
        main(["gold", "finalize"])


def test_query_override_equal_proposed_canonicalizes_on_load() -> None:
    case = SilverCase.model_validate(
        {
            "draft_case_id": "d1",
            "proposed_query": "What is X?",
            "human_review": {
                "status": "pending",
                "judgments": [],
                "query_override": "What is X?",
                "category_override": {"is_overridden": False, "value": None},
                "tags_override": None,
                "grade_basis_query": None,
            },
        }
    )
    assert case.human_review is not None
    assert case.human_review.query_override is None
    assert case.effective_query() == "What is X?"
    assert case.proposal_content_changed() is False


def test_finalize_temp_validation_failure_leaves_new_destination_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from offline_rag.evaluation.gold import GoldDatasetError

    settings = _settings(tmp_path)
    corpus_name = "manuals"
    (settings.paths.corpora / corpus_name).mkdir(parents=True, exist_ok=True)
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = accept_case(
        _grade_all(_run([case], corpus_name=corpus_name), "d1", [2, 0]),
        draft_case_id="d1",
    )
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, run)
    out = tmp_path / "gold_new"
    assert not out.exists()

    def boom(_path: Path) -> None:
        raise GoldDatasetError("injected pre-publish failure")

    monkeypatch.setattr(
        "offline_rag.gold_authoring.finalize.load_gold_dataset", boom
    )
    with pytest.raises(FinalizePreRunError, match="before publication"):
        run_gold_finalize(settings, run_path=run_path, output=out)
    assert not out.exists()


def test_finalize_force_temp_validation_failure_preserves_old(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from offline_rag.evaluation.gold import GoldDatasetError

    settings = _settings(tmp_path)
    corpus_name = "manuals"
    (settings.paths.corpora / corpus_name).mkdir(parents=True, exist_ok=True)
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = accept_case(
        _grade_all(_run([case], corpus_name=corpus_name), "d1", [2, 0]),
        draft_case_id="d1",
    )
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, run)
    out = tmp_path / "gold"
    first = run_gold_finalize(settings, run_path=run_path, output=out)
    old_id = first.dataset_id
    old_meta = (out / "meta.json").read_text(encoding="utf-8")

    observed: dict[str, object] = {}

    def boom(path: Path):
        observed["validated_path"] = Path(path)
        observed["destination_exists_during_validate"] = out.exists()
        if out.exists():
            observed["old_id_during_validate"] = load_gold_dataset(out).dataset_id
        raise GoldDatasetError("injected pre-publish failure")

    monkeypatch.setattr(
        "offline_rag.gold_authoring.finalize.load_gold_dataset", boom
    )
    # Edit silver so a new dataset would differ, then fail validation.
    run2 = reopen_case(run, draft_case_id="d1")
    run2 = set_human_grade(run2, draft_case_id="d1", chunk_id="c1", relevance=1)
    run2 = set_human_grade(run2, draft_case_id="d1", chunk_id="c2", relevance=0)
    run2 = accept_case(run2, draft_case_id="d1")
    write_authoring_run(run_path, run2)

    with pytest.raises(FinalizePreRunError, match="before publication"):
        run_gold_finalize(settings, run_path=run_path, output=out, force=True)

    assert observed["destination_exists_during_validate"] is True
    assert observed["old_id_during_validate"] == old_id
    validated = Path(str(observed["validated_path"]))
    assert validated != out
    assert out.exists()
    still = load_gold_dataset(out)
    assert still.dataset_id == old_id
    assert (out / "meta.json").read_text(encoding="utf-8") == old_meta


def test_finalize_force_successful_replacement(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    corpus_name = "manuals"
    (settings.paths.corpora / corpus_name).mkdir(parents=True, exist_ok=True)
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = accept_case(
        _grade_all(_run([case], corpus_name=corpus_name), "d1", [2, 0]),
        draft_case_id="d1",
    )
    run_path = tmp_path / "run.json"
    write_authoring_run(run_path, run)
    out = tmp_path / "gold"
    first = run_gold_finalize(settings, run_path=run_path, output=out)
    old_id = first.dataset_id

    run2 = reopen_case(run, draft_case_id="d1")
    run2 = set_human_grade(run2, draft_case_id="d1", chunk_id="c1", relevance=1)
    run2 = set_human_grade(run2, draft_case_id="d1", chunk_id="c2", relevance=2)
    run2 = accept_case(run2, draft_case_id="d1")
    write_authoring_run(run_path, run2)
    second = run_gold_finalize(settings, run_path=run_path, output=out, force=True)
    assert second.dataset_id != old_id
    loaded = load_gold_dataset(out)
    assert loaded.dataset_id == second.dataset_id
    assert {j.relevance for j in loaded.cases[0].judgments} == {1, 2}


def test_historical_evidence_missing_chunk_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from offline_rag.gold_authoring.chunk_access import ChunkAccessError
    from offline_rag.gold_authoring.review_view import build_case_detail_payload

    settings = AppSettings()
    case = _case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])
    run = _run([case])

    def missing(settings, *, chunk_set_id, chunk_id):
        raise ChunkAccessError(f"chunk_id {chunk_id} not found")

    monkeypatch.setattr(
        "offline_rag.gold_authoring.review_view.resolve_seed_text_from_chunk_set",
        missing,
    )
    with pytest.raises(ReviewError, match="historical evidence unavailable") as exc:
        build_case_detail_payload(settings, run, case)
    assert exc.value.code == "evidence_unavailable"


def test_historical_evidence_missing_chunk_set_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from offline_rag.gold_authoring.chunk_access import ChunkAccessError
    from offline_rag.gold_authoring.review_view import build_case_detail_payload

    settings = AppSettings()
    case = _case("d1", "What is X?", [_candidate("c1")])
    run = _run([case])

    def missing_set(settings, *, chunk_set_id, chunk_id):
        raise ChunkAccessError(f"historical chunk-set unavailable: {chunk_set_id}")

    monkeypatch.setattr(
        "offline_rag.gold_authoring.review_view.resolve_seed_text_from_chunk_set",
        missing_set,
    )
    with pytest.raises(ReviewError) as exc:
        build_case_detail_payload(settings, run, case)
    assert exc.value.code == "evidence_unavailable"


def test_historical_evidence_never_uses_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from offline_rag.gold_authoring.review_view import build_case_detail_payload

    settings = AppSettings()
    case = _case("d1", "What is X?", [_candidate("c1")])
    run = _run([case])
    seen: list[str] = []

    def capture(settings, *, chunk_set_id, chunk_id):
        seen.append(chunk_set_id)
        return "exact historical text"

    monkeypatch.setattr(
        "offline_rag.gold_authoring.review_view.resolve_seed_text_from_chunk_set",
        capture,
    )
    detail = build_case_detail_payload(settings, run, case)
    assert seen == ["chunkset_A"]
    assert detail["candidates"][0]["text"] == "exact historical text"
    assert "[evidence unavailable" not in detail["candidates"][0]["text"]


def test_case_detail_http_fails_closed_on_missing_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from offline_rag.gold_authoring.chunk_access import ChunkAccessError

    settings = _settings(tmp_path)
    run_path = tmp_path / "run.json"
    write_authoring_run(
        run_path,
        _run([_case("d1", "What is X?", [_candidate("c1")])]),
    )

    def missing(settings, *, chunk_set_id, chunk_id):
        raise ChunkAccessError(f"chunk_id {chunk_id} not found")

    monkeypatch.setattr(
        "offline_rag.gold_authoring.review_view.resolve_seed_text_from_chunk_set",
        missing,
    )
    server, _session, _url = create_review_server(
        settings=settings, run_path=run_path, host="127.0.0.1", port=0
    )
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/cases/d1", headers={"Host": f"127.0.0.1:{port}"})
        res = conn.getresponse()
        data = json.loads(res.read().decode())
        conn.close()
        assert res.status == 400
        assert data["ok"] is False
        assert data["error"]["code"] == "evidence_unavailable"
        assert "case" not in data
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_strict_json_category_and_tags_mutations(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    run_path = tmp_path / "run.json"
    write_authoring_run(
        run_path,
        _run([_case("d1", "What is X?", [_candidate("c1"), _candidate("c2", rank=2)])]),
    )
    server, _session, _url = create_review_server(
        settings=settings, run_path=run_path, host="127.0.0.1", port=0
    )
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{port}"
        headers_base = {
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/json",
            "Origin": origin,
        }

        def post(path: str, payload: dict) -> tuple[int, dict]:
            body = json.dumps(payload).encode()
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(
                "POST",
                path,
                body=body,
                headers={**headers_base, "Content-Length": str(len(body))},
            )
            res = conn.getresponse()
            data = json.loads(res.read().decode())
            conn.close()
            return res.status, data

        for payload in (
            {"clear": "false"},
            {"clear": 1},
            {},
        ):
            status, data = post("/api/cases/d1/category", payload)
            assert status == 400
            assert data["ok"] is False

        for payload in (
            {"clear_override": "false"},
            {"clear_override": 0},
            {},
            {"clear_override": False},  # false without tags list
        ):
            status, data = post("/api/cases/d1/tags", payload)
            assert status == 400
            assert data["ok"] is False

        before = load_authoring_run(run_path)
        assert before.cases[0].human_review is None or (
            before.cases[0].human_review.category_override.is_overridden is False
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_ipv6_loopback_bind_when_available(tmp_path: Path) -> None:
    import socket

    try:
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        probe.bind(("::1", 0))
        probe.close()
    except OSError:
        pytest.skip("IPv6 loopback unavailable on this platform")

    settings = _settings(tmp_path)
    run_path = tmp_path / "run.json"
    write_authoring_run(
        run_path,
        _run([_case("d1", "What is X?", [_candidate("c1")])]),
    )
    server, session, url = create_review_server(
        settings=settings, run_path=run_path, host="::1", port=0
    )
    assert session.host == "::1"
    assert url.startswith("http://[::1]:")
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("::1", port, timeout=5)
        conn.request("GET", "/", headers={"Host": f"[::1]:{port}"})
        res = conn.getresponse()
        body = res.read()
        assert res.status == 200
        assert b"Gold Review" in body
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
