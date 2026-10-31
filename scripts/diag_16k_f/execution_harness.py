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
import sys
import time
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

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


def compare_cold_warm(cold: dict[str, Any], warm: dict[str, Any]) -> dict[str, Any]:
    """Compare paired full-corpus cells without imposing an unfrozen materiality
    threshold. The result reports reductions; reviewers apply accepted criteria.
    """
    if cold.get("source_identity_sha256") != warm.get("source_identity_sha256"):
        raise HarnessError("cold and warm source identities do not match")
    if cold.get("cache_state") != "cold" or warm.get("cache_state") != "warm":
        raise HarnessError("paired cache states must be cold then warm")
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
        "reductions": reductions,
        "materiality_disposition": "REVIEW_AGAINST_ACCEPTED_CRITERIA",
    }


def _nested_metric(metrics: dict[str, Any], dotted_path: str) -> Any:
    value: Any = metrics
    for segment in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(segment)
    return value


def _write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


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
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Execute one source-set cell via durable workspace API operations."""
    check_cache_state(data_root, cache_state)
    sources, manifest_hash = load_sources(corpus_root, manifest_path)
    batches = batch_sources(sources)
    query_deck = json.loads(query_deck_path.read_text(encoding="utf-8"))
    questions = query_deck.get("questions")
    if not isinstance(questions, list) or not questions:
        raise HarnessError("query deck must contain at least one question")

    own_client = client is None
    active_client = client or httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(connect=10, read=60, write=3600, pool=10),
    )
    if own_client:
        active_client.base_url = httpx.URL(base_url.rstrip("/"))

    start_time = time.monotonic()
    operations: list[dict[str, Any]] = []
    try:
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

            while True:
                active_client.get("/health/ready").raise_for_status()
                current = active_client.get(f"/v1/operations/{operation_id}")
                current.raise_for_status()
                operation = current.json()
                status = operation.get("status")
                if status in TERMINAL_STATUSES:
                    break
                time.sleep(poll_seconds)

            safe = _safe_operation(operation)
            operations.append(safe)
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

        queries = []
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
            queries.append(
                {
                    "query_id": query_id,
                    "question_sha256": hashlib.sha256(
                        question.encode("utf-8")
                    ).hexdigest(),
                    "status": result.get("status"),
                    "workspace_revision": result.get("workspace_revision"),
                    "snapshot_id": result.get("snapshot_id"),
                    "citation_count": len(result.get("citations", [])),
                }
            )

        evidence = {
            "schema": "16k-f-cell-evidence-v1",
            "cell_id": cell_id,
            "execution_authority": authority,
            "cache_state": cache_state,
            "manifest_sha256": manifest_hash,
            "source_count_expected": len(sources),
            "source_count_published": len(active_sources),
            "source_identity_sha256": hashlib.sha256(
                "\n".join(sorted(item.sha256 for item in sources)).encode("ascii")
            ).hexdigest(),
            "workspace": {
                "workspace_id": workspace_id,
                "revision": final_workspace["revision"],
                "snapshot_id": final_workspace["current_snapshot_id"],
                "source_count": final_workspace["source_count"],
            },
            "elapsed_seconds": round(time.monotonic() - start_time, 3),
            "upload_batch_count": len(batches),
            "capabilities": capability_summary,
            "operations": operations,
            "aggregate_metrics": _sum_operation_metrics(operations),
            "queries": queries,
        }
        _write_evidence(output_path, evidence)
        return evidence
    finally:
        if own_client:
            active_client.close()


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
    run_parser.add_argument("--execute-real-corpus", action="store_true")
    run_parser.add_argument("--authority")
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--cold", required=True, type=Path)
    compare_parser.add_argument("--warm", required=True, type=Path)
    compare_parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "compare":
        try:
            cold = json.loads(args.cold.read_text(encoding="utf-8"))
            warm = json.loads(args.warm.read_text(encoding="utf-8"))
            comparison = compare_cold_warm(cold, warm)
            _write_evidence(args.output, comparison)
            print(json.dumps(comparison, sort_keys=True))
            return 0
        except (OSError, json.JSONDecodeError, HarnessError) as exc:
            print(
                f"16K-F comparison failed: {type(exc).__name__}: {exc}", file=sys.stderr
            )
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
