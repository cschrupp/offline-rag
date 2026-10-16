"""Lexical indexing pipeline over an active ChunkSet."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from offline_rag.chunking.persistence import (
    chunk_artifact_path,
    chunk_state_path,
    load_chunk_artifact,
    load_chunk_set_manifest,
    load_chunk_state,
)
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    LEXICAL_EXCLUDE_ZERO_TERM_V1,
    lexical_index_id,
    new_execution_id,
)
from offline_rag.core.progress import ProgressReporter, report_progress
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import (
    IndexingStatus,
    LexicalIndexingReport,
    LexicalIndexManifest,
    LexicalIndexState,
)
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.ingestion.persistence import (
    corpus_state_path,
    load_corpus_manifest,
    load_corpus_state,
)
from offline_rag.lexical.analyzer import TechnicalLexicalAnalyzer
from offline_rag.lexical.backend import (
    LexicalDocumentInput,
    LexicalIndexBackend,
    LocalInvertedIndexBackend,
)
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.persistence import (
    lexical_index_manifest_relpath,
    lexical_index_state_path,
    try_load_lexical_index_manifest,
    try_load_lexical_index_state,
    write_lexical_index_manifest,
    write_lexical_index_state,
)
from offline_rag.lexical.searchable_units import analyze_and_classify
from offline_rag.lexical.text import (
    LexicalTextBuilder,
    PlainLexicalTextBuilder,
    TitleSectionLexicalTextBuilder,
)
from offline_rag.retrieval.ranking_text import (
    RankingTextError,
    ranking_inputs_for_chunk,
    resolve_document_titles_from_source_names,
)


class LexicalIndexingError(RuntimeError):
    pass


def _universe_reconciles(
    *,
    chunk_set_child_count: int,
    zero_term_excluded_count: int,
    eligible_child_count: int,
    indexed_child_count: int | None = None,
) -> bool:
    if chunk_set_child_count != zero_term_excluded_count + eligible_child_count:
        return False
    if indexed_child_count is not None and eligible_child_count != indexed_child_count:
        return False
    return True


def _manifest_has_exclude_zero_term_universe(manifest: LexicalIndexManifest) -> bool:
    if manifest.searchable_units_contract != LEXICAL_EXCLUDE_ZERO_TERM_V1:
        return False
    if (
        manifest.chunk_set_child_count is None
        or manifest.zero_term_excluded_count is None
        or manifest.eligible_child_count is None
    ):
        return False
    return _universe_reconciles(
        chunk_set_child_count=manifest.chunk_set_child_count,
        zero_term_excluded_count=manifest.zero_term_excluded_count,
        eligible_child_count=manifest.eligible_child_count,
        indexed_child_count=manifest.indexed_child_count,
    )


def _report_universe_kwargs(manifest: LexicalIndexManifest) -> dict:
    return {
        "searchable_units_contract": manifest.searchable_units_contract,
        "chunk_set_child_count": manifest.chunk_set_child_count,
        "zero_term_excluded_count": manifest.zero_term_excluded_count,
        "eligible_child_count": manifest.eligible_child_count,
        "indexed_child_count": manifest.indexed_child_count,
        "children_total": manifest.chunk_set_child_count
        if manifest.chunk_set_child_count is not None
        else manifest.indexed_child_count,
    }


def make_lexical_text_builder(settings: AppSettings) -> LexicalTextBuilder:
    strategy = settings.lexical.text.strategy
    contract = settings.lexical.text.contract_version
    if strategy == "plain" and contract == PlainLexicalTextBuilder.contract_version:
        return PlainLexicalTextBuilder()
    if (
        strategy == TitleSectionLexicalTextBuilder.strategy
        and contract == TitleSectionLexicalTextBuilder.contract_version
    ):
        return TitleSectionLexicalTextBuilder()
    raise LexicalIndexingError(
        f"unsupported lexical text strategy/contract: {strategy}/{contract}"
    )


def _requires_document_titles(builder: LexicalTextBuilder) -> bool:
    return (
        builder.strategy == TitleSectionLexicalTextBuilder.strategy
        and builder.contract_version == TitleSectionLexicalTextBuilder.contract_version
    )


def make_lexical_analyzer(settings: AppSettings) -> TechnicalLexicalAnalyzer:
    analyzer_settings = settings.lexical.analyzer
    if (
        analyzer_settings.strategy == "technical"
        and analyzer_settings.contract_version == TechnicalLexicalAnalyzer.contract_version
        and analyzer_settings.unicode_normalization == "NFKC"
        and analyzer_settings.case_normalization == "casefold"
        and analyzer_settings.stopwords == "none"
        and analyzer_settings.stemming == "none"
        and analyzer_settings.lemmatization == "none"
    ):
        return TechnicalLexicalAnalyzer()
    raise LexicalIndexingError(
        "unsupported lexical analyzer settings; expected technical-v1 "
        "(NFKC/casefold/no stopwords/stemming/lemmatization)"
    )


def _child_jobs_from_chunk_set(
    *,
    settings: AppSettings,
    chunk_set_id: str,
    chunk_manifest_name: str,
) -> tuple[list[tuple[Chunk, str]], int]:
    """Return (child, chunk_artifact_id) pairs and unique document count."""
    manifest_path = settings.paths.chunk_manifests / Path(chunk_manifest_name).name
    if not manifest_path.exists():
        raise LexicalIndexingError(f"missing chunk-set manifest: {chunk_manifest_name}")
    chunk_set = load_chunk_set_manifest(manifest_path)
    if chunk_set.chunk_set_id != chunk_set_id:
        raise LexicalIndexingError("chunk state/manifest ID mismatch")

    jobs: list[tuple[Chunk, str]] = []
    documents: set[str] = set()
    for entry in sorted(chunk_set.documents, key=lambda item: item.document_id):
        artifact_path = chunk_artifact_path(settings.paths.chunks, entry.chunk_artifact_id)
        if not artifact_path.exists():
            raise LexicalIndexingError(f"missing chunk artifact: {entry.chunk_artifact_id}")
        artifact = load_chunk_artifact(artifact_path)
        if artifact.chunk_artifact_id != entry.chunk_artifact_id:
            raise LexicalIndexingError("chunk artifact ID mismatch")
        if artifact.document_id != entry.document_id:
            raise LexicalIndexingError("chunk artifact document_id mismatch")
        documents.add(artifact.document_id)
        for chunk in artifact.children:
            if chunk.kind != ChunkKind.CHILD:
                continue
            jobs.append((chunk, artifact.chunk_artifact_id))

    jobs.sort(key=lambda item: item[0].chunk_id)
    if len(jobs) != chunk_set.total_child_count:
        raise LexicalIndexingError(
            f"child count mismatch: loaded {len(jobs)} vs manifest {chunk_set.total_child_count}"
        )
    return jobs, len(documents)


def _publish_lexical_index_state(
    *,
    settings: AppSettings,
    corpus_name: str,
    corpus_id: str,
    chunk_set_id: str,
    index_id: str,
    lex_cfg_hash: str,
    completed: datetime,
) -> LexicalIndexState:
    relative_manifest = lexical_index_manifest_relpath(index_id)
    new_state = LexicalIndexState(
        corpus_name=corpus_name,
        source_corpus_id=corpus_id,
        source_chunk_set_id=chunk_set_id,
        current_lexical_index_id=index_id,
        current_lexical_index_manifest=relative_manifest,
        lexical_config_hash=lex_cfg_hash,
        created_at=completed,
        updated_at=completed,
    )
    state_path = lexical_index_state_path(settings.paths.corpora, corpus_name)
    existing = try_load_lexical_index_state(state_path)
    if existing is not None and existing.created_at:
        new_state = new_state.model_copy(update={"created_at": existing.created_at})
    write_lexical_index_state(state_path, new_state)
    return new_state


def run_lexical_indexing(
    *,
    settings: AppSettings,
    corpus_name: str = "default",
    backend: LexicalIndexBackend | None = None,
    on_progress: ProgressReporter | None = None,
) -> LexicalIndexingReport:
    started = datetime.now(tz=UTC)
    run_id = new_execution_id(prefix="lexindex")
    name = validate_corpus_name(corpus_name)
    owned_backend = backend is None
    backend_impl: LexicalIndexBackend | None = None

    try:
        corpus_path = corpus_state_path(settings.paths.corpora, name)
        if not corpus_path.exists():
            completed = datetime.now(tz=UTC)
            return LexicalIndexingReport(
                run_id=run_id,
                corpus_name=name,
                status=IndexingStatus.FAILED,
                started_at=started,
                completed_at=completed,
                duration_ms=int((completed - started).total_seconds() * 1000),
                errors=[f"corpus '{name}' is not initialized; run offline-rag ingest first"],
            )

        corpus_state = load_corpus_state(corpus_path)
        if corpus_state.corpus_name != name:
            raise LexicalIndexingError("corpus state name mismatch")

        chunk_path = chunk_state_path(settings.paths.corpora, name)
        if not chunk_path.exists():
            completed = datetime.now(tz=UTC)
            return LexicalIndexingReport(
                run_id=run_id,
                corpus_name=name,
                corpus_id=corpus_state.current_corpus_id,
                status=IndexingStatus.FAILED,
                started_at=started,
                completed_at=completed,
                duration_ms=int((completed - started).total_seconds() * 1000),
                errors=[f"corpus '{name}' has no chunk state; run offline-rag chunk first"],
            )

        chunk_state = load_chunk_state(chunk_path)
        if chunk_state.source_corpus_id != corpus_state.current_corpus_id:
            completed = datetime.now(tz=UTC)
            return LexicalIndexingReport(
                run_id=run_id,
                corpus_name=name,
                corpus_id=corpus_state.current_corpus_id,
                chunk_set_id=chunk_state.current_chunk_set_id,
                status=IndexingStatus.FAILED,
                started_at=started,
                completed_at=completed,
                duration_ms=int((completed - started).total_seconds() * 1000),
                errors=[
                    (
                        "ChunkState is stale relative to CorpusState; "
                        "re-run offline-rag chunk before lexical indexing"
                    )
                ],
            )

        lex_cfg_hash = build_lexical_config_hash(settings)
        index_id = lexical_index_id(
            chunk_state.current_chunk_set_id,
            lex_cfg_hash,
            backend_contract=settings.lexical.backend_contract,
        )

        jobs, documents_total = _child_jobs_from_chunk_set(
            settings=settings,
            chunk_set_id=chunk_state.current_chunk_set_id,
            chunk_manifest_name=chunk_state.current_chunk_manifest,
        )
        chunk_set_child_count = len(jobs)

        backend_impl = backend or LocalInvertedIndexBackend(settings.paths.lexical_indexes)
        settings.paths.lexical_index_manifests.mkdir(parents=True, exist_ok=True)
        settings.paths.lexical_indexes.mkdir(parents=True, exist_ok=True)

        existing_state = try_load_lexical_index_state(
            lexical_index_state_path(settings.paths.corpora, name)
        )
        existing_manifest = try_load_lexical_index_manifest(
            settings.paths.lexical_index_manifests,
            index_id,
        )
        physical_ok = backend_impl.index_exists(index_id) and backend_impl.validate(index_id)
        universe_ok = (
            existing_manifest is not None
            and _manifest_has_exclude_zero_term_universe(existing_manifest)
            and existing_manifest.chunk_set_child_count == chunk_set_child_count
        )
        published_complete = (
            existing_manifest is not None
            and existing_manifest.lexical_index_id == index_id
            and existing_manifest.corpus_id == corpus_state.current_corpus_id
            and existing_manifest.chunk_set_id == chunk_state.current_chunk_set_id
            and existing_manifest.lexical_config_hash == lex_cfg_hash
            and universe_ok
            and physical_ok
        )

        if (
            existing_state is not None
            and existing_state.current_lexical_index_id == index_id
            and existing_state.source_corpus_id == corpus_state.current_corpus_id
            and existing_state.source_chunk_set_id == chunk_state.current_chunk_set_id
            and existing_state.lexical_config_hash == lex_cfg_hash
            and existing_manifest is not None
            and existing_manifest.lexical_config_hash == lex_cfg_hash
            and existing_manifest.chunk_set_id == chunk_state.current_chunk_set_id
            and universe_ok
            and physical_ok
        ):
            completed = datetime.now(tz=UTC)
            return LexicalIndexingReport(
                run_id=run_id,
                corpus_name=name,
                corpus_id=corpus_state.current_corpus_id,
                chunk_set_id=chunk_state.current_chunk_set_id,
                lexical_config_hash=lex_cfg_hash,
                status=IndexingStatus.NO_OP,
                started_at=started,
                completed_at=completed,
                duration_ms=int((completed - started).total_seconds() * 1000),
                documents_total=documents_total,
                vocabulary_size=existing_manifest.vocabulary_size,
                lexical_index_id=index_id,
                lexical_index_manifest_path=existing_state.current_lexical_index_manifest,
                **_report_universe_kwargs(existing_manifest),
            )

        if published_complete:
            completed = datetime.now(tz=UTC)
            state = _publish_lexical_index_state(
                settings=settings,
                corpus_name=name,
                corpus_id=corpus_state.current_corpus_id,
                chunk_set_id=chunk_state.current_chunk_set_id,
                index_id=index_id,
                lex_cfg_hash=lex_cfg_hash,
                completed=completed,
            )
            assert existing_manifest is not None
            return LexicalIndexingReport(
                run_id=run_id,
                corpus_name=name,
                corpus_id=corpus_state.current_corpus_id,
                chunk_set_id=chunk_state.current_chunk_set_id,
                lexical_config_hash=lex_cfg_hash,
                status=IndexingStatus.SUCCESS,
                started_at=started,
                completed_at=completed,
                duration_ms=int((completed - started).total_seconds() * 1000),
                documents_total=documents_total,
                vocabulary_size=existing_manifest.vocabulary_size,
                lexical_index_id=index_id,
                lexical_index_manifest_path=state.current_lexical_index_manifest,
                metadata={"reused_published_index": True},
                **_report_universe_kwargs(existing_manifest),
            )

        text_builder = make_lexical_text_builder(settings)
        analyzer = make_lexical_analyzer(settings)

        manifest_path = settings.paths.manifests / Path(corpus_state.current_manifest).name
        if not manifest_path.exists():
            raise LexicalIndexingError(
                f"missing corpus manifest: {corpus_state.current_manifest}"
            )
        corpus_manifest = load_corpus_manifest(manifest_path)
        source_names = {
            entry.document_id: entry.source_name for entry in corpus_manifest.documents
        }
        document_ids = {chunk.document_id for chunk, _ in jobs}
        try:
            document_titles = resolve_document_titles_from_source_names(
                document_ids=document_ids,
                source_name_by_document_id=source_names,
                require=_requires_document_titles(text_builder),
            )
        except RankingTextError as exc:
            raise LexicalIndexingError(str(exc)) from exc

        analyzed: list[LexicalDocumentInput] = []
        excluded_ids: list[str] = []
        processed = 0
        report_progress(
            on_progress,
            step="analyzing_lexical_chunks",
            current=0,
            total=chunk_set_child_count if chunk_set_child_count > 0 else None,
            unit="chunks",
        )
        for chunk, chunk_artifact_id in jobs:
            try:
                inputs = ranking_inputs_for_chunk(
                    chunk_text=chunk.text,
                    section_path=list(chunk.section_path or []),
                    document_title=document_titles.get(chunk.document_id),
                )
                lexical_text = text_builder.build(inputs)
            except RankingTextError as exc:
                raise LexicalIndexingError(str(exc)) from exc
            terms, classification = analyze_and_classify(analyzer, lexical_text)
            processed += 1
            if classification == "excluded":
                excluded_ids.append(chunk.chunk_id)
            else:
                analyzed.append(
                    LexicalDocumentInput(
                        chunk_id=chunk.chunk_id,
                        terms=terms,
                        chunk_artifact_id=chunk_artifact_id,
                        document_id=chunk.document_id,
                    )
                )
            report_progress(
                on_progress,
                step="analyzing_lexical_chunks",
                current=processed,
                total=chunk_set_child_count if chunk_set_child_count > 0 else None,
                unit="chunks",
            )

        zero_term_excluded_count = len(excluded_ids)
        eligible_child_count = len(analyzed)
        if not _universe_reconciles(
            chunk_set_child_count=chunk_set_child_count,
            zero_term_excluded_count=zero_term_excluded_count,
            eligible_child_count=eligible_child_count,
        ):
            raise LexicalIndexingError(
                "lexical searchable-universe accounting failed reconciliation"
            )
        if eligible_child_count < 1:
            raise LexicalIndexingError(
                "lexical searchable-unit policy excluded all children; "
                "refusing empty lexical index"
            )

        eligible_ids = {item.chunk_id for item in analyzed}
        chunk_set_ids = {chunk.chunk_id for chunk, _ in jobs}
        if eligible_ids | set(excluded_ids) != chunk_set_ids:
            raise LexicalIndexingError(
                "lexical eligibility partition does not cover the chunk-set universe"
            )
        if eligible_ids & set(excluded_ids):
            raise LexicalIndexingError(
                "lexical eligibility partition has overlapping eligible/excluded IDs"
            )

        report_progress(
            on_progress,
            step="materializing_lexical_index",
            current=0,
            total=None,
            unit="chunks",
        )
        metadata = backend_impl.build(
            index_id,
            analyzed,
            chunk_set_id=chunk_state.current_chunk_set_id,
            lexical_config_hash=lex_cfg_hash,
            k1=settings.lexical.bm25.k1,
            b=settings.lexical.bm25.b,
            extra_metadata={
                "corpus_id": corpus_state.current_corpus_id,
                "text_strategy": text_builder.strategy,
                "text_contract": text_builder.contract_version,
                "analyzer_strategy": analyzer.strategy,
                "analyzer_contract": analyzer.contract_version,
                "searchable_units_contract": LEXICAL_EXCLUDE_ZERO_TERM_V1,
                "chunk_set_child_count": chunk_set_child_count,
                "zero_term_excluded_count": zero_term_excluded_count,
                "eligible_child_count": eligible_child_count,
            },
        )
        if not backend_impl.validate(index_id):
            raise LexicalIndexingError("built lexical index failed integrity validation")
        indexed_child_count = int(metadata["indexed_child_count"])
        if indexed_child_count != eligible_child_count:
            raise LexicalIndexingError(
                "lexical indexed_child_count does not match eligible_child_count"
            )
        # Exact backend membership == eligible ID set (not merely equal cardinality).
        backend_impl.open(index_id)
        try:
            backend_ids = set(backend_impl.indexed_chunk_ids())
        finally:
            backend_impl.close()
        if backend_ids != eligible_ids:
            raise LexicalIndexingError(
                "lexical backend membership does not equal eligible child-ID set"
            )

        completed = datetime.now(tz=UTC)
        physical_relpath = f"lexical-indexes/{index_id}"
        manifest = LexicalIndexManifest(
            lexical_index_id=index_id,
            corpus_id=corpus_state.current_corpus_id,
            chunk_set_id=chunk_state.current_chunk_set_id,
            lexical_config_hash=lex_cfg_hash,
            text_strategy=text_builder.strategy,
            text_contract=text_builder.contract_version,
            analyzer_strategy=analyzer.strategy,
            analyzer_contract=analyzer.contract_version,
            bm25_contract=settings.lexical.bm25.contract_version,
            bm25_k1=settings.lexical.bm25.k1,
            bm25_b=settings.lexical.bm25.b,
            bm25_idf=settings.lexical.bm25.idf,
            bm25_query_tf=settings.lexical.bm25.query_tf,
            backend=settings.lexical.backend,
            backend_contract=settings.lexical.backend_contract,
            expected_child_count=eligible_child_count,
            indexed_child_count=indexed_child_count,
            document_count=int(metadata["N"]),
            vocabulary_size=int(metadata["vocabulary_size"]),
            avgdl=float(metadata["avgdl"]),
            physical_index_relpath=physical_relpath,
            created_at=completed,
            searchable_units_contract=LEXICAL_EXCLUDE_ZERO_TERM_V1,
            chunk_set_child_count=chunk_set_child_count,
            zero_term_excluded_count=zero_term_excluded_count,
            eligible_child_count=eligible_child_count,
        )
        write_lexical_index_manifest(settings.paths.lexical_index_manifests, manifest)
        state = _publish_lexical_index_state(
            settings=settings,
            corpus_name=name,
            corpus_id=corpus_state.current_corpus_id,
            chunk_set_id=chunk_state.current_chunk_set_id,
            index_id=index_id,
            lex_cfg_hash=lex_cfg_hash,
            completed=completed,
        )

        return LexicalIndexingReport(
            run_id=run_id,
            corpus_name=name,
            corpus_id=corpus_state.current_corpus_id,
            chunk_set_id=chunk_state.current_chunk_set_id,
            lexical_config_hash=lex_cfg_hash,
            status=IndexingStatus.SUCCESS,
            started_at=started,
            completed_at=completed,
            duration_ms=int((completed - started).total_seconds() * 1000),
            children_total=chunk_set_child_count,
            indexed_child_count=indexed_child_count,
            documents_total=documents_total,
            vocabulary_size=int(metadata["vocabulary_size"]),
            lexical_index_id=index_id,
            lexical_index_manifest_path=state.current_lexical_index_manifest,
            searchable_units_contract=LEXICAL_EXCLUDE_ZERO_TERM_V1,
            chunk_set_child_count=chunk_set_child_count,
            zero_term_excluded_count=zero_term_excluded_count,
            eligible_child_count=eligible_child_count,
        )
    except Exception as exc:  # noqa: BLE001
        completed = datetime.now(tz=UTC)
        return LexicalIndexingReport(
            run_id=run_id,
            corpus_name=name,
            status=IndexingStatus.FAILED,
            started_at=started,
            completed_at=completed,
            duration_ms=int((completed - started).total_seconds() * 1000),
            errors=[str(exc)],
        )
    finally:
        if owned_backend and backend_impl is not None:
            close = getattr(backend_impl, "close", None)
            if callable(close):
                close()
