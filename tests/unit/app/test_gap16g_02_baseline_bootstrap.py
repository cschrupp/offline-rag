"""GAP-16G-02 — Gold Lab baseline bootstrap product path."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_APP_TEST_DIR = Path(__file__).resolve().parent
if str(_APP_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_TEST_DIR))

from test_slice16f_d_gold_lab_api import (
    _active_workspace,
    _FakeQdrant,
    _runtime,
)
from test_slice16f_d_gold_lab_historical_source import (
    CHUNK_A,
    CHUNK_B,
    CHUNK_CFG,
    CORPUS_NAME,
    DOC_ID,
    PARSED,
    _publish_integrity,
)
from test_slice16f_d_gold_lab_historical_source import (
    _settings as _integrity_settings,
)

from offline_rag.api.app import create_app
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.gold_lab.bootstrap import (
    GoldLabBaselineBootstrapService,
    bootstrap_request_fingerprint,
    reconcile_gold_bootstrap_operations,
)
from offline_rag.app.gold_lab.bootstrap_seed import derive_bootstrap_sampling_seed
from offline_rag.app.gold_lab.bootstrap_staging import (
    bootstrap_staging_run_path,
    scavenge_bootstrap_staging,
)
from offline_rag.app.gold_lab.models import GoldProjectType
from offline_rag.app.gold_lab.reviewable import is_reviewable_case
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.publication import ProductPublicationRegistry
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.snapshot import CanonicalSnapshotManifest
from offline_rag.app.workspace.lifecycle import recover_workspace_journals
from offline_rag.app.workspace.models import (
    GoldLabBaselineBootstrapAuthority,
    ManagedOperationKind,
    ManagedOperationStatus,
    OperationProgressStage,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.chunking.persistence import (
    chunk_artifact_relpath,
    write_chunk_artifact,
)
from offline_rag.config.models import AppSettings, AuthoringSettings
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.core.ids import (
    DENSE_INDEX_CONTRACT_VERSION,
    STRUCTURE_AWARE_CHUNKER_VERSION,
    chunk_artifact_id,
    chunk_set_id_from_entries,
    corpus_id_from_entries,
    dense_index_id,
    dense_point_uuid,
    lexical_index_id,
)
from offline_rag.dense.backend import DensePointRecord
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.domain.chunking import (
    ChunkSetDocumentEntry,
    ChunkSetManifest,
    DocumentChunkArtifact,
)
from offline_rag.domain.corpus import CorpusDocumentEntry, CorpusManifest
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import DenseIndexManifest, LexicalIndexManifest
from offline_rag.gold_authoring.models import (
    GoldAuthoringRun,
    ProposalAttempt,
    ProposalAttemptStatus,
    SilverCase,
    SourceSeed,
)
from offline_rag.gold_authoring.persist import (
    default_authoring_run_path,
    load_authoring_run,
    serialize_authoring_run_bytes,
    write_authoring_run_bytes,
)
from offline_rag.gold_authoring.pooling_models import PoolCandidate
from offline_rag.gold_authoring.propose import ProposeJobResult, run_gold_propose
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.lexical.backend import LexicalDocumentInput, LocalInvertedIndexBackend
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.rerank.config_hash import build_reranker_config_hash
from offline_rag.rerank.fake import FakeReranker


def _authoring_ready(settings: AppSettings) -> AppSettings:
    auth = AuthoringSettings(
        enabled=True,
        model="test-model",
        approved_models=["test-model"],
        approved_endpoints=["http://127.0.0.1:11434/v1"],
        base_url="http://127.0.0.1:11434/v1",
        api_key="author-secret",
        network_policy="localhost_only",
    )
    api = settings.api.model_copy(
        update={
            "max_concurrent_gold_bootstrap": 1,
            "gold_bootstrap_staging_retention_hours": 24,
        }
    )
    return settings.model_copy(update={"authoring": auth, "api": api})


def _reviewable_run(
    *,
    corpus_id: str,
    chunk_set_id: str,
    authoring_run_id: str,
    sampling_seed: int = 1,
) -> GoldAuthoringRun:
    return GoldAuthoringRun(
        authoring_run_id=authoring_run_id,
        authorcfg_id="authorcfg_" + ("a" * 64),
        network_policy="localhost_only",
        created_at=datetime.now(tz=UTC),
        corpus_name=CORPUS_NAME,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        sampling_seed=sampling_seed,
        attempts=[
            ProposalAttempt(
                source_seed=SourceSeed(chunk_id=CHUNK_A, document_id=DOC_ID),
                status=ProposalAttemptStatus.SUCCEEDED,
                draft_case_id="draft_reviewable",
            )
        ],
        cases=[
            SilverCase(
                draft_case_id="draft_reviewable",
                proposed_query="What is offline RAG?",
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
        ],
        pool_successful_case_count=1,
    )


@contextmanager
def _client(runtime: ApplicationRuntime) -> Iterator[TestClient]:
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        yield client


def _patch_ensure_noop():
    """Skip Arm-H ensure for tests that mock pool and use integrity-only fixtures."""
    return patch(
        "offline_rag.app.gold_lab.bootstrap.ensure_pooling_artifacts",
        return_value=MagicMock(),
    )


def _project_and_workspace(tmp_path: Path):
    settings = _authoring_ready(_integrity_settings(tmp_path))
    snap_id, corpus_id, chunk_set_id, _ = _publish_integrity(settings)
    workspace = _active_workspace(settings, snap_id)
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=workspace.workspace_id,
        title="Bootstrap Desk",
        description="",
        project_type=GoldProjectType.BENCHMARK,
    )
    q = _FakeQdrant()
    q.counts["col_16fd"] = 2
    runtime = _runtime(settings, qdrant=q)
    runtime.start()
    # TestClient / publication resolution needs the live fake counts.
    runtime.publication.qdrant = q
    return settings, runtime, project, workspace, corpus_id, chunk_set_id, snap_id


def _pooling_ready_settings(tmp_path: Path) -> AppSettings:
    """Authoring-ready settings with fake embed/rerank for real 9C execution."""
    settings = _authoring_ready(_integrity_settings(tmp_path))
    return settings.model_copy(
        update={
            "indexing": settings.indexing.model_copy(
                update={
                    "embedding": settings.indexing.embedding.model_copy(
                        update={
                            "implementation": "fake",
                            "model_id": "fake",
                            "revision": "fake-v1",
                            "dimension": 8,
                            "adapter_contract": "fake-embedder-v1",
                        }
                    )
                }
            ),
            "reranker": settings.reranker.model_copy(
                update={"enabled": True, "implementation": "fake"}
            ),
        }
    )


def _publish_real_qdrant_pooling_ready(
    settings: AppSettings,
    *,
    include_arm_h: bool = False,
) -> tuple[str, str, str, str]:
    """Publish ordinary Seneca publication artifacts for real 9C.

    Builds lexical + baseline-dense (and optionally Arm-H) with identity IDs
    derived from current settings hashes, and materializes vectors into a real
    persistent ``QdrantLocalBackend`` (closed before return so runtime can own
    the exclusive storage lock).

    Default ``include_arm_h=False`` matches ordinary Add Sources / publication
    (16M product path). Pass ``include_arm_h=True`` only for tests whose subject
    is reuse of a pre-existing Arm-H artifact or pure preflight.
    """
    from offline_rag.chunking.tokenize import TiktokenTokenCounter
    from offline_rag.gold_authoring.pool_contract import (
        settings_arm_h as arm_h_settings,
    )

    counter = TiktokenTokenCounter(
        encoding=settings.chunking.tokenizer.encoding,
        artifacts_path=settings.paths.tokenizer_artifacts,
    )
    hashes = {
        "embedding_config_hash": build_embedding_config_hash(settings),
        "index_config_hash": build_index_config_hash(settings),
        "lexical_config_hash": build_lexical_config_hash(settings),
        "fusion_config_hash": build_fusion_config_hash(settings),
        "reranker_config_hash": build_reranker_config_hash(settings),
        "context_config_hash": build_context_config_hash(
            settings, token_counter=counter
        ),
    }
    art_id = chunk_artifact_id(
        PARSED, CHUNK_CFG, chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION
    )
    children = [
        Chunk(
            chunk_id=CHUNK_A,
            document_id=DOC_ID,
            kind=ChunkKind.CHILD,
            text="alpha candidate text for gold lab",
            order=0,
            token_count=4,
            content_hash="ch_a",
            source_block_ids=["blk_a"],
        ),
        Chunk(
            chunk_id=CHUNK_B,
            document_id=DOC_ID,
            kind=ChunkKind.CHILD,
            text="beta candidate text for gold lab",
            order=1,
            token_count=4,
            content_hash="ch_b",
            source_block_ids=["blk_b"],
        ),
    ]
    artifact = DocumentChunkArtifact(
        chunk_artifact_id=art_id,
        parsed_artifact_id=PARSED,
        document_id=DOC_ID,
        chunk_config_hash=CHUNK_CFG,
        chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION,
        tokenizer_name="tiktoken",
        tokenizer_encoding="cl100k_base",
        parents=[],
        children=children,
        parent_count=0,
        child_count=2,
    )
    _path, digest = write_chunk_artifact(settings.paths.chunks, artifact)
    docs = [
        CorpusDocumentEntry(
            document_id=DOC_ID,
            source_path="spec.pdf",
            source_name="spec.pdf",
            source_content_hash="ch_16fd",
            source_size_bytes=12,
            source_media_type="application/pdf",
            parser_name="docling_pdf",
            parser_version="v1",
            block_count=1,
            processed_artifact="processed/x.json",
            processed_artifact_hash="pah_1",
            parsed_artifact_id=PARSED,
            parse_config_hash="cfg_parse",
        )
    ]
    schema = "offline-rag-corpus-manifest-v1"
    cfg_hash = "cfg_corpus"
    corpus_id = corpus_id_from_entries(
        schema_version=schema,
        parse_cfg_hash=cfg_hash,
        document_identities=[
            {
                "document_id": d.document_id,
                "source_content_hash": d.source_content_hash,
                "processed_artifact_hash": d.processed_artifact_hash,
                "parsed_artifact_id": d.parsed_artifact_id,
            }
            for d in docs
        ],
    )
    now = datetime.now(tz=UTC)
    corpus = CorpusManifest(
        schema_version=schema,
        corpus_id=corpus_id,
        corpus_hash="corphash",
        created_at=now,
        config_hash=cfg_hash,
        documents=docs,
    )
    chunk_set_id = chunk_set_id_from_entries(
        corpus_id=corpus_id,
        chunk_cfg_hash=CHUNK_CFG,
        chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION,
        document_entries=[
            {
                "document_id": DOC_ID,
                "parsed_artifact_id": PARSED,
                "chunk_artifact_id": art_id,
            }
        ],
    )
    entry = ChunkSetDocumentEntry(
        document_id=DOC_ID,
        parsed_artifact_id=PARSED,
        chunk_artifact_id=art_id,
        chunk_artifact=chunk_artifact_relpath(art_id),
        chunk_artifact_hash=digest,
        parent_count=0,
        child_count=2,
    )
    chunk = ChunkSetManifest(
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
        chunk_config_hash=CHUNK_CFG,
        chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION,
        tokenizer_name="tiktoken",
        tokenizer_encoding="cl100k_base",
        created_at=now,
        documents=[entry],
        total_parent_count=0,
        total_child_count=2,
    )
    for root in (
        settings.paths.manifests,
        settings.paths.chunk_manifests,
        settings.paths.index_manifests,
        settings.paths.lexical_index_manifests,
        settings.paths.lexical_indexes,
        settings.paths.qdrant_storage,
    ):
        root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        settings.paths.manifests / f"{corpus_id}.json", corpus.model_dump_json()
    )
    atomic_write_text(
        settings.paths.chunk_manifests / f"{chunk_set_id}.json", chunk.model_dump_json()
    )

    from offline_rag.core.ids import dense_collection_name

    baseline_cfg = hashes["index_config_hash"]
    baseline_id = dense_index_id(chunk_set_id, baseline_cfg)
    arm_h_cfg = build_index_config_hash(arm_h_settings(settings))
    arm_h_id = dense_index_id(chunk_set_id, arm_h_cfg)
    lex_id = lexical_index_id(
        chunk_set_id,
        hashes["lexical_config_hash"],
        backend_contract=settings.lexical.backend_contract,
    )
    baseline_collection = dense_collection_name(baseline_id)
    arm_h_collection = dense_collection_name(arm_h_id)

    def _dense_manifest(
        index_id: str, collection: str, index_cfg: str
    ) -> DenseIndexManifest:
        return DenseIndexManifest(
            index_id=index_id,
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            embedding_config_hash=hashes["embedding_config_hash"],
            index_config_hash=index_cfg,
            index_contract_version=DENSE_INDEX_CONTRACT_VERSION,
            embedding_text_strategy="plain",
            embedding_text_contract="plain-v1",
            embedding_model_id="fake",
            embedding_model_revision="fake-v1",
            embedding_dimension=8,
            normalize=True,
            similarity_metric="cosine",
            backend="qdrant_local",
            backend_contract=settings.indexing.backend_contract,
            collection_name=collection,
            expected_child_count=2,
            indexed_child_count=2,
            created_at=now,
        )

    atomic_write_text(
        settings.paths.index_manifests / f"{baseline_id}.json",
        _dense_manifest(
            baseline_id, baseline_collection, baseline_cfg
        ).model_dump_json(),
    )
    if include_arm_h:
        atomic_write_text(
            settings.paths.index_manifests / f"{arm_h_id}.json",
            _dense_manifest(arm_h_id, arm_h_collection, arm_h_cfg).model_dump_json(),
        )
    lexical = LexicalIndexManifest(
        lexical_index_id=lex_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        lexical_config_hash=hashes["lexical_config_hash"],
        text_strategy="plain",
        text_contract="plain-v1",
        analyzer_strategy="technical",
        analyzer_contract="technical-v1",
        bm25_contract="bm25-okapi-v1",
        bm25_k1=1.2,
        bm25_b=0.75,
        bm25_idf="rsj-positive-smoothed-v1",
        bm25_query_tf="unique-terms-v1",
        backend="local_inverted",
        backend_contract=settings.lexical.backend_contract,
        expected_child_count=2,
        indexed_child_count=2,
        document_count=1,
        vocabulary_size=2,
        avgdl=1.0,
        physical_index_relpath=f"{lex_id}",
        created_at=now,
    )
    atomic_write_text(
        settings.paths.lexical_index_manifests / f"{lex_id}.json",
        lexical.model_dump_json(),
    )
    LocalInvertedIndexBackend(settings.paths.lexical_indexes).build(
        lex_id,
        [
            LexicalDocumentInput(
                chunk_id=CHUNK_A, terms=["offline", "rag"], document_id=DOC_ID
            ),
            LexicalDocumentInput(
                chunk_id=CHUNK_B, terms=["gold", "lab"], document_id=DOC_ID
            ),
        ],
        chunk_set_id=chunk_set_id,
        lexical_config_hash=hashes["lexical_config_hash"],
    )

    embedder = FakeEmbedder(dimension=8, normalize=True)
    points = [
        DensePointRecord(
            point_id=dense_point_uuid(chunk.chunk_id),
            vector=embedder.embed_documents([chunk.text])[0],
            payload={
                "chunk_id": chunk.chunk_id,
                "chunk_artifact_id": art_id,
                "document_id": DOC_ID,
                "kind": "child",
            },
        )
        for chunk in children
    ]
    backend = QdrantLocalBackend(settings.paths.qdrant_storage)
    try:
        collections = [baseline_collection]
        if include_arm_h:
            collections.append(arm_h_collection)
        for collection in collections:
            backend.create_collection(collection, dimension=8, metric="cosine")
            backend.upsert(collection, points)
        identity = CanonicalSnapshotManifest(
            corpus_id=corpus_id,
            corpus_manifest=f"{corpus_id}.json",
            chunk_set_id=chunk_set_id,
            chunk_manifest=f"{chunk_set_id}.json",
            dense_index_id=baseline_id,
            dense_index_manifest=f"{baseline_id}.json",
            lexical_index_id=lex_id,
            lexical_index_manifest=f"{lex_id}.json",
            **hashes,
        )
        registry = ProductPublicationRegistry(settings, qdrant=backend)
        snapshot_id = registry.publish(
            CORPUS_NAME, identity, require_current_config_match=True
        )
    finally:
        backend.close()
    return snapshot_id, corpus_id, chunk_set_id, art_id


class _Closeable:
    def close(self) -> None:
        return None


# --- Seed -----------------------------------------------------------------


def test_seed_v1_exact_and_operation_derived() -> None:
    op_a = "wop_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    op_b = "wop_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    material = f"baseline-bootstrap-sampling-seed-v1|{op_a}"
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    expected = int.from_bytes(digest[0:8], "big") % (2**63)
    assert derive_bootstrap_sampling_seed(op_a) == expected
    assert derive_bootstrap_sampling_seed(op_a) == derive_bootstrap_sampling_seed(op_a)
    assert derive_bootstrap_sampling_seed(op_a) != derive_bootstrap_sampling_seed(op_b)


def test_fingerprint_expected_revision_null() -> None:
    fp = bootstrap_request_fingerprint(
        project_id="proj_x", proposal_count=20, prelabel_enabled=False
    )
    assert isinstance(fp, str) and fp.startswith("reqfp_")
    other = bootstrap_request_fingerprint(
        project_id="proj_x", proposal_count=21, prelabel_enabled=False
    )
    assert fp != other


# --- HTTP admission / errors ---------------------------------------------


def test_http_pre_admission_error_matrix(tmp_path: Path) -> None:
    settings, runtime, project, _ws, *_ = _project_and_workspace(tmp_path)
    with _client(runtime) as client:
        # missing idempotency
        r = client.post(
            f"/v1/gold-lab/projects/{project.project_id}/baseline-bootstrap",
            json={"proposal_count": 20, "prelabel_enabled": False},
        )
        assert r.status_code == 422
        assert r.json()["details"]["reason"] == "idempotency_key_invalid"

        # invalid proposal_count (bool)
        r = client.post(
            f"/v1/gold-lab/projects/{project.project_id}/baseline-bootstrap",
            headers={"Idempotency-Key": "k1"},
            json={"proposal_count": True, "prelabel_enabled": False},
        )
        assert r.status_code == 422
        assert r.json()["details"]["reason"] == "proposal_count_invalid"

        # invalid prelabel
        r = client.post(
            f"/v1/gold-lab/projects/{project.project_id}/baseline-bootstrap",
            headers={"Idempotency-Key": "k2"},
            json={"proposal_count": 20, "prelabel_enabled": 1},
        )
        assert r.status_code == 422
        assert r.json()["details"]["reason"] == "prelabel_enabled_invalid"

        # unknown project
        r = client.post(
            "/v1/gold-lab/projects/goldproj_" + ("0" * 32) + "/baseline-bootstrap",
            headers={"Idempotency-Key": "k3"},
            json={"proposal_count": 20, "prelabel_enabled": False},
        )
        assert r.status_code == 404
        assert r.json()["details"]["reason"] == "project_unknown"

        # archived
        store = GoldLabStore(settings)
        store.archive_project(project.project_id)
        r = client.post(
            f"/v1/gold-lab/projects/{project.project_id}/baseline-bootstrap",
            headers={"Idempotency-Key": "k4"},
            json={"proposal_count": 20, "prelabel_enabled": False},
        )
        assert r.status_code == 409
        assert r.json()["details"]["reason"] == "project_archived"


# --- Orchestration with fakes --------------------------------------------


def test_happy_path_idempotency_capacity_privacy(tmp_path: Path) -> None:
    settings, runtime, project, workspace, corpus_id, chunk_set_id, _snap_id = (
        _project_and_workspace(tmp_path)
    )
    svc = GoldLabBaselineBootstrapService(runtime)

    def propose(settings_arg, **kwargs):
        snap = kwargs["snapshot"]
        run = _reviewable_run(
            corpus_id=str(getattr(snap, "corpus_id", corpus_id) or corpus_id),
            chunk_set_id=str(
                getattr(snap, "chunk_set_id", chunk_set_id) or chunk_set_id
            ),
            authoring_run_id=kwargs["authoring_run_id"],
            sampling_seed=kwargs["seed"],
        )
        # Force captured identities from authority via frozen IDs on path write.
        run = run.model_copy(
            update={"corpus_id": corpus_id, "chunk_set_id": chunk_set_id}
        )
        path = kwargs["output"]
        path.parent.mkdir(parents=True, exist_ok=True)
        write_authoring_run_bytes(path, serialize_authoring_run_bytes(run))
        return ProposeJobResult(exit_code=0, run=run, output_path=path)

    def pool(settings_arg, **kwargs):
        from offline_rag.gold_authoring.persist import load_authoring_run
        from offline_rag.gold_authoring.pool import PoolJobResult

        run = load_authoring_run(kwargs["run_path"])
        return PoolJobResult(exit_code=0, run=run, output_path=kwargs["run_path"])

    with (
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_propose_on_snapshot",
            side_effect=propose,
        ),
        patch("offline_rag.app.gold_lab.bootstrap.run_gold_pool", side_effect=pool),
        _patch_ensure_noop(),
        patch(
            "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
            return_value=[object()] * 50,
        ),
        patch(
            "offline_rag.app.gold_lab.bootstrap.validate_historical_chunk_identities",
            return_value=None,
        ),
    ):
        record = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=5,
            prelabel_enabled=False,
            idempotency_key="idem-happy",
        )
        assert record.kind is ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP
        assert record.expected_revision is None
        deadline = time.time() + 10
        ops = ManagedOperationStore(settings)
        while time.time() < deadline:
            current = ops.get(workspace.workspace_id, record.operation_id)
            if current.status is ManagedOperationStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        else:
            pytest.fail(f"bootstrap did not succeed: {current.status} {current.error}")

        assert current.result is not None
        assert current.result.baseline_eligible is True
        assert current.result.prelabel_targeted == 0
        assert current.result.prelabel_succeeded == 0
        assert current.result.prelabel_failed == 0
        assert current.bootstrap_authority is not None
        seed = current.bootstrap_authority.sampling_seed
        assert seed == derive_bootstrap_sampling_seed(record.operation_id)

        # Same key / body after "revision change" still recovers.
        again = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=5,
            prelabel_enabled=False,
            idempotency_key="idem-happy",
        )
        assert again.operation_id == record.operation_id
        assert again.bootstrap_authority is not None
        assert again.bootstrap_authority.sampling_seed == seed

        # Changed body conflicts.
        with pytest.raises(AppError) as exc:
            svc.start_baseline_bootstrap(
                project_id=project.project_id,
                proposal_count=6,
                prelabel_enabled=False,
                idempotency_key="idem-happy",
            )
        assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

        # Privacy: operation view must not expose staging paths / authority.
        with _client(runtime) as client:
            view = client.get(f"/v1/operations/{record.operation_id}").json()
            blob = json.dumps(view)
            assert "staging" not in blob
            assert "bootstrap_authority" not in blob
            assert "author-secret" not in blob
            assert view["result"]["baseline_eligible"] is True
            assert "corpus_name" not in view["result"]


def test_single_flight_and_capacity(tmp_path: Path) -> None:
    settings, runtime, project, workspace, corpus_id, chunk_set_id, _ = (
        _project_and_workspace(tmp_path)
    )
    # Second project on same workspace.
    store = GoldLabStore(settings)
    project_b = store.create_project(
        workspace_id=workspace.workspace_id,
        title="Shared Workspace Project",
        description="",
        project_type=GoldProjectType.IMPROVEMENT,
    )
    svc = GoldLabBaselineBootstrapService(runtime)
    gate = threading.Event()
    started = threading.Event()

    def slow_propose(settings_arg, **kwargs):
        started.set()
        gate.wait(timeout=5)
        run = _reviewable_run(
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            authoring_run_id=kwargs["authoring_run_id"],
            sampling_seed=kwargs["seed"],
        )
        path = kwargs["output"]
        path.parent.mkdir(parents=True, exist_ok=True)
        write_authoring_run_bytes(path, serialize_authoring_run_bytes(run))
        return ProposeJobResult(exit_code=0, run=run, output_path=path)

    def pool(settings_arg, **kwargs):
        from offline_rag.gold_authoring.persist import load_authoring_run
        from offline_rag.gold_authoring.pool import PoolJobResult

        run = load_authoring_run(kwargs["run_path"])
        return PoolJobResult(exit_code=0, run=run, output_path=kwargs["run_path"])

    with (
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_propose_on_snapshot",
            side_effect=slow_propose,
        ),
        patch("offline_rag.app.gold_lab.bootstrap.run_gold_pool", side_effect=pool),
        _patch_ensure_noop(),
        patch(
            "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
            return_value=[object()] * 50,
        ),
        patch(
            "offline_rag.app.gold_lab.bootstrap.validate_historical_chunk_identities",
            return_value=None,
        ),
    ):
        first = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=3,
            prelabel_enabled=False,
            idempotency_key="sf-a",
        )
        assert started.wait(timeout=5)
        with pytest.raises(AppError) as busy:
            svc.start_baseline_bootstrap(
                project_id=project_b.project_id,
                proposal_count=3,
                prelabel_enabled=False,
                idempotency_key="sf-b",
            )
        assert busy.value.code is ErrorCode.GOLD_BUSY
        assert busy.value.details["reason"] == "baseline_bootstrap_active"
        # Capacity exhausted for a different workspace while slot held.
        # Reuse same snapshot artificially; create project on different workspace.
        # Publish integrity already used CORPUS_NAME — create empty-ish second workspace
        # by cloning publication identity onto another workspace record.
        from offline_rag.app.workspace.models import (
            SourceVersionRecord,
            WorkspaceStatus,
            new_empty_workspace,
            new_source_id,
        )
        from offline_rag.app.workspace.store import WorkspaceStore

        ws_store = WorkspaceStore(settings)
        empty = ws_store.create(
            new_empty_workspace(title="Other Desk").model_copy(
                update={"backing_corpus_name": CORPUS_NAME}
            )
        )
        other = empty.model_copy(
            update={
                "status": WorkspaceStatus.ACTIVE,
                "current_snapshot_id": workspace.current_snapshot_id,
                "sources": [
                    SourceVersionRecord(
                        source_id=new_source_id(),
                        version=1,
                        display_name="other.pdf",
                        vault_object_id="vobj_" + "d" * 32,
                        created_at=datetime.now(tz=UTC),
                        active_from_revision=1,
                        active_from_snapshot_id=workspace.current_snapshot_id,
                    )
                ],
                "revision": 1,
            }
        )
        other = ws_store.save(other)
        project_c = store.create_project(
            workspace_id=other.workspace_id,
            title="Other WS",
            description="",
            project_type=GoldProjectType.BENCHMARK,
        )
        with pytest.raises(AppError) as cap:
            svc.start_baseline_bootstrap(
                project_id=project_c.project_id,
                proposal_count=3,
                prelabel_enabled=False,
                idempotency_key="cap-1",
            )
        assert cap.value.code is ErrorCode.SERVICE_OVERLOADED
        assert cap.value.details["reason"] == "gold_bootstrap_capacity_exhausted"
        # No operation created for capacity failure.
        assert (
            ManagedOperationStore(settings).find_by_idempotency(
                other.workspace_id, "cap-1"
            )
            is None
        )
        gate.set()
        # Drain first op.
        deadline = time.time() + 10
        ops = ManagedOperationStore(settings)
        while time.time() < deadline:
            cur = ops.get(workspace.workspace_id, first.operation_id)
            if cur.status in {
                ManagedOperationStatus.SUCCEEDED,
                ManagedOperationStatus.FAILED,
            }:
                break
            time.sleep(0.05)


def test_zero_proposals_fails_without_canonical(tmp_path: Path) -> None:
    settings, runtime, project, workspace, corpus_id, chunk_set_id, _ = (
        _project_and_workspace(tmp_path)
    )
    svc = GoldLabBaselineBootstrapService(runtime)

    def propose(settings_arg, **kwargs):
        run = GoldAuthoringRun(
            authoring_run_id=kwargs["authoring_run_id"],
            authorcfg_id="authorcfg_" + ("a" * 64),
            network_policy="localhost_only",
            created_at=datetime.now(tz=UTC),
            corpus_name=CORPUS_NAME,
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            sampling_seed=kwargs["seed"],
            attempts=[
                ProposalAttempt(
                    source_seed=SourceSeed(chunk_id=CHUNK_A, document_id=DOC_ID),
                    status=ProposalAttemptStatus.FAILED_SCHEMA,
                )
            ],
            cases=[],
        )
        path = kwargs["output"]
        path.parent.mkdir(parents=True, exist_ok=True)
        write_authoring_run_bytes(path, serialize_authoring_run_bytes(run))
        return ProposeJobResult(exit_code=1, run=run, output_path=path)

    with (
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_propose_on_snapshot",
            side_effect=propose,
        ),
        patch(
            "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
            return_value=[object()] * 50,
        ),
    ):
        record = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=2,
            prelabel_enabled=False,
            idempotency_key="zero-prop",
        )
        deadline = time.time() + 10
        ops = ManagedOperationStore(settings)
        while time.time() < deadline:
            current = ops.get(workspace.workspace_id, record.operation_id)
            if current.status is ManagedOperationStatus.FAILED:
                break
            time.sleep(0.05)
        assert current.error is not None
        assert current.error.details["reason"] == "zero_usable_proposals"
        auth = current.bootstrap_authority
        assert auth is not None
        canonical = default_authoring_run_path(
            settings,
            corpus_name=auth.corpus_name,
            authoring_run_id=auth.authoring_run_id,
        )
        assert not canonical.exists()


def test_crash_reconcile_success_and_absent(tmp_path: Path) -> None:
    settings, runtime, project, workspace, corpus_id, chunk_set_id, snap_id = (
        _project_and_workspace(tmp_path)
    )
    ops = ManagedOperationStore(settings)
    authoring_run_id = "authorrun_crash_ok"
    run = _reviewable_run(
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        authoring_run_id=authoring_run_id,
        sampling_seed=42,
    )
    final_bytes = serialize_authoring_run_bytes(run)
    expected_sha = hashlib.sha256(final_bytes).hexdigest()
    canonical = default_authoring_run_path(
        settings, corpus_name=CORPUS_NAME, authoring_run_id=authoring_run_id
    )
    canonical.parent.mkdir(parents=True, exist_ok=True)
    write_authoring_run_bytes(canonical, final_bytes)

    record, _ = ops.reserve(
        workspace_id=workspace.workspace_id,
        idempotency_key="crash-ok",
        kind=ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP,
        request_payload={
            "project_id": project.project_id,
            "proposal_count": 5,
            "prelabel_enabled": False,
        },
        expected_revision=None,
    )
    auth = GoldLabBaselineBootstrapAuthority(
        project_id=project.project_id,
        workspace_id=workspace.workspace_id,
        workspace_revision=workspace.revision,
        snapshot_id=snap_id,
        corpus_name=CORPUS_NAME,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        authoring_run_id=authoring_run_id,
        proposal_count=5,
        sampling_seed=42,
        prelabel_enabled=False,
        expected_final_artifact_sha256=expected_sha,
        proposal_attempted=1,
        proposal_succeeded=1,
        proposal_failed=0,
        pool_targeted=1,
        pool_succeeded=1,
        pool_failed=0,
        reviewable_case_count=1,
    )
    ops.update_status(
        workspace.workspace_id,
        record.operation_id,
        ManagedOperationStatus.RUNNING,
        progress_stage=OperationProgressStage.FINALIZING,
        bootstrap_authority=auth,
    )
    out = reconcile_gold_bootstrap_operations(runtime)
    assert record.operation_id in out["reconciled_succeeded"]
    done = ops.get(workspace.workspace_id, record.operation_id)
    assert done.status is ManagedOperationStatus.SUCCEEDED

    # Absent canonical → left for interrupt.
    record2, _ = ops.reserve(
        workspace_id=workspace.workspace_id,
        idempotency_key="crash-absent",
        kind=ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP,
        request_payload={
            "project_id": project.project_id,
            "proposal_count": 5,
            "prelabel_enabled": False,
        },
        expected_revision=None,
    )
    auth2 = auth.model_copy(
        update={
            "authoring_run_id": "authorrun_missing",
            "expected_final_artifact_sha256": "a" * 64,
        }
    )
    ops.update_status(
        workspace.workspace_id,
        record2.operation_id,
        ManagedOperationStatus.RUNNING,
        bootstrap_authority=auth2,
    )
    out2 = reconcile_gold_bootstrap_operations(runtime)
    assert record2.operation_id in out2["left_for_interrupt"]


def test_staging_not_baseline_discoverable_and_scavenge(tmp_path: Path) -> None:
    settings, runtime, project, workspace, corpus_id, chunk_set_id, _ = (
        _project_and_workspace(tmp_path)
    )
    op_id = "wop_staging_only"
    staging = bootstrap_staging_run_path(
        settings, workspace_id=workspace.workspace_id, operation_id=op_id
    )
    staging.parent.mkdir(parents=True, exist_ok=True)
    run = _reviewable_run(
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        authoring_run_id="authorrun_staged",
    )
    write_authoring_run_bytes(staging, serialize_authoring_run_bytes(run))
    with _client(runtime) as client:
        body = client.get(
            f"/v1/gold-lab/projects/{project.project_id}/baselines"
        ).json()
        ids = {b["authoring_run_id"] for b in body["baselines"]}
        assert "authorrun_staged" not in ids
    # TTL scavenge with retention 0 hours.
    removed = scavenge_bootstrap_staging(settings, retention_hours=0)
    assert removed
    assert not staging.exists()


def test_journals_recovery_does_not_interrupt(tmp_path: Path) -> None:
    settings, _runtime, project, workspace, corpus_id, chunk_set_id, snap_id = (
        _project_and_workspace(tmp_path)
    )
    ops = ManagedOperationStore(settings)
    record, _ = ops.reserve(
        workspace_id=workspace.workspace_id,
        idempotency_key="journal-only",
        kind=ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP,
        request_payload={
            "project_id": project.project_id,
            "proposal_count": 5,
            "prelabel_enabled": False,
        },
        expected_revision=None,
    )
    ops.update_status(
        workspace.workspace_id,
        record.operation_id,
        ManagedOperationStatus.RUNNING,
        bootstrap_authority=GoldLabBaselineBootstrapAuthority(
            project_id=project.project_id,
            workspace_id=workspace.workspace_id,
            workspace_revision=workspace.revision,
            snapshot_id=snap_id,
            corpus_name=CORPUS_NAME,
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            authoring_run_id="authorrun_pending",
            proposal_count=5,
            sampling_seed=1,
            prelabel_enabled=False,
        ),
    )
    recover_workspace_journals(settings)
    still = ops.get(workspace.workspace_id, record.operation_id)
    assert still.status is ManagedOperationStatus.RUNNING


def test_cli_propose_still_resolves_current(tmp_path: Path) -> None:
    """CLI wrapper must still call CURRENT resolution (mocked)."""
    settings = _authoring_ready(_integrity_settings(tmp_path))
    with (
        patch(
            "offline_rag.gold_authoring.propose.evaluate_authoring_readiness",
            return_value=MagicMock(ready=True, reason_codes=[]),
        ),
        patch(
            "offline_rag.gold_authoring.propose.authorize_authoring_endpoint",
            return_value=MagicMock(endpoint="http://127.0.0.1:11434/v1"),
        ),
        patch(
            "offline_rag.gold_authoring.propose.load_current_corpus_chunk_snapshot",
            side_effect=Exception("CURRENT path used"),
        ) as current,
        patch(
            "offline_rag.gold_authoring.propose.run_gold_propose_on_snapshot",
        ) as core,
    ):
        with pytest.raises(Exception, match="CURRENT path used"):
            run_gold_propose(settings, corpus_name=CORPUS_NAME, count=1, seed=0)
        current.assert_called_once()
        core.assert_not_called()


def test_allow_production_file_unchanged() -> None:
    path = Path(__file__).resolve().parents[3] / "ALLOW_PRODUCTION"
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        assert text == ""
    else:
        # Absent file is the empty/unchanged production gate.
        assert not path.exists()


# --- IMPL-REWORK-AUTH-001 regressions -------------------------------------


def test_r1_injected_qdrant_avoids_second_storage_owner(tmp_path: Path) -> None:
    """Product 9C must reuse runtime-owned persistent Qdrant Local."""
    from offline_rag.gold_authoring.pool_arms import HistoricalPoolArmExecutor

    settings = _authoring_ready(_integrity_settings(tmp_path))
    constructions: list[Path] = []

    class TrackingBackend:
        def __init__(self, storage_path):  # type: ignore[no-untyped-def]
            constructions.append(Path(storage_path))
            self.storage_path = Path(storage_path)
            self._client = object()

        def close(self) -> None:
            self._client = None

        def search(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return []

    owner = TrackingBackend(settings.paths.qdrant_storage)
    assert len(constructions) == 1

    with patch(
        "offline_rag.gold_authoring.pool_arms.QdrantLocalBackend", TrackingBackend
    ):
        executor = HistoricalPoolArmExecutor(settings, qdrant=owner)  # type: ignore[arg-type]
        assert executor._qdrant is owner
        assert executor._owns_qdrant is False
        assert len(constructions) == 1
        executor.close()
        assert owner._client is not None

        owned = HistoricalPoolArmExecutor(settings)
        assert owned._owns_qdrant is True
        assert owned._qdrant is None
        # Same lazy construction site used by _dense_hits when no owner injected.
        from offline_rag.gold_authoring import pool_arms as pool_arms_mod

        owned._qdrant = pool_arms_mod.QdrantLocalBackend(settings.paths.qdrant_storage)
        assert len(constructions) == 2
        owned.close()
        assert owned._qdrant is None


def test_r1_bootstrap_passes_runtime_qdrant_into_pool(tmp_path: Path) -> None:
    settings, runtime, project, workspace, corpus_id, chunk_set_id, _ = (
        _project_and_workspace(tmp_path)
    )
    svc = GoldLabBaselineBootstrapService(runtime)
    seen: dict[str, object] = {}

    def propose(settings_arg, **kwargs):
        run = _reviewable_run(
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            authoring_run_id=kwargs["authoring_run_id"],
            sampling_seed=kwargs["seed"],
        )
        path = kwargs["output"]
        path.parent.mkdir(parents=True, exist_ok=True)
        write_authoring_run_bytes(path, serialize_authoring_run_bytes(run))
        from offline_rag.gold_authoring.propose import ProposeJobResult

        return ProposeJobResult(exit_code=0, run=run, output_path=path)

    def pool(settings_arg, **kwargs):
        seen["executor"] = kwargs.get("executor")
        from offline_rag.gold_authoring.persist import load_authoring_run
        from offline_rag.gold_authoring.pool import PoolJobResult

        run = load_authoring_run(kwargs["run_path"])
        return PoolJobResult(exit_code=0, run=run, output_path=kwargs["run_path"])

    with (
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_propose_on_snapshot",
            side_effect=propose,
        ),
        patch("offline_rag.app.gold_lab.bootstrap.run_gold_pool", side_effect=pool),
        _patch_ensure_noop(),
        patch(
            "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
            return_value=[object()] * 50,
        ),
        patch(
            "offline_rag.app.gold_lab.bootstrap.validate_historical_chunk_identities",
            return_value=None,
        ),
    ):
        record = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=3,
            prelabel_enabled=False,
            idempotency_key="r1-qdrant",
        )
        deadline = time.time() + 10
        ops = ManagedOperationStore(settings)
        while time.time() < deadline:
            current = ops.get(workspace.workspace_id, record.operation_id)
            if current.status is ManagedOperationStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        assert current.status is ManagedOperationStatus.SUCCEEDED
    executor = seen["executor"]
    assert executor is not None
    assert getattr(executor, "_qdrant", None) is runtime.resources.qdrant
    assert getattr(executor, "_owns_qdrant", True) is False


def test_r1_real_persistent_qdrant_nine_c_product_path(tmp_path: Path) -> None:
    """AUTH-002: real persistent Qdrant Local + real run_gold_pool dense path.

    Proves the F001 product path: runtime owns exclusive Qdrant storage while
    actual HistoricalPoolArmExecutor / run_gold_pool execute six-arm 9C without
    opening a second persistent owner.
    """
    from offline_rag.app.gold_lab import bootstrap as bootstrap_mod
    from offline_rag.gold_authoring import pool_arms as pool_arms_mod
    from offline_rag.gold_authoring.pool_arms import HistoricalPoolArmExecutor

    settings = _pooling_ready_settings(tmp_path)
    snap_id, corpus_id, chunk_set_id, _art_id = _publish_real_qdrant_pooling_ready(
        settings
    )
    workspace = _active_workspace(settings, snap_id)
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=workspace.workspace_id,
        title="R1 Real Qdrant Desk",
        description="",
        project_type=GoldProjectType.BENCHMARK,
    )

    storage = settings.paths.qdrant_storage.expanduser().resolve()
    constructions: list[Path] = []
    orig_init = QdrantLocalBackend.__init__

    def counting_init(self, storage_path):  # type: ignore[no-untyped-def]
        constructions.append(Path(storage_path).expanduser().resolve())
        return orig_init(self, storage_path)

    def fake_make_embedder(_settings: AppSettings) -> FakeEmbedder:
        # FakeEmbedder cannot satisfy model-query-prompt; keep deterministic
        # vectors while exercising the real dense search / ownership path.
        return FakeEmbedder(dimension=8, normalize=True)

    seen_executor: dict[str, object] = {}

    class _ObservingExecutor(HistoricalPoolArmExecutor):
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            super().__init__(*args, **kwargs)
            seen_executor["executor"] = self

    with patch.object(QdrantLocalBackend, "__init__", counting_init):
        runtime = ApplicationRuntime(
            settings=settings,
            factories=ResourceFactories(
                embedder=lambda _s: FakeEmbedder(dimension=8, normalize=True),
                reranker=lambda _s: FakeReranker(),
                generator_client=lambda _s: _Closeable(),
                qdrant=lambda s: QdrantLocalBackend(s.paths.qdrant_storage),
            ),
        )
        runtime.start()
        assert runtime.resources is not None
        assert isinstance(runtime.resources.qdrant, QdrantLocalBackend)
        assert len(constructions) == 1
        assert constructions[0] == storage
        owner = runtime.resources.qdrant

        def propose(settings_arg, **kwargs):
            # Deterministic 9B: write a query that hits lexical offline/rag terms.
            run = _reviewable_run(
                corpus_id=corpus_id,
                chunk_set_id=chunk_set_id,
                authoring_run_id=kwargs["authoring_run_id"],
                sampling_seed=kwargs["seed"],
            )
            # Clear pre-seeded candidates so real 9C builds the pool.
            cases = [c.model_copy(update={"candidates": []}) for c in run.cases]
            run = run.model_copy(
                update={
                    "corpus_id": corpus_id,
                    "chunk_set_id": chunk_set_id,
                    "cases": cases,
                    "pool_successful_case_count": 0,
                }
            )
            path = kwargs["output"]
            path.parent.mkdir(parents=True, exist_ok=True)
            write_authoring_run_bytes(path, serialize_authoring_run_bytes(run))
            return ProposeJobResult(exit_code=0, run=run, output_path=path)

        svc = GoldLabBaselineBootstrapService(runtime)
        with (
            patch(
                "offline_rag.app.gold_lab.bootstrap.run_gold_propose_on_snapshot",
                side_effect=propose,
            ),
            # Real run_gold_pool remains unbound — only observe executor construction.
            patch.object(
                bootstrap_mod, "HistoricalPoolArmExecutor", _ObservingExecutor
            ),
            patch.object(
                pool_arms_mod, "make_embedder", side_effect=fake_make_embedder
            ),
            patch(
                "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
                return_value=[object()] * 50,
            ),
        ):
            record = svc.start_baseline_bootstrap(
                project_id=project.project_id,
                proposal_count=3,
                prelabel_enabled=False,
                idempotency_key="r1-real-qdrant-9c",
            )
            deadline = time.time() + 30
            ops = ManagedOperationStore(settings)
            current = ops.get(workspace.workspace_id, record.operation_id)
            while time.time() < deadline:
                current = ops.get(workspace.workspace_id, record.operation_id)
                if current.status in (
                    ManagedOperationStatus.SUCCEEDED,
                    ManagedOperationStatus.FAILED,
                ):
                    break
                time.sleep(0.05)
            else:
                pytest.fail(
                    f"bootstrap did not finish: {current.status} {current.error}"
                )

        assert current.status is ManagedOperationStatus.SUCCEEDED, (
            f"bootstrap failed: {current.error}"
        )
        executor = seen_executor.get("executor")
        assert executor is not None
        assert getattr(executor, "_qdrant", None) is owner
        assert getattr(executor, "_owns_qdrant", True) is False
        # No second persistent Qdrant Local owner for the same storage path.
        assert constructions == [storage]
        assert current.bootstrap_authority is not None
        assert current.bootstrap_authority.reviewable_case_count >= 1
        assert current.result is not None
        assert current.result.baseline_eligible is True

        # Canonical published run must be reviewable after real 9C.
        auth = current.bootstrap_authority
        published = default_authoring_run_path(
            settings,
            corpus_name=CORPUS_NAME,
            authoring_run_id=auth.authoring_run_id,
        )
        run = load_authoring_run(published)
        assert sum(1 for c in run.cases if is_reviewable_case(c)) >= 1
        assert (run.pool_successful_case_count or 0) >= 1


def test_r2_pool_and_prelabel_persistence_failures(tmp_path: Path) -> None:
    from offline_rag.gold_authoring.pool import PoolJobResult
    from offline_rag.gold_authoring.prelabel import PrelabelJobResult
    from offline_rag.gold_authoring.propose import ProposeJobResult

    settings, runtime, project, workspace, corpus_id, chunk_set_id, _ = (
        _project_and_workspace(tmp_path)
    )
    svc = GoldLabBaselineBootstrapService(runtime)

    def propose(settings_arg, **kwargs):
        run = _reviewable_run(
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            authoring_run_id=kwargs["authoring_run_id"],
            sampling_seed=kwargs["seed"],
        )
        path = kwargs["output"]
        path.parent.mkdir(parents=True, exist_ok=True)
        write_authoring_run_bytes(path, serialize_authoring_run_bytes(run))
        return ProposeJobResult(exit_code=0, run=run, output_path=path)

    def pool_persist_fail(settings_arg, **kwargs):
        return PoolJobResult(
            exit_code=2,
            run=None,
            output_path=None,
            message="failed to persist enriched authoring run: /secret/pool.json",
        )

    with (
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_propose_on_snapshot",
            side_effect=propose,
        ),
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_pool",
            side_effect=pool_persist_fail,
        ),
        _patch_ensure_noop(),
        patch(
            "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
            return_value=[object()] * 50,
        ),
    ):
        record = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=2,
            prelabel_enabled=False,
            idempotency_key="r2-pool",
        )
        deadline = time.time() + 10
        ops = ManagedOperationStore(settings)
        while time.time() < deadline:
            current = ops.get(workspace.workspace_id, record.operation_id)
            if current.status is ManagedOperationStatus.FAILED:
                break
            time.sleep(0.05)
        assert current.error is not None
        assert current.error.details["reason"] == "bootstrap_internal_failure"
        assert "/secret/pool.json" not in (current.error.message or "")

    def pool_ok(settings_arg, **kwargs):
        from offline_rag.gold_authoring.persist import load_authoring_run

        run = load_authoring_run(kwargs["run_path"])
        return PoolJobResult(exit_code=0, run=run, output_path=kwargs["run_path"])

    def prelabel_persist_fail(settings_arg, **kwargs):
        return PrelabelJobResult(
            exit_code=2,
            run=None,
            output_path=None,
            message="failed to persist: /secret/prelabel.json provider=boom",
        )

    with (
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_propose_on_snapshot",
            side_effect=propose,
        ),
        patch("offline_rag.app.gold_lab.bootstrap.run_gold_pool", side_effect=pool_ok),
        _patch_ensure_noop(),
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_prelabel",
            side_effect=prelabel_persist_fail,
        ),
        patch(
            "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
            return_value=[object()] * 50,
        ),
    ):
        record = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=2,
            prelabel_enabled=True,
            idempotency_key="r2-prelabel",
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            current = ops.get(workspace.workspace_id, record.operation_id)
            if current.status is ManagedOperationStatus.FAILED:
                break
            time.sleep(0.05)
        assert current.error is not None
        assert current.error.details["reason"] == "bootstrap_internal_failure"
        blob = json.dumps(current.error.model_dump(mode="json"))
        assert "/secret/prelabel.json" not in blob
        assert "provider=boom" not in blob


def test_r3_worker_launch_failure_returns_failed_op(tmp_path: Path) -> None:
    _settings, runtime, project, _workspace, *_ = _project_and_workspace(tmp_path)
    svc = GoldLabBaselineBootstrapService(runtime)
    with patch("threading.Thread.start", side_effect=RuntimeError("thread boom")):
        record = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=2,
            prelabel_enabled=False,
            idempotency_key="r3-launch",
        )
    assert record.status is ManagedOperationStatus.FAILED
    assert record.error is not None
    assert record.error.details["reason"] == "bootstrap_internal_failure"
    # Capacity released — a subsequent admit can acquire again.
    control = runtime.operations.admit_gold_bootstrap()
    runtime.operations.release(control)


def test_r3_publication_capture_failure_is_post_admission(tmp_path: Path) -> None:
    settings, runtime, project, workspace, *_ = _project_and_workspace(tmp_path)
    svc = GoldLabBaselineBootstrapService(runtime)
    with patch.object(
        runtime.publication,
        "resolve_snapshot",
        side_effect=RuntimeError("bind failed /secret/snap.json"),
    ):
        record = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=2,
            prelabel_enabled=False,
            idempotency_key="r3-capture",
        )
    assert record.status is ManagedOperationStatus.FAILED
    assert record.error is not None
    assert record.error.code is ErrorCode.SNAPSHOT_UNAVAILABLE
    assert record.error.details["reason"] == "captured_chunk_set_unavailable"
    assert "/secret/snap.json" not in record.error.message
    stored = ManagedOperationStore(settings).find_by_idempotency(
        workspace.workspace_id, "r3-capture"
    )
    assert stored is not None
    assert stored.operation_id == record.operation_id


def test_r5_zero_reviewable_reconcile_not_succeeded(tmp_path: Path) -> None:
    settings, runtime, project, workspace, corpus_id, chunk_set_id, snap_id = (
        _project_and_workspace(tmp_path)
    )
    ops = ManagedOperationStore(settings)
    authoring_run_id = "authorrun_zero_review"
    run = GoldAuthoringRun(
        authoring_run_id=authoring_run_id,
        authorcfg_id="authorcfg_" + ("a" * 64),
        network_policy="localhost_only",
        created_at=datetime.now(tz=UTC),
        corpus_name=CORPUS_NAME,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        sampling_seed=1,
        cases=[
            SilverCase(
                draft_case_id="draft_inert",
                proposed_query="ignored",
                candidates=[],
            )
        ],
    )
    final_bytes = serialize_authoring_run_bytes(run)
    expected_sha = hashlib.sha256(final_bytes).hexdigest()
    canonical = default_authoring_run_path(
        settings, corpus_name=CORPUS_NAME, authoring_run_id=authoring_run_id
    )
    canonical.parent.mkdir(parents=True, exist_ok=True)
    write_authoring_run_bytes(canonical, final_bytes)
    record, _ = ops.reserve(
        workspace_id=workspace.workspace_id,
        idempotency_key="r5-zero",
        kind=ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP,
        request_payload={
            "project_id": project.project_id,
            "proposal_count": 5,
            "prelabel_enabled": False,
        },
        expected_revision=None,
    )
    auth = GoldLabBaselineBootstrapAuthority(
        project_id=project.project_id,
        workspace_id=workspace.workspace_id,
        workspace_revision=workspace.revision,
        snapshot_id=snap_id,
        corpus_name=CORPUS_NAME,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        authoring_run_id=authoring_run_id,
        proposal_count=5,
        sampling_seed=1,
        prelabel_enabled=False,
        expected_final_artifact_sha256=expected_sha,
        reviewable_case_count=0,
    )
    ops.update_status(
        workspace.workspace_id,
        record.operation_id,
        ManagedOperationStatus.RUNNING,
        bootstrap_authority=auth,
    )
    out = reconcile_gold_bootstrap_operations(runtime)
    assert record.operation_id in out["left_for_interrupt"]
    still = ops.get(workspace.workspace_id, record.operation_id)
    assert still.status is ManagedOperationStatus.RUNNING
    assert still.result is None


def test_r6_workspace_ops_cannot_jump_to_succeeded(tmp_path: Path) -> None:
    settings, _runtime, _project, workspace, *_ = _project_and_workspace(tmp_path)
    ops = ManagedOperationStore(settings)
    record, _ = ops.reserve(
        workspace_id=workspace.workspace_id,
        idempotency_key="r6-ws",
        kind=ManagedOperationKind.SOURCE_ADD,
        request_payload={"files": ["a.pdf"]},
        expected_revision=1,
    )
    with pytest.raises(AppError) as exc:
        ops.update_status(
            workspace.workspace_id,
            record.operation_id,
            ManagedOperationStatus.SUCCEEDED,
        )
    assert exc.value.details["reason"] == "illegal_operation_status_transition"
    prep = ops.update_status(
        workspace.workspace_id,
        record.operation_id,
        ManagedOperationStatus.PREPARING,
    )
    assert prep.status is ManagedOperationStatus.PREPARING
    with pytest.raises(AppError) as exc2:
        ops.update_status(
            workspace.workspace_id,
            record.operation_id,
            ManagedOperationStatus.SUCCEEDED,
        )
    assert exc2.value.details["reason"] == "illegal_operation_status_transition"


def test_pooling_zero_reviewable_preserves_safe_reason_on_get(tmp_path: Path) -> None:
    """POST-admission pooling GOLD_CONFLICT reason survives GET /v1/operations."""
    settings, runtime, project, workspace, corpus_id, chunk_set_id, _ = (
        _project_and_workspace(tmp_path)
    )
    svc = GoldLabBaselineBootstrapService(runtime)

    def propose(settings_arg, **kwargs):
        run = _reviewable_run(
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            authoring_run_id=kwargs["authoring_run_id"],
            sampling_seed=kwargs["seed"],
        )
        path = kwargs["output"]
        path.parent.mkdir(parents=True, exist_ok=True)
        write_authoring_run_bytes(path, serialize_authoring_run_bytes(run))
        return ProposeJobResult(exit_code=0, run=run, output_path=path)

    def pool(settings_arg, **kwargs):
        from offline_rag.gold_authoring.persist import load_authoring_run
        from offline_rag.gold_authoring.pool import PoolJobResult

        run = load_authoring_run(kwargs["run_path"])
        stripped = [
            case.model_copy(update={"candidates": []}) for case in run.cases
        ]
        bare = run.model_copy(
            update={"cases": stripped, "pool_successful_case_count": 0}
        )
        return PoolJobResult(exit_code=0, run=bare, output_path=kwargs["run_path"])

    with (
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_propose_on_snapshot",
            side_effect=propose,
        ),
        patch("offline_rag.app.gold_lab.bootstrap.run_gold_pool", side_effect=pool),
        _patch_ensure_noop(),
        patch(
            "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
            return_value=[object()] * 50,
        ),
        patch(
            "offline_rag.app.gold_lab.bootstrap.validate_historical_chunk_identities",
            return_value=None,
        ),
    ):
        record = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=2,
            prelabel_enabled=False,
            idempotency_key="zero-review-get",
        )
        deadline = time.time() + 10
        ops = ManagedOperationStore(settings)
        while time.time() < deadline:
            current = ops.get(workspace.workspace_id, record.operation_id)
            if current.status is ManagedOperationStatus.FAILED:
                break
            time.sleep(0.05)
        else:
            pytest.fail(f"expected FAILED: {current.status} {current.error}")

        assert current.progress_stage is OperationProgressStage.POOLING
        assert current.error is not None
        assert current.error.code is ErrorCode.GOLD_CONFLICT
        assert current.error.details["reason"] == "zero_reviewable_cases"

        with _client(runtime) as client:
            view = client.get(f"/v1/operations/{record.operation_id}").json()
        assert view["status"] == "failed"
        assert view["progress_stage"] == "pooling"
        assert view["error"]["code"] == "gold_conflict"
        assert view["error"]["details"]["reason"] == "zero_reviewable_cases"
        assert view["error"]["retryable"] is False


def test_proposing_population_exceeded_preserves_safe_reason_on_get(
    tmp_path: Path,
) -> None:
    settings, runtime, project, workspace, *_rest = _project_and_workspace(tmp_path)
    svc = GoldLabBaselineBootstrapService(runtime)

    with (
        patch(
            "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
            return_value=[object(), object()],
        ),
        patch(
            "offline_rag.app.gold_lab.bootstrap.validate_historical_chunk_identities",
            return_value=None,
        ),
    ):
        record = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=5,
            prelabel_enabled=False,
            idempotency_key="pop-exceed-get",
        )
        deadline = time.time() + 10
        ops = ManagedOperationStore(settings)
        while time.time() < deadline:
            current = ops.get(workspace.workspace_id, record.operation_id)
            if current.status is ManagedOperationStatus.FAILED:
                break
            time.sleep(0.05)
        else:
            pytest.fail(f"expected FAILED: {current.status} {current.error}")

        assert current.progress_stage is OperationProgressStage.PROPOSING
        assert current.error is not None
        assert current.error.details["reason"] == (
            "proposal_count_exceeds_eligible_population"
        )

        with _client(runtime) as client:
            view = client.get(f"/v1/operations/{record.operation_id}").json()
        assert view["status"] == "failed"
        assert view["progress_stage"] == "proposing"
        assert view["error"]["code"] == "gold_conflict"
        assert view["error"]["details"]["reason"] == (
            "proposal_count_exceeds_eligible_population"
        )
