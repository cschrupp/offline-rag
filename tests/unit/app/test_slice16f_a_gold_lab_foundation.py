"""Slice 16F-A — Gold Lab contracts & persistence foundation."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.gold_lab import (
    ABSOLUTE_RELEVANCE_CONTRACT,
    AUXILIARY_PREFERENCE_CONTRACT,
    HARD_CALL_DESIGNATION_CONTRACT,
    HARD_CALLS_SCHEMA,
    LEDGER_SCHEMA,
    QUESTION_CHECK_CONTRACT,
    GoldCampaignService,
    GoldLabError,
    GoldLabLedger,
    GoldLabStore,
    GoldLedgerRecordType,
    GoldProjectStatus,
    GoldProjectType,
    HardCallDesignation,
    HardCallsArtifact,
    absolute_relevance_task_id,
    auxiliary_preference_task_id,
    build_selection_policy,
    hard_call_designation_id,
    is_reviewable_case,
    new_campaign_id,
    new_judgment_id,
    new_ledger_record_id,
    new_project_id,
    query_fingerprint,
    question_check_task_id,
    selection_policy_fingerprint,
    validate_campaign_id,
    validate_judgment_id,
    validate_project_id,
    validate_record_id,
    validate_request_fingerprint,
    validate_selection_policy_fingerprint,
    validate_task_id,
)
from offline_rag.app.gold_lab.baseline import assert_pristine_baseline
from offline_rag.app.gold_lab.leases import GoldLabCampaignLease
from offline_rag.app.gold_lab.models import (
    AbsoluteRelevancePayload,
    GoldSelectionPolicy,
)
from offline_rag.app.gold_lab.paths import (
    campaign_dir,
    campaign_json_path,
    campaigns_root,
    datasets_root,
    gold_lab_root,
    project_dir,
    project_json_path,
    projects_root,
    registrations_root,
)
from offline_rag.app.paths import ensure_data_directories, required_data_directories
from offline_rag.app.publication import ProductPublicationRegistry
from offline_rag.app.snapshot import CanonicalSnapshotManifest
from offline_rag.app.workspace.models import (
    SourceVersionRecord,
    WorkspaceStatus,
    new_empty_workspace,
    new_source_id,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.chunking.persistence import write_chunk_artifact
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings, PathSettings
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.domain.chunking import (
    ChunkSetDocumentEntry,
    ChunkSetManifest,
    DocumentChunkArtifact,
)
from offline_rag.domain.corpus import CorpusDocumentEntry, CorpusManifest
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import DenseIndexManifest, LexicalIndexManifest
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase, SourceSeed
from offline_rag.gold_authoring.pooling_models import PoolCandidate
from offline_rag.gold_authoring.review_models import (
    CategoryOverride,
    HumanJudgment,
    HumanReview,
    HumanReviewStatus,
)
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.rerank.config_hash import build_reranker_config_hash

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"

CHUNK_A = "chunk_a_16fa"
CHUNK_B = "chunk_b_16fa"
DOC_ID = "doc_16fa"
CORPUS_ID = "corpus_16fa"
CHUNK_SET_ID = "chunkset_16fa"
CORPUS_NAME = "goldlab16fa"


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
    from offline_rag.chunking.tokenize import TiktokenTokenCounter

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


def _write_chunks(settings: AppSettings) -> None:
    child_a = Chunk(
        chunk_id=CHUNK_A,
        document_id=DOC_ID,
        kind=ChunkKind.CHILD,
        text="alpha candidate text for gold lab",
        order=0,
        token_count=4,
        content_hash="ch_a",
        source_block_ids=["blk_a"],
    )
    child_b = Chunk(
        chunk_id=CHUNK_B,
        document_id=DOC_ID,
        kind=ChunkKind.CHILD,
        text="beta candidate text for gold lab",
        order=1,
        token_count=4,
        content_hash="ch_b",
        source_block_ids=["blk_b"],
    )
    artifact = DocumentChunkArtifact(
        chunk_artifact_id="chunkart_16fa",
        parsed_artifact_id="parsed_16fa",
        document_id=DOC_ID,
        chunk_config_hash="cfg_chunk",
        chunker_version="v1",
        tokenizer_name="tiktoken",
        tokenizer_encoding="cl100k_base",
        parents=[],
        children=[child_a, child_b],
        parent_count=0,
        child_count=2,
    )
    write_chunk_artifact(settings.paths.chunks, artifact)


def _publish_bound(
    settings: AppSettings,
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
    corpus_manifest_name = f"{CORPUS_ID}.json"
    chunk_manifest_name = f"{CHUNK_SET_ID}.json"
    dense_index_id = "denseindex_16fa"
    lexical_index_id = "lexical_16fa"
    dense_manifest_name = f"{dense_index_id}.json"
    lexical_manifest_name = f"{lexical_index_id}.json"
    collection_name = "col_16fa"

    corpus = CorpusManifest(
        corpus_id=CORPUS_ID,
        corpus_hash="corphash_16fa",
        created_at=now,
        config_hash="cfg_corpus",
        documents=[
            CorpusDocumentEntry(
                document_id=DOC_ID,
                source_path="/secret/absolute/path/spec.pdf",
                source_name="spec.pdf",
                source_content_hash="ch_16fa",
                source_size_bytes=12,
                source_media_type="application/pdf",
                parser_name="docling_pdf",
                parser_version="v1",
                block_count=1,
                processed_artifact="processed/x.json",
                processed_artifact_hash="pah_1",
                parsed_artifact_id="parsed_16fa",
                parse_config_hash="cfg_parse",
            )
        ],
    )
    _write_chunks(settings)
    chunk = ChunkSetManifest(
        chunk_set_id=CHUNK_SET_ID,
        corpus_id=CORPUS_ID,
        chunk_config_hash="cfg_chunk",
        chunker_version="v1",
        tokenizer_name="tiktoken",
        tokenizer_encoding="cl100k_base",
        created_at=now,
        documents=[
            ChunkSetDocumentEntry(
                document_id=DOC_ID,
                parsed_artifact_id="parsed_16fa",
                chunk_artifact_id="chunkart_16fa",
                chunk_artifact="chunks/chunkart_16fa.json",
                chunk_artifact_hash="art_placeholder",
                parent_count=0,
                child_count=2,
            )
        ],
        total_parent_count=0,
        total_child_count=2,
    )
    dense = DenseIndexManifest(
        index_id=dense_index_id,
        corpus_id=CORPUS_ID,
        chunk_set_id=CHUNK_SET_ID,
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
        expected_child_count=2,
        indexed_child_count=2,
        created_at=now,
    )
    lexical = LexicalIndexManifest(
        lexical_index_id=lexical_index_id,
        corpus_id=CORPUS_ID,
        chunk_set_id=CHUNK_SET_ID,
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
        expected_child_count=2,
        indexed_child_count=2,
        document_count=1,
        vocabulary_size=2,
        avgdl=1.0,
        physical_index_relpath=f"{lexical_index_id}",
        created_at=now,
    )
    for root in (
        settings.paths.manifests,
        settings.paths.chunk_manifests,
        settings.paths.index_manifests,
        settings.paths.lexical_index_manifests,
        settings.paths.lexical_indexes,
    ):
        root.mkdir(parents=True, exist_ok=True)
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
                chunk_id=CHUNK_A, terms=["offline", "rag"], document_id=DOC_ID
            ),
            LexicalDocumentInput(
                chunk_id=CHUNK_B, terms=["gold", "lab"], document_id=DOC_ID
            ),
        ],
        chunk_set_id=CHUNK_SET_ID,
        lexical_config_hash=hashes["lexical_config_hash"],
    )
    q.counts[collection_name] = 2
    identity = CanonicalSnapshotManifest(
        corpus_id=CORPUS_ID,
        corpus_manifest=corpus_manifest_name,
        chunk_set_id=CHUNK_SET_ID,
        chunk_manifest=chunk_manifest_name,
        dense_index_id=dense_index_id,
        dense_index_manifest=dense_manifest_name,
        lexical_index_id=lexical_index_id,
        lexical_index_manifest=lexical_manifest_name,
        **hashes,
    )
    registry = ProductPublicationRegistry(settings, qdrant=q)
    snapshot_id = registry.publish(
        CORPUS_NAME, identity, require_current_config_match=True
    )
    return registry, snapshot_id, identity


def _active_workspace(
    settings: AppSettings, snapshot_id: str, *, title: str = "Gold Lab Desk"
) -> object:
    store = WorkspaceStore(settings)
    empty = store.create(
        new_empty_workspace(title=title).model_copy(
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


def _baseline(
    *,
    cases: list[SilverCase] | None = None,
    corpus_name: str | None = CORPUS_NAME,
    corpus_id: str | None = CORPUS_ID,
    chunk_set_id: str | None = CHUNK_SET_ID,
    authoring_run_id: str = "authorrun_16fa",
) -> GoldAuthoringRun:
    if cases is None:
        cases = [
            SilverCase(
                draft_case_id="draft_reviewable",
                proposed_query="What is offline RAG?",
                source_seed=SourceSeed(chunk_id=CHUNK_A, document_id=DOC_ID),
                candidates=[
                    PoolCandidate(chunk_id=CHUNK_A, document_id=DOC_ID),
                    PoolCandidate(chunk_id=CHUNK_B, document_id=DOC_ID),
                ],
            ),
            SilverCase(draft_case_id="draft_inert"),  # zero candidates preserved
        ]
    return GoldAuthoringRun(
        authoring_run_id=authoring_run_id,
        authorcfg_id="authorcfg_" + ("a" * 64),
        network_policy="localhost_only",
        corpus_name=corpus_name,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        created_at=datetime(2026, 10, 8, tzinfo=UTC),
        cases=cases,
    )


def _policy(*, project_type: GoldProjectType = GoldProjectType.BENCHMARK, **params):
    return build_selection_policy(
        selection_policy_id="selpol_16fa",
        project_type=project_type,
        parameters=params or {"top_k": 5},
    )


def _reqfp(payload: dict) -> str:
    from offline_rag.app.workspace.models import canonical_request_fingerprint

    return canonical_request_fingerprint(payload)


# --- A. PATHS ---


def test_gold_lab_default_root_and_remap(tmp_path: Path) -> None:
    assert PathSettings().gold_lab == Path("data/gold-lab")
    settings = _settings(tmp_path)
    assert settings.paths.gold_lab == (tmp_path / "data" / "gold-lab").resolve() or (
        settings.paths.gold_lab == tmp_path / "data" / "gold-lab"
    )
    assert gold_lab_root(settings) == settings.paths.gold_lab
    assert settings.paths.gold_lab in required_data_directories(settings)
    assert settings.paths.gold_lab.is_dir()
    for root in (
        projects_root(settings),
        campaigns_root(settings),
        datasets_root(settings),
        registrations_root(settings),
    ):
        root.mkdir(parents=True, exist_ok=True)
        assert root.is_dir()


# --- B. IDS ---


def test_identity_helpers_and_contracts() -> None:
    assert new_project_id().startswith("goldproj_")
    assert new_campaign_id().startswith("goldcamp_")
    assert new_ledger_record_id().startswith("goldrec_")
    assert new_judgment_id().startswith("goldjud_")
    assert ABSOLUTE_RELEVANCE_CONTRACT == "gold-absolute-relevance-v1"
    assert QUESTION_CHECK_CONTRACT == "gold-question-check-v1"
    assert AUXILIARY_PREFERENCE_CONTRACT == "gold-auxiliary-preference-v1"
    assert HARD_CALL_DESIGNATION_CONTRACT == "gold-hard-call-designation-v1"
    assert LEDGER_SCHEMA == "offline-rag-gold-lab-ledger-v1"
    assert HARD_CALLS_SCHEMA == "offline-rag-gold-hard-calls-v1"

    abs1 = absolute_relevance_task_id(
        campaign_id="goldcamp_x", case_id="c1", candidate_chunk_id="chunk_a"
    )
    abs2 = absolute_relevance_task_id(
        campaign_id="goldcamp_x", case_id="c1", candidate_chunk_id="chunk_a"
    )
    assert abs1 == abs2 and abs1.startswith("goldtask_")
    q1 = question_check_task_id(campaign_id="goldcamp_x", case_id="c1")
    assert q1.startswith("goldtask_")
    assert q1 != abs1
    pair1 = auxiliary_preference_task_id(
        campaign_id="goldcamp_x",
        case_id="c1",
        candidate_a="chunk_b",
        candidate_b="chunk_a",
    )
    pair2 = auxiliary_preference_task_id(
        campaign_id="goldcamp_x",
        case_id="c1",
        candidate_a="chunk_a",
        candidate_b="chunk_b",
    )
    assert pair1 == pair2
    different = absolute_relevance_task_id(
        campaign_id="goldcamp_x", case_id="c1", candidate_chunk_id="chunk_b"
    )
    assert different != abs1
    fp1 = query_fingerprint("  Hello World  ")
    fp2 = query_fingerprint("Hello World")
    assert fp1 == fp2 and fp1.startswith("goldquery_")


# --- C. SELECTION POLICY ---


def test_selection_policy_fingerprint_rules() -> None:
    fp_a = selection_policy_fingerprint(
        selection_policy_id="selpol_1",
        project_type="benchmark",
        parameters={"b": 2, "a": 1},
    )
    fp_b = selection_policy_fingerprint(
        selection_policy_id="selpol_1",
        project_type="benchmark",
        parameters={"a": 1, "b": 2},
    )
    assert fp_a == fp_b and fp_a.startswith("cfg_")
    fp_c = selection_policy_fingerprint(
        selection_policy_id="selpol_1",
        project_type="benchmark",
        parameters={"a": 1, "b": 3},
    )
    assert fp_c != fp_a
    policy = build_selection_policy(
        selection_policy_id="selpol_1",
        project_type=GoldProjectType.BENCHMARK,
        parameters={"a": 1},
    )
    with pytest.raises(ValidationError):
        GoldSelectionPolicy(
            selection_policy_id=policy.selection_policy_id,
            project_type=GoldProjectType.IMPROVEMENT,
            parameters=policy.parameters,
            selection_policy_fingerprint=policy.selection_policy_fingerprint,
        )
    with pytest.raises(GoldLabError) as exc:
        selection_policy_fingerprint(
            selection_policy_id="selpol_1",
            project_type="benchmark",
            parameters={"x": math.nan},
        )
    assert exc.value.reason == "selection_policy_parameters_invalid"
    with pytest.raises(GoldLabError):
        selection_policy_fingerprint(
            selection_policy_id="selpol_1",
            project_type="benchmark",
            parameters={"x": math.inf},
        )
    with pytest.raises(GoldLabError):
        selection_policy_fingerprint(
            selection_policy_id="selpol_1",
            project_type="benchmark",
            parameters={"x": Path("/tmp")},
        )
    with pytest.raises(GoldLabError):
        selection_policy_fingerprint(
            selection_policy_id="selpol_1",
            project_type="benchmark",
            parameters={"x": datetime.now(tz=UTC)},
        )


# --- D. PROJECTS ---


def test_project_crud_and_lifecycle(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    del registry
    ws = _active_workspace(settings, snapshot_id)
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Bench",
        description="d",
        project_type=GoldProjectType.BENCHMARK,
    )
    assert store.get_project(project.project_id).title == "Bench"
    assert len(store.list_projects()) == 1
    with pytest.raises(GoldLabError) as exc:
        store.create_project(
            workspace_id=ws.workspace_id,
            title="Dup",
            project_type=GoldProjectType.BENCHMARK,
            project_id=project.project_id,
        )
    assert exc.value.reason == "project_already_exists"
    archived = store.archive_project(project.project_id)
    assert archived.status is GoldProjectStatus.ARCHIVED
    with pytest.raises(GoldLabError) as exc:
        store.unarchive_project(project.project_id)
    assert exc.value.reason == "project_unarchive_forbidden"
    svc = GoldCampaignService(settings, qdrant=_FakeQdrant())
    # re-publish qdrant counts for resolve
    registry, snapshot_id2, _ = _publish_bound(settings)
    assert snapshot_id2 == snapshot_id
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(),
            selection_policy=_policy(),
        )
    assert exc.value.reason == "project_archived"
    del registry


# --- E. BASELINE ADMISSION ---


def test_baseline_admission_matrix() -> None:
    assert_pristine_baseline(_baseline())
    pristine = _baseline(
        cases=[
            SilverCase(
                draft_case_id="d1",
                proposed_query="q",
                candidates=[PoolCandidate(chunk_id=CHUNK_A)],
                human_review=HumanReview(status=HumanReviewStatus.PENDING),
            )
        ]
    )
    assert_pristine_baseline(pristine)

    def _reject(case: SilverCase, *, reason: str = "baseline_human_state_present") -> None:
        run = _baseline(cases=[case])
        with pytest.raises(GoldLabError) as exc:
            assert_pristine_baseline(run)
        assert exc.value.reason == reason

    _reject(
        SilverCase(
            draft_case_id="d1",
            proposed_query="q",
            candidates=[PoolCandidate(chunk_id=CHUNK_A)],
            human_review=HumanReview(
                status=HumanReviewStatus.PENDING,
                judgments=[HumanJudgment(chunk_id=CHUNK_A, relevance=1)],
                grade_basis_query="q",
            ),
        )
    )
    _reject(
        SilverCase(
            draft_case_id="d1",
            proposed_query="q",
            candidates=[PoolCandidate(chunk_id=CHUNK_A)],
            human_review=HumanReview(status=HumanReviewStatus.REJECTED),
        )
    )
    _reject(
        SilverCase(
            draft_case_id="d1",
            proposed_query="q",
            candidates=[PoolCandidate(chunk_id=CHUNK_A)],
            human_review=HumanReview(
                status=HumanReviewStatus.PENDING,
                query_override="edited query",
            ),
        )
    )
    _reject(
        SilverCase(
            draft_case_id="d1",
            proposed_query="q",
            candidates=[PoolCandidate(chunk_id=CHUNK_A)],
            human_review=HumanReview(
                status=HumanReviewStatus.PENDING,
                category_override=CategoryOverride(is_overridden=True, value="other"),
            ),
        )
    )
    _reject(
        SilverCase(
            draft_case_id="d1",
            proposed_query="q",
            candidates=[PoolCandidate(chunk_id=CHUNK_A)],
            human_review=HumanReview(
                status=HumanReviewStatus.PENDING,
                tags_override=["t1"],
            ),
        )
    )
    # grade_basis with empty judgments is rejected by HumanReview; use construct.
    bad_basis = SilverCase.model_construct(
        draft_case_id="d1",
        proposed_query="q",
        proposed_category=None,
        proposed_tags=[],
        proposal_rationale=None,
        source_seed=None,
        candidates=[PoolCandidate(chunk_id=CHUNK_A)],
        model_judgments=[],
        prelabel_provenance=None,
        prelabel_summary=None,
        human_review=HumanReview.model_construct(
            status=HumanReviewStatus.PENDING,
            judgments=[],
            query_override=None,
            category_override=CategoryOverride(),
            tags_override=None,
            grade_basis_query="q",
        ),
    )
    with pytest.raises(GoldLabError) as exc:
        assert_pristine_baseline(_baseline(cases=[bad_basis]))
    assert exc.value.reason == "baseline_human_state_present"

    for field, value in (
        ("corpus_name", None),
        ("corpus_id", None),
        ("chunk_set_id", None),
    ):
        kwargs = {
            "corpus_name": CORPUS_NAME,
            "corpus_id": CORPUS_ID,
            "chunk_set_id": CHUNK_SET_ID,
        }
        kwargs[field] = value
        with pytest.raises(GoldLabError) as exc:
            assert_pristine_baseline(_baseline(**kwargs))
        assert exc.value.reason == "baseline_identity_missing"


# --- H. REVIEWABLE ---


def test_reviewable_case_helper() -> None:
    ok = SilverCase(
        draft_case_id="d1",
        proposed_query="hello",
        candidates=[PoolCandidate(chunk_id=CHUNK_A)],
    )
    assert is_reviewable_case(ok) is True
    assert is_reviewable_case(SilverCase(draft_case_id="d2", proposed_query=None)) is False
    assert (
        is_reviewable_case(SilverCase(draft_case_id="d3", proposed_query="  ")) is False
    )
    assert (
        is_reviewable_case(
            SilverCase(draft_case_id="d4", proposed_query="hello", candidates=[])
        )
        is False
    )


# --- F/G/I/J campaign publication ---


def test_campaign_publication_binding_and_hard_calls(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, identity = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id)
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Bench",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    baseline = _baseline()
    original_json = baseline.model_dump_json()
    campaign_id = new_campaign_id()
    target = absolute_relevance_task_id(
        campaign_id=campaign_id,
        case_id="draft_reviewable",
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
        baseline=baseline,
        selection_policy=_policy(),
        hard_call_designations=[designation],
        campaign_id=campaign_id,
    )
    root = campaign_dir(settings, campaign.campaign_id)
    assert (root / "campaign.json").is_file()
    assert (root / "hard_calls.json").is_file()
    assert (root / "baseline" / "authoring_run.json").is_file()
    assert (root / "ledger").is_dir()
    assert (root / "projection").is_dir()
    staged_bytes = (root / "baseline" / "authoring_run.json").read_bytes()
    assert hashlib.sha256(staged_bytes).hexdigest() == campaign.baseline_sha256
    assert original_json.encode("utf-8") == baseline.model_dump_json().encode("utf-8")
    assert campaign.snapshot_id == snapshot_id
    assert campaign.chunk_set_id == identity.chunk_set_id
    assert campaign.workspace_revision_at_creation == ws.revision

    # empty hard calls valid
    campaign_id2 = new_campaign_id()
    c2 = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(authoring_run_id="authorrun_16fa_b"),
        selection_policy=_policy(),
        campaign_id=campaign_id2,
    )
    artifact = HardCallsArtifact.model_validate_json(
        (campaign_dir(settings, c2.campaign_id) / "hard_calls.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact.designations == []

    # overwrite rejected
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(authoring_run_id="authorrun_16fa_c"),
            selection_policy=_policy(),
            campaign_id=campaign.campaign_id,
        )
    assert exc.value.reason == "campaign_already_exists"

    # hard call invalid targets
    bad_cid = new_campaign_id()
    other = absolute_relevance_task_id(
        campaign_id="goldcamp_other",
        case_id="draft_reviewable",
        candidate_chunk_id=CHUNK_A,
    )
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(authoring_run_id="authorrun_bad_hc"),
            selection_policy=_policy(),
            campaign_id=bad_cid,
            hard_call_designations=[
                HardCallDesignation(
                    designation_id=hard_call_designation_id(
                        campaign_id=bad_cid, target_task_id=other
                    ),
                    target_task_id=other,
                    reason_code="x",
                )
            ],
        )
    assert exc.value.reason == "hard_call_target_invalid"

    inert_target = absolute_relevance_task_id(
        campaign_id=bad_cid,
        case_id="draft_inert",
        candidate_chunk_id=CHUNK_A,
    )
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(authoring_run_id="authorrun_bad_inert"),
            selection_policy=_policy(),
            campaign_id=bad_cid,
            hard_call_designations=[
                HardCallDesignation(
                    designation_id=hard_call_designation_id(
                        campaign_id=bad_cid, target_task_id=inert_target
                    ),
                    target_task_id=inert_target,
                    reason_code="x",
                )
            ],
        )
    assert exc.value.reason == "hard_call_target_invalid"

    # mismatches
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(
                authoring_run_id="authorrun_cs",
                chunk_set_id="chunkset_other",
            ),
            selection_policy=_policy(),
        )
    assert exc.value.reason == "chunk_set_mismatch"
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(
                authoring_run_id="authorrun_ci",
                corpus_id="corpus_other",
            ),
            selection_policy=_policy(),
        )
    assert exc.value.reason == "corpus_id_mismatch"
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(
                authoring_run_id="authorrun_cn",
                corpus_name="othername",
            ),
            selection_policy=_policy(),
        )
    assert exc.value.reason == "corpus_name_mismatch"

    # unknown candidate
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(
                authoring_run_id="authorrun_uc",
                cases=[
                    SilverCase(
                        draft_case_id="d1",
                        proposed_query="q",
                        candidates=[PoolCandidate(chunk_id="chunk_missing")],
                    )
                ],
            ),
            selection_policy=_policy(),
        )
    assert exc.value.reason == "candidate_chunk_unresolved"

    # source seed document mismatch
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(
                authoring_run_id="authorrun_sd",
                cases=[
                    SilverCase(
                        draft_case_id="d1",
                        proposed_query="q",
                        source_seed=SourceSeed(
                            chunk_id=CHUNK_A, document_id="doc_wrong"
                        ),
                        candidates=[PoolCandidate(chunk_id=CHUNK_A)],
                    )
                ],
            ),
            selection_policy=_policy(),
        )
    assert exc.value.reason == "source_seed_document_mismatch"

    # zero-candidate preserved
    zero_cid = new_campaign_id()
    zc = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(authoring_run_id="authorrun_zero"),
        selection_policy=_policy(),
        campaign_id=zero_cid,
    )
    restored = GoldAuthoringRun.model_validate_json(
        (
            campaign_dir(settings, zc.campaign_id) / "baseline" / "authoring_run.json"
        ).read_text(encoding="utf-8")
    )
    assert any(c.draft_case_id == "draft_inert" and not c.candidates for c in restored.cases)

    # hard calls immutable after publication (file rewrite not API)
    hc_path = campaign_dir(settings, campaign.campaign_id) / "hard_calls.json"
    before = hc_path.read_text(encoding="utf-8")
    HardCallsArtifact.model_validate_json(before)
    # artifact content is the authority — no rewrite API exists
    assert "prelabel_disagreement" in before


def test_workspace_race_and_inactive(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="Race Desk")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Race",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    wstore = WorkspaceStore(settings)

    def bump() -> None:
        current = wstore.get(ws.workspace_id)
        wstore.save(current.model_copy(update={"revision": current.revision + 1}))

    cid = new_campaign_id()
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(authoring_run_id="authorrun_race_rev"),
            selection_policy=_policy(),
            campaign_id=cid,
            after_stage=bump,
        )
    assert exc.value.reason == "workspace_revision_changed"
    assert not campaign_dir(settings, cid).exists()

    def bump_snap() -> None:
        current = wstore.get(ws.workspace_id)
        wstore.save(
            current.model_copy(update={"current_snapshot_id": "snap_other_fake"})
        )

    # restore revision for next attempt
    current = wstore.get(ws.workspace_id)
    wstore.save(
        current.model_copy(
            update={"revision": ws.revision, "current_snapshot_id": snapshot_id}
        )
    )
    cid2 = new_campaign_id()
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(authoring_run_id="authorrun_race_snap"),
            selection_policy=_policy(),
            campaign_id=cid2,
            after_stage=bump_snap,
        )
    assert exc.value.reason == "workspace_snapshot_changed"
    assert not campaign_dir(settings, cid2).exists()

    # inactive workspace
    empty = wstore.create(new_empty_workspace(title="Empty Gold"))
    # force project pointing at empty workspace via direct file (workspace immutable
    # on project — create project against empty fails campaign)
    p2 = store.create_project(
        workspace_id=empty.workspace_id,
        title="EmptyP",
        project_type=GoldProjectType.BENCHMARK,
    )
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=p2.project_id,
            baseline=_baseline(authoring_run_id="authorrun_empty"),
            selection_policy=_policy(),
        )
    assert exc.value.reason == "workspace_not_active"

    # staged temp not authority
    staging = campaigns_root(settings) / f".goldcamp_fake.{'a'*32}.tmp"
    staging.mkdir(parents=True)
    (staging / "campaign.json").write_text("{}", encoding="utf-8")
    assert all(not c.campaign_id.startswith(".") for c in store.list_campaigns())


def test_selection_policy_project_type_mismatch(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="Type Desk")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Bench",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(),
            selection_policy=_policy(project_type=GoldProjectType.IMPROVEMENT),
        )
    assert exc.value.reason == "selection_policy_project_type_mismatch"


# --- K/L/M LEDGER ---


def _ready_campaign(tmp_path: Path):
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="Ledger Desk")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Ledger",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    campaign = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(),
        selection_policy=_policy(),
    )
    return settings, store, campaign, registry


def test_ledger_append_and_integrity(tmp_path: Path) -> None:
    settings, store, campaign, _registry = _ready_campaign(tmp_path)
    ledger = GoldLabLedger(settings, store=store)
    r1 = ledger.append(
        campaign.campaign_id,
        record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
        case_id="draft_reviewable",
        candidate_chunk_id=CHUNK_A,
        payload={"relevance": 2},
        idempotency_key="idem_1",
        request_fingerprint=_reqfp({"n": 1}),
        query_fingerprint=query_fingerprint("What is offline RAG?"),
    )
    assert r1.sequence == 1
    path1 = (
        campaign_dir(settings, campaign.campaign_id)
        / "ledger"
        / f"000000000001_{r1.record_id}.json"
    )
    assert path1.is_file()
    before = path1.read_text(encoding="utf-8")
    r2 = ledger.append(
        campaign.campaign_id,
        record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
        case_id="draft_reviewable",
        candidate_chunk_id=CHUNK_B,
        payload={"relevance": 0},
        idempotency_key="idem_2",
        request_fingerprint=_reqfp({"n": 2}),
        query_fingerprint=query_fingerprint("What is offline RAG?"),
    )
    assert r2.sequence == 2
    assert path1.read_text(encoding="utf-8") == before

    with pytest.raises((ValidationError, TypeError)):
        AbsoluteRelevancePayload.model_validate({"relevance": True})
    with pytest.raises(GoldLabError) as bool_exc:
        ledger.append(
            campaign.campaign_id,
            record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
            case_id="draft_reviewable",
            candidate_chunk_id=CHUNK_A,
            payload={"relevance": True},
            idempotency_key="idem_bool",
            request_fingerprint=_reqfp({"n": 3}),
        )
    assert bool_exc.value.reason == "ledger_record_invalid"

    with pytest.raises(GoldLabError) as exc:
        ledger.append(
            campaign.campaign_id,
            record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
            case_id="draft_reviewable",
            candidate_chunk_id=CHUNK_A,
            task_id=absolute_relevance_task_id(
                campaign_id=campaign.campaign_id,
                case_id="draft_reviewable",
                candidate_chunk_id=CHUNK_B,
            ),
            payload={"relevance": 1},
            idempotency_key="idem_task",
            request_fingerprint=_reqfp({"n": 4}),
        )
    assert exc.value.reason == "task_identity_mismatch"

    # closed / archived
    store.close_campaign(campaign.campaign_id)
    with pytest.raises(GoldLabError) as exc:
        ledger.append(
            campaign.campaign_id,
            record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
            case_id="draft_reviewable",
            candidate_chunk_id=CHUNK_A,
            payload={"relevance": 1},
            idempotency_key="idem_closed",
            request_fingerprint=_reqfp({"n": 5}),
        )
    assert exc.value.reason == "campaign_closed"

    # reopen by rewriting status for archive-project test on a new campaign
    settings2, store2, campaign2, _ = _ready_campaign(tmp_path / "p2")
    ledger2 = GoldLabLedger(settings2, store=store2)
    store2.archive_project(campaign2.project_id)
    with pytest.raises(GoldLabError) as exc:
        ledger2.append(
            campaign2.campaign_id,
            record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
            case_id="draft_reviewable",
            candidate_chunk_id=CHUNK_A,
            payload={"relevance": 1},
            idempotency_key="idem_arch",
            request_fingerprint=_reqfp({"n": 6}),
        )
    assert exc.value.reason == "project_archived"

    # integrity failures on first campaign ledger
    settings3, store3, campaign3, _ = _ready_campaign(tmp_path / "p3")
    ledger3 = GoldLabLedger(settings3, store=store3)
    ledger3.append(
        campaign3.campaign_id,
        record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
        case_id="draft_reviewable",
        candidate_chunk_id=CHUNK_A,
        payload={"relevance": 1},
        idempotency_key="idem_i1",
        request_fingerprint=_reqfp({"n": 7}),
    )
    root = campaign_dir(settings3, campaign3.campaign_id) / "ledger"
    # gap
    gap = root / "000000000003_goldrec_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json"
    gap.write_text(
        json.dumps(
            {
                "schema_version": LEDGER_SCHEMA,
                "sequence": 3,
                "record_id": "goldrec_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "record_type": "absolute_relevance",
                "judgment_id": "goldjud_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "task_id": absolute_relevance_task_id(
                    campaign_id=campaign3.campaign_id,
                    case_id="draft_reviewable",
                    candidate_chunk_id=CHUNK_A,
                ),
                "project_id": campaign3.project_id,
                "campaign_id": campaign3.campaign_id,
                "workspace_id": campaign3.workspace_id,
                "snapshot_id": campaign3.snapshot_id,
                "chunk_set_id": campaign3.chunk_set_id,
                "authoring_run_id": campaign3.baseline_authoring_run_id,
                "case_id": "draft_reviewable",
                "candidate_chunk_id": CHUNK_A,
                "semantic_contract": ABSOLUTE_RELEVANCE_CONTRACT,
                "selection_policy_id": campaign3.selection_policy.selection_policy_id,
                "selection_policy_fingerprint": (
                    campaign3.selection_policy.selection_policy_fingerprint
                ),
                "idempotency_key": "g",
                "request_fingerprint": _reqfp({"g": 1}),
                "created_at": datetime.now(tz=UTC).isoformat(),
                "payload": {"relevance": 1},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GoldLabError) as exc:
        ledger3.list_records(campaign3.campaign_id)
    assert exc.value.reason == "ledger_sequence_gap"
    gap.unlink()

    # malformed JSON
    bad = root / "000000000002_goldrec_cccccccccccccccccccccccccccccccc.json"
    bad.write_text("{not-json", encoding="utf-8")
    with pytest.raises(GoldLabError) as exc:
        ledger3.list_records(campaign3.campaign_id)
    assert exc.value.reason == "ledger_record_invalid"
    bad.unlink()

    # temp file ignored / not committed
    tmp = root / "000000000002_goldrec_dddddddddddddddddddddddddddddddd.json.tmp"
    tmp.write_text("{}", encoding="utf-8")
    assert len(ledger3.list_records(campaign3.campaign_id)) == 1
    tmp.unlink()

    # provenance mismatch
    bad_prov = root / "000000000002_goldrec_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee.json"
    bad_prov.write_text(
        json.dumps(
            {
                "schema_version": LEDGER_SCHEMA,
                "sequence": 2,
                "record_id": "goldrec_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                "record_type": "absolute_relevance",
                "judgment_id": "goldjud_ffffffffffffffffffffffffffffffff",
                "task_id": absolute_relevance_task_id(
                    campaign_id=campaign3.campaign_id,
                    case_id="draft_reviewable",
                    candidate_chunk_id=CHUNK_A,
                ),
                "project_id": campaign3.project_id,
                "campaign_id": campaign3.campaign_id,
                "workspace_id": campaign3.workspace_id,
                "snapshot_id": campaign3.snapshot_id,
                "chunk_set_id": campaign3.chunk_set_id,
                "authoring_run_id": campaign3.baseline_authoring_run_id,
                "case_id": "draft_reviewable",
                "candidate_chunk_id": CHUNK_A,
                "semantic_contract": ABSOLUTE_RELEVANCE_CONTRACT,
                "selection_policy_id": campaign3.selection_policy.selection_policy_id,
                "selection_policy_fingerprint": "cfg_" + ("0" * 64),
                "idempotency_key": "p",
                "request_fingerprint": _reqfp({"p": 1}),
                "created_at": datetime.now(tz=UTC).isoformat(),
                "payload": {"relevance": 1},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GoldLabError) as exc:
        ledger3.list_records(campaign3.campaign_id)
    assert exc.value.reason == "ledger_provenance_mismatch"
    bad_prov.unlink()

    # filename/sequence mismatch
    ok2 = ledger3.append(
        campaign3.campaign_id,
        record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
        case_id="draft_reviewable",
        candidate_chunk_id=CHUNK_B,
        payload={"relevance": 0},
        idempotency_key="idem_i2",
        request_fingerprint=_reqfp({"n": 8}),
    )
    p = root / f"000000000002_{ok2.record_id}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["sequence"] = 9
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(GoldLabError) as exc:
        ledger3.list_records(campaign3.campaign_id)
    assert exc.value.reason == "ledger_filename_sequence_mismatch"


def test_campaign_lease_excludes_concurrent_owner(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="Lock Desk")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Lock",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    campaign = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(),
        selection_policy=_policy(),
    )
    held = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with GoldLabCampaignLease(settings, campaign.campaign_id):
            held.set()
            release.wait(timeout=5)

    t = threading.Thread(target=holder)
    t.start()
    assert held.wait(timeout=5)
    with pytest.raises(GoldLabError) as exc:
        GoldLabCampaignLease(settings, campaign.campaign_id).acquire()
    assert exc.value.reason == "gold_lab_lease_held"
    # persistent lock filename alone is not busy after release
    release.set()
    t.join(timeout=5)
    lease = GoldLabCampaignLease(settings, campaign.campaign_id)
    lease.acquire()
    assert lease.path.exists()
    lease.release()
    lease2 = GoldLabCampaignLease(settings, campaign.campaign_id)
    lease2.acquire()
    lease2.release()


# --- N. NON-SCOPE ---


def test_nonscope_surfaces() -> None:
    api_root = REPO_ROOT / "src" / "offline_rag" / "api"
    for path in api_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "gold_lab" not in text
        assert "GoldLab" not in text
    ui = REPO_ROOT / "ui"
    if ui.exists():
        for path in ui.rglob("*"):
            if path.is_file() and path.suffix in {".tsx", ".ts", ".jsx", ".js"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                assert "GoldLab" not in text
    # scientific gold module untouched by import surface
    from offline_rag.evaluation import gold as gold_mod

    assert hasattr(gold_mod, "load_gold_dataset")


# --- Rework 1: strict IDs / path safety / commit races / ledger membership ---


def test_rework1_strict_id_grammar() -> None:
    with pytest.raises(GoldLabError) as exc:
        validate_project_id("goldproj_bad")
    assert exc.value.reason == "invalid_project_id"
    with pytest.raises(GoldLabError):
        validate_campaign_id("goldcamp_../x")
    with pytest.raises(GoldLabError):
        validate_record_id("goldrec_bad")
    with pytest.raises(GoldLabError):
        validate_judgment_id("goldjud_" + "g" * 32)
    with pytest.raises(GoldLabError):
        validate_task_id("goldtask_short")
    with pytest.raises(GoldLabError):
        validate_request_fingerprint("reqfp_short")
    with pytest.raises(GoldLabError):
        validate_selection_policy_fingerprint("cfg_short")
    # generated forms remain valid
    validate_project_id(new_project_id())
    validate_campaign_id(new_campaign_id())
    validate_record_id(new_ledger_record_id())
    validate_judgment_id(new_judgment_id())
    validate_task_id(
        absolute_relevance_task_id(
            campaign_id=new_campaign_id(),
            case_id="c1",
            candidate_chunk_id="chunk_a",
        )
    )


def test_rework1_path_safety_and_identity_consistency(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(GoldLabError):
        project_dir(settings, "goldproj_../../etc")
    with pytest.raises(GoldLabError):
        campaign_dir(settings, "goldcamp_not32hexcharsxxxxxxxxxxxx")

    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="Path Desk")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Path",
        project_type=GoldProjectType.BENCHMARK,
    )
    # corrupt stored project identity
    path = project_json_path(settings, project.project_id)
    path.write_text(
        project.model_copy(update={"project_id": new_project_id()}).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(GoldLabError) as exc:
        store.get_project(project.project_id)
    assert exc.value.reason == "project_identity_mismatch"

    path.write_text(project.model_dump_json(), encoding="utf-8")
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    campaign = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(authoring_run_id="authorrun_path"),
        selection_policy=_policy(),
    )
    cpath = campaign_json_path(settings, campaign.campaign_id)
    cpath.write_text(
        campaign.model_copy(update={"campaign_id": new_campaign_id()}).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(GoldLabError) as exc:
        store.get_campaign(campaign.campaign_id)
    assert exc.value.reason == "campaign_identity_mismatch"


def test_rework1_ledger_precommit_and_membership(tmp_path: Path) -> None:
    settings, store, campaign, _ = _ready_campaign(tmp_path)
    ledger = GoldLabLedger(settings, store=store)
    root = campaign_dir(settings, campaign.campaign_id) / "ledger"
    before = set(root.glob("*.json")) if root.exists() else set()

    with pytest.raises(GoldLabError) as exc:
        ledger.append(
            campaign.campaign_id,
            record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
            case_id="draft_reviewable",
            candidate_chunk_id=CHUNK_A,
            payload={"relevance": 1},
            idempotency_key="bad_rec",
            request_fingerprint=_reqfp({"bad": 1}),
            record_id="goldrec_bad",
        )
    assert exc.value.reason == "invalid_record_id"
    after = set(root.glob("*.json")) if root.exists() else set()
    assert after == before

    with pytest.raises(GoldLabError) as exc:
        ledger.append(
            campaign.campaign_id,
            record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
            case_id="draft_missing",
            candidate_chunk_id=CHUNK_A,
            payload={"relevance": 1},
            idempotency_key="miss_case",
            request_fingerprint=_reqfp({"miss": 1}),
        )
    assert exc.value.reason == "ledger_case_not_found"

    with pytest.raises(GoldLabError) as exc:
        ledger.append(
            campaign.campaign_id,
            record_type=GoldLedgerRecordType.QUESTION_CHECK,
            case_id="draft_inert",
            payload={"decision": "accept"},
            idempotency_key="inert_qc",
            request_fingerprint=_reqfp({"inert": 1}),
        )
    assert exc.value.reason == "ledger_case_not_reviewable"

    # CHUNK_B is in snapshot and in reviewable case — use a snapshot-valid id
    # that is absent from a case that only has CHUNK_A.
    settings2, store2, campaign2, registry = _ready_campaign(tmp_path / "mem")
    svc = GoldCampaignService(settings2, qdrant=registry.qdrant)
    # overwrite with a fresh campaign that has a single-candidate reviewable case
    # (reuse helper project via new campaign)
    project = store2.get_project(campaign2.project_id)
    single = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(
            authoring_run_id="authorrun_single",
            cases=[
                SilverCase(
                    draft_case_id="draft_single",
                    proposed_query="single candidate query",
                    source_seed=SourceSeed(chunk_id=CHUNK_A, document_id=DOC_ID),
                    candidates=[PoolCandidate(chunk_id=CHUNK_A, document_id=DOC_ID)],
                )
            ],
        ),
        selection_policy=_policy(),
    )
    ledger2 = GoldLabLedger(settings2, store=store2)
    with pytest.raises(GoldLabError) as exc:
        ledger2.append(
            single.campaign_id,
            record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
            case_id="draft_single",
            candidate_chunk_id=CHUNK_B,  # in chunk set, not in this case pool
            payload={"relevance": 1},
            idempotency_key="case_pool",
            request_fingerprint=_reqfp({"pool": 1}),
        )
    assert exc.value.reason == "ledger_candidate_not_in_case"

    with pytest.raises(GoldLabError) as exc:
        ledger2.append(
            single.campaign_id,
            record_type=GoldLedgerRecordType.AUXILIARY_PREFERENCE,
            case_id="draft_single",
            payload={"preferred_chunk_id": CHUNK_A, "other_chunk_id": CHUNK_B},
            idempotency_key="aux_pool",
            request_fingerprint=_reqfp({"aux": 1}),
        )
    assert exc.value.reason == "ledger_candidate_not_in_case"

    assert ledger2.list_records(single.campaign_id) == []


def test_rework1_baseline_authority_for_ledger(tmp_path: Path) -> None:
    settings, store, campaign, _ = _ready_campaign(tmp_path)
    ledger = GoldLabLedger(settings, store=store)
    baseline_path = (
        campaign_dir(settings, campaign.campaign_id) / "baseline" / "authoring_run.json"
    )
    original = baseline_path.read_bytes()

    baseline_path.unlink()
    with pytest.raises(GoldLabError) as exc:
        ledger.append(
            campaign.campaign_id,
            record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
            case_id="draft_reviewable",
            candidate_chunk_id=CHUNK_A,
            payload={"relevance": 1},
            idempotency_key="no_base",
            request_fingerprint=_reqfp({"nb": 1}),
        )
    assert exc.value.reason == "baseline_missing"
    baseline_path.write_bytes(original)

    baseline_path.write_text("{not-json", encoding="utf-8")
    # hash will mismatch first
    with pytest.raises(GoldLabError) as exc:
        ledger.append(
            campaign.campaign_id,
            record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
            case_id="draft_reviewable",
            candidate_chunk_id=CHUNK_A,
            payload={"relevance": 1},
            idempotency_key="bad_hash",
            request_fingerprint=_reqfp({"bh": 1}),
        )
    assert exc.value.reason == "baseline_hash_mismatch"

    # restore bytes but mutate authoring_run_id while keeping hash in campaign
    # (force hash match by rewriting campaign.json baseline_sha256)
    run = GoldAuthoringRun.model_validate_json(original.decode("utf-8"))
    mutated = run.model_copy(update={"authoring_run_id": "authorrun_mutated"})
    mutated_bytes = mutated.model_dump_json().encode("utf-8")
    baseline_path.write_bytes(mutated_bytes)
    cpath = campaign_json_path(settings, campaign.campaign_id)
    cpayload = json.loads(cpath.read_text(encoding="utf-8"))
    cpayload["baseline_sha256"] = hashlib.sha256(mutated_bytes).hexdigest()
    cpath.write_text(json.dumps(cpayload), encoding="utf-8")
    with pytest.raises(GoldLabError) as exc:
        ledger.append(
            campaign.campaign_id,
            record_type=GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
            case_id="draft_reviewable",
            candidate_chunk_id=CHUNK_A,
            payload={"relevance": 1},
            idempotency_key="bad_arid",
            request_fingerprint=_reqfp({"ba": 1}),
        )
    assert exc.value.reason == "baseline_authoring_run_id_mismatch"


def test_rework1_workspace_commit_boundary_lease(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="Commit Desk")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Commit",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)
    wstore = WorkspaceStore(settings)
    held = threading.Event()
    release = threading.Event()
    mutation_error: list[BaseException] = []

    def mutate_under_contention() -> None:
        assert held.wait(timeout=5)
        try:
            current = wstore.get(ws.workspace_id)
            wstore.save(current.model_copy(update={"revision": current.revision + 1}))
        except BaseException as exc:  # noqa: BLE001 - capture for assertion
            mutation_error.append(exc)
        finally:
            release.set()

    def hold_point() -> None:
        held.set()
        assert release.wait(timeout=5)

    t = threading.Thread(target=mutate_under_contention)
    t.start()
    campaign = svc.create_campaign(
        project_id=project.project_id,
        baseline=_baseline(authoring_run_id="authorrun_lease_ws"),
        selection_policy=_policy(),
        before_commit=hold_point,
    )
    t.join(timeout=5)
    assert campaign_dir(settings, campaign.campaign_id).is_dir()
    assert mutation_error
    assert isinstance(mutation_error[0], AppError)
    assert mutation_error[0].code is ErrorCode.WORKSPACE_CONFLICT
    # workspace unchanged through the validation→rename window
    assert wstore.get(ws.workspace_id).revision == ws.revision


def test_rework1_project_archive_commit_race(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry, snapshot_id, _ = _publish_bound(settings)
    ws = _active_workspace(settings, snapshot_id, title="Archive Desk")
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=ws.workspace_id,
        title="Archive",
        project_type=GoldProjectType.BENCHMARK,
    )
    svc = GoldCampaignService(settings, qdrant=registry.qdrant)

    # archive commits first (after_stage) -> campaign fails
    cid = new_campaign_id()
    with pytest.raises(GoldLabError) as exc:
        svc.create_campaign(
            project_id=project.project_id,
            baseline=_baseline(authoring_run_id="authorrun_arch_first"),
            selection_policy=_policy(),
            campaign_id=cid,
            after_stage=lambda: store.archive_project(project.project_id),
        )
    assert exc.value.reason == "project_archived"
    assert not campaign_dir(settings, cid).exists()

    # new active project for lease-owner race
    project2 = store.create_project(
        workspace_id=ws.workspace_id,
        title="Archive2",
        project_type=GoldProjectType.BENCHMARK,
    )
    held = threading.Event()
    release = threading.Event()
    archive_error: list[BaseException] = []

    def archive_under_contention() -> None:
        assert held.wait(timeout=5)
        try:
            store.archive_project(project2.project_id)
        except BaseException as exc:  # noqa: BLE001
            archive_error.append(exc)
        finally:
            release.set()

    def hold_point() -> None:
        held.set()
        assert release.wait(timeout=5)

    t = threading.Thread(target=archive_under_contention)
    t.start()
    campaign = svc.create_campaign(
        project_id=project2.project_id,
        baseline=_baseline(authoring_run_id="authorrun_arch_lease"),
        selection_policy=_policy(),
        before_commit=hold_point,
    )
    t.join(timeout=5)
    assert campaign_dir(settings, campaign.campaign_id).is_dir()
    assert archive_error
    assert isinstance(archive_error[0], GoldLabError)
    assert archive_error[0].reason == "gold_lab_lease_held"
    assert store.get_project(project2.project_id).status is GoldProjectStatus.ACTIVE
