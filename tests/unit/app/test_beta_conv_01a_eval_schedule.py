from __future__ import annotations

from copy import deepcopy

import pytest
from scripts.beta_conv_01a_eval_schedule import (
    build_schedule,
    validate_counterbalanced_schedule,
)


def test_schedule_candidates_cover_each_attempt_once_and_match_warm_pairs() -> None:
    case_ids = [f"heldout-{index:03d}" for index in range(120)]

    schedule = build_schedule(case_ids, seed="schedule-test-seed")

    assert schedule["case_count"] == 120
    assert schedule["attempt_count_per_alternative"] == 720
    assert schedule["execution_choice"] == "PENDING_SEPARATE_AUTHORITY"
    assert schedule["preferred_for_methodology_review"] == (
        "counterbalanced_serialized"
    )
    for name in ("serialized", "interleaved"):
        section = schedule[name]
        attempts = section["attempts"]
        assert len(attempts) == 720
        assert (
            len({(row["case_id"], row["arm"], row["repeat"]) for row in attempts})
            == 720
        )
        assert len(section["predeclared_warm_pairs"]) == 359
        assert sum(row["measurement_phase"] == "cold_start" for row in attempts) == 2

    counterbalanced = schedule["counterbalanced_serialized"]
    attempts = counterbalanced["attempts"]
    assert len(attempts) == 720
    assert len(counterbalanced["predeclared_warm_pairs"]) == 357
    assert counterbalanced["cold_observation_count"] == 6
    assert sum(row["measurement_phase"] == "cold_start" for row in attempts) == 6
    assert schedule["router_mode_execution"]["counterbalanced_session_count"] == 6
    assert schedule["router_mode_execution"]["counterbalanced_controlled_restarts"] == 5

    session_order = [
        (repeat, arm)
        for _order, repeat, arm in sorted(
            {(row["session_order"], row["repeat"], row["arm"]) for row in attempts}
        )
    ]
    assert session_order == [
        (1, "legacy"),
        (1, "planner"),
        (2, "planner"),
        (2, "legacy"),
        (3, "legacy"),
        (3, "planner"),
    ]


def test_schedule_is_deterministic_and_rejects_non_120_population() -> None:
    case_ids = [f"heldout-{index:03d}" for index in range(120)]
    assert build_schedule(case_ids, seed="same") == build_schedule(
        case_ids, seed="same"
    )

    try:
        build_schedule(case_ids[:-1], seed="same")
    except ValueError as exc:
        assert "exactly 120" in str(exc)
    else:
        raise AssertionError("incomplete held-out population was accepted")


def test_counterbalanced_schedule_rejects_missing_session_cold_observation() -> None:
    case_ids = [f"heldout-{index:03d}" for index in range(120)]
    attempts = build_schedule(case_ids, seed="schedule-test-seed")[
        "counterbalanced_serialized"
    ]["attempts"]
    malformed_attempts = deepcopy(attempts)
    malformed_attempts[0]["measurement_phase"] = "warm_interactive"

    with pytest.raises(ValueError, match="first attempt in every session must be cold"):
        validate_counterbalanced_schedule(case_ids, malformed_attempts)


def test_counterbalanced_schedule_rejects_mixed_case_order_within_pair() -> None:
    case_ids = [f"heldout-{index:03d}" for index in range(120)]
    attempts = build_schedule(case_ids, seed="schedule-test-seed")[
        "counterbalanced_serialized"
    ]["attempts"]
    malformed_attempts = deepcopy(attempts)
    planner_rows = sorted(
        (
            row
            for row in malformed_attempts
            if row["repeat"] == 1 and row["arm"] == "planner"
        ),
        key=lambda row: row["order"],
    )
    planner_rows[0]["case_id"], planner_rows[1]["case_id"] = (
        planner_rows[1]["case_id"],
        planner_rows[0]["case_id"],
    )

    with pytest.raises(ValueError, match="identical case order per repeat"):
        validate_counterbalanced_schedule(case_ids, malformed_attempts)
