"""Slice 16A — workspace persistence foundation (no HTTP/UI)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.paths import ensure_data_directories
from offline_rag.app.publication import (
    ProductPublicationRegistry,
    current_pointer_path,
    snapshot_manifest_path,
)
from offline_rag.app.snapshot import CanonicalSnapshotManifest, compute_snapshot_id
from offline_rag.app.workspace.journal import (
    EmptyTransitionCoordinator,
    EmptyTransitionPhase,
)
from offline_rag.app.workspace.models import (
    ManagedOperationKind,
    ManagedOperationStatus,
    SourceVersionRecord,
    WorkspaceRecord,
    WorkspaceStatus,
    advance_revision,
    document_id_for_content,
    new_empty_workspace,
    new_source_id,
    serialize_revision,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.retirement import (
    list_snapshot_manifests,
    restore_current_publication_pointer,
    retire_current_publication,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.vault import RawSourceVault
from offline_rag.chunking.tokenize import TiktokenTokenCounter
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.domain.chunking import ChunkSetManifest
from offline_rag.domain.corpus import CorpusDocumentEntry, CorpusManifest
from offline_rag.domain.indexing import DenseIndexManifest, LexicalIndexManifest
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.rerank.config_hash import build_reranker_config_hash

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"


class _FakeQdrant:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def collection_exists(self, name: str) -> bool:
        return name in self.counts

    def count(self, name: str) -> int:
        return int(self.counts[name])


def _settings(tmp_path: Path) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
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


def _config_hashes(settings: AppSettings) -> dict[str, str]:
    counter = TiktokenTokenCounter(
        encoding=settings.chunking.tokenizer.encoding,
        artifacts_path=settings.paths.tokenizer_artifacts,
    )
    return {
        "embedding_config_hash": build_embedding_config_hash(settings),
        "index_config_hash": build_index_config_hash(settings),
        "lexical_config_hash": build_lexical_config_hash(settings),
        "fusion_config_hash": build_fusion_config_hash(settings),
        "reranker_config_hash": build_reranker_config_hash(settings),
        "context_config_hash": build_context_config_hash(
            settings, token_counter=counter
        ),
    }


def _publish_minimal(
    settings: AppSettings,
    corpus_name: str,
    *,
    qdrant: _FakeQdrant | None = None,
) -> tuple[ProductPublicationRegistry, str, CanonicalSnapshotManifest]:
    from offline_rag.lexical.backend import (
        LexicalDocumentInput,
        LocalInvertedIndexBackend,
    )

    q = qdrant or _FakeQdrant()
    hashes = _config_hashes(settings)
    now = datetime.now(tz=UTC)
    corpus_id = "corpus_ws16a"
    chunk_set_id = "chunkset_ws16a"
    dense_index_id = "denseindex_ws16a"
    lexical_index_id = "lexical_ws16a"
    collection_name = "col_ws16a"
    corpus_manifest_name = f"{corpus_id}.json"
    chunk_manifest_name = f"{chunk_set_id}.json"
    dense_manifest_name = f"{dense_index_id}.json"
    lexical_manifest_name = f"{lexical_index_id}.json"

    corpus = CorpusManifest(
        corpus_id=corpus_id,
        corpus_hash="corphash_ws16a",
        created_at=now,
        config_hash="cfg_corpus",
        documents=[
            CorpusDocumentEntry(
                document_id="doc_ws16a",
                source_path="/secret/absolute/path/spec.pdf",
                source_name="spec.pdf",
                source_content_hash="ch_ws16a",
                source_size_bytes=12,
                source_media_type="application/pdf",
                parser_name="docling_pdf",
                parser_version="v1",
                block_count=1,
                processed_artifact="processed/x.json",
                processed_artifact_hash="pah_1",
                parsed_artifact_id="parsed_1",
                parse_config_hash="cfg_parse",
            )
        ],
    )
    chunk = ChunkSetManifest(
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
        chunk_config_hash="cfg_chunk",
        chunker_version="v1",
        tokenizer_name="tiktoken",
        tokenizer_encoding="cl100k_base",
        created_at=now,
    )
    dense = DenseIndexManifest(
        index_id=dense_index_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        embedding_config_hash=hashes["embedding_config_hash"],
        index_config_hash=hashes["index_config_hash"],
        index_contract_version="dense-index-v1",
        embedding_text_strategy="plain",
        embedding_text_contract="plain-v1",
        embedding_model_id="model",
        embedding_model_revision="rev",
        embedding_dimension=8,
        normalize=True,
        similarity_metric="cosine",
        backend="qdrant_local",
        backend_contract="qdrant-local-v1",
        collection_name=collection_name,
        expected_child_count=1,
        indexed_child_count=1,
        created_at=now,
    )
    lexical = LexicalIndexManifest(
        lexical_index_id=lexical_index_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        lexical_config_hash=hashes["lexical_config_hash"],
        text_strategy="plain",
        text_contract="plain-v1",
        analyzer_strategy="technical",
        analyzer_contract="technical-v1",
        bm25_contract="bm25-v1",
        bm25_k1=1.2,
        bm25_b=0.75,
        bm25_idf="standard",
        bm25_query_tf="raw",
        backend="local_inverted",
        backend_contract="local-inverted-index-v1",
        expected_child_count=1,
        indexed_child_count=1,
        document_count=1,
        vocabulary_size=1,
        avgdl=1.0,
        physical_index_relpath=f"{lexical_index_id}",
        created_at=now,
    )
    settings.paths.manifests.mkdir(parents=True, exist_ok=True)
    settings.paths.chunk_manifests.mkdir(parents=True, exist_ok=True)
    settings.paths.index_manifests.mkdir(parents=True, exist_ok=True)
    settings.paths.lexical_index_manifests.mkdir(parents=True, exist_ok=True)
    settings.paths.lexical_indexes.mkdir(parents=True, exist_ok=True)
    atomic_write_text(settings.paths.manifests / corpus_manifest_name, corpus.model_dump_json())
    atomic_write_text(
        settings.paths.chunk_manifests / chunk_manifest_name, chunk.model_dump_json()
    )
    atomic_write_text(
        settings.paths.index_manifests / dense_manifest_name, dense.model_dump_json()
    )
    atomic_write_text(
        settings.paths.lexical_index_manifests / lexical_manifest_name,
        lexical.model_dump_json(),
    )
    lexical_path = settings.paths.lexical_indexes / lexical_index_id
    if lexical_path.exists():
        shutil.rmtree(lexical_path)
    LocalInvertedIndexBackend(settings.paths.lexical_indexes).build(
        lexical_index_id,
        [
            LexicalDocumentInput(
                chunk_id="chunk_1",
                terms=["offline", "rag"],
                document_id="doc_ws16a",
            )
        ],
        chunk_set_id=chunk_set_id,
        lexical_config_hash=hashes["lexical_config_hash"],
    )
    q.counts[collection_name] = 1
    identity = CanonicalSnapshotManifest(
        corpus_id=corpus_id,
        corpus_manifest=corpus_manifest_name,
        chunk_set_id=chunk_set_id,
        chunk_manifest=chunk_manifest_name,
        dense_index_id=dense_index_id,
        dense_index_manifest=dense_manifest_name,
        lexical_index_id=lexical_index_id,
        lexical_index_manifest=lexical_manifest_name,
        **hashes,
    )
    registry = ProductPublicationRegistry(settings, qdrant=q)
    snapshot_id = registry.publish(
        corpus_name, identity, require_current_config_match=True
    )
    return registry, snapshot_id, identity


# --- 1. Workspace model invariants ---


def test_workspace_empty_and_active_invariants() -> None:
    empty = new_empty_workspace(title="Empty Desk")
    assert empty.status is WorkspaceStatus.EMPTY
    assert empty.sources == []
    assert empty.current_snapshot_id is None
    assert empty.title != empty.backing_corpus_name

    with pytest.raises(ValidationError):
        WorkspaceRecord.model_validate(
            {
                **empty.model_dump(mode="python"),
                "current_snapshot_id": "snap_x",
            }
        )

    bad = {
        **empty.model_dump(mode="python"),
        "status": WorkspaceStatus.ACTIVE,
        "current_snapshot_id": "snap_x",
        "sources": [],
    }
    with pytest.raises(ValidationError):
        WorkspaceRecord.model_validate(bad)

    mixed = {
        **empty.model_dump(mode="python"),
        "status": WorkspaceStatus.EMPTY,
        "sources": [
            SourceVersionRecord(
                source_id="src_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                version=1,
                display_name="x.pdf",
                vault_object_id="vobj_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                created_at=datetime.now(tz=UTC),
                active_from_revision=1,
            ).model_dump(mode="python")
        ],
    }
    with pytest.raises(ValidationError):
        WorkspaceRecord.model_validate(mixed)


# --- 2. Revision semantics ---


def test_metadata_revision_independent_of_snapshot(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = WorkspaceStore(settings)
    empty = store.create(new_empty_workspace(title="Rev Desk"))
    # Simulate published active workspace without real registry.
    active = empty.model_copy(
        update={
            "status": WorkspaceStatus.ACTIVE,
            "current_snapshot_id": "snap_fixed",
            "sources": [
                SourceVersionRecord(
                    source_id=new_source_id(),
                    version=1,
                    display_name="a.pdf",
                    vault_object_id="vobj_" + "a" * 32,
                    created_at=datetime.now(tz=UTC),
                    active_from_revision=1,
                    active_from_snapshot_id="snap_fixed",
                )
            ],
            "revision": 1,
        }
    )
    store.save(active)
    patched = store.apply_metadata_patch(
        active.workspace_id, expected_revision=1, title="Renamed Desk"
    )
    assert patched.revision == 2
    assert patched.current_snapshot_id == "snap_fixed"
    assert serialize_revision(patched.revision) == "2"
    assert advance_revision(2) == 3


# --- 3. Source identity ---


def test_source_version_and_byte_identical_document_id(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    content = b"identical-bytes"
    doc_a = document_id_for_content(content)
    doc_b = document_id_for_content(content)
    assert doc_a == doc_b
    assert document_id_for_content(b"other") != doc_a

    store = WorkspaceStore(settings)
    vault = RawSourceVault(settings.paths.workspaces)
    ops = ManagedOperationStore(settings)
    ws = store.create(new_empty_workspace(title="Sources"))
    meta1 = vault.put_bytes(ws.workspace_id, content, display_name="v1.pdf")
    meta2 = vault.put_bytes(ws.workspace_id, content, display_name="v1-again.pdf")
    assert meta1.content_hash == meta2.content_hash
    source_id = new_source_id()
    v1 = SourceVersionRecord(
        source_id=source_id,
        version=1,
        display_name="v1.pdf",
        content_hash=meta1.content_hash,
        document_id=doc_a,
        vault_object_id=meta1.object_id,
        created_at=datetime.now(tz=UTC),
        active_from_revision=1,
    )
    v2 = v1.model_copy(
        update={
            "version": 2,
            "display_name": "v1-again.pdf",
            "vault_object_id": meta2.object_id,
            "document_id": doc_b,
        }
    )
    assert v2.source_id == source_id
    assert v2.version == 2
    assert v2.document_id == v1.document_id

    payload = {"source_id": source_id, "vault_object_id": meta2.object_id}
    first = ops.begin(
        workspace_id=ws.workspace_id,
        idempotency_key="replace-1",
        kind=ManagedOperationKind.SOURCE_REPLACE,
        request_payload=payload,
    )
    second = ops.begin(
        workspace_id=ws.workspace_id,
        idempotency_key="replace-1",
        kind=ManagedOperationKind.SOURCE_REPLACE,
        request_payload=payload,
    )
    assert first.operation_id == second.operation_id


# --- 4. Workspace persistence ---


def test_workspace_persistence_round_trip_and_corrupt(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = WorkspaceStore(settings)
    created = store.create(new_empty_workspace(title="Persist"))
    loaded = store.get(created.workspace_id)
    assert loaded.workspace_id == created.workspace_id
    assert loaded.status is WorkspaceStatus.EMPTY

    with pytest.raises(AppError) as unknown:
        store.get("ws_" + "f" * 32)
    assert unknown.value.code is ErrorCode.WORKSPACE_UNKNOWN

    path = store.workspace_path(created.workspace_id)
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(AppError) as corrupt:
        store.get(created.workspace_id)
    assert corrupt.value.code is ErrorCode.WORKSPACE_STATE_UNAVAILABLE


# --- 5. Raw vault ---


def test_raw_vault_store_load_and_path_safety(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = WorkspaceStore(settings)
    vault = RawSourceVault(settings.paths.workspaces)
    ws = store.create(new_empty_workspace(title="Vault"))
    meta = vault.put_bytes(
        ws.workspace_id, b"hello-vault", display_name="report.pdf", content_type="application/pdf"
    )
    assert meta.object_id.startswith("vobj_")
    assert meta.display_name == "report.pdf"
    loaded = vault.load_bytes(ws.workspace_id, meta.object_id)
    assert loaded == b"hello-vault"
    # Physical path must not depend on display filename.
    obj_path = settings.paths.workspaces / ws.workspace_id / "vault" / "objects" / meta.object_id
    assert obj_path.exists()
    assert "report.pdf" not in str(obj_path)

    with pytest.raises(AppError) as bad_name:
        vault.put_bytes(ws.workspace_id, b"x", display_name="../escape.pdf")
    assert bad_name.value.code is ErrorCode.REQUEST_INVALID

    with pytest.raises(AppError) as abs_name:
        vault.put_bytes(ws.workspace_id, b"x", display_name="/tmp/x.pdf")
    assert abs_name.value.code is ErrorCode.REQUEST_INVALID


# --- 6. Operation / idempotency ---


def test_operation_idempotency_and_terminal_states(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = WorkspaceStore(settings)
    ops = ManagedOperationStore(settings)
    ws = store.create(new_empty_workspace(title="Ops"))
    payload = {"title": "Ops", "kind": "create"}
    a = ops.begin(
        workspace_id=ws.workspace_id,
        idempotency_key="k1",
        kind=ManagedOperationKind.WORKSPACE_CREATE,
        request_payload=payload,
    )
    b = ops.begin(
        workspace_id=ws.workspace_id,
        idempotency_key="k1",
        kind=ManagedOperationKind.WORKSPACE_CREATE,
        request_payload=payload,
    )
    assert a.operation_id == b.operation_id

    with pytest.raises(AppError) as conflict:
        ops.begin(
            workspace_id=ws.workspace_id,
            idempotency_key="k1",
            kind=ManagedOperationKind.WORKSPACE_CREATE,
            request_payload={"title": "Other"},
        )
    assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

    terminal = ops.update_status(
        ws.workspace_id,
        a.operation_id,
        ManagedOperationStatus.SUCCEEDED,
        result_summary="ok",
    )
    assert terminal.status is ManagedOperationStatus.SUCCEEDED
    interrupted = ops.update_status(
        ws.workspace_id, a.operation_id, ManagedOperationStatus.INTERRUPTED
    )
    assert interrupted.status is ManagedOperationStatus.INTERRUPTED
    reloaded = ops.get(ws.workspace_id, a.operation_id)
    assert reloaded.status is ManagedOperationStatus.INTERRUPTED


# --- 7. Tombstone ---


def test_tombstone_excludes_from_active_listing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = WorkspaceStore(settings)
    ws = store.create(new_empty_workspace(title="Tomb"))
    store.tombstone(ws.workspace_id, expected_revision=1)
    with pytest.raises(AppError) as unknown:
        store.get(ws.workspace_id)
    assert unknown.value.code is ErrorCode.WORKSPACE_UNKNOWN
    historical = store.get(ws.workspace_id, include_tombstoned=True)
    assert historical.status is WorkspaceStatus.TOMBSTONED
    assert historical.current_snapshot_id is None
    assert all(r.workspace_id != ws.workspace_id for r in store.list_active())


# --- 8. Publication retirement ---


def test_publication_retirement_preserves_snapshots(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _identity = _publish_minimal(settings, "manuals")
    pointer = current_pointer_path(settings.paths.corpora, "manuals")
    snap = snapshot_manifest_path(settings.paths.corpora, "manuals", snapshot_id)
    assert pointer.exists()
    assert snap.exists()
    resolved = registry.resolve("manuals")
    assert resolved.snapshot_id == snapshot_id

    record = retire_current_publication(settings, "manuals")
    assert record.last_snapshot_id == snapshot_id
    assert not pointer.exists()
    assert snap.exists()
    assert list_snapshot_manifests(settings, "manuals")
    with pytest.raises(AppError) as unresolved:
        registry.resolve("manuals")
    assert unresolved.value.code is ErrorCode.CORPUS_UNKNOWN
    assert registry.published_snapshot_id("manuals") is None

    # Re-publish after retirement establishes a future current snapshot.
    restore_current_publication_pointer(settings, "manuals", snapshot_id)
    assert registry.resolve("manuals").snapshot_id == snapshot_id


# --- 9. Crash / recovery ---


def test_empty_transition_recovery_points(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_minimal(settings, "wsc_recoverydemo")
    # Use workspace whose backing corpus matches published corpus by constructing manually.
    store = WorkspaceStore(settings)
    vault = RawSourceVault(settings.paths.workspaces)
    empty = new_empty_workspace(title="Recovery Desk")
    # Force backing corpus to the published name for this foundation test.
    empty = empty.model_copy(update={"backing_corpus_name": "wsc_recoverydemo"})
    store.create(empty)
    content = b"one-source"
    meta = vault.put_bytes(empty.workspace_id, content, display_name="only.pdf")
    active = empty.model_copy(
        update={
            "status": WorkspaceStatus.ACTIVE,
            "current_snapshot_id": snapshot_id,
            "revision": 2,
            "sources": [
                SourceVersionRecord(
                    source_id=new_source_id(),
                    version=1,
                    display_name="only.pdf",
                    content_hash=meta.content_hash,
                    document_id=document_id_for_content(content),
                    vault_object_id=meta.object_id,
                    created_at=datetime.now(tz=UTC),
                    active_from_revision=2,
                    active_from_snapshot_id=snapshot_id,
                )
            ],
            "updated_at": datetime.now(tz=UTC),
        }
    )
    store.save(active)
    coord = EmptyTransitionCoordinator(settings, store)

    # Interrupt after intent only → recover A
    journal = coord.begin(active.workspace_id, expected_revision=2)
    assert journal.phase is EmptyTransitionPhase.INTENT_RECORDED
    assert coord.recover(active.workspace_id) == "A"
    assert store.get(active.workspace_id).status is WorkspaceStatus.ACTIVE
    assert registry.published_snapshot_id("wsc_recoverydemo") == snapshot_id
    assert coord.recover(active.workspace_id) == "clean"  # idempotent

    # Interrupt after retirement → recover A (restore pointer)
    store.save(active)
    coord.begin(active.workspace_id, expected_revision=2)
    coord.step_retire_publication(active.workspace_id)
    assert registry.published_snapshot_id("wsc_recoverydemo") is None
    assert snapshot_manifest_path(
        settings.paths.corpora, "wsc_recoverydemo", snapshot_id
    ).exists()
    assert coord.recover(active.workspace_id) == "A"
    assert registry.published_snapshot_id("wsc_recoverydemo") == snapshot_id

    # Complete transition → B; recover clean afterward
    store.save(active)
    coord.begin(active.workspace_id, expected_revision=2)
    coord.step_retire_publication(active.workspace_id)
    # Interrupt after workspace emptied but before commit clear
    coord.step_empty_workspace(active.workspace_id)
    assert store.get(active.workspace_id).status is WorkspaceStatus.EMPTY
    assert store.get(active.workspace_id).current_snapshot_id is None
    assert coord.recover(active.workspace_id) == "B"
    assert registry.published_snapshot_id("wsc_recoverydemo") is None
    assert snapshot_manifest_path(
        settings.paths.corpora, "wsc_recoverydemo", snapshot_id
    ).exists()
    assert coord.recover(active.workspace_id) == "clean"

    # Full commit path
    # Re-publish and re-activate for commit test
    restore_current_publication_pointer(settings, "wsc_recoverydemo", snapshot_id)
    store.save(active)
    coord.begin(active.workspace_id, expected_revision=2)
    done = coord.step_commit(active.workspace_id)
    assert done.phase is EmptyTransitionPhase.COMMITTED
    assert not coord.journal_path(active.workspace_id).exists()
    emptied = store.get(active.workspace_id)
    assert emptied.status is WorkspaceStatus.EMPTY
    assert emptied.sources == []
    assert emptied.current_snapshot_id is None
    with pytest.raises(AppError):
        registry.resolve("wsc_recoverydemo")


# --- 10. Slice-15 regression ---


def test_slice15_publish_resolve_unchanged_and_no_empty_ingest(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, identity = _publish_minimal(settings, "manuals")
    assert compute_snapshot_id(identity) == snapshot_id
    assert registry.resolve("manuals").snapshot_id == snapshot_id
    # Retire then republish ordinary path still works
    retire_current_publication(settings, "manuals")
    restore_current_publication_pointer(settings, "manuals", snapshot_id)
    assert registry.resolve("manuals").snapshot_id == snapshot_id
    # No empty-ingest API introduced on registry
    assert not hasattr(registry, "publish_empty")
