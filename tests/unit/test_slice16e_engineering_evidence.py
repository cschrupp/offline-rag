"""Slice 16E engineering evidence exporter tests."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_seneca_engineering_evidence.py"
REGISTRY = REPO_ROOT / "eval" / "presentation" / "accepted_evidence_registry_v1.json"
MANIFEST = REPO_ROOT / "ui" / "public" / "evidence" / "engineering-evidence-v1.json"


def _load_exporter():
    spec = importlib.util.spec_from_file_location(
        "build_seneca_engineering_evidence", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exp = _load_exporter()


def _base_registry(tmp_path: Path, records: list[dict]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "source.md"
    src.write_text("# fixture\nvalue = 1\n", encoding="utf-8")
    digest = exp.sha256_file(src)
    for record in records:
        for ref in record.setdefault("source_refs", []):
            if "path" not in ref:
                ref["path"] = "source.md"
            if "expected_sha256" not in ref:
                ref["expected_sha256"] = digest
            ref.setdefault("source_ref_id", "src")
            ref.setdefault("role", "accepted_report")
            ref.setdefault("source_kind", "accepted_markdown_projection")
            if ref["source_kind"] == "accepted_markdown_projection":
                ref.setdefault("source_locator", "§fixture")
    payload = {
        "contract": exp.REGISTRY_CONTRACT,
        "version": 1,
        "records": records,
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _minimal_record(**overrides) -> dict:
    base = {
        "evidence_id": "retrieval.fixture",
        "evidence_family": "retrieval",
        "title": "Fixture",
        "summary": "Fixture summary",
        "evidence_authority": "accepted",
        "promotion_status": "non_promotional",
        "claim_scope": "Fixture claim scope.",
        "caveats": ["PILOT / NON-PROMOTIONAL"],
        "provenance": {"evidence_family": "retrieval_fixture", "fields": {}},
        "value_source": "curated",
        "presentation": {
            "kind": "fixture",
            "metric": {
                "availability": "measured",
                "value": 1.0,
                "value_qualifier": "exact",
            },
        },
        "source_refs": [{}],
    }
    base.update(overrides)
    return base


def test_committed_manifest_byte_identical_and_stable_id() -> None:
    m1, b1 = exp.build_from_paths(registry_path=REGISTRY, repo_root=REPO_ROOT)
    m2, b2 = exp.build_from_paths(registry_path=REGISTRY, repo_root=REPO_ROOT)
    assert b1 == b2
    assert m1["manifest_id"] == m2["manifest_id"]
    assert m1["manifest_id"].startswith("engmanifest_")
    assert MANIFEST.read_bytes() == b1


def test_deterministic_record_ordering() -> None:
    manifest, _ = exp.build_from_paths(registry_path=REGISTRY, repo_root=REPO_ROOT)
    ids = [row["evidence_id"] for row in manifest["records"]]
    assert ids == sorted(ids)


def test_source_hash_emitted_and_locator_preserved() -> None:
    manifest, _ = exp.build_from_paths(registry_path=REGISTRY, repo_root=REPO_ROOT)
    retrieval = next(
        r for r in manifest["records"] if r["evidence_id"] == "retrieval.slice9hp"
    )
    ref = retrieval["source_refs"][0]
    assert ref["actual_sha256"] == ref["expected_sha256"]
    assert "source_locator" in ref
    assert ref["path"] == "docs/pilots/slice9h_p_results.md"


def test_source_hash_mismatch_fails(tmp_path: Path) -> None:
    record = _minimal_record()
    path = _base_registry(tmp_path, [record])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["records"][0]["source_refs"][0]["expected_sha256"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(exp.ExporterError, match="source hash mismatch"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_missing_source_fails(tmp_path: Path) -> None:
    record = _minimal_record()
    path = _base_registry(tmp_path, [record])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["records"][0]["source_refs"][0]["path"] = "missing.md"
    # keep expected hash from original; resolve fails on missing first
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(exp.ExporterError, match="missing referenced source"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_absolute_source_path_fails(tmp_path: Path) -> None:
    record = _minimal_record()
    path = _base_registry(tmp_path, [record])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["records"][0]["source_refs"][0]["path"] = "/tmp/evil.md"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(exp.ExporterError, match="absolute source path"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_traversal_source_path_fails(tmp_path: Path) -> None:
    record = _minimal_record()
    path = _base_registry(tmp_path, [record])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["records"][0]["source_refs"][0]["path"] = "../outside.md"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(exp.ExporterError, match="path traversal"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_duplicate_evidence_id_fails(tmp_path: Path) -> None:
    a = _minimal_record(evidence_id="retrieval.dup")
    b = _minimal_record(evidence_id="retrieval.dup")
    path = _base_registry(tmp_path, [a, b])
    with pytest.raises(exp.ExporterError, match="duplicate evidence_id"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_unknown_family_fails(tmp_path: Path) -> None:
    path = _base_registry(tmp_path, [_minimal_record(evidence_family="future_family")])
    with pytest.raises(exp.ExporterError, match="unknown evidence_family"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_invalid_authority_fails(tmp_path: Path) -> None:
    path = _base_registry(
        tmp_path, [_minimal_record(evidence_authority="production")]
    )
    with pytest.raises(exp.ExporterError, match="invalid evidence_authority"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_invalid_promotion_fails(tmp_path: Path) -> None:
    path = _base_registry(
        tmp_path, [_minimal_record(promotion_status="winner")]
    )
    with pytest.raises(exp.ExporterError, match="invalid promotion_status"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_missing_claim_scope_fails(tmp_path: Path) -> None:
    record = _minimal_record()
    del record["claim_scope"]
    path = _base_registry(tmp_path, [record])
    with pytest.raises(exp.ExporterError, match="claim_scope"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_measured_requires_numeric(tmp_path: Path) -> None:
    record = _minimal_record(
        presentation={
            "kind": "fixture",
            "metric": {
                "availability": "measured",
                "value": None,
                "value_qualifier": "exact",
            },
        }
    )
    path = _base_registry(tmp_path, [record])
    with pytest.raises(exp.ExporterError, match="measured metric requires numeric"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_non_measured_requires_null(tmp_path: Path) -> None:
    record = _minimal_record(
        presentation={
            "kind": "fixture",
            "metric": {
                "availability": "unevaluable",
                "value": 0,
                "value_qualifier": None,
            },
        }
    )
    path = _base_registry(tmp_path, [record])
    with pytest.raises(exp.ExporterError, match="non-measured metric requires null"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_qualifier_and_measured_zero(tmp_path: Path) -> None:
    record = _minimal_record(
        presentation={
            "kind": "fixture",
            "zero": {
                "availability": "measured",
                "value": 0,
                "value_qualifier": "exact",
            },
            "approx": {
                "availability": "measured",
                "value": 50.83,
                "unit": "s",
                "value_qualifier": "approximate",
            },
        }
    )
    path = _base_registry(tmp_path, [record])
    manifest, _ = exp.build_from_paths(registry_path=path, repo_root=tmp_path)
    presentation = manifest["records"][0]["presentation"]
    assert presentation["zero"]["value"] == 0
    assert presentation["approx"]["value_qualifier"] == "approximate"

    bad = _minimal_record(
        presentation={
            "kind": "fixture",
            "metric": {
                "availability": "measured",
                "value": 1,
                "value_qualifier": "roughly",
            },
        }
    )
    bad_path = _base_registry(tmp_path / "bad", [bad])
    with pytest.raises(exp.ExporterError, match="value_qualifier"):
        exp.build_from_paths(registry_path=bad_path, repo_root=tmp_path / "bad")


def test_nan_infinity_rejected(tmp_path: Path) -> None:
    for bad in (float("nan"), float("inf")):
        record = _minimal_record(
            presentation={
                "kind": "fixture",
                "metric": {
                    "availability": "measured",
                    "value": bad,
                    "value_qualifier": "exact",
                },
            }
        )
        path = _base_registry(tmp_path / str(bad), [record])
        with pytest.raises(exp.ExporterError, match="NaN/Infinity"):
            exp.build_from_paths(registry_path=path, repo_root=tmp_path / str(bad))


def test_14c_machine_extraction_from_committed_artifacts() -> None:
    manifest, _ = exp.build_from_paths(registry_path=REGISTRY, repo_root=REPO_ROOT)
    row = next(
        r for r in manifest["records"] if r["evidence_id"] == "performance.slice14c"
    )
    variants = {v["variant_id"]: v for v in row["presentation"]["variants"]}
    assert set(variants) == {"hybrid", "hybrid_rerank"}
    assert variants["hybrid"]["quality"]["ndcg_at_10"]["value"] == pytest.approx(
        0.7905068212751879
    )
    assert variants["hybrid"]["latency"]["retrieval_p50"]["value"] == pytest.approx(
        5.617130434024148
    )
    assert variants["hybrid_rerank"]["latency"]["retrieval_p95"]["value"] == pytest.approx(
        13.53324203192023
    )
    assert variants["hybrid"]["quality"]["ndcg_at_10"]["value_qualifier"] == "exact"
    assert row["provenance"]["fields"]["suite_id"].startswith("perfsuite_")
    assert row["provenance"]["fields"]["run_id"].startswith("perfrun_")
    assert row["presentation"]["variants"][0]["resources"]["vram_availability"][
        "availability"
    ] == "unavailable"


def test_check_mode_passes_and_detects_drift(tmp_path: Path) -> None:
    assert exp.main(["--check"]) == 0
    drifted = tmp_path / "engineering-evidence-v1.json"
    drifted.write_text("{}\n", encoding="utf-8")
    assert (
        exp.main(
            [
                "--check",
                "--output",
                str(drifted),
            ]
        )
        == 1
    )


def test_markdown_locator_required_for_markdown_projection(tmp_path: Path) -> None:
    record = _minimal_record()
    path = _base_registry(tmp_path, [record])
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["records"][0]["source_refs"][0]["source_locator"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(exp.ExporterError, match="source_locator required"):
        exp.build_from_paths(registry_path=path, repo_root=tmp_path)


def test_security_and_recovery_semantics_present_in_manifest() -> None:
    manifest, _ = exp.build_from_paths(registry_path=REGISTRY, repo_root=REPO_ROOT)
    security = next(
        r for r in manifest["records"] if r["evidence_id"] == "security.slice13b"
    )
    primary = security["presentation"]["primary"]
    assert primary["execution"] == "Completed"
    assert "Fail" in primary["campaign_outcome"]
    assert "unevaluable" in primary["interpretation"].lower()
    assert primary["harness_implementation"] == "Accepted"
    recovery = next(
        r for r in manifest["records"] if r["evidence_id"] == "recovery.slice12c"
    )
    assert recovery["promotion_status"] == "disabled"
    assert recovery["presentation"]["product_recovery"] == "Disabled"


def test_level_c_approximate_and_unevaluable() -> None:
    manifest, _ = exp.build_from_paths(registry_path=REGISTRY, repo_root=REPO_ROOT)
    level_c = next(
        r
        for r in manifest["records"]
        if r["evidence_id"] == "performance.slice14-level-c"
    )
    metrics = level_c["presentation"]["metrics"]
    assert metrics["end_to_end_p50"]["value_qualifier"] == "approximate"
    assert metrics["end_to_end_p50"]["value"] == 50.83
    assert metrics["ttft"]["availability"] == "unevaluable"
    assert metrics["ttft"]["value"] is None
    assert not math.isnan(0)  # keep import used if refactored
