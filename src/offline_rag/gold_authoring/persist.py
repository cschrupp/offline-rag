"""Authoring-run persistence paths and IO."""

from __future__ import annotations

from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.gold_authoring.models import GoldAuthoringRun
from offline_rag.ingestion.io import atomic_write_text


def default_authoring_runs_dir(settings: AppSettings, *, corpus_name: str) -> Path:
    return settings.paths.corpora / corpus_name / "gold_authoring" / "runs"


def default_authoring_run_path(
    settings: AppSettings,
    *,
    corpus_name: str,
    authoring_run_id: str,
) -> Path:
    return default_authoring_runs_dir(settings, corpus_name=corpus_name) / (
        f"{authoring_run_id}.json"
    )


def default_authoring_gold_dir(
    settings: AppSettings,
    *,
    corpus_name: str,
    authoring_run_id: str,
) -> Path:
    return (
        settings.paths.corpora
        / corpus_name
        / "gold_authoring"
        / "gold"
        / authoring_run_id
    )


def serialize_authoring_run_bytes(run: GoldAuthoringRun) -> bytes:
    """Exact UTF-8 JSON bytes used for hashing and atomic canonical writes."""
    return run.model_dump_json().encode("utf-8")


def write_authoring_run(path: Path, run: GoldAuthoringRun) -> None:
    atomic_write_text(path, run.model_dump_json())


def write_authoring_run_bytes(path: Path, payload: bytes) -> None:
    """Atomically write pre-serialized authoring-run bytes (hash/write identity)."""
    from offline_rag.ingestion.io import atomic_write_bytes

    atomic_write_bytes(path, payload)


def load_authoring_run(path: Path) -> GoldAuthoringRun:
    return GoldAuthoringRun.model_validate_json(path.read_text(encoding="utf-8"))
