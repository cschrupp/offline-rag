"""Slice 1 ingestion pipeline: discover → parse/reuse → persist → commit."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    PARSER_SCHEMA_VERSION,
    content_hash_from_bytes,
    corpus_id_from_entries,
    document_id_from_bytes,
    new_execution_id,
    parse_config_hash,
    parsed_artifact_id,
)
from offline_rag.domain.blocks import ParsedDocument
from offline_rag.domain.corpus import (
    CorpusDocumentEntry,
    CorpusManifest,
    CorpusSourceEntry,
    CorpusState,
)
from offline_rag.domain.ingestion import (
    FileIngestionResult,
    FileIngestionStatus,
    IngestionReport,
    IngestionStatus,
)
from offline_rag.ingestion.discovery import (
    DiscoveredSource,
    DiscoveryError,
    discover_sources,
    validate_corpus_name,
)
from offline_rag.ingestion.docling_parser import DoclingPdfParser
from offline_rag.ingestion.markdown_parser import MarkdownParser
from offline_rag.ingestion.persistence import (
    corpus_state_path,
    load_corpus_state,
    processed_artifact_relpath,
    try_load_reusable_artifact,
    write_corpus_manifest,
    write_corpus_state,
    write_parsed_document,
)
from offline_rag.ingestion.text_parser import TextParser

ParserFactory = Callable[[], object]


class IngestionError(RuntimeError):
    pass


def _parser_for_media(
    media_type: str,
    settings: AppSettings,
) -> tuple[str, str, object, bool]:
    if media_type == "text/plain":
        parser = TextParser()
        return parser.name, parser.version, parser, False
    if media_type == "text/markdown":
        parser = MarkdownParser()
        return parser.name, parser.version, parser, False
    if media_type == "application/pdf":
        parser = DoclingPdfParser(
            artifacts_path=settings.paths.docling_artifacts,
            strict_offline=settings.project.strict_offline,
            ocr_enabled=settings.parsing.pdf.ocr_enabled,
        )
        return parser.name, parser.version, parser, settings.parsing.pdf.ocr_enabled
    raise IngestionError(f"no parser for media type: {media_type}")


def _source_entry_from_parsed(
    *,
    source: DiscoveredSource,
    parsed: ParsedDocument,
    content_hash: str,
    artifact_hash: str,
) -> CorpusSourceEntry:
    assert parsed.parsed_artifact_id
    assert parsed.parse_config_hash
    return CorpusSourceEntry(
        source_path=source.source_path,
        source_content_hash=content_hash,
        document_id=parsed.document.document_id,
        parsed_artifact_id=parsed.parsed_artifact_id,
        parse_config_hash=parsed.parse_config_hash,
        processed_artifact=processed_artifact_relpath(parsed.parsed_artifact_id),
        source_name=source.source_name,
        source_media_type=source.media_type,
        parser_name=parsed.parser_name,
        parser_version=parsed.parser_version,
        block_count=len(parsed.blocks),
        processed_artifact_hash=artifact_hash,
        warnings_count=len(parsed.warnings),
    )


def _states_equivalent(left: CorpusState, right: CorpusState) -> bool:
    return (
        left.corpus_name == right.corpus_name
        and left.current_corpus_id == right.current_corpus_id
        and left.current_manifest == right.current_manifest
        and left.sources == right.sources
    )


def load_active_state(
    settings: AppSettings,
    corpus_name: str,
) -> CorpusState | None:
    path = corpus_state_path(settings.paths.corpora, corpus_name)
    if not path.exists():
        return None
    state = load_corpus_state(path)
    if state.corpus_name != corpus_name:
        raise IngestionError(
            f"corpus state name mismatch: state has {state.corpus_name!r}, "
            f"requested {corpus_name!r}"
        )
    manifest_path = Path(state.current_manifest)
    if not manifest_path.is_absolute():
        manifest_path = settings.paths.manifests / Path(state.current_manifest).name
    if not manifest_path.exists():
        raise IngestionError(
            f"active corpus state references missing manifest: {state.current_manifest}"
        )
    return state


def run_ingestion(
    *,
    settings: AppSettings,
    inputs: list[Path],
    corpus_name: str = "default",
    recursive: bool = False,
    root: Path | None = None,
) -> IngestionReport:
    started = datetime.now(tz=UTC)
    run_id = new_execution_id(prefix="ingest")
    name = validate_corpus_name(corpus_name)

    try:
        discovered, skipped = discover_sources(inputs, recursive=recursive, root=root)
    except DiscoveryError as exc:
        completed = datetime.now(tz=UTC)
        return IngestionReport(
            run_id=run_id,
            corpus_name=name,
            status=IngestionStatus.FAILED,
            started_at=started,
            completed_at=completed,
            duration_ms=int((completed - started).total_seconds() * 1000),
            errors=[str(exc)],
        )

    previous = load_active_state(settings, name)
    previous_sources = dict(previous.sources) if previous else {}

    settings.paths.processed.mkdir(parents=True, exist_ok=True)
    settings.paths.manifests.mkdir(parents=True, exist_ok=True)

    file_results: list[FileIngestionResult] = []
    candidate_sources = dict(previous_sources)
    failed = False
    added = updated = unchanged = parsed_count = reused_count = warned = 0
    blocks_total = 0

    # Cache Docling parser instance across PDFs.
    pdf_parser: DoclingPdfParser | None = None

    for source in discovered:
        file_started = datetime.now(tz=UTC)
        try:
            source_bytes = source.absolute_path.read_bytes()
            if not source_bytes:
                raise IngestionError("source file is empty")
            doc_id = document_id_from_bytes(source_bytes)
            content_hash = content_hash_from_bytes(source_bytes)
            parser_name, parser_version, parser, ocr_enabled = _parser_for_media(
                source.media_type, settings
            )
            if isinstance(parser, DoclingPdfParser):
                if pdf_parser is None:
                    pdf_parser = parser
                parser = pdf_parser

            cfg_hash = parse_config_hash(
                parser_name=parser_name,
                parser_version=parser_version,
                ocr_enabled=ocr_enabled,
            )
            artifact_id = parsed_artifact_id(doc_id, cfg_hash)

            reused = try_load_reusable_artifact(
                settings.paths.processed,
                artifact_id,
                expected_document_id=doc_id,
                expected_parse_config_hash=cfg_hash,
            )
            if reused is not None:
                parsed, artifact_hash = reused
                status = FileIngestionStatus.REUSED
                reused_count += 1
            else:
                parsed = parser.parse(
                    source.absolute_path,
                    source_bytes=source_bytes,
                    document_id=doc_id,
                )
                # Ensure identity fields are set for native parsers too.
                parsed = parsed.model_copy(
                    update={
                        "parsed_artifact_id": artifact_id,
                        "parse_config_hash": cfg_hash,
                    }
                )
                _, artifact_hash = write_parsed_document(settings.paths.processed, parsed)
                status = FileIngestionStatus.PARSED
                parsed_count += 1

            entry = _source_entry_from_parsed(
                source=source,
                parsed=parsed,
                content_hash=content_hash,
                artifact_hash=artifact_hash,
            )
            prior = previous_sources.get(source.source_path)
            if prior is None:
                # New path; may still be content reuse.
                if any(
                    existing.document_id == entry.document_id
                    and existing.parsed_artifact_id == entry.parsed_artifact_id
                    for existing in previous_sources.values()
                ):
                    unchanged += 1
                else:
                    added += 1
            elif (
                prior.source_content_hash == entry.source_content_hash
                and prior.parsed_artifact_id == entry.parsed_artifact_id
            ):
                unchanged += 1
            else:
                updated += 1

            candidate_sources[source.source_path] = entry
            blocks_total += entry.block_count
            if entry.warnings_count:
                warned += 1
            duration = int((datetime.now(tz=UTC) - file_started).total_seconds() * 1000)
            file_results.append(
                FileIngestionResult(
                    source_path=source.source_path,
                    source_name=source.source_name,
                    absolute_path=str(source.absolute_path),
                    status=status,
                    document_id=entry.document_id,
                    parsed_artifact_id=entry.parsed_artifact_id,
                    parser_name=entry.parser_name,
                    parser_version=entry.parser_version,
                    block_count=entry.block_count,
                    warning_count=entry.warnings_count,
                    warnings=parsed.warnings,
                    duration_ms=duration,
                    processed_artifact=entry.processed_artifact,
                )
            )
        except Exception as exc:
            failed = True
            duration = int((datetime.now(tz=UTC) - file_started).total_seconds() * 1000)
            file_results.append(
                FileIngestionResult(
                    source_path=source.source_path,
                    source_name=source.source_name,
                    absolute_path=str(source.absolute_path),
                    status=FileIngestionStatus.FAILED,
                    duration_ms=duration,
                    error=str(exc),
                )
            )

    completed = datetime.now(tz=UTC)
    duration_ms = int((completed - started).total_seconds() * 1000)

    if failed:
        return IngestionReport(
            run_id=run_id,
            corpus_name=name,
            status=IngestionStatus.FAILED,
            started_at=started,
            completed_at=completed,
            duration_ms=duration_ms,
            files_discovered=len(discovered),
            files_parsed=parsed_count,
            files_reused=reused_count,
            files_added=added,
            files_updated=updated,
            files_unchanged=unchanged,
            files_failed=sum(1 for item in file_results if item.status == FileIngestionStatus.FAILED),
            files_warned=warned,
            blocks_total=blocks_total,
            unsupported_files_skipped=skipped,
            files=file_results,
            errors=["one or more sources failed; active corpus state was not updated"],
        )

    # Build full-corpus snapshot from candidate_sources.
    # Use a corpus-level parse hash that ignores per-file parser differences by
    # hashing the sorted set of per-source parse configs + schema.
    parse_identity = {
        "parser_schema_version": PARSER_SCHEMA_VERSION,
        "ocr_enabled": settings.parsing.pdf.ocr_enabled,
        "sources": sorted(
            {
                entry.source_path: {
                    "document_id": entry.document_id,
                    "parse_config_hash": entry.parse_config_hash,
                    "parsed_artifact_id": entry.parsed_artifact_id,
                }
                for entry in candidate_sources.values()
            }.items()
        ),
    }
    # Simpler stable config hash for corpus: schema + ocr + sorted artifact ids
    from offline_rag.core.ids import canonical_config_hash

    corpus_parse_hash = canonical_config_hash(
        {
            "parser_schema_version": PARSER_SCHEMA_VERSION,
            "ocr_enabled": settings.parsing.pdf.ocr_enabled,
            "entries": [
                {
                    "document_id": entry.document_id,
                    "source_content_hash": entry.source_content_hash,
                    "parsed_artifact_id": entry.parsed_artifact_id,
                    "parse_config_hash": entry.parse_config_hash,
                    "processed_artifact_hash": entry.processed_artifact_hash,
                }
                for entry in sorted(candidate_sources.values(), key=lambda e: e.document_id)
            ],
        }
    )
    _ = parse_identity  # reserved for future diagnostics

    identities = [
        {
            "document_id": entry.document_id,
            "source_content_hash": entry.source_content_hash,
            "processed_artifact_hash": entry.processed_artifact_hash,
            "parsed_artifact_id": entry.parsed_artifact_id,
        }
        for entry in candidate_sources.values()
    ]
    corpus_id = corpus_id_from_entries(
        schema_version="offline-rag-corpus-manifest-v1",
        parse_cfg_hash=corpus_parse_hash,
        document_identities=identities,
    )

    documents = [
        CorpusDocumentEntry(
            document_id=entry.document_id,
            source_path=entry.source_path,
            source_name=entry.source_name,
            source_content_hash=entry.source_content_hash,
            source_size_bytes=0,
            source_media_type=entry.source_media_type,
            parser_name=entry.parser_name,
            parser_version=entry.parser_version,
            block_count=entry.block_count,
            processed_artifact=entry.processed_artifact,
            processed_artifact_hash=entry.processed_artifact_hash,
            parsed_artifact_id=entry.parsed_artifact_id,
            parse_config_hash=entry.parse_config_hash,
            warnings_count=entry.warnings_count,
        )
        for entry in sorted(candidate_sources.values(), key=lambda e: e.source_path)
    ]
    size_by_path = {item.source_path: item.absolute_path.stat().st_size for item in discovered}
    prior_sizes: dict[str, int] = {}
    if previous is not None:
        try:
            from offline_rag.ingestion.persistence import load_corpus_manifest

            prior_manifest_path = settings.paths.manifests / Path(previous.current_manifest).name
            if prior_manifest_path.exists():
                prior_manifest = load_corpus_manifest(prior_manifest_path)
                prior_sizes = {
                    doc.source_path: doc.source_size_bytes for doc in prior_manifest.documents
                }
        except (OSError, ValueError, TypeError):
            prior_sizes = {}

    documents = [
        doc.model_copy(
            update={
                "source_size_bytes": size_by_path.get(
                    doc.source_path, prior_sizes.get(doc.source_path, 0)
                )
            }
        )
        for doc in documents
    ]

    manifest = CorpusManifest(
        corpus_id=corpus_id,
        corpus_hash=corpus_id,
        created_at=completed,
        config_hash=corpus_parse_hash,
        documents=documents,
        parser_environment={
            "parser_schema_version": PARSER_SCHEMA_VERSION,
            "ocr_enabled": settings.parsing.pdf.ocr_enabled,
        },
    )
    manifest_path = write_corpus_manifest(settings.paths.manifests, manifest)
    relative_manifest = f"manifests/{manifest_path.name}"

    new_state = CorpusState(
        corpus_name=name,
        current_corpus_id=corpus_id,
        current_manifest=relative_manifest,
        sources=candidate_sources,
        created_at=previous.created_at if previous else completed,
        updated_at=completed,
    )

    status = IngestionStatus.SUCCESS
    if previous is not None and _states_equivalent(
        previous.model_copy(update={"updated_at": previous.updated_at, "created_at": previous.created_at}),
        new_state.model_copy(update={"updated_at": previous.updated_at, "created_at": previous.created_at}),
    ):
        status = IngestionStatus.NO_OP
    else:
        # Compare without timestamps
        if previous is not None and (
            previous.current_corpus_id == new_state.current_corpus_id
            and previous.sources == new_state.sources
        ):
            status = IngestionStatus.NO_OP
        else:
            write_corpus_state(corpus_state_path(settings.paths.corpora, name), new_state)

    return IngestionReport(
        run_id=run_id,
        corpus_name=name,
        status=status,
        started_at=started,
        completed_at=completed,
        duration_ms=duration_ms,
        files_discovered=len(discovered),
        files_parsed=parsed_count,
        files_reused=reused_count,
        files_added=added,
        files_updated=updated,
        files_unchanged=unchanged,
        files_failed=0,
        files_warned=warned,
        blocks_total=blocks_total,
        unsupported_files_skipped=skipped,
        corpus_id=corpus_id,
        manifest_path=relative_manifest,
        files=file_results,
    )
