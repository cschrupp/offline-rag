"""Slice 16K-B — durable ingestion metrics + worklist observability."""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.api.workspace_views import operation_view
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.paths import ensure_data_directories
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.workspace.models import (
    MANAGED_OP_SCHEMA_VERSION,
    ManagedOperationDocumentPhase,
    ManagedOperationKind,
    ManagedOperationMetrics,
    ManagedOperationRecord,
    ManagedOperationStatus,
    ManagedOperationWorklistDocument,
    build_managed_operation_worklist,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.generation.fake import FakeGenerator
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.rerank.fake import FakeReranker

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"


def _settings(tmp_path: Path, **api_overrides: object) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    generation = settings.generation.model_copy(
        update={
            "enabled": True,
            "base_url": APPROVED_ENDPOINT,
            "model": APPROVED_MODEL,
            "approved_endpoints": [APPROVED_ENDPOINT],
            "approved_models": [APPROVED_MODEL],
        }
    )
    api = settings.api.model_copy(update=api_overrides) if api_overrides else settings.api
    reranker = settings.reranker.model_copy(
        update={"enabled": True, "implementation": "fake"}
    )
    indexing = settings.indexing.model_copy(
        update={
            "embedding": settings.indexing.embedding.model_copy(
                update={"batch_size": 2, "dimension": 8}
            )
        }
    )
    settings = settings.model_copy(
        update={
            "generation": generation,
            "api": api,
            "reranker": reranker,
            "indexing": indexing,
        }
    )
    ensure_data_directories(settings)
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(settings.paths.docling_artifacts, docling_version="test")
    if not (TIKTOKEN_SRC / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)
    return settings


def _runtime(settings: AppSettings) -> ApplicationRuntime:
    embedder = FakeEmbedder(dimension=8, normalize=True)

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: FakeReranker(),
            generator_client=lambda _s: FakeGenerator(
                default_response='{"abstain": true, "answer": null, "citation_ids": []}'
            ),
            qdrant=_qdrant,
        ),
    )


@contextmanager
def _client(tmp_path: Path, **api: object) -> Iterator[tuple[TestClient, ApplicationRuntime]]:
    settings = _settings(tmp_path, **api)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        yield client, runtime


def _wait(client: TestClient, op_id: str, *, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/v1/operations/{op_id}").json()
        if body["status"] in {"succeeded", "failed", "interrupted"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"op {op_id} did not terminate")


def _create(client: TestClient, key: str = "c") -> dict:
    r = client.post(
        "/v1/workspaces",
        json={"title": "Desk", "description": "d"},
        headers={"Idempotency-Key": key},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _add_sources(
    client: TestClient,
    wid: str,
    *,
    files: list[tuple[str, bytes]],
    key: str,
    rev: int,
) -> dict:
    upload = [("files", (name, body, "text/plain")) for name, body in files]
    r = client.post(
        f"/v1/workspaces/{wid}/sources",
        headers={"Idempotency-Key": key, "If-Match": f'"{rev}"'},
        files=upload,
    )
    assert r.status_code == 202, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Schema / legacy compatibility / store invariants
# ---------------------------------------------------------------------------


def test_legacy_record_without_metrics_worklist_validates_and_projects_null() -> None:
    now = datetime.now(tz=UTC)
    legacy = {
        "schema_version": MANAGED_OP_SCHEMA_VERSION,
        "operation_id": "wop_legacy",
        "idempotency_key": "k1",
        "kind": "source_add",
        "workspace_id": "ws_1",
        "request_fingerprint": "fp",
        "expected_revision": 1,
        "status": "running",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "progress_stage": "building_indexes",
    }
    record = ManagedOperationRecord.model_validate(legacy)
    assert record.metrics is None
    assert record.worklist is None
    view = operation_view(record)
    assert view["metrics"] is None
    assert view["worklist"] is None
    assert "progress" in view


def test_progress_metrics_worklist_are_separate_fields() -> None:
    now = datetime.now(tz=UTC)
    docs = [
        ManagedOperationWorklistDocument(
            document_id="doc_a",
            display_name="a.md",
            phase=ManagedOperationDocumentPhase.INDEXING,
        ),
        ManagedOperationWorklistDocument(
            document_id="doc_b",
            display_name="b.md",
            phase=ManagedOperationDocumentPhase.INDEXING,
        ),
    ]
    worklist = build_managed_operation_worklist(
        docs, active_document_ids=["doc_a", "doc_b"]
    )
    assert len(worklist.active_documents) == 2
    record = ManagedOperationRecord(
        operation_id="wop_1",
        idempotency_key="k",
        kind=ManagedOperationKind.SOURCE_ADD,
        workspace_id="ws_1",
        request_fingerprint="fp",
        expected_revision=1,
        status=ManagedOperationStatus.RUNNING,
        created_at=now,
        updated_at=now,
        metrics=ManagedOperationMetrics(requested_document_count=2),
        worklist=worklist,
    )
    view = operation_view(record)
    assert view["progress"] is None
    assert view["metrics"]["requested_document_count"] == 2
    assert len(view["worklist"]["active_documents"]) == 2
    assert "metrics" not in (view.get("progress") or {})
    assert "worklist" not in (view.get("progress") or {})


def test_worklist_membership_immutable_after_first_write(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = ManagedOperationStore(settings)
    now = datetime.now(tz=UTC)
    wid = "ws_immut"
    op = store.begin(
        workspace_id=wid,
        idempotency_key="k",
        kind=ManagedOperationKind.SOURCE_ADD,
        request_payload={"files": []},
        expected_revision=1,
    )
    store.update_status(wid, op.operation_id, ManagedOperationStatus.RUNNING)
    first = build_managed_operation_worklist(
        [
            ManagedOperationWorklistDocument(
                document_id="doc_a",
                display_name="a.md",
                phase=ManagedOperationDocumentPhase.PENDING,
            )
        ]
    )
    store.update_worklist(wid, op.operation_id, first)
    changed = build_managed_operation_worklist(
        [
            ManagedOperationWorklistDocument(
                document_id="doc_b",
                display_name="b.md",
                phase=ManagedOperationDocumentPhase.PENDING,
            )
        ]
    )
    with pytest.raises(AppError) as exc:
        store.update_worklist(wid, op.operation_id, changed)
    assert exc.value.code is ErrorCode.REQUEST_INVALID
    details = exc.value.details
    assert details is not None
    reason = details.get("reason") if isinstance(details, dict) else getattr(details, "reason", None)
    assert reason == "worklist_membership_immutable"
    _ = now


def test_active_documents_supports_zero_to_n_and_is_not_phase_derived() -> None:
    docs = [
        ManagedOperationWorklistDocument(
            document_id="doc_a",
            display_name="a.md",
            phase=ManagedOperationDocumentPhase.INDEXING,
        ),
        ManagedOperationWorklistDocument(
            document_id="doc_b",
            display_name="b.md",
            phase=ManagedOperationDocumentPhase.INDEXING,
        ),
        ManagedOperationWorklistDocument(
            document_id="doc_c",
            display_name="c.md",
            phase=ManagedOperationDocumentPhase.INDEXING,
        ),
    ]
    empty = build_managed_operation_worklist(docs, active_document_ids=[])
    assert empty.active_documents == []
    multi = build_managed_operation_worklist(
        docs, active_document_ids=["doc_a", "doc_c"]
    )
    assert {d.document_id for d in multi.active_documents} == {"doc_a", "doc_c"}
    # Indexing phase alone must not imply activity for doc_b.
    assert "doc_b" not in {d.document_id for d in multi.active_documents}


# ---------------------------------------------------------------------------
# End-to-end managed ingest observability
# ---------------------------------------------------------------------------


def test_successful_add_persists_bounded_metrics_and_worklist(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _runtime):
        wid = _create(client)["workspace_id"]
        accepted = _add_sources(
            client,
            wid,
            files=[
                ("alpha.md", b"# Alpha\n\nHello world one.\n"),
                ("beta.md", b"# Beta\n\nHello world two.\n"),
            ],
            key="add-2",
            rev=1,
        )
        op_id = accepted["operation_id"]
        # Durability during run: poll until metrics/worklist appear, then reload.
        saw_worklist = False
        deadline = time.time() + 30.0
        while time.time() < deadline:
            mid = client.get(f"/v1/operations/{op_id}").json()
            if mid.get("worklist") is not None:
                saw_worklist = True
                assert mid["progress"] is None or "metrics" not in mid["progress"]
                assert mid["worklist"]["total_document_count"] == 2
                assert isinstance(mid["worklist"]["active_documents"], list)
                break
            time.sleep(0.05)
        assert saw_worklist
        final = _wait(client, op_id)
        assert final["status"] == "succeeded"
        metrics = final["metrics"]
        worklist = final["worklist"]
        assert metrics is not None
        assert worklist is not None
        assert metrics["requested_document_count"] == 2
        assert metrics["pre_active_source_count"] == 0
        assert metrics["post_active_source_count"] == 2
        assert metrics["uploaded_raw_bytes"] > 0
        assert metrics["parsed_artifacts_generated"] + metrics["parsed_artifacts_reused"] >= 1
        assert metrics["chunk_artifacts_generated"] + metrics["chunk_artifacts_reused"] >= 1
        assert metrics["embeddings_generated"] + metrics["embeddings_reused"] >= 1
        assert metrics["child_chunk_count"] is not None and metrics["child_chunk_count"] >= 1
        dense = metrics["dense_execution"]
        assert dense["device"] == "test"
        assert dense["batch_size"] == 2
        assert dense["embedding_dimension"] == 8
        # Fake embedder has no truthful token throughput — must be absent/null.
        assert metrics.get("model_input_tokens_per_sec") is None
        durations = metrics["stage_durations"]
        for key in (
            "parsing_ms",
            "chunking_ms",
            "dense_generation_ms",
            "lexical_ms",
            "publication_ms",
            "finalization_ms",
            "total_ms",
        ):
            assert durations.get(key) is None or durations[key] >= 0
        assert durations.get("total_ms") is not None and durations["total_ms"] >= 0
        assert durations.get("finalization_ms") is not None
        # Fake embedder: dtype/attention truthfully unavailable (not invented).
        assert dense.get("dtype") is None
        assert dense.get("attention_backend") is None
        assert worklist["total_document_count"] == 2
        assert worklist["pending_count"] == 0
        assert worklist["completed_count"] == 2
        assert worklist["remaining_count"] == 0
        assert worklist["active_documents"] == []
        names = {d["display_name"] for d in worklist["documents"]}
        assert names == {"alpha.md", "beta.md"}
        assert all(d["phase"] == "indexed" for d in worklist["documents"])
        # Reload proof: GET again after terminal.
        again = client.get(f"/v1/operations/{op_id}").json()
        assert again["metrics"]["requested_document_count"] == 2
        assert again["worklist"]["total_document_count"] == 2
        # Progress remains a separate object when present.
        if again.get("progress") is not None:
            assert "requested_document_count" not in again["progress"]
            assert "documents" not in again["progress"]


def test_dense_active_documents_follow_exact_batch_membership(tmp_path: Path) -> None:
    """R2: activity tracks batch membership, not the full indexing-ready set."""
    from offline_rag.app.observability_publish import DurableObservabilityPublisher
    from offline_rag.core.observability import DocumentActivityEvent, DocumentPhaseEvent

    settings = _settings(tmp_path)
    store = ManagedOperationStore(settings)
    wid = "ws_act"
    op = store.begin(
        workspace_id=wid,
        idempotency_key="act",
        kind=ManagedOperationKind.SOURCE_ADD,
        request_payload={"files": []},
        expected_revision=1,
    )
    store.update_status(wid, op.operation_id, ManagedOperationStatus.RUNNING)
    pub = DurableObservabilityPublisher(
        operations=store, workspace_id=wid, operation_id=op.operation_id
    )
    docs = [
        ManagedOperationWorklistDocument(
            document_id="doc_a",
            display_name="a.md",
            phase=ManagedOperationDocumentPhase.PENDING,
        ),
        ManagedOperationWorklistDocument(
            document_id="doc_b",
            display_name="b.md",
            phase=ManagedOperationDocumentPhase.PENDING,
        ),
        ManagedOperationWorklistDocument(
            document_id="doc_c",
            display_name="c.md",
            phase=ManagedOperationDocumentPhase.PENDING,
        ),
        ManagedOperationWorklistDocument(
            document_id="doc_d",
            display_name="d.md",
            phase=ManagedOperationDocumentPhase.PENDING,
        ),
    ]
    pub.freeze_admission(
        documents=docs,
        requested_document_count=4,
        uploaded_raw_bytes=10,
        pre_active_source_count=0,
        post_active_source_count=4,
    )
    for doc_id in ("doc_a", "doc_b", "doc_c", "doc_d"):
        pub(
            DocumentPhaseEvent(
                document_id=doc_id, source_name=f"{doc_id}.md", phase="indexing"
            )
        )
    assert pub.snapshot_active_ids() == []
    pub.on_activity(
        DocumentActivityEvent(document_ids=("doc_a", "doc_c"), stage="dense_batch")
    )
    recorded = store.get(wid, op.operation_id)
    assert recorded.worklist is not None
    assert {d.document_id for d in recorded.worklist.active_documents} == {
        "doc_a",
        "doc_c",
    }
    assert all(
        d.phase is ManagedOperationDocumentPhase.INDEXING
        for d in recorded.worklist.documents
    )
    pub.on_activity(DocumentActivityEvent(document_ids=(), stage="dense_batch"))
    cleared = store.get(wid, op.operation_id)
    assert cleared.worklist is not None
    assert cleared.worklist.active_documents == []


def test_idempotent_replay_keeps_single_worklist_identity(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _runtime):
        wid = _create(client)["workspace_id"]
        first = _add_sources(
            client,
            wid,
            files=[("only.md", b"# Only\n\nContent.\n")],
            key="idem-obs",
            rev=1,
        )
        final = _wait(client, first["operation_id"])
        assert final["status"] == "succeeded"
        worklist_a = final["worklist"]
        metrics_a = final["metrics"]
        replay = _add_sources(
            client,
            wid,
            files=[("only.md", b"# Only\n\nContent.\n")],
            key="idem-obs",
            rev=1,
        )
        assert replay["operation_id"] == first["operation_id"]
        body = client.get(f"/v1/operations/{first['operation_id']}").json()
        assert body["worklist"] == worklist_a
        assert body["metrics"]["requested_document_count"] == metrics_a[
            "requested_document_count"
        ]


def test_live_failure_preserves_observability_and_recovered_a(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client)["workspace_id"]

        # Force dense failure after worklist admission by patching run_indexing.
        from offline_rag.app import ingest as ingest_mod

        real_run_indexing = ingest_mod.run_indexing

        def boom(**kwargs):
            raise AppError(ErrorCode.INGEST_FAILED)

        ingest_mod.run_indexing = boom  # type: ignore[assignment]
        try:
            accepted = _add_sources(
                client,
                wid,
                files=[("fail.md", b"# Fail\n\nWill break at dense.\n")],
                key="fail-obs",
                rev=1,
            )
            final = _wait(client, accepted["operation_id"])
        finally:
            ingest_mod.run_indexing = real_run_indexing  # type: ignore[assignment]
        assert final["status"] == "failed"
        assert final["error"] is not None
        op = runtime.workspace_lifecycle.operations.get_by_operation_id(
            accepted["operation_id"]
        )
        assert op.recovery_note == "recovered_A"
        assert op.error is not None
        assert op.worklist is not None
        assert op.worklist.total_document_count == 1
        assert op.metrics is not None
        assert op.metrics.requested_document_count == 1


def test_existing_16i_progress_tests_still_importable() -> None:
    # Smoke: progress module contracts remain importable alongside 16K-B models.
    from offline_rag.app.workspace.models import ManagedOperationProgress

    assert ManagedOperationProgress is not None


# ---------------------------------------------------------------------------
# R1–R4 rework proofs
# ---------------------------------------------------------------------------


def test_r1_add_to_existing_separates_request_from_reconstruction(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _runtime):
        wid = _create(client)["workspace_id"]
        first = _add_sources(
            client,
            wid,
            files=[("seed.md", b"# Seed\n\nExisting source body.\n")],
            key="seed",
            rev=1,
        )
        assert _wait(client, first["operation_id"])["status"] == "succeeded"
        rev = int(client.get(f"/v1/workspaces/{wid}").json()["revision"])
        added = b"# New\n\nAdded one document only.\n"
        second = _add_sources(
            client,
            wid,
            files=[("new.md", added)],
            key="add-existing",
            rev=rev,
        )
        # Worklist durable on 202 body.
        assert second["worklist"] is not None
        assert second["metrics"]["requested_document_count"] == 1
        assert second["metrics"]["uploaded_raw_bytes"] == len(added)
        assert second["metrics"]["pre_active_source_count"] == 1
        assert second["metrics"]["post_active_source_count"] == 2
        assert second["worklist"]["total_document_count"] == 2
        final = _wait(client, second["operation_id"])
        assert final["status"] == "succeeded"
        assert final["metrics"]["requested_document_count"] == 1
        assert final["metrics"]["uploaded_raw_bytes"] == len(added)
        assert final["worklist"]["total_document_count"] == 2


def test_r1_replace_request_metrics(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _runtime):
        wid = _create(client)["workspace_id"]
        first = _add_sources(
            client,
            wid,
            files=[
                ("keep.md", b"# Keep\n\nStay.\n"),
                ("old.md", b"# Old\n\nReplace me.\n"),
            ],
            key="seed-rep",
            rev=1,
        )
        assert _wait(client, first["operation_id"])["status"] == "succeeded"
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        target = next(s for s in sources if s["display_name"] == "old.md")
        rev = int(client.get(f"/v1/workspaces/{wid}").json()["revision"])
        replacement = b"# New\n\nReplacement body.\n"
        r = client.put(
            f"/v1/workspaces/{wid}/sources/{target['source_id']}",
            headers={"Idempotency-Key": "rep-1", "If-Match": f'"{rev}"'},
            files={"files": ("new.md", replacement, "text/plain")},
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["metrics"]["requested_document_count"] == 1
        assert body["metrics"]["uploaded_raw_bytes"] == len(replacement)
        assert body["metrics"]["pre_active_source_count"] == 2
        assert body["metrics"]["post_active_source_count"] == 2
        assert body["worklist"]["total_document_count"] == 2
        final = _wait(client, body["operation_id"])
        assert final["status"] == "succeeded"


def test_r1_remove_with_remaining_and_empty(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _runtime):
        wid = _create(client)["workspace_id"]
        first = _add_sources(
            client,
            wid,
            files=[
                ("a.md", b"# A\n\nOne.\n"),
                ("b.md", b"# B\n\nTwo.\n"),
            ],
            key="seed-rm",
            rev=1,
        )
        assert _wait(client, first["operation_id"])["status"] == "succeeded"
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        remove_a = next(s for s in sources if s["display_name"] == "a.md")
        rev = int(client.get(f"/v1/workspaces/{wid}").json()["revision"])
        r = client.delete(
            f"/v1/workspaces/{wid}/sources/{remove_a['source_id']}",
            headers={"Idempotency-Key": "rm-1", "If-Match": f'"{rev}"'},
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["metrics"]["requested_document_count"] == 1
        assert body["metrics"].get("uploaded_raw_bytes") is None
        assert body["metrics"]["pre_active_source_count"] == 2
        assert body["metrics"]["post_active_source_count"] == 1
        assert body["worklist"]["total_document_count"] == 1
        assert body["worklist"]["documents"][0]["display_name"] == "b.md"
        assert _wait(client, body["operation_id"])["status"] == "succeeded"

        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        last = sources[0]
        rev = int(client.get(f"/v1/workspaces/{wid}").json()["revision"])
        r2 = client.delete(
            f"/v1/workspaces/{wid}/sources/{last['source_id']}",
            headers={"Idempotency-Key": "rm-empty", "If-Match": f'"{rev}"'},
        )
        assert r2.status_code == 202, r2.text
        empty_body = r2.json()
        assert empty_body["metrics"]["requested_document_count"] == 1
        assert empty_body["metrics"].get("uploaded_raw_bytes") is None
        assert empty_body["metrics"]["pre_active_source_count"] == 1
        assert empty_body["metrics"]["post_active_source_count"] == 0
        assert empty_body["worklist"]["total_document_count"] == 1
        assert empty_body["worklist"]["documents"][0]["display_name"] == last["display_name"]
        final = _wait(client, empty_body["operation_id"])
        assert final["status"] == "succeeded"
        assert final["worklist"]["documents"][0]["phase"] == "removed"
        durations = final["metrics"]["stage_durations"]
        assert durations.get("parsing_ms") is None
        assert durations.get("chunking_ms") is None
        assert durations.get("dense_generation_ms") is None
        assert durations.get("total_ms") is not None


def test_r3_worklist_durable_on_202_before_worker(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client)["workspace_id"]
        # Block the worker from running by not releasing — instead, intercept
        # reserve and do not launch: call reserve_and_admit directly.
        lifecycle = runtime.workspace_lifecycle
        blob = b"# Early\n\nFrozen before worker.\n"
        from offline_rag.core.ids import content_hash_from_bytes

        sha = content_hash_from_bytes(blob)
        payload = {
            "files": [
                {
                    "display_name": "early.md",
                    "content_type": "text/plain",
                    "content_sha256": sha,
                }
            ]
        }
        op, handle = lifecycle.reserve_and_admit_scientific(
            wid,
            kind=ManagedOperationKind.SOURCE_ADD,
            idempotency_key="early-freeze",
            expected_revision=1,
            payload=payload,
            uploaded_raw_bytes=len(blob),
        )
        try:
            assert handle is not None
            assert op.worklist is not None
            assert op.metrics is not None
            assert op.worklist.total_document_count == 1
            assert op.metrics.requested_document_count == 1
            assert op.metrics.uploaded_raw_bytes == len(blob)
            # Crash-after-202 simulation: release capacity without running worker.
        finally:
            if handle is not None:
                runtime.operations.release(handle)
        reloaded = lifecycle.operations.get(wid, op.operation_id)
        assert reloaded.worklist is not None
        assert reloaded.worklist.documents[0].display_name == "early.md"


def test_r4_fake_embedder_execution_facts_are_truthfully_unavailable() -> None:
    from offline_rag.dense.embedder import FakeEmbedder, observe_embedder_execution_facts

    embedder = FakeEmbedder(dimension=8)
    facts = observe_embedder_execution_facts(embedder)
    assert facts["dtype"] is None
    assert facts["attention_backend"] is None
    # Explicit observe path must not invent FP32.
    assert embedder.observe_execution_facts() == {
        "dtype": None,
        "attention_backend": None,
    }
