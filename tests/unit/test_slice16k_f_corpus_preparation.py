from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diag_16k_f import execution_harness
from scripts.diag_16k_f.execution_harness import (
    HarnessError,
    SourceFile,
    _validate_query_result,
    batch_sources,
    check_cache_state,
    compare_cold_warm,
    load_sources,
    run_cell,
    validate_capabilities,
    validate_robustness_case_evidence,
)
from scripts.diag_16k_f.prepare_corpus import (
    DUPLICATE_STATUS,
    ELIGIBLE_STATUS,
    OCR_STATUS,
    OVERSIZE_STATUS,
    PreparationError,
    build_primary_manifest,
    build_replacement_acceptance_manifest,
    build_single_source_manifest,
    inventory_directory,
    summarize_manifest,
    validate_replacement_manifest,
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


def test_replacement_manifest_keeps_all_paths_and_derives_eligible_population(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    first = corpus / "a.txt"
    first.write_bytes(b"first eligible text")
    (corpus / "a-copy.txt").write_bytes(first.read_bytes())
    second = corpus / "b.md"
    second.write_bytes(b"second eligible text")
    scan = corpus / "scan.pdf"
    scan.write_bytes(b"pdf bytes without native text")
    native_pdf = corpus / "native.pdf"
    native_pdf.write_bytes(b"pdf bytes with native text")
    inventory = inventory_directory(corpus)
    hashes = {row["relative_path"]: row["sha256"] for row in inventory["files"]}

    manifest = build_replacement_acceptance_manifest(
        corpus,
        inventory,
        {
            hashes["scan.pdf"]: {"classification": "NO_NATIVE_TEXT"},
            hashes["native.pdf"]: {"classification": "NATIVE_TEXT_ALL_PAGES"},
        },
    )
    eligible = validate_replacement_manifest(manifest)

    assert manifest["population_counts"]["admission_and_robustness_paths"] == 5
    assert manifest["population_counts"]["distinct_byte_identities"] == 4
    assert manifest["population_counts"][ELIGIBLE_STATUS] == 3
    assert manifest["population_counts"][OCR_STATUS] == 1
    assert manifest["population_counts"][OVERSIZE_STATUS] == 0
    assert manifest["population_counts"][DUPLICATE_STATUS] == 1
    assert {row["relative_path"] for row in eligible} == {
        "a-copy.txt",
        "b.md",
        "native.pdf",
    }
    assert len(manifest["representations"]) == 5
    scenarios = {
        row["scenario_id"]: row for row in manifest["robustness_matrix"]["scenarios"]
    }
    assert scenarios["individual_ocr_required_ingestion"]["case_count"] == 1
    assert scenarios["exact_duplicate_rejection"]["case_count"] == 1
    assert scenarios["mixed_valid_ocr_required_atomic_rejection"]["case_count"] == 1
    assert scenarios["mixed_valid_duplicate_atomic_rejection"]["case_count"] == 1
    assert scenarios["valid_retry_after_rejection"]["case_count"] == 1
    assert manifest["robustness_matrix"]["execution_status"] == "PREPARED_NOT_EXECUTED"
    assert "first eligible text" not in json.dumps(manifest)
    assert (
        manifest["workload_comparability"][
            "comparable_to_historical_39_primary_threshold_population"
        ]
        is False
    )

    manifest_path = tmp_path / "replacement.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    scan.write_bytes(b"changed after manifest freeze")
    with pytest.raises(HarnessError, match="corpus path changed"):
        load_sources(corpus, manifest_path)

    manifest_path = tmp_path / "replacement.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    scan.write_bytes(b"changed after manifest freeze")
    with pytest.raises(HarnessError, match="corpus path changed"):
        load_sources(corpus, manifest_path)


def test_replacement_manifest_classifies_over_limit_without_dropping_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.diag_16k_f import prepare_corpus

    monkeypatch.setattr(prepare_corpus, "MAX_PDF_BYTES", 10)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    oversized = corpus / "oversized.pdf"
    oversized.write_bytes(b"eleven bytes")
    inventory = inventory_directory(corpus)

    manifest = build_replacement_acceptance_manifest(corpus, inventory, {})

    assert manifest["population_counts"]["admission_and_robustness_paths"] == 1
    assert manifest["population_counts"][OVERSIZE_STATUS] == 1
    assert manifest["expected_rejection_cases"]["oversized"] == [
        {
            "relative_path": "oversized.pdf",
            "sha256": hashlib.sha256(b"eleven bytes").hexdigest(),
        }
    ]
    assert manifest["successful_ingestion_population"]["source_count"] == 0


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
    active_data_root = data_root
    operation_status = "succeeded"
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
            workspace_dir = active_data_root / "workspaces" / "ws_synthetic"
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
                    "status": operation_status,
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
                    }
                    if operation_status == "succeeded"
                    else None,
                    "error": None
                    if operation_status == "succeeded"
                    else {"code": "internal_error", "retryable": False},
                },
            )
        if (
            request.url.path == "/v1/workspaces/ws_synthetic/sources"
            and request.method == "GET"
        ):
            return httpx.Response(
                200,
                json={
                    "sources": [
                        {
                            "source_id": "src_synthetic",
                            "document_id": "doc_synthetic",
                        }
                    ]
                },
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
                    "citations": [
                        {
                            "source_id": "src_synthetic",
                            "document_id": "doc_synthetic",
                            "evidence_unit_id": "ev_synthetic",
                            "source_chunk_id": "chunk_synthetic",
                            "kind": "child",
                            "citation_ref": "c1",
                            "excerpt": "synthetic citation excerpt",
                        }
                    ],
                    "answer_blocks": [
                        {"text": "Synthetic claim", "citation_refs": ["c1"]}
                    ],
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
        reconnect_client_factory=lambda: httpx.Client(
            base_url="http://seneca.test",
            transport=httpx.MockTransport(respond),
        ),
    )
    serialized = output.read_text()

    assert evidence["source_count_published"] == 1
    assert evidence["operations"][0]["status"] == "succeeded"
    assert evidence["operations"][0]["reconnect_verified"] is True
    assert evidence["queries"][0]["citation_count"] == 1
    assert evidence["queries"][0]["validation_status"] == "PASS"
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

    active_data_root = tmp_path / "failed-data"
    active_data_root.mkdir()
    operation_status = "failed"
    failed_output = tmp_path / "failed-evidence.json"
    with pytest.raises(HarnessError, match="ended as failed"):
        run_cell(
            base_url="http://seneca.test",
            corpus_root=corpus,
            manifest_path=manifest_path,
            query_deck_path=query_deck,
            data_root=active_data_root,
            cache_state="cold",
            cell_id="synthetic-failure",
            authority="synthetic-only",
            output_path=failed_output,
            client=client,
            reconnect_client_factory=lambda: httpx.Client(
                base_url="http://seneca.test",
                transport=httpx.MockTransport(respond),
            ),
        )
    failed_evidence = json.loads(failed_output.read_text())
    assert failed_evidence["campaign_status"] == "FAILED"
    assert failed_evidence["operations"][0]["status"] == "failed"
    assert "private synthetic source body" not in failed_output.read_text()

    active_data_root = tmp_path / "watchdog-data"
    active_data_root.mkdir()
    operation_status = "running"
    watchdog_output = tmp_path / "watchdog-evidence.json"
    with pytest.raises(HarnessError, match="watchdog expired"):
        run_cell(
            base_url="http://seneca.test",
            corpus_root=corpus,
            manifest_path=manifest_path,
            query_deck_path=query_deck,
            data_root=active_data_root,
            cache_state="cold",
            cell_id="synthetic-watchdog",
            authority="synthetic-only",
            output_path=watchdog_output,
            poll_seconds=0.01,
            cell_watchdog_seconds=1,
            client=client,
            reconnect_client_factory=lambda: httpx.Client(
                base_url="http://seneca.test",
                transport=httpx.MockTransport(respond),
            ),
        )
    watchdog_evidence = json.loads(watchdog_output.read_text())
    assert watchdog_evidence["campaign_status"] == "FAILED"
    assert watchdog_evidence["operations"][0]["watchdog_expired"] is True
    assert watchdog_evidence["watchdog_semantics"] == (
        "safety_stop_only_no_operation_cancellation"
    )
    assert not any(request.method == "DELETE" for request in requests)

    client.close()


def test_cold_warm_comparison_requires_same_source_identity() -> None:
    cold = {
        "campaign_status": "COMPLETE",
        "cache_state": "cold",
        "cell_id": "full-cold",
        "source_identity_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "source_count_expected": 39,
        "aggregate_metrics": {
            "embeddings_generated": 100,
            "parsed_artifacts_generated": 10,
            "chunk_artifacts_generated": 10,
            "stage_durations_ms": {"dense_generation_ms": 2_000, "total_ms": 4_000},
        },
    }
    warm = {
        "campaign_status": "COMPLETE",
        "cache_state": "warm",
        "cell_id": "full-warm",
        "source_identity_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "source_count_expected": 39,
        "aggregate_metrics": {
            "embeddings_generated": 0,
            "parsed_artifacts_generated": 0,
            "chunk_artifacts_generated": 0,
            "stage_durations_ms": {"dense_generation_ms": 0, "total_ms": 500},
        },
    }

    cold_bytes_hash = hashlib.sha256(b"cold evidence").hexdigest()
    cold.update(
        {
            "pair_run_id": "pair-1",
            "pair_sequence": 1,
            "data_root_id": hashlib.sha256(b"root-1").hexdigest(),
            "completed_at": "2026-10-31T10:00:00Z",
            "manifest_sha256": "b" * 64,
            "source_count_expected": 39,
            "campaign_status": "COMPLETE",
        }
    )
    warm.update(
        {
            "pair_run_id": "pair-1",
            "pair_sequence": 2,
            "data_root_id": hashlib.sha256(b"root-1").hexdigest(),
            "started_at": "2026-10-31T10:00:01Z",
            "predecessor_evidence_sha256": cold_bytes_hash,
            "manifest_sha256": "b" * 64,
            "source_count_expected": 39,
            "campaign_status": "COMPLETE",
        }
    )
    report = compare_cold_warm(
        cold,
        warm,
        cold_evidence_sha256=cold_bytes_hash,
    )

    assert report["reductions"]["embeddings_generated"]["fractional_reduction"] == 1
    assert report["materiality_disposition"] == "REVIEW_AGAINST_ACCEPTED_CRITERIA"
    warm["source_identity_sha256"] = "b" * 64
    with pytest.raises(HarnessError, match="source identities do not match"):
        compare_cold_warm(
            cold,
            warm,
            cold_evidence_sha256=cold_bytes_hash,
        )


def test_cold_warm_comparison_requires_same_cache_root() -> None:
    cold = {
        "campaign_status": "COMPLETE",
        "cache_state": "cold",
        "pair_run_id": "pair-1",
        "pair_sequence": 1,
        "data_root_id": hashlib.sha256(b"root-1").hexdigest(),
        "completed_at": "2026-10-31T10:00:00Z",
        "source_identity_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "source_count_expected": 39,
        "aggregate_metrics": {},
    }
    cold_hash = hashlib.sha256(b"cold").hexdigest()
    warm = {
        "campaign_status": "COMPLETE",
        "cache_state": "warm",
        "pair_run_id": "pair-1",
        "pair_sequence": 2,
        "data_root_id": hashlib.sha256(b"root-2").hexdigest(),
        "started_at": "2026-10-31T10:00:01Z",
        "predecessor_evidence_sha256": cold_hash,
        "source_identity_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "source_count_expected": 39,
        "aggregate_metrics": {},
    }
    with pytest.raises(HarnessError, match="different data roots"):
        compare_cold_warm(cold, warm, cold_evidence_sha256=cold_hash)


def test_full_pair_runs_cold_then_warm_on_same_root_and_links_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    primary_sources = []
    for index in range(39):
        filename = f"primary-{index:02d}.txt"
        content = f"synthetic primary source {index}".encode()
        (corpus / filename).write_bytes(content)
        primary_sources.append(
            {
                "relative_path": filename,
                "byte_size": len(content),
                "media_type": "text/plain",
                "sha256": hashlib.sha256(content).hexdigest(),
                "logical_document_id": f"logical-{index:02d}",
                "role": "primary",
                "text_bearing": True,
            }
        )
    manifest = {
        "schema": "16k-f-primary-corpus-manifest-v1",
        "primary_document_count": 39,
        "primary_sources": primary_sources,
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_run_cell(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        sequence = kwargs["pair_sequence"]
        completed_at = "2026-10-31T10:00:00+00:00"
        evidence = {
            "schema": "16k-f-cell-evidence-v1",
            "campaign_status": "COMPLETE",
            "cell_id": kwargs["cell_id"],
            "cache_state": kwargs["cache_state"],
            "source_identity_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
            "source_count_expected": 39,
            "pair_run_id": kwargs["pair_run_id"],
            "pair_sequence": sequence,
            "data_root_id": hashlib.sha256(
                str(Path(kwargs["data_root"]).resolve()).encode()
            ).hexdigest(),
            "aggregate_metrics": {},
            "completed_at": completed_at,
        }
        if sequence == 2:
            evidence["started_at"] = "2026-10-31T10:00:01+00:00"
            evidence["predecessor_evidence_sha256"] = kwargs[
                "predecessor_evidence_sha256"
            ]
        output_path = Path(kwargs["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(evidence), encoding="utf-8")
        return evidence

    monkeypatch.setattr(execution_harness, "run_cell", fake_run_cell)
    data_root = tmp_path / "same-data-root"
    cold_output = tmp_path / "cold.json"
    warm_output = tmp_path / "warm.json"
    comparison_output = tmp_path / "comparison.json"
    comparison = execution_harness.run_full_cold_warm_pair(
        base_url="http://seneca.test",
        corpus_root=corpus,
        manifest_path=manifest_path,
        query_deck_path=tmp_path / "queries.json",
        data_root=data_root,
        authority="synthetic-only",
        cold_output_path=cold_output,
        warm_output_path=warm_output,
        comparison_output_path=comparison_output,
    )

    cold_evidence_hash = hashlib.sha256(cold_output.read_bytes()).hexdigest()
    assert [call["cache_state"] for call in calls] == ["cold", "warm"]
    assert all(call["data_root"] == data_root for call in calls)
    assert calls[0]["pair_run_id"] == calls[1]["pair_run_id"]
    assert calls[0]["pair_sequence"] == 1
    assert calls[1]["pair_sequence"] == 2
    assert calls[1]["predecessor_evidence_sha256"] == cold_evidence_hash
    assert comparison["cold_evidence_sha256"] == cold_evidence_hash
    assert comparison["same_data_root"] is True
    assert comparison["warm_follows_cold_evidence"] is True


@pytest.mark.parametrize("manifest_kind", ["single-source", "proxy"])
def test_full_pair_rejects_non_primary_manifest_before_api_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_kind: str,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "synthetic.txt"
    source.write_bytes(b"synthetic source")
    if manifest_kind == "single-source":
        manifest = build_single_source_manifest(
            corpus,
            inventory_directory(corpus),
            relative_path=source.name,
            text_bearing_confirmed=True,
        )
    else:
        manifest = {
            "schema_version": "offline-rag-corpus-manifest-v1",
            "documents": [{"source_path": source.name}],
        }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def unexpected_api_run(**_: object) -> dict[str, object]:
        pytest.fail("full-pair manifest guard must run before either cell")

    monkeypatch.setattr(execution_harness, "run_cell", unexpected_api_run)
    with pytest.raises(HarnessError, match="requires a primary corpus manifest"):
        execution_harness.run_full_cold_warm_pair(
            base_url="http://seneca.test",
            corpus_root=corpus,
            manifest_path=manifest_path,
            query_deck_path=tmp_path / "queries.json",
            data_root=tmp_path / "data",
            authority="synthetic-only",
            cold_output_path=tmp_path / "cold.json",
            warm_output_path=tmp_path / "warm.json",
            comparison_output_path=tmp_path / "comparison.json",
        )


def test_full_pair_accepts_verified_replacement_manifest_exact_count(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    paths = []
    for name, content in (
        ("a.txt", b"eligible source a"),
        ("b.md", b"eligible source b"),
    ):
        path = corpus / name
        path.write_bytes(content)
        paths.append(path)
    inventory = inventory_directory(corpus)
    manifest = build_replacement_acceptance_manifest(corpus, inventory, {})
    manifest_path = tmp_path / "replacement.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    sources, manifest_hash = load_sources(corpus, manifest_path)

    assert len(sources) == 2
    assert manifest_hash == manifest["manifest_sha256"]
    execution_harness._require_full_primary_manifest(manifest_path)

    changed = json.loads(json.dumps(manifest))
    changed["successful_ingestion_population"]["source_count"] = 39
    body = {key: value for key, value in changed.items() if key != "manifest_sha256"}
    changed["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(HarnessError, match="source count is inconsistent"):
        execution_harness._require_full_primary_manifest(manifest_path)


def test_full_pair_runs_replacement_population_without_fixed_39_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name, content in (
        ("a.txt", b"eligible source a"),
        ("b.md", b"eligible source b"),
    ):
        (corpus / name).write_bytes(content)
    manifest = build_replacement_acceptance_manifest(
        corpus,
        inventory_directory(corpus),
        {},
    )
    manifest_path = tmp_path / "replacement.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    source_count = manifest["successful_ingestion_population"]["source_count"]
    eligible_hash = manifest["successful_ingestion_population"]["sources"][0]["sha256"]
    query_deck_path = tmp_path / "queries.json"
    query_deck_path.write_text(
        json.dumps(
            {
                "corpus_candidate_sha256": manifest["manifest_sha256"],
                "questions": [
                    {
                        "query_id": "synthetic-q1",
                        "question": "synthetic question",
                        "target_source_sha256": eligible_hash,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    query_deck_sha256 = hashlib.sha256(query_deck_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        execution_harness,
        "PREPARED_REPLACEMENT_MANIFEST_SHA256",
        manifest["manifest_sha256"],
    )
    monkeypatch.setattr(
        execution_harness,
        "PREPARED_REPLACEMENT_QUERY_DECK_FILE_SHA256",
        query_deck_sha256,
    )
    calls: list[dict[str, object]] = []

    def fake_run_cell(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        sequence = kwargs["pair_sequence"]
        evidence: dict[str, object] = {
            "campaign_status": "COMPLETE",
            "cell_id": kwargs["cell_id"],
            "cache_state": kwargs["cache_state"],
            "source_identity_sha256": "a" * 64,
            "manifest_sha256": manifest["manifest_sha256"],
            "source_count_expected": source_count,
            "pair_run_id": kwargs["pair_run_id"],
            "pair_sequence": sequence,
            "data_root_id": hashlib.sha256(
                str(Path(kwargs["data_root"]).resolve()).encode()
            ).hexdigest(),
            "aggregate_metrics": {},
            "completed_at": "2026-10-31T10:00:00+00:00",
        }
        if sequence == 2:
            evidence["started_at"] = "2026-10-31T10:00:01+00:00"
            evidence["predecessor_evidence_sha256"] = kwargs[
                "predecessor_evidence_sha256"
            ]
        output_path = Path(kwargs["output_path"])
        output_path.write_text(json.dumps(evidence), encoding="utf-8")
        return evidence

    monkeypatch.setattr(execution_harness, "run_cell", fake_run_cell)
    result = execution_harness.run_full_cold_warm_pair(
        base_url="http://seneca.test",
        corpus_root=corpus,
        manifest_path=manifest_path,
        query_deck_path=query_deck_path,
        data_root=tmp_path / "data",
        authority="synthetic-only",
        approved_manifest_sha256=manifest["manifest_sha256"],
        approved_query_deck_file_sha256=query_deck_sha256,
        cold_output_path=tmp_path / "cold.json",
        warm_output_path=tmp_path / "warm.json",
        comparison_output_path=tmp_path / "comparison.json",
    )

    assert source_count == 2
    assert len(calls) == 2
    assert result["same_data_root"] is True


def test_replacement_artifacts_must_match_prepared_and_authority_digests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "candidate.txt"
    source.write_bytes(b"eligible source")
    manifest = build_replacement_acceptance_manifest(
        corpus,
        inventory_directory(corpus),
        {},
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    query_deck_path = tmp_path / "queries.json"
    query_deck = {
        "corpus_candidate_sha256": manifest["manifest_sha256"],
        "questions": [
            {
                "query_id": "q1",
                "question": "synthetic question",
                "target_source_sha256": manifest["successful_ingestion_population"][
                    "sources"
                ][0]["sha256"],
            }
        ],
    }
    query_deck_path.write_text(json.dumps(query_deck), encoding="utf-8")
    deck_sha = hashlib.sha256(query_deck_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        execution_harness,
        "PREPARED_REPLACEMENT_MANIFEST_SHA256",
        manifest["manifest_sha256"],
    )
    monkeypatch.setattr(
        execution_harness,
        "PREPARED_REPLACEMENT_QUERY_DECK_FILE_SHA256",
        deck_sha,
    )

    pins = execution_harness.verify_replacement_execution_artifact_pins(
        manifest_path,
        query_deck_path,
        approved_manifest_sha256=manifest["manifest_sha256"],
        approved_query_deck_file_sha256=deck_sha,
    )
    assert pins == {
        "manifest_sha256": manifest["manifest_sha256"],
        "query_deck_file_sha256": deck_sha,
    }

    with pytest.raises(HarnessError, match="authority manifest digest"):
        execution_harness.verify_replacement_execution_artifact_pins(
            manifest_path,
            query_deck_path,
            approved_manifest_sha256="0" * 64,
            approved_query_deck_file_sha256=deck_sha,
        )

    query_deck["questions"][0]["question"] = "changed question"
    query_deck_path.write_text(json.dumps(query_deck), encoding="utf-8")
    with pytest.raises(HarnessError, match="query deck differs"):
        execution_harness.verify_replacement_execution_artifact_pins(
            manifest_path,
            query_deck_path,
            approved_manifest_sha256=manifest["manifest_sha256"],
            approved_query_deck_file_sha256=deck_sha,
        )


def test_replacement_pin_mismatch_stops_before_api_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "eligible.txt"
    source.write_bytes(b"eligible source")
    manifest = build_replacement_acceptance_manifest(
        corpus,
        inventory_directory(corpus),
        {},
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    query_deck_path = tmp_path / "queries.json"
    query_deck_path.write_text(
        json.dumps(
            {
                "corpus_candidate_sha256": manifest["manifest_sha256"],
                "questions": [
                    {
                        "query_id": "q1",
                        "question": "synthetic question",
                        "target_source_sha256": manifest[
                            "successful_ingestion_population"
                        ]["sources"][0]["sha256"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    deck_sha = hashlib.sha256(query_deck_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        execution_harness,
        "PREPARED_REPLACEMENT_MANIFEST_SHA256",
        manifest["manifest_sha256"],
    )
    monkeypatch.setattr(
        execution_harness,
        "PREPARED_REPLACEMENT_QUERY_DECK_FILE_SHA256",
        deck_sha,
    )

    class UnexpectedApiClient:
        def get(self, *_: object, **__: object) -> object:
            pytest.fail("artifact pin mismatch must stop before API access")

        def post(self, *_: object, **__: object) -> object:
            pytest.fail("artifact pin mismatch must stop before API mutation")

    output_path = tmp_path / "evidence.json"
    with pytest.raises(HarnessError, match="authority manifest digest"):
        run_cell(
            base_url="http://seneca.test",
            corpus_root=corpus,
            manifest_path=manifest_path,
            query_deck_path=query_deck_path,
            data_root=tmp_path / "data",
            cache_state="cold",
            cell_id="synthetic-pin-check",
            authority="synthetic-only",
            approved_manifest_sha256="0" * 64,
            approved_query_deck_file_sha256=deck_sha,
            output_path=output_path,
            client=UnexpectedApiClient(),  # type: ignore[arg-type]
        )
    failure_evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert failure_evidence["campaign_status"] == "FAILED"
    assert failure_evidence["failure_type"] == "HarnessError"


@pytest.mark.parametrize(
    ("category", "reason", "http_status", "operation_status", "retry_required"),
    [
        ("oversized", "source_file_too_large", 413, None, False),
        ("ocr_required", "ocr_required", 202, "failed", True),
        ("duplicate", "document_identity_conflict", 422, None, False),
    ],
)
def test_robustness_evidence_checks_rejection_atomicity_and_retry(
    category: str,
    reason: str,
    http_status: int,
    operation_status: str | None,
    retry_required: bool,
) -> None:
    before = {
        "revision": 4,
        "snapshot_id": "snap-before",
        "source_count": 2,
        "source_identity_sha256": "a" * 64,
    }
    record: dict[str, object] = {
        "schema": "16k-f-robustness-case-evidence-v1",
        "case_id": f"synthetic-{category}",
        "expected_failure_category": category,
        "input_source_sha256s": ["b" * 64],
        "before": before,
        "rejection": {
            "http_status": http_status,
            "operation_status": operation_status,
            "safe_error_code": "document_invalid",
            "reason": reason,
        },
        "after": dict(before),
        "readiness_http_status": 200,
        "retry_required": retry_required,
        "retry": {
            "status": "succeeded",
            "revision": 5,
            "snapshot_id": "snap-after-retry",
            "source_count": 3,
            "source_identity_sha256": "c" * 64,
            "readiness_http_status": 200,
        }
        if retry_required
        else None,
    }

    summary = validate_robustness_case_evidence(record)

    assert summary["publication_unchanged"] is True
    assert summary["validation_status"] == "PASS"
    assert summary["retry_status"] == ("succeeded" if retry_required else None)

    changed_state = json.loads(json.dumps(record))
    changed_state["after"]["revision"] = before["revision"] + 1
    with pytest.raises(HarnessError, match="changed the published workspace"):
        validate_robustness_case_evidence(changed_state)


def test_markdown_parser_acceptance_smoke(tmp_path: Path) -> None:
    from offline_rag.core.ids import document_id_from_bytes
    from offline_rag.domain.blocks import ContentType
    from offline_rag.ingestion.markdown_parser import MarkdownParser

    raw = b"# Incident Plan\n\nStage the rescue line before entry.\n"
    path = tmp_path / "incident-plan.md"
    path.write_bytes(raw)
    parsed = MarkdownParser().parse(
        path,
        source_bytes=raw,
        document_id=document_id_from_bytes(raw),
    )

    assert any(block.content_type == ContentType.HEADING for block in parsed.blocks)
    assert any("rescue line" in block.text for block in parsed.blocks)


def test_query_validation_rejects_abstention_and_unmapped_citation() -> None:
    active_sources = [{"source_id": "src-1", "document_id": "doc-1"}]
    valid = {
        "status": "answered",
        "answer": "Synthetic grounded answer.",
        "citations": [
            {
                "source_id": "src-1",
                "document_id": "doc-1",
                "evidence_unit_id": "ev-1",
                "source_chunk_id": "chunk-1",
                "kind": "child",
                "citation_ref": "c1",
                "excerpt": "synthetic excerpt",
            }
        ],
        "answer_blocks": [{"text": "Synthetic claim", "citation_refs": ["c1"]}],
    }
    valid.update({"workspace_revision": 2, "snapshot_id": "snap-1"})
    assert _validate_query_result(
        valid,
        active_sources,
        expected_revision=2,
        expected_snapshot_id="snap-1",
    )["valid_source_mappings"]

    abstention = {**valid, "status": "model_abstain", "citations": []}
    with pytest.raises(HarnessError, match="grounded answered status"):
        _validate_query_result(
            abstention,
            active_sources,
            expected_revision=2,
            expected_snapshot_id="snap-1",
        )

    unmapped = json.loads(json.dumps(valid))
    unmapped["citations"][0]["source_id"] = "src-unknown"
    with pytest.raises(HarnessError, match="does not map to an active source"):
        _validate_query_result(
            unmapped,
            active_sources,
            expected_revision=2,
            expected_snapshot_id="snap-1",
        )
