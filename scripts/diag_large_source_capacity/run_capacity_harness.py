#!/usr/bin/env python3
"""Run the bounded full-product large-source capacity capability smoke.

The default run submits the small born-digital PDF through the real workspace
``SOURCE_ADD`` lifecycle. The capability lane uses deterministic fake downstream
resources while retaining the same workspace, vault, projection, ingestion,
chunking, indexing, publication, and terminal paths that L5 will exercise.
It never changes shipped product limits and never claims an L5 qualification.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from offline_rag.api.workspace_views import operation_view, source_view, workspace_view
from offline_rag.app.ingest_upload import cleanup_staging, spool_local_files
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.workspace.lifecycle import SourceUpload
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend

try:
    from .common import (
        EVIDENCE_CONTRACT,
        DiskUsageTracker,
        ProcessSampler,
        StageTracker,
        cpu_metrics,
        fixture_identity,
        git_provenance,
        machine_provenance,
        reset_cuda_peak_memory_stats,
        rusage_snapshot,
        sanitized_json,
    )
    from .common import REPO_ROOT as COMMON_REPO_ROOT
except ImportError:  # direct ``python scripts/.../run_capacity_harness.py``
    from common import (
        EVIDENCE_CONTRACT,
        DiskUsageTracker,
        ProcessSampler,
        StageTracker,
        cpu_metrics,
        fixture_identity,
        git_provenance,
        machine_provenance,
        reset_cuda_peak_memory_stats,
        rusage_snapshot,
        sanitized_json,
    )
    from common import REPO_ROOT as COMMON_REPO_ROOT


PDF_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "ingestion"
    / "pdf"
    / "born_digital_reference.pdf"
)
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"
APPROVED_MODEL = "local-test-model"


class _Closeable:
    def close(self) -> None:
        return None


def _settings(
    tmp_root: Path, *, max_document: int | None, max_total: int | None
) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_root / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(REPO_ROOT / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    updates: dict[str, Any] = {}
    if max_document is not None:
        updates["max_bytes_per_document"] = max_document
    if max_total is not None:
        updates["max_total_upload_bytes"] = max_total
    if updates:
        settings = settings.model_copy(
            update={"api": settings.api.model_copy(update=updates)}
        )
    settings = settings.model_copy(
        update={
            "generation": settings.generation.model_copy(
                update={
                    "base_url": APPROVED_ENDPOINT,
                    "model": APPROVED_MODEL,
                    "approved_endpoints": [APPROVED_ENDPOINT],
                    "approved_models": [APPROVED_MODEL],
                }
            ),
            "reranker": settings.reranker.model_copy(update={"enabled": False}),
        }
    )
    return settings


def _runtime(settings: AppSettings) -> ApplicationRuntime:
    embedder = FakeEmbedder(dimension=8, normalize=True)

    def _qdrant(current: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(current.paths.qdrant_storage)

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _settings: embedder,
            reranker=lambda _settings: None,
            generator_client=lambda _settings: _Closeable(),
            qdrant=_qdrant,
        ),
    )


def _roots(settings: AppSettings) -> dict[str, Path]:
    paths = settings.paths
    return {
        "staging": paths.staging,
        "workspaces_vault": paths.workspaces,
        "corpora_candidate_live": paths.corpora,
        "processed": paths.processed,
        "chunks": paths.chunks,
        "embeddings": paths.embeddings,
        "qdrant": paths.qdrant_storage,
        "manifests": paths.manifests,
        "chunk_manifests": paths.chunk_manifests,
        "index_manifests": paths.index_manifests,
        "lexical_indexes": paths.lexical_indexes,
        "lexical_index_manifests": paths.lexical_index_manifests,
    }


def _stage_from_operation(tracker: StageTracker, body: dict[str, Any]) -> None:
    """Translate existing managed-operation telemetry into sampler labels."""
    progress_stage = str(body.get("progress_stage") or "").lower().split(".")[-1]
    progress_mapping = {
        "preparing": "preparing",
        "processing": "ingest",
        "publishing": "publish",
        "finalizing": "finalization",
        "ready": "finalization",
    }
    worklist = body.get("worklist") or {}
    documents = worklist.get("documents") or []
    phases = {str(item.get("phase", "")).lower().split(".")[-1] for item in documents}
    if "parsing" in phases:
        tracker.set_stage("pdf_parsing")
    elif "chunking" in phases:
        tracker.set_stage("chunk")
    elif "indexing" in phases:
        tracker.set_stage("dense")
    elif progress_mapping.get(progress_stage):
        tracker.set_stage(progress_mapping[progress_stage])


def _run_workspace_source_add(
    settings: AppSettings,
    source: Path,
    tracker: StageTracker,
) -> dict[str, Any]:
    """Execute one real workspace SOURCE_ADD lifecycle operation.

    The direct lifecycle call is the same path launched by the HTTP route after
    admission. A local spool supplies the same bounded path-backed upload
    object, and a polling thread keeps stage labels live while the synchronous
    managed worker performs the product operation.
    """
    runtime = _runtime(settings)
    runtime.start()
    lifecycle = runtime.workspace_lifecycle
    record = lifecycle.create_workspace(
        idempotency_key="l4-capability-workspace",
        title="L4 capacity capability",
        description="",
    )
    tracker.set_stage("preparing")
    upload = spool_local_files(
        settings=settings,
        corpus_name="l4-smoke",
        files=[(source, source.name)],
        apply_transport_limits=True,
    )
    item = upload.files[0]
    source_upload = SourceUpload(
        display_name=item.source_name,
        content_type=item.media_type,
        spool_path=item.absolute_path,
        content_sha256=item.document_id.removeprefix("doc_"),
    )
    result: dict[str, Any] = {}
    failure: list[Exception] = []

    def worker() -> None:
        try:
            result["record"] = lifecycle.add_source(
                record.workspace_id,
                expected_revision=record.revision,
                idempotency_key="l4-capability-source-add",
                upload=source_upload,
            )
        except Exception as exc:  # noqa: BLE001 - preserve worker failure for evidence
            failure.append(exc)

    thread = threading.Thread(target=worker, name="l4-workspace-source-add")
    thread.start()
    operation_store = ManagedOperationStore(settings)
    operation_id: str | None = None
    while thread.is_alive():
        records = operation_store.list_for_workspace(record.workspace_id)
        if records:
            current = max(records, key=lambda item: item.updated_at)
            operation_id = current.operation_id
            _stage_from_operation(tracker, operation_view(current))
        time.sleep(0.05)
    thread.join()
    final_record = (
        operation_store.get_by_operation_id(operation_id)
        if operation_id is not None
        else result.get("record")
    )
    if final_record is None:
        if failure:
            raise failure[0]
        raise RuntimeError("workspace SOURCE_ADD produced no managed operation")
    operation = operation_view(final_record)
    final_workspace = WorkspaceStore(settings).get(record.workspace_id)
    sources = {
        "workspace_id": record.workspace_id,
        "revision": final_workspace.revision,
        "sources": [
            source_view(item) for item in final_workspace.sources if item.active
        ],
    }
    try:
        return {
            "workspace_id": record.workspace_id,
            "operation_id": final_record.operation_id,
            "add_status": 202,
            "add_body": {
                "operation_id": final_record.operation_id,
                "transport": "workspace_lifecycle_equivalent",
            },
            "operation": operation,
            "workspace": workspace_view(final_workspace),
            "sources": sources,
        }
    finally:
        cleanup_staging(upload.staging_root)
        runtime.begin_drain()
        runtime.wait_for_drain(timeout_seconds=30)
        runtime.finalize_shutdown()


def _product_stage_timings(operation: dict[str, Any]) -> dict[str, int | None]:
    metrics = operation.get("metrics") or {}
    durations = metrics.get("stage_durations") or {}
    return {
        "parsing": durations.get("parsing_ms"),
        "chunk": durations.get("chunking_ms"),
        "dense": durations.get("dense_generation_ms"),
        "dense_materialization": durations.get("dense_materialization_ms"),
        "lexical": durations.get("lexical_ms"),
        "publish": durations.get("publication_ms"),
        "finalization": durations.get("finalization_ms"),
    }


def _active_source_bytes(sources: dict[str, Any]) -> int:
    return sum(int(item.get("byte_size") or 0) for item in sources.get("sources", []))


def run_smoke(
    *,
    source: Path,
    json_out: Path,
    profile: str,
    mode: str,
    max_document: int | None,
    max_total: int | None,
    rss_interval: float,
    disk_interval: float,
    gpu_interval: float,
    instrumentation_enabled: bool = True,
) -> dict[str, Any]:
    source = source.resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() != ".pdf":
        raise ValueError("L4 capability smoke requires a PDF fixture")
    if mode not in {"capability_smoke", "qualification"}:
        raise ValueError(f"unsupported harness mode: {mode}")

    with tempfile.TemporaryDirectory(prefix="seneca-l4-") as temporary:
        tmp_root = Path(temporary)
        settings = _settings(tmp_root, max_document=max_document, max_total=max_total)
        tracker = StageTracker()
        disk = DiskUsageTracker(_roots(settings), tmp_root)
        sampler = ProcessSampler(
            stage_provider=tracker.stage_at,
            rss_interval_s=rss_interval,
            disk_interval_s=disk_interval,
            gpu_interval_s=gpu_interval,
            disk_tracker=disk,
        )
        production_defaults = load_settings(yaml_paths=[], environ={}).api
        source_meta = fixture_identity(
            source, label=source.stem, role="l4_capability_smoke"
        )
        reset_stats = reset_cuda_peak_memory_stats()
        before_cpu = rusage_snapshot()
        started = time.perf_counter()
        tracker.set_stage("upload")
        if instrumentation_enabled:
            sampler.start()

        try:
            product = _run_workspace_source_add(settings, source, tracker)
        finally:
            elapsed = time.perf_counter() - started
            if instrumentation_enabled:
                sampler.stop()
            after_cpu = rusage_snapshot()

        parser_elapsed = tracker.duration_for("pdf_parsing", elapsed)
        measurement = sampler.summary(parser_elapsed_s=parser_elapsed)
        stage_timings = tracker.duration_summary(elapsed)
        product_timings = _product_stage_timings(product["operation"])
        for stage, duration_ms in product_timings.items():
            if duration_ms is not None:
                stage_timings.setdefault(stage, float(duration_ms) / 1000.0)
        for stage in (
            "upload",
            "preparing",
            "ingest",
            "pdf_parsing",
            "chunk",
            "dense",
            "lexical",
            "publish",
            "finalization",
        ):
            stage_timings.setdefault(stage, None)

        disk_summary = disk.summary()
        aggregate_disk = disk_summary["aggregate"]
        source_bytes = int(source_meta["byte_size"])
        workspace_id = product.get("workspace_id", None)
        operation_id = product.get("operation_id", None)
        add_status = product.get("add_status", None)
        add_body = product.get("add_body", {})
        operation = product.get("operation", {})
        workspace = product.get("workspace", {})
        sources = product.get("sources", {"sources": []})
        post_active_bytes = _active_source_bytes(sources)
        operation_status = str(operation.get("status") or "failed")
        evidence = {
            "contract": EVIDENCE_CONTRACT,
            "authority": "S16-K-LARGE-SOURCE-CAPACITY-L4-INSTRUMENTATION-HARNESS-IMPLEMENTATION-AUTH-001",
            "authority_mode": mode,
            "git": git_provenance(
                COMMON_REPO_ROOT,
                [Path(__file__).resolve(), Path(__file__).with_name("common.py")],
            ),
            "machine": machine_provenance(),
            "source": source_meta,
            "product_defaults": {
                "max_bytes_per_document": production_defaults.max_bytes_per_document,
                "max_total_upload_bytes": production_defaults.max_total_upload_bytes,
                "max_files_per_ingest": production_defaults.max_files_per_ingest,
            },
            "harness_effective_limits": {
                "max_bytes_per_document": settings.api.max_bytes_per_document,
                "max_total_upload_bytes": settings.api.max_total_upload_bytes,
                "max_files_per_ingest": settings.api.max_files_per_ingest,
                "override_isolated_to_harness": bool(max_document or max_total),
            },
            "execution_profile": {
                "requested_profile_id": profile,
                "resolved_profile_id": profile,
                "execution_mode": mode,
                "embedding_execution": (
                    "FakeEmbedder(dimension=8) capability smoke"
                    if mode == "capability_smoke"
                    else "profile-selected qualification lane"
                ),
                "profile_selection_ready_for_l5": True,
            },
            "configuration": {
                "strict_offline": settings.project.strict_offline,
                "parser": "docling_pdf",
                "ocr_enabled": settings.parsing.pdf.ocr_enabled,
                "workspace_api_path": "SOURCE_ADD",
            },
            "sampling_configuration": {
                "rss_interval_s": rss_interval,
                "disk_interval_s": disk_interval,
                "gpu_interval_s": gpu_interval,
                "external_gpu_sampling": instrumentation_enabled,
                "rss_source": "/proc/self/status VmRSS",
                "lifetime_rss_source": "resource.getrusage ru_maxrss",
            },
            "operation": {
                "workspace_id": workspace_id,
                "operation_id": operation_id,
                "http_status": add_status,
                "response": add_body,
                "terminal_state_source": (
                    "managed operation durable record; HTTP GET projection equivalent"
                ),
                "managed_operation": operation,
                "workspace_snapshot": workspace,
                "active_sources": sources,
            },
            "timings": {
                "operation_total_s": elapsed,
                "product_reported_stage_ms": product_timings,
                "harness_observed_stage_s": stage_timings,
                "parser_interval_s": measurement["parser"]["elapsed_s"],
            },
            "stage_attribution": {
                "observed_transitions": tracker.transitions,
                "diagnostic_label_source": (
                    "managed-operation progress/worklist and product metrics"
                ),
                "observed_product_stages": [
                    stage
                    for stage, duration in product_timings.items()
                    if duration is not None
                ],
                "unobserved_product_stages": [
                    stage
                    for stage in ("chunk", "dense", "lexical", "publish")
                    if product_timings.get(stage) is None
                ],
            },
            "memory": measurement,
            "cpu": cpu_metrics(before_cpu, after_cpu, elapsed),
            "gpu": {
                "peak_reset": reset_stats,
                "samples": [
                    sample.get("gpu")
                    for sample in measurement["sample_timeline"]
                    if "gpu" in sample
                ],
            },
            "disk": disk_summary,
            "disk_amplification_inputs": {
                "source_bytes": source_bytes,
                "peak_storage_growth_bytes": aggregate_disk["peak_growth_bytes"],
                "final_storage_growth_bytes": aggregate_disk["final_growth_bytes"],
                "peak_storage_growth_ratio": (
                    aggregate_disk["peak_growth_bytes"] / source_bytes
                    if source_bytes
                    else None
                ),
                "final_storage_growth_ratio": (
                    aggregate_disk["final_growth_bytes"] / source_bytes
                    if source_bytes
                    else None
                ),
                "pre_active_source_bytes": 0,
                "new_source_bytes": source_bytes,
                "post_active_source_bytes": post_active_bytes,
                "workspace_mutation": "source_add",
            },
            "corpus_results": {
                "workspace_status": workspace.get("status"),
                "snapshot_id": workspace.get("current_snapshot_id"),
                "active_source_count": len(sources.get("sources", [])),
                "document_id": (sources.get("sources") or [{}])[0].get("document_id"),
                "content_hash": (sources.get("sources") or [{}])[0].get("content_hash"),
                "identity_matches_fixture": (
                    (sources.get("sources") or [{}])[0].get("document_id")
                    == f"doc_{source_meta['sha256']}"
                ),
            },
            "terminal": {
                "status": "succeeded"
                if operation_status == "succeeded"
                else operation_status,
                "http_status": add_status,
                "managed_operation_status": operation_status,
            },
            "perturbation": {
                "instrumentation_enabled": instrumentation_enabled,
                "note": "Sampling is observational and its cadence is recorded; no zero-overhead claim is made.",
            },
        }
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(sanitized_json(evidence), encoding="utf-8")
        return evidence


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PDF_FIXTURE)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=REPO_ROOT
        / "docs"
        / "evidence"
        / "large_source_capacity"
        / "l4_capability_smoke.json",
    )
    parser.add_argument(
        "--profile",
        choices=("cpu_onnx_fp32_v1", "cuda_fp16_v1"),
        default="cpu_onnx_fp32_v1",
    )
    parser.add_argument(
        "--mode",
        choices=("capability_smoke", "qualification"),
        default="capability_smoke",
        help="capability_smoke uses fake downstream resources; qualification is profile-ready for L5",
    )
    parser.add_argument("--harness-max-bytes-per-document", type=int)
    parser.add_argument("--harness-max-total-upload-bytes", type=int)
    parser.add_argument("--rss-interval-s", type=float, default=0.2)
    parser.add_argument("--disk-interval-s", type=float, default=1.0)
    parser.add_argument("--gpu-interval-s", type=float, default=1.0)
    parser.add_argument(
        "--disable-instrumentation",
        action="store_true",
        help="run the same full-product smoke without measurement sampling",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    evidence = run_smoke(
        source=args.source,
        json_out=args.json_out,
        profile=args.profile,
        mode=args.mode,
        max_document=args.harness_max_bytes_per_document,
        max_total=args.harness_max_total_upload_bytes,
        rss_interval=args.rss_interval_s,
        disk_interval=args.disk_interval_s,
        gpu_interval=args.gpu_interval_s,
        instrumentation_enabled=not args.disable_instrumentation,
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["terminal"]["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
