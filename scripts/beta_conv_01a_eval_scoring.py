"""Deterministic scoring primitives for BETA-CONV-01A evaluation evidence."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

TERMINAL_STATES = {"response", "error", "timeout", "cancelled", "incomplete"}
OPERATIONS = {
    "grounded_query",
    "transform_text",
    "clarify",
    "unsupported_operation",
}


def nearest_rank(values: Iterable[float], percentile: float) -> float:
    """Return a nearest-rank percentile, including every recorded attempt."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    if not 0 < percentile <= 1:
        raise ValueError("percentile must be in (0, 1]")
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def wilson_interval(
    successes: int, total: int, *, z: float = 1.959963984540054
) -> tuple[float, float]:
    """Return a two-sided Wilson score interval for a binomial proportion."""
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("require 0 <= successes <= total and total > 0")
    proportion = successes / total
    z_squared = z * z
    denominator = 1 + z_squared / total
    center = (proportion + z_squared / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z_squared / (4 * total * total)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def validate_observations(
    case_ids: set[str], observations: list[dict[str, Any]], *, arm: str, repeats: int
) -> None:
    """Require exactly one complete observation per case, arm, and repeat."""
    if repeats < 1:
        raise ValueError("repeats must be positive")
    expected = {
        (case_id, arm, repeat)
        for case_id in case_ids
        for repeat in range(1, repeats + 1)
    }
    observed_keys: set[tuple[str, str, int]] = set()
    required = {
        "case_id",
        "arm",
        "repeat",
        "terminal_state",
        "elapsed_ms",
        "observed_operation",
        "citation_source_ids",
        "citations_valid",
        "snapshot_consistent",
        "query_trace_present",
        "target_kind",
        "target_role",
        "target_ordinal",
        "target_sha256",
        "target_char_count",
        "transform_kind",
        "options",
        "planner_calls",
        "resolver_calls",
        "planner_validation",
        "retrieval_calls",
        "answer_generation_calls",
        "transform_calls",
        "retry_count",
    }
    for row in observations:
        missing = required - row.keys()
        if missing:
            raise ValueError(f"observation missing fields: {sorted(missing)}")
        key = (row["case_id"], row["arm"], row["repeat"])
        if key in observed_keys:
            raise ValueError(f"duplicate observation: {key}")
        observed_keys.add(key)
        if row["arm"] != arm or row["case_id"] not in case_ids:
            raise ValueError(f"unexpected observation identity: {key}")
        if row["terminal_state"] not in TERMINAL_STATES:
            raise ValueError(f"invalid terminal_state: {row['terminal_state']}")
        elapsed = row["elapsed_ms"]
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or elapsed < 0
        ):
            raise ValueError(
                "elapsed_ms must be a nonnegative number for every attempt"
            )
        if (
            row["observed_operation"] is not None
            and row["observed_operation"] not in OPERATIONS
        ):
            raise ValueError(f"invalid observed_operation: {row['observed_operation']}")
        if row["planner_validation"] not in {
            None,
            "valid",
            "rejected",
            "unavailable",
            "cancelled",
        }:
            raise ValueError(f"invalid planner_validation: {row['planner_validation']}")
        for field in (
            "citations_valid",
            "snapshot_consistent",
            "query_trace_present",
        ):
            if not isinstance(row[field], bool):
                raise TypeError(f"{field} must be a boolean")
        if not isinstance(row["citation_source_ids"], list) or any(
            not isinstance(source_id, str) for source_id in row["citation_source_ids"]
        ):
            raise TypeError("citation_source_ids must be a list of strings")
        for field in (
            "planner_calls",
            "resolver_calls",
            "retrieval_calls",
            "answer_generation_calls",
            "transform_calls",
            "retry_count",
        ):
            count = row[field]
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise TypeError(f"{field} must be a nonnegative integer")
        if arm == "planner" and (
            row["planner_calls"] > 1
            or row["resolver_calls"] != 0
            or row["retry_count"] != 0
        ):
            raise ValueError(
                "planner arm requires at most one planner call, no resolver, "
                "and no retries"
            )
        if isinstance(row["repeat"], bool) or not isinstance(row["repeat"], int):
            raise TypeError("repeat must be an integer")
        if not 1 <= row["repeat"] <= repeats:
            raise ValueError(f"repeat outside configured range: {key}")

    if observed_keys != expected:
        missing = sorted(expected - observed_keys)
        extra = sorted(observed_keys - expected)
        raise ValueError(
            f"observation coverage mismatch; missing={missing}; extra={extra}"
        )


def score_results(
    cases: list[dict[str, Any]],
    labels: Mapping[str, dict[str, Any]],
    observations: list[dict[str, Any]],
    *,
    arm: str,
    repeats: int,
) -> dict[str, Any]:
    """Score normalized HTTP/trace observations against adjudicated labels.

    The caller must derive observations from the canonical conversation API
    response and persisted trace. This function never calls a model or executor.
    """
    case_ids = {row["case_id"] for row in cases}
    if set(labels) != case_ids:
        raise ValueError("labels must cover exactly the scored cases")
    validate_observations(case_ids, observations, arm=arm, repeats=repeats)
    case_by_id = {row["case_id"]: row for row in cases}
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        by_case[row["case_id"]].append(row)

    operation_passes = 0
    target_option_cases = 0
    target_option_passes = 0
    completion_cases = 0
    completion_passes = 0
    clarified_cases: set[str] = set()
    clarification_truth: dict[str, bool] = {}
    excess_clarification_cases: set[str] = set()
    critical_grounding_violations = 0
    scope_identity_violations = 0
    repeatability_passes = 0
    latency_by_expected_operation: dict[str, list[float]] = defaultdict(list)
    call_totals = Counter()
    validation_counts = Counter()
    supported_case_validity: dict[str, bool] = {}

    for case_id, label in labels.items():
        if label.get("expected_operation") not in OPERATIONS:
            raise ValueError(f"invalid expected operation for {case_id}")
        if not isinstance(label.get("required_source_ids"), list):
            raise TypeError(f"required_source_ids missing for {case_id}")
        if not isinstance(label.get("requires_evidence"), bool):
            raise TypeError(f"requires_evidence missing for {case_id}")
        if not isinstance(label.get("should_clarify"), bool):
            raise TypeError(f"should_clarify missing for {case_id}")
        rows = sorted(by_case[case_id], key=lambda row: row["repeat"])
        label_operation = label["expected_operation"]
        expected_sources = set(label["required_source_ids"])
        selected_sources = set(case_by_id[case_id]["request"]["source_ids"])
        if not expected_sources <= selected_sources:
            raise ValueError(f"label source scope escapes request selection: {case_id}")

        op_ok = True
        target_ok = True
        completed = True
        case_ops: set[str | None] = set()
        case_signatures: set[tuple[Any, ...]] = set()
        successful_signatures: set[tuple[Any, ...]] = set()
        successful_operations: set[str] = set()
        any_clarification = False
        all_plans_valid = True
        end_to_end_ok = True
        expected_target = label.get("target")
        for row in rows:
            operation = row["observed_operation"]
            case_ops.add(operation)
            signature = (
                operation,
                row["target_kind"],
                row["target_role"],
                row["target_ordinal"],
                row["target_sha256"],
                row["target_char_count"],
                row["transform_kind"],
                _canonical_options(row["options"]),
            )
            case_signatures.add(signature)
            if row["terminal_state"] == "response" and operation is not None:
                successful_signatures.add(signature)
                successful_operations.add(operation)
            completed = completed and row["terminal_state"] == "response"
            op_ok = op_ok and (
                row["terminal_state"] == "response" and operation == label_operation
            )
            row_completion_ok = (
                row["terminal_state"] == "response" and operation == label_operation
            )
            any_clarification = any_clarification or operation == "clarify"
            latency_by_expected_operation[label_operation].append(row["elapsed_ms"])
            for field in (
                "planner_calls",
                "resolver_calls",
                "retrieval_calls",
                "answer_generation_calls",
                "transform_calls",
                "retry_count",
            ):
                call_totals[field] += row[field]
            if row["planner_validation"] is not None:
                validation_counts[row["planner_validation"]] += 1
            if label_operation in {"grounded_query", "transform_text"}:
                all_plans_valid = (
                    all_plans_valid and row["planner_validation"] == "valid"
                )

            cited = set(row["citation_source_ids"])
            if not cited <= selected_sources or not row["snapshot_consistent"]:
                scope_identity_violations += 1
            if (
                label["requires_evidence"]
                and row["terminal_state"] == "response"
                and (
                    operation != "grounded_query"
                    or not cited
                    or not row["citations_valid"]
                    or not row["snapshot_consistent"]
                    or not row["query_trace_present"]
                )
            ):
                critical_grounding_violations += 1
            if label["requires_evidence"]:
                row_completion_ok = (
                    row_completion_ok
                    and bool(cited)
                    and bool(row["citations_valid"])
                    and bool(row["snapshot_consistent"])
                    and bool(row["query_trace_present"])
                )

            if label_operation == "transform_text":
                if not isinstance(expected_target, dict):
                    raise ValueError(f"transform target label missing for {case_id}")
                observed_target = {
                    "kind": row["target_kind"],
                    "role": row["target_role"],
                    "ordinal": row["target_ordinal"],
                    "sha256": row["target_sha256"],
                    "char_count": row["target_char_count"],
                    "transform_kind": row["transform_kind"],
                    "options": row["options"],
                }
                target_ok = target_ok and (
                    row["terminal_state"] == "response"
                    and operation == "transform_text"
                    and observed_target == expected_target
                )
                row_completion_ok = row_completion_ok and (
                    operation == "transform_text" and observed_target == expected_target
                )
            elif expected_target is not None:
                raise ValueError(f"non-transform label has a target for {case_id}")
            end_to_end_ok = end_to_end_ok and row_completion_ok

        if len(successful_operations) == 1 and len(successful_signatures) == 1:
            repeatability_passes += 1
        if label_operation in {"grounded_query", "transform_text"}:
            supported_case_validity[case_id] = all_plans_valid
        if op_ok:
            operation_passes += 1
        if label_operation == "transform_text":
            target_option_cases += 1
            if target_ok:
                target_option_passes += 1
        if label_operation in {"grounded_query", "transform_text"}:
            completion_cases += 1
            if end_to_end_ok:
                completion_passes += 1
        if any_clarification:
            clarified_cases.add(case_id)
            clarification_truth[case_id] = bool(label.get("should_clarify"))
            if label_operation in {"grounded_query", "transform_text"}:
                excess_clarification_cases.add(case_id)

    clarification_true_positives = sum(clarification_truth.values())
    clarification_precision = (
        {
            "numerator": clarification_true_positives,
            "denominator": len(clarified_cases),
            "rate": clarification_true_positives / len(clarified_cases),
            "wilson_95": list(
                wilson_interval(clarification_true_positives, len(clarified_cases))
            ),
        }
        if clarified_cases
        else {"numerator": 0, "denominator": 0, "rate": None, "wilson_95": None}
    )
    percentiles = {
        operation: {
            "attempts_including_failures": len(values),
            "p50_ms_nearest_rank": nearest_rank(values, 0.50),
            "p95_ms_nearest_rank": nearest_rank(values, 0.95),
        }
        for operation, values in sorted(latency_by_expected_operation.items())
    }
    per_repeat_operation_accuracy = {}
    clarification_by_repeat = {}
    for repeat in range(1, repeats + 1):
        passing = sum(
            row["repeat"] == repeat
            and row["terminal_state"] == "response"
            and row["observed_operation"]
            == labels[row["case_id"]]["expected_operation"]
            for row in observations
        )
        per_repeat_operation_accuracy[str(repeat)] = {
            "numerator": passing,
            "denominator": len(cases),
            "rate": passing / len(cases),
        }
        clarified_this_repeat = {
            row["case_id"]
            for row in observations
            if row["repeat"] == repeat and row["observed_operation"] == "clarify"
        }
        necessary_clarifications = sum(
            labels[case_id]["should_clarify"] for case_id in clarified_this_repeat
        )
        fully_supported = {
            case_id
            for case_id, label in labels.items()
            if label["expected_operation"] in {"grounded_query", "transform_text"}
            and not label["should_clarify"]
        }
        excess_clarifications = len(clarified_this_repeat & fully_supported)
        clarification_by_repeat[str(repeat)] = {
            "precision": {
                "numerator": necessary_clarifications,
                "denominator": len(clarified_this_repeat),
                "rate": (
                    necessary_clarifications / len(clarified_this_repeat)
                    if clarified_this_repeat
                    else None
                ),
            },
            "excess_clarification": {
                "numerator": excess_clarifications,
                "denominator": len(fully_supported),
                "rate": (
                    excess_clarifications / len(fully_supported)
                    if fully_supported
                    else None
                ),
            },
        }
    per_stratum = {}
    for stratum in sorted({row["stratum"] for row in cases}):
        stratum_cases = [row for row in cases if row["stratum"] == stratum]
        stratum_ids = {row["case_id"] for row in stratum_cases}
        passing = sum(
            case_id in stratum_ids
            and all(
                row["terminal_state"] == "response"
                and row["observed_operation"] == labels[case_id]["expected_operation"]
                for row in by_case[case_id]
            )
            for case_id in stratum_ids
        )
        per_stratum[stratum] = {
            "numerator": passing,
            "denominator": len(stratum_cases),
            "rate": passing / len(stratum_cases),
            "wilson_95": list(wilson_interval(passing, len(stratum_cases))),
        }
    unsupported_cases = [
        case_id
        for case_id, label in labels.items()
        if label["expected_operation"] == "unsupported_operation"
    ]
    unsupported_passes = sum(
        all(
            row["terminal_state"] == "response"
            and row["observed_operation"] == "unsupported_operation"
            for row in by_case[case_id]
        )
        for case_id in unsupported_cases
    )
    return {
        "arm": arm,
        "repeats_per_case": repeats,
        "operation_accuracy": {
            "numerator": operation_passes,
            "denominator": len(cases),
            "rate": operation_passes / len(cases),
            "wilson_95": list(wilson_interval(operation_passes, len(cases))),
        },
        "operation_accuracy_by_stratum": per_stratum,
        "operation_accuracy_by_repeat": per_repeat_operation_accuracy,
        "target_options_accuracy": {
            "numerator": target_option_passes,
            "denominator": target_option_cases,
            "rate": target_option_passes / target_option_cases
            if target_option_cases
            else None,
        },
        "end_to_end_completion": {
            "numerator": completion_passes,
            "denominator": completion_cases,
            "rate": completion_passes / completion_cases if completion_cases else None,
        },
        "clarification_precision": clarification_precision,
        "excess_clarification": {
            "numerator": len(excess_clarification_cases),
            "denominator": sum(
                label["expected_operation"] in {"grounded_query", "transform_text"}
                and not label["should_clarify"]
                for label in labels.values()
            ),
        },
        "clarification_by_repeat": clarification_by_repeat,
        "critical_grounding_violations": critical_grounding_violations,
        "scope_identity_violations": scope_identity_violations,
        "unsupported_operation_accuracy": {
            "numerator": unsupported_passes,
            "denominator": len(unsupported_cases),
            "rate": unsupported_passes / len(unsupported_cases)
            if unsupported_cases
            else None,
        },
        "case_repeatability": {
            "numerator": repeatability_passes,
            "denominator": len(cases),
        },
        "structured_plan_validity": {
            "numerator": sum(supported_case_validity.values()),
            "denominator": len(supported_case_validity),
            "rate": (
                sum(supported_case_validity.values()) / len(supported_case_validity)
                if supported_case_validity
                else None
            ),
        },
        "latency_by_expected_operation": percentiles,
        "planner_validation_counts": dict(sorted(validation_counts.items())),
        "call_counts": dict(sorted(call_totals.items())),
    }


def _canonical_options(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
