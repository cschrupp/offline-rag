"""CLI for OfflineRAG."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from offline_rag.chunking.persistence import (
    chunk_state_path,
    load_chunk_artifact,
    load_chunk_set_manifest,
    load_chunk_state,
)
from offline_rag.chunking.pipeline import chunking_status_for_corpus, run_chunking
from offline_rag.chunking.tokenize import validate_tiktoken_artifacts
from offline_rag.config import ConfigError, load_settings
from offline_rag.config.models import AppSettings
from offline_rag.domain.chunking import ChunkingStatus
from offline_rag.domain.ingestion import IngestionStatus
from offline_rag.ingestion.discovery import DiscoveryError, validate_corpus_name
from offline_rag.ingestion.docling_artifacts import validate_docling_artifacts
from offline_rag.ingestion.persistence import corpus_state_path, load_corpus_state
from offline_rag.ingestion.pipeline import run_ingestion
from offline_rag.observability import configure_logging, log_event

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
                    "qdrant_storage": _resolve(settings.paths.qdrant_storage),
                    "retrieval_models": _resolve(settings.paths.retrieval_models),
                    "docling_artifacts": _resolve(settings.paths.docling_artifacts),
                    "tokenizer_artifacts": _resolve(settings.paths.tokenizer_artifacts),
                    "eval_results": _resolve(settings.paths.eval_results),
                }
            )
        }
    )


def _load_settings(args: argparse.Namespace) -> AppSettings:
    yaml_paths = args.config or [_default_config_path()]
    return _resolve_settings(load_settings(yaml_paths=yaml_paths))


def _not_implemented(command: str) -> int:
    print(
        f"offline-rag {command}: not implemented in this slice "
        "(deferred beyond Slice 2).",
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


def cmd_query(_args: argparse.Namespace) -> int:
    return _not_implemented("query")


def cmd_eval_run(_args: argparse.Namespace) -> int:
    return _not_implemented("eval run")


def cmd_eval_compare(_args: argparse.Namespace) -> int:
    return _not_implemented("eval compare")


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
        ("qdrant_storage", settings.paths.qdrant_storage),
        ("retrieval_models", settings.paths.retrieval_models),
        ("eval_results", settings.paths.eval_results),
    ]

    for name, path in path_fields:
        if not path.exists():
            if name in {"corpora", "processed", "manifests", "chunks", "chunk_manifests"}:
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

    query = subparsers.add_parser("query", help="Query the corpus (not implemented yet)")
    _add_config_argument(query)
    query.set_defaults(func=cmd_query)

    eval_parser = subparsers.add_parser("eval", help="Evaluation commands")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_run = eval_sub.add_parser("run", help="Run evaluation (not implemented yet)")
    _add_config_argument(eval_run)
    eval_run.set_defaults(func=cmd_eval_run)
    eval_compare = eval_sub.add_parser("compare", help="Compare evaluations (not implemented yet)")
    _add_config_argument(eval_compare)
    eval_compare.set_defaults(func=cmd_eval_compare)

    doctor = subparsers.add_parser("doctor", help="Run local diagnostics")
    _add_config_argument(doctor)
    doctor.add_argument("--corpus", default="default", help="Logical corpus name (default: default)")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
