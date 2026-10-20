"""Focused tests for 16K-D D1 scientific harness (no model execution)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON_PATH = ROOT / "scripts/diag_16k_d_dense/d1_common.py"


def _load_common():
    spec = importlib.util.spec_from_file_location("d1_common", COMMON_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_d1b_encode_order_is_counterbalanced_six_each() -> None:
    common = _load_common()
    assert len(common.D1B_ENCODE_ORDER) == 36
    for idx in common.D1B_BATCH_INDICES:
        assert common.D1B_ENCODE_ORDER.count(idx) == 6
    # P1 / P2 / P3 blocks
    assert list(common.D1B_ENCODE_ORDER[:12]) == [
        1,
        14,
        14,
        1,
        1,
        14,
        14,
        1,
        1,
        14,
        14,
        1,
    ]
    assert list(common.D1B_ENCODE_ORDER[12:24]) == [
        17,
        13,
        13,
        17,
        17,
        13,
        13,
        17,
        17,
        13,
        13,
        17,
    ]
    assert list(common.D1B_ENCODE_ORDER[24:]) == [
        4,
        6,
        6,
        4,
        4,
        6,
        6,
        4,
        4,
        6,
        6,
        4,
    ]


def test_d1b_schedule_repetitions() -> None:
    common = _load_common()
    schedule = common.d1b_schedule()
    assert len(schedule) == 36
    assert schedule[0]["batch_index"] == 1 and schedule[0]["repetition"] == 1
    assert schedule[1]["batch_index"] == 14 and schedule[1]["repetition"] == 1
    assert schedule[2]["batch_index"] == 14 and schedule[2]["repetition"] == 2
    assert {s["batch_index"] for s in schedule} == set(common.D1B_BATCH_INDICES)


def test_enrich_wall_minus_device() -> None:
    common = _load_common()
    observed = common.enrich_batch_wall_minus_device(
        {
            "encode_ms": 100.0,
            "encode_cuda_device_ms": 80.0,
            "encode_cuda_device_status": "observed",
        }
    )
    assert observed["wall_minus_device_ms"] == pytest.approx(20.0)
    missing = common.enrich_batch_wall_minus_device(
        {
            "encode_ms": 100.0,
            "encode_cuda_device_ms": None,
            "encode_cuda_device_status": "unavailable",
        }
    )
    assert missing["wall_minus_device_ms"] is None


def test_frozen_d1b_cells_match_matrix() -> None:
    common = _load_common()
    assert common.D1B_BATCH_INDICES == (1, 14, 17, 13, 4, 6)
    assert common.D1B_CELL_BY_INDEX[1] == "F1"
    assert common.D1B_CELL_BY_INDEX[14] == "S1"
    assert common.D1B_CELL_BY_INDEX[4] == "D1"
    assert common.D1B_CELL_BY_INDEX[6] == "D2"


def test_expected_workload_constants() -> None:
    common = _load_common()
    assert common.EXPECTED_CHILD_COUNT == 1296
    assert common.EXPECTED_BATCH_SIZE == 32
    assert common.EXPECTED_BATCH_COUNT == 41
    assert common.MATRIX_PARENT.startswith("0ecf2f74")
    assert common.TOOLING_SUBJECT.startswith("43372595")
