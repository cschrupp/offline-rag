"""Fail-closed native Stage 2 manifest and workspace-binding validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stage2_timing import (
    CAMPAIGN_EXECUTION_CEILING_SECONDS,
    MAINTENANCE_PREPARATION_ALLOWANCE_SECONDS,
    MINIMUM_MAINTENANCE_ENTRY_WINDOW_SECONDS,
    RESTORATION_RESERVE_SECONDS,
)

NATIVE_SETTINGS_SHA256 = (
    "017ed15283d80d34f69773c642db39e4e9bc1f8e3ef465a3f94a9d2e70d05ee3"
)
SOURCE_COMMIT = "1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e"
IMAGE_DIGEST = "sha256:59252d0655267001c4c9ac42e5a2045131b4086bb1ab84e10dbfd98f2e831dee"
SCIENCE_SETTINGS_SHA256 = (
    "5dce337dc1875b2aa615d62ee771a0ae384559c2da14be384e067ded035f5417"
)
STAGE1_BINDINGS_SHA256 = (
    "7bfc80f1ab7455077e41672d547b3b9938b18fd630f1615e80822477796af9f7"
)
RICH2_BINDING_SHA256 = (
    "b3e2fcae6140ca3d1e87c3d925f3ec281d8c48889ff44723739def4cbd0db7a1"
)


class NativeContractError(ValueError):
    """An input differs from the frozen native Stage 2 contract."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(inputs: Path) -> dict:
    """Verify the exact static native settings manifest and its linked inputs."""
    manifest_path = inputs / "NATIVE_SETTINGS_RICH2.json"
    workloads_path = inputs / "workloads-rich2.json"
    stage1_path = inputs / "stage1-bindings.json"
    provider_path = inputs / "provider_fixture.py"
    if sha256(manifest_path) != NATIVE_SETTINGS_SHA256:
        raise NativeContractError("native settings manifest digest mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    workloads = json.loads(workloads_path.read_text(encoding="utf-8"))
    expected_host = {
        "cloud_project": "seneca-515016",
        "instance": "seneca-review",
        "zone": "us-central1-a",
        "original_container": "seneca-review",
        "original_image_ref": "seneca-review:9c92e706c4b9",
        "original_data_mount": "/srv/seneca/data",
        "model_mount": "/srv/seneca/models",
        "effective_cpus": 4,
    }
    if (
        manifest.get("schema") != "seneca-stage2-native-settings-v1"
        or manifest.get("status") != "prepared_not_execution_authority"
        or manifest.get("application_source_commit") != SOURCE_COMMIT
        or manifest.get("diagnostic_image_digest") != IMAGE_DIGEST
        or manifest.get("host_contract") != expected_host
        or manifest.get("effective_config")
        != {
            "path": "/app/config/base.yaml",
            "sha256": "dc45247f1c807237cf09e8570d26b2600e685f637f967b7f162ed84cf9db77f0",
        }
        or manifest.get("scientific_settings_hash") != SCIENCE_SETTINGS_SHA256
        or manifest.get("workloads_file_sha256") != sha256(workloads_path)
        or manifest.get("stage1_binding_file_sha256") != STAGE1_BINDINGS_SHA256
        or sha256(stage1_path) != STAGE1_BINDINGS_SHA256
        or workloads.get("stage1_binding_file_sha256") != STAGE1_BINDINGS_SHA256
        or manifest.get("rich2_binding_sha256") != RICH2_BINDING_SHA256
        or sha256(inputs / "rich2-stage1-binding.json") != RICH2_BINDING_SHA256
        or workloads.get("rich2_binding_sha256")
        != sha256(inputs / "rich2-stage1-binding.json")
        or manifest.get("provider_fixture") != workloads.get("provider")
        or manifest["provider_fixture"].get("sha256") != sha256(provider_path)
        or manifest.get("budget", {}).get("total_submissions") != 36
        or manifest.get("budget", {}).get("retries") != 0
        or manifest.get("budget", {}).get("diagnostic_execution_ceiling_seconds")
        != CAMPAIGN_EXECUTION_CEILING_SECONDS
        or manifest.get("budget", {}).get("minimum_seconds_to_automatic_stop")
        != MINIMUM_MAINTENANCE_ENTRY_WINDOW_SECONDS
        or manifest.get("budget", {}).get("restoration_reserve_seconds")
        != RESTORATION_RESERVE_SECONDS
        or manifest.get("budget", {}).get("maintenance_preparation_allowance_seconds")
        != MAINTENANCE_PREPARATION_ALLOWANCE_SECONDS
        or manifest.get("scientific_profile", {})
        .get("api", {})
        .get("query_deadline_seconds")
        != 180
    ):
        raise NativeContractError("native settings manifest provenance mismatch")
    return manifest


def validate_scientific_settings(actual: dict, manifest: dict) -> None:
    """Reject publication settings that differ from the frozen native profile."""
    expected = manifest["scientific_settings_hash"]
    observed = [
        binding.get("science_settings_hash")
        for binding in actual.values()
        if isinstance(binding, dict)
    ]
    if len(observed) != 2 or any(value != expected for value in observed):
        raise NativeContractError("native scientific settings identity differs")


def verify_config_file(manifest: dict, path: Path) -> None:
    """Verify the loaded application config bytes without exposing settings."""
    expected = manifest["effective_config"]
    if str(path) != expected["path"] or sha256(path) != expected["sha256"]:
        raise NativeContractError("effective application config identity differs")


def validate_bindings(envelope: dict, *, inputs: Path) -> dict[str, dict]:
    """Validate resolved source IDs against the exact frozen workspace set."""
    load_manifest(inputs)
    workloads_path = inputs / "workloads-rich2.json"
    stage1_path = inputs / "stage1-bindings.json"
    workloads = json.loads(workloads_path.read_text(encoding="utf-8"))["workloads"]
    actual = envelope.get("workloads")
    if envelope.get("schema") != "seneca-stage2-native-bindings-v1":
        raise NativeContractError("native binding schema differs")
    if (
        envelope.get("workloads_sha256") != sha256(workloads_path)
        or envelope.get("stage1_bindings_sha256") != sha256(stage1_path)
        or envelope.get("native_settings_manifest_sha256") != NATIVE_SETTINGS_SHA256
    ):
        raise NativeContractError("native binding provenance mismatch")
    if not isinstance(actual, dict) or set(actual) != {"Recipes", "Rich"}:
        raise NativeContractError("native binding workload set differs")
    for label, binding in actual.items():
        spec = workloads[label]
        if (
            binding.get("workspace_id") != spec["workspace_id"]
            or binding.get("revision") != spec["revision"]
            or binding.get("snapshot_id") != spec["snapshot_id"]
            or binding.get("document_id") != spec["required_document_id"]
            or binding.get("source_mode") != spec["source_mode"]
        ):
            raise NativeContractError(f"native {label} binding identity differs")
        source_ids = binding.get("source_ids")
        if label == "Recipes":
            if (
                not isinstance(source_ids, list)
                or len(source_ids) != 1
                or not all(isinstance(item, str) and item for item in source_ids)
            ):
                raise NativeContractError(
                    "Recipes binding must contain its one resolved source ID"
                )
        elif source_ids is not None:
            raise NativeContractError("Rich binding must retain all-active scope")
    return actual
