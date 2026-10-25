"""Deterministic unit checks for the L4 capacity instrumentation primitives."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diag_large_source_capacity import common, run_capacity_harness


def test_windowed_rss_sampler_records_current_and_parser_peak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = iter([100, 120, 180, 140, 160, 190])
    monkeypatch.setattr(common, "current_rss_bytes", lambda: next(values, 190))
    monkeypatch.setattr(
        common,
        "_gpu_snapshot",
        lambda: {"status": "unavailable", "reason": "test"},
    )
    stage = {"value": "pdf_parsing"}
    sampler = common.ProcessSampler(
        stage_provider=lambda: stage["value"],
        rss_interval_s=0.01,
        gpu_interval_s=60.0,
        max_samples=20,
    )
    sampler.start()
    time.sleep(0.04)
    stage["value"] = "finalization"
    sampler.stop()

    summary = sampler.summary()
    assert summary["rss_start_bytes"] == 100
    assert summary["rss_peak_window_bytes"] >= 180
    assert summary["rss_delta_from_start_bytes"] >= 80
    assert summary["parser"]["status"] == "observed"
    assert summary["parser"]["peak_kind"] == "observed_sampled_peak"
    assert summary["sample_timeline"][0]["gpu"]["status"] == "unavailable"


def test_disk_tracker_reports_per_root_and_non_nested_aggregate(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    (parent / "one.bin").write_bytes(b"one")
    (child / "two.bin").write_bytes(b"two-two")
    tracker = common.DiskUsageTracker(
        {"parent": parent, "nested_child": child}, tmp_path
    )
    before = tracker.summary()
    (child / "three.bin").write_bytes(b"three")
    after = tracker.summary()

    assert (
        after["roots"]["parent"]["final_bytes"]
        > before["roots"]["parent"]["final_bytes"]
    )
    assert after["aggregate"]["final_bytes"] == after["roots"]["parent"]["final_bytes"]
    assert after["roots"]["parent"]["peak_growth_bytes"] >= len(b"three")


def test_cpu_metrics_labels_process_equivalent_cpu_percentage() -> None:
    before = {
        "status": "observed",
        "user_s": 1.0,
        "system_s": 2.0,
        "voluntary_context_switches": 4,
        "involuntary_context_switches": 5,
    }
    after = {
        "status": "observed",
        "user_s": 2.5,
        "system_s": 2.5,
        "voluntary_context_switches": 7,
        "involuntary_context_switches": 6,
    }
    result = common.cpu_metrics(before, after, 2.0)
    assert result["cpu_total_s"] == 2.0
    assert result["cpu_equivalent_pct"] == 100.0
    assert result["voluntary_context_switches"] == 3


def test_stage_tracker_uses_existing_stage_and_document_boundaries() -> None:
    tracker = common.StageTracker()
    tracker.set_stage("upload")
    tracker.before_stage("ingest")
    tracker.document_phase(
        type("Event", (), {"phase": "parsing", "source_name": "source.pdf"})()
    )
    tracker.document_phase(
        type("Event", (), {"phase": "parsed", "source_name": "source.pdf"})()
    )
    assert [event["stage"] for event in tracker.transitions] == [
        "upload",
        "ingest",
        "pdf_parsing",
        "ingest",
    ]
    assert tracker.stage_at() == "ingest"


def test_harness_limits_are_isolated_from_product_defaults(tmp_path: Path) -> None:
    defaults = run_capacity_harness._settings(
        tmp_path / "defaults", max_document=None, max_total=None
    )
    overridden = run_capacity_harness._settings(
        tmp_path / "override",
        max_document=512 * 1024 * 1024,
        max_total=1024 * 1024 * 1024,
    )
    assert defaults.api.max_bytes_per_document == 25 * 1024 * 1024
    assert defaults.api.max_total_upload_bytes == 100 * 1024 * 1024
    assert overridden.api.max_bytes_per_document == 512 * 1024 * 1024
    assert overridden.api.max_total_upload_bytes == 1024 * 1024 * 1024


def test_fixture_identity_contains_digest_without_source_text(tmp_path: Path) -> None:
    source = tmp_path / "fixture.pdf"
    source.write_bytes(b"PDF fixture marker")
    identity = common.fixture_identity(source, label="unit")
    assert identity["byte_size"] == len(b"PDF fixture marker")
    assert len(identity["sha256"]) == 64
    assert "PDF fixture marker" not in common.sanitized_json(identity)
