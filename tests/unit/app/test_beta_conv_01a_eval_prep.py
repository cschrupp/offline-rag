from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from scripts.beta_conv_01a_eval_prep import (
    HISTORICAL_CHALLENGES,
    STRATA,
    build_candidate,
    build_cases,
    validate_cases,
)
from scripts.beta_conv_01a_eval_scoring import (
    score_paired_results,
)
from scripts.beta_conv_01a_eval_scoring import (
    score_results as _score_results,
)


def score_results(
    cases: list[dict[str, object]],
    labels: dict[str, dict[str, object]],
    observations: list[dict[str, object]],
    *,
    arm: str,
    repeats: int,
) -> dict[str, object]:
    """Bind legacy synthetic observations to their explicit fixture identities."""
    expected_hashes = {case["case_id"]: case["request_sha256"] for case in cases}
    bound_observations = []
    for observation in observations:
        bound = dict(observation)
        bound.setdefault("request_sha256", expected_hashes[bound["case_id"]])
        bound.setdefault(
            "query_trace_link_consistent",
            True if bound.get("terminal_state") == "response" else None,
        )
        bound_observations.append(bound)
    return _score_results(cases, labels, bound_observations, arm=arm, repeats=repeats)


def _bind_label(
    case: dict[str, object], label: dict[str, object]
) -> dict[str, dict[str, object]]:
    request_json = json.dumps(
        case["request"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    request_sha256 = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
    case["request_sha256"] = request_sha256
    return {case["case_id"]: {**label, "request_sha256": request_sha256}}


def _observation(
    *,
    repeat: int,
    terminal_state: str = "response",
    observed_operation: str | None = "grounded_query",
    snapshot_consistent: bool = True,
    arm: str = "planner",
    planner_calls: int = 1,
    resolver_calls: int = 0,
    retry_count: int = 0,
    response_status: str | None = None,
) -> dict[str, object]:
    if response_status is None and terminal_state == "response":
        response_status = {
            "grounded_query": "answered",
            "transform_text": "transformed",
            "clarify": "clarification_required",
            "unsupported_operation": "clarification_required",
        }.get(observed_operation)
    return {
        "case_id": "case-1",
        "arm": arm,
        "repeat": repeat,
        "terminal_state": terminal_state,
        "response_status": response_status,
        "measurement_phase": "warm_interactive",
        "elapsed_ms": 800 if terminal_state == "response" else 120_000,
        "planner_elapsed_ms": 350 if planner_calls else None,
        "observed_operation": observed_operation,
        "reason_code": None,
        "citation_source_ids": ["source_manual"]
        if terminal_state == "response"
        else [],
        "citations_valid": terminal_state == "response",
        "snapshot_consistent": snapshot_consistent,
        "source_scope_consistent": True,
        "query_trace_present": terminal_state == "response",
        "query_trace_link_consistent": (True if terminal_state == "response" else None),
        "target_kind": None,
        "target_role": None,
        "target_ordinal": None,
        "target_sha256": None,
        "target_char_count": None,
        "transform_kind": None,
        "options": None,
        "planner_calls": planner_calls,
        "resolver_calls": resolver_calls,
        "planner_validation": None if arm == "legacy" else "valid",
        "retrieval_calls": 1,
        "answer_generation_calls": 1,
        "transform_calls": 0,
        "retry_count": retry_count,
    }


def test_candidate_dataset_preserves_accepted_strata_and_grouped_split() -> None:
    cases = build_cases()
    validate_cases(cases)

    assert len(cases) == 300
    assert Counter(row["split"] for row in cases) == {
        "development": 180,
        "held_out": 120,
    }
    assert Counter(row["stratum"] for row in cases) == {
        row["id"]: row["total"] for row in STRATA
    }
    assert sum(row["language"] == "es" for row in cases) == 90

    family_splits: dict[str, set[str]] = {}
    template_splits: dict[str, set[str]] = {}
    context_template_splits: dict[str, set[str]] = {}
    for row in cases:
        family_splits.setdefault(row["semantic_family_id"], set()).add(row["split"])
        template_splits.setdefault(row["prompt_template_id"], set()).add(row["split"])
        if row["context_template_id"] is not None:
            context_template_splits.setdefault(row["context_template_id"], set()).add(
                row["split"]
            )
        assert "development" not in row["semantic_family_key"]
        assert "held_out" not in row["semantic_family_key"]
        assert row["request"].get("source_ids") != []
    assert all(len(splits) == 1 for splits in family_splits.values())
    assert all(len(splits) == 1 for splits in template_splits.values())
    assert all(len(splits) == 1 for splits in context_template_splits.values())
    development_templates = {
        row["prompt_template_id"] for row in cases if row["split"] == "development"
    }
    held_out_templates = {
        row["prompt_template_id"] for row in cases if row["split"] == "held_out"
    }
    assert development_templates.isdisjoint(held_out_templates)
    development_context_templates = {
        row["context_template_id"]
        for row in cases
        if row["split"] == "development" and row["context_template_id"] is not None
    }
    held_out_context_templates = {
        row["context_template_id"]
        for row in cases
        if row["split"] == "held_out" and row["context_template_id"] is not None
    }
    assert development_context_templates.isdisjoint(held_out_context_templates)
    assert all(row["semantic_family_id"].startswith("family-") for row in cases)


def test_historical_challenges_have_valid_user_assistant_turn_order() -> None:
    for _, _, prior_turns, selected_sources, _ in HISTORICAL_CHALLENGES:
        assert len(prior_turns) % 2 == 0
        assert selected_sources != []
        assert [turn["role"] for turn in prior_turns] == [
            role for _ in range(len(prior_turns) // 2) for role in ("user", "assistant")
        ]


def test_candidate_files_are_hashable_and_annotation_labels_remain_blank(
    tmp_path: Path,
) -> None:
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    digests = build_candidate(public_root, private_root)

    manifest = json.loads(
        (public_root / "PREP_FREEZE_MANIFEST_CANDIDATE.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["held_out_status"]["blindness"] == (
        "NOT_BLIND_GENERATOR_IS_SOURCE_VISIBLE"
    )
    assert manifest["annotation_status"]["independent_labels"] == 0
    assert manifest["safety_challenge_status"]["new_families_authored"] == 0
    assert manifest["http_execution_harness_status"] == (
        "DETERMINISTIC_CANONICAL_ROUTE_QUALIFIED; NO_REAL_MODEL_CALLS"
    )
    assert manifest["canonical_api_adapter"]["execution_qualified"] is True
    assert manifest["canonical_api_adapter"]["real_model_qualified"] is False
    assert manifest["canonical_api_adapter"]["real_model_calls"] == 0
    assert manifest["held_out_custody"]["within_domain_only"] is True
    assert (
        manifest["held_out_custody"]["planner_tuning_from_held_out_prohibited"] is True
    )
    schedule = manifest["evaluation_schedule"]
    assert schedule["candidate_status"] == (
        "COUNTERBALANCED_SERIALIZED_PREFERRED_FOR_METHODOLOGY_REVIEW; "
        "NOT_FROZEN_OR_EXECUTED"
    )
    assert schedule["session_count"] == 6
    assert schedule["router_mode_switches"] == 5
    assert schedule["repetition_block_arm_order"] == [
        ["legacy", "planner"],
        ["planner", "legacy"],
        ["legacy", "planner"],
    ]
    assert "not drift-controlled" in schedule["temporal_drift_limitation"]
    assert schedule["warm_pairs_by_alternative"] == {
        "counterbalanced_serialized": 357,
        "full_arm_serialized_baseline": 359,
        "interleaved_diagnostic": 359,
    }
    assert schedule["execution_choice"] == "PENDING_SEPARATE_AUTHORITY"
    assert manifest["thresholds"]["changed"] is False
    assert manifest["thresholds"]["gates"]["wrong_target_executions"] == 0
    assert manifest["thresholds"]["gates"]["planner_warm_p95_max_ms"] == 3000
    assert manifest["request_source_scope_semantics"]["source_ids_null_or_omitted"] == (
        "ALL_ACTIVE"
    )
    assert manifest["request_source_scope_semantics"]["source_ids_empty_list"] == (
        "INVALID_REQUEST"
    )
    assert manifest["response_evidence"]["api_status_field"] == "response_status"
    assert manifest["latency_accounting"]["incomplete_warm_pair_coverage"] == (
        "NOT_EVALUABLE"
    )

    assert len(digests) >= 7
    for name, digest in digests.items():
        if name.startswith("private/"):
            file_path = private_root / name.removeprefix("private/")
        elif (public_root / name).is_file():
            file_path = public_root / name
        else:
            file_path = Path(__file__).resolve().parents[3] / name
        assert hashlib.sha256(file_path.read_bytes()).hexdigest() == digest

    first_packet = [
        json.loads(line)
        for line in (private_root / "annotation_packet_1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    second_packet = [
        json.loads(line)
        for line in (private_root / "annotation_packet_2.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(first_packet) == len(second_packet) == 300
    assert [row["case_id"] for row in first_packet] == [
        row["case_id"] for row in second_packet
    ]
    assert all(row["expected_operation"] is None for row in first_packet)
    assert all("split" not in row and "stratum" not in row for row in first_packet)
    assert not (public_root / "requests_held_out_candidate.jsonl").exists()

    safety_slots = [
        json.loads(line)
        for line in (public_root / "new_safety_family_slots.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(safety_slots) == 40
    assert sum(row["language_required"] == "es" for row in safety_slots) == 15
    assert all(row["prompt"] is None for row in safety_slots)


def test_validator_rejects_semantic_family_crossing_split() -> None:
    cases = build_cases()
    development_case = next(row for row in cases if row["split"] == "development")
    development_case["split"] = "held_out"
    with pytest.raises(ValueError, match="count mismatch|crosses splits"):
        validate_cases(cases)


def test_scorer_keeps_timeout_attempt_in_case_and_latency_denominators() -> None:
    cases = [
        {
            "case_id": "case-1",
            "stratum": "factual_source",
            "language": "en",
            "request": {"source_ids": ["source_manual"]},
            "available_source_ids": ["source_manual"],
        }
    ]
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    observations = []
    for repeat in (1, 2, 3):
        is_timeout = repeat == 3
        observations.append(
            {
                "case_id": "case-1",
                "arm": "planner",
                "repeat": repeat,
                "terminal_state": "timeout" if is_timeout else "response",
                "response_status": None if is_timeout else "answered",
                "measurement_phase": "warm_interactive",
                "elapsed_ms": 120_000 if is_timeout else 800,
                "planner_elapsed_ms": 1_000 if is_timeout else 350,
                "observed_operation": None if is_timeout else "grounded_query",
                "reason_code": None,
                "citation_source_ids": [] if is_timeout else ["source_manual"],
                "citations_valid": not is_timeout,
                "snapshot_consistent": not is_timeout,
                "source_scope_consistent": not is_timeout,
                "query_trace_present": not is_timeout,
                "target_kind": None,
                "target_role": None,
                "target_ordinal": None,
                "target_sha256": None,
                "target_char_count": None,
                "transform_kind": None,
                "options": None,
                "planner_calls": 1,
                "resolver_calls": 0,
                "planner_validation": "valid",
                "retrieval_calls": 1,
                "answer_generation_calls": 1,
                "transform_calls": 0,
                "retry_count": 0,
            }
        )

    report = score_results(
        cases,
        _bind_label(cases[0], label),
        observations,
        arm="planner",
        repeats=3,
    )

    assert report["operation_accuracy"]["numerator"] == 0
    assert report["operation_accuracy"]["denominator"] == 1
    latency = report["latency_by_expected_operation"]["grounded_query"][
        "warm_interactive"
    ]
    assert latency["attempts_including_failures"] == 3
    assert latency["p95_ms_nearest_rank"] == 120_000


def test_scorer_rejects_missing_attempt_instead_of_dropping_it() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "ambiguous_reference",
        "language": "en",
        "request": {"source_ids": None},
        "available_source_ids": ["source_manual", "source_report", "source_policy"],
    }
    label = {
        "expected_operation": "clarify",
        "required_source_ids": [],
        "requires_evidence": False,
        "should_clarify": True,
        "expected_reason_code": "ambiguous_reference",
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    with pytest.raises(ValueError, match="coverage mismatch"):
        score_results(
            [case],
            _bind_label(case, label),
            [],
            arm="planner",
            repeats=1,
        )


def test_scorer_rejects_label_not_bound_to_exact_request() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "ambiguous_reference",
        "language": "en",
        "request": {"source_ids": None},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "clarify",
        "required_source_ids": [],
        "requires_evidence": False,
        "should_clarify": True,
        "expected_reason_code": "ambiguous_reference",
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    labels = _bind_label(case, label)
    labels["case-1"]["request_sha256"] = "wrong-hash"

    with pytest.raises(ValueError, match="not bound to exact request"):
        score_results([case], labels, [], arm="planner", repeats=1)


def test_scorer_rejects_observation_bound_to_another_request() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"question": "What does the manual say?", "source_ids": None},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    labels = _bind_label(case, label)
    observation = _observation(repeat=1)
    observation["request_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="observation request hash"):
        _score_results([case], labels, [observation], arm="planner", repeats=1)


def test_scorer_counts_unlinked_query_trace_as_identity_and_grounding_failure() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"question": "What does the manual say?", "source_ids": None},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    observation = _observation(repeat=1)
    observation["query_trace_link_consistent"] = False

    report = score_results(
        [case], _bind_label(case, label), [observation], arm="planner", repeats=1
    )

    assert report["scope_identity_violations"] == 1
    assert report["critical_grounding_violations"] == 1
    assert report["end_to_end_completion"]["numerator"] == 0


def test_scorer_rejects_planner_retry_and_extra_resolver_calls() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": ["source_manual"]},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }

    with pytest.raises(ValueError, match="at most one planner call"):
        score_results(
            [case],
            _bind_label(case, label),
            [_observation(repeat=1, retry_count=1)],
            arm="planner",
            repeats=1,
        )


def test_scorer_requires_success_for_transform_target_accuracy() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "prior_transform",
        "language": "en",
        "request": {"source_ids": None},
        "available_source_ids": ["source_manual"],
    }
    target = {
        "kind": "prior_turn",
        "role": "assistant",
        "ordinal": 1,
        "sha256": "0" * 64,
        "char_count": 22,
        "transform_kind": "summarize",
        "options": {"bullet_count": 3},
    }
    observation = _observation(
        repeat=1,
        terminal_state="timeout",
        observed_operation=None,
    )
    observation.update(
        {
            "citation_source_ids": [],
            "citations_valid": False,
            "snapshot_consistent": True,
            "query_trace_present": False,
            "target_kind": target["kind"],
            "target_role": target["role"],
            "target_ordinal": target["ordinal"],
            "target_sha256": target["sha256"],
            "target_char_count": target["char_count"],
            "transform_kind": target["transform_kind"],
            "options": target["options"],
            "resolver_calls": 0,
            "retrieval_calls": 0,
            "answer_generation_calls": 0,
            "transform_calls": 0,
        }
    )
    label = {
        "expected_operation": "transform_text",
        "required_source_ids": [],
        "requires_evidence": False,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
        "target": target,
    }

    report = score_results(
        [case],
        _bind_label(case, label),
        [observation],
        arm="planner",
        repeats=1,
    )

    target_accuracy = report["target_options_accuracy"]
    assert target_accuracy["numerator"] == 0
    assert target_accuracy["denominator"] == 1
    assert target_accuracy["rate"] == 0.0
    assert target_accuracy["wilson_95"] is not None

    wrong_target = _observation(repeat=1, observed_operation="transform_text")
    wrong_target.update(
        {
            "citation_source_ids": [],
            "citations_valid": False,
            "query_trace_present": False,
            "retrieval_calls": 0,
            "answer_generation_calls": 0,
            "transform_calls": 1,
            "target_kind": "prior_turn",
            "target_role": "assistant",
            "target_ordinal": 1,
            "target_sha256": "1" * 64,
            "target_char_count": 22,
            "transform_kind": "summarize",
            "options": {"bullet_count": 3},
        }
    )
    wrong_target_report = score_results(
        [case],
        _bind_label(case, label),
        [wrong_target],
        arm="planner",
        repeats=1,
    )
    assert wrong_target_report["wrong_target_executions"] == 1


def test_scorer_counts_snapshot_mismatch_and_reports_plan_validity() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": ["source_manual"]},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    report = score_results(
        [case],
        _bind_label(case, label),
        [
            _observation(repeat=1, snapshot_consistent=False),
            _observation(repeat=2),
            _observation(repeat=3, terminal_state="timeout", observed_operation=None),
        ],
        arm="planner",
        repeats=3,
    )

    assert report["scope_identity_violations"] == 1
    assert report["structured_plan_validity"]["numerator"] == 1
    assert report["structured_plan_validity"]["denominator"] == 1
    assert report["structured_plan_validity"]["rate"] == 1.0
    assert report["structured_plan_validity"]["wilson_95"] is not None
    assert report["case_repeatability"]["numerator"] == 0


def test_safe_clarification_is_not_a_grounding_violation_but_counts_as_outcome() -> (
    None
):
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": ["source_manual"]},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "grounded_query",
        "expected_reason_code": None,
        "allowed_safe_outcomes": [
            {"operation": "clarify", "reason_code": "source_reference_unclear"}
        ],
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "mandatory_unsupported": False,
    }
    observation = _observation(repeat=1, observed_operation="clarify")
    observation.update(
        {
            "reason_code": "source_reference_unclear",
            "citation_source_ids": [],
            "citations_valid": False,
            "query_trace_present": False,
            "retrieval_calls": 0,
            "answer_generation_calls": 0,
        }
    )

    report = score_results(
        [case],
        _bind_label(case, label),
        [observation],
        arm="planner",
        repeats=1,
    )

    assert report["critical_grounding_violations"] == 0
    assert report["outcome_contract_violations"] == 0
    assert report["operation_accuracy"]["numerator"] == 0


@pytest.mark.parametrize("response_status", ["insufficient_evidence", "model_abstain"])
def test_grounded_abstention_is_not_a_critical_grounding_violation(
    response_status: str,
) -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": None},
        "available_source_ids": ["source_manual", "source_report"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    observation = _observation(repeat=1, response_status=response_status)
    observation.update(
        {
            "citation_source_ids": [],
            "citations_valid": False,
            "query_trace_present": False,
        }
    )

    report = score_results(
        [case],
        _bind_label(case, label),
        [observation],
        arm="planner",
        repeats=1,
    )

    assert report["critical_grounding_violations"] == 0
    assert report["scope_identity_violations"] == 0
    assert report["required_source_scope_violations"] == 0
    assert report["end_to_end_completion"]["numerator"] == 0


def test_citation_free_answered_response_is_a_critical_grounding_violation() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": ["source_manual"]},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    observation = _observation(repeat=1, response_status="answered")
    observation.update(
        {
            "citation_source_ids": [],
            "citations_valid": False,
            "query_trace_present": False,
        }
    )

    report = score_results(
        [case],
        _bind_label(case, label),
        [observation],
        arm="planner",
        repeats=1,
    )

    assert report["critical_grounding_violations"] == 1


def test_scorer_flags_wrong_reason_code_for_clarification() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "ambiguous_reference",
        "language": "en",
        "request": {"source_ids": None},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "clarify",
        "required_source_ids": [],
        "requires_evidence": False,
        "should_clarify": True,
        "expected_reason_code": "ambiguous_reference",
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    observation = _observation(repeat=1, observed_operation="clarify")
    observation["reason_code"] = "source_not_found"

    report = score_results(
        [case],
        _bind_label(case, label),
        [observation],
        arm="planner",
        repeats=1,
    )

    assert report["outcome_contract_violations"] == 1


@pytest.mark.parametrize("elapsed", [float("nan"), float("inf"), float("-inf")])
def test_scorer_rejects_non_finite_latency(elapsed: float) -> None:
    case = {
        "case_id": "case-1",
        "stratum": "ambiguous_reference",
        "language": "en",
        "request": {"source_ids": None},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "clarify",
        "required_source_ids": [],
        "requires_evidence": False,
        "should_clarify": True,
        "expected_reason_code": "ambiguous_reference",
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    observation = _observation(repeat=1, observed_operation="clarify")
    observation["elapsed_ms"] = elapsed

    with pytest.raises(ValueError, match="finite and nonnegative"):
        score_results(
            [case],
            _bind_label(case, label),
            [observation],
            arm="planner",
            repeats=1,
        )


def test_scorer_rejects_case_with_invalid_selected_source_scope() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": ["not-in-workspace"]},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }

    with pytest.raises(ValueError, match="invalid selected source identity"):
        score_results(
            [case],
            _bind_label(case, label),
            [_observation(repeat=1)],
            arm="planner",
            repeats=1,
        )


def test_scorer_resolves_null_source_scope_to_all_available_aliases() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": None},
        "available_source_ids": ["source_manual", "source_report"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    observation = _observation(repeat=1)

    report = score_results(
        [case],
        _bind_label(case, label),
        [observation],
        arm="planner",
        repeats=1,
    )

    assert report["scope_identity_violations"] == 0
    assert report["required_source_scope_violations"] == 0


def test_scorer_rejects_inconsistent_api_source_scope_under_all_active_scope() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": None},
        "available_source_ids": ["source_manual", "source_report"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    observation = _observation(repeat=1)
    observation["source_scope_consistent"] = False

    report = score_results(
        [case],
        _bind_label(case, label),
        [observation],
        arm="planner",
        repeats=1,
    )

    assert report["scope_identity_violations"] == 1
    assert report["end_to_end_completion"]["numerator"] == 0


def test_answer_citation_must_match_independently_required_source_scope() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": None},
        "available_source_ids": ["source_manual", "source_report"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    wrong_source_answer = _observation(repeat=1)
    wrong_source_answer["citation_source_ids"] = ["source_report"]

    report = score_results(
        [case],
        _bind_label(case, label),
        [wrong_source_answer],
        arm="planner",
        repeats=1,
    )

    assert report["required_source_scope_violations"] == 1
    assert report["scope_identity_violations"] == 1
    assert report["critical_grounding_violations"] == 1
    assert report["end_to_end_completion"]["numerator"] == 0


def test_scorer_resolves_omitted_source_scope_to_all_available_aliases() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {},
        "available_source_ids": ["source_manual", "source_report"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }

    report = score_results(
        [case],
        _bind_label(case, label),
        [_observation(repeat=1)],
        arm="planner",
        repeats=1,
    )

    assert report["scope_identity_violations"] == 0


def test_scorer_rejects_empty_source_scope_list() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": []},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }

    with pytest.raises(ValueError, match="invalid empty source scope"):
        score_results(
            [case],
            _bind_label(case, label),
            [_observation(repeat=1)],
            arm="planner",
            repeats=1,
        )


def test_scorer_reports_wrong_target_execution_as_safety_event() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "language": "en",
        "request": {"source_ids": ["source_manual"]},
        "available_source_ids": ["source_manual"],
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    observation = _observation(repeat=1, observed_operation="transform_text")
    observation.update(
        {
            "citation_source_ids": [],
            "citations_valid": False,
            "snapshot_consistent": True,
            "query_trace_present": False,
        }
    )

    report = score_results(
        [case],
        _bind_label(case, label),
        [observation],
        arm="planner",
        repeats=1,
    )

    assert report["critical_grounding_violations"] == 1
    assert report["wrong_target_executions"] == 1


def test_paired_scorer_reports_each_required_latency_category() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "request": {
            "question": "What does the manual say?",
            "prior_turns": [],
            "source_ids": ["source_manual"],
        },
        "available_source_ids": ["source_manual"],
        "language": "en",
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    legacy = _observation(repeat=1, arm="legacy", planner_calls=0)
    legacy["elapsed_ms"] = 1000
    planner = _observation(repeat=1)
    planner["elapsed_ms"] = 1100
    labels = _bind_label(case, label)
    legacy["request_sha256"] = labels["case-1"]["request_sha256"]
    planner["request_sha256"] = labels["case-1"]["request_sha256"]
    warm_population = {
        "first_turn_factual": {("case-1", 1)},
        "contextual_grounded": set(),
        "text_transformation": set(),
    }

    report = score_paired_results(
        [case],
        labels,
        {"legacy": [legacy], "planner": [planner]},
        repeats=1,
        warm_comparison_population=warm_population,
    )

    assert set(report["paired_end_to_end_latency"]) == {
        "first_turn_factual",
        "contextual_grounded",
        "text_transformation",
    }
    assert report["paired_end_to_end_latency"]["first_turn_factual"]["status"] == "PASS"

    planner["elapsed_ms"] = 2000
    failed_report = score_paired_results(
        [case],
        labels,
        {"legacy": [legacy], "planner": [planner]},
        repeats=1,
        warm_comparison_population=warm_population,
    )
    assert (
        failed_report["paired_end_to_end_latency"]["first_turn_factual"]["status"]
        == "FAIL"
    )


def test_paired_scorer_refuses_pass_with_incomplete_warm_population() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "request": {
            "question": "What does the manual say?",
            "prior_turns": [],
            "source_ids": ["source_manual"],
        },
        "available_source_ids": ["source_manual"],
        "language": "en",
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
        "expected_reason_code": None,
        "allowed_safe_outcomes": [],
        "mandatory_unsupported": False,
    }
    labels = _bind_label(case, label)
    legacy_rows = []
    planner_rows = []
    for repeat in range(1, 4):
        legacy_row = _observation(repeat=repeat, arm="legacy", planner_calls=0)
        planner_row = _observation(repeat=repeat)
        if repeat in {2, 3}:
            legacy_row["measurement_phase"] = "cold_start"
            planner_row["measurement_phase"] = "cold_start"
        legacy_rows.append(legacy_row)
        planner_rows.append(planner_row)
        legacy_row["request_sha256"] = labels["case-1"]["request_sha256"]
        planner_row["request_sha256"] = labels["case-1"]["request_sha256"]
    warm_population = {
        "first_turn_factual": {
            ("case-1", 1),
            ("case-1", 2),
            ("case-1", 3),
        },
        "contextual_grounded": set(),
        "text_transformation": set(),
    }

    report = score_paired_results(
        [case],
        labels,
        {"legacy": legacy_rows, "planner": planner_rows},
        repeats=3,
        warm_comparison_population=warm_population,
    )

    result = report["paired_end_to_end_latency"]["first_turn_factual"]
    assert result["status"] == "NOT_EVALUABLE"
    assert result["warm_coverage_complete"] is False
    assert result["matched_case_repeats"] == 1
    assert result["expected_warm_case_repeats"] == 3
