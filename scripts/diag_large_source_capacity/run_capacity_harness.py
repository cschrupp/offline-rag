#!/usr/bin/env python3
"""Run a bounded large-source capacity instrumentation smoke.

The default run uses the existing small born-digital PDF and the real Docling
parser through the bounded ingestion pipeline. It validates the measurement
contract only; it is not an L5 capacity qualification and never changes shipped
product limits.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

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
    from .common import (
        REPO_ROOT as COMMON_REPO_ROOT,
    )
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
    from common import (
        REPO_ROOT as COMMON_REPO_ROOT,
    )

from offline_rag.app.ingest_upload import cleanup_staging, spool_local_files
from offline_rag.chunking.persistence import chunk_state_path, load_chunk_state
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.persistence import (
    corpus_state_path,
    load_corpus_state,
    load_parsed_document,
    processed_artifact_path,
)
from offline_rag.ingestion.pipeline import SourceIdentity, run_ingestion

PDF_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "ingestion"
    / "pdf"
    / "born_digital_reference.pdf"
)


def _settings(
    tmp_root: Path, *, max_document: int | None, max_total: int | None
) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_root / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(REPO_ROOT / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "true",
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
    return settings


def _roots(settings: AppSettings) -> dict[str, Path]:
    paths = settings.paths
    return {
        "staging": paths.staging,
        "workspaces": paths.workspaces,
        "corpora": paths.corpora,
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


def _product_stage_timings(reports: list[dict[str, Any]]) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for item in reports:
        stage = str(item.get("stage", ""))
        report = item.get("report")
        result[stage] = report.get("duration_ms") if isinstance(report, dict) else None
    return result


def _corpus_results(settings: AppSettings, corpus: str) -> dict[str, Any]:
    state_path = corpus_state_path(settings.paths.corpora, corpus)
    if not state_path.exists():
        return {"status": "unavailable", "document_count": 0}
    state = load_corpus_state(state_path)
    source = next(iter(state.sources.values()), None)
    result: dict[str, Any] = {
        "status": "observed",
        "document_count": len(state.sources),
        "corpus_id": state.current_corpus_id,
    }
    if source is not None:
        result.update(
            {
                "document_id": source.document_id,
                "parsed_block_count": source.block_count,
                "chunk_count": None,
            }
        )
        artifact = load_parsed_document(
            processed_artifact_path(settings.paths.processed, source.parsed_artifact_id)
        )
        pages = {
            block.page_number
            for block in artifact.blocks
            if block.page_number is not None
        }
        result["page_count"] = len(pages) if pages else None
    chunk_state = chunk_state_path(settings.paths.corpora, corpus)
    if chunk_state.exists():
        result["chunk_set_id"] = load_chunk_state(chunk_state).current_chunk_set_id
    return result


def run_smoke(
    *,
    source: Path,
    json_out: Path,
    profile: str,
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
        response_status = None
        response_body: dict[str, Any] = {}
        upload = None
        try:
            # Use the accepted local spool adapter and ingestion pipeline so
            # the smoke remains bounded and never materializes the PDF body.
            upload = spool_local_files(
                settings=settings,
                corpus_name="l4-smoke",
                files=[(source, source.name)],
                apply_transport_limits=True,
            )
            tracker.set_stage("preparing")
            trusted = {
                item.storage_name: SourceIdentity(
                    document_id=item.document_id,
                    content_hash=item.document_id.removeprefix("doc_"),
                )
                for item in upload.files
            }
            report = run_ingestion(
                settings=settings,
                inputs=[item.absolute_path for item in upload.files],
                corpus_name="l4-smoke",
                recursive=False,
                root=upload.files_root,
                source_name_by_path=upload.source_name_by_storage_name(),
                trusted_identities=trusted,
                on_document_phase=tracker.document_phase,
            )
            tracker.after_stage_report("ingest", report)
            response_status = (
                200 if report.status.value in {"success", "no_op"} else 500
            )
            response_body = {
                "corpus": report.corpus_name,
                "document_count": len(report.files),
                "status": report.status.value,
            }
            cleanup_staging(upload.staging_root)
            upload = None
            tracker.set_stage("finalization")
        finally:
            if upload is not None:
                cleanup_staging(upload.staging_root)
            elapsed = time.perf_counter() - started
            if instrumentation_enabled:
                sampler.stop()
            after_cpu = rusage_snapshot()

        corpus = _corpus_results(settings, "l4-smoke")
        stage_timings = tracker.duration_summary(elapsed)
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
        peak_growth = aggregate_disk["peak_growth_bytes"]
        final_growth = aggregate_disk["final_growth_bytes"]
        evidence = {
            "contract": EVIDENCE_CONTRACT,
            "authority": "S16-K-LARGE-SOURCE-CAPACITY-L4-INSTRUMENTATION-HARNESS-IMPLEMENTATION-AUTH-001",
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
                "embedding_execution": "not executed; parser/ingestion capability smoke",
            },
            "configuration": {
                "strict_offline": settings.project.strict_offline,
                "parser": "docling_pdf",
                "ocr_enabled": settings.parsing.pdf.ocr_enabled,
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
                "corpus": "l4-smoke",
                "http_status": response_status,
                "response": {
                    "corpus": response_body.get("corpus"),
                    "snapshot_id": response_body.get("snapshot_id"),
                    "document_count": response_body.get("document_count"),
                },
                "terminal_state_source": "IngestionReport.status",
            },
            "timings": {
                "operation_total_s": elapsed,
                "product_reported_stage_ms": _product_stage_timings(
                    tracker.stage_reports
                ),
                "harness_observed_stage_s": stage_timings,
                "parser_interval_s": sampler.summary()["parser"]["elapsed_s"],
            },
            "stage_attribution": {
                "observed_transitions": tracker.transitions,
                "diagnostic_label_source": "ProductIngestHooks stage vocabulary and document-phase events",
                "unobserved_product_stages": [
                    stage
                    for stage in ("chunk", "dense", "lexical", "publish")
                    if stage_timings.get(stage) is None
                ],
            },
            "memory": sampler.summary(),
            "cpu": cpu_metrics(before_cpu, after_cpu, elapsed),
            "gpu": {
                "peak_reset": reset_stats,
                "samples": [
                    sample.get("gpu") for sample in sampler.samples if "gpu" in sample
                ],
            },
            "disk": disk_summary,
            "disk_amplification_inputs": {
                "source_bytes": source_bytes,
                "peak_storage_growth_bytes": peak_growth,
                "final_storage_growth_bytes": final_growth,
                "peak_storage_growth_ratio": peak_growth / source_bytes
                if source_bytes
                else None,
                "final_storage_growth_ratio": final_growth / source_bytes
                if source_bytes
                else None,
                "pre_active_source_bytes": None,
                "new_source_bytes": source_bytes,
                "post_active_source_bytes": None,
                "workspace_mutation": "not_run",
            },
            "corpus_results": corpus,
            "terminal": {
                "status": "succeeded" if response_status == 200 else "failed",
                "http_status": response_status,
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
    parser.add_argument("--harness-max-bytes-per-document", type=int)
    parser.add_argument("--harness-max-total-upload-bytes", type=int)
    parser.add_argument("--rss-interval-s", type=float, default=0.2)
    parser.add_argument("--disk-interval-s", type=float, default=1.0)
    parser.add_argument("--gpu-interval-s", type=float, default=1.0)
    parser.add_argument(
        "--disable-instrumentation",
        action="store_true",
        help="run the same bounded smoke without measurement sampling",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    evidence = run_smoke(
        source=args.source,
        json_out=args.json_out,
        profile=args.profile,
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
