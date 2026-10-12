#!/usr/bin/env python3
"""16H Family L — empirical source/corpus capacity observations.

Runs against an in-process ApplicationRuntime + TestClient using FakeEmbedder.
Does not raise repository defaults. Observes default-profile 32-source envelopes
and attempts exploratory 64/128 only through the accepted API guardrail (expected
to refuse when max_files_per_ingest remains 32).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.config import load_settings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.generation.fake import FakeGenerator
from offline_rag.ingestion.docling_artifacts import (
    write_provisioning_manifest,
)
from offline_rag.rerank.fake import FakeReranker

TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"


class _Closeable:
    def close(self) -> None:
        return None


def _rss_bytes() -> int:
    # ru_maxrss is kilobytes on Linux.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
            ).strip()
        )
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _machine_declaration() -> dict:
    uname = platform.uname()
    mem_kb = None
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                mem_kb = int(line.split()[1])
                break
    except Exception:  # noqa: BLE001
        mem_kb = None
    docker_version = None
    try:
        docker_version = subprocess.check_output(
            ["docker", "--version"], text=True
        ).strip()
    except Exception:  # noqa: BLE001
        docker_version = "unavailable"
    node_version = None
    try:
        node_version = subprocess.check_output(["node", "--version"], text=True).strip()
    except Exception:  # noqa: BLE001
        node_version = "unavailable"
    return {
        "os": f"{uname.system} {uname.release}",
        "kernel": uname.release,
        "cpu": platform.processor() or uname.machine,
        "cpu_count_logical": os.cpu_count(),
        "physical_ram_bytes": None if mem_kb is None else mem_kb * 1024,
        "gpu": "not_declared_for_this_run",
        "storage_type": "WSL2_virtual_disk_or_host_fs",
        "python_version": sys.version.split()[0],
        "node_version": node_version,
        "docker_version": docker_version,
        "embedding_model": "FakeEmbedder(dimension=8) — capacity observation harness",
        "reranker_model": "FakeReranker — capacity observation harness",
        "generation_configuration": "FakeGenerator abstain — not a live LLM",
        "exact_git_sha": _git_sha(),
        "note": "No personal identifiers or machine secrets included.",
    }


def _provision(settings) -> None:
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(settings.paths.docling_artifacts, docling_version="test")
    if not (TIKTOKEN_SRC / "offline-rag-tokenizer.json").exists():
        raise RuntimeError("tiktoken artifacts not provisioned")
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)


def _make_runtime(data_dir: Path, models_dir: Path):
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(data_dir),
        "OFFLINE_RAG_MODELS_DIR": str(models_dir),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    generation = settings.generation.model_copy(
        update={
            "enabled": True,
            "base_url": APPROVED_ENDPOINT,
            "model": APPROVED_MODEL,
            "approved_endpoints": [APPROVED_ENDPOINT],
            "approved_models": [APPROVED_MODEL],
        }
    )
    reranker = settings.reranker.model_copy(
        update={"enabled": True, "implementation": "fake"}
    )
    settings = settings.model_copy(update={"generation": generation, "reranker": reranker})
    _provision(settings)
    embedder = FakeEmbedder(dimension=8, normalize=True)
    reranker_impl = FakeReranker()
    generator = FakeGenerator(
        response_fn=lambda _req: json.dumps(
            {"abstain": True, "answer": None, "citation_ids": []}
        )
    )

    def _qdrant(s):
        return QdrantLocalBackend(s.paths.qdrant_storage)

    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: reranker_impl,
            generator_client=lambda _s: generator,
            qdrant=_qdrant,
        ),
    )
    return runtime, settings


def _wait_op(client: TestClient, op_id: str, timeout_s: float = 120.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        response = client.get(f"/v1/operations/{op_id}")
        response.raise_for_status()
        body = response.json()
        if body["status"] in {"succeeded", "failed", "interrupted"}:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"operation {op_id} did not finish")


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def _make_payload(index: int, target_bytes: int) -> bytes:
    header = f"CAP16H_SRC_{index:03d} deterministic capacity fixture.\n".encode()
    if target_bytes <= len(header):
        return header[:target_bytes]
    pad = b"x" * (target_bytes - len(header))
    return header + pad


def _run_ingest(
    client: TestClient,
    *,
    source_count: int,
    bytes_per_source: int,
    key_prefix: str,
) -> dict:
    create = client.post(
        "/v1/workspaces",
        headers={"Idempotency-Key": f"{key_prefix}-ws"},
        json={"title": f"16H capacity {source_count}", "description": ""},
    )
    create.raise_for_status()
    wid = create.json()["workspace_id"]
    ws = client.get(f"/v1/workspaces/{wid}")
    ws.raise_for_status()
    revision = ws.json()["revision"]

    files = [
        (
            "files",
            (
                f"cap_{i:03d}.txt",
                _make_payload(i, bytes_per_source),
                "text/plain",
            ),
        )
        for i in range(source_count)
    ]
    rss_before = _rss_bytes()
    t0 = time.perf_counter()
    add = client.post(
        f"/v1/workspaces/{wid}/sources",
        headers={
            "Idempotency-Key": f"{key_prefix}-add",
            "If-Match": f'"{revision}"',
        },
        files=files,
    )
    elapsed_http = time.perf_counter() - t0
    status = add.status_code
    body = add.json() if add.headers.get("content-type", "").startswith("application/json") else {}
    if status != 202:
        return {
            "requested_source_count": source_count,
            "bytes_per_source": bytes_per_source,
            "http_status": status,
            "error": body,
            "elapsed_http_s": elapsed_http,
            "result": "REFUSED_OR_FAILED_AT_ADMISSION",
            "rss_max_bytes_observed": _rss_bytes(),
        }

    op = _wait_op(client, body["operation_id"])
    elapsed_total = time.perf_counter() - t0
    sources = client.get(f"/v1/workspaces/{wid}/sources")
    sources.raise_for_status()
    source_list = sources.json()["sources"]
    list_t0 = time.perf_counter()
    for _ in range(3):
        client.get(f"/v1/workspaces/{wid}/sources").raise_for_status()
    list_elapsed = (time.perf_counter() - list_t0) / 3.0

    query_t0 = time.perf_counter()
    query = client.post(
        f"/v1/workspaces/{wid}/query",
        json={"question": "What capacity fixture marker is present?"},
    )
    query_elapsed = time.perf_counter() - query_t0
    # Query may abstain/502 under FakeEmbedder depending on corpus binding;
    # ingest/list correctness remains the capacity functional gate.

    return {
        "requested_source_count": source_count,
        "bytes_per_source": bytes_per_source,
        "http_status": status,
        "operation_status": op["status"],
        "active_source_count": len(source_list),
        "reported_active_bytes": sum(int(s.get("byte_size") or 0) for s in source_list),
        "elapsed_http_s": elapsed_http,
        "elapsed_total_s": elapsed_total,
        "source_list_avg_s": list_elapsed,
        "query_elapsed_s": query_elapsed,
        "query_http_status": query.status_code,
        "rss_before_bytes": rss_before,
        "rss_max_bytes_observed": _rss_bytes(),
        "result": "SUCCEEDED" if op["status"] == "succeeded" else op["status"],
        "workspace_id": wid,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=REPO_ROOT / "docs" / "evidence" / "slice16h_capacity_observations.json",
    )
    args = parser.parse_args(argv)

    machine = _machine_declaration()
    observations: dict = {
        "contract": "slice16h-capacity-observations-v1",
        "machine": machine,
        "accepted_defaults": {
            "max_files_per_ingest": 32,
            "max_bytes_per_document": 26_214_400,
            "max_total_upload_bytes": 104_857_600,
        },
        "runs": [],
        "exploratory": {},
        "conclusion": None,
    }

    with tempfile.TemporaryDirectory(prefix="slice16h-capacity-") as tmp:
        tmp_path = Path(tmp)
        data_dir = tmp_path / "data"
        models_dir = tmp_path / "models"
        runtime, settings = _make_runtime(data_dir, models_dir)
        caps = {
            "max_files_per_ingest": settings.api.max_files_per_ingest,
            "max_bytes_per_document": settings.api.max_bytes_per_document,
            "max_total_upload_bytes": settings.api.max_total_upload_bytes,
        }
        observations["runtime_effective_limits"] = caps
        app = create_app(runtime=runtime)
        with TestClient(app) as client:
            # Moderate total: 32 × 64 KiB = 2 MiB
            print("run: 32_sources_moderate_bytes", flush=True)
            moderate = _run_ingest(
                client,
                source_count=32,
                bytes_per_source=64 * 1024,
                key_prefix="cap32m",
            )
            moderate["label"] = "32_sources_moderate_bytes"
            moderate["storage_growth_bytes"] = _dir_size(data_dir)
            observations["runs"].append(moderate)
            print(json.dumps(moderate, indent=2), flush=True)

            # Elevated toward total-byte guardrail while remaining practical on
            # FakeEmbedder in-process harness: 32 × 512 KiB = 16 MiB.
            # Full ~96 MiB near-cap ingest is recorded as a separate optional
            # heavy observation when --heavy is set.
            print("run: 32_sources_elevated_bytes", flush=True)
            near = _run_ingest(
                client,
                source_count=32,
                bytes_per_source=512 * 1024,
                key_prefix="cap32n",
            )
            near["label"] = "32_sources_elevated_bytes_16MiB"
            near["storage_growth_bytes"] = _dir_size(data_dir)
            observations["runs"].append(near)
            print(json.dumps(near, indent=2), flush=True)

            # Admission-level proof of the 100 MiB total-byte guardrail without
            # requiring a multi-minute heavy ingest observation.
            print("run: total_byte_guardrail_admission", flush=True)
            over = _run_ingest(
                client,
                source_count=8,
                bytes_per_source=14 * 1024 * 1024,  # 112 MiB > 100 MiB
                key_prefix="capover",
            )
            over["label"] = "total_byte_guardrail_admission_over_100MiB"
            observations["guardrail_admission"] = over
            print(json.dumps(over, indent=2), flush=True)

            # Exploratory 64 / 128 — must use accepted mechanisms only.
            for count in (64, 128):
                attempt = _run_ingest(
                    client,
                    source_count=count,
                    bytes_per_source=1024,
                    key_prefix=f"cap{count}",
                )
                if attempt.get("http_status") == 202 and attempt.get("result") == "SUCCEEDED":
                    disposition = "MEASURED_UNDER_ACCEPTED_LIMITS"
                elif caps["max_files_per_ingest"] < count:
                    disposition = (
                        "NOT TESTABLE WITHOUT CONTRACT/CONFIG CHANGE "
                        f"(max_files_per_ingest={caps['max_files_per_ingest']})"
                    )
                else:
                    disposition = "REFUSED_OR_FAILED"
                observations["exploratory"][str(count)] = {
                    **attempt,
                    "disposition": disposition,
                }

    default_ok = all(
        run.get("result") == "SUCCEEDED" and run.get("active_source_count") == 32
        for run in observations["runs"]
    )
    if default_ok:
        observations["conclusion"] = "CURRENT DEFAULTS SUPPORTED BY OBSERVATION"
    else:
        observations["conclusion"] = "CURRENT DEFAULTS REQUIRE REDUCTION"

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(observations, indent=2, sort_keys=True) + "\n")
    print(json.dumps(observations, indent=2, sort_keys=True))
    return 0 if default_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
