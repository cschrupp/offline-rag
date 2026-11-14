"""Independent preservation and negative binding checks for Slice 18D."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "evidence_exporter", ROOT / "scripts/build_seneca_engineering_evidence.py"
)
assert spec and spec.loader
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def registry():
    return json.loads(
        (ROOT / "eval/presentation/accepted_evidence_registry_v3.json").read_text()
    )


def observations(node, path=""):
    if isinstance(node, dict):
        if "availability" in node and "value" in node:
            yield (
                path,
                (
                    node["availability"],
                    node["value"],
                    node.get("unit"),
                    node.get("value_qualifier"),
                ),
            )
        else:
            for key, value in node.items():
                yield from observations(value, path + "/" + key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from observations(value, path + "/" + str(index))


def test_v3_preserves_every_v2_observation_without_recomputation():
    old = json.loads(
        (ROOT / "ui/public/evidence/engineering-evidence-v2.json").read_text()
    )
    new, blob = exporter.build_manifest(registry(), repo_root=ROOT)
    assert new["version"] == 3
    assert (
        blob == (ROOT / "ui/public/evidence/engineering-evidence-v3.json").read_bytes()
    )
    assert len(new["records"]) == len(old["records"]) == 12
    for before, after in zip(old["records"], new["records"], strict=True):
        assert before["evidence_id"] == after["evidence_id"]
        assert dict(observations(before["presentation"])) == dict(
            observations(after["presentation"])
        )


@pytest.mark.parametrize(
    "change,match",
    [
        ("catalog", "catalog identity"),
        ("missing", "missing observation"),
        ("revision", "unknown definition"),
        ("population", "population required"),
        ("unit", "incompatible observation unit"),
        ("unused", "unused observation"),
    ],
)
def test_invalid_v3_bindings_fail_closed(change, match):
    value = registry()
    row = next(r for r in value["records"] if r["evidence_id"] == "retrieval.slice9hp")
    key = next(iter(row["observation_bindings"]))
    binding = row["observation_bindings"][key]
    if change == "catalog":
        value["catalog_id"] = "wrong"
    elif change == "missing":
        del row["observation_bindings"][key]
    elif change == "revision":
        binding["definition_ref"]["definition_revision"] = 999
    elif change == "population":
        binding["population"] = {}
    elif change == "unit":
        row["presentation"]["populations"]["full-22"]["arms"][0]["metrics"][
            "ndcg_at_10"
        ]["unit"] = "bytes"
    else:
        row["observation_bindings"]["/absent"] = copy.deepcopy(binding)
    with pytest.raises(exporter.ExporterError, match=match):
        exporter.build_manifest(value, repo_root=ROOT)


def test_proportion_out_of_range_rejected():
    value = registry()
    row = next(r for r in value["records"] if r["evidence_id"] == "generation.slice10e")
    row["presentation"]["prompts"][0]["metrics"]["answer_rate"]["value"] = 1.4
    with pytest.raises(exporter.ExporterError, match="outside definition range"):
        exporter.build_manifest(value, repo_root=ROOT)


def test_no_fabricated_population_counts():
    for row in registry()["records"]:
        for binding in row["observation_bindings"].values():
            assert set(binding["population"]) <= {"label", "population_id"}
            assert "applicable_count" not in binding
            assert "availability_reason" not in binding


def test_inventory_coverage_and_defect_clearance_are_separate():
    folder = ROOT / "docs/evidence/slice18d_metrics"
    inventory = json.loads((folder / "SURFACE_INVENTORY.json").read_text())
    ledger = json.loads((folder / "DEFECT_LEDGER.json").read_text())
    rows = inventory["surfaces"]
    assert len({row["surface_id"] for row in rows}) == len(rows)
    paths = {
        str(path.relative_to(ROOT))
        for base in ("pages", "features", "components")
        for path in (ROOT / "ui/src" / base).rglob("*.tsx")
    }
    assert paths <= {row["path"] for row in rows}
    catalog = json.loads(
        (ROOT / "eval/presentation/indicator_catalog_v1.json").read_text()
    )
    definitions = {
        (d["definition_id"], d["definition_revision"]) for d in catalog["definitions"]
    }
    dispositions = {
        "AUDITED_KEEP",
        "AUDITED_RELABEL",
        "AUDITED_REFORMAT",
        "AUDITED_EXPLAIN",
        "AUDITED_REMOVE",
        "SCIENTIFIC_ESCALATION_REQUIRED",
        "EXEMPT_NON_METRIC",
    }
    for row in rows:
        assert row["audit_disposition"] in dispositions
        assert row["clearance"] == "cleared"
        if "source_sha256" in row:
            assert (
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
                == row["source_sha256"]
            )
        for ref in row["definition_refs"]:
            assert (ref["definition_id"], ref["definition_revision"]) in definitions
    for defect in ledger["defects"]:
        assert defect["resolution"] in {
            "RESOLVED",
            "REMOVED_FROM_SUPPORTED_SURFACE",
            "ACCEPTED_DEFERRAL",
        }
        if defect["resolution"] == "ACCEPTED_DEFERRAL":
            assert defect["governing_authority"] and defect["allowed_visibility"]
