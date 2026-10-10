"""Slice 16F-D — Gold Lab application API data plane."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_APP_TEST_DIR = Path(__file__).resolve().parent
if str(_APP_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_TEST_DIR))

from test_slice16f_d_gold_lab_historical_source import (
    CHUNK_A,
    CHUNK_B,
    CORPUS_NAME,
    DOC_ID,
    _FakeQdrant,
    _publish_integrity,
)
from test_slice16f_d_gold_lab_historical_source import (
    _settings as _integrity_settings,
)

from offline_rag.api.app import create_app
from offline_rag.app.errors import ErrorCode, SafeErrorDetails
from offline_rag.app.gold_lab.application import (
    GOLD_LAB_REASON_TO_ERROR_CODE,
    translate_gold_lab_error,
)
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.models import GoldProjectType
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.workspace.models import (
    SourceVersionRecord,
    WorkspaceStatus,
    new_empty_workspace,
    new_source_id,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase, SourceSeed
from offline_rag.gold_authoring.persist import (
    default_authoring_run_path,
    write_authoring_run,
)
from offline_rag.gold_authoring.pooling_models import PoolCandidate
from offline_rag.gold_authoring.review_models import HumanReview, HumanReviewStatus

EXPECTED_ROUTES = {
    ("GET", "/v1/gold-lab/projects"),
    ("POST", "/v1/gold-lab/projects"),
    ("GET", "/v1/gold-lab/projects/{project_id}"),
    ("POST", "/v1/gold-lab/projects/{project_id}/archive"),
    ("GET", "/v1/gold-lab/projects/{project_id}/baselines"),
    ("GET", "/v1/gold-lab/projects/{project_id}/campaigns"),
    ("POST", "/v1/gold-lab/projects/{project_id}/campaigns"),
    ("GET", "/v1/gold-lab/campaigns/{campaign_id}"),
    ("POST", "/v1/gold-lab/campaigns/{campaign_id}/close"),
    ("GET", "/v1/gold-lab/campaigns/{campaign_id}/tasks"),
    ("GET", "/v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}"),
    ("POST", "/v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}/question-check"),
    ("POST", "/v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}/relevance"),
    ("POST", "/v1/gold-lab/campaigns/{campaign_id}/preferences"),
    ("GET", "/v1/gold-lab/campaigns/{campaign_id}/contribution"),
    ("POST", "/v1/gold-lab/campaigns/{campaign_id}/export"),
    ("GET", "/v1/gold-lab/campaigns/{campaign_id}/registrations"),
    (
        "GET",
        "/v1/gold-lab/campaigns/{campaign_id}/registrations/{dataset_id}/training-package",
    ),
}


class _Closeable:
    def close(self) -> None:
        return None


def _runtime(settings: AppSettings, *, qdrant: _FakeQdrant | None = None) -> ApplicationRuntime:
    embedder = FakeEmbedder(dimension=8, normalize=True)
    q = qdrant or _FakeQdrant()

    def _qdrant(_s: AppSettings) -> _FakeQdrant:
        return q

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=_qdrant,
        ),
    )


def _baseline(
    *,
    corpus_id: str,
    chunk_set_id: str,
    authoring_run_id: str = "authorrun_16fd",
    with_human: bool = False,
    drop_identity: bool = False,
) -> GoldAuthoringRun:
    cases = [
        SilverCase(
            draft_case_id="draft_reviewable",
            proposed_query="What is offline RAG?",
            source_seed=SourceSeed(
                chunk_id=CHUNK_A,
                document_id=DOC_ID,
                document_title="Spec Title",
            ),
            candidates=[
                PoolCandidate(
                    chunk_id=CHUNK_A,
                    document_id=DOC_ID,
                    document_title="Cand A",
                ),
                PoolCandidate(
                    chunk_id=CHUNK_B,
                    document_id=DOC_ID,
                    document_title="Cand B",
                ),
            ],
        ),
        SilverCase(
            draft_case_id="draft_inert",
            proposed_query="ignored",
            candidates=[],
        ),
    ]
    if with_human:
        cases[0] = cases[0].model_copy(
            update={
                "human_review": HumanReview(
                    status=HumanReviewStatus.PENDING,
                    query_override="human altered query",
                )
            }
        )
    return GoldAuthoringRun(
        authoring_run_id=authoring_run_id,
        authorcfg_id="authorcfg_" + ("a" * 64),
        network_policy="localhost_only",
        created_at=datetime.now(tz=UTC),
        corpus_name=None if drop_identity else CORPUS_NAME,
        corpus_id=None if drop_identity else corpus_id,
        chunk_set_id=None if drop_identity else chunk_set_id,
        cases=cases,
    )


def _write_baseline(settings: AppSettings, run: GoldAuthoringRun) -> Path:
    path = default_authoring_run_path(
        settings, corpus_name=CORPUS_NAME, authoring_run_id=run.authoring_run_id
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_authoring_run(path, run)
    return path


def _active_workspace(settings: AppSettings, snapshot_id: str):
    store = WorkspaceStore(settings)
    empty = store.create(
        new_empty_workspace(title="16FD Desk").model_copy(
            update={"backing_corpus_name": CORPUS_NAME}
        )
    )
    active = empty.model_copy(
        update={
            "status": WorkspaceStatus.ACTIVE,
            "current_snapshot_id": snapshot_id,
            "sources": [
                SourceVersionRecord(
                    source_id=new_source_id(),
                    version=1,
                    display_name="spec.pdf",
                    vault_object_id="vobj_" + "c" * 32,
                    created_at=datetime.now(tz=UTC),
                    active_from_revision=1,
                    active_from_snapshot_id=snapshot_id,
                )
            ],
            "revision": 1,
        }
    )
    return store.save(active)


@contextmanager
def _ready_client(tmp_path: Path) -> Iterator[tuple[TestClient, dict]]:
    settings = _integrity_settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, art_id = _publish_integrity(settings)
    q = _FakeQdrant()
    q.counts["col_16fd"] = 2
    runtime = _runtime(settings, qdrant=q)
    ws = _active_workspace(settings, snapshot_id)
    run = _baseline(corpus_id=corpus_id, chunk_set_id=chunk_set_id)
    _write_baseline(settings, run)
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="16FD",
        project_type=GoldProjectType.BENCHMARK,
    )
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        # Campaign create resolves CURRENT snapshot via publication + qdrant.
        runtime.publication.qdrant = q
        yield client, {
            "settings": settings,
            "runtime": runtime,
            "project_id": project.project_id,
            "workspace_id": ws.workspace_id,
            "corpus_id": corpus_id,
            "chunk_set_id": chunk_set_id,
            "snapshot_id": snapshot_id,
            "authoring_run_id": run.authoring_run_id,
            "art_id": art_id,
        }


def test_exact_route_surface() -> None:
    from offline_rag.api.gold_lab import router

    found = set()
    for route in router.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if not path:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            found.add((method, path))
    assert found == EXPECTED_ROUTES


def test_router_before_spa_and_runtime_lazy(tmp_path: Path) -> None:
    settings = _integrity_settings(tmp_path)
    runtime = _runtime(settings)
    assert runtime._gold_lab is None
    first = runtime.gold_lab
    second = runtime.gold_lab
    assert first is second
    assert first.settings is settings
    assert runtime.resources is None
    create_app(runtime=runtime)
    # Included gold router paths (prefix may be on APIRouter).
    from offline_rag.api import gold_lab as gold_mod

    assert any(
        str(getattr(r, "path", "")).endswith("/projects")
        for r in gold_mod.router.routes
    )
    # create_app registers gold router before SPA fallback mount.
    src = Path(create_app.__code__.co_filename).read_text(encoding="utf-8")
    assert src.index("include_router(gold_lab_router)") < src.index(
        "mount_frontend(app)"
    )


def test_error_translator_table_and_unknown() -> None:
    samples = {
        "project_not_found": ErrorCode.GOLD_PROJECT_UNKNOWN,
        "campaign_not_found": ErrorCode.GOLD_CAMPAIGN_UNKNOWN,
        "baseline_missing": ErrorCode.GOLD_STATE_UNAVAILABLE,
        "gold_lab_lease_held": ErrorCode.GOLD_BUSY,
        "idempotency_conflict": ErrorCode.IDEMPOTENCY_CONFLICT,
        "idempotency_catalog_corrupt": ErrorCode.GOLD_STATE_UNAVAILABLE,
        "question_check_edit_not_semantic": ErrorCode.REQUEST_INVALID,
        "effective_state_qc_edit_not_semantic": ErrorCode.GOLD_STATE_UNAVAILABLE,
        "task_identity_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
        "registration_unknown_exported_case": ErrorCode.GOLD_STATE_UNAVAILABLE,
        "gold_finalize_failed": ErrorCode.GOLD_STATE_UNAVAILABLE,
        "idempotency_command_kind_invalid": ErrorCode.INTERNAL_ERROR,
        "ledger_case_not_found": ErrorCode.GOLD_STATE_UNAVAILABLE,
        "hard_call_designation_id_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    }
    for reason, code in samples.items():
        err = translate_gold_lab_error(GoldLabError(reason, "secret prose PATH=/x"))
        assert err.code is code
        assert err.message != "secret prose PATH=/x"
        assert err.details is not None
        assert err.details["reason"] == reason
    unknown = translate_gold_lab_error(GoldLabError("future_reason_xyz"))
    assert unknown.code is ErrorCode.INTERNAL_ERROR
    assert unknown.details["reason"] == "gold_lab_unmapped_error"
    assert len(GOLD_LAB_REASON_TO_ERROR_CODE) >= 160


def test_project_campaign_task_mutations_export(tmp_path: Path) -> None:
    with _ready_client(tmp_path) as (client, ctx):
        pid = ctx["project_id"]
        # project get / list
        r = client.get("/v1/gold-lab/projects")
        assert r.status_code == 200
        assert r.json()["projects"][0]["project_id"] == pid
        assert set(r.json()["projects"][0]) == {
            "project_id",
            "workspace_id",
            "title",
            "description",
            "project_type",
            "status",
            "created_at",
        }
        assert not any(
            "/" in str(v) and "data" in str(v)
            for v in r.json()["projects"][0].values()
        )

        r = client.get(f"/v1/gold-lab/projects/{pid}/baselines")
        assert r.status_code == 200
        assert len(r.json()["baselines"]) == 1
        assert r.json()["baselines"][0]["authoring_run_id"] == ctx["authoring_run_id"]

        r = client.post(
            f"/v1/gold-lab/projects/{pid}/campaigns",
            json={
                "baseline_authoring_run_id": ctx["authoring_run_id"],
                "selection_policy_id": "default",
            },
        )
        assert r.status_code == 201, r.text
        campaign = r.json()
        cid = campaign["campaign_id"]
        assert campaign["project_type"] == "benchmark"
        assert campaign["snapshot_id"] == ctx["snapshot_id"]
        assert set(campaign) == {
            "campaign_id",
            "project_id",
            "workspace_id",
            "project_type",
            "snapshot_id",
            "chunk_set_id",
            "corpus_id",
            "corpus_name",
            "baseline_authoring_run_id",
            "workspace_revision_at_creation",
            "status",
            "created_at",
        }

        r = client.get(f"/v1/gold-lab/campaigns/{cid}/tasks")
        assert r.status_code == 200
        tasks = r.json()["tasks"]
        assert tasks[0]["task_kind"] == "question_check"
        assert tasks[0]["case_id"] == "draft_reviewable"
        assert not any(t["case_id"] == "draft_inert" for t in tasks)
        forbidden = {"rank", "score", "model_judgments", "reason_code", "prelabel"}
        for t in tasks:
            assert forbidden.isdisjoint(t)

        qc_id = tasks[0]["task_id"]
        r = client.get(f"/v1/gold-lab/campaigns/{cid}/tasks/{qc_id}")
        assert r.status_code == 200, r.text
        detail = r.json()
        assert detail["presentation"]["kind"] == "question_check"
        assert detail["presentation"]["source"]["chunk_id"] == CHUNK_A
        assert detail["presentation"]["source"]["document_title"] == "Spec Title"
        assert detail["presentation"]["source"]["text"]
        assert "rank" not in detail["presentation"]["source"]

        # accept without effective fields
        r = client.post(
            f"/v1/gold-lab/campaigns/{cid}/tasks/{qc_id}/question-check",
            headers={"Idempotency-Key": "qc1"},
            json={"decision": "accept"},
        )
        assert r.status_code == 200
        assert r.json()["replayed"] is False
        receipt_keys = {
            "campaign_id",
            "record_id",
            "judgment_id",
            "task_id",
            "record_type",
            "sequence",
            "created_at",
            "replayed",
        }
        assert set(r.json()) == receipt_keys

        # exact replay
        r2 = client.post(
            f"/v1/gold-lab/campaigns/{cid}/tasks/{qc_id}/question-check",
            headers={"Idempotency-Key": "qc1"},
            json={"decision": "accept"},
        )
        assert r2.status_code == 200
        assert r2.json()["replayed"] is True

        # accept + explicit null effective field invalid
        r = client.post(
            f"/v1/gold-lab/campaigns/{cid}/tasks/{qc_id}/question-check",
            headers={"Idempotency-Key": "qc_bad"},
            json={"decision": "accept", "effective_query": None},
        )
        assert r.status_code == 422

        # missing idempotency
        r = client.post(
            f"/v1/gold-lab/campaigns/{cid}/tasks/{qc_id}/question-check",
            json={"decision": "accept"},
        )
        assert r.status_code == 422

        # absolute relevance after accept
        abs_tasks = [
            t
            for t in client.get(f"/v1/gold-lab/campaigns/{cid}/tasks").json()["tasks"]
            if t["task_kind"] == "absolute_relevance" and t["active"]
        ]
        assert abs_tasks
        abs_id = abs_tasks[0]["task_id"]
        r = client.get(f"/v1/gold-lab/campaigns/{cid}/tasks/{abs_id}")
        assert r.status_code == 200
        assert r.json()["presentation"]["kind"] == "absolute_relevance"
        assert r.json()["presentation"]["candidate"]["chunk_id"] in {CHUNK_A, CHUNK_B}

        r = client.post(
            f"/v1/gold-lab/campaigns/{cid}/tasks/{abs_id}/relevance",
            headers={"Idempotency-Key": "rel1"},
            json={"relevance": True},
        )
        assert r.status_code == 422

        # Complete both active absolute tasks for positive export eligibility.
        for index, task in enumerate(abs_tasks):
            r = client.post(
                f"/v1/gold-lab/campaigns/{cid}/tasks/{task['task_id']}/relevance",
                headers={"Idempotency-Key": f"rel_{index}"},
                json={"relevance": 2 if index == 0 else 0},
            )
            assert r.status_code == 200, r.text

        r = client.post(
            f"/v1/gold-lab/campaigns/{cid}/preferences",
            headers={"Idempotency-Key": "pref1"},
            json={
                "case_id": "draft_reviewable",
                "preferred_chunk_id": CHUNK_A,
                "other_chunk_id": CHUNK_B,
            },
        )
        assert r.status_code == 200

        r = client.get(f"/v1/gold-lab/campaigns/{cid}/contribution")
        assert r.status_code == 200
        assert r.json()["contract"] == "gold-contribution-v1"
        assert "leaderboard" not in r.json()

        r = client.post(f"/v1/gold-lab/campaigns/{cid}/export")
        assert r.status_code == 201, r.text
        export_body = r.json()
        assert export_body["dataset_path"].startswith("datasets/")
        assert ".." not in export_body["dataset_path"]
        r = client.post(f"/v1/gold-lab/campaigns/{cid}/export")
        assert r.status_code == 200
        assert r.json()["registration_replayed"] is True

        r = client.get(f"/v1/gold-lab/campaigns/{cid}/registrations")
        assert r.status_code == 200
        assert len(r.json()["registrations"]) == 1

        r = client.post(f"/v1/gold-lab/campaigns/{cid}/close")
        assert r.status_code == 200
        r = client.post(f"/v1/gold-lab/campaigns/{cid}/close")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "gold_conflict"

        # replay after close
        r = client.post(
            f"/v1/gold-lab/campaigns/{cid}/tasks/{qc_id}/question-check",
            headers={"Idempotency-Key": "qc1"},
            json={"decision": "accept"},
        )
        assert r.status_code == 200
        assert r.json()["replayed"] is True

        # new key after close
        r = client.post(
            f"/v1/gold-lab/campaigns/{cid}/tasks/{qc_id}/question-check",
            headers={"Idempotency-Key": "qc_after_close"},
            json={"decision": "reject"},
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "gold_conflict"

        r = client.post(f"/v1/gold-lab/projects/{pid}/archive")
        assert r.status_code == 200
        r = client.post(f"/v1/gold-lab/projects/{pid}/archive")
        assert r.status_code == 409


def test_baseline_class_d_and_discovery_suppress(tmp_path: Path) -> None:
    settings = _integrity_settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, _ = _publish_integrity(settings)
    q = _FakeQdrant()
    q.counts["col_16fd"] = 2
    runtime = _runtime(settings, qdrant=q)
    ws = _active_workspace(settings, snapshot_id)
    good = _baseline(corpus_id=corpus_id, chunk_set_id=chunk_set_id)
    _write_baseline(settings, good)
    human = _baseline(
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        authoring_run_id="authorrun_human",
        with_human=True,
    )
    _write_baseline(settings, human)
    missing = _baseline(
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        authoring_run_id="authorrun_noid",
        drop_identity=True,
    )
    path = default_authoring_run_path(
        settings, corpus_name=CORPUS_NAME, authoring_run_id=missing.authoring_run_id
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_authoring_run(path, missing)

    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="D",
        project_type=GoldProjectType.BENCHMARK,
    )
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        runtime.publication.qdrant = q
        r = client.get(f"/v1/gold-lab/projects/{project.project_id}/baselines")
        assert r.status_code == 200
        ids = {b["authoring_run_id"] for b in r.json()["baselines"]}
        assert ids == {"authorrun_16fd"}

        r = client.post(
            f"/v1/gold-lab/projects/{project.project_id}/campaigns",
            json={
                "baseline_authoring_run_id": "authorrun_human",
                "selection_policy_id": "default",
            },
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "gold_conflict"
        assert r.json()["details"]["reason"] == "baseline_human_state_present"

        r = client.post(
            f"/v1/gold-lab/projects/{project.project_id}/campaigns",
            json={
                "baseline_authoring_run_id": "authorrun_noid",
                "selection_policy_id": "default",
            },
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "gold_conflict"
        assert r.json()["details"]["reason"] == "baseline_identity_missing"

        r = client.post(
            f"/v1/gold-lab/projects/{project.project_id}/campaigns",
            json={
                "baseline_authoring_run_id": "authorrun_absent",
                "selection_policy_id": "default",
            },
        )
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "gold_baseline_unknown"


def test_noop_edit_and_kind_mismatch(tmp_path: Path) -> None:
    with _ready_client(tmp_path) as (client, ctx):
        pid = ctx["project_id"]
        r = client.post(
            f"/v1/gold-lab/projects/{pid}/campaigns",
            json={
                "baseline_authoring_run_id": ctx["authoring_run_id"],
                "selection_policy_id": "default",
            },
        )
        cid = r.json()["campaign_id"]
        tasks = client.get(f"/v1/gold-lab/campaigns/{cid}/tasks").json()["tasks"]
        qc = next(t for t in tasks if t["task_kind"] == "question_check")
        abs_pending = next(
            t for t in tasks if t["task_kind"] == "absolute_relevance"
        )
        # kind mismatch
        r = client.post(
            f"/v1/gold-lab/campaigns/{cid}/tasks/{abs_pending['task_id']}/question-check",
            headers={"Idempotency-Key": "km"},
            json={"decision": "accept"},
        )
        assert r.status_code == 422
        assert r.json()["details"]["reason"] == "gold_task_kind_mismatch"

        # accept then no-op edit
        client.post(
            f"/v1/gold-lab/campaigns/{cid}/tasks/{qc['task_id']}/question-check",
            headers={"Idempotency-Key": "a1"},
            json={"decision": "accept"},
        )
        r = client.post(
            f"/v1/gold-lab/campaigns/{cid}/tasks/{qc['task_id']}/question-check",
            headers={"Idempotency-Key": "edit_noop"},
            json={
                "decision": "edit",
                "effective_query": "What is offline RAG?",
                "effective_category": None,
                "effective_tags": [],
            },
        )
        assert r.status_code == 422
        assert r.json()["details"]["reason"] == "question_check_edit_not_semantic"


def test_safe_error_details_gold_ids() -> None:
    details = SafeErrorDetails(
        project_id="goldproj_" + ("a" * 32),
        campaign_id="goldcamp_" + ("b" * 32),
        task_id="goldtask_" + ("c" * 64),
        dataset_id="gold_" + ("d" * 64),
        case_id="draft_reviewable",
        reason="baseline_missing",
    )
    assert details.project_id is not None


def test_question_check_discriminated_union_openapi_and_reject_shape(
    tmp_path: Path,
) -> None:
    from pydantic import TypeAdapter, ValidationError

    from offline_rag.api.gold_lab import (
        QuestionCheckAcceptRequest,
        QuestionCheckEditRequest,
        QuestionCheckRejectRequest,
        QuestionCheckRequest,
    )

    adapter = TypeAdapter(QuestionCheckRequest)
    assert isinstance(
        adapter.validate_python({"decision": "accept"}), QuestionCheckAcceptRequest
    )
    assert isinstance(
        adapter.validate_python({"decision": "reject"}), QuestionCheckRejectRequest
    )
    assert isinstance(
        adapter.validate_python(
            {
                "decision": "edit",
                "effective_query": "revised?",
                "effective_category": None,
                "effective_tags": ["t"],
            }
        ),
        QuestionCheckEditRequest,
    )
    with pytest.raises(ValidationError):
        adapter.validate_python({"decision": "accept", "effective_query": None})
    with pytest.raises(ValidationError):
        adapter.validate_python({"decision": "reject", "effective_tags": []})
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"decision": "edit", "effective_query": "x", "effective_tags": []}
        )

    with _ready_client(tmp_path) as (client, _ctx):
        schema = client.app.openapi()
        qc_path = (
            "/v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}/question-check"
        )
        body_schema = schema["paths"][qc_path]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        # Discriminated union must surface as oneOf / discriminator, not a single
        # flat model with optional effective_* fields.
        dumped = json.dumps(body_schema)
        assert "oneOf" in dumped or "discriminator" in dumped or "$ref" in dumped
        # Resolve $ref if present and assert accept variant forbids effective_*.
        resolved = body_schema
        if "$ref" in body_schema:
            name = body_schema["$ref"].rsplit("/", 1)[-1]
            resolved = schema["components"]["schemas"][name]
        text = json.dumps(resolved) + json.dumps(schema.get("components", {}))
        assert "QuestionCheckAcceptRequest" in text
        assert "QuestionCheckEditRequest" in text
        assert "QuestionCheckRejectRequest" in text


def test_rfc3339_z_normalizes_non_utc_aware_datetime() -> None:
    from datetime import datetime, timedelta, timezone

    from offline_rag.app.gold_lab.views import rfc3339_z

    eastern = timezone(timedelta(hours=-4))
    value = datetime(2024, 6, 15, 12, 30, 0, tzinfo=eastern)
    assert rfc3339_z(value) == "2024-06-15T16:30:00Z"
    assert rfc3339_z(value).endswith("Z")
    assert "-04:00" not in rfc3339_z(value)
