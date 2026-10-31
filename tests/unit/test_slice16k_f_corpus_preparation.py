from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diag_16k_f.execution_harness import (
    HarnessError,
    SourceFile,
    batch_sources,
    check_cache_state,
    compare_cold_warm,
    run_cell,
    validate_capabilities,
)
from scripts.diag_16k_f.prepare_corpus import (
    PreparationError,
    build_primary_manifest,
    build_single_source_manifest,
    inventory_directory,
    summarize_manifest,
)


def _corpus_and_roster(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sources: list[dict[str, object]] = []
    primary_content: dict[str, bytes] = {}

    for index in range(39):
        logical_id = f"logical-{index:02d}"
        relative_path = f"primary/{logical_id}.txt"
        content = f"private synthetic body {index}".encode()
        primary_content[logical_id] = content
        path = corpus / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        sources.append(
            {
                "relative_path": relative_path,
                "logical_document_id": logical_id,
                "role": "primary",
                "text_bearing": True,
                "representation": "txt",
            }
        )

    for index in range(3):
        logical_id = f"logical-{index:02d}"
        relative_path = f"alternates/{logical_id}-alternate.txt"
        path = corpus / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(primary_content[logical_id])
        sources.append(
            {
                "relative_path": relative_path,
                "logical_document_id": logical_id,
                "role": "alternate",
                "text_bearing": True,
                "representation": "alternate-txt",
            }
        )

    for index in range(3):
        relative_path = f"ocr-only/scan-{index}.pdf"
        path = corpus / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"synthetic OCR-only bytes {index}".encode())
        sources.append(
            {
                "relative_path": relative_path,
                "logical_document_id": None,
                "role": "ocr_excluded",
                "text_bearing": False,
                "representation": "scan",
            }
        )

    roster: dict[str, object] = {
        "schema": "16k-f-source-roster-v1",
        "sources": sources,
    }
    return corpus, roster


def test_inventory_uses_streaming_hashes_and_ignores_unsupported_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "a.txt"
    source.write_bytes(b"synthetic text body")
    (corpus / "unrelated.bin").write_bytes(b"ignored")

    def fail_read_bytes(_self: Path) -> bytes:
        raise AssertionError("whole-file read is forbidden")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    inventory = inventory_directory(corpus)

    assert inventory["supported_file_count"] == 1
    assert inventory["ignored_file_count"] == 1
    assert inventory["files"][0]["byte_size"] == len(b"synthetic text body")
    assert inventory["files"][0]["sha256"] == (
        "057fc379aeb4181917fe26854ecd54a0cec56ae09608d6c23aff06242ff70edb"
    )


def test_manifest_uses_explicit_logical_roster_and_reports_capacity(
    tmp_path: Path,
) -> None:
    corpus, roster = _corpus_and_roster(tmp_path)
    inventory = inventory_directory(corpus)

    manifest = build_primary_manifest(
        corpus,
        inventory,
        roster,
        workspace_byte_limit=1,
    )
    summary = summarize_manifest(manifest)

    assert summary["supplied_file_count"] == 45
    assert summary["primary_document_count"] == 39
    assert summary["non_ocr_representation_count"] == 42
    assert summary["ocr_exclusion_count"] == 3
    assert summary["workspace_capacity_preflight"] == "BLOCKED"
    assert summary["largest_text_bearing_bytes"] > 0


def test_manifest_reports_unconfigured_workspace_byte_ceiling(
    tmp_path: Path,
) -> None:
    corpus, roster = _corpus_and_roster(tmp_path)
    inventory = inventory_directory(corpus)

    manifest = build_primary_manifest(corpus, inventory, roster)

    assert manifest["workspace_byte_limit"] is None
    assert manifest["workspace_capacity_preflight"] == "NO_CONFIGURED_CEILING"


def test_single_source_manifest_requires_explicit_text_bearing_confirmation(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "candidate.pdf"
    source.write_bytes(b"synthetic pdf bytes")
    inventory = inventory_directory(corpus)

    with pytest.raises(PreparationError, match="text-bearing confirmation"):
        build_single_source_manifest(
            corpus,
            inventory,
            relative_path="candidate.pdf",
            text_bearing_confirmed=False,
        )

    manifest = build_single_source_manifest(
        corpus,
        inventory,
        relative_path="candidate.pdf",
        text_bearing_confirmed=True,
    )

    assert manifest["source_count"] == 1
    assert manifest["source"]["text_bearing"] is True
    assert "synthetic pdf bytes" not in json.dumps(manifest)


def test_manifest_excludes_source_text_and_is_deterministic(tmp_path: Path) -> None:
    corpus, roster = _corpus_and_roster(tmp_path)
    inventory = inventory_directory(corpus)
    manifest_a = build_primary_manifest(corpus, inventory, roster)
    manifest_b = build_primary_manifest(corpus, inventory, roster)

    serialized = json.dumps(manifest_a, sort_keys=True)
    assert "private synthetic body" not in serialized
    assert manifest_a["manifest_sha256"] == manifest_b["manifest_sha256"]


def test_manifest_rejects_missing_source_and_wrong_ocr_classification(
    tmp_path: Path,
) -> None:
    corpus, roster = _corpus_and_roster(tmp_path)
    inventory = inventory_directory(corpus)
    missing_roster = json.loads(json.dumps(roster))
    missing_roster["sources"][0]["relative_path"] = "missing.txt"

    with pytest.raises(PreparationError, match="absent from the inventory"):
        build_primary_manifest(corpus, inventory, missing_roster)

    wrong_ocr_roster = json.loads(json.dumps(roster))
    wrong_ocr_roster["sources"][-1]["text_bearing"] = True
    with pytest.raises(PreparationError, match="OCR-only exclusions"):
        build_primary_manifest(corpus, inventory, wrong_ocr_roster)


def test_upload_batches_respect_request_file_and_byte_limits() -> None:
    sources = [
        SourceFile(f"{index}.txt", 4, "text/plain", f"{index:064x}")
        for index in range(5)
    ]

    batches = batch_sources(sources, max_files=3, max_bytes=12)

    assert [len(batch) for batch in batches] == [3, 2]
    assert all(sum(item.byte_size for item in batch) <= 12 for batch in batches)


def test_cold_cache_preflight_rejects_existing_product_artifacts(
    tmp_path: Path,
) -> None:
    (tmp_path / "processed").mkdir()
    (tmp_path / "processed" / "old.json").write_text("{}")

    with pytest.raises(HarnessError, match="prior runtime artifacts"):
        check_cache_state(tmp_path, "cold")


def test_capability_preflight_preserves_transport_and_unconfigured_capacity() -> None:
    source = SourceFile("small.txt", 10, "text/plain", "a" * 64)
    capabilities = {
        "transport_limits": {
            "max_files_per_upload_request": 32,
            "max_bytes_per_uploaded_file": 25 * 1024 * 1024,
            "max_bytes_per_upload_request": 100 * 1024 * 1024,
        },
        "workspace_capacity": {
            "max_active_source_bytes": None,
            "max_active_sources": None,
        },
        "large_pdf": {"runtime_eligible": False, "effective_max_bytes": 0},
        "embedding": {"profile_id": "cuda_fp16_v1"},
    }

    result = validate_capabilities(capabilities, [source])

    assert result["workspace_max_active_source_bytes"] is None
    assert result["max_bytes_per_upload_request"] == 100 * 1024 * 1024


def test_synthetic_api_cell_records_sanitized_durable_evidence(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "synthetic.txt"
    source.write_bytes(b"private synthetic source body")
    inventory = inventory_directory(corpus)
    manifest = build_single_source_manifest(
        corpus,
        inventory,
        relative_path=source.name,
        text_bearing_confirmed=True,
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    query_deck = tmp_path / "queries.json"
    query_deck.write_text(
        json.dumps({"questions": [{"query_id": "q1", "question": "private question"}]})
    )
    output = tmp_path / "evidence.json"
    data_root = tmp_path / "isolated-data"
    data_root.mkdir()
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/health/ready":
            return httpx.Response(200, json={"status": "ready"})
        if request.url.path == "/v1/capabilities":
            return httpx.Response(
                200,
                json={
                    "transport_limits": {
                        "max_files_per_upload_request": 32,
                        "max_bytes_per_uploaded_file": 25 * 1024 * 1024,
                        "max_bytes_per_upload_request": 100 * 1024 * 1024,
                    },
                    "workspace_capacity": {
                        "max_active_source_bytes": None,
                        "max_active_sources": None,
                    },
                    "large_pdf": {
                        "runtime_eligible": False,
                        "effective_max_bytes": 25 * 1024 * 1024,
                        "qualified_profiles": [],
                    },
                    "embedding": {"profile_id": "cuda_fp16_v1"},
                },
            )
        if request.url.path == "/v1/workspaces" and request.method == "POST":
            workspace_dir = data_root / "workspaces" / "ws_synthetic"
            workspace_dir.mkdir(parents=True)
            (workspace_dir / "workspace.json").write_text(
                json.dumps({"workspace_id": "ws_synthetic"})
            )
            return httpx.Response(
                201,
                json={"workspace_id": "ws_synthetic", "revision": 1},
            )
        if (
            request.url.path == "/v1/workspaces/ws_synthetic/sources"
            and request.method == "POST"
        ):
            return httpx.Response(202, json={"operation_id": "op_synthetic"})
        if request.url.path == "/v1/operations/op_synthetic":
            return httpx.Response(
                200,
                json={
                    "operation_id": "op_synthetic",
                    "kind": "source_add",
                    "status": "succeeded",
                    "progress_stage": "ready",
                    "progress": None,
                    "metrics": {
                        "post_active_source_count": 1,
                        "requested_document_count": 1,
                        "uploaded_raw_bytes": source.stat().st_size,
                        "child_chunk_count": 1,
                        "parsed_artifacts_generated": 1,
                        "parsed_artifacts_reused": 0,
                        "chunk_artifacts_generated": 1,
                        "chunk_artifacts_reused": 0,
                        "embeddings_generated": 1,
                        "embeddings_reused": 0,
                        "embeddings_failed": 0,
                        "stage_durations": {
                            "parsing_ms": 1,
                            "chunking_ms": 1,
                            "dense_generation_ms": 1,
                            "dense_materialization_ms": 1,
                            "lexical_ms": 1,
                            "publication_ms": 1,
                            "finalization_ms": 1,
                            "total_ms": 10,
                        },
                    },
                    "worklist": {
                        "total_document_count": 1,
                        "pending_count": 0,
                        "completed_count": 1,
                        "remaining_count": 0,
                        "documents": [{"display_name": "synthetic.txt"}],
                    },
                    "result": {
                        "workspace_revision": 2,
                        "workspace_status": "active",
                        "snapshot_id": "snap_synthetic",
                        "source_count": 1,
                    },
                    "error": None,
                },
            )
        if (
            request.url.path == "/v1/workspaces/ws_synthetic/sources"
            and request.method == "GET"
        ):
            return httpx.Response(
                200,
                json={"sources": [{"source_id": "src_synthetic"}]},
            )
        if request.url.path == "/v1/workspaces/ws_synthetic":
            return httpx.Response(
                200,
                json={
                    "workspace_id": "ws_synthetic",
                    "revision": 2,
                    "source_count": 1,
                    "current_snapshot_id": "snap_synthetic",
                },
            )
        if request.url.path == "/v1/workspaces/ws_synthetic/query":
            return httpx.Response(
                200,
                json={
                    "status": "answered",
                    "workspace_revision": 2,
                    "snapshot_id": "snap_synthetic",
                    "citations": [{}],
                    "answer": "private answer",
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.Client(
        base_url="http://seneca.test",
        transport=httpx.MockTransport(respond),
    )
    evidence = run_cell(
        base_url="http://seneca.test",
        corpus_root=corpus,
        manifest_path=manifest_path,
        query_deck_path=query_deck,
        data_root=data_root,
        cache_state="cold",
        cell_id="synthetic",
        authority="synthetic-only",
        output_path=output,
        client=client,
    )
    serialized = output.read_text()

    assert evidence["source_count_published"] == 1
    assert evidence["operations"][0]["status"] == "succeeded"
    assert evidence["queries"][0]["citation_count"] == 1
    assert evidence["aggregate_metrics"]["embeddings_generated"] == 1
    assert "private synthetic source body" not in serialized
    assert "private question" not in serialized
    assert "private answer" not in serialized
    add_request = next(
        request
        for request in requests
        if request.url.path == "/v1/workspaces/ws_synthetic/sources"
        and request.method == "POST"
    )
    assert add_request.headers["if-match"] == '"1"'

    client.close()


def test_cold_warm_comparison_requires_same_source_identity() -> None:
    cold = {
        "cache_state": "cold",
        "cell_id": "full-cold",
        "source_identity_sha256": "a" * 64,
        "aggregate_metrics": {
            "embeddings_generated": 100,
            "parsed_artifacts_generated": 10,
            "chunk_artifacts_generated": 10,
            "stage_durations_ms": {"dense_generation_ms": 2_000, "total_ms": 4_000},
        },
    }
    warm = {
        "cache_state": "warm",
        "cell_id": "full-warm",
        "source_identity_sha256": "a" * 64,
        "aggregate_metrics": {
            "embeddings_generated": 0,
            "parsed_artifacts_generated": 0,
            "chunk_artifacts_generated": 0,
            "stage_durations_ms": {"dense_generation_ms": 0, "total_ms": 500},
        },
    }

    report = compare_cold_warm(cold, warm)

    assert report["reductions"]["embeddings_generated"]["fractional_reduction"] == 1
    assert report["materiality_disposition"] == "REVIEW_AGAINST_ACCEPTED_CRITERIA"
    warm["source_identity_sha256"] = "b" * 64
    with pytest.raises(HarnessError, match="source identities do not match"):
        compare_cold_warm(cold, warm)
