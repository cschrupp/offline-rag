"""Slice 16F-B — Gold Lab effective-state / tasks / scoring / idempotent mutations."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_APP_TEST_DIR = Path(__file__).resolve().parent
if str(_APP_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_TEST_DIR))

from test_slice16f_a_gold_lab_foundation import (
    CHUNK_A,
    CHUNK_B,
    DOC_ID,
    REPO_ROOT,
    _active_workspace,
    _baseline,
    _policy,
    _publish_bound,
    _ready_campaign,
    _settings,
)

from offline_rag.app.gold_lab import (
    CONTRIBUTION_CONTRACT,
    IDEMPOTENCY_SCHEMA,
    GoldCampaignService,
    GoldLabError,
    GoldLabIdempotencyCatalog,
    GoldLabLedger,
    GoldLabMutationService,
    GoldLabStore,
    GoldLedgerRecordType,
    GoldProjectType,
    HardCallDesignation,
    absolute_relevance_task_id,
    hard_call_designation_id,
    new_campaign_id,
    normalize_idempotency_key,
    project_contribution,
    query_fingerprint,
    question_check_task_id,
)
from offline_rag.app.gold_lab.idempotency import idempotency_entry_filename
from offline_rag.app.gold_lab.ids import new_judgment_id, new_ledger_record_id
from offline_rag.app.gold_lab.leases import GoldLabCampaignLease
from offline_rag.app.gold_lab.paths import (
    datasets_root,
    hard_calls_path,
    idempotency_dir,
    projection_dir,
    registrations_root,
)
from offline_rag.app.workspace.models import canonical_request_fingerprint
from offline_rag.gold_authoring.models import SilverCase
from offline_rag.gold_authoring.pooling_models import PoolCandidate

CASE_ID = "draft_reviewable"


def _ready(tmp_path: Path, *, hard_calls: list[HardCallDesignation] | None = None):
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="16FB Desk")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="16FB",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    campaign_id = new_campaign_id()
    designations = list(hard_calls or [])
    if designations:
        # Caller must build designations against this campaign_id; rewrite if needed.
        pass
    campaign = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(),
        selection_policy=_policy(),
        hard_call_designations=designations,
        campaign_id=campaign_id,
    )
    mut = GoldLabMutationService(settings, store=store)
    return settings, store, campaign, mut


def _ready_with_hard_call(tmp_path: Path):
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="16FB HC")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="16FB HC",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    campaign_id = new_campaign_id()
    target = absolute_relevance_task_id(
        campaign_id=campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
    )
    designation = HardCallDesignation(
        designation_id=hard_call_designation_id(
            campaign_id=campaign_id, target_task_id=target
        ),
        target_task_id=target,
        reason_code="prelabel_disagreement",
    )
    campaign = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(),
        selection_policy=_policy(),
        hard_call_designations=[designation],
        campaign_id=campaign_id,
    )
    mut = GoldLabMutationService(settings, store=store)
    return settings, store, campaign, mut, target


# --- A. QUESTION CHECK ---


def test_question_check_lifecycle_and_correction(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    tasks = mut.project_tasks(campaign.campaign_id)
    qc = [t for t in tasks if t.task_kind.value == "question_check"]
    assert len(qc) == 1
    assert qc[0].active is True and qc[0].state.value == "pending"
    assert not any(t.case_id == "draft_inert" for t in tasks)

    r1 = mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc_accept_1",
    )
    assert r1.replayed is False
    assert r1.record.payload == {"decision": "accept"}
    assert r1.record.query_fingerprint == query_fingerprint("What is offline RAG?")
    assert r1.record.supersedes_judgment_id is None

    qc_task = question_check_task_id(campaign_id=campaign.campaign_id, case_id=CASE_ID)
    state = mut.load_effective_state(campaign.campaign_id)
    assert state.question_by_task[qc_task].decision.value == "accept"
    tasks = mut.project_tasks(campaign.campaign_id)
    assert next(t for t in tasks if t.task_id == qc_task).state.value == "completed"

    with pytest.raises(GoldLabError) as exc:
        mut.submit_question_check(
            campaign_id=campaign.campaign_id,
            case_id=CASE_ID,
            payload={
                "decision": "edit",
                "effective_query": "What is offline RAG?",
                "effective_category": None,
                "effective_tags": [],
            },
            idempotency_key="qc_edit_same",
        )
    assert exc.value.reason == "question_check_edit_not_semantic"

    r2 = mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={
            "decision": "edit",
            "effective_query": "  What is Seneca RAG?  ",
            "effective_category": "systems",
            "effective_tags": ["seneca", "rag"],
        },
        idempotency_key="qc_edit_1",
    )
    assert r2.record.supersedes_judgment_id == r1.record.judgment_id
    assert r2.record.payload["effective_query"] == "What is Seneca RAG?"
    assert r2.record.payload["effective_tags"] == ["rag", "seneca"]
    assert r2.record.query_fingerprint == query_fingerprint("What is Seneca RAG?")

    rows = GoldLabLedger(settings, store=store).list_records(campaign.campaign_id)
    assert len(rows) == 2
    assert rows[0].judgment_id == r1.record.judgment_id

    r3 = mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "reject"},
        idempotency_key="qc_reject_1",
    )
    assert r3.record.payload == {"decision": "reject"}
    assert r3.record.query_fingerprint is None
    assert r3.record.supersedes_judgment_id == r2.record.judgment_id


def test_question_check_branch_fails_in_fold(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path / "branch")
    r1 = mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc_a",
    )
    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "reject"},
        idempotency_key="qc_b",
    )
    ledger = GoldLabLedger(settings, store=store)
    ledger.append(
        campaign.campaign_id,
        record_type=GoldLedgerRecordType.QUESTION_CHECK,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc_branch",
        request_fingerprint=canonical_request_fingerprint({"branch": True}),
        query_fingerprint=query_fingerprint("What is offline RAG?"),
        supersedes_judgment_id=r1.record.judgment_id,
    )
    with pytest.raises(GoldLabError) as fold_exc:
        mut.load_effective_state(campaign.campaign_id)
    assert fold_exc.value.reason == "effective_state_supersession_non_current"


# --- B/C. TASK ACTIVATION + ABSOLUTE ---


def test_absolute_activation_query_basis_and_correction(tmp_path: Path) -> None:
    _, _, campaign, mut = _ready(tmp_path)
    abs_a = absolute_relevance_task_id(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
    )
    tasks = mut.project_tasks(campaign.campaign_id)
    abs_tasks = [t for t in tasks if t.task_kind.value == "absolute_relevance"]
    assert all(t.active is False and t.state.value == "pending" for t in abs_tasks)

    with pytest.raises(GoldLabError) as exc:
        mut.submit_absolute_relevance(
            campaign_id=campaign.campaign_id,
            case_id=CASE_ID,
            candidate_chunk_id=CHUNK_A,
            relevance=2,
            idempotency_key="abs_early",
        )
    assert exc.value.reason == "absolute_task_inactive"

    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc1",
    )
    tasks = mut.project_tasks(campaign.campaign_id)
    abs_tasks = [t for t in tasks if t.task_kind.value == "absolute_relevance"]
    assert all(t.active is True and t.state.value == "pending" for t in abs_tasks)

    with pytest.raises(GoldLabError):
        mut.submit_absolute_relevance(
            campaign_id=campaign.campaign_id,
            case_id=CASE_ID,
            candidate_chunk_id=CHUNK_A,
            relevance=True,  # type: ignore[arg-type]
            idempotency_key="abs_bool",
        )

    a1 = mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=2,
        idempotency_key="abs_a1",
    )
    assert a1.record.supersedes_judgment_id is None
    assert a1.record.query_fingerprint == query_fingerprint("What is offline RAG?")
    assert a1.record.task_id == abs_a

    a2 = mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=1,
        idempotency_key="abs_a2",
    )
    assert a2.record.supersedes_judgment_id == a1.record.judgment_id

    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={
            "decision": "edit",
            "effective_query": "What is offline RAG?",
            "effective_category": "systems",
            "effective_tags": ["x"],
        },
        idempotency_key="qc_meta",
    )
    state = mut.load_effective_state(campaign.campaign_id)
    assert abs_a in state.absolute_current_by_task
    assert state.absolute_current_by_task[abs_a].relevance == 1
    assert (
        next(t for t in mut.project_tasks(campaign.campaign_id) if t.task_id == abs_a).state.value
        == "completed"
    )

    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={
            "decision": "edit",
            "effective_query": "What is Seneca?",
            "effective_category": "systems",
            "effective_tags": ["x"],
        },
        idempotency_key="qc_query",
    )
    t_abs = next(t for t in mut.project_tasks(campaign.campaign_id) if t.task_id == abs_a)
    assert t_abs.task_id == abs_a
    assert t_abs.active is True and t_abs.state.value == "pending"

    a3 = mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=0,
        idempotency_key="abs_a3_new_basis",
    )
    assert a3.record.supersedes_judgment_id is None
    assert a3.record.query_fingerprint == query_fingerprint("What is Seneca?")
    state = mut.load_effective_state(campaign.campaign_id)
    assert state.absolute_current_by_task[abs_a].relevance == 0
    old_fp = query_fingerprint("What is offline RAG?")
    assert (abs_a, old_fp) in state.absolute_by_basis

    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "reject"},
        idempotency_key="qc_rej",
    )
    assert all(
        t.active is False and t.state.value == "pending"
        for t in mut.project_tasks(campaign.campaign_id)
        if t.task_kind.value == "absolute_relevance"
    )


# --- D. EVENT-TIME AUDIT ---


def test_event_time_audit_fail_closed(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path / "audit")
    ledger = GoldLabLedger(settings, store=store)
    ledger.append(
        campaign.campaign_id,
        record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        payload={"relevance": 2},
        idempotency_key="tamper_early",
        request_fingerprint=canonical_request_fingerprint({"t": 1}),
        query_fingerprint=query_fingerprint("What is offline RAG?"),
    )
    with pytest.raises(GoldLabError) as exc:
        mut.load_effective_state(campaign.campaign_id)
    assert exc.value.reason == "effective_state_absolute_inactive_question"

    settings2, store2, campaign2, mut2 = _ready(tmp_path / "audit2")
    ledger2 = GoldLabLedger(settings2, store=store2)
    mut2.submit_question_check(
        campaign_id=campaign2.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc",
    )
    ledger2.append(
        campaign2.campaign_id,
        record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        payload={"relevance": 1},
        idempotency_key="tamper_fp",
        request_fingerprint=canonical_request_fingerprint({"t": 2}),
        query_fingerprint=query_fingerprint("Wrong query"),
    )
    with pytest.raises(GoldLabError) as exc:
        mut2.load_effective_state(campaign2.campaign_id)
    assert exc.value.reason == "effective_state_absolute_query_mismatch"

    settings3, store3, campaign3, mut3 = _ready(tmp_path / "audit3")
    ledger3 = GoldLabLedger(settings3, store=store3)
    r = mut3.submit_question_check(
        campaign_id=campaign3.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc3",
    )
    ledger3.append(
        campaign3.campaign_id,
        record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        payload={"relevance": 2},
        idempotency_key="dup_jud",
        request_fingerprint=canonical_request_fingerprint({"t": 3}),
        query_fingerprint=query_fingerprint("What is offline RAG?"),
        judgment_id=r.record.judgment_id,
    )
    with pytest.raises(GoldLabError) as exc:
        mut3.load_effective_state(campaign3.campaign_id)
    assert exc.value.reason == "effective_state_duplicate_judgment_id"

    settings4, store4, campaign4, mut4 = _ready(tmp_path / "audit4")
    ledger4 = GoldLabLedger(settings4, store=store4)
    mut4.submit_question_check(
        campaign_id=campaign4.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc4",
    )
    a = mut4.submit_absolute_relevance(
        campaign_id=campaign4.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=2,
        idempotency_key="abs4a",
    )
    mut4.submit_absolute_relevance(
        campaign_id=campaign4.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        relevance=0,
        idempotency_key="abs4b",
    )
    ledger4.append(
        campaign4.campaign_id,
        record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        payload={"relevance": 1},
        idempotency_key="cross_task",
        request_fingerprint=canonical_request_fingerprint({"t": 4}),
        query_fingerprint=query_fingerprint("What is offline RAG?"),
        supersedes_judgment_id=a.record.judgment_id,
    )
    with pytest.raises(GoldLabError) as fold_exc:
        mut4.load_effective_state(campaign4.campaign_id)
    assert fold_exc.value.reason == "effective_state_cross_task_supersession"


# --- E/F. IDEMPOTENCY ---


def test_idempotency_replay_conflict_and_lifecycle(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    first = mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="  same_key  ",
        game_id="g1",
    )
    replay = mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="same_key",
        game_id="g1",
    )
    assert replay.replayed is True
    assert replay.record.record_id == first.record.record_id
    assert replay.record.sequence == first.record.sequence
    assert len(GoldLabLedger(settings, store=store).list_records(campaign.campaign_id)) == 1

    with pytest.raises(GoldLabError) as exc:
        mut.submit_question_check(
            campaign_id=campaign.campaign_id,
            case_id=CASE_ID,
            payload={"decision": "reject"},
            idempotency_key="same_key",
            game_id="g1",
        )
    assert exc.value.reason == "idempotency_conflict"

    store.close_campaign(campaign.campaign_id)
    with pytest.raises(GoldLabError) as exc:
        mut.submit_question_check(
            campaign_id=campaign.campaign_id,
            case_id=CASE_ID,
            payload={"decision": "reject"},
            idempotency_key="same_key",
            game_id="g1",
        )
    assert exc.value.reason == "idempotency_conflict"

    closed_replay = mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="same_key",
        game_id="g1",
    )
    assert closed_replay.record.record_id == first.record.record_id

    with pytest.raises(GoldLabError) as exc:
        mut.submit_question_check(
            campaign_id=campaign.campaign_id,
            case_id=CASE_ID,
            payload={"decision": "accept"},
            idempotency_key="new_after_close",
        )
    assert exc.value.reason == "campaign_closed"

    _settings2, store2, campaign2, mut2 = _ready(tmp_path / "arch")
    orig = mut2.submit_question_check(
        campaign_id=campaign2.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="arch_key",
    )
    store2.archive_project(campaign2.project_id)
    with pytest.raises(GoldLabError) as exc:
        mut2.submit_question_check(
            campaign_id=campaign2.campaign_id,
            case_id=CASE_ID,
            payload={"decision": "reject"},
            idempotency_key="arch_key",
        )
    assert exc.value.reason == "idempotency_conflict"
    again = mut2.submit_question_check(
        campaign_id=campaign2.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="arch_key",
    )
    assert again.record.record_id == orig.record.record_id
    with pytest.raises(GoldLabError) as exc:
        mut2.submit_question_check(
            campaign_id=campaign2.campaign_id,
            case_id=CASE_ID,
            payload={"decision": "accept"},
            idempotency_key="new_after_archive",
        )
    assert exc.value.reason == "project_archived"


def test_idempotency_crash_recovery(tmp_path: Path) -> None:
    settings, _store, campaign, mut = _ready(tmp_path)
    catalog = GoldLabIdempotencyCatalog(settings)
    key = normalize_idempotency_key("crash_key")
    req = canonical_request_fingerprint(
        {
            "kind": "question_check",
            "campaign_id": campaign.campaign_id,
            "case_id": CASE_ID,
            "payload": {"decision": "accept"},
            "game_id": None,
            "presentation_id": None,
        }
    )
    rid = new_ledger_record_id()
    jid = new_judgment_id()
    catalog.write_pending(
        campaign_id=campaign.campaign_id,
        idempotency_key=key,
        request_fingerprint=req,
        command_kind="question_check",
        record_id=rid,
        judgment_id=jid,
    )
    result = mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key=key,
    )
    assert result.record.record_id == rid
    assert result.record.judgment_id == jid
    entry = catalog.load_entry(campaign.campaign_id, key)
    assert entry is not None and entry.status.value == "committed"

    settings2, store2, campaign2, mut2 = _ready(tmp_path / "crash2")
    catalog2 = GoldLabIdempotencyCatalog(settings2)
    key2 = "crash2_key"
    req2 = canonical_request_fingerprint(
        {
            "kind": "question_check",
            "campaign_id": campaign2.campaign_id,
            "case_id": CASE_ID,
            "payload": {"decision": "accept"},
            "game_id": None,
            "presentation_id": None,
        }
    )
    rid2 = new_ledger_record_id()
    jid2 = new_judgment_id()
    catalog2.write_pending(
        campaign_id=campaign2.campaign_id,
        idempotency_key=key2,
        request_fingerprint=req2,
        command_kind="question_check",
        record_id=rid2,
        judgment_id=jid2,
    )
    ledger2 = GoldLabLedger(settings2, store=store2)
    with GoldLabCampaignLease(settings2, campaign2.campaign_id) as lease:
        ledger2.append_under_lease(
            lease,
            campaign2.campaign_id,
            record_type=GoldLedgerRecordType.QUESTION_CHECK,
            case_id=CASE_ID,
            payload={"decision": "accept"},
            idempotency_key=key2,
            request_fingerprint=req2,
            query_fingerprint=query_fingerprint("What is offline RAG?"),
            record_id=rid2,
            judgment_id=jid2,
        )
    assert catalog2.load_entry(campaign2.campaign_id, key2).status.value == "pending"
    recovered = mut2.submit_question_check(
        campaign_id=campaign2.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key=key2,
    )
    assert recovered.record.record_id == rid2
    assert recovered.replayed is True
    assert len(ledger2.list_records(campaign2.campaign_id)) == 1
    assert catalog2.load_entry(campaign2.campaign_id, key2).status.value == "committed"

    settings3, _, campaign3, mut3 = _ready(tmp_path / "crash3")
    catalog3 = GoldLabIdempotencyCatalog(settings3)
    key3 = "missing_ledger"
    req3 = canonical_request_fingerprint(
        {
            "kind": "question_check",
            "campaign_id": campaign3.campaign_id,
            "case_id": CASE_ID,
            "payload": {"decision": "accept"},
            "game_id": None,
            "presentation_id": None,
        }
    )
    catalog3.write_pending(
        campaign_id=campaign3.campaign_id,
        idempotency_key=key3,
        request_fingerprint=req3,
        command_kind="question_check",
        record_id=new_ledger_record_id(),
        judgment_id=new_judgment_id(),
    )
    catalog3.mark_committed(campaign_id=campaign3.campaign_id, idempotency_key=key3)
    with pytest.raises(GoldLabError) as exc:
        mut3.submit_question_check(
            campaign_id=campaign3.campaign_id,
            case_id=CASE_ID,
            payload={"decision": "accept"},
            idempotency_key=key3,
        )
    assert exc.value.reason == "idempotency_committed_missing_ledger"

    settings4, store4, campaign4, mut4 = _ready(tmp_path / "crash4")
    ledger4 = GoldLabLedger(settings4, store=store4)
    ledger4.append(
        campaign4.campaign_id,
        record_type=GoldLedgerRecordType.QUESTION_CHECK,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="orphan_key",
        request_fingerprint=canonical_request_fingerprint({"orphan": True}),
        query_fingerprint=query_fingerprint("What is offline RAG?"),
    )
    with pytest.raises(GoldLabError) as exc:
        mut4.submit_question_check(
            campaign_id=campaign4.campaign_id,
            case_id=CASE_ID,
            payload={"decision": "reject"},
            idempotency_key="orphan_key",
        )
    assert exc.value.reason == "idempotency_orphan_ledger_key"


# --- G. CANONICAL REQUEST FINGERPRINT ---


def test_canonical_request_fingerprints() -> None:
    a = canonical_request_fingerprint(
        {
            "kind": "question_check",
            "campaign_id": "goldcamp_" + ("a" * 32),
            "case_id": "c1",
            "payload": {
                "decision": "edit",
                "effective_query": "Q",
                "effective_category": None,
                "effective_tags": ["a", "b"],
            },
            "game_id": None,
            "presentation_id": None,
        }
    )
    b = canonical_request_fingerprint(
        {
            "presentation_id": None,
            "game_id": None,
            "payload": {
                "effective_tags": ["a", "b"],
                "effective_category": None,
                "effective_query": "Q",
                "decision": "edit",
            },
            "case_id": "c1",
            "campaign_id": "goldcamp_" + ("a" * 32),
            "kind": "question_check",
        }
    )
    assert a == b and a.startswith("reqfp_")
    c = canonical_request_fingerprint(
        {
            "kind": "question_check",
            "campaign_id": "goldcamp_" + ("a" * 32),
            "case_id": "c1",
            "payload": {"decision": "accept"},
            "game_id": None,
            "presentation_id": None,
        }
    )
    assert c != a
    d = canonical_request_fingerprint(
        {
            "kind": "question_check",
            "campaign_id": "goldcamp_" + ("a" * 32),
            "case_id": "c1",
            "payload": {
                "decision": "edit",
                "effective_query": "Q",
                "effective_category": None,
                "effective_tags": ["a", "b"],
            },
            "game_id": "g",
            "presentation_id": None,
        }
    )
    assert d != a


# --- H/I. CONTRIBUTION ---


def test_contribution_scoring_and_finalized_boundary(tmp_path: Path) -> None:
    settings, store, campaign, mut, abs_task_a = _ready_with_hard_call(tmp_path)

    live = mut.contribution(campaign.campaign_id)
    assert live.contract == CONTRIBUTION_CONTRACT
    assert live.gold_finalized == 0
    assert live.coverage_fraction is None
    assert live.total_question_tasks == 1
    assert live.total_score == 0

    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc",
    )
    c1 = mut.contribution(campaign.campaign_id)
    assert c1.questions_reviewed == 1
    assert c1.total_score == 5
    assert c1.total_active_absolute_tasks == 2
    assert c1.completed_active_absolute_tasks == 0
    assert c1.coverage_fraction == 0.0

    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=2,
        idempotency_key="abs_a",
    )
    c2 = mut.contribution(campaign.campaign_id)
    assert c2.expert_judgments == 1
    assert c2.hard_calls_resolved == 1
    assert abs_task_a in {
        t.task_id for t in mut.project_tasks(campaign.campaign_id)
    }
    assert c2.total_score == 5 + 1 + 5

    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        relevance=0,
        idempotency_key="abs_b",
    )
    c3 = mut.contribution(campaign.campaign_id)
    assert c3.cases_completed == 1
    assert c3.expert_judgments == 2
    assert c3.total_score == 5 + 2 + 10 + 5
    assert c3.coverage_fraction == 1.0

    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=1,
        idempotency_key="abs_a_corr",
    )
    c4 = mut.contribution(campaign.campaign_id)
    assert c4.expert_judgments == 2
    assert c4.total_score == c3.total_score

    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={
            "decision": "edit",
            "effective_query": "Changed query",
            "effective_category": None,
            "effective_tags": [],
        },
        idempotency_key="qc_chg",
    )
    c5 = mut.contribution(campaign.campaign_id)
    assert c5.expert_judgments == 0
    assert c5.hard_calls_resolved == 0
    assert c5.cases_completed == 0
    assert c5.questions_reviewed == 1
    assert c5.total_score == 5

    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=2,
        idempotency_key="abs_a_re",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        relevance=0,
        idempotency_key="abs_b_re",
    )
    c6 = mut.contribution(campaign.campaign_id)
    assert c6.expert_judgments == 2
    assert c6.hard_calls_resolved == 1
    assert c6.cases_completed == 1

    before = c6.total_score
    mut.submit_auxiliary_preference(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        preferred_chunk_id=CHUNK_A,
        other_chunk_id=CHUNK_B,
        idempotency_key="aux1",
    )
    assert mut.contribution(campaign.campaign_id).total_score == before

    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "reject"},
        idempotency_key="qc_rej",
    )
    c7 = mut.contribution(campaign.campaign_id)
    assert c7.questions_reviewed == 1
    assert c7.cases_completed == 0
    assert c7.expert_judgments == 0
    assert c7.total_active_absolute_tasks == 0
    assert c7.coverage_fraction is None
    assert c7.total_score == 5

    state = mut.load_effective_state(campaign.campaign_id)
    hard = mut.load_hard_calls(campaign.campaign_id)
    one = project_contribution(
        state, hard_calls=hard, finalized_case_ids=[CASE_ID]
    )
    assert one.gold_finalized == 1
    assert one.total_score == 5 + 15
    dup = project_contribution(
        state, hard_calls=hard, finalized_case_ids=[CASE_ID, CASE_ID]
    )
    assert dup.gold_finalized == 1
    with pytest.raises(GoldLabError) as exc:
        project_contribution(
            state, hard_calls=hard, finalized_case_ids=["unknown_case"]
        )
    assert exc.value.reason == "contribution_unknown_finalized_case"
    assert mut.contribution(campaign.campaign_id).gold_finalized == 0
    assert not any(p.is_file() for p in datasets_root(settings).rglob("*"))
    assert not any(p.is_file() for p in registrations_root(settings).rglob("*"))
    del store


def test_all_zero_map_gets_case_complete(tmp_path: Path) -> None:
    _, _, campaign, mut = _ready(tmp_path)
    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=0,
        idempotency_key="a",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_B,
        relevance=0,
        idempotency_key="b",
    )
    c = mut.contribution(campaign.campaign_id)
    assert c.cases_completed == 1
    assert c.total_score == 5 + 2 + 10


def test_zero_candidate_no_case_complete(tmp_path: Path) -> None:
    settings, store, campaign, _registry = _ready_campaign(tmp_path)
    mut = GoldLabMutationService(settings, store=store)
    c = mut.contribution(campaign.campaign_id)
    assert c.total_question_tasks == 1
    assert c.cases_completed == 0
    assert c.coverage_fraction is None


# --- J. BLIND VIEW ---


def test_blind_task_view_excludes_leakage(tmp_path: Path) -> None:
    _, _, campaign, mut = _ready(tmp_path)
    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc",
    )
    views = mut.blind_task_views(campaign.campaign_id)
    assert views
    forbidden = {
        "retrieval_hits",
        "rank",
        "score",
        "model_judgments",
        "prelabel_summary",
        "prelabel_provenance",
        "reason_code",
        "hard_call_reason_code",
        "model_confidence",
        "model_agreement",
    }
    for view in views:
        payload = view.to_dict()
        assert forbidden.isdisjoint(payload.keys())
        blob = json.dumps(payload)
        for key in forbidden:
            assert key not in blob


# --- K. NON-SCOPE ---


def test_nonscope_no_api_ui_export_registration(tmp_path: Path) -> None:
    settings, _, campaign, mut = _ready(tmp_path)
    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc",
    )
    proj = projection_dir(settings, campaign.campaign_id)
    assert not (proj / "authoring_run.json").exists()
    assert not any(p.is_file() for p in datasets_root(settings).rglob("*"))
    assert not any(p.is_file() for p in registrations_root(settings).rglob("*"))
    from offline_rag.app import gold_lab as gl

    assert not hasattr(gl, "router")
    assert IDEMPOTENCY_SCHEMA == "offline-rag-gold-idempotency-v1"
    assert normalize_idempotency_key("  x  ") == "x"
    assert idempotency_entry_filename("x").startswith("idem_")
    assert hard_calls_path(settings, campaign.campaign_id).is_file()
    assert idempotency_dir(settings, campaign.campaign_id).is_dir()
    assert (REPO_ROOT / "src" / "offline_rag" / "evaluation" / "gold.py").is_file()


def test_idempotency_catalog_path_deterministic() -> None:
    key = normalize_idempotency_key("abc")
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    assert idempotency_entry_filename(key) == f"idem_{digest}.json"


def test_cross_basis_supersession_fails(tmp_path: Path) -> None:
    settings, store, campaign, mut = _ready(tmp_path)
    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={"decision": "accept"},
        idempotency_key="qc1",
    )
    a1 = mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=2,
        idempotency_key="a1",
    )
    mut.submit_question_check(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        payload={
            "decision": "edit",
            "effective_query": "New query basis",
            "effective_category": None,
            "effective_tags": [],
        },
        idempotency_key="qc2",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign.campaign_id,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        relevance=0,
        idempotency_key="a2_new_basis",
    )
    ledger = GoldLabLedger(settings, store=store)
    ledger.append(
        campaign.campaign_id,
        record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
        case_id=CASE_ID,
        candidate_chunk_id=CHUNK_A,
        payload={"relevance": 1},
        idempotency_key="cross_basis",
        request_fingerprint=canonical_request_fingerprint({"x": 1}),
        query_fingerprint=query_fingerprint("New query basis"),
        supersedes_judgment_id=a1.record.judgment_id,
    )
    with pytest.raises(GoldLabError) as exc:
        mut.load_effective_state(campaign.campaign_id)
    assert exc.value.reason == "effective_state_cross_basis_supersession"


def test_two_finalized_cases_score(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id)
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Two",
        project_type=GoldProjectType.BENCHMARK,
    )
    cases = [
        SilverCase(
            draft_case_id="c1",
            proposed_query="Q1",
            candidates=[PoolCandidate(chunk_id=CHUNK_A, document_id=DOC_ID)],
        ),
        SilverCase(
            draft_case_id="c2",
            proposed_query="Q2",
            candidates=[PoolCandidate(chunk_id=CHUNK_B, document_id=DOC_ID)],
        ),
    ]
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    campaign = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(cases=cases, authoring_run_id="authorrun_16fb_two"),
        selection_policy=_policy(),
    )
    mut = GoldLabMutationService(settings, store=store)
    state = mut.load_effective_state(campaign.campaign_id)
    hard = mut.load_hard_calls(campaign.campaign_id)
    proj = project_contribution(
        state, hard_calls=hard, finalized_case_ids=["c1", "c2"]
    )
    assert proj.gold_finalized == 2
    assert proj.total_score == 30
