"""CLI for OfflineRAG."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from offline_rag.chunking.persistence import (
    chunk_state_path,
    load_chunk_artifact,
    load_chunk_set_manifest,
    load_chunk_state,
)
from offline_rag.chunking.pipeline import chunking_status_for_corpus, run_chunking
from offline_rag.chunking.tokenize import validate_tiktoken_artifacts
from offline_rag.config import ConfigError, load_dotenv, load_settings
from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import (
    HybridRerankContextAssembler,
    HybridRerankContextError,
)
from offline_rag.context.evaluate import HybridRerankContextEvaluator
from offline_rag.context.status import (
    context_status_for_corpus,
    describe_context_status,
)
from offline_rag.core.ids import dense_point_uuid
from offline_rag.dense.evaluate import (
    DenseEvaluationError,
    DenseRetrievalEvaluator,
    EvaluationError,
)
from offline_rag.dense.persistence import (
    index_state_path,
    load_index_manifest,
    try_load_index_manifest,
    try_load_index_state,
)
from offline_rag.dense.pipeline import run_indexing
from offline_rag.dense.provision import (
    EmbeddingReadiness,
    provision_embedding_model,
    resolve_embedding_model_dir,
    validate_embedding_artifacts,
)
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.resolver import ChunkResolutionError, resolve_child_chunk
from offline_rag.dense.retrieve import DenseRetrievalError, DenseRetriever
from offline_rag.dense.status import indexing_status_for_corpus
from offline_rag.domain.chunking import ChunkingStatus
from offline_rag.domain.indexing import IndexingStatus, ProvisioningStatus
from offline_rag.domain.ingestion import IngestionStatus
from offline_rag.generation.evaluate import QueryEvaluator
from offline_rag.generation.orchestrate import (
    GroundedAnswerError,
    GroundedAnswerOrchestrator,
)
from offline_rag.generation.status import (
    describe_generation_status,
    generation_status_for_corpus,
)
from offline_rag.hybrid.evaluate import HybridRetrievalEvaluator
from offline_rag.hybrid.retrieve import HybridRetrievalError, HybridRetriever
from offline_rag.hybrid.status import hybrid_status_for_corpus
from offline_rag.ingestion.discovery import DiscoveryError, validate_corpus_name
from offline_rag.ingestion.docling_artifacts import validate_docling_artifacts
from offline_rag.ingestion.persistence import corpus_state_path, load_corpus_state
from offline_rag.ingestion.pipeline import run_ingestion
from offline_rag.lexical.backend import LocalInvertedIndexBackend
from offline_rag.lexical.evaluate import (
    LexicalEvaluationError,
    LexicalRetrievalEvaluator,
)
from offline_rag.lexical.persistence import (
    lexical_index_state_path,
    load_lexical_index_manifest,
    try_load_lexical_index_manifest,
    try_load_lexical_index_state,
)
from offline_rag.lexical.pipeline import make_lexical_analyzer, run_lexical_indexing
from offline_rag.lexical.retrieve import LexicalRetrievalError, LexicalRetriever
from offline_rag.lexical.scoring import idf as bm25_idf
from offline_rag.lexical.status import (
    describe_lexical_indexing_status,
    lexical_indexing_status_for_corpus,
)
from offline_rag.observability import configure_logging, log_event
from offline_rag.rerank.evaluate import HybridRerankRetrievalEvaluator
from offline_rag.rerank.provision import (
    RerankerReadiness,
    provision_reranker_model,
    resolve_reranker_model_dir,
    validate_reranker_artifacts,
)
from offline_rag.rerank.retrieve import (
    HybridRerankRetrievalError,
    HybridRerankRetriever,
)
from offline_rag.rerank.status import (
    hybrid_rerank_status_for_corpus,
    reranker_artifact_status,
)

NOT_IMPLEMENTED_EXIT = 2


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_config_path() -> Path:
    return _repo_root() / "config" / "base.yaml"


def _add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        action="append",
        default=None,
        help="YAML config path (repeatable; later files override earlier ones)",
    )


def _resolve_settings(settings: AppSettings) -> AppSettings:
    root_cwd = Path.cwd()

    def _resolve(path: Path) -> Path:
        return path if path.is_absolute() else (root_cwd / path)

    return settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "raw_data": _resolve(settings.paths.raw_data),
                    "manifests": _resolve(settings.paths.manifests),
                    "processed": _resolve(settings.paths.processed),
                    "corpora": _resolve(settings.paths.corpora),
                    "chunks": _resolve(settings.paths.chunks),
                    "chunk_manifests": _resolve(settings.paths.chunk_manifests),
                    "embeddings": _resolve(settings.paths.embeddings),
                    "index_manifests": _resolve(settings.paths.index_manifests),
                    "lexical_indexes": _resolve(settings.paths.lexical_indexes),
                    "lexical_index_manifests": _resolve(settings.paths.lexical_index_manifests),
                    "qdrant_storage": _resolve(settings.paths.qdrant_storage),
                    "retrieval_models": _resolve(settings.paths.retrieval_models),
                    "docling_artifacts": _resolve(settings.paths.docling_artifacts),
                    "tokenizer_artifacts": _resolve(settings.paths.tokenizer_artifacts),
                    "embedding_artifacts": _resolve(settings.paths.embedding_artifacts),
                    "reranker_artifacts": _resolve(settings.paths.reranker_artifacts),
                    "eval_results": _resolve(settings.paths.eval_results),
                }
            ),
            "dense": settings.dense.model_copy(
                update={"model_path": _resolve(settings.dense.model_path)}
            ),
            "reranker": settings.reranker.model_copy(
                update={
                    "model": settings.reranker.model.model_copy(
                        update={"model_path": _resolve(settings.reranker.model.model_path)}
                    )
                }
            ),
        }
    )


def _load_settings(args: argparse.Namespace) -> AppSettings:
    yaml_paths = args.config or [_default_config_path()]
    return _resolve_settings(load_settings(yaml_paths=yaml_paths))


def _not_implemented(command: str) -> int:
    print(
        f"offline-rag {command}: not implemented in this slice "
        "(deferred beyond Slice 3).",
        file=sys.stderr,
    )
    return NOT_IMPLEMENTED_EXIT


def cmd_ingest(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"ingest: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "ingest started", event="ingest.start")

    try:
        report = run_ingestion(
            settings=settings,
            inputs=[Path(p) for p in args.paths],
            corpus_name=args.corpus,
            recursive=bool(args.recursive),
            root=Path(args.root) if args.root else None,
        )
    except (DiscoveryError, ConfigError) as exc:
        print(f"ingest: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(report.model_dump_json())
    else:
        label = {
            IngestionStatus.SUCCESS: "Ingestion completed",
            IngestionStatus.NO_OP: "Ingestion completed (no changes)",
            IngestionStatus.FAILED: "Ingestion failed",
        }[report.status]
        print(label)
        print()
        print(f"Discovered:  {report.files_discovered}")
        print(f"Parsed:      {report.files_parsed}")
        print(f"Reused:      {report.files_reused}")
        print(f"Added:       {report.files_added}")
        print(f"Updated:     {report.files_updated}")
        print(f"Unchanged:   {report.files_unchanged}")
        print(f"Failed:      {report.files_failed}")
        print(f"Warnings:    {report.files_warned}")
        print(f"Blocks:      {report.blocks_total}")
        print()
        if report.corpus_id and report.manifest_path:
            print(f"Corpus:   {report.corpus_id}")
            print(f"Manifest: {report.manifest_path}")
        else:
            print("No complete corpus manifest was published.")
        failed_files = [item for item in report.files if item.status.value == "failed"]
        if failed_files:
            print()
            print("Failed:")
            for item in failed_files:
                print(f"  {item.source_path}")
                if item.error:
                    print(f"    {item.error}")

    return 1 if report.status == IngestionStatus.FAILED else 0


def cmd_chunk(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"chunk: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "chunk started", event="chunk.start")
    report = run_chunking(settings=settings, corpus_name=args.corpus)

    if args.json:
        print(report.model_dump_json())
    else:
        label = {
            ChunkingStatus.SUCCESS: "Chunking completed",
            ChunkingStatus.NO_OP: "Chunking completed (no changes)",
            ChunkingStatus.FAILED: "Chunking failed",
        }[report.status]
        print(label)
        print()
        print(f"Documents:   {report.documents_total}")
        print(f"Chunked:     {report.documents_chunked}")
        print(f"Reused:      {report.documents_reused}")
        print(f"Failed:      {report.documents_failed}")
        print(f"Parents:     {report.parent_chunks}")
        print(f"Children:    {report.child_chunks}")
        print()
        if report.chunk_set_id and report.chunk_manifest_path:
            print(f"Chunk set: {report.chunk_set_id}")
            print(f"Manifest:  {report.chunk_manifest_path}")
        else:
            print("No complete chunk-set manifest was published.")
        failed = [item for item in report.documents if item.status.value == "failed"]
        if failed:
            print()
            print("Failed:")
            for item in failed:
                print(f"  {item.document_id}")
                if item.error:
                    print(f"    {item.error}")
    return 1 if report.status == ChunkingStatus.FAILED else 0


def cmd_chunk_inspect(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"chunk inspect: configuration failed: {exc}", file=sys.stderr)
        return 1

    name = validate_corpus_name(args.corpus)
    state_file = chunk_state_path(settings.paths.corpora, name)
    if not state_file.exists():
        print(f"chunk inspect: chunk state not initialized for corpus '{name}'", file=sys.stderr)
        return 1
    state = load_chunk_state(state_file)
    manifest = load_chunk_set_manifest(
        settings.paths.chunk_manifests / Path(state.current_chunk_manifest).name
    )

    if args.chunk:
        for entry in manifest.documents:
            artifact = load_chunk_artifact(
                settings.paths.chunks / Path(entry.chunk_artifact).name
            )
            for chunk in [*artifact.parents, *artifact.children]:
                if chunk.chunk_id == args.chunk:
                    if args.json:
                        print(chunk.model_dump_json())
                    else:
                        print(f"chunk_id: {chunk.chunk_id}")
                        print(f"kind: {chunk.kind.value}")
                        print(f"document_id: {chunk.document_id}")
                        print(f"parent_chunk_id: {chunk.parent_chunk_id}")
                        print(f"previous_chunk_id: {chunk.previous_chunk_id}")
                        print(f"next_chunk_id: {chunk.next_chunk_id}")
                        print(f"token_count: {chunk.token_count}")
                        print(f"section_path: {chunk.section_path}")
                        print(f"page_start/end: {chunk.page_start}/{chunk.page_end}")
                        print(f"line_start/end: {chunk.line_start}/{chunk.line_end}")
                        print(f"source_block_ids: {chunk.source_block_ids}")
                        print()
                        print(chunk.text)
                    return 0
        print(f"chunk inspect: chunk not found: {args.chunk}", file=sys.stderr)
        return 1

    if args.document:
        for entry in manifest.documents:
            if entry.document_id == args.document:
                artifact = load_chunk_artifact(
                    settings.paths.chunks / Path(entry.chunk_artifact).name
                )
                summary = {
                    "document_id": entry.document_id,
                    "parsed_artifact_id": entry.parsed_artifact_id,
                    "chunk_artifact_id": entry.chunk_artifact_id,
                    "parent_count": entry.parent_count,
                    "child_count": entry.child_count,
                    "parents": [
                        {
                            "chunk_id": chunk.chunk_id,
                            "order": chunk.order,
                            "token_count": chunk.token_count,
                            "section_path": chunk.section_path,
                        }
                        for chunk in artifact.parents
                    ],
                    "children": [
                        {
                            "chunk_id": chunk.chunk_id,
                            "order": chunk.order,
                            "parent_chunk_id": chunk.parent_chunk_id,
                            "token_count": chunk.token_count,
                            "section_path": chunk.section_path,
                        }
                        for chunk in artifact.children
                    ],
                }
                if args.json:
                    print(json.dumps(summary, ensure_ascii=False))
                    return 0
                print(f"document_id: {summary['document_id']}")
                print(f"parsed_artifact_id: {summary['parsed_artifact_id']}")
                print(f"chunk_artifact_id: {summary['chunk_artifact_id']}")
                print(f"parent_count: {summary['parent_count']}")
                print(f"child_count: {summary['child_count']}")
                print("ordered children:")
                for chunk in artifact.children:
                    print(
                        f"  [{chunk.order}] {chunk.chunk_id} "
                        f"parent={chunk.parent_chunk_id} tokens={chunk.token_count}"
                    )
                return 0
        print(f"chunk inspect: document not found: {args.document}", file=sys.stderr)
        return 1

    print("chunk inspect: provide --chunk or --document", file=sys.stderr)
    return 1


def cmd_provision_embedding(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"provision embedding: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "provision embedding started", event="provision.embedding.start")

    destination = resolve_embedding_model_dir(
        embedding_artifacts_root=settings.paths.embedding_artifacts,
        model_path=settings.dense.model_path,
    )
    report = provision_embedding_model(
        destination,
        model_id=settings.indexing.embedding.model_id,
        revision=settings.indexing.embedding.revision,
        expected_dimension=settings.indexing.embedding.dimension,
        force=bool(args.force),
    )

    if args.json:
        print(report.model_dump_json())
    else:
        label = {
            ProvisioningStatus.READY: "Embedding provisioning completed",
            ProvisioningStatus.ALREADY_PROVISIONED: "Embedding already provisioned",
            ProvisioningStatus.FAILED: "Embedding provisioning failed",
        }[report.status]
        print(label)
        print()
        print(f"Model:       {report.model_id}")
        print(f"Revision:    {report.resolved_revision or report.requested_revision}")
        print(f"Destination: {report.destination}")
        if report.artifact_id:
            print(f"Artifact:    {report.artifact_id}")
        if report.manifest_path:
            print(f"Manifest:    {report.manifest_path}")
        print(f"Downloaded:  {report.files_downloaded}")
        if report.errors:
            print()
            print("Errors:")
            for error in report.errors:
                print(f"  {error}")

    return 1 if report.status == ProvisioningStatus.FAILED else 0


def cmd_provision_reranker(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"provision reranker: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "provision reranker started", event="provision.reranker.start")

    destination = resolve_reranker_model_dir(
        reranker_artifacts_root=settings.paths.reranker_artifacts,
        model_path=settings.reranker.model.model_path,
    )
    report = provision_reranker_model(
        destination,
        model_id=settings.reranker.model.model_id,
        revision=settings.reranker.model.revision,
        adapter_contract=settings.reranker.model.adapter_contract,
        force=bool(args.force),
    )

    if args.json:
        print(report.model_dump_json())
    else:
        label = {
            ProvisioningStatus.READY: "Reranker provisioning completed",
            ProvisioningStatus.ALREADY_PROVISIONED: "Reranker already provisioned",
            ProvisioningStatus.FAILED: "Reranker provisioning failed",
        }[report.status]
        print(label)
        print()
        print(f"Model:       {report.model_id}")
        print(f"Revision:    {report.resolved_revision or report.requested_revision}")
        print(f"Destination: {report.destination}")
        if report.artifact_id:
            print(f"Artifact:    {report.artifact_id}")
        if report.manifest_path:
            print(f"Manifest:    {report.manifest_path}")
        print(f"Downloaded:  {report.files_downloaded}")
        if report.errors:
            print()
            print("Errors:")
            for error in report.errors:
                print(f"  {error}")

    return 1 if report.status == ProvisioningStatus.FAILED else 0


def cmd_index(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"index: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "index started", event="index.start")
    report = run_indexing(settings=settings, corpus_name=args.corpus)

    if args.json:
        print(report.model_dump_json())
    else:
        label = {
            IndexingStatus.SUCCESS: "Indexing completed",
            IndexingStatus.NO_OP: "Indexing completed (no changes)",
            IndexingStatus.FAILED: "Indexing failed",
        }[report.status]
        print(label)
        print()
        print(f"Documents:            {report.documents_total}")
        print(f"Children:             {report.children_total}")
        print(f"Embeddings generated: {report.embeddings_generated}")
        print(f"Embeddings reused:    {report.embeddings_reused}")
        print(f"Embeddings failed:    {report.embeddings_failed}")
        print(f"Vectors:              {report.vectors_materialized}")
        print()
        if report.index_id and report.index_manifest_path:
            print(f"Index:      {report.index_id}")
            print(f"Collection: {report.collection_name}")
            print(f"Manifest:   {report.index_manifest_path}")
        else:
            print("No complete dense index was published.")
        if report.errors:
            print()
            print("Errors:")
            for error in report.errors:
                print(f"  {error}")
    return 1 if report.status == IndexingStatus.FAILED else 0


def cmd_index_lexical(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"index lexical: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "lexical index started", event="index.lexical.start")
    report = run_lexical_indexing(settings=settings, corpus_name=args.corpus)

    if args.json:
        print(report.model_dump_json())
    else:
        label = {
            IndexingStatus.SUCCESS: "Lexical indexing completed",
            IndexingStatus.NO_OP: "Lexical indexing completed (no changes)",
            IndexingStatus.FAILED: "Lexical indexing failed",
        }[report.status]
        print(label)
        print()
        print(f"Documents:            {report.documents_total}")
        print(f"Children:             {report.children_total}")
        print(f"Indexed children:     {report.indexed_child_count}")
        print(f"Vocabulary:           {report.vocabulary_size}")
        print()
        if report.lexical_index_id and report.lexical_index_manifest_path:
            print(f"Lexical index: {report.lexical_index_id}")
            print(f"Manifest:      {report.lexical_index_manifest_path}")
        else:
            print("No complete lexical index was published.")
        if report.errors:
            print()
            print("Errors:")
            for error in report.errors:
                print(f"  {error}")
    return 1 if report.status == IndexingStatus.FAILED else 0


def cmd_index_lexical_inspect(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"index lexical inspect: configuration failed: {exc}", file=sys.stderr)
        return 1

    try:
        name = validate_corpus_name(args.corpus)
    except DiscoveryError as exc:
        print(f"index lexical inspect: {exc}", file=sys.stderr)
        return 1

    status = lexical_indexing_status_for_corpus(settings, name)
    state = try_load_lexical_index_state(lexical_index_state_path(settings.paths.corpora, name))
    target_id = getattr(args, "index", None) or (state.current_lexical_index_id if state else None)
    manifest = None
    if target_id is not None:
        manifest = try_load_lexical_index_manifest(settings.paths.lexical_index_manifests, target_id)
        if manifest is None and state is not None and state.current_lexical_index_id == target_id:
            path = settings.paths.lexical_index_manifests / Path(state.current_lexical_index_manifest).name
            if path.exists():
                manifest = load_lexical_index_manifest(path)

    if args.term is not None or args.chunk is not None:
        if target_id is None or manifest is None:
            print("index lexical inspect: no published lexical index to inspect", file=sys.stderr)
            return 1
        backend = LocalInvertedIndexBackend(settings.paths.lexical_indexes)
        try:
            backend.open(target_id)
            if args.term is not None:
                analyzer = make_lexical_analyzer(settings)
                terms = analyzer.analyze_query_terms(args.term)
                if len(terms) != 1:
                    print(
                        "index lexical inspect: --term must analyze to exactly one term "
                        f"(got {terms!r})",
                        file=sys.stderr,
                    )
                    return 1
                term = terms[0]
                info = backend.term_info(term)
                if info is None:
                    payload = {"term": term, "found": False}
                else:
                    payload = {
                        "term": term,
                        "found": True,
                        "df": info["df"],
                        "idf": bm25_idf(n=backend.n, df=int(info["df"])),
                        "posting_count": len(info["postings"]),
                        "postings": info["postings"],
                    }
                if args.json:
                    print(json.dumps(payload, ensure_ascii=False))
                else:
                    print(f"term:           {payload['term']}")
                    print(f"found:          {payload['found']}")
                    if payload["found"]:
                        print(f"df:             {payload['df']}")
                        print(f"idf:            {payload['idf']:.6f}")
                        print(f"posting_count:  {payload['posting_count']}")
                        for chunk_id, tf in payload["postings"]:
                            print(f"  {chunk_id}  tf={tf}")
                return 0

            # --chunk
            doc = backend.document_info(args.chunk)
            if doc is None:
                print(f"index lexical inspect: chunk not in lexical index: {args.chunk}", file=sys.stderr)
                return 1
            chunk = resolve_child_chunk(
                settings.paths.chunks,
                chunk_artifact_id=str(doc.get("chunk_artifact_id") or ""),
                chunk_id=args.chunk,
            )
            payload = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "analyzed_length": doc.get("length"),
                "text": chunk.text,
                "lexical_index_id": target_id,
                "chunk_set_id": manifest.chunk_set_id,
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for key, value in payload.items():
                    print(f"{key}: {value}")
            return 0
        except (ChunkResolutionError, OSError, ValueError, RuntimeError) as exc:
            print(f"index lexical inspect: {exc}", file=sys.stderr)
            return 1
        finally:
            backend.close()

    summary = {
        "corpus_name": name,
        "status": status,
        "source_corpus_id": state.source_corpus_id if state else None,
        "source_chunk_set_id": state.source_chunk_set_id if state else None,
        "lexical_index_id": target_id,
        "lexical_config_hash": (
            manifest.lexical_config_hash if manifest else (state.lexical_config_hash if state else None)
        ),
        "text_builder": (
            f"{manifest.text_strategy}/{manifest.text_contract}" if manifest else None
        ),
        "analyzer": (
            f"{manifest.analyzer_strategy}/{manifest.analyzer_contract}" if manifest else None
        ),
        "bm25_contract": manifest.bm25_contract if manifest else None,
        "k1": manifest.bm25_k1 if manifest else None,
        "b": manifest.bm25_b if manifest else None,
        "N": manifest.document_count if manifest else None,
        "avgdl": manifest.avgdl if manifest else None,
        "vocabulary_size": manifest.vocabulary_size if manifest else None,
        "indexed_child_count": manifest.indexed_child_count if manifest else None,
        "physical_index": manifest.physical_index_relpath if manifest else None,
        "details": describe_lexical_indexing_status(settings, name),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, default=str))
    else:
        for key, value in summary.items():
            if key == "details":
                continue
            print(f"{key}: {value}")
    return 0


def _index_summary_payload(
    *,
    settings: AppSettings,
    corpus_name: str,
    index_id: str | None,
    status: str,
) -> dict[str, Any]:
    state = try_load_index_state(index_state_path(settings.paths.corpora, corpus_name))
    target_id = index_id
    if target_id is None and state is not None:
        target_id = state.current_index_id

    manifest = None
    if target_id is not None:
        manifest = try_load_index_manifest(settings.paths.index_manifests, target_id)
        # Fall back to state pointer filename when present.
        if manifest is None and state is not None and state.current_index_id == target_id:
            path = settings.paths.index_manifests / Path(state.current_index_manifest).name
            if path.exists():
                manifest = load_index_manifest(path)

    vector_count: int | None = None
    if manifest is not None:
        backend = QdrantLocalBackend(settings.paths.qdrant_storage)
        try:
            if backend.collection_exists(manifest.collection_name):
                vector_count = backend.count(manifest.collection_name)
        finally:
            backend.close()

    return {
        "corpus_name": corpus_name,
        "status": status,
        "source_corpus_id": state.source_corpus_id if state else None,
        "source_chunk_set_id": state.source_chunk_set_id if state else None,
        "index_id": target_id,
        "index_config_hash": (
            manifest.index_config_hash if manifest else (state.index_config_hash if state else None)
        ),
        "collection_name": manifest.collection_name if manifest else None,
        "embedding_model_id": manifest.embedding_model_id if manifest else None,
        "embedding_model_revision": manifest.embedding_model_revision if manifest else None,
        "embedding_dimension": manifest.embedding_dimension if manifest else None,
        "normalize": manifest.normalize if manifest else None,
        "similarity_metric": manifest.similarity_metric if manifest else None,
        "embedding_text": (
            f"{manifest.embedding_text_strategy}/{manifest.embedding_text_contract}"
            if manifest
            else None
        ),
        "expected_child_count": manifest.expected_child_count if manifest else None,
        "vector_count": vector_count,
        "index_manifest_path": state.current_index_manifest if state and target_id == state.current_index_id else (
            f"index-manifests/{target_id}.json" if target_id else None
        ),
    }


def _print_index_summary(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False))
        return
    print(f"corpus_name:              {summary['corpus_name']}")
    print(f"status:                   {summary['status']}")
    print(f"source_corpus_id:         {summary['source_corpus_id']}")
    print(f"source_chunk_set_id:      {summary['source_chunk_set_id']}")
    print(f"index_id:                 {summary['index_id']}")
    print(f"index_config_hash:        {summary['index_config_hash']}")
    print(f"collection_name:          {summary['collection_name']}")
    print(f"embedding_model_id:       {summary['embedding_model_id']}")
    print(f"embedding_model_revision: {summary['embedding_model_revision']}")
    print(f"embedding_dimension:      {summary['embedding_dimension']}")
    print(f"normalize:                {summary['normalize']}")
    print(f"similarity_metric:        {summary['similarity_metric']}")
    print(f"embedding_text:           {summary.get('embedding_text')}")
    print(f"expected_child_count:     {summary['expected_child_count']}")
    print(f"vector_count:             {summary['vector_count']}")
    print(f"index_manifest_path:      {summary['index_manifest_path']}")


def _resolve_index_collection(
    settings: AppSettings,
    *,
    corpus_name: str,
    index_id: str | None,
) -> tuple[str, str]:
    """Return (index_id, collection_name) for inspect lookups."""
    state = try_load_index_state(index_state_path(settings.paths.corpora, corpus_name))
    target = index_id
    if target is None:
        if state is None:
            raise LookupError(f"index state not initialized for corpus '{corpus_name}'")
        target = state.current_index_id
    manifest = try_load_index_manifest(settings.paths.index_manifests, target)
    if manifest is None and state is not None and state.current_index_id == target:
        path = settings.paths.index_manifests / Path(state.current_index_manifest).name
        if path.exists():
            manifest = load_index_manifest(path)
    if manifest is None:
        raise LookupError(f"dense index manifest not found: {target}")
    return target, manifest.collection_name


def cmd_index_inspect(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"index inspect: configuration failed: {exc}", file=sys.stderr)
        return 1

    try:
        name = validate_corpus_name(args.corpus)
    except DiscoveryError as exc:
        print(f"index inspect: {exc}", file=sys.stderr)
        return 1

    selectors = [flag for flag in (args.index, args.point, args.chunk) if flag]
    if args.point and args.chunk:
        print("index inspect: provide only one of --point or --chunk", file=sys.stderr)
        return 1

    status = indexing_status_for_corpus(settings, name)

    if args.point or args.chunk:
        try:
            index_id, collection_name = _resolve_index_collection(
                settings,
                corpus_name=name,
                index_id=args.index,
            )
        except LookupError as exc:
            print(f"index inspect: {exc}", file=sys.stderr)
            return 1

        point_id = args.point or dense_point_uuid(args.chunk)
        backend = QdrantLocalBackend(settings.paths.qdrant_storage)
        try:
            record = backend.get_point(collection_name, point_id)
        finally:
            backend.close()

        if record is None:
            print(f"index inspect: point not found: {point_id}", file=sys.stderr)
            return 1

        payload = dict(record.payload)
        chunk_id = str(payload.get("chunk_id") or args.chunk or "")
        chunk_artifact_id = str(payload.get("chunk_artifact_id") or "")
        text: str | None = None
        resolution_error: str | None = None
        if chunk_id and chunk_artifact_id:
            try:
                chunk = resolve_child_chunk(
                    settings.paths.chunks,
                    chunk_artifact_id=chunk_artifact_id,
                    chunk_id=chunk_id,
                )
                text = chunk.text
            except ChunkResolutionError as exc:
                resolution_error = str(exc)

        detail = {
            "index_id": index_id,
            "collection_name": collection_name,
            "point_id": record.point_id,
            "chunk_id": chunk_id or None,
            "document_id": payload.get("document_id"),
            "parent_chunk_id": payload.get("parent_chunk_id"),
            "previous_chunk_id": payload.get("previous_chunk_id"),
            "next_chunk_id": payload.get("next_chunk_id"),
            "chunk_artifact_id": chunk_artifact_id or None,
            "embedding_id": payload.get("embedding_id"),
            "section_path": payload.get("section_path") or [],
            "page_start": payload.get("page_start"),
            "page_end": payload.get("page_end"),
            "line_start": payload.get("line_start"),
            "line_end": payload.get("line_end"),
            "order": payload.get("order"),
            "token_count": payload.get("token_count"),
            "vector_dimension": len(record.vector),
            "text": text,
            "resolution_error": resolution_error,
            "payload": payload,
        }
        if args.json:
            print(json.dumps(detail, ensure_ascii=False))
        else:
            print(f"index_id:          {detail['index_id']}")
            print(f"collection_name:   {detail['collection_name']}")
            print(f"point_id:          {detail['point_id']}")
            print(f"chunk_id:          {detail['chunk_id']}")
            print(f"document_id:       {detail['document_id']}")
            print(f"parent_chunk_id:   {detail['parent_chunk_id']}")
            print(f"previous_chunk_id: {detail['previous_chunk_id']}")
            print(f"next_chunk_id:     {detail['next_chunk_id']}")
            print(f"chunk_artifact_id: {detail['chunk_artifact_id']}")
            print(f"embedding_id:      {detail['embedding_id']}")
            print(f"section_path:      {detail['section_path']}")
            print(f"page_start/end:    {detail['page_start']}/{detail['page_end']}")
            print(f"line_start/end:    {detail['line_start']}/{detail['line_end']}")
            print(f"order:             {detail['order']}")
            print(f"token_count:       {detail['token_count']}")
            print(f"vector_dimension:  {detail['vector_dimension']}")
            if resolution_error:
                print(f"resolution_error:  {resolution_error}")
            print()
            if text is not None:
                print(text)
        return 0

    if args.index or not selectors:
        if args.index:
            manifest = try_load_index_manifest(settings.paths.index_manifests, args.index)
            if manifest is None:
                print(f"index inspect: index not found: {args.index}", file=sys.stderr)
                return 1
            active = try_load_index_state(index_state_path(settings.paths.corpora, name))
            summary_status = (
                status if active is not None and active.current_index_id == args.index else "HISTORICAL"
            )
            summary = _index_summary_payload(
                settings=settings,
                corpus_name=name,
                index_id=args.index,
                status=summary_status,
            )
        else:
            summary = _index_summary_payload(
                settings=settings,
                corpus_name=name,
                index_id=None,
                status=status,
            )
        _print_index_summary(summary, as_json=bool(args.json))
        return 0

    print("index inspect: invalid selector combination", file=sys.stderr)
    return 1


def cmd_retrieve(args: argparse.Namespace) -> int:
    if not args.query:
        print("retrieve: --query is required", file=sys.stderr)
        return 1
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"retrieve: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "retrieve started", event="retrieve.start")

    retriever = DenseRetriever(settings)
    try:
        result = retriever.retrieve(
            query=args.query,
            corpus_name=args.corpus,
            top_k=args.top_k,
        )
    except DenseRetrievalError as exc:
        print(f"retrieve: {exc}", file=sys.stderr)
        return 1
    finally:
        retriever.close()

    if args.json:
        print(result.model_dump_json())
    else:
        print("Query:")
        print(result.query)
        print()
        print("Index:")
        print(result.index_id)
        print()
        for candidate in result.candidates:
            section = " / ".join(candidate.section_path) if candidate.section_path else "-"
            page = (
                f"{candidate.page_start}"
                if candidate.page_start == candidate.page_end
                else f"{candidate.page_start}-{candidate.page_end}"
            )
            print(f"{candidate.rank}. score={candidate.score:.3f}")
            print(f"   document: {candidate.document_id}")
            print(f"   section: {section}")
            print(f"   page: {page}")
            print(f"   chunk: {candidate.chunk_id}")
            print()
            for line in candidate.text.splitlines() or [candidate.text]:
                print(f"   {line}")
            print()
    return 0


def cmd_retrieve_lexical(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"retrieve lexical: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "lexical retrieve started", event="retrieve.lexical.start")

    retriever = LexicalRetriever(settings)
    try:
        result = retriever.retrieve(
            query=args.query,
            corpus_name=args.corpus,
            top_k=args.top_k,
        )
    except LexicalRetrievalError as exc:
        print(f"retrieve lexical: {exc}", file=sys.stderr)
        return 1
    finally:
        retriever.close()

    if args.json:
        print(result.model_dump_json())
    else:
        print("Query:")
        print(result.query)
        print()
        print("Method:")
        print(result.method)
        print()
        print("Lexical index:")
        print(result.index_id)
        print()
        for candidate in result.candidates:
            section = " / ".join(candidate.section_path) if candidate.section_path else "-"
            print(f"{candidate.rank}. bm25={candidate.score:.6f}")
            print(f"   document: {candidate.document_id}")
            print(f"   section: {section}")
            print(f"   chunk: {candidate.chunk_id}")
            print()
            for line in candidate.text.splitlines() or [candidate.text]:
                print(f"   {line}")
            print()
    return 0


def cmd_retrieve_hybrid(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"retrieve hybrid: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "hybrid retrieve started", event="retrieve.hybrid.start")

    retriever = HybridRetriever(settings)
    try:
        result = retriever.retrieve(
            query=args.query,
            corpus_name=args.corpus,
            top_k=args.top_k,
        )
    except HybridRetrievalError as exc:
        print(f"retrieve hybrid: {exc}", file=sys.stderr)
        return 1
    finally:
        retriever.close()

    if args.json:
        print(result.model_dump_json())
    else:
        print("Hybrid Retrieval")
        print()
        print("Query:")
        print(result.query)
        print()
        print(f"Dense index:   {result.dense_index_id}")
        print(f"Lexical index: {result.lexical_index_id}")
        print(
            f"Fusion:        {settings.fusion.contract_version} "
            f"(k={settings.fusion.rrf_k}, "
            f"dense={settings.fusion.dense_top_k}, "
            f"lexical={settings.fusion.lexical_top_k})"
        )
        print(f"fusion_config: {result.fusion_config_hash}")
        print()
        for candidate in result.candidates:
            section = " / ".join(candidate.section_path) if candidate.section_path else "-"
            dens = (
                f"rank {candidate.fusion.dense_rank} score {candidate.fusion.dense_score:.3f}"
                if candidate.fusion.dense_rank is not None
                else "-"
            )
            lexi = (
                f"rank {candidate.fusion.lexical_rank} score {candidate.fusion.lexical_score:.3f}"
                if candidate.fusion.lexical_rank is not None
                else "-"
            )
            print(f"{candidate.rank}. RRF={candidate.score:.6f}")
            print(f"   chunk: {candidate.chunk_id}")
            print(f"   dense:   {dens}")
            print(f"   lexical: {lexi}")
            print(f"   section: {section}")
            print()
            for line in candidate.text.splitlines() or [candidate.text]:
                print(f"   {line}")
            print()
    return 0


def cmd_retrieve_hybrid_rerank(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"retrieve hybrid-rerank: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "hybrid-rerank retrieve started", event="retrieve.hybrid_rerank.start")

    retriever = HybridRerankRetriever(settings)
    try:
        result = retriever.retrieve(
            query=args.query,
            corpus_name=args.corpus,
            top_k=args.top_k,
        )
    except HybridRerankRetrievalError as exc:
        print(f"retrieve hybrid-rerank: {exc}", file=sys.stderr)
        return 1
    finally:
        retriever.close()

    if args.json:
        print(result.model_dump_json())
    else:
        print("Hybrid-Rerank Retrieval")
        print()
        print("Query:")
        print(result.query)
        print()
        print(f"Dense index:   {result.dense_index_id}")
        print(f"Lexical index: {result.lexical_index_id}")
        print(f"fusion_config: {result.fusion_config_hash}")
        print(f"reranker_cfg:  {result.reranker_config_hash}")
        print(
            f"Reranker:      {settings.reranker.model.model_id} "
            f"(input_k={settings.reranker.input_k}, output_k={result.top_k})"
        )
        print()
        for candidate in result.candidates:
            section = " / ".join(candidate.section_path) if candidate.section_path else "-"
            prov = candidate.hybrid_rerank
            print(f"{candidate.rank}. logit={candidate.score:.6f}")
            print(f"   chunk:  {candidate.chunk_id}")
            print(f"   hybrid: rank {prov.hybrid_rank} RRF {prov.rrf_score:.6f}")
            print(f"   section: {section}")
            print()
            for line in candidate.text.splitlines() or [candidate.text]:
                print(f"   {line}")
            print()
    return 0


def cmd_retrieve_hybrid_rerank_context(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"retrieve hybrid-rerank-context: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(
        logger,
        20,
        "hybrid-rerank-context retrieve started",
        event="retrieve.hybrid_rerank_context.start",
    )

    assembler = HybridRerankContextAssembler(settings)
    try:
        result = assembler.assemble(query=args.query, corpus_name=args.corpus)
    except HybridRerankContextError as exc:
        print(f"retrieve hybrid-rerank-context: {exc}", file=sys.stderr)
        return 1
    finally:
        assembler.close()

    if args.json:
        print(result.model_dump_json())
    else:
        print("Hybrid-Rerank-Context Assembly")
        print()
        print("Query:")
        print(result.query)
        print()
        print(f"Strategy:      {result.effective_context_semantics.get('strategy')}")
        print(
            f"Anchors:       {result.diagnostics.actual_anchor_count} / "
            f"anchor_k={result.diagnostics.requested_anchor_k}"
        )
        print(f"Evidence units:{result.diagnostics.evidence_unit_count}")
        print(
            f"Context tokens:{result.context_token_count} / "
            f"max={result.max_context_tokens}"
        )
        print(f"Stop reason:   {result.diagnostics.stop_reason}")
        print(f"Dense index:   {result.dense_index_id}")
        print(f"Lexical index: {result.lexical_index_id}")
        print(f"fusion_config: {result.fusion_config_hash}")
        print(f"reranker_cfg:  {result.reranker_config_hash}")
        print(f"context_cfg:   {result.context_config_hash}")
        print()
        for index, unit in enumerate(result.evidence_units, start=1):
            clip_note = " clipped" if unit.clipped else ""
            print(
                f"{index}. [{unit.kind}{clip_note}] source={unit.source_chunk_id} "
                f"tokens={unit.token_count}"
            )
            print(f"   primary_anchor: {unit.primary_anchor_chunk_id}")
            print()
            for line in unit.text.splitlines() or [unit.text]:
                print(f"   {line}")
            print()
        if result.assembled_text:
            print("Assembled evidence:")
            print(result.assembled_text)
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"query: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "query started", event="query.start")

    orchestrator = GroundedAnswerOrchestrator(settings)
    try:
        result = orchestrator.answer(query=args.query, corpus_name=args.corpus)
    except GroundedAnswerError as exc:
        print(f"query: {exc}", file=sys.stderr)
        return 1
    finally:
        orchestrator.close()

    if args.json:
        print(result.model_dump_json())
        return 0

    print("Grounded Query")
    print()
    print("Query:")
    print(result.query)
    print()
    print(f"Status:       {result.status}")
    if result.abstention_reason:
        print(f"Abstention:   {result.abstention_reason}")
    if result.generation_failure_reason:
        print(f"Failure:      {result.generation_failure_reason}")
    print(f"Method:       {result.method}")
    print(f"gen_config:   {result.generation_config_hash}")
    if result.context_config_hash:
        print(f"context_cfg:  {result.context_config_hash}")
    print()
    if result.status == "answered" and result.answer_text is not None:
        print("Answer:")
        print(result.answer_text)
        print()
        print("Citations:")
        for citation in result.citations:
            clip = " clipped" if citation.clipped else ""
            print(
                f"- {citation.evidence_unit_id} [{citation.kind}{clip}] "
                f"source={citation.source_chunk_id}"
            )
    elif result.status == "insufficient_evidence":
        print("Insufficient evidence to answer groundedly.")
    else:
        print("No validated grounded answer was produced.")
    return 0


def cmd_eval_run(_args: argparse.Namespace) -> int:
    return _not_implemented("eval run")


def cmd_eval_compare(args: argparse.Namespace) -> int:
    from offline_rag.evaluation.compare import (
        CompareError,
        compare_retrieval_results,
        format_comparison_human,
        load_retrieval_eval_result,
    )

    try:
        result_a = load_retrieval_eval_result(Path(args.a))
        result_b = load_retrieval_eval_result(Path(args.b))
        comparison = compare_retrieval_results(result_a, result_b)
    except CompareError as exc:
        print(f"eval compare: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(comparison.model_dump_json())
        return 0
    print(format_comparison_human(comparison))
    return 0


def cmd_eval_query(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"eval query: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "eval query started", event="eval.query.start")

    evaluator = QueryEvaluator(settings)
    try:
        report = evaluator.evaluate(
            Path(args.dataset),
            corpus_name=args.corpus,
            output_path=Path(args.output) if args.output else None,
        )
    except (EvaluationError, GroundedAnswerError) as exc:
        print(f"eval query: {exc}", file=sys.stderr)
        return 1
    finally:
        evaluator.orchestrator.close()

    if args.json:
        print(report.model_dump_json())
        return 0

    print("Query evaluation completed")
    print()
    print(f"Run:          {report.run_id}")
    print(f"Method:       {report.method}")
    print(f"Dataset:      {report.dataset_id}")
    print(f"Cases:        {report.case_count}")
    print(f"Gen hash:     {report.generation_config_hash}")
    print()
    print("Outcomes")
    print(f"  answered:              {report.outcomes.answered} ({report.answered_rate:.4f})")
    print(
        f"  insufficient_evidence: {report.outcomes.insufficient_evidence} "
        f"({report.insufficient_evidence_rate:.4f})"
    )
    print(
        f"    empty_context:       {report.outcomes.empty_context} "
        f"({report.empty_context_rate:.4f})"
    )
    print(
        f"    model_abstain:       {report.outcomes.model_abstain} "
        f"({report.model_abstain_rate:.4f})"
    )
    print(
        f"  generation_failed:     {report.outcomes.generation_failed} "
        f"({report.generation_failed_rate:.4f})"
    )
    print(
        f"  citation_invalid:      {report.outcomes.citation_invalid} "
        f"({report.citation_invalid_rate:.4f} of invoked)"
    )
    print()
    print(f"Generator invoked: {report.generator_invoked_case_count}")
    print(f"Attempts total:    {report.total_generator_attempts}")
    print(f"Latency mean:      {report.latency_mean_ms:.1f} ms")
    print(f"Gen latency mean:  {report.generation_latency_mean_ms:.1f} ms")
    result_path = report.metadata.get("result_path")
    if result_path:
        print()
        print(f"Report:       {result_path}")
    return 0


def cmd_eval_retrieve(args: argparse.Namespace) -> int:
    from offline_rag.evaluation.format import format_retrieval_result_human

    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"eval retrieve: configuration failed: {exc}", file=sys.stderr)
        return 1

    method = getattr(args, "method", "dense") or "dense"
    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(
        logger,
        20,
        "eval retrieve started",
        event="eval.retrieve.start",
        method=method,
    )

    report = None
    closer = None
    try:
        if method == "lexical":
            evaluator = LexicalRetrievalEvaluator(settings)
            closer = evaluator.retriever.close
            report = evaluator.evaluate(
                Path(args.dataset),
                corpus_name=args.corpus,
                top_k=int(args.top_k),
                output_path=Path(args.output) if args.output else None,
            )
        elif method == "hybrid":
            evaluator = HybridRetrievalEvaluator(settings)
            closer = evaluator.retriever.close
            report = evaluator.evaluate(
                Path(args.dataset),
                corpus_name=args.corpus,
                top_k=int(args.top_k),
                output_path=Path(args.output) if args.output else None,
            )
        elif method == "hybrid-rerank":
            evaluator = HybridRerankRetrievalEvaluator(settings)
            closer = evaluator.retriever.close
            report = evaluator.evaluate(
                Path(args.dataset),
                corpus_name=args.corpus,
                top_k=int(args.top_k),
                output_path=Path(args.output) if args.output else None,
            )
        elif method == "hybrid-rerank-context":
            evaluator = HybridRerankContextEvaluator(settings)
            closer = evaluator.assembler.close
            report = evaluator.evaluate(
                Path(args.dataset),
                corpus_name=args.corpus,
                output_path=Path(args.output) if args.output else None,
            )
        elif method == "dense":
            evaluator = DenseRetrievalEvaluator(settings)
            closer = evaluator.retriever.close
            report = evaluator.evaluate(
                Path(args.dataset),
                corpus_name=args.corpus,
                top_k=int(args.top_k),
                output_path=Path(args.output) if args.output else None,
            )
        else:
            print(
                f"eval retrieve: unsupported method '{method}' "
                "(use dense|lexical|hybrid|hybrid-rerank|hybrid-rerank-context)",
                file=sys.stderr,
            )
            return 1
    except (
        EvaluationError,
        DenseEvaluationError,
        LexicalEvaluationError,
        DenseRetrievalError,
        LexicalRetrievalError,
        HybridRetrievalError,
        HybridRerankRetrievalError,
        HybridRerankContextError,
    ) as exc:
        print(f"eval retrieve: {exc}", file=sys.stderr)
        return 1
    finally:
        if closer is not None:
            closer()

    assert report is not None
    if args.json:
        print(report.model_dump_json())
    else:
        print(format_retrieval_result_human(report))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"doctor: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "doctor started", event="doctor.start")

    errors: list[str] = []
    notes: list[str] = []

    try:
        corpus_name = validate_corpus_name(args.corpus)
    except DiscoveryError as exc:
        print(f"doctor: FAIL: {exc}", file=sys.stderr)
        return 1

    if settings.project.strict_offline:
        if settings.security.reject_unapproved_generation_endpoint and not settings.generation.approved_endpoints:
            errors.append("strict_offline requires generation.approved_endpoints when endpoint rejection is enabled")
        if settings.security.allow_network_tools:
            errors.append("strict_offline is incompatible with security.allow_network_tools=true")

    path_fields = [
        ("raw_data", settings.paths.raw_data),
        ("manifests", settings.paths.manifests),
        ("processed", settings.paths.processed),
        ("corpora", settings.paths.corpora),
        ("chunks", settings.paths.chunks),
        ("chunk_manifests", settings.paths.chunk_manifests),
        ("embeddings", settings.paths.embeddings),
        ("index_manifests", settings.paths.index_manifests),
        ("lexical_indexes", settings.paths.lexical_indexes),
        ("lexical_index_manifests", settings.paths.lexical_index_manifests),
        ("qdrant_storage", settings.paths.qdrant_storage),
        ("retrieval_models", settings.paths.retrieval_models),
        ("eval_results", settings.paths.eval_results),
    ]

    creatable = {
        "corpora",
        "processed",
        "manifests",
        "chunks",
        "chunk_manifests",
        "embeddings",
        "index_manifests",
        "lexical_indexes",
        "lexical_index_manifests",
    }

    for name, path in path_fields:
        if not path.exists():
            if name in creatable:
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    errors.append(f"cannot create paths.{name}={path} ({exc})")
                    continue
            else:
                errors.append(f"configured path does not exist: paths.{name}={path}")
                continue
        if not path.is_dir():
            errors.append(f"path must be a directory: paths.{name}={path}")
            continue
        if name == "retrieval_models":
            continue
        probe = path / ".offline_rag_write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"path is not writable: paths.{name}={path} ({exc})")

    notes.append(f"Embeddings path                 {settings.paths.embeddings}")
    notes.append(f"Index manifests path            {settings.paths.index_manifests}")
    notes.append(f"Embedding artifacts path        {settings.paths.embedding_artifacts}")
    notes.append(f"Qdrant storage path             {settings.paths.qdrant_storage}")
    notes.append(
        "Dense ranking text               "
        f"{settings.indexing.embedding_text.strategy}/"
        f"{settings.indexing.embedding_text.contract_version}"
    )
    notes.append(
        "Dense query text                 "
        f"{settings.dense.query_text.strategy}/"
        f"{settings.dense.query_text.contract_version}"
    )
    notes.append(
        "Dense searchable units           "
        f"{settings.indexing.searchable_units.strategy}/"
        f"{settings.indexing.searchable_units.contract_version}"
    )
    notes.append(
        "Lexical ranking text             "
        f"{settings.lexical.text.strategy}/{settings.lexical.text.contract_version}"
    )
    if settings.indexing.embedding_text.contract_version == "title-section-text-v1":
        notes.append("Document title contract          document-title-v1")
    if settings.lexical.text.contract_version == "title-section-text-v1":
        notes.append("Lexical document title contract  document-title-v1")

    try:
        import docling

        notes.append(f"Docling package                 PASS ({getattr(docling, '__version__', '?')})")
    except Exception as exc:
        errors.append(f"Docling package import failed: {exc}")
        notes.append("Docling package                 FAIL")

    artifacts = validate_docling_artifacts(settings.paths.docling_artifacts)
    notes.append(f"Docling artifacts path         {artifacts.path}")
    if artifacts.ready:
        notes.append("Docling artifacts provisioned  PASS")
        notes.append("PDF parser offline-ready       PASS")
    else:
        notes.append("Docling artifacts provisioned  FAIL")
        notes.append(f"Reason: {artifacts.reason}")
        notes.append("Action: uv run python scripts/provision_docling.py")
        if settings.project.strict_offline:
            errors.append(f"Docling artifacts not ready: {artifacts.reason}")

    notes.append(f"Tokenizer implementation        {settings.chunking.tokenizer.implementation}")
    notes.append(f"Tokenizer encoding              {settings.chunking.tokenizer.encoding}")
    tok_ok, tok_reason = validate_tiktoken_artifacts(
        settings.paths.tokenizer_artifacts,
        encoding=settings.chunking.tokenizer.encoding,
    )
    if tok_ok:
        notes.append("Tokenizer artifacts             PASS")
        notes.append("Offline token counting          PASS")
    else:
        notes.append("Tokenizer artifacts             FAIL")
        notes.append(f"Reason: {tok_reason}")
        notes.append("Action: uv run python scripts/provision_tiktoken.py")
        if settings.project.strict_offline:
            errors.append(f"Tokenizer artifacts not ready: {tok_reason}")

    embedding_dir = resolve_embedding_model_dir(
        embedding_artifacts_root=settings.paths.embedding_artifacts,
        model_path=settings.dense.model_path,
    )
    emb_status = validate_embedding_artifacts(
        embedding_dir,
        expected_model_id=settings.indexing.embedding.model_id,
        expected_revision=settings.indexing.embedding.revision,
        expected_dimension=settings.indexing.embedding.dimension,
    )
    notes.append(f"Embedding model path            {emb_status.path}")
    if emb_status.readiness == EmbeddingReadiness.READY:
        notes.append("Embedding model artifacts       PASS")
        notes.append("Offline dense embedding         PASS")
        if emb_status.manifest is not None:
            notes.append(f"Embedding artifact_id           {emb_status.manifest.artifact_id}")
    else:
        notes.append(f"Embedding model artifacts       FAIL ({emb_status.readiness.value})")
        notes.append(f"Reason: {emb_status.reason}")
        notes.append("Action: offline-rag provision embedding")
        if settings.project.strict_offline:
            errors.append(f"Embedding artifacts not ready: {emb_status.reason}")

    state_file = corpus_state_path(settings.paths.corpora, corpus_name)
    notes.append(f"Corpus name                     {corpus_name}")
    notes.append(f"State path                      {state_file}")
    active_corpus_id: str | None = None
    if not state_file.exists():
        notes.append("State                           NOT INITIALIZED")
    else:
        try:
            state = load_corpus_state(state_file)
            if state.corpus_name != corpus_name:
                errors.append("State corpus_name mismatch")
                notes.append("State                           FAIL")
            else:
                notes.append("State                           PASS")
                active_corpus_id = state.current_corpus_id
                notes.append(f"Active corpus                   {state.current_corpus_id}")
                manifest = settings.paths.manifests / Path(state.current_manifest).name
                if manifest.exists():
                    notes.append("Current manifest                PASS")
                else:
                    notes.append("Current manifest                FAIL")
                    errors.append(f"missing manifest {state.current_manifest}")
        except Exception as exc:
            notes.append("State                           FAIL")
            errors.append(f"invalid corpus state: {exc}")

    chunk_status = chunking_status_for_corpus(settings, corpus_name)
    notes.append(f"Chunking status                 {chunk_status}")
    cstate_file = chunk_state_path(settings.paths.corpora, corpus_name)
    notes.append(f"Chunk state path                {cstate_file}")
    if cstate_file.exists():
        try:
            cstate = load_chunk_state(cstate_file)
            notes.append(f"Chunked corpus                  {cstate.source_corpus_id}")
            notes.append(f"Chunk set                       {cstate.current_chunk_set_id}")
            notes.append(f"Chunk config hash               {cstate.chunk_config_hash}")
        except Exception as exc:
            errors.append(f"invalid chunk state: {exc}")
    if chunk_status == "STALE" or chunk_status == "NOT_INITIALIZED" and active_corpus_id:
        notes.append(f"Action                           offline-rag chunk --corpus {corpus_name}")

    index_status = indexing_status_for_corpus(settings, corpus_name)
    notes.append(f"Indexing status                 {index_status}")
    istate_file = index_state_path(settings.paths.corpora, corpus_name)
    notes.append(f"Index state path                {istate_file}")
    istate = try_load_index_state(istate_file)
    if istate is not None:
        notes.append(f"Indexed corpus                  {istate.source_corpus_id}")
        notes.append(f"Indexed chunk set               {istate.source_chunk_set_id}")
        notes.append(f"Index                           {istate.current_index_id}")
        notes.append(f"Index config hash               {istate.index_config_hash}")
        notes.append(f"Index manifest                  {istate.current_index_manifest}")
    if index_status in {"NOT_INDEXED", "INDEX_STALE", "INDEX_CONFIG_STALE", "CHUNKS_STALE"}:
        notes.append(f"Action                           offline-rag index --corpus {corpus_name}")

    lexical_status = lexical_indexing_status_for_corpus(settings, corpus_name)
    notes.append(f"Lexical indexing status         {lexical_status}")
    lstate_file = lexical_index_state_path(settings.paths.corpora, corpus_name)
    notes.append(f"Lexical state path              {lstate_file}")
    lstate = try_load_lexical_index_state(lstate_file)
    if lstate is not None:
        notes.append(f"Lexical corpus                  {lstate.source_corpus_id}")
        notes.append(f"Lexical chunk set               {lstate.source_chunk_set_id}")
        notes.append(f"Lexical index                   {lstate.current_lexical_index_id}")
        notes.append(f"Lexical config hash             {lstate.lexical_config_hash}")
        notes.append(f"Lexical manifest                {lstate.current_lexical_index_manifest}")
    if lexical_status in {
        "NOT_INDEXED",
        "LEXICAL_INDEX_STALE",
        "LEXICAL_CONFIG_STALE",
        "CHUNKS_STALE",
    }:
        notes.append(
            f"Action                           offline-rag index lexical --corpus {corpus_name}"
        )

    hybrid_status = hybrid_status_for_corpus(settings, corpus_name)
    notes.append(f"Hybrid status                   {hybrid_status}")
    if hybrid_status != "READY":
        notes.append(
            "Action                           ensure dense+lexical CURRENT on same chunk set"
        )

    artifact_status = reranker_artifact_status(settings)
    notes.append(f"Reranker artifacts              {artifact_status}")
    notes.append(f"Reranker model                  {settings.reranker.model.model_id}")
    notes.append(f"Reranker revision               {settings.reranker.model.revision}")
    model_dir = resolve_reranker_model_dir(
        reranker_artifacts_root=settings.paths.reranker_artifacts,
        model_path=settings.reranker.model.model_path,
    )
    notes.append(f"Reranker model path             {model_dir}")
    if artifact_status != "READY":
        notes.append("Action                           offline-rag provision reranker")
        if settings.project.strict_offline and settings.reranker.enabled:
            art = validate_reranker_artifacts(
                model_dir,
                expected_model_id=settings.reranker.model.model_id,
                expected_revision=settings.reranker.model.revision,
                expected_adapter_contract=settings.reranker.model.adapter_contract,
            )
            if art.readiness != RerankerReadiness.READY:
                errors.append(f"Reranker artifacts not ready: {art.reason}")

    hybrid_rerank_status = hybrid_rerank_status_for_corpus(settings, corpus_name)
    notes.append(f"Hybrid-rerank status            {hybrid_rerank_status}")
    if hybrid_rerank_status != "READY":
        notes.append(
            "Action                           ensure Hybrid READY + provisioned enabled reranker"
        )

    context_status = context_status_for_corpus(settings, corpus_name)
    notes.append(f"Context status                  {context_status}")
    notes.append(f"Context strategy                {settings.context.strategy}")
    notes.append(f"Context enabled                 {settings.context.enabled}")
    if context_status != "READY":
        details = describe_context_status(settings, corpus_name)
        for reason in details.get("reasons") or []:
            notes.append(f"Context reason                  {reason}")
        notes.append(
            "Action                           ensure Hybrid-rerank READY + context.enabled "
            "+ valid chunk structure + TokenCounter"
        )

    generation_status = generation_status_for_corpus(settings, corpus_name)
    notes.append(f"Generation status               {generation_status}")
    notes.append(f"Generation enabled              {settings.generation.enabled}")
    notes.append(f"Generation provider             {settings.generation.provider}")
    notes.append(f"Generation model                {settings.generation.model}")
    notes.append(
        f"Generation prompt                {settings.generation.prompt.contract_version}"
    )
    notes.append(
        "Generation API key               "
        f"{'configured' if settings.generation.api_key else 'not set'}"
    )
    if generation_status != "READY":
        details = describe_generation_status(settings, corpus_name)
        for reason in details.get("reasons") or []:
            notes.append(f"Generation reason               {reason}")
        notes.append(
            "Action                           ensure Context READY + approved endpoint/model "
            "+ reachable OpenAI-compatible generator"
        )

    from offline_rag.gold_authoring.readiness import (
        authoring_status_label,
        evaluate_authoring_readiness,
    )

    authoring = evaluate_authoring_readiness(settings)
    authoring_label = authoring_status_label(authoring)
    notes.append(f"Authoring status                {authoring_label}")
    notes.append(f"Authoring enabled               {settings.authoring.enabled}")
    notes.append(f"Authoring provider              {authoring.provider}")
    notes.append(f"Authoring adapter               {authoring.adapter_contract}")
    notes.append(
        f"Authoring model                 {authoring.model if authoring.model else 'unset'}"
    )
    notes.append(f"Authoring network policy        {authoring.network_policy}")
    notes.append(
        f"Authoring endpoint authorized   {'yes' if authoring.endpoint_approved else 'no'}"
    )
    notes.append(
        f"Authoring model authorized      {'yes' if authoring.model_approved else 'no'}"
    )
    notes.append(
        "Authoring API key               "
        f"{'configured' if authoring.api_key_configured else 'not configured'}"
    )
    notes.append("Authoring connectivity checked  no")
    for reason in authoring.reason_codes:
        notes.append(f"Authoring reason                {reason}")
    if settings.authoring.enabled and not authoring.ready:
        for reason in authoring.reason_codes:
            errors.append(f"Authoring NOT READY: {reason}")
        notes.append(
            "Action                           configure authoring.model + "
            "authoring.approved_endpoints/models under an allowed network_policy"
        )

    for note in notes:
        print(f"doctor: {note}")

    if errors:
        for error in errors:
            print(f"doctor: FAIL: {error}", file=sys.stderr)
            log_event(logger, 40, error, event="doctor.check_failed")
        return 1

    print("doctor: OK — configuration valid; local paths usable; offline readiness checked.")
    log_event(logger, 20, "doctor completed successfully", event="doctor.ok")
    return 0


def cmd_gold_propose(args: argparse.Namespace) -> int:
    from offline_rag.gold_authoring.propose import ProposePreRunError, run_gold_propose

    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"gold propose: configuration failed: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_gold_propose(
            settings,
            corpus_name=str(args.corpus),
            count=int(args.count),
            seed=int(args.seed),
            output=Path(args.output) if args.output else None,
            force=bool(args.force),
        )
    except ProposePreRunError as exc:
        print(f"gold propose: {exc}", file=sys.stderr)
        return 2

    run = result.run
    if run is None:
        print(f"gold propose: {result.message or 'failed'}", file=sys.stderr)
        return result.exit_code

    print(result.message or "Gold proposal run completed.")
    print()
    print(f"Gold proposal run: {run.authoring_run_id}")
    print(f"Corpus:               {run.corpus_name or args.corpus}")
    print(f"Chunk set:            {run.chunk_set_id}")
    pipeline = run.proposal_pipeline
    print(
        "Sampling contract:    "
        f"{pipeline.sampling_contract if pipeline is not None else ''}"
    )
    print(f"Sampling seed:        {run.sampling_seed}")
    print()
    print(f"Requested seeds:      {run.requested_count}")
    print(f"Selected seeds:       {len(run.selected_chunk_ids)}")
    print(f"Successful proposals: {run.successful_count}")
    print(f"Failed proposals:     {run.failed_count}")
    print(f"Pending SilverCases:  {len(run.cases)}")
    if result.failure_reason_counts:
        print()
        print("Failures:")
        for reason, count in sorted(result.failure_reason_counts.items()):
            print(f"  {reason}: {count}")
    if result.output_path is not None:
        print()
        print("Output:")
        print(f"  {result.output_path}")
    elif result.message:
        print()
        print(result.message, file=sys.stderr)
    return result.exit_code


def cmd_gold_pool(args: argparse.Namespace) -> int:
    from offline_rag.gold_authoring.pool import PoolPreRunError, run_gold_pool

    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"gold pool: configuration failed: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_gold_pool(
            settings,
            run_path=Path(args.run),
            output=Path(args.output) if args.output else None,
            force=bool(args.force),
        )
    except PoolPreRunError as exc:
        print(f"gold pool: {exc}", file=sys.stderr)
        return 2

    run = result.run
    if run is None:
        print(f"gold pool: {result.message or 'failed'}", file=sys.stderr)
        return result.exit_code

    print(result.message or "Candidate pooling completed.")
    print()
    print(f"Gold authoring run:   {run.authoring_run_id}")
    print(f"Chunk set:            {run.chunk_set_id}")
    pooling = run.pooling
    if pooling is not None:
        print(f"Pooling contract:     {pooling.pooling_contract}")
        print(f"Retrievers:           {', '.join(pooling.retrievers)}")
    print()
    print(f"Targeted cases:       {run.pool_targeted_case_count}")
    print(f"Successful pools:     {run.pool_successful_case_count}")
    print(f"Failed pools:         {run.pool_failed_case_count}")
    if result.failure_reason_counts:
        print()
        print("Failures:")
        for reason, count in sorted(result.failure_reason_counts.items()):
            print(f"  {reason}: {count}")
    if result.output_path is not None:
        print()
        print("Output:")
        print(f"  {result.output_path}")
    return result.exit_code


def cmd_gold_prelabel(args: argparse.Namespace) -> int:
    from offline_rag.gold_authoring.prelabel import PrelabelPreRunError, run_gold_prelabel

    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"gold prelabel: configuration failed: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_gold_prelabel(
            settings,
            run_path=Path(args.run),
            output=Path(args.output) if args.output else None,
            force=bool(args.force),
        )
    except PrelabelPreRunError as exc:
        print(f"gold prelabel: {exc}", file=sys.stderr)
        return 2

    run = result.run
    if run is None:
        print(f"gold prelabel: {result.message or 'failed'}", file=sys.stderr)
        return result.exit_code

    print(result.message or "Relevance prelabeling completed.")
    print()
    print(f"Gold authoring run:   {run.authoring_run_id}")
    print(f"Chunk set:            {run.chunk_set_id}")
    stage = run.prelabeling
    if stage is not None:
        print(f"Prelabel contract:    {stage.provenance.relevance_contract}")
        print(f"Authorcfg:            {stage.provenance.authorcfg_id}")
        print()
        print(f"Targeted cases:       {stage.targeted_case_count}")
        print(f"Successful:           {stage.successful_case_count}")
        print(f"Failed:               {stage.failed_case_count}")
        print(f"Model requests:       {result.model_request_count}")
    if result.failure_reason_counts:
        print()
        print("Failures:")
        for reason, count in sorted(result.failure_reason_counts.items()):
            print(f"  {reason}: {count}")
    if result.output_path is not None:
        print()
        print("Output:")
        print(f"  {result.output_path}")
    return result.exit_code


def cmd_gold_review(args: argparse.Namespace) -> int:
    from offline_rag.gold_authoring.review_server import (
        DEFAULT_REVIEW_HOST,
        DEFAULT_REVIEW_PORT,
        ReviewServerError,
        create_review_server,
    )

    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"gold review: configuration failed: {exc}", file=sys.stderr)
        return 2

    host = args.host if args.host is not None else DEFAULT_REVIEW_HOST
    port = int(args.port) if args.port is not None else DEFAULT_REVIEW_PORT
    try:
        server, _session, url = create_review_server(
            settings=settings,
            run_path=Path(args.run),
            host=host,
            port=port,
        )
    except ReviewServerError as exc:
        print(f"gold review: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"gold review: {exc}", file=sys.stderr)
        return 2

    print("Gold review server started (loopback-only).")
    print(f"Review UI: {url}")
    print(f"Authoring run: {Path(args.run).resolve()}")
    print("Press Ctrl+C to stop. Review mutations persist as you save.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("Review server stopped.")
    finally:
        server.server_close()
    return 0


def cmd_gold_finalize(args: argparse.Namespace) -> int:
    from offline_rag.gold_authoring.finalize import FinalizePreRunError, run_gold_finalize

    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"gold finalize: configuration failed: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_gold_finalize(
            settings,
            run_path=Path(args.run),
            output=Path(args.output) if args.output else None,
            force=bool(args.force),
        )
    except FinalizePreRunError as exc:
        print(f"gold finalize: {exc}", file=sys.stderr)
        return 2

    print(result.message or "GoldDataset finalization completed.")
    print()
    if result.status_counts:
        print("Run status counts:")
        for key in ("pending", "accepted", "edited", "rejected"):
            print(f"  {key}: {result.status_counts.get(key, 0)}")
    print()
    print(f"Exported cases: {len(result.exported_case_ids)}")
    if result.dataset_id:
        print(f"Gold dataset ID: {result.dataset_id}")
    if result.output_path is not None:
        print()
        print("Output:")
        print(f"  {result.output_path}")
    return result.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="offline-rag", description="OfflineRAG CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser(
        "ingest",
        help="Ingest documents into a named corpus (additive/update; no deletion)",
    )
    _add_config_argument(ingest)
    ingest.add_argument("paths", nargs="+", help="Files and/or directories to ingest")
    ingest.add_argument("--recursive", action="store_true", help="Recurse into directories")
    ingest.add_argument("--root", type=Path, default=None, help="Corpus root for portable source paths")
    ingest.add_argument("--corpus", default="default", help="Logical corpus name (default: default)")
    ingest.add_argument("--json", action="store_true", help="Emit IngestionReport JSON on stdout")
    ingest.set_defaults(func=cmd_ingest)

    chunk = subparsers.add_parser("chunk", help="Chunk an active parsed corpus")
    _add_config_argument(chunk)
    chunk.add_argument("--corpus", default="default", help="Logical corpus name")
    chunk.add_argument("--json", action="store_true", help="Emit ChunkingReport JSON on stdout")
    chunk.set_defaults(func=cmd_chunk)
    chunk_sub = chunk.add_subparsers(dest="chunk_command", required=False)

    inspect = chunk_sub.add_parser("inspect", help="Inspect chunk artifacts (read-only)")
    _add_config_argument(inspect)
    inspect.add_argument("--corpus", default="default")
    inspect.add_argument("--chunk", default=None)
    inspect.add_argument("--document", default=None)
    inspect.add_argument("--json", action="store_true")
    inspect.set_defaults(func=cmd_chunk_inspect)

    provision = subparsers.add_parser("provision", help="Provision local offline artifacts")
    provision_sub = provision.add_subparsers(dest="provision_command", required=True)
    provision_embedding = provision_sub.add_parser(
        "embedding",
        help="Download/pin the local dense embedding model",
    )
    _add_config_argument(provision_embedding)
    provision_embedding.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when artifacts already validate as READY",
    )
    provision_embedding.add_argument("--json", action="store_true", help="Emit EmbeddingProvisionReport JSON")
    provision_embedding.set_defaults(func=cmd_provision_embedding)

    provision_reranker = provision_sub.add_parser(
        "reranker",
        help="Download/pin the local cross-encoder reranker model",
    )
    _add_config_argument(provision_reranker)
    provision_reranker.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when artifacts already validate as READY",
    )
    provision_reranker.add_argument(
        "--json",
        action="store_true",
        help="Emit RerankerProvisionReport JSON",
    )
    provision_reranker.set_defaults(func=cmd_provision_reranker)

    index = subparsers.add_parser("index", help="Build/publish the dense index for a corpus")
    _add_config_argument(index)
    index.add_argument("--corpus", default="default", help="Logical corpus name")
    index.add_argument("--json", action="store_true", help="Emit IndexingReport JSON on stdout")
    index.set_defaults(func=cmd_index)
    index_sub = index.add_subparsers(dest="index_command", required=False)

    index_inspect = index_sub.add_parser("inspect", help="Inspect dense index state (read-only)")
    _add_config_argument(index_inspect)
    index_inspect.add_argument("--corpus", default="default")
    index_inspect.add_argument("--index", default=None, help="Dense index ID")
    index_inspect.add_argument("--point", default=None, help="Qdrant point UUID")
    index_inspect.add_argument("--chunk", default=None, help="Child chunk ID")
    index_inspect.add_argument("--json", action="store_true")
    index_inspect.set_defaults(func=cmd_index_inspect)

    index_lexical = index_sub.add_parser("lexical", help="Build/publish the lexical BM25 index")
    _add_config_argument(index_lexical)
    index_lexical.add_argument("--corpus", default="default", help="Logical corpus name")
    index_lexical.add_argument("--json", action="store_true", help="Emit LexicalIndexingReport JSON")
    index_lexical.set_defaults(func=cmd_index_lexical)
    index_lexical_sub = index_lexical.add_subparsers(dest="lexical_command", required=False)

    index_lexical_inspect = index_lexical_sub.add_parser(
        "inspect",
        help="Inspect lexical index state (read-only)",
    )
    _add_config_argument(index_lexical_inspect)
    index_lexical_inspect.add_argument("--corpus", default="default")
    index_lexical_inspect.add_argument("--index", default=None, help="Lexical index ID")
    index_lexical_inspect.add_argument("--chunk", default=None, help="Child chunk ID")
    index_lexical_inspect.add_argument("--term", default=None, help="Term to inspect")
    index_lexical_inspect.add_argument("--json", action="store_true")
    index_lexical_inspect.set_defaults(func=cmd_index_lexical_inspect)

    retrieve = subparsers.add_parser("retrieve", help="Dense retrieval over the active current index")
    _add_config_argument(retrieve)
    retrieve.add_argument("--corpus", default="default", help="Logical corpus name")
    retrieve.add_argument("--query", default=None, help="Query text")
    retrieve.add_argument("--top-k", type=int, default=None, dest="top_k", help="Override dense.top_k")
    retrieve.add_argument("--json", action="store_true", help="Emit DenseRetrievalResult JSON")
    retrieve.set_defaults(func=cmd_retrieve)
    retrieve_sub = retrieve.add_subparsers(dest="retrieve_command", required=False)

    retrieve_lexical = retrieve_sub.add_parser("lexical", help="Lexical BM25 retrieval")
    _add_config_argument(retrieve_lexical)
    retrieve_lexical.add_argument("--corpus", default="default", help="Logical corpus name")
    retrieve_lexical.add_argument("--query", required=True, help="Query text")
    retrieve_lexical.add_argument(
        "--top-k",
        type=int,
        default=None,
        dest="top_k",
        help="Override lexical.top_k",
    )
    retrieve_lexical.add_argument("--json", action="store_true", help="Emit LexicalRetrievalResult JSON")
    retrieve_lexical.set_defaults(func=cmd_retrieve_lexical)

    retrieve_hybrid = retrieve_sub.add_parser("hybrid", help="Hybrid dense+lexical RRF retrieval")
    _add_config_argument(retrieve_hybrid)
    retrieve_hybrid.add_argument("--corpus", default="default", help="Logical corpus name")
    retrieve_hybrid.add_argument("--query", required=True, help="Query text")
    retrieve_hybrid.add_argument(
        "--top-k",
        type=int,
        default=None,
        dest="top_k",
        help="Override fusion.output_top_k",
    )
    retrieve_hybrid.add_argument("--json", action="store_true", help="Emit HybridRetrievalResult JSON")
    retrieve_hybrid.set_defaults(func=cmd_retrieve_hybrid)

    retrieve_hybrid_rerank = retrieve_sub.add_parser(
        "hybrid-rerank",
        help="Hybrid RRF followed by cross-encoder reranking",
    )
    _add_config_argument(retrieve_hybrid_rerank)
    retrieve_hybrid_rerank.add_argument("--corpus", default="default", help="Logical corpus name")
    retrieve_hybrid_rerank.add_argument("--query", required=True, help="Query text")
    retrieve_hybrid_rerank.add_argument(
        "--top-k",
        type=int,
        default=None,
        dest="top_k",
        help="Override reranker.output_k (final truncation only)",
    )
    retrieve_hybrid_rerank.add_argument(
        "--json",
        action="store_true",
        help="Emit HybridRerankRetrievalResult JSON",
    )
    retrieve_hybrid_rerank.set_defaults(func=cmd_retrieve_hybrid_rerank)

    retrieve_hybrid_rerank_context = retrieve_sub.add_parser(
        "hybrid-rerank-context",
        help="Hybrid-rerank followed by structural context expansion",
    )
    _add_config_argument(retrieve_hybrid_rerank_context)
    retrieve_hybrid_rerank_context.add_argument(
        "--corpus", default="default", help="Logical corpus name"
    )
    retrieve_hybrid_rerank_context.add_argument("--query", required=True, help="Query text")
    retrieve_hybrid_rerank_context.add_argument(
        "--json",
        action="store_true",
        help="Emit HybridRerankContextResult JSON",
    )
    retrieve_hybrid_rerank_context.set_defaults(func=cmd_retrieve_hybrid_rerank_context)

    query = subparsers.add_parser("query", help="Grounded answer generation with citations")
    _add_config_argument(query)
    query.add_argument("--corpus", default="default", help="Logical corpus name")
    query.add_argument("--query", required=True, help="Query text")
    query.add_argument("--json", action="store_true", help="Emit GroundedAnswerResult JSON")
    query.set_defaults(func=cmd_query)

    eval_parser = subparsers.add_parser("eval", help="Evaluation commands")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_run = eval_sub.add_parser("run", help="Run evaluation (not implemented yet)")
    _add_config_argument(eval_run)
    eval_run.set_defaults(func=cmd_eval_run)
    eval_compare = eval_sub.add_parser(
        "compare",
        help="Compare two offline-rag-retrieval-eval-result-v1 artifacts",
    )
    eval_compare.add_argument("--a", required=True, help="Baseline result JSON path")
    eval_compare.add_argument("--b", required=True, help="Candidate result JSON path")
    eval_compare.add_argument(
        "--json",
        action="store_true",
        help="Emit offline-rag-retrieval-eval-comparison-v1 JSON",
    )
    eval_compare.set_defaults(func=cmd_eval_compare)
    eval_query = eval_sub.add_parser("query", help="Run grounded query evaluation")
    _add_config_argument(eval_query)
    eval_query.add_argument("--dataset", required=True, type=Path, help="Dataset dir or cases.jsonl")
    eval_query.add_argument("--corpus", default="default", help="Logical corpus name")
    eval_query.add_argument("--output", type=Path, default=None, help="Optional result JSON path")
    eval_query.add_argument("--json", action="store_true", help="Emit evaluation result JSON")
    eval_query.set_defaults(func=cmd_eval_query)
    eval_retrieve = eval_sub.add_parser(
        "retrieve",
        help="Run dense or lexical retrieval evaluation",
    )
    _add_config_argument(eval_retrieve)
    eval_retrieve.add_argument("--dataset", required=True, type=Path, help="Dataset dir or cases.jsonl")
    eval_retrieve.add_argument("--corpus", default="default", help="Logical corpus name")
    eval_retrieve.add_argument(
        "--method",
        choices=("dense", "lexical", "hybrid", "hybrid-rerank", "hybrid-rerank-context"),
        default="dense",
        help="Retriever under test (default: dense)",
    )
    eval_retrieve.add_argument("--top-k", type=int, default=10, dest="top_k")
    eval_retrieve.add_argument("--output", type=Path, default=None, help="Optional result JSON path")
    eval_retrieve.add_argument("--json", action="store_true", help="Emit evaluation result JSON")
    eval_retrieve.set_defaults(func=cmd_eval_retrieve)

    gold_parser = subparsers.add_parser("gold", help="Offline gold-authoring commands")
    gold_sub = gold_parser.add_subparsers(dest="gold_command", required=True)
    gold_propose = gold_sub.add_parser(
        "propose",
        help=(
            "Sample source seeds and propose pending SilverCases via the local "
            "authoring model (Slice 9B)"
        ),
    )
    _add_config_argument(gold_propose)
    gold_propose.add_argument(
        "--corpus",
        required=True,
        help="Logical corpus name whose CURRENT ChunkSet will be sampled",
    )
    gold_propose.add_argument(
        "--count",
        type=int,
        default=20,
        help=(
            "Number of source seeds to sample and proposal attempts to make "
            "(default: 20)"
        ),
    )
    gold_propose.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Deterministic source-sampling seed (default: 0)",
    )
    gold_propose.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Optional authoring-run JSON path "
            "(default: <corpus>/gold_authoring/runs/<run_id>.json)"
        ),
    )
    gold_propose.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the exact output path if it already exists",
    )
    gold_propose.set_defaults(func=cmd_gold_propose)

    gold_pool = gold_sub.add_parser(
        "pool",
        help=(
            "Build candidate-pooling-v1 retrieval pools for pending SilverCases "
            "(Slice 9C)"
        ),
    )
    _add_config_argument(gold_pool)
    gold_pool.add_argument(
        "--run",
        required=True,
        type=Path,
        help="Path to an existing offline-rag-gold-authoring-v1 run JSON",
    )
    gold_pool.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Optional destination path for the enriched run "
            "(default: enrich --run in place)"
        ),
    )
    gold_pool.add_argument(
        "--force",
        action="store_true",
        help=(
            "Re-pool cases that already have candidates and/or overwrite an "
            "existing --output file"
        ),
    )
    gold_pool.set_defaults(func=cmd_gold_pool)

    gold_prelabel = gold_sub.add_parser(
        "prelabel",
        help=(
            "Blind double-pass local relevance prelabeling for pooled "
            "SilverCases (Slice 9D)"
        ),
    )
    _add_config_argument(gold_prelabel)
    gold_prelabel.add_argument(
        "--run",
        required=True,
        type=Path,
        help="Path to an existing pooled offline-rag-gold-authoring-v1 run JSON",
    )
    gold_prelabel.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Optional destination path for the enriched run "
            "(default: enrich --run in place)"
        ),
    )
    gold_prelabel.add_argument(
        "--force",
        action="store_true",
        help=(
            "Re-prelabel cases that already have complete durable prelabels "
            "and/or overwrite an existing --output file"
        ),
    )
    gold_prelabel.set_defaults(func=cmd_gold_prelabel)

    gold_review = gold_sub.add_parser(
        "review",
        help=(
            "Serve the localhost human-review UI for an authoring run "
            "(Slice 9E; in-place silver mutations)"
        ),
    )
    _add_config_argument(gold_review)
    gold_review.add_argument(
        "--run",
        required=True,
        type=Path,
        help="Human-review an existing gold-authoring run (in place)",
    )
    gold_review.add_argument(
        "--host",
        default="127.0.0.1",
        help="Review server bind host (loopback only; default: 127.0.0.1)",
    )
    gold_review.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Review server port (default: 8765)",
    )
    gold_review.set_defaults(func=cmd_gold_review)

    gold_finalize = gold_sub.add_parser(
        "finalize",
        help=(
            "Publish qualifying accepted/edited cases to offline-rag-gold-v1 "
            "(Slice 9E)"
        ),
    )
    _add_config_argument(gold_finalize)
    gold_finalize.add_argument(
        "--run",
        required=True,
        type=Path,
        help="Existing human-reviewed gold-authoring run",
    )
    gold_finalize.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Destination directory for the finalized offline-rag-gold-v1 dataset "
            "(default: <corpus>/gold_authoring/gold/<authoring_run_id>/)"
        ),
    )
    gold_finalize.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing destination GoldDataset artifact",
    )
    gold_finalize.set_defaults(func=cmd_gold_finalize)

    doctor = subparsers.add_parser("doctor", help="Run local diagnostics")
    _add_config_argument(doctor)
    doctor.add_argument("--corpus", default="default", help="Logical corpus name (default: default)")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
