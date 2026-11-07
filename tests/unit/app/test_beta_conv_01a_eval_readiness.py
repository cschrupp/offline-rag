from __future__ import annotations

import hashlib

from scripts.beta_conv_01a_eval_readiness import (
    REQUIRED_GATES,
    check_readiness,
    verify_candidate_identities,
    verify_gate_evidence,
)


def _complete_readiness_state() -> dict[str, object]:
    digest = "a" * 64
    return {
        "gates": {
            name: {"status": status, "evidence_sha256": digest}
            for name, status in REQUIRED_GATES.items()
        },
        "held_out_custody": {
            "status": "INDEPENDENT_CUSTODY_VERIFIED",
            "evidence_sha256": digest,
        },
        "thresholds_changed": False,
        "held_out_scored": False,
        "real_model_execution_authorized": False,
    }


def test_readiness_requires_all_verified_gates_and_hashes() -> None:
    result = check_readiness(_complete_readiness_state())
    assert result["readiness"] == "READY_FOR_FREEZE_REVIEW"
    assert result["blockers"] == []
    assert result["model_execution_performed"] is False


def test_readiness_fails_closed_for_pending_custody_and_missing_annotation() -> None:
    state = _complete_readiness_state()
    state["gates"]["independent_annotations"] = {
        "status": "PENDING",
        "evidence_sha256": None,
    }
    state["held_out_custody"] = {"status": "PENDING", "evidence_sha256": None}

    result = check_readiness(state)

    assert result["readiness"] == "BLOCKED"
    assert "gate_not_satisfied:independent_annotations" in result["blockers"]
    assert "held_out_custody_not_resolved" in result["blockers"]


def test_readiness_rejects_threshold_drift_and_scored_holdout() -> None:
    state = _complete_readiness_state()
    state["thresholds_changed"] = True
    state["held_out_scored"] = True

    result = check_readiness(state)

    assert "accepted_thresholds_must_remain_unchanged" in result["blockers"]
    assert "held_out_must_remain_unscored_before_freeze" in result["blockers"]


def test_candidate_identity_check_fails_on_changed_candidate_bytes(tmp_path) -> None:
    repository = tmp_path / "repo"
    preparation = repository / "docs/evidence"
    private = repository / "artifacts"
    preparation.mkdir(parents=True)
    private.mkdir(parents=True)
    (repository / "adapter.py").write_text("adapter-v1", encoding="utf-8")
    (preparation / "requests.jsonl").write_text("case-1\n", encoding="utf-8")
    (private / "heldout.jsonl").write_text("heldout-1\n", encoding="utf-8")
    manifest = {
        "identity_sha256": {"adapter.py": hashlib.sha256(b"adapter-v1").hexdigest()},
        "public_file_sha256": {
            "requests.jsonl": hashlib.sha256(b"case-1\n").hexdigest()
        },
        "private_file_sha256": {
            "heldout.jsonl": hashlib.sha256(b"heldout-1\n").hexdigest()
        },
    }

    assert (
        verify_candidate_identities(
            manifest,
            repository_root=repository,
            preparation_root=preparation,
            private_root=private,
        )
        == []
    )

    (preparation / "requests.jsonl").write_text("case-2\n", encoding="utf-8")
    blockers = verify_candidate_identities(
        manifest,
        repository_root=repository,
        preparation_root=preparation,
        private_root=private,
    )
    assert blockers == ["public_candidate_identity_hash_mismatch:requests.jsonl"]


def test_completed_gate_evidence_must_resolve_to_exact_file_hash(tmp_path) -> None:
    evidence_root = tmp_path / "private"
    evidence_root.mkdir()
    evidence = evidence_root / "labels.jsonl"
    evidence.write_text("annotated-labels", encoding="utf-8")
    state = {
        "gates": {
            "independent_annotations": {
                "status": REQUIRED_GATES["independent_annotations"],
                "evidence_location": "private",
                "evidence_path": "labels.jsonl",
                "evidence_sha256": hashlib.sha256(b"annotated-labels").hexdigest(),
            }
        },
        "held_out_custody": {"status": "PENDING", "evidence_sha256": None},
    }

    assert verify_gate_evidence(state, private_root=evidence_root) == []
    evidence.write_text("changed", encoding="utf-8")
    assert verify_gate_evidence(state, private_root=evidence_root) == [
        "gate_evidence_hash_mismatch:independent_annotations"
    ]
