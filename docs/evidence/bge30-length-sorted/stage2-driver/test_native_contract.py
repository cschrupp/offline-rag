import json
import shutil
from pathlib import Path

import pytest
from native_contract import (
    NATIVE_SETTINGS_SHA256,
    NativeContractError,
    load_manifest,
    sha256,
    validate_bindings,
    validate_scientific_settings,
)

INPUTS = Path(__file__).parents[1] / "stage2-integration"


def binding_envelope(inputs: Path = INPUTS):
    workloads = json.loads((inputs / "workloads-rich2.json").read_text())
    return {
        "schema": "seneca-stage2-native-bindings-v1",
        "workloads_sha256": sha256(inputs / "workloads-rich2.json"),
        "stage1_bindings_sha256": sha256(inputs / "stage1-bindings.json"),
        "native_settings_manifest_sha256": NATIVE_SETTINGS_SHA256,
        "workloads": {
            label: {
                "workspace_id": spec["workspace_id"],
                "revision": spec["revision"],
                "snapshot_id": spec["snapshot_id"],
                "document_id": spec["required_document_id"],
                "source_mode": spec["source_mode"],
                "source_ids": ["src_fixture"] if label == "Recipes" else None,
            }
            for label, spec in workloads["workloads"].items()
        },
    }


def test_native_manifest_matches_frozen_application_and_artifacts():
    manifest = load_manifest(INPUTS)
    assert (
        manifest["application_source_commit"]
        == "1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e"
    )
    assert manifest["diagnostic_image_digest"].startswith("sha256:")
    assert manifest["scientific_profile"]["reranker"]["input_k"] == 30
    assert manifest["scientific_profile"]["api"]["query_deadline_seconds"] == 180
    assert manifest["host_contract"]["original_data_mount"] == "/srv/seneca/data"
    assert manifest["host_contract"]["model_mount"] == "/srv/seneca/models"


def test_rich2_workload_preserves_original_scientific_contract():
    historical = json.loads((INPUTS / "workloads.json").read_text())
    current = json.loads((INPUTS / "workloads-rich2.json").read_text())
    binding = json.loads((INPUTS / "rich2-stage1-binding.json").read_text())
    assert current["models"] == historical["models"]
    assert current["provider"] == historical["provider"]
    assert current["workloads"]["Recipes"] == historical["workloads"]["Recipes"]
    rich = dict(current["workloads"]["Rich"])
    assert rich.pop("workspace_id") == binding["workspace"]["workspace_id"]
    assert rich.pop("revision") == binding["workspace"]["revision"]
    original = dict(historical["workloads"]["Rich"])
    original.pop("workspace_id")
    original.pop("revision")
    assert rich == original
    assert current["rich2_binding_sha256"] == sha256(
        INPUTS / "rich2-stage1-binding.json"
    )


def test_schedule_retains_28_load_and_8_lifecycle_submissions():
    from driver import schedule

    submissions = [submission for wave in schedule() for submission in wave]
    assert len(submissions) == 36
    assert sum(item.case == "load" for item in submissions) == 28
    assert sum(item.case != "load" for item in submissions) == 8
    assert {item.strategy for item in submissions} == {"consecutive", "length_sorted_8"}
    assert [item.ordinal for item in submissions] == list(range(1, 37))


def test_native_manifest_tampering_fails_closed(tmp_path):
    copied_inputs = tmp_path / "inputs"
    copied_inputs.mkdir()
    for name in (
        "NATIVE_SETTINGS_RICH2.json",
        "workloads-rich2.json",
        "stage1-bindings.json",
        "provider_fixture.py",
        "rich2-stage1-binding.json",
    ):
        shutil.copy2(INPUTS / name, copied_inputs / name)
    path = copied_inputs / "NATIVE_SETTINGS_RICH2.json"
    data = json.loads(path.read_text())
    data["scientific_settings_hash"] = "changed"
    path.write_text(json.dumps(data))
    with pytest.raises(NativeContractError, match="manifest digest"):
        load_manifest(copied_inputs)


def test_changed_stage1_bindings_fail_before_native_preflight(tmp_path):
    copied_inputs = tmp_path / "inputs"
    copied_inputs.mkdir()
    for name in (
        "NATIVE_SETTINGS_RICH2.json",
        "workloads-rich2.json",
        "stage1-bindings.json",
        "provider_fixture.py",
        "rich2-stage1-binding.json",
    ):
        shutil.copy2(INPUTS / name, copied_inputs / name)
    (copied_inputs / "stage1-bindings.json").write_bytes(b"{}\n")

    with pytest.raises(NativeContractError, match="manifest provenance"):
        load_manifest(copied_inputs)


def test_resolved_native_bindings_are_tied_to_frozen_workloads():
    resolved = validate_bindings(binding_envelope(), inputs=INPUTS)
    assert resolved["Recipes"]["source_ids"] == ["src_fixture"]
    assert resolved["Rich"]["source_ids"] is None


@pytest.mark.parametrize(
    ("workload", "field", "value", "message"),
    [
        ("Recipes", "snapshot_id", "snap_wrong", "binding identity differs"),
        ("Recipes", "source_ids", [], "one resolved source ID"),
        ("Rich", "source_ids", ["src_fixture"], "all-active scope"),
    ],
)
def test_invalid_native_binding_fails_closed(workload, field, value, message):
    envelope = binding_envelope()
    envelope["workloads"][workload][field] = value
    with pytest.raises(NativeContractError, match=message):
        validate_bindings(envelope, inputs=INPUTS)


def test_native_binding_with_changed_input_hash_fails_closed():
    envelope = binding_envelope()
    envelope["workloads_sha256"] = "0" * 64
    with pytest.raises(NativeContractError, match="provenance mismatch"):
        validate_bindings(envelope, inputs=INPUTS)


def test_native_preflight_rejects_scientific_settings_hash_drift():
    manifest = {"scientific_settings_hash": "expected"}
    actual = {
        "Recipes": {"science_settings_hash": "expected"},
        "Rich": {"science_settings_hash": "expected"},
    }
    validate_scientific_settings(actual, manifest)

    actual["Rich"]["science_settings_hash"] = "changed"
    with pytest.raises(NativeContractError, match="scientific settings identity"):
        validate_scientific_settings(actual, manifest)
