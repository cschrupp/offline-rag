#!/usr/bin/env python3
"""Run one external 16K-F corpus cell against a dedicated Seneca API.

The runner uploads files in product-limit batches, waits on durable managed
operations, verifies publication/worklist/metrics, runs a private query deck,
and writes content-free JSON evidence. Real execution requires an explicit
authority string and a matching local data root for cache-state checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from scripts.diag_16k_f.prepare_corpus import (
    REPLACEMENT_MANIFEST_SCHEMA,
    PreparationError,
    validate_replacement_manifest,
    verify_replacement_manifest_files,
)

MiB = 1024 * 1024
MAX_FILES_PER_REQUEST = 32
MAX_BYTES_PER_REQUEST = 100 * MiB
MAX_PDF_BYTES = 90 * MiB
MAX_OTHER_BYTES = 25 * MiB
CACHE_DIR_NAMES = (
    "processed",
    "manifests",
    "corpora",
    "chunks",
    "chunk-manifests",
    "embeddings",
    "index-manifests",
    "lexical-indexes",
    "lexical-index-manifests",
    "qdrant",
    "workspaces",
)
WARM_CACHE_DIR_NAMES = ("processed", "chunks", "embeddings")
TERMINAL_STATUSES = {"succeeded", "failed", "interrupted"}
DEFAULT_CELL_WATCHDOG_SECONDS = 6 * 60 * 60
PRIMARY_CORPUS_MANIFEST_SCHEMA = "16k-f-primary-corpus-manifest-v1"
EXPECTED_PRIMARY_DOCUMENTS = 39
PREPARED_REPLACEMENT_MANIFEST_SHA256 = (
    "4d6d32c42d50e6753378d6f8dacc42b5fa0d3d18bdbdc4a9d4b4b3dfb000c92b"
)
PREPARED_REPLACEMENT_QUERY_DECK_FILE_SHA256 = (
    "f10da5270a440004de8cac9db7d3e4836f46a87613f4f2d8124b58479d0f717a"
)


class HarnessError(ValueError):
    """Raised when a manifest, execution precondition, or API result is invalid."""


@dataclass(frozen=True)
class SourceFile:
    relative_path: str
    byte_size: int
    media_type: str
    sha256: str


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_manifest_hash(manifest: dict[str, Any]) -> None:
    declared = manifest.get("manifest_sha256")
    if not isinstance(declared, str) or len(declared) != 64:
        raise HarnessError("manifest lacks a valid manifest_sha256")
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    actual = hashlib.sha256(_canonical_json(body)).hexdigest()
    if actual != declared:
        raise HarnessError("manifest hash does not match its contents")


def _manifest_source_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema") == "16k-f-primary-corpus-manifest-v1":
        if manifest.get("primary_document_count") != 39:
            raise HarnessError("primary corpus manifest must include 39 documents")
        rows = manifest.get("primary_sources")
    elif manifest.get("schema") == REPLACEMENT_MANIFEST_SCHEMA:
        try:
            rows = validate_replacement_manifest(manifest)
        except PreparationError as exc:
            raise HarnessError(str(exc)) from exc
    elif manifest.get("schema") == "16k-f-single-source-manifest-v1":
        if manifest.get("source_count") != 1:
            raise HarnessError("single-source manifest must contain exactly one source")
        source = manifest.get("source")
        rows = [source] if isinstance(source, dict) else None
    elif manifest.get("schema_version") == "offline-rag-corpus-manifest-v1":
        parser_environment = manifest.get("parser_environment")
        if (
            not isinstance(parser_environment, dict)
            or parser_environment.get("ocr_enabled") is not False
        ):
            raise HarnessError("proxy corpus must be frozen with OCR disabled")
        rows = manifest.get("documents")
    else:
        raise HarnessError("unsupported source manifest schema")
    if not isinstance(rows, list) or not rows:
        raise HarnessError("manifest must contain at least one source")
    return rows


def load_sources(
    corpus_root: Path, manifest_path: Path
) -> tuple[list[SourceFile], str]:
    """Verify source identities from either a 16K-F or accepted corpus manifest."""
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if "manifest_sha256" in manifest:
        _verify_manifest_hash(manifest)

    root = corpus_root.resolve(strict=True)
    if manifest.get("schema") == REPLACEMENT_MANIFEST_SCHEMA:
        try:
            verify_replacement_manifest_files(root, manifest)
        except PreparationError as exc:
            raise HarnessError(str(exc)) from exc
    inventory: dict[str, list[Path]] = {}
    hash_index: dict[str, list[Path]] | None = None
    sources: list[SourceFile] = []
    for row in _manifest_source_rows(manifest):
        relative_path = row.get("relative_path") or row.get("source_path")
        expected_size = row.get("byte_size", row.get("source_size_bytes"))
        expected_hash = row.get("sha256", row.get("source_content_hash"))
        media_type = row.get("media_type", row.get("source_media_type"))
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            raise HarnessError("manifest source identity is incomplete")
        if not isinstance(expected_size, int) or expected_size < 0:
            raise HarnessError("manifest source size is invalid")
        candidate = Path(relative_path)
        if not candidate.is_absolute() and ".." not in candidate.parts:
            possible = root / candidate
            if possible.is_file():
                resolved = possible.resolve()
                if resolved.is_relative_to(root):
                    inventory.setdefault(expected_hash, []).append(resolved)

        # Historical proxy corpus manifests may retain obsolete absolute paths.
        # Recover only by exact content hash and require a unique match.
        matches = inventory.get(expected_hash, [])
        if not matches:
            if hash_index is None:
                hash_index = {}
                for path in root.rglob("*"):
                    if path.is_file() and _media_type_for_path(path) != (
                        "application/octet-stream"
                    ):
                        digest = _sha256_path(path)
                        hash_index.setdefault(digest, []).append(path.resolve())
            inventory.update(hash_index)
            matches = inventory.get(expected_hash, [])
        source_name = row.get("source_name")
        if isinstance(source_name, str) and len(matches) > 1:
            matching_names = [path for path in matches if path.name == source_name]
            if matching_names:
                matches = matching_names
        unique_matches = sorted(set(matches))
        if len(unique_matches) != 1:
            raise HarnessError(
                "source identity must resolve to exactly one file in corpus root"
            )
        path = unique_matches[0]
        if path.stat().st_size != expected_size or _sha256_path(path) != expected_hash:
            raise HarnessError("source changed after manifest creation")
        authoritative_media_type = _media_type_for_path(path)
        if authoritative_media_type == "application/octet-stream":
            raise HarnessError("source extension is outside supported upload types")
        if isinstance(media_type, str) and media_type != authoritative_media_type:
            raise HarnessError("manifest media type disagrees with source extension")
        media_type = authoritative_media_type
        limit = MAX_PDF_BYTES if media_type == "application/pdf" else MAX_OTHER_BYTES
        if expected_size > limit:
            raise HarnessError("source exceeds its active per-file transport limit")
        sources.append(
            SourceFile(
                relative_path=path.relative_to(root).as_posix(),
                byte_size=expected_size,
                media_type=media_type,
                sha256=expected_hash,
            )
        )

    sources.sort(key=lambda source: source.relative_path)
    if len({source.sha256 for source in sources}) != len(sources):
        raise HarnessError("manifest contains duplicate source byte identities")
    manifest_hash = manifest.get("manifest_sha256")
    if not isinstance(manifest_hash, str):
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    return sources, manifest_hash


def verify_replacement_execution_artifact_pins(
    manifest_path: Path,
    query_deck_path: Path,
    *,
    approved_manifest_sha256: str | None,
    approved_query_deck_file_sha256: str | None,
) -> dict[str, str]:
    """Require the prepared replacement bytes and authority pins before execution."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        query_deck = json.loads(query_deck_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError("replacement manifest or query deck is unreadable") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != REPLACEMENT_MANIFEST_SCHEMA
    ):
        raise HarnessError("artifact pinning applies only to replacement manifests")
    if not isinstance(query_deck, dict):
        raise HarnessError("replacement query deck must be a JSON object")
    _verify_manifest_hash(manifest)
    manifest_sha256 = manifest["manifest_sha256"]
    query_deck_sha256 = _sha256_path(query_deck_path)
    if manifest_sha256 != PREPARED_REPLACEMENT_MANIFEST_SHA256:
        raise HarnessError("replacement manifest differs from the prepared baseline")
    if query_deck_sha256 != PREPARED_REPLACEMENT_QUERY_DECK_FILE_SHA256:
        raise HarnessError("replacement query deck differs from the prepared baseline")
    if approved_manifest_sha256 != manifest_sha256:
        raise HarnessError("execution authority manifest digest does not match")
    if approved_query_deck_file_sha256 != query_deck_sha256:
        raise HarnessError("execution authority query-deck digest does not match")
    if query_deck.get("corpus_candidate_sha256") != manifest_sha256:
        raise HarnessError("query deck is not bound to the replacement manifest")
    return {
        "manifest_sha256": manifest_sha256,
        "query_deck_file_sha256": query_deck_sha256,
    }


def _media_type_for_path(path: Path) -> str:
    return {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
    }.get(path.suffix.lower(), "application/octet-stream")


def validate_capabilities(
    capabilities: dict[str, Any], sources: list[SourceFile]
) -> dict[str, Any]:
    """Require accepted transport limits and eligible profile admission."""
    transport = capabilities.get("transport_limits")
    workspace = capabilities.get("workspace_capacity")
    large_pdf = capabilities.get("large_pdf")
    embedding = capabilities.get("embedding")
    if not all(isinstance(item, dict) for item in (transport, workspace, large_pdf)):
        raise HarnessError("capabilities response lacks capacity projections")
    if transport.get("max_files_per_upload_request") != MAX_FILES_PER_REQUEST:
        raise HarnessError("active max-files limit differs from accepted envelope")
    if transport.get("max_bytes_per_upload_request") != MAX_BYTES_PER_REQUEST:
        raise HarnessError("active request-byte limit differs from accepted envelope")
    if transport.get("max_bytes_per_uploaded_file") != MAX_OTHER_BYTES:
        raise HarnessError("active non-PDF file limit differs from accepted policy")

    pdf_sizes = [
        source.byte_size for source in sources if source.media_type == "application/pdf"
    ]
    largest_pdf_bytes = max(pdf_sizes, default=0)
    if largest_pdf_bytes > MAX_OTHER_BYTES:
        if (
            large_pdf.get("runtime_eligible") is not True
            or large_pdf.get("effective_max_bytes", 0) < largest_pdf_bytes
        ):
            raise HarnessError("active runtime cannot admit the largest PDF source")
        qualified = large_pdf.get("qualified_profiles")
        active_profile = (
            embedding.get("profile_id") if isinstance(embedding, dict) else None
        )
        if not isinstance(qualified, list) or active_profile not in qualified:
            raise HarnessError("active embedding profile is not large-PDF qualified")

    total_bytes = sum(source.byte_size for source in sources)
    aggregate_byte_limit = workspace.get("max_active_source_bytes")
    if aggregate_byte_limit is not None and total_bytes > aggregate_byte_limit:
        raise HarnessError("manifest exceeds the active workspace byte ceiling")
    source_count_limit = workspace.get("max_active_sources")
    if source_count_limit is not None and len(sources) > source_count_limit:
        raise HarnessError("manifest exceeds the active workspace source-count ceiling")
    return {
        "max_files_per_upload_request": transport["max_files_per_upload_request"],
        "max_bytes_per_uploaded_file": transport["max_bytes_per_uploaded_file"],
        "max_bytes_per_upload_request": transport["max_bytes_per_upload_request"],
        "workspace_max_active_source_bytes": aggregate_byte_limit,
        "workspace_max_active_sources": source_count_limit,
        "large_pdf_runtime_eligible": large_pdf.get("runtime_eligible"),
        "large_pdf_effective_max_bytes": large_pdf.get("effective_max_bytes"),
        "active_profile_id": (
            embedding.get("profile_id") if isinstance(embedding, dict) else None
        ),
    }


def batch_sources(
    sources: list[SourceFile],
    *,
    max_files: int = MAX_FILES_PER_REQUEST,
    max_bytes: int = MAX_BYTES_PER_REQUEST,
) -> list[list[SourceFile]]:
    """Group files within the API's request count and raw-byte envelope."""
    batches: list[list[SourceFile]] = []
    current: list[SourceFile] = []
    current_bytes = 0
    for source in sources:
        if source.byte_size > max_bytes:
            raise HarnessError("one source exceeds the request byte envelope")
        if current and (
            len(current) >= max_files or current_bytes + source.byte_size > max_bytes
        ):
            batches.append(current)
            current = []
            current_bytes = 0
        current.append(source)
        current_bytes += source.byte_size
    if current:
        batches.append(current)
    return batches


def check_cache_state(data_root: Path, cache_state: str) -> None:
    """Fail closed unless a declared cold/warm local data root is plausible."""
    root = data_root.resolve()
    observed: list[Path] = []
    for dirname in CACHE_DIR_NAMES:
        path = root / dirname
        if path.exists():
            observed.extend(item for item in path.rglob("*") if item.is_file())
    if cache_state == "cold" and observed:
        raise HarnessError("cold cell data root contains prior runtime artifacts")
    if cache_state == "warm":
        missing = [
            dirname
            for dirname in WARM_CACHE_DIR_NAMES
            if not any(path.is_file() for path in (root / dirname).rglob("*"))
        ]
        if missing:
            raise HarnessError(
                "warm cell data root lacks required cache state: " + ", ".join(missing)
            )


def _safe_metrics(operation: dict[str, Any]) -> dict[str, Any] | None:
    metrics = operation.get("metrics")
    if not isinstance(metrics, dict):
        return None
    allowed = {
        "requested_document_count",
        "pre_active_source_count",
        "post_active_source_count",
        "uploaded_raw_bytes",
        "parsed_searchable_document_count",
        "child_chunk_count",
        "parsed_artifacts_generated",
        "parsed_artifacts_reused",
        "chunk_artifacts_generated",
        "chunk_artifacts_reused",
        "embeddings_generated",
        "embeddings_reused",
        "embeddings_failed",
        "generated_chunks_per_sec",
        "model_input_tokens_per_sec",
        "stage_durations",
        "lexical",
        "dense_execution",
    }
    return {key: metrics[key] for key in sorted(allowed) if key in metrics}


def _safe_operation(operation: dict[str, Any]) -> dict[str, Any]:
    worklist = operation.get("worklist")
    safe_worklist = None
    if isinstance(worklist, dict):
        safe_worklist = {
            key: worklist.get(key)
            for key in (
                "total_document_count",
                "pending_count",
                "completed_count",
                "remaining_count",
            )
            if key in worklist
        }
    result = operation.get("result")
    safe_result = None
    if isinstance(result, dict):
        safe_result = {
            key: result[key]
            for key in (
                "workspace_revision",
                "workspace_status",
                "snapshot_id",
                "source_count",
            )
            if key in result
        }
    error = operation.get("error")
    safe_error = None
    if isinstance(error, dict):
        safe_error = {key: error[key] for key in ("code", "retryable") if key in error}
    return {
        "operation_id": operation.get("operation_id"),
        "kind": operation.get("kind"),
        "status": operation.get("status"),
        "progress_stage": operation.get("progress_stage"),
        "progress": operation.get("progress"),
        "metrics": _safe_metrics(operation),
        "worklist": safe_worklist,
        "result": safe_result,
        "error": safe_error,
    }


def _validate_operation_metrics(
    operation: dict[str, Any],
    *,
    expected_source_count: int,
    expected_requested_document_count: int,
    expected_uploaded_raw_bytes: int,
) -> None:
    metrics = operation.get("metrics")
    if not isinstance(metrics, dict):
        raise HarnessError("terminal operation omitted metrics")
    if metrics.get("post_active_source_count") != expected_source_count:
        raise HarnessError("operation metrics report an incorrect active source count")
    if metrics.get("requested_document_count") != expected_requested_document_count:
        raise HarnessError(
            "operation metrics report an incorrect request document count"
        )
    if metrics.get("uploaded_raw_bytes") != expected_uploaded_raw_bytes:
        raise HarnessError("operation metrics report incorrect uploaded raw bytes")
    stage_durations = metrics.get("stage_durations")
    required_stages = (
        "parsing_ms",
        "chunking_ms",
        "dense_generation_ms",
        "dense_materialization_ms",
        "lexical_ms",
        "publication_ms",
        "finalization_ms",
        "total_ms",
    )
    if not isinstance(stage_durations, dict) or any(
        type(stage_durations.get(field)) is not int or stage_durations[field] < 0
        for field in required_stages
    ):
        raise HarnessError("terminal operation omitted stage durations")
    if stage_durations["total_ms"] < max(
        stage_durations[field] for field in required_stages if field != "total_ms"
    ):
        raise HarnessError("stage duration exceeds total operation duration")
    for field in (
        "requested_document_count",
        "uploaded_raw_bytes",
        "child_chunk_count",
        "parsed_artifacts_generated",
        "parsed_artifacts_reused",
        "chunk_artifacts_generated",
        "chunk_artifacts_reused",
        "embeddings_generated",
        "embeddings_reused",
        "embeddings_failed",
    ):
        value = metrics.get(field)
        if value is not None and (type(value) is not int or value < 0):
            raise HarnessError(f"operation metric {field} is invalid")


def _sum_operation_metrics(operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum measurements across the executed mutation sequence, without claiming
    that repeated workspace rebuild measurements represent unique documents.
    """
    counter_fields = (
        "uploaded_raw_bytes",
        "child_chunk_count",
        "parsed_artifacts_generated",
        "parsed_artifacts_reused",
        "chunk_artifacts_generated",
        "chunk_artifacts_reused",
        "embeddings_generated",
        "embeddings_reused",
        "embeddings_failed",
    )
    stage_fields = (
        "parsing_ms",
        "chunking_ms",
        "dense_generation_ms",
        "dense_materialization_ms",
        "lexical_ms",
        "publication_ms",
        "finalization_ms",
        "total_ms",
    )
    totals: dict[str, Any] = {}
    for field in counter_fields:
        values = [
            operation["metrics"][field]
            for operation in operations
            if isinstance(operation.get("metrics"), dict)
            and isinstance(operation["metrics"].get(field), int)
        ]
        totals[field] = sum(values) if values else None
    stage_totals: dict[str, int | None] = {}
    for field in stage_fields:
        values = [
            operation["metrics"]["stage_durations"][field]
            for operation in operations
            if isinstance(operation.get("metrics"), dict)
            and isinstance(operation["metrics"].get("stage_durations"), dict)
            and isinstance(operation["metrics"]["stage_durations"].get(field), int)
        ]
        stage_totals[field] = sum(values) if values else None
    totals["stage_durations_ms"] = stage_totals
    totals["interpretation"] = "sum_of_operation_measurements_including_rebuilds"
    return totals


def compare_cold_warm(
    cold: dict[str, Any],
    warm: dict[str, Any],
    *,
    cold_evidence_sha256: str,
) -> dict[str, Any]:
    """Compare paired full-corpus cells without imposing an unfrozen materiality
    threshold. The result reports reductions; reviewers apply accepted criteria.
    """
    if cold.get("source_identity_sha256") != warm.get("source_identity_sha256"):
        raise HarnessError("cold and warm source identities do not match")
    if (
        not isinstance(cold.get("source_identity_sha256"), str)
        or not cold["source_identity_sha256"]
    ):
        raise HarnessError("paired cells lack source identity")
    if cold.get("manifest_sha256") != warm.get("manifest_sha256"):
        raise HarnessError("cold and warm manifests do not match")
    if not isinstance(cold.get("manifest_sha256"), str) or not cold["manifest_sha256"]:
        raise HarnessError("paired cells lack manifest identity")
    if cold.get("source_count_expected") != warm.get("source_count_expected"):
        raise HarnessError("cold and warm source counts do not match")
    if (
        not isinstance(cold.get("source_count_expected"), int)
        or cold["source_count_expected"] <= 0
    ):
        raise HarnessError("paired cells lack a valid expected source count")
    if (
        cold.get("campaign_status") != "COMPLETE"
        or warm.get("campaign_status") != "COMPLETE"
    ):
        raise HarnessError("paired cells must both be complete")
    if cold.get("cache_state") != "cold" or warm.get("cache_state") != "warm":
        raise HarnessError("paired cache states must be cold then warm")
    if not cold.get("pair_run_id") or cold.get("pair_run_id") != warm.get(
        "pair_run_id"
    ):
        raise HarnessError("cold and warm cells are not from the same pair run")
    if cold.get("pair_sequence") != 1 or warm.get("pair_sequence") != 2:
        raise HarnessError("cold and warm cells are not in immediate pair order")
    data_root_id = cold.get("data_root_id")
    if (
        not isinstance(data_root_id, str)
        or len(data_root_id) != 64
        or data_root_id != warm.get("data_root_id")
    ):
        raise HarnessError("cold and warm cells used different data roots")
    if (
        not isinstance(cold_evidence_sha256, str)
        or len(cold_evidence_sha256) != 64
        or any(
            character not in "0123456789abcdef" for character in cold_evidence_sha256
        )
    ):
        raise HarnessError("cold evidence hash is invalid")
    if warm.get("predecessor_evidence_sha256") != cold_evidence_sha256:
        raise HarnessError("warm cell does not reference the exact cold evidence")
    try:
        cold_completed = datetime.fromisoformat(cold["completed_at"])
        warm_started = datetime.fromisoformat(warm["started_at"])
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise HarnessError("paired cells lack valid ordering timestamps") from exc
    if cold_completed.tzinfo is None or warm_started.tzinfo is None:
        raise HarnessError("paired cell timestamps must include a timezone")
    if warm_started < cold_completed:
        raise HarnessError("warm cell started before cold cell completed")
    cold_totals = cold.get("aggregate_metrics")
    warm_totals = warm.get("aggregate_metrics")
    if not isinstance(cold_totals, dict) or not isinstance(warm_totals, dict):
        raise HarnessError("paired cells lack aggregate metrics")
    reductions: dict[str, Any] = {}
    metrics = (
        "parsed_artifacts_generated",
        "chunk_artifacts_generated",
        "embeddings_generated",
        "stage_durations_ms.dense_generation_ms",
        "stage_durations_ms.total_ms",
    )
    for metric in metrics:
        cold_value = _nested_metric(cold_totals, metric)
        warm_value = _nested_metric(warm_totals, metric)
        reductions[metric] = {
            "cold": cold_value,
            "warm": warm_value,
            "absolute_reduction": (
                cold_value - warm_value
                if isinstance(cold_value, int) and isinstance(warm_value, int)
                else None
            ),
            "fractional_reduction": (
                (cold_value - warm_value) / cold_value
                if isinstance(cold_value, int)
                and isinstance(warm_value, int)
                and cold_value > 0
                else None
            ),
        }
    return {
        "schema": "16k-f-cold-warm-comparison-v1",
        "source_identity_sha256": cold["source_identity_sha256"],
        "cold_cell_id": cold.get("cell_id"),
        "warm_cell_id": warm.get("cell_id"),
        "same_data_root": True,
        "warm_follows_cold_evidence": True,
        "cold_completed_at": cold["completed_at"],
        "warm_started_at": warm["started_at"],
        "reductions": reductions,
        "materiality_disposition": "REVIEW_AGAINST_ACCEPTED_CRITERIA",
    }


def validate_robustness_case_evidence(record: dict[str, Any]) -> dict[str, Any]:
    """Validate sanitized manual/API evidence for one expected rejection case."""
    if record.get("schema") != "16k-f-robustness-case-evidence-v1":
        raise HarnessError("unsupported robustness evidence schema")
    category = record.get("expected_failure_category")
    allowed_reasons = {
        "oversized": {"source_file_too_large"},
        "ocr_required": {
            "ocr_required",
            "ocr_required_while_ocr_disabled",
            "zero_searchable_text",
        },
        "duplicate": {"document_identity_conflict"},
    }
    if category not in allowed_reasons:
        raise HarnessError("robustness evidence failure category is invalid")
    case_id = record.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise HarnessError("robustness evidence case ID is invalid")

    input_hashes = record.get("input_source_sha256s")
    if (
        not isinstance(input_hashes, list)
        or not input_hashes
        or any(
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            for digest in input_hashes
        )
    ):
        raise HarnessError("robustness evidence source identities are invalid")

    before = record.get("before")
    after = record.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise HarnessError("robustness evidence lacks pre/post workspace state")
    for state in (before, after):
        if (
            type(state.get("revision")) is not int
            or state["revision"] < 1
            or type(state.get("source_count")) is not int
            or state["source_count"] < 0
            or not isinstance(state.get("snapshot_id"), str)
            or not isinstance(state.get("source_identity_sha256"), str)
            or len(state["source_identity_sha256"]) != 64
            or any(
                char not in "0123456789abcdef"
                for char in state["source_identity_sha256"]
            )
        ):
            raise HarnessError("robustness workspace-state record is invalid")
    if any(
        before[field] != after[field]
        for field in (
            "revision",
            "snapshot_id",
            "source_count",
            "source_identity_sha256",
        )
    ):
        raise HarnessError("rejected mutation changed the published workspace")
    if record.get("readiness_http_status") != 200:
        raise HarnessError("API readiness did not remain healthy after rejection")

    rejection = record.get("rejection")
    if not isinstance(rejection, dict):
        raise HarnessError("robustness evidence lacks rejection outcome")
    http_status = rejection.get("http_status")
    operation_status = rejection.get("operation_status")
    if not (
        type(http_status) is int
        and 400 <= http_status < 500
        and operation_status is None
    ) and not (
        type(http_status) is int and http_status == 202 and operation_status == "failed"
    ):
        raise HarnessError(
            "request was not rejected at admission or managed-operation stage"
        )
    if rejection.get("safe_error_code") not in {"document_invalid", "request_invalid"}:
        raise HarnessError("rejection did not expose an expected safe error code")
    observed_reason = rejection.get("reason")
    if observed_reason not in allowed_reasons[category]:
        raise HarnessError("rejection reason does not match the expected category")

    retry = record.get("retry")
    retry_required = record.get("retry_required") is True
    if retry_required:
        if not isinstance(retry, dict) or retry.get("status") != "succeeded":
            raise HarnessError("valid subsequent retry did not succeed")
        if retry.get("readiness_http_status") != 200:
            raise HarnessError("API readiness failed after valid retry")
        if (
            type(retry.get("revision")) is not int
            or retry["revision"] != before["revision"] + 1
        ):
            raise HarnessError("successful retry did not advance exactly one revision")
        if (
            type(retry.get("source_count")) is not int
            or retry["source_count"] != before["source_count"] + 1
        ):
            raise HarnessError("successful retry published an unexpected source count")
        retry_identity = retry.get("source_identity_sha256")
        if (
            not isinstance(retry_identity, str)
            or len(retry_identity) != 64
            or any(char not in "0123456789abcdef" for char in retry_identity)
            or retry_identity == before["source_identity_sha256"]
        ):
            raise HarnessError("successful retry did not change source identity")
    elif retry is not None:
        raise HarnessError("unexpected retry evidence for a case without a retry")

    return {
        "schema": "16k-f-robustness-case-summary-v1",
        "case_id": case_id,
        "expected_failure_category": category,
        "input_source_count": len(input_hashes),
        "rejection_http_status": http_status,
        "operation_status": operation_status,
        "safe_error_code": rejection["safe_error_code"],
        "reason": observed_reason,
        "publication_unchanged": True,
        "readiness_http_status": 200,
        "retry_status": retry.get("status") if retry_required else None,
        "retry_revision": retry.get("revision") if retry_required else None,
        "validation_status": "PASS",
    }


def _nested_metric(metrics: dict[str, Any], dotted_path: str) -> Any:
    value: Any = metrics
    for segment in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(segment)
    return value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _data_root_id(data_root: Path) -> str:
    return hashlib.sha256(str(data_root.resolve()).encode("utf-8")).hexdigest()


def _validate_query_result(
    result: dict[str, Any],
    active_sources: list[dict[str, Any]],
    *,
    expected_revision: int,
    expected_snapshot_id: str,
) -> dict[str, Any]:
    """Require a grounded answer whose citations map to published sources."""
    if result.get("status") != "answered":
        raise HarnessError("query did not return a grounded answered status")
    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise HarnessError("grounded query response omitted its answer")
    if result.get("workspace_revision") != expected_revision:
        raise HarnessError("query result is bound to a different workspace revision")
    if result.get("snapshot_id") != expected_snapshot_id:
        raise HarnessError("query result is bound to a different published snapshot")
    source_docs = {
        source.get("source_id"): source.get("document_id")
        for source in active_sources
        if isinstance(source.get("source_id"), str)
        and isinstance(source.get("document_id"), str)
    }
    citations = result.get("citations")
    if not isinstance(citations, list) or not citations:
        raise HarnessError("grounded query response has no citations")
    citation_refs: set[str] = set()
    for citation in citations:
        if not isinstance(citation, dict):
            raise HarnessError("query citation is malformed")
        source_id = citation.get("source_id")
        if not isinstance(source_id, str) or source_id not in source_docs:
            raise HarnessError("query citation does not map to an active source")
        if citation.get("document_id") != source_docs[source_id]:
            raise HarnessError("query citation document does not match its source")
        for field in ("evidence_unit_id", "source_chunk_id"):
            if not isinstance(citation.get(field), str) or not citation[field]:
                raise HarnessError("query citation lacks stable evidence identity")
        if citation.get("kind") not in {"parent", "child"}:
            raise HarnessError("query citation has an invalid evidence kind")
        if (
            not isinstance(citation.get("excerpt"), str)
            or not citation["excerpt"].strip()
        ):
            raise HarnessError("query citation lacks a useful excerpt")
        citation_ref = citation.get("citation_ref")
        if not isinstance(citation_ref, str) or not citation_ref:
            raise HarnessError("query citation lacks its public reference")
        if citation_ref in citation_refs:
            raise HarnessError("query response repeats a citation reference")
        citation_refs.add(citation_ref)

    answer_blocks = result.get("answer_blocks")
    if not isinstance(answer_blocks, list) or not answer_blocks:
        raise HarnessError("grounded query response has no answer blocks")
    for block in answer_blocks:
        if not isinstance(block, dict):
            raise HarnessError("query answer block is malformed")
        if not isinstance(block.get("text"), str) or not block["text"].strip():
            raise HarnessError("query answer block is empty")
        references = block.get("citation_refs")
        if (
            not isinstance(references, list)
            or not references
            or any(not isinstance(reference, str) for reference in references)
            or not set(references).issubset(citation_refs)
        ):
            raise HarnessError("answer block lacks valid citation references")
    return {
        "status": "answered",
        "citation_count": len(citations),
        "answer_block_count": len(answer_blocks),
        "valid_source_mappings": True,
        "valid_answer_block_references": True,
    }


def _write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_cell(
    *,
    base_url: str,
    corpus_root: Path,
    manifest_path: Path,
    query_deck_path: Path,
    data_root: Path,
    cache_state: str,
    cell_id: str,
    authority: str,
    output_path: Path,
    poll_seconds: float = 2.0,
    cell_watchdog_seconds: int = DEFAULT_CELL_WATCHDOG_SECONDS,
    approved_manifest_sha256: str | None = None,
    approved_query_deck_file_sha256: str | None = None,
    pair_run_id: str | None = None,
    pair_sequence: int | None = None,
    predecessor_evidence_sha256: str | None = None,
    client: httpx.Client | None = None,
    reconnect_client_factory: Any = None,
) -> dict[str, Any]:
    """Execute one source-set cell via durable workspace API operations."""
    if output_path.exists():
        raise HarnessError("refusing to overwrite existing 16K-F evidence")
    started_at = _utc_now()
    evidence: dict[str, Any] = {
        "schema": "16k-f-cell-evidence-v1",
        "cell_id": cell_id,
        "execution_authority": authority,
        "cache_state": cache_state,
        "data_root_id": _data_root_id(data_root),
        "pair_run_id": pair_run_id,
        "pair_sequence": pair_sequence,
        "predecessor_evidence_sha256": predecessor_evidence_sha256,
        "started_at": started_at,
        "operational_watchdog_seconds": cell_watchdog_seconds,
        "watchdog_semantics": "safety_stop_only_no_operation_cancellation",
        "campaign_status": "PREPARING",
        "operations": [],
        "queries": [],
    }
    own_client = client is None
    start_time = time.monotonic()
    campaign_deadline = start_time + cell_watchdog_seconds
    active_client: httpx.Client | None = None
    try:
        if poll_seconds <= 0:
            raise HarnessError("poll interval must be positive")
        if cell_watchdog_seconds <= 0:
            raise HarnessError("cell watchdog must be positive")
        check_cache_state(data_root, cache_state)
        sources, manifest_hash = load_sources(corpus_root, manifest_path)
        batches = batch_sources(sources)
        query_deck = json.loads(query_deck_path.read_text(encoding="utf-8"))
        questions = query_deck.get("questions")
        if not isinstance(questions, list) or not questions:
            raise HarnessError("query deck must contain at least one question")
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        execution_artifact_pins: dict[str, str] | None = None
        if manifest_data.get("schema") == REPLACEMENT_MANIFEST_SCHEMA:
            execution_artifact_pins = verify_replacement_execution_artifact_pins(
                manifest_path,
                query_deck_path,
                approved_manifest_sha256=approved_manifest_sha256,
                approved_query_deck_file_sha256=approved_query_deck_file_sha256,
            )
            if query_deck.get("corpus_candidate_sha256") != manifest_hash:
                raise HarnessError(
                    "query deck is not bound to the replacement manifest"
                )
            active_hashes = {source.sha256 for source in sources}
            if any(
                not isinstance(question, dict)
                or question.get("target_source_sha256") not in active_hashes
                for question in questions
            ):
                raise HarnessError(
                    "replacement query deck targets a source outside the eligible population"
                )
        evidence.update(
            {
                "manifest_sha256": manifest_hash,
                "source_count_expected": len(sources),
                "source_identity_sha256": hashlib.sha256(
                    "\n".join(sorted(item.sha256 for item in sources)).encode("ascii")
                ).hexdigest(),
                "upload_batch_count": len(batches),
                "campaign_status": "RUNNING",
            }
        )
        if manifest_data.get("schema") == REPLACEMENT_MANIFEST_SCHEMA:
            evidence["workload_comparability"] = manifest_data["workload_comparability"]
            evidence["threshold_measurement_disposition"] = (
                "NOT_COMPARABLE_TO_HISTORICAL_39_PRIMARY_THRESHOLD_POPULATION"
            )
            evidence["execution_artifact_pins"] = execution_artifact_pins
        _write_evidence(output_path, evidence)

        active_client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(connect=10, read=60, write=3600, pool=10),
        )
        ready = active_client.get("/health/ready")
        ready.raise_for_status()
        capability_response = active_client.get("/v1/capabilities")
        capability_response.raise_for_status()
        capability_summary = validate_capabilities(capability_response.json(), sources)
        created = active_client.post(
            "/v1/workspaces",
            headers={"Idempotency-Key": f"16kf-{cell_id}-{uuid.uuid4().hex}"},
            json={"title": f"16K-F {cell_id}", "description": "Acceptance cell"},
        )
        created.raise_for_status()
        workspace = created.json()
        workspace_id = workspace["workspace_id"]
        revision = int(workspace["revision"])
        persisted_workspace = data_root / "workspaces" / workspace_id / "workspace.json"
        if not persisted_workspace.is_file():
            raise HarnessError(
                "API workspace does not appear under the declared data root; "
                "check OFFLINE_RAG_DATA_DIR"
            )
        persisted_record = json.loads(persisted_workspace.read_text(encoding="utf-8"))
        if persisted_record.get("workspace_id") != workspace_id:
            raise HarnessError("declared data root contains a mismatched workspace")
        evidence["workspace"] = {
            "workspace_id": workspace_id,
            "initial_revision": revision,
        }
        _write_evidence(output_path, evidence)

        for batch_number, batch in enumerate(batches, start=1):
            headers = {
                "Idempotency-Key": f"16kf-{cell_id}-{batch_number}-{uuid.uuid4().hex}",
                "If-Match": f'"{revision}"',
            }
            with ExitStack() as stack:
                files = []
                for source in batch:
                    source_path = (corpus_root / source.relative_path).resolve(
                        strict=True
                    )
                    if not source_path.is_relative_to(corpus_root.resolve()):
                        raise HarnessError("source path escaped corpus root")
                    handle = stack.enter_context(source_path.open("rb"))
                    files.append(
                        ("files", (source_path.name, handle, source.media_type))
                    )
                accepted = active_client.post(
                    f"/v1/workspaces/{workspace_id}/sources",
                    headers=headers,
                    files=files,
                )
            if accepted.status_code != 202:
                accepted.raise_for_status()
                raise HarnessError("SOURCE_ADD did not return HTTP 202")
            operation_id = accepted.json().get("operation_id")
            if not isinstance(operation_id, str):
                raise HarnessError("accepted SOURCE_ADD omitted operation_id")

            operation_slot = {
                "operation_id": operation_id,
                "batch_number": batch_number,
                "status": "pending",
                "reconnect_verified": False,
            }
            evidence["operations"].append(operation_slot)
            _write_evidence(output_path, evidence)
            while True:
                active_client.get("/health/ready").raise_for_status()
                current = active_client.get(f"/v1/operations/{operation_id}")
                current.raise_for_status()
                operation = current.json()
                status = operation.get("status")
                operation_slot.update(_safe_operation(operation))
                operation_slot["batch_number"] = batch_number
                _write_evidence(output_path, evidence)
                if status in TERMINAL_STATUSES:
                    break
                if time.monotonic() >= campaign_deadline:
                    operation_slot["watchdog_expired"] = True
                    _write_evidence(output_path, evidence)
                    raise HarnessError(
                        "operation watchdog expired; no cancellation sent"
                    )
                time.sleep(poll_seconds)

            reconnect_client = (
                reconnect_client_factory()
                if reconnect_client_factory is not None
                else httpx.Client(
                    base_url=base_url.rstrip("/"),
                    timeout=httpx.Timeout(connect=10, read=60, write=60, pool=10),
                )
            )
            try:
                refreshed = reconnect_client.get(f"/v1/operations/{operation_id}")
                refreshed.raise_for_status()
                refreshed_operation = refreshed.json()
            finally:
                reconnect_client.close()
            if (
                refreshed_operation.get("status") != status
                or refreshed_operation.get("worklist") != operation.get("worklist")
                or refreshed_operation.get("result") != operation.get("result")
            ):
                raise HarnessError(
                    "fresh-connection operation read changed terminal worklist/result"
                )
            operation_slot["reconnect_verified"] = True
            operation_slot["reconnect_worklist_sha256"] = hashlib.sha256(
                _canonical_json(operation.get("worklist"))
            ).hexdigest()
            _write_evidence(output_path, evidence)
            if status != "succeeded":
                raise HarnessError(f"managed operation ended as {status}")
            revision = int(operation["result"]["workspace_revision"])
            if operation.get("worklist") is None:
                raise HarnessError("terminal operation omitted its durable worklist")
            active_count = revision_source_count(active_client, workspace_id)
            _validate_operation_metrics(
                operation,
                expected_source_count=active_count,
                expected_requested_document_count=len(batch),
                expected_uploaded_raw_bytes=sum(item.byte_size for item in batch),
            )
            worklist = operation["worklist"]
            if worklist.get("total_document_count") != active_count:
                raise HarnessError(
                    "durable worklist count disagrees with active sources"
                )
            if worklist.get("pending_count") != 0:
                raise HarnessError("terminal worklist retains pending documents")

        workspace_response = active_client.get(f"/v1/workspaces/{workspace_id}")
        workspace_response.raise_for_status()
        final_workspace = workspace_response.json()
        sources_response = active_client.get(f"/v1/workspaces/{workspace_id}/sources")
        sources_response.raise_for_status()
        active_sources = sources_response.json()["sources"]
        if len(active_sources) != len(sources):
            raise HarnessError("published source count does not match manifest")

        for item in questions:
            query_id = item.get("query_id")
            question = item.get("question")
            if not isinstance(query_id, str) or not isinstance(question, str):
                raise HarnessError("query deck item requires query_id and question")
            query_response = active_client.post(
                f"/v1/workspaces/{workspace_id}/query",
                json={"question": question},
                timeout=240,
            )
            query_response.raise_for_status()
            result = query_response.json()
            query_summary = {
                "query_id": query_id,
                "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
                "status": result.get("status"),
                "workspace_revision": result.get("workspace_revision"),
                "snapshot_id": result.get("snapshot_id"),
                "citation_count": len(result.get("citations", []))
                if isinstance(result.get("citations"), list)
                else None,
                "validation_status": "PENDING",
            }
            evidence["queries"].append(query_summary)
            _write_evidence(output_path, evidence)
            validation = _validate_query_result(
                result,
                active_sources,
                expected_revision=int(final_workspace["revision"]),
                expected_snapshot_id=str(final_workspace["current_snapshot_id"]),
            )
            query_summary.update(validation)
            query_summary["validation_status"] = "PASS"
            _write_evidence(output_path, evidence)

        completed_at = _utc_now()
        evidence.update(
            {
                "campaign_status": "COMPLETE",
                "source_count_published": len(active_sources),
                "workspace": {
                    "workspace_id": workspace_id,
                    "revision": final_workspace["revision"],
                    "snapshot_id": final_workspace["current_snapshot_id"],
                    "source_count": final_workspace["source_count"],
                },
                "completed_at": completed_at,
                "elapsed_seconds": round(time.monotonic() - start_time, 3),
                "capabilities": capability_summary,
                "aggregate_metrics": _sum_operation_metrics(evidence["operations"]),
            }
        )
        _write_evidence(output_path, evidence)
        return evidence
    except Exception as exc:
        evidence["campaign_status"] = "FAILED"
        evidence["failure_type"] = type(exc).__name__
        evidence["completed_at"] = _utc_now()
        evidence["elapsed_seconds"] = round(time.monotonic() - start_time, 3)
        evidence["aggregate_metrics"] = _sum_operation_metrics(evidence["operations"])
        _write_evidence(output_path, evidence)
        raise
    finally:
        if own_client and active_client is not None:
            active_client.close()


def run_full_cold_warm_pair(
    *,
    base_url: str,
    corpus_root: Path,
    manifest_path: Path,
    query_deck_path: Path,
    data_root: Path,
    authority: str,
    cold_output_path: Path,
    warm_output_path: Path,
    comparison_output_path: Path,
    poll_seconds: float = 2.0,
    cell_watchdog_seconds: int = DEFAULT_CELL_WATCHDOG_SECONDS,
    approved_manifest_sha256: str | None = None,
    approved_query_deck_file_sha256: str | None = None,
    client: httpx.Client | None = None,
    reconnect_client_factory: Any = None,
) -> dict[str, Any]:
    """Run the full-corpus cold and warm cells consecutively against one cache root."""
    output_paths = (cold_output_path, warm_output_path, comparison_output_path)
    if len({path.resolve() for path in output_paths}) != len(output_paths):
        raise HarnessError("paired evidence outputs must use distinct paths")
    if any(path.exists() for path in output_paths):
        raise HarnessError("refusing to overwrite existing 16K-F evidence")
    _require_full_primary_manifest(manifest_path)
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest_data.get("schema") == REPLACEMENT_MANIFEST_SCHEMA:
        verify_replacement_execution_artifact_pins(
            manifest_path,
            query_deck_path,
            approved_manifest_sha256=approved_manifest_sha256,
            approved_query_deck_file_sha256=approved_query_deck_file_sha256,
        )

    pair_run_id = f"16kf-pair-{uuid.uuid4().hex}"
    cold = run_cell(
        base_url=base_url,
        corpus_root=corpus_root,
        manifest_path=manifest_path,
        query_deck_path=query_deck_path,
        data_root=data_root,
        cache_state="cold",
        cell_id="full-primary-cold",
        authority=authority,
        output_path=cold_output_path,
        poll_seconds=poll_seconds,
        cell_watchdog_seconds=cell_watchdog_seconds,
        approved_manifest_sha256=approved_manifest_sha256,
        approved_query_deck_file_sha256=approved_query_deck_file_sha256,
        pair_run_id=pair_run_id,
        pair_sequence=1,
        client=client,
        reconnect_client_factory=reconnect_client_factory,
    )
    cold_evidence_sha256 = hashlib.sha256(cold_output_path.read_bytes()).hexdigest()
    warm = run_cell(
        base_url=base_url,
        corpus_root=corpus_root,
        manifest_path=manifest_path,
        query_deck_path=query_deck_path,
        data_root=data_root,
        cache_state="warm",
        cell_id="full-primary-warm",
        authority=authority,
        output_path=warm_output_path,
        poll_seconds=poll_seconds,
        cell_watchdog_seconds=cell_watchdog_seconds,
        approved_manifest_sha256=approved_manifest_sha256,
        approved_query_deck_file_sha256=approved_query_deck_file_sha256,
        pair_run_id=pair_run_id,
        pair_sequence=2,
        predecessor_evidence_sha256=cold_evidence_sha256,
        client=client,
        reconnect_client_factory=reconnect_client_factory,
    )
    comparison = compare_cold_warm(
        cold,
        warm,
        cold_evidence_sha256=cold_evidence_sha256,
    )
    comparison["pair_run_id"] = pair_run_id
    comparison["cold_evidence_sha256"] = cold_evidence_sha256
    _write_evidence(comparison_output_path, comparison)
    return comparison


def _require_full_primary_manifest(manifest_path: Path) -> None:
    """Reject unsupported manifests before a full-corpus pair starts.

    Historical primary manifests retain their fixed 39-document contract.
    The replacement acceptance manifest carries and validates its own exact
    source count and complete all-path population.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise HarnessError("full-corpus pair requires a primary corpus manifest")
    if manifest.get("schema") == REPLACEMENT_MANIFEST_SCHEMA:
        _verify_manifest_hash(manifest)
        try:
            validate_replacement_manifest(manifest)
        except PreparationError as exc:
            raise HarnessError(str(exc)) from exc
        population = manifest["successful_ingestion_population"]
        if population["source_count"] <= 0:
            raise HarnessError("replacement manifest has no eligible ingestion sources")
        return
    if manifest.get("schema") != PRIMARY_CORPUS_MANIFEST_SCHEMA:
        raise HarnessError("full-corpus pair requires a primary corpus manifest")
    _verify_manifest_hash(manifest)

    primary_sources = manifest.get("primary_sources")
    if (
        manifest.get("primary_document_count") != EXPECTED_PRIMARY_DOCUMENTS
        or not isinstance(primary_sources, list)
        or len(primary_sources) != EXPECTED_PRIMARY_DOCUMENTS
    ):
        raise HarnessError("full-corpus manifest must select exactly 39 primaries")

    logical_document_ids: set[str] = set()
    for source in primary_sources:
        if not isinstance(source, dict):
            raise HarnessError("full-corpus primary source row is malformed")
        logical_document_id = source.get("logical_document_id")
        if (
            source.get("role") != "primary"
            or source.get("text_bearing") is not True
            or not isinstance(logical_document_id, str)
            or not logical_document_id
            or logical_document_id in logical_document_ids
        ):
            raise HarnessError(
                "full-corpus manifest must select 39 unique primary logical documents"
            )
        logical_document_ids.add(logical_document_id)


def revision_source_count(client: httpx.Client, workspace_id: str) -> int:
    response = client.get(f"/v1/workspaces/{workspace_id}/sources")
    response.raise_for_status()
    return len(response.json()["sources"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run-cell")
    run_parser.add_argument("--base-url", required=True)
    run_parser.add_argument("--corpus-dir", required=True, type=Path)
    run_parser.add_argument("--manifest", required=True, type=Path)
    run_parser.add_argument("--query-deck", required=True, type=Path)
    run_parser.add_argument("--data-root", required=True, type=Path)
    run_parser.add_argument("--cache-state", choices=("cold", "warm"), required=True)
    run_parser.add_argument("--cell-id", required=True)
    run_parser.add_argument("--output", required=True, type=Path)
    run_parser.add_argument("--poll-seconds", type=float, default=2.0)
    run_parser.add_argument("--approved-manifest-sha256")
    run_parser.add_argument("--approved-query-deck-file-sha256")
    run_parser.add_argument(
        "--cell-watchdog-seconds",
        type=int,
        default=DEFAULT_CELL_WATCHDOG_SECONDS,
    )
    run_parser.add_argument("--execute-real-corpus", action="store_true")
    run_parser.add_argument("--authority")
    pair_parser = subparsers.add_parser("run-full-pair")
    pair_parser.add_argument("--base-url", required=True)
    pair_parser.add_argument("--corpus-dir", required=True, type=Path)
    pair_parser.add_argument("--manifest", required=True, type=Path)
    pair_parser.add_argument("--query-deck", required=True, type=Path)
    pair_parser.add_argument("--data-root", required=True, type=Path)
    pair_parser.add_argument("--cold-output", required=True, type=Path)
    pair_parser.add_argument("--warm-output", required=True, type=Path)
    pair_parser.add_argument("--comparison-output", required=True, type=Path)
    pair_parser.add_argument("--poll-seconds", type=float, default=2.0)
    pair_parser.add_argument("--approved-manifest-sha256")
    pair_parser.add_argument("--approved-query-deck-file-sha256")
    pair_parser.add_argument(
        "--cell-watchdog-seconds",
        type=int,
        default=DEFAULT_CELL_WATCHDOG_SECONDS,
    )
    pair_parser.add_argument("--execute-real-corpus", action="store_true")
    pair_parser.add_argument("--authority")
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--cold", required=True, type=Path)
    compare_parser.add_argument("--warm", required=True, type=Path)
    compare_parser.add_argument("--output", required=True, type=Path)
    robustness_parser = subparsers.add_parser("validate-robustness-evidence")
    robustness_parser.add_argument("--input", required=True, type=Path)
    robustness_parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate-robustness-evidence":
        try:
            record = json.loads(args.input.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise HarnessError("robustness evidence must be a JSON object")
            summary = validate_robustness_case_evidence(record)
            _write_evidence(args.output, summary)
            print(json.dumps(summary, sort_keys=True))
            return 0
        except (OSError, json.JSONDecodeError, HarnessError) as exc:
            print(
                f"16K-F robustness evidence failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 2
    if args.command == "compare":
        try:
            cold = json.loads(args.cold.read_text(encoding="utf-8"))
            warm = json.loads(args.warm.read_text(encoding="utf-8"))
            cold_sha = hashlib.sha256(args.cold.read_bytes()).hexdigest()
            comparison = compare_cold_warm(
                cold,
                warm,
                cold_evidence_sha256=cold_sha,
            )
            _write_evidence(args.output, comparison)
            print(json.dumps(comparison, sort_keys=True))
            return 0
        except (OSError, json.JSONDecodeError, HarnessError) as exc:
            print(
                f"16K-F comparison failed: {type(exc).__name__}: {exc}", file=sys.stderr
            )
            return 2
    if args.command == "run-full-pair":
        if not args.execute_real_corpus or not args.authority:
            print(
                "real corpus execution requires --execute-real-corpus and an "
                "explicit execution authority",
                file=sys.stderr,
            )
            return 2
        try:
            comparison = run_full_cold_warm_pair(
                base_url=args.base_url,
                corpus_root=args.corpus_dir,
                manifest_path=args.manifest,
                query_deck_path=args.query_deck,
                data_root=args.data_root,
                authority=args.authority,
                cold_output_path=args.cold_output,
                warm_output_path=args.warm_output,
                comparison_output_path=args.comparison_output,
                poll_seconds=args.poll_seconds,
                cell_watchdog_seconds=args.cell_watchdog_seconds,
                approved_manifest_sha256=args.approved_manifest_sha256,
                approved_query_deck_file_sha256=args.approved_query_deck_file_sha256,
            )
            print(json.dumps(comparison, sort_keys=True))
            return 0
        except (OSError, httpx.HTTPError, json.JSONDecodeError, HarnessError) as exc:
            print(f"16K-F pair failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    if args.command != "run-cell":
        _parser().print_help()
        return 2
    if not args.execute_real_corpus or not args.authority:
        print(
            "real corpus execution requires --execute-real-corpus and an "
            "explicit execution authority",
            file=sys.stderr,
        )
        return 2
    try:
        evidence = run_cell(
            base_url=args.base_url,
            corpus_root=args.corpus_dir,
            manifest_path=args.manifest,
            query_deck_path=args.query_deck,
            data_root=args.data_root,
            cache_state=args.cache_state,
            cell_id=args.cell_id,
            authority=args.authority,
            output_path=args.output,
            poll_seconds=args.poll_seconds,
            cell_watchdog_seconds=args.cell_watchdog_seconds,
            approved_manifest_sha256=args.approved_manifest_sha256,
            approved_query_deck_file_sha256=args.approved_query_deck_file_sha256,
        )
        print(
            json.dumps(
                {
                    "cell_id": evidence["cell_id"],
                    "source_count_published": evidence["source_count_published"],
                    "upload_batch_count": evidence["upload_batch_count"],
                    "evidence": str(args.output),
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, httpx.HTTPError, json.JSONDecodeError, HarnessError) as exc:
        print(f"16K-F cell failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
