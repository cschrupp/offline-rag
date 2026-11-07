"""Deterministic scoring primitives for BETA-CONV-01A evaluation evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
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
RESPONSE_STATUSES = {
    "answered",
    "insufficient_evidence",
    "model_abstain",
    "clarification_required",
    "transformed",
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
    if arm not in {"legacy", "planner"}:
        raise ValueError(f"unsupported comparison arm: {arm}")
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
        "response_status",
        "measurement_phase",
        "elapsed_ms",
        "planner_elapsed_ms",
        "observed_operation",
        "reason_code",
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
        response_status = row["response_status"]
        if row["terminal_state"] == "response":
            if response_status not in RESPONSE_STATUSES:
                raise ValueError("response_status is required for a response")
        elif response_status is not None:
            raise ValueError("response_status must be null for a non-response")
        if row["measurement_phase"] not in {"cold_start", "warm_interactive"}:
            raise ValueError(f"invalid measurement_phase: {row['measurement_phase']}")
        elapsed = row["elapsed_ms"]
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or isinstance(elapsed, float)
            and not math.isfinite(elapsed)
            or elapsed < 0
        ):
            raise ValueError("elapsed_ms must be finite and nonnegative")
        planner_elapsed = row["planner_elapsed_ms"]
        if planner_elapsed is not None and (
            isinstance(planner_elapsed, bool)
            or not isinstance(planner_elapsed, (int, float))
            or isinstance(planner_elapsed, float)
            and not math.isfinite(planner_elapsed)
            or planner_elapsed < 0
        ):
            raise ValueError(
                "planner_elapsed_ms must be null or finite and nonnegative"
            )
        if (
            row["observed_operation"] is not None
            and row["observed_operation"] not in OPERATIONS
        ):
            raise ValueError(f"invalid observed_operation: {row['observed_operation']}")
        if row["reason_code"] is not None and not isinstance(row["reason_code"], str):
            raise TypeError("reason_code must be a string or null")
        if row["planner_validation"] not in {
            None,
            "valid",
            "rejected",
            "unavailable",
            "cancelled",
        }:
            raise ValueError(f"invalid planner_validation: {row['planner_validation']}")
        for field in ("citations_valid", "query_trace_present"):
            if not isinstance(row[field], bool):
                raise TypeError(f"{field} must be a boolean")
        if row["snapshot_consistent"] is not None and not isinstance(
            row["snapshot_consistent"], bool
        ):
            raise TypeError("snapshot_consistent must be boolean or null")
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
        if arm == "planner" and row["planner_calls"] > 0 and planner_elapsed is None:
            raise ValueError(
                "planner_elapsed_ms required when planner_calls is positive"
            )
        if arm != "planner" and planner_elapsed is not None:
            raise ValueError("planner_elapsed_ms must be unavailable for legacy arm")
        if (
            arm == "planner"
            and row["planner_calls"] == 0
            and planner_elapsed is not None
        ):
            raise ValueError("planner_elapsed_ms must be unavailable without a call")
        if arm == "legacy" and (
            row["planner_calls"] != 0 or row["planner_validation"] is not None
        ):
            raise ValueError("legacy arm must not execute or validate a planner")
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
    if len(case_ids) != len(cases):
        raise ValueError("duplicate case identity in scored input")
    if set(labels) != case_ids:
        raise ValueError("labels must cover exactly the scored cases")
    case_by_id = {row["case_id"]: row for row in cases}
    for case_id, case in case_by_id.items():
        request_json = json.dumps(
            case["request"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        expected_request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        if case.get("request_sha256") != expected_request_hash:
            raise ValueError(f"case request hash mismatch: {case_id}")
        if labels[case_id].get("request_sha256") != expected_request_hash:
            raise ValueError(f"label is not bound to exact request bytes: {case_id}")
    validate_observations(case_ids, observations, arm=arm, repeats=repeats)
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
    wrong_target_executions = 0
    outcome_contract_violations = 0
    repeatability_passes = 0
    latency_by_operation_and_phase: dict[tuple[str, str], list[float]] = defaultdict(
        list
    )
    call_totals = Counter()
    validation_counts = Counter()
    supported_case_validity: dict[str, bool] = {}
    planner_stage_times: dict[str, list[float]] = defaultdict(list)

    for case_id, label in labels.items():
        if label.get("expected_operation") not in OPERATIONS:
            raise ValueError(f"invalid expected operation for {case_id}")
        if not isinstance(label.get("required_source_ids"), list):
            raise TypeError(f"required_source_ids missing for {case_id}")
        if any(
            not isinstance(source_id, str) for source_id in label["required_source_ids"]
        ):
            raise TypeError(f"required_source_ids must contain strings: {case_id}")
        if not isinstance(label.get("requires_evidence"), bool):
            raise TypeError(f"requires_evidence missing for {case_id}")
        if not isinstance(label.get("should_clarify"), bool):
            raise TypeError(f"should_clarify missing for {case_id}")
        if "expected_reason_code" not in label:
            raise ValueError(f"expected_reason_code missing for {case_id}")
        if label["expected_reason_code"] is not None and not isinstance(
            label["expected_reason_code"], str
        ):
            raise TypeError(f"expected_reason_code must be string or null: {case_id}")
        if not isinstance(label.get("allowed_safe_outcomes"), list):
            raise TypeError(f"allowed_safe_outcomes missing for {case_id}")
        allowed_outcomes: set[tuple[str, str | None]] = set()
        for safe_outcome in label["allowed_safe_outcomes"]:
            if (
                not isinstance(safe_outcome, dict)
                or set(safe_outcome) != {"operation", "reason_code"}
                or safe_outcome.get("operation") not in OPERATIONS
                or (
                    safe_outcome.get("reason_code") is not None
                    and not isinstance(safe_outcome.get("reason_code"), str)
                )
            ):
                raise ValueError(f"invalid allowed safe outcome for {case_id}")
            allowed_outcomes.add(
                (safe_outcome["operation"], safe_outcome.get("reason_code"))
            )
        if not isinstance(label.get("mandatory_unsupported"), bool):
            raise TypeError(f"mandatory_unsupported must be boolean: {case_id}")
        if (
            label["mandatory_unsupported"]
            and label["expected_operation"] != "unsupported_operation"
        ):
            raise ValueError(
                f"mandatory_unsupported must label a decline case: {case_id}"
            )
        rows = sorted(by_case[case_id], key=lambda row: row["repeat"])
        if case_by_id[case_id].get("language") not in {"en", "es"}:
            raise ValueError(f"case language must be en or es: {case_id}")
        label_operation = label["expected_operation"]
        expected_target = label.get("target")
        if label_operation == "transform_text":
            expected_target_fields = {
                "kind",
                "role",
                "ordinal",
                "sha256",
                "char_count",
                "transform_kind",
                "options",
            }
            if (
                not isinstance(expected_target, dict)
                or set(expected_target) != expected_target_fields
            ):
                raise ValueError(
                    f"transform target label has invalid schema: {case_id}"
                )
            if (
                not isinstance(expected_target["kind"], str)
                or not isinstance(expected_target["role"], str)
                or (
                    expected_target["ordinal"] is not None
                    and (
                        isinstance(expected_target["ordinal"], bool)
                        or not isinstance(expected_target["ordinal"], int)
                        or expected_target["ordinal"] < 1
                    )
                )
                or not isinstance(expected_target["sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", expected_target["sha256"]) is None
                or isinstance(expected_target["char_count"], bool)
                or not isinstance(expected_target["char_count"], int)
                or expected_target["char_count"] < 0
                or not isinstance(expected_target["transform_kind"], str)
                or not isinstance(expected_target["options"], dict)
            ):
                raise ValueError(
                    f"transform target label values are invalid: {case_id}"
                )
        elif expected_target is not None:
            raise ValueError(f"non-transform label must have null target: {case_id}")
        expected_sources = set(label["required_source_ids"])
        selected_source_rows = case_by_id[case_id]["request"].get("source_ids")
        available_source_rows = case_by_id[case_id]["available_source_ids"]
        if selected_source_rows == []:
            raise ValueError(f"request uses invalid empty source scope: {case_id}")
        if (
            (
                selected_source_rows is not None
                and (
                    not isinstance(selected_source_rows, list)
                    or any(
                        not isinstance(source_id, str)
                        for source_id in selected_source_rows
                    )
                )
            )
            or not isinstance(available_source_rows, list)
            or any(
                not isinstance(source_id, str) for source_id in available_source_rows
            )
            or len(available_source_rows) != len(set(available_source_rows))
            or (
                isinstance(selected_source_rows, list)
                and len(selected_source_rows) != len(set(selected_source_rows))
            )
        ):
            raise TypeError(f"source identities must be string lists: {case_id}")
        available_sources = set(available_source_rows)
        if selected_source_rows is None:
            selected_sources = available_sources
        else:
            selected_sources = set(selected_source_rows)
        if not selected_sources <= available_sources:
            raise ValueError(
                f"request contains invalid selected source identity: {case_id}"
            )
        if not expected_sources <= selected_sources:
            raise ValueError(f"label source scope escapes request selection: {case_id}")

        op_ok = True
        target_ok = True
        completed = True
        case_ops: set[str | None] = set()
        case_signatures: set[tuple[Any, ...]] = set()
        any_clarification = False
        all_plans_valid = True
        end_to_end_ok = True
        for row in rows:
            operation = row["observed_operation"]
            observed_outcome = (operation, row["reason_code"])
            expected_outcome = (label_operation, label["expected_reason_code"])
            if (
                row["terminal_state"] == "response"
                and observed_outcome != expected_outcome
                and observed_outcome not in allowed_outcomes
            ):
                outcome_contract_violations += 1
            case_ops.add(operation)
            signature: tuple[Any, ...] = (operation,)
            if operation == "transform_text":
                signature += (
                    row["target_kind"],
                    row["target_role"],
                    row["target_ordinal"],
                    row["target_sha256"],
                    row["target_char_count"],
                    row["transform_kind"],
                    _canonical_options(row["options"]),
                )
            case_signatures.add(signature)
            if row["terminal_state"] == "response" and operation == "transform_text":
                if label_operation != "transform_text":
                    wrong_target_executions += 1
                else:
                    observed_transform_target = {
                        "kind": row["target_kind"],
                        "role": row["target_role"],
                        "ordinal": row["target_ordinal"],
                        "sha256": row["target_sha256"],
                        "char_count": row["target_char_count"],
                        "transform_kind": row["transform_kind"],
                        "options": row["options"],
                    }
                    if observed_transform_target != expected_target:
                        wrong_target_executions += 1
            completed = completed and row["terminal_state"] == "response"
            op_ok = op_ok and (
                row["terminal_state"] == "response" and operation == label_operation
            )
            row_completion_ok = (
                row["terminal_state"] == "response" and operation == label_operation
            )
            any_clarification = any_clarification or operation == "clarify"
            latency_by_operation_and_phase[
                (label_operation, row["measurement_phase"])
            ].append(row["elapsed_ms"])
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
            if row["planner_elapsed_ms"] is not None:
                planner_stage_times[row["measurement_phase"]].append(
                    row["planner_elapsed_ms"]
                )
            if arm == "planner" and label_operation in {
                "grounded_query",
                "transform_text",
            }:
                all_plans_valid = (
                    all_plans_valid and row["planner_validation"] == "valid"
                )

            cited = set(row["citation_source_ids"])
            if not cited <= selected_sources or row["snapshot_consistent"] is False:
                scope_identity_violations += 1
            factual_success = row["response_status"] == "answered"
            if (
                label["requires_evidence"]
                and row["terminal_state"] == "response"
                and (
                    operation == "transform_text"
                    or (
                        factual_success
                        and (
                            operation != "grounded_query"
                            or not cited
                            or not row["citations_valid"]
                            or row["snapshot_consistent"] is not True
                            or not row["query_trace_present"]
                        )
                    )
                )
            ):
                critical_grounding_violations += 1
            if label["requires_evidence"]:
                row_completion_ok = (
                    row_completion_ok
                    and row["response_status"] == "answered"
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
            end_to_end_ok = end_to_end_ok and row_completion_ok

        if completed and len(case_signatures) == 1 and None not in case_ops:
            repeatability_passes += 1
        if arm == "planner" and label_operation in {
            "grounded_query",
            "transform_text",
        }:
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
            if (
                label_operation in {"grounded_query", "transform_text"}
                and not label["should_clarify"]
            ):
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
    percentiles = {}
    for operation in sorted({key[0] for key in latency_by_operation_and_phase}):
        percentiles[operation] = {}
        for phase in ("cold_start", "warm_interactive"):
            values = latency_by_operation_and_phase.get((operation, phase), [])
            percentiles[operation][phase] = {
                "attempts_including_failures": len(values),
                "p50_ms_nearest_rank": nearest_rank(values, 0.50) if values else None,
                "p95_ms_nearest_rank": nearest_rank(values, 0.95) if values else None,
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
    per_language = {}
    for language in sorted({row["language"] for row in cases}):
        language_cases = [row for row in cases if row["language"] == language]
        language_ids = {row["case_id"] for row in language_cases}
        passing = sum(
            all(
                row["terminal_state"] == "response"
                and row["observed_operation"] == labels[case_id]["expected_operation"]
                for row in by_case[case_id]
            )
            for case_id in language_ids
        )
        per_language[language] = {
            "numerator": passing,
            "denominator": len(language_cases),
            "rate": passing / len(language_cases),
            "wilson_95": list(wilson_interval(passing, len(language_cases))),
        }
    contract_strata = {
        "factual": {
            case_id
            for case_id, label in labels.items()
            if label["expected_operation"] == "grounded_query"
        },
        "transform": {
            case_id
            for case_id, label in labels.items()
            if label["expected_operation"] == "transform_text"
        },
    }
    operation_accuracy_by_contract_stratum = {}
    for stratum, case_ids in contract_strata.items():
        passing = sum(
            all(
                row["terminal_state"] == "response"
                and row["observed_operation"] == labels[case_id]["expected_operation"]
                for row in by_case[case_id]
            )
            for case_id in case_ids
        )
        operation_accuracy_by_contract_stratum[stratum] = {
            "numerator": passing,
            "denominator": len(case_ids),
            "rate": passing / len(case_ids) if case_ids else None,
            "wilson_95": list(wilson_interval(passing, len(case_ids)))
            if case_ids
            else None,
        }
    unsupported_cases = [
        case_id
        for case_id, label in labels.items()
        if label["expected_operation"] == "unsupported_operation"
    ]
    unsupported_passes_by_class = {"mandatory": 0, "other": 0}
    unsupported_counts_by_class = {"mandatory": 0, "other": 0}
    for case_id in unsupported_cases:
        bucket = "mandatory" if labels[case_id]["mandatory_unsupported"] else "other"
        unsupported_counts_by_class[bucket] += 1
        passed = all(
            row["terminal_state"] == "response"
            and row["observed_operation"] == "unsupported_operation"
            for row in by_case[case_id]
        )
        unsupported_passes_by_class[bucket] += int(passed)
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
        "operation_accuracy_by_language": per_language,
        "operation_accuracy_by_contract_stratum": operation_accuracy_by_contract_stratum,
        "operation_accuracy_by_repeat": per_repeat_operation_accuracy,
        "target_options_accuracy": {
            "numerator": target_option_passes,
            "denominator": target_option_cases,
            "rate": target_option_passes / target_option_cases
            if target_option_cases
            else None,
            "wilson_95": list(
                wilson_interval(target_option_passes, target_option_cases)
            )
            if target_option_cases
            else None,
        },
        "end_to_end_completion": {
            "numerator": completion_passes,
            "denominator": completion_cases,
            "rate": completion_passes / completion_cases if completion_cases else None,
            "wilson_95": list(wilson_interval(completion_passes, completion_cases))
            if completion_cases
            else None,
        },
        "clarification_precision": clarification_precision,
        "excess_clarification": {
            "numerator": len(excess_clarification_cases),
            "denominator": sum(
                label["expected_operation"] in {"grounded_query", "transform_text"}
                and not label["should_clarify"]
                for label in labels.values()
            ),
            "rate": (
                len(excess_clarification_cases)
                / sum(
                    label["expected_operation"] in {"grounded_query", "transform_text"}
                    and not label["should_clarify"]
                    for label in labels.values()
                )
                if any(
                    label["expected_operation"] in {"grounded_query", "transform_text"}
                    and not label["should_clarify"]
                    for label in labels.values()
                )
                else None
            ),
        },
        "clarification_by_repeat": clarification_by_repeat,
        "critical_grounding_violations": critical_grounding_violations,
        "scope_identity_violations": scope_identity_violations,
        "wrong_target_executions": wrong_target_executions,
        "outcome_contract_violations": outcome_contract_violations,
        "unsupported_operation_accuracy": {
            "numerator": unsupported_passes,
            "denominator": len(unsupported_cases),
            "rate": unsupported_passes / len(unsupported_cases)
            if unsupported_cases
            else None,
        },
        "unsupported_operation_accuracy_by_class": {
            bucket: {
                "numerator": unsupported_passes_by_class[bucket],
                "denominator": unsupported_counts_by_class[bucket],
                "rate": (
                    unsupported_passes_by_class[bucket]
                    / unsupported_counts_by_class[bucket]
                    if unsupported_counts_by_class[bucket]
                    else None
                ),
            }
            for bucket in ("mandatory", "other")
        },
        "case_repeatability": {
            "numerator": repeatability_passes,
            "denominator": len(cases),
            "wilson_95": list(wilson_interval(repeatability_passes, len(cases))),
        },
        "structured_plan_validity": {
            "numerator": sum(supported_case_validity.values()),
            "denominator": len(supported_case_validity),
            "rate": (
                sum(supported_case_validity.values()) / len(supported_case_validity)
                if supported_case_validity
                else None
            ),
            "wilson_95": list(
                wilson_interval(
                    sum(supported_case_validity.values()), len(supported_case_validity)
                )
            )
            if supported_case_validity
            else None,
        },
        "latency_by_expected_operation": percentiles,
        "planner_stage_latency_ms": {
            phase: {
                "attempts_with_planner_call": len(planner_stage_times[phase]),
                "p50_ms_nearest_rank": (
                    nearest_rank(planner_stage_times[phase], 0.50)
                    if planner_stage_times[phase]
                    else None
                ),
                "p95_ms_nearest_rank": (
                    nearest_rank(planner_stage_times[phase], 0.95)
                    if planner_stage_times[phase]
                    else None
                ),
            }
            for phase in ("cold_start", "warm_interactive")
        },
        "planner_validation_counts": dict(sorted(validation_counts.items())),
        "call_counts": dict(sorted(call_totals.items())),
    }


def _canonical_options(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def score_paired_results(
    cases: list[dict[str, Any]],
    labels: Mapping[str, dict[str, Any]],
    observations_by_arm: Mapping[str, list[dict[str, Any]]],
    *,
    repeats: int,
    warm_comparison_population: Mapping[str, set[tuple[str, int]]],
) -> dict[str, Any]:
    """Report accepted paired end-to-end latency gates for both arms.

    This consumes already-normalized canonical HTTP/trace observations. It does
    not execute the API, planner, or any downstream executor.
    """
    required_arms = {"legacy", "planner"}
    if set(observations_by_arm) != required_arms:
        raise ValueError("paired scoring requires exactly legacy and planner arms")

    arm_reports = {
        arm: score_results(
            cases,
            labels,
            observations_by_arm[arm],
            arm=arm,
            repeats=repeats,
        )
        for arm in sorted(required_arms)
    }
    case_by_id = {row["case_id"]: row for row in cases}
    categories = {
        "first_turn_factual": {
            case_id
            for case_id, case in case_by_id.items()
            if case["stratum"] == "factual_source"
            and not case["request"].get("prior_turns")
            and labels[case_id]["expected_operation"] == "grounded_query"
        },
        "contextual_grounded": {
            case_id
            for case_id, case in case_by_id.items()
            if case["stratum"] == "contextual_grounded"
            and labels[case_id]["expected_operation"] == "grounded_query"
        },
        "text_transformation": {
            case_id
            for case_id, label in labels.items()
            if label["expected_operation"] == "transform_text"
        },
    }
    if set(warm_comparison_population) != set(categories):
        raise ValueError(
            "warm comparison population must define all three latency categories"
        )
    rows_by_arm = {
        arm: {(row["case_id"], row["repeat"]): row for row in observations_by_arm[arm]}
        for arm in required_arms
    }
    threshold_config = {
        "p50_absolute_addition_ms": 1500,
        "p95_absolute_addition_ms": 3000,
        "relative_multiplier": 1.25,
    }
    paired_latency = {}
    for category, case_ids in categories.items():
        candidate_keys = sorted(
            (case_id, repeat)
            for case_id in case_ids
            for repeat in range(1, repeats + 1)
        )
        expected_warm_keys = warm_comparison_population[category]
        if not expected_warm_keys <= set(candidate_keys):
            raise ValueError(f"warm comparison population escapes {category} category")
        keys = sorted(expected_warm_keys)
        warm_coverage_complete = bool(keys) and all(
            rows_by_arm[arm][key]["measurement_phase"] == "warm_interactive"
            for key in keys
            for arm in required_arms
        )
        legacy_values = [rows_by_arm["legacy"][key]["elapsed_ms"] for key in keys]
        planner_values = [rows_by_arm["planner"][key]["elapsed_ms"] for key in keys]
        cold_pair_count = sum(
            any(
                rows_by_arm[arm][key]["measurement_phase"] != "warm_interactive"
                for arm in required_arms
            )
            for key in candidate_keys
        )
        outside_predeclared_population = len(candidate_keys) - len(keys)
        if not warm_coverage_complete:
            paired_latency[category] = {
                "status": "NOT_EVALUABLE",
                "matched_case_repeats": sum(
                    all(
                        rows_by_arm[arm][key]["measurement_phase"] == "warm_interactive"
                        for arm in required_arms
                    )
                    for key in keys
                ),
                "expected_warm_case_repeats": len(keys),
                "excluded_cold_pairs": cold_pair_count,
                "outside_predeclared_warm_population": outside_predeclared_population,
                "warm_coverage_complete": False,
                "legacy": None,
                "planner": None,
                "thresholds": threshold_config,
            }
            continue

        legacy_p50 = nearest_rank(legacy_values, 0.50)
        legacy_p95 = nearest_rank(legacy_values, 0.95)
        planner_p50 = nearest_rank(planner_values, 0.50)
        planner_p95 = nearest_rank(planner_values, 0.95)
        p50_pass = legacy_p50 > 0 and (
            planner_p50 <= legacy_p50 + threshold_config["p50_absolute_addition_ms"]
            and planner_p50 <= legacy_p50 * threshold_config["relative_multiplier"]
        )
        p95_pass = legacy_p95 > 0 and (
            planner_p95 <= legacy_p95 + threshold_config["p95_absolute_addition_ms"]
            and planner_p95 <= legacy_p95 * threshold_config["relative_multiplier"]
        )
        paired_latency[category] = {
            "status": "PASS" if p50_pass and p95_pass else "FAIL",
            "matched_case_repeats": len(keys),
            "expected_warm_case_repeats": len(keys),
            "excluded_cold_pairs": cold_pair_count,
            "outside_predeclared_warm_population": outside_predeclared_population,
            "warm_coverage_complete": True,
            "legacy": {
                "p50_ms_nearest_rank": legacy_p50,
                "p95_ms_nearest_rank": legacy_p95,
            },
            "planner": {
                "p50_ms_nearest_rank": planner_p50,
                "p95_ms_nearest_rank": planner_p95,
            },
            "gates": {
                "p50_pass": p50_pass,
                "p95_pass": p95_pass,
            },
            "thresholds": threshold_config,
        }
    planner_warm_latency = arm_reports["planner"]["planner_stage_latency_ms"][
        "warm_interactive"
    ]
    planner_p50 = planner_warm_latency["p50_ms_nearest_rank"]
    planner_p95 = planner_warm_latency["p95_ms_nearest_rank"]
    planner_stage_gate = {
        "status": (
            "NOT_EVALUABLE"
            if planner_p50 is None or planner_p95 is None
            else "PASS"
            if planner_p50 <= 1500 and planner_p95 <= 3000
            else "FAIL"
        ),
        "p50_pass": planner_p50 is not None and planner_p50 <= 1500,
        "p95_pass": planner_p95 is not None and planner_p95 <= 3000,
        "thresholds_ms": {"p50_max": 1500, "p95_max": 3000},
    }
    return {
        "arms": arm_reports,
        "paired_end_to_end_latency": paired_latency,
        "planner_stage_latency_gate": planner_stage_gate,
        "planner_stage_latency_ms": arm_reports["planner"]["planner_stage_latency_ms"],
    }
