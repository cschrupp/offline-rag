"""Deterministic tests for the prepared Rich 2 Stage 1 path."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

DRIVER_DIR = Path(__file__).parent
sys.path.insert(0, str(DRIVER_DIR))

import native_host_control
from rich2_stage1 import (
    Rich2Stage1Error,
    _claim_single_use,
    _require_single_use_paths_available,
    validate_binding_document,
    validate_observation,
    workload_labels_for_mode,
)

INPUTS = DRIVER_DIR.parent / "stage2-integration"
BINDING_PATH = INPUTS / "rich2-stage1-binding.json"
HISTORICAL_PATH = INPUTS / "stage1-bindings.json"


def load_binding() -> tuple[dict, str]:
    binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
    historical_sha = hashlib.sha256(HISTORICAL_PATH.read_bytes()).hexdigest()
    return binding, historical_sha


def valid_observation() -> dict:
    candidate_ids = [f"chunk-{index:02d}" for index in range(10)]
    logits = [float(10 - index) for index in range(10)]
    return {
        "candidate_ids": candidate_ids,
        "candidate_document_ids": ["rich2-doc"] * 10,
        "expected_document_id": "rich2-doc",
        "score_pairs": [
            {
                "candidate_id": candidate_id,
                "pair_input_sha256": hashlib.sha256(
                    f"pair-{index}".encode()
                ).hexdigest(),
                "raw_logit": logits[index],
            }
            for index, candidate_id in enumerate(candidate_ids)
        ],
        "ranked_ids": list(candidate_ids),
        "anchor_ids": list(candidate_ids),
        "evidence_unit_ids": ["evidence-unit-1"],
        "expected_candidate_ids": set(candidate_ids),
    }


def test_rich2_binding_is_distinct_and_historical_binding_is_unchanged():
    binding, historical_sha = load_binding()
    validate_binding_document(binding, historical_sha)
    assert (
        binding["workspace"]["workspace_id"]
        != binding["historical_rich_binding"]["workspace_id"]
    )
    assert binding["workspace"]["revision"] == 2
    assert binding["historical_rich_binding"]["preserved_sha256"] == historical_sha


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("metadata", ("Recipes", "Rich")),
        ("isolated", ("Recipes", "Rich")),
        ("native", ("Recipes", "Rich")),
        ("rich2-metadata", ("Recipes",)),
        ("rich2-stage1", ("Recipes",)),
    ],
)
def test_rich2_modes_preserve_historical_rich_validation_path(mode, expected):
    assert workload_labels_for_mode(mode) == expected


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("workspace", "workspace_id"), "ws_wrong"),
        (("workspace", "revision"), 3),
        (("workspace", "source_inventory_sha256"), "0" * 64),
        (("source", "identity", "source_id"), "src_wrong"),
        (("source", "identity", "content_hash"), "0" * 64),
        (("publication", "published_pointer"), "snap_wrong"),
        (("publication", "science_settings_sha256"), "0" * 64),
        (("publication", "snapshot_manifest_sha256"), "0" * 64),
        (("question", "normalized_sha256"), "0" * 64),
        (("source_scope", "mode"), "selected"),
        (("expected_candidate_count",), 9),
        (("effective_config", "sha256"), "0" * 64),
        (("artifacts", "dense", "indexed_child_count"), 9),
        (("artifacts", "lexical", "lexical_files_sha256", "postings.json"), "0" * 64),
        (("status",), "execution_authorized"),
    ],
)
def test_rich2_binding_identity_drift_fails_closed(path, value):
    binding, historical_sha = load_binding()
    changed = copy.deepcopy(binding)
    target = changed
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(Rich2Stage1Error):
        validate_binding_document(changed, historical_sha)


def test_wrong_historical_binding_digest_fails_closed():
    binding, _historical_sha = load_binding()
    with pytest.raises(Rich2Stage1Error, match="historical Rich binding provenance"):
        validate_binding_document(binding, "0" * 64)


def test_candidate_score_ranking_and_scope_are_validated_together():
    observation = valid_observation()
    validate_observation(**observation)


def test_ranking_uses_chunk_id_ascending_for_equal_raw_logits():
    observation = valid_observation()
    observation["candidate_ids"] = ["chunk-z", "chunk-a"] + [
        f"chunk-{index:02d}" for index in range(8)
    ]
    observation["expected_candidate_ids"] = set(observation["candidate_ids"])
    observation["score_pairs"] = [
        {
            "candidate_id": candidate_id,
            "pair_input_sha256": hashlib.sha256(f"pair-{index}".encode()).hexdigest(),
            "raw_logit": 1.0 if index < 2 else 0.0,
        }
        for index, candidate_id in enumerate(observation["candidate_ids"])
    ]
    observation["ranked_ids"] = [
        "chunk-a",
        "chunk-z",
        *observation["candidate_ids"][2:],
    ]
    observation["anchor_ids"] = list(observation["ranked_ids"])

    validate_observation(**observation)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("candidate_count", "fused candidate population"),
        ("candidate_duplicate", "fused candidate population"),
        ("unexpected_candidate", "frozen chunk inventory"),
        ("scope_escape", "candidate escaped"),
        ("score_order", "candidate-score association"),
        ("missing_score", "candidate-score association"),
        ("nonfinite_score", "non-finite"),
        ("malformed_pair_hash", "incomplete or non-finite"),
        ("rank_order", "raw-logit/chunk-ID ordering"),
        ("missing_anchor", "anchor identity instrumentation"),
        ("missing_evidence", "evidence-unit identity instrumentation"),
    ],
)
def test_incomplete_or_unexpected_observation_fails_closed(change, message):
    observation = valid_observation()
    if change == "candidate_count":
        observation["candidate_ids"].pop()
    elif change == "candidate_duplicate":
        observation["candidate_ids"][-1] = observation["candidate_ids"][0]
    elif change == "unexpected_candidate":
        observation["candidate_ids"][-1] = "chunk-outside-snapshot"
        observation["score_pairs"][-1]["candidate_id"] = "chunk-outside-snapshot"
        observation["ranked_ids"][-1] = "chunk-outside-snapshot"
        observation["anchor_ids"][-1] = "chunk-outside-snapshot"
    elif change == "scope_escape":
        observation["candidate_document_ids"][-1] = "other-document"
    elif change == "score_order":
        observation["score_pairs"][0], observation["score_pairs"][1] = (
            observation["score_pairs"][1],
            observation["score_pairs"][0],
        )
    elif change == "missing_score":
        observation["score_pairs"].pop()
    elif change == "nonfinite_score":
        observation["score_pairs"][0]["raw_logit"] = float("nan")
    elif change == "malformed_pair_hash":
        observation["score_pairs"][0]["pair_input_sha256"] = "not-a-hash"
    elif change == "rank_order":
        observation["ranked_ids"][0], observation["ranked_ids"][1] = (
            observation["ranked_ids"][1],
            observation["ranked_ids"][0],
        )
    elif change == "missing_anchor":
        observation["anchor_ids"] = []
    elif change == "missing_evidence":
        observation["evidence_unit_ids"] = []

    with pytest.raises(Rich2Stage1Error, match=message):
        validate_observation(**observation)


def test_single_use_claim_cannot_be_reused(tmp_path):
    claim = tmp_path / "rich2.claimed"
    _claim_single_use(claim, "binding-digest")
    with pytest.raises(FileExistsError):
        _claim_single_use(claim, "binding-digest")
    assert json.loads(claim.read_text())["binding_sha256"] == "binding-digest"


@pytest.mark.parametrize("existing_path", ["claim", "output"])
def test_existing_single_use_artifact_rejected_before_model_work(
    tmp_path, existing_path
):
    claim = tmp_path / "rich2.claimed"
    output = tmp_path / "rich2.json"
    (claim if existing_path == "claim" else output).write_text("occupied")

    with pytest.raises(Rich2Stage1Error, match="already exists"):
        _require_single_use_paths_available(claim, output)


def test_rich2_restoration_layout_checks_its_only_qdrant_copy(tmp_path, monkeypatch):
    observed = []
    monkeypatch.setattr(
        native_host_control,
        "assert_qdrant_unowned",
        lambda path: observed.append(path),
    )

    native_host_control.verify_scratch_unowned(tmp_path, layout="rich2-stage1")

    assert observed == [tmp_path / "data" / "qdrant"]


def test_existing_stage2_restoration_layout_keeps_both_qdrant_checks(
    tmp_path, monkeypatch
):
    observed = []
    monkeypatch.setattr(native_host_control, "docker", lambda *_args: "")
    monkeypatch.setattr(
        native_host_control,
        "assert_qdrant_unowned",
        lambda path: observed.append(path),
    )

    native_host_control.verify_scratch_unowned(tmp_path)

    assert observed == [
        tmp_path / "A" / "data" / "qdrant",
        tmp_path / "B" / "data" / "qdrant",
    ]
