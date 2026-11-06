from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from scripts.beta_conv_01a_eval_prep import (
    STRATA,
    build_candidate,
    build_cases,
    validate_cases,
)
from scripts.beta_conv_01a_eval_scoring import score_results


def _observation(
    *,
    repeat: int,
    terminal_state: str = "response",
    observed_operation: str | None = "grounded_query",
    snapshot_consistent: bool = True,
    planner_calls: int = 1,
    resolver_calls: int = 0,
    retry_count: int = 0,
) -> dict[str, object]:
    return {
        "case_id": "case-1",
        "arm": "planner",
        "repeat": repeat,
        "terminal_state": terminal_state,
        "elapsed_ms": 800 if terminal_state == "response" else 120_000,
        "observed_operation": observed_operation,
        "citation_source_ids": ["source_manual"]
        if terminal_state == "response"
        else [],
        "citations_valid": terminal_state == "response",
        "snapshot_consistent": snapshot_consistent,
        "query_trace_present": terminal_state == "response",
        "target_kind": None,
        "target_role": None,
        "target_ordinal": None,
        "target_sha256": None,
        "target_char_count": None,
        "transform_kind": None,
        "options": None,
        "planner_calls": planner_calls,
        "resolver_calls": resolver_calls,
        "planner_validation": "valid",
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
    for row in cases:
        family_splits.setdefault(row["semantic_family_id"], set()).add(row["split"])
    assert all(len(splits) == 1 for splits in family_splits.values())


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
    assert manifest["http_execution_harness_status"] == "NOT_IMPLEMENTED_OR_EXECUTED"

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
            "request": {"source_ids": ["source_manual"]},
        }
    ]
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
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
                "elapsed_ms": 120_000 if is_timeout else 800,
                "observed_operation": None if is_timeout else "grounded_query",
                "citation_source_ids": [] if is_timeout else ["source_manual"],
                "citations_valid": not is_timeout,
                "snapshot_consistent": not is_timeout,
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
        {"case-1": label},
        observations,
        arm="planner",
        repeats=3,
    )

    assert report["operation_accuracy"]["numerator"] == 0
    assert report["operation_accuracy"]["denominator"] == 1
    latency = report["latency_by_expected_operation"]["grounded_query"]
    assert latency["attempts_including_failures"] == 3
    assert latency["p95_ms_nearest_rank"] == 120_000


def test_scorer_rejects_missing_attempt_instead_of_dropping_it() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "ambiguous_reference",
        "request": {"source_ids": []},
    }
    label = {
        "expected_operation": "clarify",
        "required_source_ids": [],
        "requires_evidence": False,
        "should_clarify": True,
    }
    with pytest.raises(ValueError, match="coverage mismatch"):
        score_results(
            [case],
            {"case-1": label},
            [],
            arm="planner",
            repeats=1,
        )


def test_scorer_rejects_planner_retry_and_extra_resolver_calls() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "request": {"source_ids": ["source_manual"]},
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
    }

    with pytest.raises(ValueError, match="at most one planner call"):
        score_results(
            [case],
            {"case-1": label},
            [_observation(repeat=1, retry_count=1)],
            arm="planner",
            repeats=1,
        )


def test_scorer_requires_success_for_transform_target_accuracy() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "prior_transform",
        "request": {"source_ids": []},
    }
    target = {
        "kind": "prior_turn",
        "role": "assistant",
        "ordinal": 1,
        "sha256": "target-hash",
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
        "target": target,
    }

    report = score_results(
        [case],
        {"case-1": label},
        [observation],
        arm="planner",
        repeats=1,
    )

    assert report["target_options_accuracy"] == {
        "numerator": 0,
        "denominator": 1,
        "rate": 0.0,
    }


def test_scorer_counts_snapshot_mismatch_and_reports_plan_validity() -> None:
    case = {
        "case_id": "case-1",
        "stratum": "factual_source",
        "request": {"source_ids": ["source_manual"]},
    }
    label = {
        "expected_operation": "grounded_query",
        "required_source_ids": ["source_manual"],
        "requires_evidence": True,
        "should_clarify": False,
    }
    report = score_results(
        [case],
        {"case-1": label},
        [
            _observation(repeat=1, snapshot_consistent=False),
            _observation(repeat=2),
            _observation(repeat=3, terminal_state="timeout", observed_operation=None),
        ],
        arm="planner",
        repeats=3,
    )

    assert report["scope_identity_violations"] == 1
    assert report["structured_plan_validity"] == {
        "numerator": 1,
        "denominator": 1,
        "rate": 1.0,
    }
    assert report["case_repeatability"] == {"numerator": 1, "denominator": 1}
