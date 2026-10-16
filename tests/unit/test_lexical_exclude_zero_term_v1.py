"""Regression: exclude-zero-term-v1 lexical searchable-universe policy."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

# Break dense↔app circular import before dense/lexical package inits.
from offline_rag.app.errors import AppError  # noqa: F401
from offline_rag.app.workspace.models import (
    ManagedOperationKind,
    ManagedOperationLexicalFacts,
    ManagedOperationMetrics,
    ManagedOperationStatus,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.chunking.pipeline import run_chunking
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import LEXICAL_EXCLUDE_ZERO_TERM_V1, lexical_index_id
from offline_rag.domain.indexing import IndexingStatus, LexicalIndexingReport
from offline_rag.ingestion.pipeline import run_ingestion
from offline_rag.lexical.analyzer import TechnicalLexicalAnalyzer
from offline_rag.lexical.backend import LocalInvertedIndexBackend
from offline_rag.lexical.config_hash import (
    build_legacy_lexical_config_hash_without_searchable_units,
    build_lexical_config_hash,
)
from offline_rag.lexical.persistence import (
    lexical_index_state_path,
    load_lexical_index_manifest,
    load_lexical_index_state,
)
from offline_rag.lexical.pipeline import run_lexical_indexing
from offline_rag.lexical.searchable_units import analyze_and_classify
from offline_rag.lexical.text import PlainLexicalTextBuilder
from offline_rag.retrieval.ranking_text import RankingTextInputs


def _settings(tmp_path: Path) -> AppSettings:
    settings = AppSettings()
    return settings.model_copy(
        update={
            "project": settings.project.model_copy(update={"strict_offline": False}),
            "paths": settings.paths.model_copy(
                update={
                    "raw_data": tmp_path / "raw",
                    "manifests": tmp_path / "manifests",
                    "processed": tmp_path / "processed",
                    "corpora": tmp_path / "corpora",
                    "chunks": tmp_path / "chunks",
                    "chunk_manifests": tmp_path / "chunk-manifests",
                    "embeddings": tmp_path / "embeddings",
                    "index_manifests": tmp_path / "index-manifests",
                    "lexical_indexes": tmp_path / "lexical-indexes",
                    "lexical_index_manifests": tmp_path / "lexical-index-manifests",
                    "qdrant_storage": tmp_path / "qdrant",
                    "retrieval_models": tmp_path / "models",
                    "docling_artifacts": tmp_path / "models" / "docling",
                    "tokenizer_artifacts": tmp_path / "models" / "tokenizers" / "tiktoken",
                    "embedding_artifacts": tmp_path / "models" / "embeddings",
                    "eval_results": tmp_path / "eval" / "results",
                }
            ),
            "chunking": settings.chunking.model_copy(
                update={
                    "tokenizer": settings.chunking.tokenizer.model_copy(
                        update={"implementation": "fake"}
                    )
                }
            ),
        }
    )


def _prepare_corpus(
    settings: AppSettings, docs: dict[str, str], *, corpus_name: str = "default"
) -> None:
    raw = settings.paths.raw_data
    raw.mkdir(parents=True, exist_ok=True)
    for name, text in docs.items():
        (raw / name).write_text(text, encoding="utf-8")
    for path in (
        settings.paths.manifests,
        settings.paths.processed,
        settings.paths.corpora,
        settings.paths.chunks,
        settings.paths.chunk_manifests,
        settings.paths.lexical_indexes,
        settings.paths.lexical_index_manifests,
        settings.paths.eval_results,
        settings.paths.tokenizer_artifacts,
    ):
        path.mkdir(parents=True, exist_ok=True)
    ingest = run_ingestion(
        settings=settings,
        inputs=[raw],
        corpus_name=corpus_name,
        recursive=False,
        root=raw,
    )
    assert ingest.status.value in {"success", "no_op"}
    chunk = run_chunking(
        settings=settings,
        corpus_name=corpus_name,
        token_counter=FakeTokenCounter(),
    )
    assert chunk.status.value in {"success", "no_op"}


def _assert_five_facts(obj: Any) -> None:
    assert obj.searchable_units_contract == LEXICAL_EXCLUDE_ZERO_TERM_V1
    assert obj.chunk_set_child_count is not None
    assert obj.zero_term_excluded_count is not None
    assert obj.eligible_child_count is not None
    assert obj.indexed_child_count is not None
    assert (
        obj.chunk_set_child_count
        == obj.zero_term_excluded_count + obj.eligible_child_count
    )
    assert obj.eligible_child_count == obj.indexed_child_count


def test_exclude_zero_term_participates_in_lexical_identity(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    new_hash = build_lexical_config_hash(settings)
    legacy_hash = build_legacy_lexical_config_hash_without_searchable_units(settings)
    assert new_hash != legacy_hash
    assert LEXICAL_EXCLUDE_ZERO_TERM_V1 == "exclude-zero-term-v1"
    chunk_set_id = "chunkset_identity_probe"
    new_id = lexical_index_id(
        chunk_set_id, new_hash, backend_contract=settings.lexical.backend_contract
    )
    legacy_id = lexical_index_id(
        chunk_set_id, legacy_hash, backend_contract=settings.lexical.backend_contract
    )
    assert new_id != legacy_id


def test_mixed_corpus_excludes_zero_term_indexes_eligible(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _prepare_corpus(
        settings,
        {
            "good.txt": "Nozzle foam application uses API-12 pressure control.\n",
            "punct.txt": "!!! ??? ...\n",
        },
    )
    report = run_lexical_indexing(settings=settings, corpus_name="default")
    assert report.status == IndexingStatus.SUCCESS
    _assert_five_facts(report)
    assert report.zero_term_excluded_count >= 1
    assert report.eligible_child_count >= 1
    assert report.chunk_set_child_count == report.zero_term_excluded_count + report.eligible_child_count
    assert report.eligible_child_count == report.indexed_child_count

    analyzer = TechnicalLexicalAnalyzer()
    builder = PlainLexicalTextBuilder()
    from offline_rag.chunking.persistence import (
        chunk_artifact_path,
        chunk_state_path,
        load_chunk_artifact,
        load_chunk_set_manifest,
        load_chunk_state,
    )
    from offline_rag.domain.documents import ChunkKind

    chunk_state = load_chunk_state(chunk_state_path(settings.paths.corpora, "default"))
    manifest_path = settings.paths.chunk_manifests / Path(chunk_state.current_chunk_manifest).name
    chunk_set = load_chunk_set_manifest(manifest_path)
    excluded: list[str] = []
    eligible: list[str] = []
    text_by_id: dict[str, str] = {}
    for entry in chunk_set.documents:
        artifact = load_chunk_artifact(
            chunk_artifact_path(settings.paths.chunks, entry.chunk_artifact_id)
        )
        for child in artifact.children:
            if child.kind != ChunkKind.CHILD:
                continue
            text = builder.build(
                RankingTextInputs(
                    document_title=None,
                    section_path=tuple(child.section_path or ()),
                    chunk_text=child.text,
                )
            )
            text_by_id[child.chunk_id] = text
            terms = analyzer.analyze(text)
            if not terms:
                excluded.append(child.chunk_id)
            else:
                eligible.append(child.chunk_id)

    assert len(excluded) == report.zero_term_excluded_count
    assert len(eligible) == report.eligible_child_count
    for cid in excluded:
        assert analyzer.analyze(text_by_id[cid]) == []
    for cid in eligible:
        assert analyzer.analyze(text_by_id[cid]) != []

    assert report.lexical_index_id is not None
    backend = LocalInvertedIndexBackend(settings.paths.lexical_indexes)
    backend.open(report.lexical_index_id)
    try:
        assert set(backend.indexed_chunk_ids()) == set(eligible)
    finally:
        backend.close()

    manifest = load_lexical_index_manifest(
        settings.paths.lexical_index_manifests / f"{report.lexical_index_id}.json"
    )
    _assert_five_facts(manifest)


def test_all_zero_term_corpus_fails_closed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _prepare_corpus(settings, {"punct.txt": "!!! ??? ...\n"})
    report = run_lexical_indexing(settings=settings, corpus_name="default")
    assert report.status == IndexingStatus.FAILED
    assert any("refusing empty lexical index" in err for err in report.errors)
    state_path = lexical_index_state_path(settings.paths.corpora, "default")
    assert not state_path.exists()
    assert list(settings.paths.lexical_index_manifests.glob("*.json")) == []
    assert list(settings.paths.lexical_indexes.iterdir()) == [] or not any(
        settings.paths.lexical_indexes.iterdir()
    )


def test_ordinary_fixtures_have_zero_false_exclusions(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _prepare_corpus(
        settings,
        {
            "alpha.txt": "Alpha well uses API-12 for maximum operating pressure control.\n",
            "beta.txt": "Beta system documents C++ tooling and .NET runtime notes.\n",
        },
    )
    report = run_lexical_indexing(settings=settings, corpus_name="default")
    assert report.status == IndexingStatus.SUCCESS
    _assert_five_facts(report)
    assert report.zero_term_excluded_count == 0
    assert report.eligible_child_count == report.chunk_set_child_count
    assert report.eligible_child_count == report.indexed_child_count


def test_pre_policy_index_not_reused_as_new_policy(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _prepare_corpus(
        settings,
        {"doc.txt": "Firefighting nozzle foam uses API-12 pressure guidelines.\n"},
    )
    # Seed a legacy-identity pointer that must not satisfy new-policy reuse.
    from offline_rag.chunking.persistence import chunk_state_path, load_chunk_state
    from offline_rag.ingestion.persistence import corpus_state_path, load_corpus_state
    from offline_rag.lexical.persistence import (
        lexical_index_manifest_relpath,
        write_lexical_index_manifest,
        write_lexical_index_state,
    )
    from offline_rag.domain.indexing import LexicalIndexManifest, LexicalIndexState

    corpus_state = load_corpus_state(corpus_state_path(settings.paths.corpora, "default"))
    chunk_state = load_chunk_state(chunk_state_path(settings.paths.corpora, "default"))
    legacy_hash = build_legacy_lexical_config_hash_without_searchable_units(settings)
    legacy_id = lexical_index_id(
        chunk_state.current_chunk_set_id,
        legacy_hash,
        backend_contract=settings.lexical.backend_contract,
    )
    now = datetime.now(tz=UTC)
    legacy_manifest = LexicalIndexManifest(
        lexical_index_id=legacy_id,
        corpus_id=corpus_state.current_corpus_id,
        chunk_set_id=chunk_state.current_chunk_set_id,
        lexical_config_hash=legacy_hash,
        text_strategy=settings.lexical.text.strategy,
        text_contract=settings.lexical.text.contract_version,
        analyzer_strategy=settings.lexical.analyzer.strategy,
        analyzer_contract=settings.lexical.analyzer.contract_version,
        bm25_contract=settings.lexical.bm25.contract_version,
        bm25_k1=settings.lexical.bm25.k1,
        bm25_b=settings.lexical.bm25.b,
        bm25_idf=settings.lexical.bm25.idf,
        bm25_query_tf=settings.lexical.bm25.query_tf,
        backend=settings.lexical.backend,
        backend_contract=settings.lexical.backend_contract,
        expected_child_count=1,
        indexed_child_count=1,
        document_count=1,
        vocabulary_size=1,
        avgdl=1.0,
        physical_index_relpath=f"lexical-indexes/{legacy_id}",
        created_at=now,
    )
    write_lexical_index_manifest(settings.paths.lexical_index_manifests, legacy_manifest)
    write_lexical_index_state(
        lexical_index_state_path(settings.paths.corpora, "default"),
        LexicalIndexState(
            corpus_name="default",
            source_corpus_id=corpus_state.current_corpus_id,
            source_chunk_set_id=chunk_state.current_chunk_set_id,
            current_lexical_index_id=legacy_id,
            current_lexical_index_manifest=lexical_index_manifest_relpath(legacy_id),
            lexical_config_hash=legacy_hash,
            created_at=now,
            updated_at=now,
        ),
    )

    report = run_lexical_indexing(settings=settings, corpus_name="default")
    assert report.status == IndexingStatus.SUCCESS
    assert report.lexical_index_id != legacy_id
    assert report.lexical_config_hash == build_lexical_config_hash(settings)
    assert report.lexical_config_hash != legacy_hash
    _assert_five_facts(report)
    state = load_lexical_index_state(lexical_index_state_path(settings.paths.corpora, "default"))
    assert state.current_lexical_index_id == report.lexical_index_id
    assert state.lexical_config_hash == report.lexical_config_hash


def test_noop_preserves_five_lexical_facts(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _prepare_corpus(
        settings,
        {
            "good.txt": "Nozzle foam application uses API-12 pressure control.\n",
            "punct.txt": "!!! ???\n",
        },
    )
    first = run_lexical_indexing(settings=settings, corpus_name="default")
    assert first.status == IndexingStatus.SUCCESS
    _assert_five_facts(first)
    second = run_lexical_indexing(settings=settings, corpus_name="default")
    assert second.status == IndexingStatus.NO_OP
    _assert_five_facts(second)
    assert second.searchable_units_contract == first.searchable_units_contract
    assert second.chunk_set_child_count == first.chunk_set_child_count
    assert second.zero_term_excluded_count == first.zero_term_excluded_count
    assert second.eligible_child_count == first.eligible_child_count
    assert second.indexed_child_count == first.indexed_child_count
    assert second.lexical_index_id == first.lexical_index_id


def test_empty_universe_failure_leaves_prior_state_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    _prepare_corpus(
        settings,
        {"doc.txt": "Firefighting nozzle foam uses API-12 pressure guidelines.\n"},
    )
    first = run_lexical_indexing(settings=settings, corpus_name="default")
    assert first.status == IndexingStatus.SUCCESS
    state_before = load_lexical_index_state(
        lexical_index_state_path(settings.paths.corpora, "default")
    ).model_dump_json()
    manifest_before = (
        settings.paths.lexical_index_manifests / f"{first.lexical_index_id}.json"
    ).read_text(encoding="utf-8")

    # Force rebuild path (invalidate universe accounting) while excluding all children.
    from offline_rag.domain.indexing import LexicalIndexManifest

    manifest = LexicalIndexManifest.model_validate_json(manifest_before)
    stripped = manifest.model_copy(
        update={
            "searchable_units_contract": None,
            "chunk_set_child_count": None,
            "zero_term_excluded_count": None,
            "eligible_child_count": None,
        }
    )
    path = settings.paths.lexical_index_manifests / f"{first.lexical_index_id}.json"
    path.write_text(stripped.model_dump_json(), encoding="utf-8")

    def _exclude_all(analyzer: Any, lexical_text: str) -> tuple[list[str], str]:
        return [], "excluded"

    monkeypatch.setattr(
        "offline_rag.lexical.pipeline.analyze_and_classify",
        _exclude_all,
    )
    failed = run_lexical_indexing(settings=settings, corpus_name="default")
    assert failed.status == IndexingStatus.FAILED
    assert any("refusing empty lexical index" in err for err in failed.errors)

    state_after = load_lexical_index_state(
        lexical_index_state_path(settings.paths.corpora, "default")
    ).model_dump_json()
    assert state_after == state_before
    # Prior published physical index remains valid under the original index id.
    backend = LocalInvertedIndexBackend(settings.paths.lexical_indexes)
    assert backend.index_exists(first.lexical_index_id)
    assert backend.validate(first.lexical_index_id)


def test_technical_v1_representative_outputs_unchanged() -> None:
    analyzer = TechnicalLexicalAnalyzer()
    cases = {
        "API-12 maximum pressure": ["api-12", "maximum", "pressure"],
        "Firmware v1.2": ["firmware", "v1.2"],
        "part_no AB-104": ["part_no", "ab-104"],
        "C++ parser": ["c++", "parser"],
        "C# client": ["c#", "client"],
        ".NET runtime": [".net", "runtime"],
        "HPHT MDT C5-C6": ["hpht", "mdt", "c5-c6"],
        "Qwen3-Embedding-0.6B": ["qwen3-embedding-0.6b"],
        "api/v1 parent_chunk_id": ["api/v1", "parent_chunk_id"],
        "!!! ???": [],
    }
    for text, expected in cases.items():
        assert analyzer.analyze(text) == expected, text
        terms, classification = analyze_and_classify(analyzer, text)
        assert terms == expected
        assert classification == ("excluded" if not expected else "eligible")


def test_managed_operation_metrics_lexical_projection_and_legacy_null(
    tmp_path: Path,
) -> None:
    from offline_rag.app.observability_publish import DurableObservabilityPublisher

    # Historical records remain valid with lexical=None.
    legacy = ManagedOperationMetrics.model_validate(
        {"requested_document_count": 1, "lexical": None}
    )
    assert legacy.lexical is None
    bare = ManagedOperationMetrics()
    assert bare.lexical is None

    settings = _settings(tmp_path)
    store = ManagedOperationStore(settings)
    wid = "ws_lex_facts"
    op = store.begin(
        workspace_id=wid,
        idempotency_key="lex-facts",
        kind=ManagedOperationKind.SOURCE_ADD,
        request_payload={"files": []},
        expected_revision=1,
    )
    store.update_status(wid, op.operation_id, ManagedOperationStatus.RUNNING)
    pub = DurableObservabilityPublisher(
        operations=store, workspace_id=wid, operation_id=op.operation_id
    )
    pub.freeze_admission(
        documents=[],
        requested_document_count=0,
        uploaded_raw_bytes=0,
        pre_active_source_count=0,
        post_active_source_count=0,
    )
    now = datetime.now(tz=UTC)
    report = LexicalIndexingReport(
        run_id="lexindex_test",
        corpus_name="default",
        status=IndexingStatus.SUCCESS,
        started_at=now,
        completed_at=now,
        duration_ms=12,
        searchable_units_contract=LEXICAL_EXCLUDE_ZERO_TERM_V1,
        chunk_set_child_count=10,
        zero_term_excluded_count=3,
        eligible_child_count=7,
        indexed_child_count=7,
    )
    pub._apply_lexical_report(report)
    pub._persist()
    recorded = store.get(wid, op.operation_id)
    assert recorded.metrics is not None
    assert recorded.metrics.lexical is not None
    facts = recorded.metrics.lexical
    assert isinstance(facts, ManagedOperationLexicalFacts)
    _assert_five_facts(facts)
    assert facts.chunk_set_child_count == 10
    assert facts.zero_term_excluded_count == 3
    assert facts.eligible_child_count == 7
    assert facts.indexed_child_count == 7
