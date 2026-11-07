from __future__ import annotations

from scripts.beta_conv_01a_eval_schedule import build_schedule


def test_schedule_candidates_cover_each_attempt_once_and_match_warm_pairs() -> None:
    case_ids = [f"heldout-{index:03d}" for index in range(120)]

    schedule = build_schedule(case_ids, seed="schedule-test-seed")

    assert schedule["case_count"] == 120
    assert schedule["attempt_count_per_alternative"] == 720
    assert schedule["execution_choice"] == "PENDING_SEPARATE_AUTHORITY"
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
