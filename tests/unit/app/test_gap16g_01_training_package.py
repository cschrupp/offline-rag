"""GAP-16G-01 — immutable Training / Calibration package read."""

from __future__ import annotations

import hashlib
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

from test_slice16f_d_gold_lab_api import (
    _active_workspace,
    _FakeQdrant,
    _runtime,
    _write_baseline,
)
from test_slice16f_d_gold_lab_historical_source import (
    CHUNK_A,
    CHUNK_B,
    CORPUS_NAME,
    DOC_ID,
    _publish_integrity,
)
from test_slice16f_d_gold_lab_historical_source import (
    _settings as _integrity_settings,
)

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.gold_lab import (
    GoldCampaignService,
    GoldLabError,
    GoldLabMutationService,
    GoldLabScientificExportService,
    GoldLabStore,
    GoldProjectType,
    build_selection_policy,
)
from offline_rag.app.gold_lab.paths import (
    dataset_dir,
    hard_calls_path,
    ledger_dir,
    projection_authoring_run_path,
    registration_path,
)
from offline_rag.app.gold_lab.training_package import (
    PACKAGE_SCHEMA_VERSION,
    GoldLabTrainingPackageService,
)
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.config.models import AppSettings
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase, SourceSeed
from offline_rag.gold_authoring.pooling_models import PoolCandidate
from offline_rag.ingestion.io import atomic_write_text

CASE_ACCEPT = "draft_accept"
CASE_REJECT = "draft_reject"
CASE_PENDING = "draft_pending"


def _gap_baseline(*, corpus_id: str, chunk_set_id: str) -> GoldAuthoringRun:
    def reviewable(case_id: str, query: str) -> SilverCase:
        return SilverCase(
            draft_case_id=case_id,
            proposed_query=query,
            proposed_category="ops",
            proposed_tags=["gold"],
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
        )

    return GoldAuthoringRun(
        authoring_run_id="authorrun_gap16g01",
        authorcfg_id="authorcfg_" + ("b" * 64),
        network_policy="localhost_only",
        created_at=datetime.now(tz=UTC),
        corpus_name=CORPUS_NAME,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        cases=[
            reviewable(CASE_ACCEPT, "What is offline RAG?"),
            reviewable(CASE_REJECT, "Should this be rejected?"),
            reviewable(CASE_PENDING, "Leave this pending?"),
        ],
    )


@contextmanager
def _gap_env(
    tmp_path: Path,
) -> Iterator[tuple[AppSettings, GoldLabStore, object, ApplicationRuntime]]:
    settings = _integrity_settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, _art = _publish_integrity(settings)
    q = _FakeQdrant()
    q.counts["col_16fd"] = 2
    runtime = _runtime(settings, qdrant=q)
    runtime.publication.qdrant = q
    ws = _active_workspace(settings, snapshot_id)
    run = _gap_baseline(corpus_id=corpus_id, chunk_set_id=chunk_set_id)
    _write_baseline(settings, run)
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="GAP16G01",
        project_type=GoldProjectType.BENCHMARK,
    )
    campaign = GoldCampaignService(
        settings, store=store, qdrant=q
    ).create_campaign(
        project_id=project.project_id,
        baseline=run,
        selection_policy=build_selection_policy(
            selection_policy_id="selpol_gap16g01",
            project_type=GoldProjectType.BENCHMARK,
            parameters={"top_k": 5},
        ),
    )
    yield settings, store, campaign, runtime


def _complete_accept(
    mut: GoldLabMutationService, campaign_id: str, *, case_id: str = CASE_ACCEPT
) -> None:
    mut.submit_question_check(
        campaign_id=campaign_id,
        case_id=case_id,
        payload={"decision": "accept"},
        idempotency_key=f"qc_accept_{case_id}",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign_id,
        case_id=case_id,
        candidate_chunk_id=CHUNK_A,
        relevance=2,
        idempotency_key=f"abs_a_{case_id}",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign_id,
        case_id=case_id,
        candidate_chunk_id=CHUNK_B,
        relevance=0,
        idempotency_key=f"abs_b_{case_id}",
    )


def _complete_edit(mut: GoldLabMutationService, campaign_id: str) -> None:
    mut.submit_question_check(
        campaign_id=campaign_id,
        case_id=CASE_ACCEPT,
        payload={
            "decision": "edit",
            "effective_query": "Edited offline RAG question?",
            "effective_category": "edited",
            "effective_tags": ["edited-tag"],
        },
        idempotency_key="qc_edit",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign_id,
        case_id=CASE_ACCEPT,
        candidate_chunk_id=CHUNK_A,
        relevance=1,
        idempotency_key="abs_a_edit",
    )
    mut.submit_absolute_relevance(
        campaign_id=campaign_id,
        case_id=CASE_ACCEPT,
        candidate_chunk_id=CHUNK_B,
        relevance=2,
        idempotency_key="abs_b_edit",
    )


def _reject_case(mut: GoldLabMutationService, campaign_id: str) -> None:
    mut.submit_question_check(
        campaign_id=campaign_id,
        case_id=CASE_REJECT,
        payload={"decision": "reject"},
        idempotency_key="qc_reject",
    )


def _export(settings, store, campaign_id: str):
    return GoldLabScientificExportService(
        settings, store=store
    ).export_and_register(campaign_id)


def _walk_forbidden(obj, *, path: str = "$") -> list[str]:
    forbidden_keys = {
        "dataset_path",
        "rank",
        "score",
        "retrieval_hits",
        "retriever",
        "embedding_score",
        "reranker_score",
        "model_judgments",
        "model_confidence",
        "model_agreement",
        "prelabel",
        "prelabel_provenance",
        "proposal_rationale",
        "hard_call_reason",
        "effective_endpoint",
        "reason_code",
    }
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}"
            if key in forbidden_keys:
                hits.append(here)
            if isinstance(value, str) and (
                "/data/" in value
                or value.startswith("/data")
                or "datasets/" in value
            ):
                hits.append(f"{here}=pathish:{value}")
            hits.extend(_walk_forbidden(value, path=here))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            hits.extend(_walk_forbidden(value, path=f"{path}[{index}]"))
    return hits


def test_happy_accept_edit_reject_pending_and_sources(tmp_path: Path) -> None:
    with _gap_env(tmp_path) as (settings, store, campaign, _runtime):
        mut = GoldLabMutationService(settings, store=store)
        _complete_accept(mut, campaign.campaign_id)
        _reject_case(mut, campaign.campaign_id)
        # CASE_PENDING left untouched
        result = _export(settings, store, campaign.campaign_id)

        pkg = GoldLabTrainingPackageService(
            settings, store=store
        ).get_training_package(
            campaign_id=campaign.campaign_id,
            dataset_id=result.dataset_id,
        )
        assert pkg["schema_version"] == PACKAGE_SCHEMA_VERSION
        assert pkg["campaign_id"] == campaign.campaign_id
        assert pkg["dataset_id"] == result.dataset_id
        assert pkg["registration"]["projection_sha256"] == result.projection_sha256
        assert "dataset_path" not in pkg["registration"]

        gold_cases = {c["case_id"]: c for c in pkg["registered_dataset"]["cases"]}
        assert set(gold_cases) == {CASE_ACCEPT}
        assert gold_cases[CASE_ACCEPT]["judgments"] == [
            {"chunk_id": CHUNK_A, "relevance": 2}
        ]

        adj = {c["case_id"]: c for c in pkg["adjudication"]["cases"]}
        assert CASE_PENDING not in adj
        assert adj[CASE_ACCEPT]["qc_disposition"] == "accept"
        assert adj[CASE_ACCEPT]["relevance_judgments"] == [
            {"chunk_id": CHUNK_A, "relevance": 2},
            {"chunk_id": CHUNK_B, "relevance": 0},
        ]
        assert adj[CASE_ACCEPT]["question_source"]["text"]
        assert adj[CASE_ACCEPT]["candidates"][0]["source"]["chunk_id"] == CHUNK_A

        assert adj[CASE_REJECT]["qc_disposition"] == "reject"
        assert adj[CASE_REJECT]["relevance_judgments"] == []
        assert adj[CASE_REJECT]["effective_query"] is None
        assert adj[CASE_REJECT]["effective_category"] is None
        assert adj[CASE_REJECT]["effective_tags"] == []
        assert adj[CASE_REJECT]["proposed_query"] == "Should this be rejected?"

        assert _walk_forbidden(pkg) == []


def test_edit_preserves_effective_fields(tmp_path: Path) -> None:
    with _gap_env(tmp_path) as (settings, store, campaign, _runtime):
        mut = GoldLabMutationService(settings, store=store)
        _complete_edit(mut, campaign.campaign_id)
        result = _export(settings, store, campaign.campaign_id)
        pkg = GoldLabTrainingPackageService(
            settings, store=store
        ).get_training_package(
            campaign_id=campaign.campaign_id,
            dataset_id=result.dataset_id,
        )
        case = pkg["adjudication"]["cases"][0]
        assert case["qc_disposition"] == "edit"
        assert case["effective_query"] == "Edited offline RAG question?"
        assert case["effective_category"] == "edited"
        assert case["effective_tags"] == ["edited-tag"]
        gold = pkg["registered_dataset"]["cases"][0]
        assert gold["query"] == case["effective_query"]
        assert gold["category"] == case["effective_category"]
        assert set(gold["tags"]) == set(case["effective_tags"])


def test_old_registration_after_later_export_reconstructs(tmp_path: Path) -> None:
    with _gap_env(tmp_path) as (settings, store, campaign, _runtime):
        mut = GoldLabMutationService(settings, store=store)
        _complete_accept(mut, campaign.campaign_id)
        first = _export(settings, store, campaign.campaign_id)
        hash_a = first.projection_sha256
        dataset_a = first.dataset_id

        # Later correction → new scientific state / export B.
        mut.submit_absolute_relevance(
            campaign_id=campaign.campaign_id,
            case_id=CASE_ACCEPT,
            candidate_chunk_id=CHUNK_A,
            relevance=1,
            idempotency_key="abs_a_correct",
        )
        second = _export(settings, store, campaign.campaign_id)
        assert second.projection_sha256 != hash_a
        assert second.dataset_id != dataset_a

        # Durable projection artifact is now B.
        proj_bytes = projection_authoring_run_path(
            settings, campaign.campaign_id
        ).read_bytes()
        assert hashlib.sha256(proj_bytes).hexdigest() == second.projection_sha256

        pkg_a = GoldLabTrainingPackageService(
            settings, store=store
        ).get_training_package(
            campaign_id=campaign.campaign_id,
            dataset_id=dataset_a,
        )
        assert pkg_a["registration"]["projection_sha256"] == hash_a
        assert pkg_a["adjudication"]["projection_sha256"] == hash_a
        judgments = pkg_a["adjudication"]["cases"][0]["relevance_judgments"]
        assert {"chunk_id": CHUNK_A, "relevance": 2} in judgments

        pkg_b = GoldLabTrainingPackageService(
            settings, store=store
        ).get_training_package(
            campaign_id=campaign.campaign_id,
            dataset_id=second.dataset_id,
        )
        judgments_b = pkg_b["adjudication"]["cases"][0]["relevance_judgments"]
        assert {"chunk_id": CHUNK_A, "relevance": 1} in judgments_b


def test_missing_projection_artifact_reconstructs_from_ledger(
    tmp_path: Path,
) -> None:
    with _gap_env(tmp_path) as (settings, store, campaign, _runtime):
        mut = GoldLabMutationService(settings, store=store)
        _complete_accept(mut, campaign.campaign_id)
        result = _export(settings, store, campaign.campaign_id)
        path = projection_authoring_run_path(settings, campaign.campaign_id)
        path.unlink()
        pkg = GoldLabTrainingPackageService(
            settings, store=store
        ).get_training_package(
            campaign_id=campaign.campaign_id,
            dataset_id=result.dataset_id,
        )
        assert pkg["adjudication"]["projection_sha256"] == result.projection_sha256


def test_no_matching_projection_fail_closed(tmp_path: Path) -> None:
    with _gap_env(tmp_path) as (settings, store, campaign, _runtime):
        mut = GoldLabMutationService(settings, store=store)
        _complete_accept(mut, campaign.campaign_id)
        result = _export(settings, store, campaign.campaign_id)
        reg_path = registration_path(
            settings, result.dataset_id, campaign.campaign_id
        )
        raw = json.loads(reg_path.read_text(encoding="utf-8"))
        raw["projection_sha256"] = "a" * 64
        atomic_write_text(reg_path, json.dumps(raw, indent=2) + "\n")
        with pytest.raises(GoldLabError) as exc:
            GoldLabTrainingPackageService(
                settings, store=store
            ).get_training_package(
                campaign_id=campaign.campaign_id,
                dataset_id=result.dataset_id,
            )
        assert exc.value.reason in {
            "training_package_projection_unavailable",
            "registration_provenance_mismatch",
        }


def test_corrupt_dataset_fail_closed(tmp_path: Path) -> None:
    with _gap_env(tmp_path) as (settings, store, campaign, _runtime):
        mut = GoldLabMutationService(settings, store=store)
        _complete_accept(mut, campaign.campaign_id)
        result = _export(settings, store, campaign.campaign_id)
        ddir = dataset_dir(settings, result.dataset_id)
        for path in ddir.glob("*.jsonl"):
            path.write_text("{not-json\n", encoding="utf-8")
        with pytest.raises(GoldLabError) as exc:
            GoldLabTrainingPackageService(
                settings, store=store
            ).get_training_package(
                campaign_id=campaign.campaign_id,
                dataset_id=result.dataset_id,
            )
        assert "dataset" in exc.value.reason or "corrupt" in exc.value.reason


def test_historical_source_corrupt_fail_closed(tmp_path: Path) -> None:
    with _gap_env(tmp_path) as (settings, store, campaign, _runtime):
        mut = GoldLabMutationService(settings, store=store)
        _complete_accept(mut, campaign.campaign_id)
        result = _export(settings, store, campaign.campaign_id)
        # Tamper every durable chunk artifact so historical resolve fails closed.
        for path in settings.paths.chunks.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("children"):
                payload["children"][0]["text"] = "tampered package evidence"
                path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(AppError) as exc:
            GoldLabTrainingPackageService(
                settings, store=store
            ).get_training_package(
                campaign_id=campaign.campaign_id,
                dataset_id=result.dataset_id,
            )
        assert exc.value.code is ErrorCode.GOLD_STATE_UNAVAILABLE


def test_closed_campaign_and_archived_project_still_readable(
    tmp_path: Path,
) -> None:
    with _gap_env(tmp_path) as (settings, store, campaign, _runtime):
        mut = GoldLabMutationService(settings, store=store)
        _complete_accept(mut, campaign.campaign_id)
        result = _export(settings, store, campaign.campaign_id)
        store.close_campaign(campaign.campaign_id)
        store.archive_project(campaign.project_id)
        pkg = GoldLabTrainingPackageService(
            settings, store=store
        ).get_training_package(
            campaign_id=campaign.campaign_id,
            dataset_id=result.dataset_id,
        )
        assert pkg["dataset_id"] == result.dataset_id


def test_read_only_no_durable_mutation(tmp_path: Path) -> None:
    with _gap_env(tmp_path) as (settings, store, campaign, _runtime):
        mut = GoldLabMutationService(settings, store=store)
        _complete_accept(mut, campaign.campaign_id)
        result = _export(settings, store, campaign.campaign_id)

        def snapshot() -> dict[str, bytes]:
            out: dict[str, bytes] = {}
            for path in (
                projection_authoring_run_path(settings, campaign.campaign_id),
                registration_path(
                    settings, result.dataset_id, campaign.campaign_id
                ),
                hard_calls_path(settings, campaign.campaign_id),
            ):
                if path.is_file():
                    out[str(path)] = path.read_bytes()
            for path in sorted(ledger_dir(settings, campaign.campaign_id).glob("*.json")):
                out[str(path)] = path.read_bytes()
            for path in sorted(dataset_dir(settings, result.dataset_id).rglob("*")):
                if path.is_file():
                    out[str(path)] = path.read_bytes()
            return out

        before = snapshot()
        GoldLabTrainingPackageService(settings, store=store).get_training_package(
            campaign_id=campaign.campaign_id,
            dataset_id=result.dataset_id,
        )
        assert snapshot() == before


def test_api_route_invalid_dataset_and_happy_path(tmp_path: Path) -> None:
    with _gap_env(tmp_path) as (settings, store, campaign, runtime):
        mut = GoldLabMutationService(settings, store=store)
        _complete_accept(mut, campaign.campaign_id)
        result = _export(settings, store, campaign.campaign_id)
        app = __import__("offline_rag.api.app", fromlist=["create_app"]).create_app(
            runtime=runtime
        )
        with TestClient(app) as client:
            bad = client.get(
                f"/v1/gold-lab/campaigns/{campaign.campaign_id}"
                f"/registrations/not-a-valid-dataset/training-package"
            )
            assert bad.status_code == 422
            assert bad.json()["error"]["code"] == "request_invalid"
            assert bad.json()["details"]["reason"] == "transport_dataset_id_invalid"

            missing = client.get(
                f"/v1/gold-lab/campaigns/{campaign.campaign_id}"
                f"/registrations/gold_{'a' * 64}/training-package"
            )
            assert missing.status_code == 409
            assert missing.json()["error"]["code"] == "gold_state_unavailable"

            ok = client.get(
                f"/v1/gold-lab/campaigns/{campaign.campaign_id}"
                f"/registrations/{result.dataset_id}/training-package"
            )
            assert ok.status_code == 200, ok.text
            body = ok.json()
            assert body["schema_version"] == PACKAGE_SCHEMA_VERSION
            assert _walk_forbidden(body) == []
