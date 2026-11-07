"""Fail-closed checks for the BETA-CONV-01A evaluation freeze candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_GATES = {
    "independent_annotations": "ADJUDICATED_TWO_INDEPENDENT_ANNOTATORS",
    "historical_challenges": "INDEPENDENTLY_MAPPED_AND_REVIEWED",
    "new_safety_families": "40_INDEPENDENTLY_AUTHORED_AND_REVIEWED",
    "api_adapter": "DETERMINISTIC_CANONICAL_ROUTE_QUALIFIED",
    "evaluation_environment": "HOST_AND_MODEL_IDENTITIES_APPROVED",
    "execution_schedule": "ONE_SCHEDULE_FROZEN",
    "scoring_methodology": "INDEPENDENTLY_REVIEWED_AND_HUMAN_ACCEPTED",
}
ALLOWED_HOLDOUT_CUSTODY = {
    "INDEPENDENT_CUSTODY_VERIFIED",
    "SOURCE_VISIBLE_EXCEPTION_HUMAN_ACCEPTED",
}
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREPARATION_ROOT = REPO_ROOT / "docs/evidence/beta_conv_01a/eval_prep_01"
DEFAULT_PRIVATE_ROOT = REPO_ROOT / "artifacts/beta_conv_01a_eval_prep_01"


def _verify_digest_map(records: object, *, root: Path, label: str) -> list[str]:
    blockers: list[str] = []
    if not isinstance(records, Mapping) or not records:
        return [f"{label}_identity_map_missing"]
    for relative_name, expected_hash in records.items():
        if (
            not isinstance(relative_name, str)
            or Path(relative_name).is_absolute()
            or ".." in Path(relative_name).parts
            or not isinstance(expected_hash, str)
            or not SHA256_RE.fullmatch(expected_hash)
        ):
            blockers.append(f"{label}_identity_record_invalid")
            continue
        candidate = root / relative_name
        if not candidate.is_file():
            blockers.append(f"{label}_identity_file_missing:{relative_name}")
            continue
        actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            blockers.append(f"{label}_identity_hash_mismatch:{relative_name}")
    return blockers


def verify_candidate_identities(
    manifest: Mapping[str, Any],
    *,
    repository_root: Path = REPO_ROOT,
    preparation_root: Path = DEFAULT_PREPARATION_ROOT,
    private_root: Path = DEFAULT_PRIVATE_ROOT,
) -> list[str]:
    """Verify all hashed candidate inputs against exact current file bytes."""
    public_files = manifest.get("public_file_sha256")
    if isinstance(public_files, Mapping):
        repository_public: dict[str, Any] = {}
        preparation_public: dict[str, Any] = {}
        for name, digest in public_files.items():
            if isinstance(name, str) and (preparation_root / name).is_file():
                preparation_public[name] = digest
            else:
                repository_public[name] = digest
    else:
        repository_public = None
        preparation_public = None
    blockers = _verify_digest_map(
        manifest.get("identity_sha256"), root=repository_root, label="repository"
    )
    if repository_public:
        blockers.extend(
            _verify_digest_map(
                repository_public, root=repository_root, label="repository_public"
            )
        )
    blockers.extend(
        _verify_digest_map(
            preparation_public,
            root=preparation_root,
            label="public_candidate",
        )
    )
    blockers.extend(
        _verify_digest_map(
            manifest.get("private_file_sha256"), root=private_root, label="private"
        )
    )
    return blockers


def verify_gate_evidence(
    state: Mapping[str, Any],
    *,
    repository_root: Path = REPO_ROOT,
    preparation_root: Path = DEFAULT_PREPARATION_ROOT,
    private_root: Path = DEFAULT_PRIVATE_ROOT,
) -> list[str]:
    """Hash-check evidence paths for every gate that claims completion."""
    roots = {
        "repository": repository_root,
        "preparation": preparation_root,
        "private": private_root,
    }
    blockers: list[str] = []
    gate_records = state.get("gates")
    if not isinstance(gate_records, Mapping):
        gate_records = {}
    records = dict(gate_records)
    if isinstance(state.get("held_out_custody"), Mapping):
        records["held_out_custody"] = state["held_out_custody"]
    for name, record in records.items():
        if not isinstance(record, Mapping):
            continue
        digest = record.get("evidence_sha256")
        if digest is None:
            continue
        location = record.get("evidence_location")
        relative_path = record.get("evidence_path")
        if (
            location not in roots
            or not isinstance(relative_path, str)
            or Path(relative_path).is_absolute()
            or ".." in Path(relative_path).parts
            or not isinstance(digest, str)
            or not SHA256_RE.fullmatch(digest)
        ):
            blockers.append(f"gate_evidence_reference_invalid:{name}")
            continue
        evidence_path = roots[location] / relative_path
        if not evidence_path.is_file():
            blockers.append(f"gate_evidence_file_missing:{name}")
            continue
        actual = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        if actual != digest:
            blockers.append(f"gate_evidence_hash_mismatch:{name}")
    return blockers


def check_readiness(
    state: Mapping[str, Any], identity_blockers: list[str] | None = None
) -> dict[str, Any]:
    """Return missing gates and malformed identities without running a model."""
    blockers: list[str] = []
    blockers.extend(identity_blockers or [])
    gates = state.get("gates")
    if not isinstance(gates, Mapping):
        gates = {}
        blockers.append("gates_object_missing")
    for name, expected in REQUIRED_GATES.items():
        record = gates.get(name)
        if not isinstance(record, Mapping) or record.get("status") != expected:
            blockers.append(f"gate_not_satisfied:{name}")
            continue
        if not SHA256_RE.fullmatch(str(record.get("evidence_sha256", ""))):
            blockers.append(f"gate_evidence_hash_invalid:{name}")

    custody = state.get("held_out_custody")
    if (
        not isinstance(custody, Mapping)
        or custody.get("status") not in ALLOWED_HOLDOUT_CUSTODY
    ):
        blockers.append("held_out_custody_not_resolved")
    elif not SHA256_RE.fullmatch(str(custody.get("evidence_sha256", ""))):
        blockers.append("held_out_custody_evidence_hash_invalid")

    if state.get("thresholds_changed") is not False:
        blockers.append("accepted_thresholds_must_remain_unchanged")
    if state.get("held_out_scored") is not False:
        blockers.append("held_out_must_remain_unscored_before_freeze")
    if state.get("real_model_execution_authorized") is not False:
        blockers.append("real_model_execution_authority_must_remain_separate")

    return {
        "readiness": "READY_FOR_FREEZE_REVIEW" if not blockers else "BLOCKED",
        "blockers": blockers,
        "model_execution_performed": False,
        "held_out_scored": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path, help="JSON readiness state candidate")
    parser.add_argument(
        "manifest", type=Path, help="PREP_FREEZE_MANIFEST_CANDIDATE.json"
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--preparation-root", type=Path, default=DEFAULT_PREPARATION_ROOT
    )
    parser.add_argument("--private-root", type=Path, default=DEFAULT_PRIVATE_ROOT)
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    identity_blockers = verify_candidate_identities(
        manifest,
        repository_root=args.repository_root,
        preparation_root=args.preparation_root,
        private_root=args.private_root,
    )
    gate_evidence_blockers = verify_gate_evidence(
        state,
        repository_root=args.repository_root,
        preparation_root=args.preparation_root,
        private_root=args.private_root,
    )
    result = check_readiness(state, identity_blockers + gate_evidence_blockers)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["readiness"] == "READY_FOR_FREEZE_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
