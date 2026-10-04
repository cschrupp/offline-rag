"""Phase 15D — product ingest (D20 transport order + full-replace publish)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import threading
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.ingest import run_product_replace_ingest
from offline_rag.app.ingest_hooks import ProductIngestHooks
from offline_rag.app.ingest_upload import spool_multipart_upload
from offline_rag.app.leases import CorpusMutationLease
from offline_rag.app.publication import current_pointer_path
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
BASELINE_SHA = "02544e3974da6e26ec512a83f856b1e8d864d86d"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"


class _Closeable:
    def close(self) -> None:
        return None


def _provision_assets(settings: AppSettings) -> None:
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(settings.paths.docling_artifacts, docling_version="test")
    if not (TIKTOKEN_SRC / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)


def _settings(tmp_path: Path, **api_overrides: object) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    generation = settings.generation.model_copy(
        update={
            "base_url": APPROVED_ENDPOINT,
            "model": APPROVED_MODEL,
            "approved_endpoints": [APPROVED_ENDPOINT],
            "approved_models": [APPROVED_MODEL],
        }
    )
    api = settings.api.model_copy(update=api_overrides) if api_overrides else settings.api
    settings = settings.model_copy(update={"generation": generation, "api": api})
    _provision_assets(settings)
    return settings


def _runtime(settings: AppSettings) -> ApplicationRuntime:
    embedder = FakeEmbedder(dimension=8, normalize=True)

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=_qdrant,
        ),
    )


def _multipart(parts: list[tuple[str, bytes | None, str | None]], boundary: str = "----15d") -> tuple[bytes, str]:
    """Build a raw multipart body.

    parts: (field_name, body_or_None_for_empty, filename_or_None)
    """
    chunks: list[bytes] = []
    for name, body, filename in parts:
        chunks.append(f"--{boundary}\r\n".encode())
        if filename is None:
            chunks.append(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            )
        else:
            chunks.append(
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode()
            )
        if body:
            chunks.append(body)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _post_raw(client: TestClient, body: bytes, content_type: str, **headers: str):
    hdrs = {"Content-Type": content_type}
    hdrs.update(headers)
    return client.post("/v1/ingest", content=body, headers=hdrs)


def test_remote_ancestry_begins_at_15d_baseline() -> None:
    merge_base = subprocess.check_output(
        ["git", "merge-base", "HEAD", BASELINE_SHA],
        cwd=REPO_ROOT,
        text=True,
    ).strip()
    assert merge_base == BASELINE_SHA
    # Branch must contain the baseline commit.
    contained = subprocess.call(
        ["git", "merge-base", "--is-ancestor", BASELINE_SHA, "HEAD"],
        cwd=REPO_ROOT,
    )
    assert contained == 0


def test_malformed_non_multipart_is_request_invalid(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            "/v1/ingest",
            content=b'{"corpus":"x"}',
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "request_invalid"


def test_missing_corpus_multiple_corpus_zero_files(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [("files", b"hello text content\n", "a.txt")],
        )
        missing = _post_raw(client, body, ct)
        assert missing.status_code == 422
        assert missing.json()["error"]["code"] == "request_invalid"

        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("corpus", b"eng2", None),
                ("files", b"hello text content\n", "a.txt"),
            ]
        )
        multi = _post_raw(client, body, ct)
        assert multi.status_code == 422
        assert multi.json()["error"]["code"] == "request_invalid"

        body, ct = _multipart([("corpus", b"eng", None)])
        zero = _post_raw(client, body, ct)
        assert zero.status_code == 422
        assert zero.json()["error"]["code"] == "request_invalid"


def test_corpus_after_file_parts_succeeds(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("files", b"Alpha pump pressure is high.\n", "a.txt"),
                ("corpus", b"manuals", None),
            ]
        )
        resp = _post_raw(client, body, ct)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["corpus"] == "manuals"
        assert payload["document_count"] == 1
        assert payload["snapshot_id"].startswith("snap_")


def test_too_many_files_is_request_invalid(tmp_path: Path) -> None:
    # Exercise the same gate as max_files_per_ingest=32 with a smaller bound.
    settings = _settings(tmp_path, max_files_per_ingest=2)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        parts: list[tuple[str, bytes | None, str | None]] = [
            ("corpus", b"eng", None),
            ("files", b"doc one content aaa\n", "a.txt"),
            ("files", b"doc two content bbb\n", "b.txt"),
            ("files", b"doc three content c\n", "c.txt"),
        ]
        body, ct = _multipart(parts)
        resp = _post_raw(client, body, ct)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "request_invalid"
    assert settings.api.max_files_per_ingest == 2


def test_individual_file_over_limit_is_document_invalid(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_bytes_per_document=64)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"x" * 80, "big.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "document_invalid"


def test_aggregate_file_bytes_over_limit_without_content_length(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_total_upload_bytes=100, max_bytes_per_document=80)
    body, _ct = _multipart(
        [
            ("corpus", b"eng", None),
            ("files", b"a" * 60, "a.txt"),
            ("files", b"b" * 60, "b.txt"),
        ]
    )

    async def run() -> None:
        async def chunks() -> AsyncIterator[bytes]:
            # Stream without presenting a trusted Content-Length to the spooler.
            view = memoryview(body)
            step = 16
            for i in range(0, len(view), step):
                yield bytes(view[i : i + step])

        with pytest.raises(AppError) as exc:
            await spool_multipart_upload(
                settings=settings,
                boundary=b"----15d",
                body_chunks=chunks(),
            )
        assert exc.value.code is ErrorCode.REQUEST_INVALID

    asyncio.run(run())
    assert list(settings.paths.staging.glob("*")) == []


def test_unsupported_source_is_document_invalid(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"%PDF-not-really", "notes.docx"),
            ]
        )
        resp = _post_raw(client, body, ct)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "document_invalid"


def test_filename_traversal_cannot_escape_storage(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                (
                    "files",
                    b"Safe document body for traverse test.\n",
                    "../../etc/passwd.txt",
                ),
            ]
        )
        resp = _post_raw(client, body, ct)
        assert resp.status_code == 200
        docs = client.get("/v1/documents", params={"corpus": "eng"}).json()
        assert docs["documents"][0]["source_name"] == "passwd.txt"
    # No escape outside the configured data root, and client basename is never
    # a physical path component.
    assert not (tmp_path / "etc").exists()
    physical = [
        p for p in runtime.settings.paths.corpora.rglob("*") if p.is_file()
    ]
    assert physical
    assert not any(p.name == "passwd.txt" for p in physical)
    assert all(p.name.startswith("doc_") for p in physical if p.suffix == ".txt")


def test_duplicate_filename_alone_is_allowed(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"First distinct body alpha.\n", "same.txt"),
                ("files", b"Second distinct body beta.\n", "same.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
        assert resp.status_code == 200
        assert resp.json()["document_count"] == 2
        docs = client.get("/v1/documents", params={"corpus": "eng"}).json()["documents"]
        assert len(docs) == 2
        assert {d["source_name"] for d in docs} == {"same.txt"}


def test_conflicting_canonical_identity_fails_atomically(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        identical = b"Identical payload for identity conflict.\n"
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", identical, "a.txt"),
                ("files", identical, "b.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "document_invalid"
        ghost = client.get("/v1/documents", params={"corpus": "eng"})
        assert ghost.status_code == 404
        assert ghost.json()["error"]["code"] == "corpus_unknown"


def test_saturated_capacity_without_expensive_body(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    assert runtime.ingest_capacity.try_acquire()
    app = create_app(runtime=runtime)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            before = list(runtime.settings.paths.staging.glob("*"))
            body, ct = _multipart(
                [
                    ("corpus", b"eng", None),
                    ("files", b"x" * 50_000, "big.txt"),
                ]
            )
            resp = _post_raw(client, body, ct)
            after = list(runtime.settings.paths.staging.glob("*"))
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "service_overloaded"
        assert resp.json()["retryable"] is True
        assert after == before
    finally:
        runtime.ingest_capacity.release()


def test_upload_interrupt_before_lease_cleans_staging(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    boundary = b"----15d"
    content_type = "multipart/form-data; boundary=----15d"
    from offline_rag.app.ingest_upload import validate_ingest_http_envelope

    validate_boundary = validate_ingest_http_envelope(
        content_type=content_type,
        content_length=None,
        settings=settings,
    )
    assert validate_boundary == boundary

    async def run() -> AppError:
        async def failing_chunks() -> AsyncIterator[bytes]:
            # Begin a file part then abort before completion / lease.
            prefix = (
                b"------15d\r\n"
                b'Content-Disposition: form-data; name="files"; filename="a.txt"\r\n'
                b"Content-Type: application/octet-stream\r\n\r\n"
                b"partial-"
            )
            yield prefix
            raise RuntimeError("client disconnect")

        with pytest.raises(AppError) as exc:
            await spool_multipart_upload(
                settings=settings,
                boundary=boundary,
                body_chunks=failing_chunks(),
            )
        return exc.value

    err = asyncio.run(run())
    assert err.code is ErrorCode.REQUEST_INVALID
    assert list(settings.paths.staging.glob("*")) == []
    assert not current_pointer_path(settings.paths.corpora, "eng").exists()
    # Interrupted upload must not leave a held live-owner lease.
    settings.paths.locks.mkdir(parents=True, exist_ok=True)
    probe = CorpusMutationLease(settings, "eng")
    probe.acquire()
    probe.release()


def test_first_ingest_visibility_only_at_publication(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    seen_pre_publish: list[int] = []

    def before_stage(name: str) -> None:
        if name == "publish":
            # Registry read only — do not nest TestClient/lifespan here.
            try:
                runtime.publication.resolve("eng")
                seen_pre_publish.append(1)
            except AppError as exc:
                assert exc.code is ErrorCode.CORPUS_UNKNOWN
                seen_pre_publish.append(0)

    runtime.product_ingest_hooks = ProductIngestHooks(before_stage=before_stage)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Visibility gate document one.\n", "a.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
        assert resp.status_code == 200
        docs = client.get("/v1/documents", params={"corpus": "eng"})
        assert docs.status_code == 200
    assert seen_pre_publish == [0]


def test_published_n_visible_while_n1_building(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Published document N content.\n", "n.txt"),
            ]
        )
        first = _post_raw(client, body, ct)
        assert first.status_code == 200
        snap_n = first.json()["snapshot_id"]

    hold = threading.Event()
    released = threading.Event()

    def after_lease(corpus: str, candidate_root: Path) -> None:
        hold.set()
        released.wait(timeout=5)

    runtime.product_ingest_hooks = ProductIngestHooks(after_lease_acquired=after_lease)
    results: dict[str, object] = {}

    def reader() -> None:
        hold.wait(timeout=5)
        try:
            snap = runtime.publication.resolve("eng")
            results["snapshot_id"] = snap.snapshot_id
            results["docs"] = [d["document_id"] for d in snap.document_summaries()]
        except Exception as exc:  # noqa: BLE001
            results["error"] = exc
        finally:
            released.set()

    thread = threading.Thread(target=reader)
    thread.start()
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Candidate N+1 different content.\n", "n1.txt"),
            ]
        )
        second = _post_raw(client, body, ct)
        assert second.status_code == 200
    thread.join(timeout=5)
    assert results.get("snapshot_id") == snap_n
    assert results.get("error") is None


def test_stage_failure_leaves_published_n(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Stable published document.\n", "a.txt"),
            ]
        )
        first = _post_raw(client, body, ct)
        assert first.status_code == 200
        snap_n = first.json()["snapshot_id"]

    def before_stage(name: str) -> None:
        if name == "chunk":
            raise AppError(ErrorCode.INGEST_FAILED)

    runtime.product_ingest_hooks = ProductIngestHooks(before_stage=before_stage)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Replacement that will fail chunk.\n", "b.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
        assert resp.status_code == 500
        docs = client.get("/v1/documents", params={"corpus": "eng"})
        assert docs.status_code == 200
        assert docs.json()["snapshot_id"] == snap_n
        assert docs.json()["documents"][0]["source_name"] == "a.txt"


def test_publish_failure_before_pointer_leaves_n(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Original published document.\n", "a.txt"),
            ]
        )
        first = _post_raw(client, body, ct)
        snap_n = first.json()["snapshot_id"]

        def before_stage(name: str) -> None:
            if name == "publish":
                raise AppError(ErrorCode.INGEST_FAILED)

        # Install after first publish; TestClient lifespan stays open so the
        # runtime/publication object remains the live process instance.
        runtime.product_ingest_hooks = ProductIngestHooks(before_stage=before_stage)
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"New candidate that fails publish.\n", "b.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
        assert resp.status_code == 500
        docs = client.get("/v1/documents", params={"corpus": "eng"})
        assert docs.json()["snapshot_id"] == snap_n


def test_successful_replace_matches_uploaded_set_exactly(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Doc A first generation.\n", "a.txt"),
                ("files", b"Doc B first generation.\n", "b.txt"),
            ]
        )
        first = _post_raw(client, body, ct)
        assert first.status_code == 200
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Doc B second generation only.\n", "b.txt"),
                ("files", b"Doc C newly introduced.\n", "c.txt"),
            ]
        )
        second = _post_raw(client, body, ct)
        assert second.status_code == 200
        docs = client.get("/v1/documents", params={"corpus": "eng"}).json()["documents"]
        names = sorted(d["source_name"] for d in docs)
        assert names == ["b.txt", "c.txt"]
        # Omitted previously published document disappears.
        assert all(d["source_name"] != "a.txt" for d in docs)


def test_repeated_identical_replacement_same_snapshot_id(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    payload = [
        ("corpus", b"eng", None),
        ("files", b"Deterministic replacement body.\n", "a.txt"),
    ]
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(payload)
        first = _post_raw(client, body, ct)
        body, ct = _multipart(payload)
        second = _post_raw(client, body, ct)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["snapshot_id"] == second.json()["snapshot_id"]


def test_dense_indexing_reuses_runtime_embedder_and_qdrant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    assert runtime.resources is not None
    seen: dict[str, object] = {}

    import offline_rag.app.ingest as ingest_mod
    from offline_rag.dense.pipeline import run_indexing as real_run_indexing

    def wrapped_run_indexing(**kwargs):  # type: ignore[no-untyped-def]
        seen["embedder"] = kwargs.get("embedder")
        seen["backend"] = kwargs.get("backend")
        return real_run_indexing(**kwargs)

    monkeypatch.setattr(ingest_mod, "run_indexing", wrapped_run_indexing)

    from offline_rag.app.ingest_upload import SpooledIngestUpload, SpooledUploadFile
    from offline_rag.core.ids import document_id_from_bytes

    files_root = settings.paths.staging / "manual" / "files"
    files_root.mkdir(parents=True)
    payload = b"Reuse runtime resources document.\n"
    doc_id = document_id_from_bytes(payload)
    storage_name = f"{doc_id}.txt"
    path = files_root / storage_name
    path.write_bytes(payload)
    upload = SpooledIngestUpload(
        upload_id="manual",
        corpus_name="eng",
        staging_root=settings.paths.staging / "manual",
        files_root=files_root,
        files=[
            SpooledUploadFile(
                absolute_path=path,
                storage_name=storage_name,
                client_filename="a.txt",
                source_name="a.txt",
                document_id=doc_id,
                size_bytes=path.stat().st_size,
                media_type="text/plain",
            )
        ],
    )
    result = run_product_replace_ingest(runtime, upload)
    assert result.document_count == 1
    assert seen["embedder"] is runtime.resources.embedder
    assert seen["backend"] is runtime.resources.qdrant
    runtime.shutdown()


def test_health_responsive_during_blocking_scientific_stage(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    block = threading.Event()
    entered = threading.Event()

    def before_stage(name: str) -> None:
        if name == "ingest":
            entered.set()
            block.wait(timeout=10)

    runtime.product_ingest_hooks = ProductIngestHooks(before_stage=before_stage)
    runtime.start()
    app = create_app(runtime=runtime)
    body, ct = _multipart(
        [
            ("corpus", b"eng", None),
            ("files", b"Blocking stage document.\n", "a.txt"),
        ]
    )

    async def run() -> None:
        # Runtime already started; avoid lifespan so shutdown is under our control.
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            ingest_task = asyncio.create_task(
                client.post(
                    "/v1/ingest", content=body, headers={"Content-Type": ct}
                )
            )
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.05)
            assert entered.is_set()
            live = await client.get("/health/live")
            assert live.status_code == 200
            block.set()
            ingest_resp = await ingest_task
            assert ingest_resp.status_code == 200

    try:
        asyncio.run(run())
    finally:
        runtime.shutdown()


def test_success_body_normative_contract_and_openapi(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"OpenAPI contract document.\n", "a.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
        assert resp.status_code == 200
        payload = resp.json()
        assert set(payload.keys()) == {"corpus", "snapshot_id", "document_count"}
        assert payload["corpus"] == "eng"
        assert isinstance(payload["snapshot_id"], str)
        assert payload["document_count"] == 1

        paths = set(client.get("/openapi.json").json().get("paths", {}))
        assert "/v1/ingest" in paths
        for forbidden in (
            "/v1/query",
            "/v1/trace/{trace_id}",
            "/eval/run",
            "/ingest",
            "/query",
        ):
            assert forbidden not in paths


def test_unexpected_path_field_rejected(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("path", b"/etc/passwd", None),
                ("files", b"Should not ingest with path field.\n", "a.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "request_invalid"


def test_corpus_busy_when_lease_held(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    settings.paths.locks.mkdir(parents=True, exist_ok=True)
    holder = CorpusMutationLease(settings, "eng")
    holder.acquire()
    try:
        app = create_app(runtime=runtime)
        with TestClient(app, raise_server_exceptions=False) as client:
            body, ct = _multipart(
                [
                    ("corpus", b"eng", None),
                    ("files", b"Busy lease document.\n", "a.txt"),
                ]
            )
            resp = _post_raw(client, body, ct)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "corpus_busy"
    finally:
        holder.release()


def test_client_filename_is_metadata_not_storage_name(tmp_path: Path) -> None:
    """Changing client filename must not change physical storage derivation."""
    settings = _settings(tmp_path)
    content = b"Identical bytes; only client filename differs.\n"

    async def spool(filename: str):
        body, _ct = _multipart(
            [("corpus", b"eng", None), ("files", content, filename)]
        )

        async def chunks() -> AsyncIterator[bytes]:
            yield body

        return await spool_multipart_upload(
            settings=settings,
            boundary=b"----15d",
            body_chunks=chunks(),
        )

    first = asyncio.run(spool("alpha-name.txt"))
    # Distinct staging roots per upload_id — clean between spools.
    cleanup = first.staging_root
    storage_a = first.files[0].storage_name
    source_a = first.files[0].source_name
    assert storage_a.startswith("doc_")
    assert storage_a.endswith(".txt")
    assert "alpha-name" not in storage_a
    assert source_a == "alpha-name.txt"
    assert first.files[0].absolute_path.name == storage_a

    import shutil

    shutil.rmtree(cleanup)

    second = asyncio.run(spool("beta-name.txt"))
    assert second.files[0].storage_name == storage_a
    assert second.files[0].document_id == first.files[0].document_id
    assert second.files[0].source_name == "beta-name.txt"
    assert "beta-name" not in second.files[0].storage_name
    shutil.rmtree(second.staging_root)


def test_invalid_corpus_first_aborts_before_file_spool(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pulled: list[int] = []

    async def run() -> AppError:
        async def chunks() -> AsyncIterator[bytes]:
            # Include the terminating boundary so the corpus part completes in
            # this chunk; subsequent file bytes must never be pulled/spooled.
            corpus_part = (
                b"------15d\r\n"
                b'Content-Disposition: form-data; name="corpus"\r\n\r\n'
                b"bad/name\r\n"
                b"------15d\r\n"
            )
            pulled.append(1)
            yield corpus_part
            pulled.append(2)
            yield (
                b'Content-Disposition: form-data; name="files"; '
                b'filename="huge.txt"\r\n'
                b"Content-Type: application/octet-stream\r\n\r\n"
                + (b"x" * 1024)
                + b"\r\n------15d--\r\n"
            )

        with pytest.raises(AppError) as exc:
            await spool_multipart_upload(
                settings=settings,
                boundary=b"----15d",
                body_chunks=chunks(),
            )
        return exc.value

    err = asyncio.run(run())
    assert err.code is ErrorCode.REQUEST_INVALID
    assert pulled == [1]
    assert list(settings.paths.staging.glob("*")) == []


def test_files_first_then_valid_corpus_still_succeeds(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("files", b"File before corpus still valid.\n", "a.txt"),
                ("files", b"Second file before corpus.\n", "b.txt"),
                ("corpus", b"manuals", None),
            ]
        )
        resp = _post_raw(client, body, ct)
    assert resp.status_code == 200
    assert resp.json()["corpus"] == "manuals"
    assert resp.json()["document_count"] == 2


def test_content_length_not_file_byte_bound(tmp_path: Path) -> None:
    """Content-Length is syntactic only; streamed file bytes remain authoritative."""
    from offline_rag.app.ingest_upload import validate_ingest_http_envelope

    settings = _settings(tmp_path)
    # Previously rejected by the unsafe 100MiB+2MiB framing assumption.
    boundary = validate_ingest_http_envelope(
        content_type="multipart/form-data; boundary=abc",
        content_length="200000000",
        settings=settings,
    )
    assert boundary == b"abc"
    with pytest.raises(AppError) as exc:
        validate_ingest_http_envelope(
            content_type="multipart/form-data; boundary=abc",
            content_length="-1",
            settings=settings,
        )
    assert exc.value.code is ErrorCode.REQUEST_INVALID

    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Small authoritative body.\n", "a.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
    assert resp.status_code == 200


def test_multipart_reorder_same_snapshot_id(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    a = b"Document A unique payload for reorder.\n"
    b = b"Document B unique payload for reorder.\n"
    with TestClient(app, raise_server_exceptions=False) as client:
        body_ab, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", a, "a.txt"),
                ("files", b, "b.txt"),
            ]
        )
        first = _post_raw(client, body_ab, ct)
        assert first.status_code == 200
        body_ba, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b, "b.txt"),
                ("files", a, "a.txt"),
            ]
        )
        second = _post_raw(client, body_ba, ct)
        assert second.status_code == 200
        assert first.json()["snapshot_id"] == second.json()["snapshot_id"]
        docs = client.get("/v1/documents", params={"corpus": "eng"}).json()["documents"]
        assert sorted(d["source_name"] for d in docs) == ["a.txt", "b.txt"]


def test_typed_document_parse_error_is_document_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from offline_rag.ingestion.base import DocumentParseError

    runtime = _runtime(_settings(tmp_path))

    def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise DocumentParseError("typed unparseable document")

    monkeypatch.setattr(
        "offline_rag.ingestion.text_parser.TextParser.parse",
        boom,
    )
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Looks like text but parse will fail.\n", "a.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "document_invalid"
    assert "typed unparseable document" not in resp.text
    assert "DocumentParseError" not in resp.text


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: RuntimeError("synthetic parser runtime fault"),
        lambda: ValueError("synthetic parser value fault"),
    ],
)
def test_unexpected_parser_exception_is_ingest_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exc_factory,
) -> None:
    runtime = _runtime(_settings(tmp_path))
    raised = exc_factory()

    def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise raised

    monkeypatch.setattr(
        "offline_rag.ingestion.text_parser.TextParser.parse",
        boom,
    )
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Looks like text but runtime will fail.\n", "a.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "ingest_failed"
    assert str(raised) not in resp.text
    assert type(raised).__name__ not in resp.text


def test_internal_ingestion_failure_is_ingest_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(_settings(tmp_path))

    def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("disk full synthetic")

    monkeypatch.setattr(
        "offline_rag.ingestion.pipeline.write_parsed_document",
        boom,
    )
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Valid text that fails on persistence.\n", "a.txt"),
            ]
        )
        resp = _post_raw(client, body, ct)
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "ingest_failed"
    assert "disk full" not in resp.text
    assert "OSError" not in resp.text

