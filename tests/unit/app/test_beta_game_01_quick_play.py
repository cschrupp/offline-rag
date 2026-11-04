"""BETA-GAME-01 Quick Play orchestration regressions."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

_APP_TEST_DIR = Path(__file__).resolve().parent
if str(_APP_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_TEST_DIR))

from test_slice16f_d_gold_lab_api import (
    _active_workspace,
    _baseline,
    _FakeQdrant,
    _integrity_settings,
    _publish_integrity,
    _runtime,
    _write_baseline,
)

from offline_rag.app.gold_lab.quick_play import QuickPlayService
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.runtime import RuntimeState
from offline_rag.app.workspace.models import (
    ManagedOperationKind,
    ManagedOperationStatus,
)

QUESTION_CHECK_GAME = "goldgame_question_check_v1"
QUESTION_CHECK_PRESENTATION = "goldpres_question_check_source_panel_v1"
RAPID_FIRE_GAME = "goldgame_rapid_fire_v1"
RAPID_FIRE_PRESENTATION = "goldpres_rapid_fire_single_card_v1"


def _runtime_fixture(tmp_path: Path, *, with_baseline: bool = True):
    settings = _integrity_settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, _ = _publish_integrity(settings)
    qdrant = _FakeQdrant()
    qdrant.counts["col_16fd"] = 2
    runtime = _runtime(settings, qdrant=qdrant)
    workspace = _active_workspace(settings, snapshot_id)
    if with_baseline:
        _write_baseline(
            settings,
            _baseline(corpus_id=corpus_id, chunk_set_id=chunk_set_id),
        )
    runtime.publication.qdrant = qdrant
    return runtime, workspace, chunk_set_id


def test_quick_play_concurrent_setup_reuses_one_improvement_campaign(
    tmp_path: Path,
) -> None:
    runtime, workspace, chunk_set_id = _runtime_fixture(tmp_path)
    workspace_id = workspace.workspace_id
    quick_play = QuickPlayService(runtime)
    initial = quick_play.get_state(workspace_id)
    assert initial["status"] == "needs_generation"

    # A reusable pristine baseline exists. Concurrent setup requests must
    # converge on one deterministic project and campaign.
    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(
            pool.map(
                lambda key: quick_play.prepare(
                    workspace_id, action="start", idempotency_key=key
                ),
                ("quick-play-tab-a", "quick-play-tab-b"),
            )
        )

    assert {state["status"] for state in states} == {"playable"}
    assert len({state["project_id"] for state in states}) == 1
    assert len({state["campaign_id"] for state in states}) == 1

    state = quick_play.get_state(workspace_id)
    assert state["status"] == "playable"
    assert state["question_check_pending"] == 1
    assert state["rapid_fire_pending"] == 0
    assert state["next_game"] == "question_check"
    assert [game["game_id"] for game in state["available_games"]] == ["question_check"]

    campaign = GoldLabStore(runtime.settings).get_campaign(state["campaign_id"])
    assert campaign.selection_policy.selection_policy_id == "quick_play_improvement_v1"

    # The existing Question Check mutation activates Rapid Fire only after
    # the question receives its accepted expert judgment.
    tasks = runtime.gold_lab.list_tasks(state["campaign_id"])["tasks"]
    question_task = next(
        task for task in tasks if task["task_kind"] == "question_check"
    )
    runtime.gold_lab.submit_question_check(
        campaign_id=state["campaign_id"],
        task_id=question_task["task_id"],
        idempotency_key="quick-play-question-check-1",
        payload={"decision": "accept"},
        game_id=QUESTION_CHECK_GAME,
        presentation_id=QUESTION_CHECK_PRESENTATION,
    )

    state = quick_play.get_state(workspace_id)
    assert state["question_check_pending"] == 0
    assert state["rapid_fire_pending"] == 2
    assert state["next_game"] == "rapid_fire"
    assert [game["game_id"] for game in state["available_games"]] == ["rapid_fire"]

    tasks = runtime.gold_lab.list_tasks(state["campaign_id"])["tasks"]
    relevance_task = next(
        task
        for task in tasks
        if task["task_kind"] == "absolute_relevance" and task["active"]
    )
    runtime.gold_lab.submit_relevance(
        campaign_id=state["campaign_id"],
        task_id=relevance_task["task_id"],
        idempotency_key="quick-play-relevance-1",
        relevance=2,
        game_id=RAPID_FIRE_GAME,
        presentation_id=RAPID_FIRE_PRESENTATION,
    )
    state = quick_play.get_state(workspace_id)
    assert state["rapid_fire_pending"] == 1

    remaining_task = next(
        task
        for task in runtime.gold_lab.list_tasks(state["campaign_id"])["tasks"]
        if task["task_kind"] == "absolute_relevance"
        and task["state"] == "pending"
        and task["active"]
    )
    runtime.gold_lab.submit_relevance(
        campaign_id=state["campaign_id"],
        task_id=remaining_task["task_id"],
        idempotency_key="quick-play-relevance-2",
        relevance=1,
        game_id=RAPID_FIRE_GAME,
        presentation_id=RAPID_FIRE_PRESENTATION,
    )
    assert quick_play.get_state(workspace_id)["status"] == "complete"

    # Replenishment remains visible while a new baseline is being generated;
    # the previously completed campaign and its judgments remain untouched.
    old_campaign_id = state["campaign_id"]
    pending_operation = SimpleNamespace(
        operation_id="wop_quickplay_replenish",
        kind=ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP,
        workspace_id=workspace_id,
        bootstrap_authority=SimpleNamespace(
            project_id=state["project_id"],
            authoring_run_id="authorrun_16fd_replenished",
        ),
        status=ManagedOperationStatus.PENDING,
        created_at=datetime.now(UTC),
        progress_stage=None,
        failure_summary=None,
        result=None,
    )
    runtime_ops = quick_play.operations
    operations: list[SimpleNamespace] = []
    runtime_ops.list_for_workspace = lambda _workspace_id: operations
    started: list[int] = []

    def start_replenishment(**kwargs):
        started.append(kwargs["proposal_count"])
        operations.append(pending_operation)
        return pending_operation

    quick_play.gold.start_baseline_bootstrap = start_replenishment
    replenished = quick_play.prepare(
        workspace_id,
        action="replenish",
        idempotency_key="quick-play-replenish-1",
    )
    assert replenished["status"] == "generating"
    assert quick_play.get_state(workspace_id)["status"] == "generating"

    _write_baseline(
        runtime.settings,
        _baseline(
            corpus_id=runtime.publication.resolve_snapshot(
                workspace.backing_corpus_name, workspace.current_snapshot_id
            ).identity.corpus_id,
            chunk_set_id=chunk_set_id,
            authoring_run_id="authorrun_16fd_replenished",
        ),
    )
    pending_operation.status = ManagedOperationStatus.SUCCEEDED
    assert quick_play.get_state(workspace_id)["status"] == "campaign_ready"
    replenished = quick_play.prepare(
        workspace_id,
        action="replenish",
        idempotency_key="quick-play-replenish-1",
    )
    assert replenished["status"] == "playable"
    assert replenished["campaign_id"] != old_campaign_id
    assert started == [2]
    assert (
        GoldLabStore(runtime.settings).get_campaign(old_campaign_id).campaign_id
        == old_campaign_id
    )


def test_quick_play_new_snapshot_identity_does_not_rebind_old_campaign(
    tmp_path: Path,
) -> None:
    runtime, workspace, chunk_set_id = _runtime_fixture(tmp_path)
    workspace_id = workspace.workspace_id
    quick_play = QuickPlayService(runtime)
    state = quick_play.prepare(
        workspace_id,
        action="start",
        idempotency_key="quick-play-identity-base",
    )
    old_campaign_id = state["campaign_id"]
    original_resolve = runtime.publication.resolve_snapshot

    def changed_snapshot(corpus_name: str, snapshot_id: str):
        snapshot = original_resolve(corpus_name, snapshot_id)
        return SimpleNamespace(
            identity=SimpleNamespace(
                corpus_id="corpus_changed_publication",
                chunk_set_id=chunk_set_id,
                corpus_manifest=snapshot.identity.corpus_manifest,
            )
        )

    runtime.publication.resolve_snapshot = changed_snapshot
    changed = quick_play.get_state(workspace_id)

    assert changed["status"] == "needs_generation"
    assert changed["project_id"] is None
    old_campaign = GoldLabStore(runtime.settings).get_campaign(old_campaign_id)
    assert old_campaign.snapshot_id == workspace.current_snapshot_id
    assert old_campaign.chunk_set_id == chunk_set_id


@pytest.mark.parametrize(
    ("population_size", "expected_count"),
    [(12, 12), (20, 20), (24, 20)],
)
def test_quick_play_generation_count_is_bounded_by_population(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    population_size: int,
    expected_count: int,
) -> None:
    import offline_rag.app.gold_lab.quick_play as quick_play_module

    runtime, workspace, _ = _runtime_fixture(tmp_path, with_baseline=False)
    loaded_snapshots: list[str] = []

    def load_chunks(*_args, **kwargs):
        loaded_snapshots.append(kwargs.get("chunk_set_id", "fixture"))
        return SimpleNamespace(chunks=[object() for _ in range(population_size)])

    monkeypatch.setattr(
        quick_play_module,
        "load_chunk_set_snapshot",
        load_chunks,
    )
    monkeypatch.setattr(
        quick_play_module, "build_eligible_population", lambda chunks: chunks
    )
    service = QuickPlayService(runtime)
    identity, blocked = service._identity(workspace.workspace_id)
    assert identity is not None and blocked is None
    assert identity.proposal_count == expected_count

    requested_counts: list[int] = []
    operation = SimpleNamespace(
        operation_id="wop_quickplay_capacity",
        status=ManagedOperationStatus.PENDING,
        progress_stage=None,
        failure_summary=None,
        result=None,
    )

    def start_baseline_bootstrap(**kwargs):
        requested_counts.append(kwargs["proposal_count"])
        return operation

    service.gold.start_baseline_bootstrap = start_baseline_bootstrap
    state = service.prepare(
        workspace.workspace_id,
        action="start",
        idempotency_key=f"quick-play-capacity-{population_size}",
    )

    assert state["status"] == "generating"
    assert requested_counts == [expected_count]
    assert len(loaded_snapshots) == 1

    # A different immutable snapshot identity must not reuse the old count.
    service._eligible_population_count(
        workspace_id=workspace.workspace_id,
        snapshot_id="snap_other_quick_play",
        corpus_name=identity.corpus_name,
        corpus_id=identity.corpus_id,
        chunk_set_id=identity.chunk_set_id,
        corpus_manifest_name="manifest_other_quick_play.json",
    )
    assert len(loaded_snapshots) == 2


def test_quick_play_empty_eligible_population_has_clear_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import offline_rag.app.gold_lab.quick_play as quick_play_module

    runtime, workspace, _ = _runtime_fixture(tmp_path, with_baseline=False)
    monkeypatch.setattr(
        quick_play_module,
        "load_chunk_set_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(chunks=[]),
    )
    service = QuickPlayService(runtime)

    state = service.get_state(workspace.workspace_id)

    assert state["status"] == "empty_population"
    assert state["reason"] == "no_eligible_source_chunks"
    assert state["project_id"] is None


def test_quick_play_failed_generation_is_visible_and_retry_is_explicit(
    tmp_path: Path,
) -> None:
    runtime, workspace, _ = _runtime_fixture(tmp_path, with_baseline=False)
    service = QuickPlayService(runtime)
    identity, blocked = service._identity(workspace.workspace_id)
    assert identity is not None and blocked is None
    project = service._ensure_project(identity)
    failed = SimpleNamespace(
        operation_id="wop_failedquickplay",
        kind=ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP,
        workspace_id=workspace.workspace_id,
        bootstrap_authority=SimpleNamespace(project_id=project.project_id),
        status=ManagedOperationStatus.FAILED,
        created_at=datetime.now(UTC),
        progress_stage=None,
        failure_summary="The configured authoring endpoint was unreachable.",
        result=None,
    )
    service.operations.list_for_workspace = lambda _workspace_id: [failed]

    before_retry = service.get_state(workspace.workspace_id)
    assert before_retry["status"] == "generation_failed"
    assert before_retry["operation"]["operation_id"] == failed.operation_id

    replacement = SimpleNamespace(
        operation_id="wop_retriedquickplay",
        status=ManagedOperationStatus.PENDING,
        progress_stage=None,
        failure_summary=None,
        result=None,
    )
    calls: list[str] = []

    def start_baseline_bootstrap(**kwargs):
        calls.append(kwargs["idempotency_key"])
        return replacement

    service.gold.start_baseline_bootstrap = start_baseline_bootstrap
    retried = service.prepare(
        workspace.workspace_id,
        action="start",
        idempotency_key="quick-play-explicit-retry",
    )

    assert calls == ["quick-play-explicit-retry"]
    assert retried["status"] == "generating"
    assert retried["operation"]["operation_id"] == replacement.operation_id


def test_quick_play_additive_api_reconciles_existing_baseline(
    tmp_path: Path,
) -> None:
    from offline_rag.api.gold_lab import (
        QuickPlayPrepareRequest,
        prepare_quick_play,
        quick_play_state,
    )

    runtime, workspace, _ = _runtime_fixture(tmp_path)
    runtime.state = RuntimeState.READY
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(runtime=runtime))
    )
    initial = quick_play_state(request, workspace.workspace_id)
    prepared = prepare_quick_play(
        request,
        workspace.workspace_id,
        QuickPlayPrepareRequest(action="start"),
        idempotency_key="quick-play-api-start",
    )
    assert initial["status"] == "needs_generation"
    assert prepared["status"] == "playable"
    assert prepared["available_games"] == [
        {
            "game_id": "question_check",
            "label": "Question Check",
            "pending_count": 1,
        }
    ]


def test_quick_play_prepare_exposes_durable_operation_location(
    tmp_path: Path, monkeypatch
) -> None:
    from fastapi.responses import JSONResponse

    from offline_rag.api.gold_lab import QuickPlayPrepareRequest, prepare_quick_play

    runtime, workspace, _ = _runtime_fixture(tmp_path)
    runtime.state = RuntimeState.READY
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(runtime=runtime))
    )
    result = {
        "status": "generating",
        "operation": {"operation_id": "wop_quickplayop"},
    }
    monkeypatch.setattr(QuickPlayService, "prepare", lambda *args, **kwargs: result)

    response = prepare_quick_play(
        request,
        workspace.workspace_id,
        QuickPlayPrepareRequest(action="start"),
        idempotency_key="quick-play-api-operation",
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 202
    assert response.headers["Location"] == "/v1/operations/wop_quickplayop"
