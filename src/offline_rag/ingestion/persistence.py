"""Content-addressed ParsedDocument and corpus persistence."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.core.ids import artifact_bytes_hash
from offline_rag.domain.blocks import ParsedDocument
from offline_rag.domain.corpus import CorpusManifest, CorpusState
from offline_rag.ingestion.io import atomic_write_text


def processed_artifact_relpath(parsed_artifact_id: str) -> str:
    return f"processed/{parsed_artifact_id}.json"


def processed_artifact_path(processed_root: Path, parsed_artifact_id: str) -> Path:
    return processed_root / f"{parsed_artifact_id}.json"


def write_parsed_document(processed_root: Path, parsed: ParsedDocument) -> tuple[Path, str]:
    if not parsed.parsed_artifact_id:
        raise ValueError("parsed_artifact_id is required for persistence")
    path = processed_artifact_path(processed_root, parsed.parsed_artifact_id)
    payload = parsed.model_dump_json()
    data = payload.encode("utf-8")
    digest = artifact_bytes_hash(data)

    if path.exists():
        existing = path.read_bytes()
        existing_hash = artifact_bytes_hash(existing)
        if existing_hash != digest:
            # Same identity path but different bytes: integrity failure.
            raise RuntimeError(
                f"parsed artifact conflict at {path}: existing hash {existing_hash} "
                f"!= new hash {digest}"
            )
        return path, digest

    atomic_write_text(path, payload)
    return path, digest


def load_parsed_document(path: Path) -> ParsedDocument:
    return ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))


def try_load_reusable_artifact(
    processed_root: Path,
    parsed_artifact_id: str,
    *,
    expected_document_id: str,
    expected_parse_config_hash: str,
) -> tuple[ParsedDocument, str] | None:
    path = processed_artifact_path(processed_root, parsed_artifact_id)
    if not path.exists():
        return None
    try:
        parsed = load_parsed_document(path)
    except (OSError, ValueError, TypeError, ValidationError):
        return None
    if parsed.document.document_id != expected_document_id:
        return None
    if parsed.parse_config_hash != expected_parse_config_hash:
        return None
    if parsed.parsed_artifact_id != parsed_artifact_id:
        return None
    digest = artifact_bytes_hash(path.read_bytes())
    return parsed, digest


def write_corpus_manifest(manifests_root: Path, manifest: CorpusManifest) -> Path:
    path = manifests_root / f"{manifest.corpus_id}.json"
    if path.exists():
        existing = load_corpus_manifest(path)
        if (
            existing.corpus_id == manifest.corpus_id
            and existing.corpus_hash == manifest.corpus_hash
            and existing.config_hash == manifest.config_hash
            and existing.documents == manifest.documents
            and existing.parser_environment == manifest.parser_environment
        ):
            return path
        raise RuntimeError(f"manifest conflict for {manifest.corpus_id}")
    atomic_write_text(path, manifest.model_dump_json())
    return path


def load_corpus_manifest(path: Path) -> CorpusManifest:
    return CorpusManifest.model_validate_json(path.read_text(encoding="utf-8"))


def corpus_state_path(corpora_root: Path, corpus_name: str) -> Path:
    return corpora_root / corpus_name / "state.json"


def load_corpus_state(path: Path) -> CorpusState:
    return CorpusState.model_validate_json(path.read_text(encoding="utf-8"))


def write_corpus_state(path: Path, state: CorpusState) -> None:
    atomic_write_text(path, state.model_dump_json())
