"""Slice 16F-C — Gold Lab scientific projection / export / registration."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

_APP_TEST_DIR = Path(__file__).resolve().parent
if str(_APP_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_TEST_DIR))

from test_slice16f_a_gold_lab_foundation import (
    CHUNK_A,
    CHUNK_B,
    CHUNK_SET_ID,
    CORPUS_ID,
    CORPUS_NAME,
    REPO_ROOT,
    _active_workspace,
    _baseline,
    _policy,
    _publish_bound,
    _settings,
)
from test_slice16f_b_effective_state import CASE_ID, _ready

from offline_rag.app.gold_lab import (
    REGISTRATION_SCHEMA,
    GoldCampaignService,
    GoldLabError,
    GoldLabMutationService,
    GoldLabScientificExportService,
    GoldLabStore,
    GoldProjectType,
    GoldRegistration,
    new_campaign_id,
    new_project_id,
    project_authoring_run,
    projection_text,
    valid_registered_case_ids_for_campaign,
)
from offline_rag.app.gold_lab.leases import GoldLabDatasetLease
from offline_rag.app.gold_lab.paths import (
    baseline_authoring_run_path,
    campaign_json_path,
    dataset_dir,
    datasets_root,
    projection_authoring_run_path,
    registration_path,
)
from offline_rag.app.gold_lab.registrations import (
    load_registration,
    validate_registration_against_authority,
)
from offline_rag.evaluation.gold import (
    GOLD_SCHEMA_V1,
    ChunkJudgment,
    GoldCase,
    GoldDatasetMeta,
    compute_gold_dataset_id,
    load_gold_dataset,
)
from offline_rag.gold_authoring.models import GoldAuthoringRun
from offline_rag.gold_authoring.review_models import HumanReviewStatus
from offline_rag.ingestion.io import atomic_write_text


def _complete_positive(mut: GoldLabMutationService, campaign_id: str) -> None:
    mut.submit_question_check(
        campaign_id=campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc_accept",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=2,
        idempotency_key="abs_a",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        relevance=0,
        idempotency_key="abs_b",
    )


def _export(settings, store, campaign_id: str, **hooks):
    return GoldLabScientificExportService(
        settings, store=store, **hooks
    ).export_and_register(campaign_id)


# --- Projection ---


def test_projection_preserves_baseline_and_non_reviewable(tmp_path: Path) -> None:
    _, store, campaign, mut = _ready(tmp_path)

    state = mut.load_effective_state(campaign.campaign_id)
    projected = project_authoring_run(state)
    assert len(projected.cases) == len(state.baseline.cases)
    assert [c.draft_case_id for c in projected.cases] == [
        c.draft_case_id for c in state.baseline.cases
    ]
    assert projected.authoring_run_id == state.baseline.authoring_run_id
    assert projected.authorcfg_id == state.baseline.authorcfg_id
    assert projected.chunk_set_id == state.baseline.chunk_set_id
    assert projected.corpus_id == state.baseline.corpus_id
    inert = next(c for c in projected.cases if c.draft_case_id == "draft_inert")
    baseline_inert = next(
        c for c in state.baseline.cases if c.draft_case_id == "draft_inert"
    )
    assert inert.human_review == baseline_inert.human_review
    assert inert.human_status is HumanReviewStatus.PENDING
    rev = next(c for c in projected.cases if c.draft_case_id == CASE_ID)
    assert rev.human_review is not None
    assert rev.human_review.status is HumanReviewStatus.PENDING
    assert rev.human_review.judgments == []
    roundtrip = GoldAuthoringRun.model_validate_json(projected.model_dump_json())
    assert roundtrip.model_dump_json() == projected.model_dump_json()
    del store


def test_projection_reject_accept_edit_status_matrix(tmp_path: Path) -> None:
    _, store, campaign, mut = _ready(tmp_path)


    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "reject"},
        idempotency_key="rej",
    )
    rejected = project_authoring_run(mut.load_effective_state(campaign.campaign_id))
    case = next(c for c in rejected.cases if c.draft_case_id == CASE_ID)
    assert case.human_review is not None
    assert case.human_review.status is HumanReviewStatus.REJECTED
    assert case.human_review.judgments == []
    assert case.human_review.query_override is None
    assert case.human_review.grade_basis_query is None

    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="acc",
    )
    partial = project_authoring_run(mut.load_effective_state(campaign.campaign_id))
    case = next(c for c in partial.cases if c.draft_case_id == CASE_ID)
    assert case.human_review is not None
    assert case.human_review.status is HumanReviewStatus.PENDING

    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=2,
        idempotency_key="a1",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        relevance=0,
        idempotency_key="b1",
    )
    accepted = project_authoring_run(mut.load_effective_state(campaign.campaign_id))
    case = next(c for c in accepted.cases if c.draft_case_id == CASE_ID)
    assert case.human_review is not None
    assert case.human_review.status is HumanReviewStatus.ACCEPTED
    grades = {j.chunk_id: j.relevance for j in case.human_review.judgments}
    assert grades[CHUNK_A] == 2
    assert grades[CHUNK_B] == 0
    assert [j.chunk_id for j in case.human_review.judgments] == sorted(grades)
    assert case.human_review.grade_basis_query == case.effective_query()

    # all-zero -> PENDING
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=0,
        idempotency_key="a0",
    )
    all_zero = project_authoring_run(mut.load_effective_state(campaign.campaign_id))
    case = next(c for c in all_zero.cases if c.draft_case_id == CASE_ID)
    assert case.human_review is not None
    assert case.human_review.status is HumanReviewStatus.PENDING
    assert {j.relevance for j in case.human_review.judgments} == {0}

    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={
            "decision": "edit",
            "effective_query": "Edited offline RAG question",
            "effective_category": "ops",
            "effective_tags": ["alpha"],
        },
        idempotency_key="edit1",
    )
    edit_partial = project_authoring_run(mut.load_effective_state(campaign.campaign_id))
    case = next(c for c in edit_partial.cases if c.draft_case_id == CASE_ID)
    assert case.human_review is not None
    assert case.human_review.status is HumanReviewStatus.PENDING
    assert case.human_review.judgments == []  # old-query grades absent
    assert case.human_review.query_override is not None

    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=1,
        idempotency_key="a_edit",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        relevance=2,
        idempotency_key="b_edit",
    )
    edited = project_authoring_run(mut.load_effective_state(campaign.campaign_id))
    case = next(c for c in edited.cases if c.draft_case_id == CASE_ID)
    assert case.human_review is not None
    assert case.human_review.status is HumanReviewStatus.EDITED
    assert case.human_review.grade_basis_query == case.effective_query()
    assert case.proposal_content_changed() is True

    # edit all-zero -> PENDING
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=0,
        idempotency_key="a_z",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        relevance=0,
        idempotency_key="b_z",
    )
    edit_zero = project_authoring_run(mut.load_effective_state(campaign.campaign_id))
    case = next(c for c in edit_zero.cases if c.draft_case_id == CASE_ID)
    assert case.human_review is not None
    assert case.human_review.status is HumanReviewStatus.PENDING
    del store


def test_projection_deterministic_bytes_and_hash(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)
    state = mut.load_effective_state(campaign.campaign_id)
    p1 = project_authoring_run(state)
    p2 = project_authoring_run(state)
    t1 = projection_text(p1)
    t2 = projection_text(p2)
    assert t1 == t2
    assert t1.endswith("\n")
    h1 = hashlib.sha256(t1.encode("utf-8")).hexdigest()
    h2 = hashlib.sha256(t2.encode("utf-8")).hexdigest()
    assert h1 == h2

    baseline_path = baseline_authoring_run_path(settings, campaign.campaign_id)
    before = baseline_path.read_bytes()
    result = _export(settings, store, campaign.campaign_id)
    after = baseline_path.read_bytes()
    assert before == after
    proj_bytes = projection_authoring_run_path(
        settings, campaign.campaign_id
    ).read_bytes()
    assert hashlib.sha256(proj_bytes).hexdigest() == result.projection_sha256
    assert result.registration.projection_sha256 == result.projection_sha256

    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=1,
        idempotency_key="a_chg",
    )
    changed = projection_text(
        project_authoring_run(mut.load_effective_state(campaign.campaign_id))
    )
    assert changed != t1
    del store


# --- Export / dataset / registration ---


def test_export_gold_dataset_positive_only_and_registration(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    before_score = mut.contribution(campaign.campaign_id)
    assert before_score.gold_finalized == 0

    _complete_positive(mut, campaign.campaign_id)
    mid = mut.contribution(campaign.campaign_id)
    assert mid.gold_finalized == 0
    assert mid.cases_completed == 1

    result = _export(settings, store, campaign.campaign_id)
    assert result.dataset_id.startswith("gold_")
    assert len(result.dataset_id) == len("gold_") + 64
    assert result.dataset_path == f"datasets/{result.dataset_id}"
    assert result.exported_case_ids == (CASE_ID,)
    assert result.dataset_reused is False
    assert result.registration_replayed is False

    canonical = dataset_dir(settings, result.dataset_id)
    loaded = load_gold_dataset(canonical)
    assert loaded.source_schema == GOLD_SCHEMA_V1
    assert loaded.dataset_id == result.dataset_id
    assert loaded.meta.chunk_set_id == CHUNK_SET_ID
    assert loaded.meta.corpus_id == CORPUS_ID
    assert loaded.meta.corpus_name == CORPUS_NAME
    assert len(loaded.cases) == 1
    gold_case = loaded.cases[0]
    assert gold_case.id == CASE_ID
    rels = {j.chunk_id: j.relevance for j in gold_case.judgments}
    assert CHUNK_A in rels and rels[CHUNK_A] == 2
    assert CHUNK_B not in rels  # grade 0 omitted

    # Projection retains grade 0
    proj = GoldAuthoringRun.model_validate_json(
        projection_authoring_run_path(settings, campaign.campaign_id).read_text(
            encoding="utf-8"
        )
    )
    hr = next(c for c in proj.cases if c.draft_case_id == CASE_ID).human_review
    assert hr is not None
    assert {j.relevance for j in hr.judgments} == {0, 2}

    reg = result.registration
    assert reg.schema_version == REGISTRATION_SCHEMA
    assert reg.campaign_id == campaign.campaign_id
    assert reg.project_id == campaign.project_id
    assert reg.baseline_sha256 == campaign.baseline_sha256
    assert reg.projection_sha256 == result.projection_sha256
    assert reg.exported_case_ids == [CASE_ID]
    assert registration_path(
        settings, result.dataset_id, campaign.campaign_id
    ).is_file()

    after = mut.contribution(campaign.campaign_id)
    assert after.gold_finalized == 1
    assert after.total_score == mid.total_score + 15

    # Idempotent retry
    reg_bytes = registration_path(
        settings, result.dataset_id, campaign.campaign_id
    ).read_bytes()
    meta_bytes = (canonical / "meta.json").read_bytes()
    cases_bytes = (canonical / "cases.jsonl").read_bytes()
    registered_at = reg.registered_at
    replay = _export(settings, store, campaign.campaign_id)
    assert replay.dataset_reused is True
    assert replay.registration_replayed is True
    assert replay.registration.registered_at == registered_at
    assert (
        registration_path(settings, result.dataset_id, campaign.campaign_id).read_bytes()
        == reg_bytes
    )
    assert (canonical / "meta.json").read_bytes() == meta_bytes
    assert (canonical / "cases.jsonl").read_bytes() == cases_bytes
    assert mut.contribution(campaign.campaign_id).gold_finalized == 1
    del store


def test_export_edited_case_and_fail_closed_empty(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={
            "decision": "edit",
            "effective_query": "Changed question text",
            "effective_category": None,
            "effective_tags": [],
        },
        idempotency_key="ed",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=1,
        idempotency_key="a",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        relevance=2,
        idempotency_key="b",
    )
    result = _export(settings, store, campaign.campaign_id)
    loaded = load_gold_dataset(dataset_dir(settings, result.dataset_id))
    assert loaded.cases[0].id == CASE_ID
    assert loaded.cases[0].query == "Changed question text"

    # Reject-only / pending-only cannot finalize
    settings2, store2, campaign2, mut2 = _ready(tmp_path / "empty")
    mut2.submit_question_check(
        campaign_id=campaign2.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "reject"},
        idempotency_key="rej",
    )
    with pytest.raises(GoldLabError) as exc:
        _export(settings2, store2, campaign2.campaign_id)
    assert exc.value.reason == "gold_finalize_failed"

    settings3, store3, campaign3, mut3 = _ready(tmp_path / "zero")
    mut3.submit_question_check(
        campaign_id=campaign3.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="acc",
    )
    mut3.submit_absolute_relevance(
        campaign_id=campaign3.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=0,
        idempotency_key="a0",
    )
    mut3.submit_absolute_relevance(
        campaign_id=campaign3.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        relevance=0,
        idempotency_key="b0",
    )
    with pytest.raises(GoldLabError) as exc2:
        _export(settings3, store3, campaign3.campaign_id)
    assert exc2.value.reason == "gold_finalize_failed"
    del store
    del store2
    del store3


def test_multi_campaign_shared_dataset_reuse(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="16FC Multi")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Multi",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    camp_a = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(authoring_run_id="authorrun_a"),
        selection_policy=_policy(),
        campaign_id=new_campaign_id(),
    )
    camp_b = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(authoring_run_id="authorrun_b"),
        selection_policy=_policy(),
        campaign_id=new_campaign_id(),
    )
    mut = GoldLabMutationService(settings, store=store)
    _complete_positive(mut, camp_a.campaign_id)
    _complete_positive(mut, camp_b.campaign_id)

    r1 = _export(settings, store, camp_a.campaign_id)
    meta1 = (dataset_dir(settings, r1.dataset_id) / "meta.json").read_bytes()
    cases1 = (dataset_dir(settings, r1.dataset_id) / "cases.jsonl").read_bytes()

    r2 = _export(settings, store, camp_b.campaign_id)
    assert r2.dataset_id == r1.dataset_id
    assert r2.dataset_reused is True
    assert r2.registration_replayed is False
    assert (
        dataset_dir(settings, r1.dataset_id) / "meta.json"
    ).read_bytes() == meta1
    assert (
        dataset_dir(settings, r1.dataset_id) / "cases.jsonl"
    ).read_bytes() == cases1
    assert r1.registration.baseline_sha256 != r2.registration.baseline_sha256
    assert r1.registration.projection_sha256 != r2.registration.projection_sha256
    assert registration_path(
        settings, r1.dataset_id, camp_a.campaign_id
    ).is_file()
    assert registration_path(
        settings, r1.dataset_id, camp_b.campaign_id
    ).is_file()
    # First publisher metadata may retain authorrun_a
    meta_obj = json.loads(meta1.decode("utf-8"))
    assert meta_obj["metadata"]["authoring_run_id"] == "authorrun_a"
    del store


def test_crash_after_dataset_before_registration(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        GoldLabScientificExportService(
            settings,
            store=store,
            after_dataset_hook=lambda: (_ for _ in ()).throw(Boom("crash")),
        ).export_and_register(campaign.campaign_id)

    # Dataset published, registration absent
    # Discover dataset id from datasets root
    datasets = [
        p
        for p in (settings.paths.gold_lab / "datasets").iterdir()
        if p.is_dir() and p.name.startswith("gold_")
    ]
    assert len(datasets) == 1
    dataset_id = datasets[0].name
    loaded = load_gold_dataset(datasets[0])
    assert loaded.dataset_id == dataset_id
    assert not registration_path(settings, dataset_id, campaign.campaign_id).exists()
    assert mut.contribution(campaign.campaign_id).gold_finalized == 0

    retry = _export(settings, store, campaign.campaign_id)
    assert retry.dataset_id == dataset_id
    assert retry.dataset_reused is True
    assert retry.registration_replayed is False
    assert registration_path(settings, dataset_id, campaign.campaign_id).is_file()
    assert mut.contribution(campaign.campaign_id).gold_finalized == 1
    del store


def test_contribution_sticky_and_malformed_fail_closed(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)
    result = _export(settings, store, campaign.campaign_id)
    scored = mut.contribution(campaign.campaign_id)
    assert scored.gold_finalized == 1
    base = scored.total_score

    # Later reject does not erase Gold-finalized +15
    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "reject"},
        idempotency_key="later_rej",
    )
    after_reject = mut.contribution(campaign.campaign_id)
    assert after_reject.gold_finalized == 1
    assert after_reject.total_score == 5 + 15  # question reviewed + finalized

    # Duplicate case across registrations still +15 once
    ids = valid_registered_case_ids_for_campaign(
        settings,
        campaign_id=campaign.campaign_id,
        campaign=store.get_campaign(campaign.campaign_id),
        project=store.get_project(campaign.project_id),
    )
    assert ids == (CASE_ID,)

    # Malformed registration fails closed
    path = registration_path(settings, result.dataset_id, campaign.campaign_id)
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(GoldLabError) as exc:
        mut.contribution(campaign.campaign_id)
    assert exc.value.reason == "registration_corrupt"
    del base
    del store


def test_closed_campaign_export_no_ledger_mutation(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)
    ledger = Path(settings.paths.gold_lab) / "campaigns" / campaign.campaign_id / "ledger"
    before_files = sorted(p.name for p in ledger.glob("*.json")) if ledger.is_dir() else []
    store.close_campaign(campaign.campaign_id)
    closed = store.get_campaign(campaign.campaign_id)
    assert closed.status.value == "closed"

    result = _export(settings, store, campaign.campaign_id)
    assert result.exported_case_ids == (CASE_ID,)
    after_files = sorted(p.name for p in ledger.glob("*.json"))
    assert after_files == before_files
    assert store.get_campaign(campaign.campaign_id).status.value == "closed"
    assert store.get_project(campaign.project_id).status.value == "active"
    del store


def test_registration_conflict_and_corrupt_dataset(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)
    result = _export(settings, store, campaign.campaign_id)
    path = registration_path(settings, result.dataset_id, campaign.campaign_id)
    existing = GoldRegistration.model_validate_json(path.read_text(encoding="utf-8"))
    conflict = existing.model_copy(
        update={"projection_sha256": "a" * 64}
    )
    path.write_text(conflict.model_dump_json(), encoding="utf-8")
    with pytest.raises(GoldLabError) as exc:
        _export(settings, store, campaign.campaign_id)
    assert exc.value.reason in {
        "registration_conflict",
        "registration_provenance_mismatch",
    }

    # Restore valid registration then corrupt dataset
    path.write_text(existing.model_dump_json(), encoding="utf-8")
    (dataset_dir(settings, result.dataset_id) / "meta.json").write_text(
        "{}", encoding="utf-8"
    )
    with pytest.raises(GoldLabError):
        mut.contribution(campaign.campaign_id)
    del store


def test_nonscope_no_api_ui_config(tmp_path: Path) -> None:
    from offline_rag.app import gold_lab as gl

    assert not hasattr(gl, "router")
    assert (REPO_ROOT / "src" / "offline_rag" / "evaluation" / "gold.py").is_file()
    gold_src = (
        REPO_ROOT / "src" / "offline_rag" / "evaluation" / "gold.py"
    ).read_text(encoding="utf-8")
    assert GOLD_SCHEMA_V1 in gold_src
    # No HTTP modules under gold_lab
    gold_lab_dir = REPO_ROOT / "src" / "offline_rag" / "app" / "gold_lab"
    assert not (gold_lab_dir / "api.py").exists()
    assert not (gold_lab_dir / "routes.py").exists()
    del tmp_path


def test_dataset_id_path_grammar() -> None:
    from offline_rag.app.gold_lab.ids import validate_dataset_id
    from offline_rag.app.gold_lab.paths import dataset_dir
    from offline_rag.config.models import PathSettings

    assert validate_dataset_id("gold_" + "ab" * 32)
    with pytest.raises(GoldLabError):
        validate_dataset_id("gold_nothex")
    with pytest.raises(GoldLabError):
        dataset_dir(PathSettings(gold_lab=Path("data/gold-lab")), "../evil")


# --- Rework 1 ---


def _candidate_dirs(settings, campaign_id: str) -> list[Path]:
    root = datasets_root(settings)
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.glob(f".candidate.{campaign_id}.*") if p.is_dir()
    )


def _write_forged_dataset(
    settings,
    *,
    chunk_set_id: str,
    corpus_id: str,
    corpus_name: str,
    case_id: str,
    query: str,
) -> str:
    cases = (
        GoldCase(
            id=case_id,
            query=query,
            category=None,
            tags=(),
            judgments=(ChunkJudgment(chunk_id=CHUNK_A, relevance=2),),
        ),
    )
    dataset_id = compute_gold_dataset_id(
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
        corpus_name=corpus_name,
        cases=cases,
    )
    dest = dataset_dir(settings, dataset_id)
    dest.mkdir(parents=True, exist_ok=False)
    meta = GoldDatasetMeta(
        schema_version=GOLD_SCHEMA_V1,
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
        corpus_name=corpus_name,
        dataset_id=dataset_id,
        metadata={"authoring_run_id": "forged"},
    )
    (dest / "meta.json").write_text(meta.model_dump_json(indent=2) + "\n", encoding="utf-8")
    line = json.dumps(
        {
            "id": cases[0].id,
            "query": cases[0].query,
            "category": cases[0].category,
            "tags": list(cases[0].tags),
            "judgments": [
                {"chunk_id": j.chunk_id, "relevance": int(j.relevance)}
                for j in cases[0].judgments
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    (dest / "cases.jsonl").write_text(line + "\n", encoding="utf-8")
    return dataset_id


def test_rework1_dataset_campaign_scientific_binding(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)
    result = _export(settings, store, campaign.campaign_id)

    # Forge a second GoldDataset with different scientific binding.
    other_id = _write_forged_dataset(
        settings,
        chunk_set_id="chunkset_other_binding",
        corpus_id="corpus_other",
        corpus_name="othercorpus",
        case_id=CASE_ID,
        query="What is offline RAG?",
    )
    assert other_id != result.dataset_id

    # Registration carries campaign A provenance but points at dataset B.
    forged = result.registration.model_copy(
        update={
            "dataset_id": other_id,
            "dataset_path": f"datasets/{other_id}",
            "exported_case_ids": [CASE_ID],
        }
    )
    # Move authoritative registration to the forged dataset path.
    registration_path(settings, result.dataset_id, campaign.campaign_id).unlink()
    dest = registration_path(settings, other_id, campaign.campaign_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(dest, forged.model_dump_json())

    with pytest.raises(GoldLabError) as exc:
        validate_registration_against_authority(
            settings,
            forged,
            campaign=store.get_campaign(campaign.campaign_id),
            project=store.get_project(campaign.project_id),
        )
    assert exc.value.reason in {
        "registration_dataset_chunk_set_mismatch",
        "registration_dataset_corpus_id_mismatch",
        "registration_dataset_corpus_name_mismatch",
    }

    with pytest.raises(GoldLabError):
        mut.contribution(campaign.campaign_id)
    del store


def test_rework1_baseline_exported_case_membership(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)
    result = _export(settings, store, campaign.campaign_id)

    ghost_id = _write_forged_dataset(
        settings,
        chunk_set_id=campaign.chunk_set_id,
        corpus_id=campaign.corpus_id,
        corpus_name=campaign.corpus_name,
        case_id="ghost_case_not_in_baseline",
        query="Ghost query",
    )
    registration_path(settings, result.dataset_id, campaign.campaign_id).unlink()
    forged = result.registration.model_copy(
        update={
            "dataset_id": ghost_id,
            "dataset_path": f"datasets/{ghost_id}",
            "exported_case_ids": ["ghost_case_not_in_baseline"],
        }
    )
    dest = registration_path(settings, ghost_id, campaign.campaign_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(dest, forged.model_dump_json())

    with pytest.raises(GoldLabError) as exc:
        validate_registration_against_authority(
            settings,
            forged,
            campaign=store.get_campaign(campaign.campaign_id),
            project=store.get_project(campaign.project_id),
        )
    assert exc.value.reason == "registration_unknown_exported_case"

    with pytest.raises(GoldLabError) as exc2:
        valid_registered_case_ids_for_campaign(
            settings,
            campaign_id=campaign.campaign_id,
            campaign=store.get_campaign(campaign.campaign_id),
            project=store.get_project(campaign.project_id),
        )
    assert exc2.value.reason == "registration_unknown_exported_case"
    del store


def test_rework1_load_registration_path_identity(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)
    result = _export(settings, store, campaign.campaign_id)
    path = registration_path(settings, result.dataset_id, campaign.campaign_id)
    existing = GoldRegistration.model_validate_json(path.read_text(encoding="utf-8"))
    other_dataset = "gold_" + ("cd" * 32)
    other_campaign = new_campaign_id()
    mismatched = existing.model_copy(
        update={
            "dataset_id": other_dataset,
            "campaign_id": other_campaign,
            "dataset_path": f"datasets/{other_dataset}",
        }
    )
    # Bypass model path consistency for this tamper by writing raw JSON.
    raw = mismatched.model_dump(mode="json")
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(GoldLabError) as exc:
        load_registration(
            settings, dataset_id=result.dataset_id, campaign_id=campaign.campaign_id
        )
    assert exc.value.reason == "registration_path_mismatch"
    del store


def test_rework1_missing_registered_dataset_no_repair(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)
    result = _export(settings, store, campaign.campaign_id)
    reg_path = registration_path(settings, result.dataset_id, campaign.campaign_id)
    reg_bytes = reg_path.read_bytes()
    canonical = dataset_dir(settings, result.dataset_id)
    shutil.rmtree(canonical)
    assert not canonical.exists()

    with pytest.raises(GoldLabError) as exc:
        _export(settings, store, campaign.campaign_id)
    assert exc.value.reason == "registered_dataset_missing"
    assert not canonical.exists()
    assert reg_path.read_bytes() == reg_bytes
    assert _candidate_dirs(settings, campaign.campaign_id) == []
    del store


def test_rework1_missing_dataset_blocks_peer_campaign_reuse(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="16FC R1 peer")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Peer",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    camp_a = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(authoring_run_id="authorrun_a"),
        selection_policy=_policy(),
        campaign_id=new_campaign_id(),
    )
    camp_b = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(authoring_run_id="authorrun_b"),
        selection_policy=_policy(),
        campaign_id=new_campaign_id(),
    )
    mut = GoldLabMutationService(settings, store=store)
    _complete_positive(mut, camp_a.campaign_id)
    _complete_positive(mut, camp_b.campaign_id)
    r1 = _export(settings, store, camp_a.campaign_id)
    shutil.rmtree(dataset_dir(settings, r1.dataset_id))
    with pytest.raises(GoldLabError) as exc:
        _export(settings, store, camp_b.campaign_id)
    assert exc.value.reason == "registered_dataset_missing"
    assert not dataset_dir(settings, r1.dataset_id).exists()
    assert registration_path(settings, r1.dataset_id, camp_a.campaign_id).is_file()
    assert not registration_path(settings, r1.dataset_id, camp_b.campaign_id).exists()
    del store


def test_rework1_crash_recovery_preserved(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        GoldLabScientificExportService(
            settings,
            store=store,
            after_dataset_hook=lambda: (_ for _ in ()).throw(Boom("crash")),
        ).export_and_register(campaign.campaign_id)

    datasets = [
        p
        for p in datasets_root(settings).iterdir()
        if p.is_dir() and p.name.startswith("gold_")
    ]
    assert len(datasets) == 1
    dataset_id = datasets[0].name
    before_meta = (datasets[0] / "meta.json").read_bytes()
    before_cases = (datasets[0] / "cases.jsonl").read_bytes()
    assert not registration_path(settings, dataset_id, campaign.campaign_id).exists()

    retry = _export(settings, store, campaign.campaign_id)
    assert retry.dataset_reused is True
    assert retry.registration_replayed is False
    assert (datasets[0] / "meta.json").read_bytes() == before_meta
    assert (datasets[0] / "cases.jsonl").read_bytes() == before_cases
    del store


def test_rework1_candidate_cleanup_on_lease_and_corrupt(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)

    # First publish so we know dataset_id, then hold lease and retry-like export
    # after removing registration would reuse — instead hold lease during first export
    # by precomputing via a parallel path: export once, then corrupt and re-export.
    result = _export(settings, store, campaign.campaign_id)
    dataset_id = result.dataset_id

    # Lease contention during a second export after deleting registration (reuse path).
    registration_path(settings, dataset_id, campaign.campaign_id).unlink()
    with GoldLabDatasetLease(settings, dataset_id):
        with pytest.raises(GoldLabError) as exc:
            _export(settings, store, campaign.campaign_id)
        assert exc.value.reason == "gold_lab_lease_held"
    assert _candidate_dirs(settings, campaign.campaign_id) == []

    # Corrupt canonical dataset; export must clean candidate and leave corrupt bytes.
    canonical = dataset_dir(settings, dataset_id)
    meta_path = canonical / "meta.json"
    corrupt_bytes = b'{"schema_version":"offline-rag-gold-v1","broken":true}\n'
    meta_path.write_bytes(corrupt_bytes)
    with pytest.raises(GoldLabError) as exc2:
        _export(settings, store, campaign.campaign_id)
    assert exc2.value.reason in {
        "canonical_dataset_corrupt",
        "registered_dataset_missing",
        "canonical_dataset_schema_invalid",
        "canonical_dataset_id_mismatch",
    }
    assert meta_path.read_bytes() == corrupt_bytes
    assert _candidate_dirs(settings, campaign.campaign_id) == []
    del store


def test_rework1_locked_project_identity(tmp_path: Path) -> None:
    from offline_rag.app.gold_lab.models import GoldCampaign

    settings, store, campaign, mut = _ready(tmp_path)
    _complete_positive(mut, campaign.campaign_id)
    captured = campaign.project_id

    def _rewrite_campaign_project() -> None:
        path = campaign_json_path(settings, campaign.campaign_id)
        current = GoldCampaign.model_validate_json(path.read_text(encoding="utf-8"))
        mutated = current.model_copy(update={"project_id": new_project_id()})
        atomic_write_text(path, mutated.model_dump_json())
        assert mutated.project_id != captured

    with pytest.raises(GoldLabError) as exc:
        GoldLabScientificExportService(
            settings,
            store=store,
            after_locks_hook=_rewrite_campaign_project,
        ).export_and_register(campaign.campaign_id)
    assert exc.value.reason == "export_project_lock_mismatch"
    assert not any(
        p.is_file()
        for p in (settings.paths.gold_lab / "registrations").rglob("*.json")
    )
    assert list(datasets_root(settings).glob("gold_*")) == []
