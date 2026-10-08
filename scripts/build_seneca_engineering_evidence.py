#!/usr/bin/env python3
"""Deterministic Seneca Engineering evidence exporter (Slice 16E).

Reads the human-reviewed presentation registry and projects a static
presentation manifest for the Seneca UI.

Scientific / evidence world → presentation world only.
No evaluation execution. No arrow back up.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

REGISTRY_CONTRACT = "seneca-engineering-evidence-registry-v1"
MANIFEST_CONTRACT = "seneca-engineering-evidence-manifest-v1"
ALLOWED_FAMILIES = frozenset(
    {"retrieval", "generation", "recovery", "security", "performance"}
)
ALLOWED_AUTHORITY = frozenset({"authoritative", "accepted", "historical"})
ALLOWED_PROMOTION = frozenset(
    {"promoted", "non_promotional", "disabled", "not_applicable"}
)
ALLOWED_AVAILABILITY = frozenset(
    {"measured", "unavailable", "unevaluable", "not_applicable"}
)
ALLOWED_QUALIFIER = frozenset({"exact", "approximate"})

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO_ROOT / "eval" / "presentation" / "accepted_evidence_registry_v1.json"
DEFAULT_MANIFEST = (
    REPO_ROOT / "ui" / "public" / "evidence" / "engineering-evidence-v1.json"
)


class ExporterError(Exception):
    """Fail-closed exporter error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(obj: Any) -> bytes:
    try:
        text = json.dumps(
            obj,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except ValueError as exc:
        raise ExporterError(f"non-finite JSON value: {exc}") from exc
    return (text + "\n").encode("utf-8")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExporterError(f"invalid JSON in {path}: {exc}") from exc


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExporterError(f"{label} must be an object")
    return value


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExporterError(f"{label} must be a non-empty string")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ExporterError(f"{label} must be an array")
    return value


def resolve_repo_path(repo_root: Path, raw_path: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ExporterError("source path must be a non-empty string")
    if raw_path.startswith(("/", "\\")):
        raise ExporterError(f"absolute source path rejected: {raw_path}")
    if ".." in Path(raw_path).parts:
        raise ExporterError(f"path traversal rejected: {raw_path}")
    # Reject Windows drive / UNC style
    if ":" in raw_path.split("/")[0]:
        raise ExporterError(f"absolute source path rejected: {raw_path}")
    resolved = (repo_root / raw_path).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ExporterError(f"source path escapes repository root: {raw_path}") from exc
    if not resolved.is_file():
        raise ExporterError(f"missing referenced source: {raw_path}")
    return resolved


def validate_metric(metric: Any, *, label: str) -> dict[str, Any]:
    m = _require_mapping(metric, label)
    availability = _require_str(m.get("availability"), f"{label}.availability")
    if availability not in ALLOWED_AVAILABILITY:
        raise ExporterError(f"{label}.availability invalid: {availability}")
    value = m.get("value")
    unit = m.get("unit")
    qualifier = m.get("value_qualifier")
    if unit is not None and (not isinstance(unit, str) or not unit.strip()):
        raise ExporterError(f"{label}.unit must be a non-empty string when present")
    if availability == "measured":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ExporterError(f"{label}: measured metric requires numeric value")
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ExporterError(f"{label}: NaN/Infinity rejected")
        if qualifier not in ALLOWED_QUALIFIER:
            raise ExporterError(
                f"{label}.value_qualifier must be exact|approximate for measured"
            )
    else:
        if value is not None:
            raise ExporterError(f"{label}: non-measured metric requires null value")
        if qualifier not in (None,):
            raise ExporterError(
                f"{label}.value_qualifier must be null for non-measured metrics"
            )
    out: dict[str, Any] = {
        "availability": availability,
        "value": value,
    }
    if unit is not None:
        out["unit"] = unit
    if qualifier is not None:
        out["value_qualifier"] = qualifier
    else:
        out["value_qualifier"] = None
    return out


def _walk_validate_metrics(node: Any, *, path: str) -> Any:
    if isinstance(node, dict):
        if "availability" in node and ("value" in node or "value_qualifier" in node):
            return validate_metric(node, label=path)
        return {
            key: _walk_validate_metrics(value, path=f"{path}.{key}")
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [
            _walk_validate_metrics(item, path=f"{path}[{idx}]")
            for idx, item in enumerate(node)
        ]
    return node


def validate_source_ref(ref: Any, *, label: str, repo_root: Path) -> dict[str, Any]:
    r = _require_mapping(ref, label)
    source_ref_id = _require_str(r.get("source_ref_id"), f"{label}.source_ref_id")
    path = _require_str(r.get("path"), f"{label}.path")
    role = _require_str(r.get("role"), f"{label}.role")
    source_kind = _require_str(r.get("source_kind"), f"{label}.source_kind")
    expected = _require_str(r.get("expected_sha256"), f"{label}.expected_sha256")
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ExporterError(f"{label}.expected_sha256 must be lowercase sha256 hex")
    locator = r.get("source_locator")
    if source_kind == "accepted_markdown_projection":
        if not isinstance(locator, str) or not locator.strip():
            raise ExporterError(
                f"{label}.source_locator required for accepted_markdown_projection"
            )
    elif locator is not None and (
        not isinstance(locator, str) or not locator.strip()
    ):
        raise ExporterError(f"{label}.source_locator malformed")
    resolved = resolve_repo_path(repo_root, path)
    actual = sha256_file(resolved)
    if actual != expected:
        raise ExporterError(
            f"source hash mismatch for {path}: expected {expected}, actual {actual}"
        )
    out: dict[str, Any] = {
        "source_ref_id": source_ref_id,
        "path": path.replace("\\", "/"),
        "role": role,
        "source_kind": source_kind,
        "expected_sha256": expected,
        "actual_sha256": actual,
    }
    if isinstance(locator, str) and locator.strip():
        out["source_locator"] = locator
    return out


def _lookup_source(
    source_refs: list[dict[str, Any]], source_ref_id: str, *, label: str
) -> dict[str, Any]:
    for ref in source_refs:
        if ref["source_ref_id"] == source_ref_id:
            return ref
    raise ExporterError(f"{label}: unknown source_ref_id {source_ref_id}")


def _metric_exact(value: float, *, unit: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "availability": "measured",
        "value": value,
        "value_qualifier": "exact",
    }
    if unit is not None:
        out["unit"] = unit
    return out


def _metric_status(availability: str) -> dict[str, Any]:
    return {
        "availability": availability,
        "value": None,
        "value_qualifier": None,
    }


def extract_performance_14c(
    *,
    registry_record: dict[str, Any],
    source_refs: list[dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any]:
    extraction = _require_mapping(
        registry_record.get("extraction"), "performance.slice14c.extraction"
    )
    agg_ref_id = _require_str(
        extraction.get("aggregate_source_ref_id"),
        "extraction.aggregate_source_ref_id",
    )
    man_ref_id = _require_str(
        extraction.get("run_manifest_source_ref_id"),
        "extraction.run_manifest_source_ref_id",
    )
    agg_ref = _lookup_source(source_refs, agg_ref_id, label="14c aggregate")
    man_ref = _lookup_source(source_refs, man_ref_id, label="14c run_manifest")
    aggregate = load_json(resolve_repo_path(repo_root, agg_ref["path"]))
    run_manifest = load_json(resolve_repo_path(repo_root, man_ref["path"]))
    if not isinstance(aggregate, dict) or not isinstance(run_manifest, dict):
        raise ExporterError("14C aggregate/run_manifest must be objects")

    variants = _require_list(extraction.get("variants"), "extraction.variants")
    quality_by_variant = {
        row["variant"]: row
        for row in aggregate.get("quality_by_variant", [])
        if isinstance(row, dict) and "variant" in row
    }
    latency_by_variant = {
        row["variant"]: row
        for row in aggregate.get("by_variant", [])
        if isinstance(row, dict) and "variant" in row
    }
    resource_by_variant = {
        row["variant"]: row
        for row in aggregate.get("resource_by_variant", [])
        if isinstance(row, dict) and "variant" in row
    }

    out_variants: list[dict[str, Any]] = []
    for variant in variants:
        variant_id = _require_str(variant, "extraction.variants[]")
        if variant_id not in quality_by_variant:
            raise ExporterError(f"14C missing quality for variant {variant_id}")
        if variant_id not in latency_by_variant:
            raise ExporterError(f"14C missing latency for variant {variant_id}")
        q = quality_by_variant[variant_id]
        stats = latency_by_variant[variant_id].get("stats")
        if not isinstance(stats, dict):
            raise ExporterError(f"14C latency stats missing for {variant_id}")
        resources = resource_by_variant.get(variant_id, {})
        vram_avail = aggregate.get("vram_availability")
        if vram_avail == "unavailable":
            vram_metric = _metric_status("unavailable")
        elif vram_avail == "available":
            vram_metric = _metric_exact(1)
        else:
            vram_metric = _metric_status("unevaluable")
        ram_avail = resources.get("ram_availability")
        if ram_avail == "available" and "ram_rss_bytes_p50" in resources:
            ram_metric = _metric_exact(resources["ram_rss_bytes_p50"], unit="bytes")
        elif ram_avail == "unavailable":
            ram_metric = _metric_status("unavailable")
        else:
            ram_metric = _metric_status("unevaluable")
        label = {
            "hybrid": "hybrid",
            "hybrid_rerank": "hybrid + reranker",
        }.get(variant_id, variant_id)
        out_variants.append(
            {
                "variant_id": variant_id,
                "label": label,
                "quality": {
                    "ndcg_at_10": _metric_exact(q["ndcg_at_10"]),
                    "mrr": _metric_exact(q["mrr"]),
                    "hit_at_1": _metric_exact(q["hit_rate_at_1"]),
                    "recall_at_10": _metric_exact(q["recall_at_10"]),
                },
                "latency": {
                    "retrieval_p50": _metric_exact(stats["p50"], unit="s"),
                    "retrieval_p95": _metric_exact(stats["p95"], unit="s"),
                },
                "resources": {
                    "ram_rss_bytes_p50": ram_metric,
                    "vram_availability": vram_metric,
                },
            }
        )

    provenance_fields = {
        "suite_id": aggregate.get("suite_id") or run_manifest.get("suite_id"),
        "run_id": aggregate.get("run_id") or run_manifest.get("run_identity_hash"),
        "config_id": run_manifest.get("config_id"),
        "executing_sha": run_manifest.get("executing_sha"),
        "machine_profile_id": run_manifest.get("machine_profile_id"),
        "start_timestamp": run_manifest.get("start_timestamp"),
        "model_ids": run_manifest.get("model_ids"),
        "machine_profile": {
            "cpu_model": (run_manifest.get("machine_profile") or {}).get("cpu_model"),
            "os_name": (run_manifest.get("machine_profile") or {}).get("os_name"),
            "logical_cores": (run_manifest.get("machine_profile") or {}).get(
                "logical_cores"
            ),
            "system_ram_bytes": (run_manifest.get("machine_profile") or {}).get(
                "system_ram_bytes"
            ),
            "architecture": (run_manifest.get("machine_profile") or {}).get(
                "architecture"
            ),
        },
        "benchmark_level": aggregate.get("benchmark_level"),
        "evidence_class": aggregate.get("evidence_class"),
    }
    return {
        "kind": "performance_14c",
        "comparison_note": _require_str(
            extraction.get("comparison_note"), "extraction.comparison_note"
        ),
        "variants": out_variants,
        "extracted_provenance": provenance_fields,
    }


def project_record(
    record: Any, *, repo_root: Path, seen_ids: set[str]
) -> dict[str, Any]:
    r = _require_mapping(record, "record")
    evidence_id = _require_str(r.get("evidence_id"), "evidence_id")
    if evidence_id in seen_ids:
        raise ExporterError(f"duplicate evidence_id: {evidence_id}")
    seen_ids.add(evidence_id)
    family = _require_str(r.get("evidence_family"), "evidence_family")
    if family not in ALLOWED_FAMILIES:
        raise ExporterError(f"unknown evidence_family: {family}")
    authority = _require_str(r.get("evidence_authority"), "evidence_authority")
    if authority not in ALLOWED_AUTHORITY:
        raise ExporterError(f"invalid evidence_authority: {authority}")
    promotion = _require_str(r.get("promotion_status"), "promotion_status")
    if promotion not in ALLOWED_PROMOTION:
        raise ExporterError(f"invalid promotion_status: {promotion}")
    claim_scope = _require_str(r.get("claim_scope"), "claim_scope")
    title = _require_str(r.get("title"), "title")
    summary = _require_str(r.get("summary"), "summary")
    caveats = [
        _require_str(c, "caveats[]") for c in _require_list(r.get("caveats"), "caveats")
    ]
    provenance = _require_mapping(r.get("provenance"), "provenance")
    if _require_str(provenance.get("evidence_family"), "provenance.evidence_family"):
        pass
    fields = provenance.get("fields")
    if fields is not None and not isinstance(fields, dict):
        raise ExporterError("provenance.fields must be an object when present")

    source_refs = [
        validate_source_ref(ref, label=f"{evidence_id}.source_refs[]", repo_root=repo_root)
        for ref in _require_list(r.get("source_refs"), "source_refs")
    ]
    if not source_refs:
        raise ExporterError(f"{evidence_id}: at least one source_ref required")

    value_source = r.get("value_source", "curated")
    if value_source == "machine_extract":
        if evidence_id != "performance.slice14c":
            raise ExporterError(
                f"{evidence_id}: machine_extract only authorized for performance.slice14c"
            )
        presentation = extract_performance_14c(
            registry_record=r, source_refs=source_refs, repo_root=repo_root
        )
        # Merge extracted provenance into typed provenance fields without inventing.
        merged_fields = dict(fields or {})
        merged_fields.update(presentation.pop("extracted_provenance"))
        provenance_out = {
            "evidence_family": provenance["evidence_family"],
            "fields": merged_fields,
        }
    elif value_source == "curated":
        presentation = _walk_validate_metrics(
            r.get("presentation"), path=f"{evidence_id}.presentation"
        )
        if not isinstance(presentation, dict):
            raise ExporterError(f"{evidence_id}.presentation must be an object")
        provenance_out = {
            "evidence_family": provenance["evidence_family"],
            "fields": fields or {},
        }
    else:
        raise ExporterError(f"{evidence_id}: unknown value_source {value_source}")

    return {
        "evidence_id": evidence_id,
        "evidence_family": family,
        "title": title,
        "summary": summary,
        "evidence_authority": authority,
        "promotion_status": promotion,
        "claim_scope": claim_scope,
        "caveats": caveats,
        "source_refs": source_refs,
        "provenance": provenance_out,
        "presentation": presentation,
    }


def build_manifest(
    registry: dict[str, Any], *, repo_root: Path
) -> tuple[dict[str, Any], bytes]:
    contract = _require_str(registry.get("contract"), "registry.contract")
    if contract != REGISTRY_CONTRACT:
        raise ExporterError(f"unknown registry contract/version: {contract}")
    version = registry.get("version")
    if version != 1:
        raise ExporterError(f"unknown registry contract/version: {version}")
    records_in = _require_list(registry.get("records"), "registry.records")
    seen: set[str] = set()
    records = [project_record(rec, repo_root=repo_root, seen_ids=seen) for rec in records_in]
    records.sort(key=lambda row: row["evidence_id"])
    payload = {
        "contract": MANIFEST_CONTRACT,
        "version": 1,
        "records": records,
    }
    body = canonical_json_bytes(payload)
    manifest_id = f"engmanifest_{sha256_bytes(body)}"
    manifest = {
        "contract": MANIFEST_CONTRACT,
        "manifest_id": manifest_id,
        "version": 1,
        "records": records,
    }
    return manifest, canonical_json_bytes(manifest)


def build_from_paths(
    *,
    registry_path: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], bytes]:
    registry = load_json(registry_path)
    if not isinstance(registry, dict):
        raise ExporterError("registry root must be an object")
    return build_manifest(registry, repo_root=repo_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build Seneca engineering evidence static manifest (16E)."
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Path to accepted evidence registry JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to write engineering-evidence-v1.json",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root for source path resolution",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Generate in memory and compare to committed output; do not write",
    )
    args = parser.parse_args(argv)
    try:
        _manifest, blob = build_from_paths(
            registry_path=args.registry.resolve(),
            repo_root=args.repo_root.resolve(),
        )
    except ExporterError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.check:
        output = args.output.resolve()
        if not output.is_file():
            print(f"ERROR: committed manifest missing: {output}", file=sys.stderr)
            return 1
        existing = output.read_bytes()
        if existing != blob:
            print(
                "ERROR: engineering evidence manifest drift "
                "(regenerate with scripts/build_seneca_engineering_evidence.py)",
                file=sys.stderr,
            )
            return 1
        print(f"OK: manifest check passed ({_manifest['manifest_id']})")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(blob)
    print(f"Wrote {args.output} ({_manifest['manifest_id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
