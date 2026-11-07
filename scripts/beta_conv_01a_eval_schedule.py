"""Build unexecuted deterministic held-out schedule candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = REPO_ROOT / "artifacts/beta_conv_01a_eval_prep_01"
HELD_OUT_PATH = PRIVATE_ROOT / "requests_held_out_candidate.jsonl"
SCHEDULE_PATH = PRIVATE_ROOT / "execution_schedule_candidate.json"
ARM_NAMES = ("legacy", "planner")
REPETITIONS = 3
CASE_COUNT = 120


def read_case_ids(path: Path = HELD_OUT_PATH) -> list[str]:
    """Read only held-out IDs; do not expose or score request contents."""
    case_ids: list[str] = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            case_id = row.get("case_id")
            if not isinstance(case_id, str) or not case_id:
                raise ValueError("held-out row has invalid case identity")
            case_ids.append(case_id)
    if len(case_ids) != CASE_COUNT or len(case_ids) != len(set(case_ids)):
        raise ValueError("held-out candidate must contain exactly 120 unique IDs")
    return case_ids


def _ordered_case_ids(case_ids: list[str], seed: str) -> list[str]:
    return sorted(
        case_ids,
        key=lambda case_id: hashlib.sha256(f"{seed}\0{case_id}".encode()).hexdigest(),
    )


def _attempt(
    case_id: str,
    arm: str,
    repeat: int,
    order: int,
    cold_seen: set[str],
) -> dict[str, Any]:
    phase = "cold_start" if arm not in cold_seen else "warm_interactive"
    cold_seen.add(arm)
    return {
        "order": order,
        "case_id": case_id,
        "arm": arm,
        "repeat": repeat,
        "measurement_phase": phase,
    }


def _serialized_schedule(case_ids: list[str]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    cold_seen: set[str] = set()
    for arm in ARM_NAMES:
        for repeat in range(1, REPETITIONS + 1):
            for case_id in case_ids:
                attempts.append(
                    _attempt(case_id, arm, repeat, len(attempts) + 1, cold_seen)
                )
    return attempts


def _interleaved_schedule(case_ids: list[str]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    cold_seen: set[str] = set()
    pair_index = 0
    for repeat in range(1, REPETITIONS + 1):
        for case_id in case_ids:
            arms = ARM_NAMES if pair_index % 2 == 0 else tuple(reversed(ARM_NAMES))
            for arm in arms:
                attempts.append(
                    _attempt(case_id, arm, repeat, len(attempts) + 1, cold_seen)
                )
            pair_index += 1
    return attempts


def _warm_pair_population(
    attempts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    phases = {
        (row["case_id"], row["repeat"], row["arm"]): row["measurement_phase"]
        for row in attempts
    }
    return [
        {"case_id": case_id, "repeat": repeat}
        for case_id, repeat, _arm in sorted(
            {(row["case_id"], row["repeat"], row["arm"]) for row in attempts}
        )
        if _arm == "legacy"
        and phases[(case_id, repeat, "legacy")] == "warm_interactive"
        and phases[(case_id, repeat, "planner")] == "warm_interactive"
    ]


def validate_schedule(
    case_ids: list[str], attempts: list[dict[str, Any]], *, interleaved: bool
) -> None:
    """Fail closed unless all planned case/arm/repetition slots occur once."""
    expected = {
        (case_id, arm, repeat)
        for case_id in case_ids
        for arm in ARM_NAMES
        for repeat in range(1, REPETITIONS + 1)
    }
    observed = [(row["case_id"], row["arm"], row["repeat"]) for row in attempts]
    if len(attempts) != 720 or len(observed) != len(set(observed)):
        raise ValueError("schedule has duplicate or missing attempt identities")
    if set(observed) != expected:
        raise ValueError("schedule identity set differs from accepted matrix")
    for arm in ARM_NAMES:
        arm_rows = [row for row in attempts if row["arm"] == arm]
        if sum(row["measurement_phase"] == "cold_start" for row in arm_rows) != 1:
            raise ValueError("each arm must have one cold-start observation")
        first = min(arm_rows, key=lambda row: row["order"])
        if first["measurement_phase"] != "cold_start":
            raise ValueError("first observation for each arm must be cold")
    if interleaved:
        for left, right in zip(attempts[::2], attempts[1::2], strict=True):
            if (
                left["case_id"],
                left["repeat"],
            ) != (right["case_id"], right["repeat"]):
                raise ValueError(
                    "interleaved schedule must keep matched pairs adjacent"
                )
            if left["arm"] == right["arm"]:
                raise ValueError("interleaved pair must use both arms")


def build_schedule(case_ids: list[str], *, seed: str) -> dict[str, Any]:
    """Build schedule candidates; serialized order is the executable proposal."""
    if len(case_ids) != CASE_COUNT or len(case_ids) != len(set(case_ids)):
        raise ValueError("schedule requires exactly 120 unique held-out IDs")
    ordered_ids = _ordered_case_ids(case_ids, seed)
    serialized = _serialized_schedule(ordered_ids)
    interleaved = _interleaved_schedule(ordered_ids)
    validate_schedule(ordered_ids, serialized, interleaved=False)
    validate_schedule(ordered_ids, interleaved, interleaved=True)
    return {
        "status": "CANDIDATE_NOT_FROZEN_NOT_EXECUTED",
        "case_id_source": "private held-out candidate; IDs only",
        "seed": seed,
        "case_count": len(case_ids),
        "arms": list(ARM_NAMES),
        "repetitions_per_case_arm": REPETITIONS,
        "attempt_count_per_alternative": len(serialized),
        "selected_for_review": "serialized",
        "router_mode_execution": {
            "one_canonical_app_at_a_time": True,
            "arm_order": ["legacy", "planner"],
            "controlled_restarts_between_arms": 1,
            "per_request_router_override": False,
            "interleaved_candidate_executable": False,
        },
        "serialized": {
            "attempts": serialized,
            "predeclared_warm_pairs": _warm_pair_population(serialized),
        },
        "interleaved": {
            "attempts": interleaved,
            "predeclared_warm_pairs": _warm_pair_population(interleaved),
        },
        "execution_choice": "PENDING_SEPARATE_AUTHORITY",
        "execution_policy": {
            "calls_in_flight": 1,
            "production_traffic": False,
            "model_instances": 1,
            "per_request_watchdog_seconds": 300,
            "campaign_wall_watchdog_hours": 8,
            "host_memory_stop_condition": "stop if available host memory falls below 4 GiB",
            "campaign_watchdog_expiry": "record remaining attempts as INCOMPLETE; score NOT_EVALUABLE",
            "limits_status": "PROPOSED_PENDING_REVIEW_AND_HUMAN_EXECUTION_AUTHORITY",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=HELD_OUT_PATH)
    parser.add_argument("--output", type=Path, default=SCHEDULE_PATH)
    parser.add_argument(
        "--seed",
        default="beta-conv-01a-eval-schedule-v1",
        help="fixed schedule seed, recorded in the candidate output",
    )
    args = parser.parse_args()
    schedule = build_schedule(read_case_ids(args.input), seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(schedule, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "case_count": schedule["case_count"],
                "attempt_count_per_alternative": schedule[
                    "attempt_count_per_alternative"
                ],
                "serialized_warm_pairs": len(
                    schedule["serialized"]["predeclared_warm_pairs"]
                ),
                "interleaved_warm_pairs": len(
                    schedule["interleaved"]["predeclared_warm_pairs"]
                ),
                "status": schedule["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
