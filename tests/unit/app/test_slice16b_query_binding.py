"""Slice 16B — workspace query binding (S16-D08 / S16-D12 / S16-D13).

The workspace record is the authority for which snapshot a workspace reads.
``run_workspace_query`` must bind ``workspace.current_snapshot_id`` directly and
must never re-resolve ``current.json`` the way the product path does, or an
unrelated publication on the backing corpus would silently answer for it.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.paths import ensure_data_directories
from offline_rag.app.publication import ProductPublicationRegistry
from offline_rag.app.query import (
    BoundSnapshotQueryOutcome,
    run_product_query,
    run_workspace_query,
)
from offline_rag.app.query_binding import build_snapshot_query_binding
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.snapshot import CanonicalSnapshotManifest, CorpusReadSnapshot
from offline_rag.app.workspace.models import (
    SourceVersionRecord,
    WorkspaceRecord,
    WorkspaceStatus,
    backing_corpus_name_for,
    new_source_id,
    new_workspace_id,
    utc_now,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.chunking import TiktokenTokenCounter
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.domain.chunking import ChunkSetManifest
from offline_rag.domain.corpus import CorpusDocumentEntry, CorpusManifest
from offline_rag.domain.indexing import DenseIndexManifest, LexicalIndexManifest
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.rerank.config_hash import build_reranker_config_hash
from offline_rag.rerank.fake import FakeReranker

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"


class _FakeQdrant:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def collection_exists(self, name: str) -> bool:
        return name in self.counts

    def count(self, name: str) -> int:
        return int(self.counts[name])

    def close(self) -> None:
        return None


class _Closeable:
    def close(self) -> None:
        return None


def _settings(tmp_path: Path) -> AppSettings:
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
    reranker = settings.reranker.model_copy(
        update={"enabled": True, "implementation": "fake"}
    )
    settings = settings.model_copy(
        update={"generation": generation, "reranker": reranker}
    )
    ensure_data_directories(settings)
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(
        settings.paths.docling_artifacts, docling_version="test"
    )
    if not (TIKTOKEN_SRC / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)
    return settings


def _runtime(settings: AppSettings, qdrant: _FakeQdrant) -> ApplicationRuntime:
    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: FakeEmbedder(dimension=8, normalize=True),
            reranker=lambda _s: FakeReranker(),
            generator_client=lambda _s: _Closeable(),
            qdrant=lambda _s: qdrant,
        ),
    )
    runtime.start()
    return runtime


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


def _publish(
    settings: AppSettings, corpus_name: str, *, tag: str, qdrant: _FakeQdrant
) -> tuple[str, str]:
    """Publish one complete grounded-capable snapshot. Returns (snapshot_id, document_id)."""
    from offline_rag.lexical.backend import (
        LexicalDocumentInput,
        LocalInvertedIndexBackend,
    )

    hashes = _config_hashes(settings)
    now = datetime.now(tz=UTC)
    corpus_id = f"corpus_{tag}"
    chunk_set_id = f"chunkset_{tag}"
    dense_index_id = f"denseindex_{tag}"
    lexical_index_id = f"lexical_{tag}"
    collection_name = f"col_{tag}"
    document_id = f"doc_{tag}"

    corpus = CorpusManifest(
        corpus_id=corpus_id,
        corpus_hash=f"corphash_{tag}",
        created_at=now,
        config_hash="cfg_corpus",
        documents=[
            CorpusDocumentEntry(
                document_id=document_id,
                source_path=f"/private/{tag}.pdf",
                source_name=f"manual_{tag}.pdf",
                source_content_hash=f"ch_{tag}",
                source_size_bytes=1024,
                source_media_type="application/pdf",
                parser_name="docling_pdf",
                parser_version="v1",
                block_count=1,
                processed_artifact=f"processed/{tag}.json",
                processed_artifact_hash=f"pah_{tag}",
                parsed_artifact_id=f"parsed_{tag}",
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
        physical_index_relpath=lexical_index_id,
        created_at=now,
    )
    for directory in (
        settings.paths.manifests,
        settings.paths.chunk_manifests,
        settings.paths.index_manifests,
        settings.paths.lexical_index_manifests,
        settings.paths.lexical_indexes,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        settings.paths.manifests / f"{corpus_id}.json", corpus.model_dump_json()
    )
    atomic_write_text(
        settings.paths.chunk_manifests / f"{chunk_set_id}.json",
        chunk.model_dump_json(),
    )
    atomic_write_text(
        settings.paths.index_manifests / f"{dense_index_id}.json",
        dense.model_dump_json(),
    )
    atomic_write_text(
        settings.paths.lexical_index_manifests / f"{lexical_index_id}.json",
        lexical.model_dump_json(),
    )
    LocalInvertedIndexBackend(settings.paths.lexical_indexes).build(
        lexical_index_id,
        [
            LexicalDocumentInput(
                chunk_id=f"chunk_{tag}",
                terms=["offline", "rag"],
                document_id=document_id,
            )
        ],
        chunk_set_id=chunk_set_id,
        lexical_config_hash=hashes["lexical_config_hash"],
    )
    qdrant.counts[collection_name] = 1

    identity = CanonicalSnapshotManifest(
        corpus_id=corpus_id,
        corpus_manifest=f"{corpus_id}.json",
        chunk_set_id=chunk_set_id,
        chunk_manifest=f"{chunk_set_id}.json",
        dense_index_id=dense_index_id,
        dense_index_manifest=f"{dense_index_id}.json",
        lexical_index_id=lexical_index_id,
        lexical_index_manifest=f"{lexical_index_id}.json",
        **hashes,
    )
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    return registry.publish(corpus_name, identity), document_id


def _workspace(
    settings: AppSettings,
    *,
    snapshot_id: str | None,
    document_id: str | None,
    display_name: str = "manual_b_v05.pdf",
) -> tuple[WorkspaceRecord, str]:
    workspace_id = new_workspace_id()
    source_id = new_source_id()
    now = utc_now()
    if snapshot_id is None:
        record = WorkspaceRecord(
            workspace_id=workspace_id,
            title="Manual B",
            revision=1,
            backing_corpus_name=backing_corpus_name_for(workspace_id),
            current_snapshot_id=None,
            status=WorkspaceStatus.EMPTY,
            created_at=now,
            updated_at=now,
            sources=[],
        )
    else:
        record = WorkspaceRecord(
            workspace_id=workspace_id,
            title="Manual B",
            revision=2,
            backing_corpus_name=backing_corpus_name_for(workspace_id),
            current_snapshot_id=snapshot_id,
            status=WorkspaceStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            sources=[
                SourceVersionRecord(
                    source_id=source_id,
                    version=3,
                    display_name=display_name,
                    content_type="application/pdf",
                    byte_size=1024,
                    content_hash="ch_v05",
                    document_id=document_id,
                    vault_object_id="vobj_" + "c" * 32,
                    active=True,
                    created_at=now,
                    active_from_revision=2,
                    active_from_snapshot_id=snapshot_id,
                )
            ],
        )
    WorkspaceStore(settings).create(record)
    return record, source_id


def _stub_outcome(
    runtime: ApplicationRuntime,
    captured: list[CorpusReadSnapshot],
    *,
    status: str = "answered",
    citations: list[dict[str, Any]] | None = None,
) -> Any:
    """Replace execution with a capture so binding is tested in isolation."""

    def _stub(
        _runtime: ApplicationRuntime,
        *,
        snapshot: CorpusReadSnapshot,
        question: str,
        control: Any = None,
    ) -> BoundSnapshotQueryOutcome:
        captured.append(snapshot)
        rows = citations
        if rows is None:
            rows = [
                {
                    "evidence_unit_id": "eu_1",
                    "document_id": snapshot.corpus_manifest.documents[0].document_id,
                    "source_chunk_id": "chunk_1",
                    "kind": "text",
                }
            ]
        return BoundSnapshotQueryOutcome(
            snapshot=snapshot,
            binding=build_snapshot_query_binding(runtime.settings, snapshot),
            trace_id="trc_stub",
            status=status,  # type: ignore[arg-type]
            answer="grounded answer" if status == "answered" else None,
            citations=list(rows),
        )

    return _stub


def test_workspace_query_binds_workspace_snapshot_not_corpus_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    runtime = _runtime(settings, qdrant)
    try:
        workspace_id = new_workspace_id()
        corpus = backing_corpus_name_for(workspace_id)
        bound_snapshot, bound_document = _publish(
            settings, corpus, tag="v05", qdrant=qdrant
        )
        # A later publication on the same backing corpus moves current.json.
        newer_snapshot, _ = _publish(settings, corpus, tag="v06", qdrant=qdrant)
        assert newer_snapshot != bound_snapshot
        assert runtime.publication.published_snapshot_id(corpus) == newer_snapshot

        now = utc_now()
        record = WorkspaceRecord(
            workspace_id=workspace_id,
            title="Manual B",
            revision=2,
            backing_corpus_name=corpus,
            current_snapshot_id=bound_snapshot,
            status=WorkspaceStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            sources=[
                SourceVersionRecord(
                    source_id=new_source_id(),
                    version=1,
                    display_name="manual_b_v05.pdf",
                    content_type="application/pdf",
                    byte_size=1024,
                    content_hash="ch_v05",
                    document_id=bound_document,
                    vault_object_id="vobj_" + "d" * 32,
                    active=True,
                    created_at=now,
                    active_from_revision=2,
                    active_from_snapshot_id=bound_snapshot,
                )
            ],
        )
        WorkspaceStore(settings).create(record)

        captured: list[CorpusReadSnapshot] = []
        monkeypatch.setattr(
            "offline_rag.app.query.run_bound_snapshot_query",
            _stub_outcome(runtime, captured),
        )

        response = run_workspace_query(
            runtime, workspace_id=workspace_id, question="what changed?"
        )

        assert [item.snapshot_id for item in captured] == [bound_snapshot]
        assert response.snapshot_id == bound_snapshot
        assert response.workspace_id == workspace_id
        assert response.workspace_revision == 2

        # The product path on the same corpus still re-resolves current.json,
        # proving the two resolutions are genuinely independent.
        product_captured: list[CorpusReadSnapshot] = []
        monkeypatch.setattr(
            "offline_rag.app.query.run_bound_snapshot_query",
            _stub_outcome(runtime, product_captured),
        )
        product = run_product_query(
            runtime, corpus=corpus, question="what changed?"
        )
        assert [item.snapshot_id for item in product_captured] == [newer_snapshot]
        assert product.snapshot_id == newer_snapshot
    finally:
        runtime.shutdown()


def test_workspace_query_fails_closed_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    runtime = _runtime(settings, qdrant)
    try:
        record, _ = _workspace(settings, snapshot_id=None, document_id=None)
        # A previously current publication exists on the backing corpus; EMPTY
        # must not reach it (S16-D13).
        _publish(settings, record.backing_corpus_name, tag="old", qdrant=qdrant)

        captured: list[CorpusReadSnapshot] = []
        monkeypatch.setattr(
            "offline_rag.app.query.run_bound_snapshot_query",
            _stub_outcome(runtime, captured),
        )

        with pytest.raises(AppError) as error:
            run_workspace_query(
                runtime, workspace_id=record.workspace_id, question="anything?"
            )
        assert error.value.code is ErrorCode.WORKSPACE_NOT_READY
        assert (error.value.details or {})["reason"] == "workspace_empty"
        assert captured == []
    finally:
        runtime.shutdown()


def test_workspace_query_rejects_torn_read_during_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    runtime = _runtime(settings, qdrant)
    try:
        workspace_id = new_workspace_id()
        corpus = backing_corpus_name_for(workspace_id)
        snapshot_id, document_id = _publish(
            settings, corpus, tag="torn", qdrant=qdrant
        )
        now = utc_now()
        record = WorkspaceRecord(
            workspace_id=workspace_id,
            title="Manual B",
            revision=2,
            backing_corpus_name=corpus,
            current_snapshot_id=snapshot_id,
            status=WorkspaceStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            sources=[
                SourceVersionRecord(
                    source_id=new_source_id(),
                    version=1,
                    display_name="manual.pdf",
                    content_type="application/pdf",
                    byte_size=1024,
                    content_hash="ch",
                    document_id=document_id,
                    vault_object_id="vobj_" + "e" * 32,
                    active=True,
                    created_at=now,
                    active_from_revision=2,
                    active_from_snapshot_id=snapshot_id,
                )
            ],
        )
        store = WorkspaceStore(settings)
        store.create(record)

        original = runtime.publication.resolve_snapshot

        def _resolve_then_mutate(name: str, snap: str) -> CorpusReadSnapshot:
            resolved = original(name, snap)
            # Concurrent display-only rename commits while we were binding.
            store.apply_metadata_patch(
                workspace_id, expected_revision=2, title="Renamed"
            )
            return resolved

        monkeypatch.setattr(
            runtime.publication, "resolve_snapshot", _resolve_then_mutate
        )
        captured: list[CorpusReadSnapshot] = []
        monkeypatch.setattr(
            "offline_rag.app.query.run_bound_snapshot_query",
            _stub_outcome(runtime, captured),
        )

        with pytest.raises(AppError) as error:
            run_workspace_query(
                runtime, workspace_id=workspace_id, question="anything?"
            )
        assert error.value.code is ErrorCode.WORKSPACE_CONFLICT
        assert (error.value.details or {})["reason"] == "workspace_revision_changed"
        assert captured == []
    finally:
        runtime.shutdown()


def test_workspace_query_enriches_citations_with_source_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    runtime = _runtime(settings, qdrant)
    try:
        workspace_id = new_workspace_id()
        corpus = backing_corpus_name_for(workspace_id)
        snapshot_id, document_id = _publish(
            settings, corpus, tag="cite", qdrant=qdrant
        )
        now = utc_now()
        source_id = new_source_id()
        record = WorkspaceRecord(
            workspace_id=workspace_id,
            title="Manual B",
            revision=2,
            backing_corpus_name=corpus,
            current_snapshot_id=snapshot_id,
            status=WorkspaceStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            sources=[
                SourceVersionRecord(
                    source_id=source_id,
                    version=4,
                    display_name="Renamed Manual.pdf",
                    content_type="application/pdf",
                    byte_size=1024,
                    content_hash="ch",
                    document_id=document_id,
                    vault_object_id="vobj_" + "f" * 32,
                    active=True,
                    created_at=now,
                    active_from_revision=2,
                    active_from_snapshot_id=snapshot_id,
                )
            ],
        )
        WorkspaceStore(settings).create(record)

        captured: list[CorpusReadSnapshot] = []
        monkeypatch.setattr(
            "offline_rag.app.query.run_bound_snapshot_query",
            _stub_outcome(runtime, captured),
        )
        response = run_workspace_query(
            runtime, workspace_id=workspace_id, question="anything?"
        )

        assert response.status == "answered"
        assert len(response.citations) == 1
        citation = response.citations[0]
        assert citation["source_id"] == source_id
        assert citation["source_version"] == 4
        assert citation["source_display_name"] == "Renamed Manual.pdf"
        # Scientific citation fields survive unchanged.
        assert citation["document_id"] == document_id
        assert citation["evidence_unit_id"] == "eu_1"
    finally:
        runtime.shutdown()


def test_workspace_query_fails_closed_when_answered_citation_is_unmappable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    runtime = _runtime(settings, qdrant)
    try:
        workspace_id = new_workspace_id()
        corpus = backing_corpus_name_for(workspace_id)
        snapshot_id, document_id = _publish(
            settings, corpus, tag="unmapped", qdrant=qdrant
        )
        now = utc_now()
        record = WorkspaceRecord(
            workspace_id=workspace_id,
            title="Manual B",
            revision=2,
            backing_corpus_name=corpus,
            current_snapshot_id=snapshot_id,
            status=WorkspaceStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            sources=[
                SourceVersionRecord(
                    source_id=new_source_id(),
                    version=1,
                    display_name="other.pdf",
                    content_type="application/pdf",
                    byte_size=1024,
                    content_hash="ch",
                    # Active source claims a different document than the
                    # snapshot citation resolves to.
                    document_id="doc_unrelated",
                    vault_object_id="vobj_" + "9" * 32,
                    active=True,
                    created_at=now,
                    active_from_revision=2,
                    active_from_snapshot_id=snapshot_id,
                )
            ],
        )
        WorkspaceStore(settings).create(record)

        captured: list[CorpusReadSnapshot] = []
        monkeypatch.setattr(
            "offline_rag.app.query.run_bound_snapshot_query",
            _stub_outcome(
                runtime,
                captured,
                citations=[
                    {
                        "evidence_unit_id": "eu_1",
                        "document_id": document_id,
                        "source_chunk_id": "chunk_1",
                        "kind": "text",
                    }
                ],
            ),
        )

        with pytest.raises(AppError) as error:
            run_workspace_query(
                runtime, workspace_id=workspace_id, question="anything?"
            )
        assert error.value.code is ErrorCode.CITATION_INVALID
        assert (error.value.details or {})["reason"] == "citation_source_unmappable"
    finally:
        runtime.shutdown()


def test_abstention_tolerates_unmappable_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    runtime = _runtime(settings, qdrant)
    try:
        workspace_id = new_workspace_id()
        corpus = backing_corpus_name_for(workspace_id)
        snapshot_id, document_id = _publish(
            settings, corpus, tag="abstain", qdrant=qdrant
        )
        now = utc_now()
        record = WorkspaceRecord(
            workspace_id=workspace_id,
            title="Manual B",
            revision=2,
            backing_corpus_name=corpus,
            current_snapshot_id=snapshot_id,
            status=WorkspaceStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            sources=[
                SourceVersionRecord(
                    source_id=new_source_id(),
                    version=1,
                    display_name="manual.pdf",
                    content_type="application/pdf",
                    byte_size=1024,
                    content_hash="ch",
                    document_id=document_id,
                    vault_object_id="vobj_" + "8" * 32,
                    active=True,
                    created_at=now,
                    active_from_revision=2,
                    active_from_snapshot_id=snapshot_id,
                )
            ],
        )
        WorkspaceStore(settings).create(record)

        captured: list[CorpusReadSnapshot] = []
        monkeypatch.setattr(
            "offline_rag.app.query.run_bound_snapshot_query",
            _stub_outcome(
                runtime, captured, status="insufficient_evidence", citations=[]
            ),
        )
        response = run_workspace_query(
            runtime, workspace_id=workspace_id, question="anything?"
        )
        assert response.status == "insufficient_evidence"
        assert response.answer is None
        assert response.citations == []
    finally:
        runtime.shutdown()
