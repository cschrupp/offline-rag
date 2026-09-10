"""Slice 2 chunking pipeline over an active parsed corpus."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from offline_rag.chunking.persistence import (
    chunk_artifact_relpath,
    chunk_state_path,
    load_chunk_state,
    try_load_reusable_chunk_artifact,
    write_chunk_artifact,
    write_chunk_set_manifest,
    write_chunk_state,
)
from offline_rag.chunking.structure_aware import ChunkerBudgets, StructureAwareChunker
from offline_rag.chunking.tokenize import (
    FakeTokenCounter,
    TiktokenTokenCounter,
    TokenCounter,
)
from offline_rag.config.models import AppSettings, ChunkingSettings
from offline_rag.core.ids import (
    STRUCTURE_AWARE_CHUNKER_VERSION,
    chunk_artifact_id,
    chunk_config_hash,
    chunk_set_id_from_entries,
    new_execution_id,
)
from offline_rag.domain.chunking import (
    ChunkingReport,
    ChunkingStatus,
    ChunkSetDocumentEntry,
    ChunkSetManifest,
    ChunkState,
    DocumentChunkResult,
    DocumentChunkStatus,
)
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.ingestion.persistence import (
    corpus_state_path,
    load_corpus_manifest,
    load_corpus_state,
    load_parsed_document,
    processed_artifact_path,
)


class ChunkingError(RuntimeError):
    pass


def build_chunk_config_hash(settings: ChunkingSettings) -> str:
    return chunk_config_hash(
        {
            "strategy": settings.strategy,
            "parent_child": settings.parent_child,
            "tokenizer": {
                "implementation": settings.tokenizer.implementation,
                "encoding": settings.tokenizer.encoding,
            },
            "child": {
                "target_tokens": settings.child.target_tokens,
                "max_tokens": settings.child.max_tokens,
            },
            "parent": {
                "target_tokens": settings.parent.target_tokens,
                "max_tokens": settings.parent.max_tokens,
            },
            "chunker_version": STRUCTURE_AWARE_CHUNKER_VERSION,
        }
    )


def make_token_counter(settings: AppSettings, *, prefer_fake: bool = False) -> TokenCounter:
    if prefer_fake or settings.chunking.tokenizer.implementation == "fake":
        return FakeTokenCounter()
    if settings.chunking.tokenizer.implementation != "tiktoken":
        raise ChunkingError(
            f"unsupported tokenizer implementation: {settings.chunking.tokenizer.implementation}"
        )
    return TiktokenTokenCounter(
        encoding=settings.chunking.tokenizer.encoding,
        artifacts_path=settings.paths.tokenizer_artifacts,
    )


def run_chunking(
    *,
    settings: AppSettings,
    corpus_name: str = "default",
    token_counter: TokenCounter | None = None,
) -> ChunkingReport:
    started = datetime.now(tz=UTC)
    run_id = new_execution_id(prefix="chunk")
    name = validate_corpus_name(corpus_name)

    state_path = corpus_state_path(settings.paths.corpora, name)
    if not state_path.exists():
        completed = datetime.now(tz=UTC)
        return ChunkingReport(
            run_id=run_id,
            corpus_name=name,
            status=ChunkingStatus.FAILED,
            started_at=started,
            completed_at=completed,
            duration_ms=int((completed - started).total_seconds() * 1000),
            errors=[f"corpus '{name}' is not initialized; run offline-rag ingest first"],
        )

    corpus_state = load_corpus_state(state_path)
    if corpus_state.corpus_name != name:
        raise ChunkingError("corpus state name mismatch")
    manifest_path = settings.paths.manifests / Path(corpus_state.current_manifest).name
    if not manifest_path.exists():
        raise ChunkingError(f"missing corpus manifest: {corpus_state.current_manifest}")
    corpus_manifest = load_corpus_manifest(manifest_path)
    if corpus_manifest.corpus_id != corpus_state.current_corpus_id:
        raise ChunkingError("corpus state/manifest ID mismatch")

    cfg_hash = build_chunk_config_hash(settings.chunking)
    counter = token_counter or make_token_counter(settings)
    budgets = ChunkerBudgets(
        child_target=settings.chunking.child.target_tokens,
        child_max=settings.chunking.child.max_tokens,
        parent_target=settings.chunking.parent.target_tokens,
        parent_max=settings.chunking.parent.max_tokens,
        parent_child=settings.chunking.parent_child,
    )
    chunker = StructureAwareChunker(counter, budgets)

    settings.paths.chunks.mkdir(parents=True, exist_ok=True)
    settings.paths.chunk_manifests.mkdir(parents=True, exist_ok=True)

    results: list[DocumentChunkResult] = []
    entries: list[ChunkSetDocumentEntry] = []
    failed = False
    chunked = reused = 0
    parents_total = children_total = 0

    for doc in sorted(corpus_manifest.documents, key=lambda item: item.document_id):
        file_started = datetime.now(tz=UTC)
        try:
            if not doc.parsed_artifact_id:
                raise ChunkingError("manifest entry missing parsed_artifact_id")
            expected_id = chunk_artifact_id(doc.parsed_artifact_id, cfg_hash)
            cached = try_load_reusable_chunk_artifact(
                settings.paths.chunks,
                expected_id,
                expected_parsed_artifact_id=doc.parsed_artifact_id,
                expected_chunk_config_hash=cfg_hash,
            )
            if cached is not None:
                artifact, digest = cached
                status = DocumentChunkStatus.REUSED
                reused += 1
            else:
                parsed_path = processed_artifact_path(
                    settings.paths.processed, doc.parsed_artifact_id
                )
                if not parsed_path.exists():
                    # Fallback to relative processed path from manifest.
                    candidate = Path(doc.processed_artifact)
                    if not candidate.is_absolute():
                        candidate = settings.paths.processed / Path(doc.processed_artifact).name
                    parsed_path = candidate
                if not parsed_path.exists():
                    raise ChunkingError(f"missing ParsedDocument artifact: {doc.processed_artifact}")
                parsed = load_parsed_document(parsed_path)
                if parsed.document.document_id != doc.document_id:
                    raise ChunkingError("ParsedDocument document_id mismatch")
                if parsed.parsed_artifact_id and parsed.parsed_artifact_id != doc.parsed_artifact_id:
                    raise ChunkingError("ParsedDocument parsed_artifact_id mismatch")
                artifact = chunker.chunk_document(
                    parsed,
                    chunk_cfg_hash=cfg_hash,
                    parsed_artifact_id=doc.parsed_artifact_id,
                    chunk_artifact_id=expected_id,
                )
                _, digest = write_chunk_artifact(settings.paths.chunks, artifact)
                status = DocumentChunkStatus.CHUNKED
                chunked += 1

            parents_total += artifact.parent_count
            children_total += artifact.child_count
            entries.append(
                ChunkSetDocumentEntry(
                    document_id=doc.document_id,
                    parsed_artifact_id=doc.parsed_artifact_id,
                    chunk_artifact_id=artifact.chunk_artifact_id,
                    chunk_artifact=chunk_artifact_relpath(artifact.chunk_artifact_id),
                    chunk_artifact_hash=digest,
                    parent_count=artifact.parent_count,
                    child_count=artifact.child_count,
                )
            )
            duration = int((datetime.now(tz=UTC) - file_started).total_seconds() * 1000)
            results.append(
                DocumentChunkResult(
                    document_id=doc.document_id,
                    parsed_artifact_id=doc.parsed_artifact_id,
                    chunk_artifact_id=artifact.chunk_artifact_id,
                    status=status,
                    parent_count=artifact.parent_count,
                    child_count=artifact.child_count,
                    duration_ms=duration,
                )
            )
        except Exception as exc:
            failed = True
            duration = int((datetime.now(tz=UTC) - file_started).total_seconds() * 1000)
            results.append(
                DocumentChunkResult(
                    document_id=doc.document_id,
                    parsed_artifact_id=doc.parsed_artifact_id,
                    status=DocumentChunkStatus.FAILED,
                    duration_ms=duration,
                    error=str(exc),
                )
            )

    completed = datetime.now(tz=UTC)
    duration_ms = int((completed - started).total_seconds() * 1000)
    if failed:
        return ChunkingReport(
            run_id=run_id,
            corpus_name=name,
            corpus_id=corpus_manifest.corpus_id,
            chunk_config_hash=cfg_hash,
            status=ChunkingStatus.FAILED,
            started_at=started,
            completed_at=completed,
            duration_ms=duration_ms,
            documents_total=len(corpus_manifest.documents),
            documents_chunked=chunked,
            documents_reused=reused,
            documents_failed=sum(1 for item in results if item.status == DocumentChunkStatus.FAILED),
            parent_chunks=parents_total,
            child_chunks=children_total,
            documents=results,
            errors=["one or more documents failed; chunk state was not updated"],
        )

    set_id = chunk_set_id_from_entries(
        corpus_id=corpus_manifest.corpus_id,
        chunk_cfg_hash=cfg_hash,
        chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION,
        document_entries=[
            {
                "document_id": entry.document_id,
                "parsed_artifact_id": entry.parsed_artifact_id,
                "chunk_artifact_id": entry.chunk_artifact_id,
            }
            for entry in entries
        ],
    )
    manifest = ChunkSetManifest(
        chunk_set_id=set_id,
        corpus_id=corpus_manifest.corpus_id,
        chunk_config_hash=cfg_hash,
        chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION,
        tokenizer_name=counter.name,
        tokenizer_encoding=counter.encoding,
        documents=sorted(entries, key=lambda item: item.document_id),
        total_parent_count=parents_total,
        total_child_count=children_total,
        created_at=completed,
    )
    manifest_file = write_chunk_set_manifest(settings.paths.chunk_manifests, manifest)
    relative_manifest = f"chunk-manifests/{manifest_file.name}"

    new_state = ChunkState(
        corpus_name=name,
        source_corpus_id=corpus_manifest.corpus_id,
        current_chunk_set_id=set_id,
        current_chunk_manifest=relative_manifest,
        chunk_config_hash=cfg_hash,
        created_at=completed,
        updated_at=completed,
    )

    existing_path = chunk_state_path(settings.paths.corpora, name)
    status = ChunkingStatus.SUCCESS
    if existing_path.exists():
        existing = load_chunk_state(existing_path)
        if (
            existing.source_corpus_id == new_state.source_corpus_id
            and existing.current_chunk_set_id == new_state.current_chunk_set_id
            and existing.chunk_config_hash == new_state.chunk_config_hash
        ):
            status = ChunkingStatus.NO_OP
        else:
            if existing.created_at:
                new_state = new_state.model_copy(update={"created_at": existing.created_at})
            write_chunk_state(existing_path, new_state)
    else:
        write_chunk_state(existing_path, new_state)

    return ChunkingReport(
        run_id=run_id,
        corpus_name=name,
        corpus_id=corpus_manifest.corpus_id,
        chunk_config_hash=cfg_hash,
        status=status,
        started_at=started,
        completed_at=completed,
        duration_ms=duration_ms,
        documents_total=len(corpus_manifest.documents),
        documents_chunked=chunked,
        documents_reused=reused,
        documents_failed=0,
        parent_chunks=parents_total,
        child_chunks=children_total,
        chunk_set_id=set_id,
        chunk_manifest_path=relative_manifest,
        documents=results,
    )


def chunking_status_for_corpus(settings: AppSettings, corpus_name: str) -> str:
    name = validate_corpus_name(corpus_name)
    corpus_path = corpus_state_path(settings.paths.corpora, name)
    chunk_path = chunk_state_path(settings.paths.corpora, name)
    if not corpus_path.exists():
        return "CORPUS_NOT_INITIALIZED"
    if not chunk_path.exists():
        return "NOT_INITIALIZED"
    corpus_state = load_corpus_state(corpus_path)
    chunk_state = load_chunk_state(chunk_path)
    if chunk_state.source_corpus_id != corpus_state.current_corpus_id:
        return "STALE"
    return "CURRENT"
