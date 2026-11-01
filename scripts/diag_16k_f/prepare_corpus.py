#!/usr/bin/env python3
"""Build a private, content-free 16K-F corpus inventory and manifest.

The inventory records supported input paths, sizes, and streaming SHA-256
digests. A separate curator roster is required to distinguish logical primary
documents, alternate representations, and OCR-only exclusions. This utility
does not parse or ingest source documents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SUPPORTED_MEDIA_TYPES = {
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}

ROSTER_SCHEMA = "16k-f-source-roster-v1"
INVENTORY_SCHEMA = "16k-f-source-inventory-v1"
MANIFEST_SCHEMA = "16k-f-primary-corpus-manifest-v1"
SINGLE_SOURCE_SCHEMA = "16k-f-single-source-manifest-v1"
REPLACEMENT_MANIFEST_SCHEMA = "16k-f-replacement-acceptance-manifest-v1"
ELIGIBLE_STATUS = "SUCCESSFUL_INGESTION_CANDIDATE"
OVERSIZE_STATUS = "EXPECTED_REJECTION_OVERSIZE"
OCR_STATUS = "EXPECTED_REJECTION_OCR_REQUIRED"
DUPLICATE_STATUS = "EXPECTED_DUPLICATE"
MAX_PDF_BYTES = 90 * 1024 * 1024
MAX_OTHER_BYTES = 25 * 1024 * 1024

EXPECTED_SUPPLIED_FILES = 45
EXPECTED_PRIMARY_DOCUMENTS = 39
EXPECTED_NON_OCR_FILES = 42
EXPECTED_OCR_EXCLUSIONS = 3
HASH_BLOCK_BYTES = 1024 * 1024


class PreparationError(ValueError):
    """Raised when the corpus inventory or curator roster is invalid."""


def build_single_source_manifest(
    root: Path,
    inventory: dict[str, Any],
    *,
    relative_path: str,
    text_bearing_confirmed: bool,
) -> dict[str, Any]:
    """Build a content-free manifest for one curator-confirmed text source."""
    if inventory.get("schema") != INVENTORY_SCHEMA:
        raise PreparationError("unsupported inventory schema")
    if text_bearing_confirmed is not True:
        raise PreparationError(
            "single-source manifest requires text-bearing confirmation"
        )
    inventory_by_path = {
        item["relative_path"]: item for item in inventory.get("files", [])
    }
    item = inventory_by_path.get(relative_path)
    if item is None:
        raise PreparationError("single source is absent from the inventory")
    path = _resolve_input(root, relative_path)
    byte_size = path.stat().st_size
    digest = _sha256_path(path)
    if byte_size != item["byte_size"] or digest != item["sha256"]:
        raise PreparationError("source changed after inventory creation")
    source = {
        "relative_path": relative_path,
        "byte_size": byte_size,
        "media_type": item["media_type"],
        "sha256": digest,
        "role": "primary",
        "text_bearing": True,
    }
    body = {
        "schema": SINGLE_SOURCE_SCHEMA,
        "inventory_sha256": inventory["inventory_sha256"],
        "source_count": 1,
        "source": source,
    }
    body["manifest_sha256"] = hashlib.sha256(_canonical_json(body)).hexdigest()
    return body


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _verify_inventory(inventory: dict[str, Any]) -> None:
    if inventory.get("schema") != INVENTORY_SCHEMA:
        raise PreparationError("unsupported inventory schema")
    body = {key: value for key, value in inventory.items() if key != "inventory_sha256"}
    declared = inventory.get("inventory_sha256")
    actual = hashlib.sha256(_canonical_json(body)).hexdigest()
    if not isinstance(declared, str) or declared != actual:
        raise PreparationError("inventory hash does not match its contents")
    files = inventory.get("files")
    if (
        not isinstance(files, list)
        or inventory.get("supported_file_count") != len(files)
        or not files
    ):
        raise PreparationError("inventory file count is invalid")


def validate_replacement_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the replacement population and return its eligible source rows."""
    if manifest.get("schema") != REPLACEMENT_MANIFEST_SCHEMA:
        raise PreparationError("unsupported replacement manifest schema")
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    declared_hash = manifest.get("manifest_sha256")
    actual_hash = hashlib.sha256(_canonical_json(body)).hexdigest()
    if not isinstance(declared_hash, str) or declared_hash != actual_hash:
        raise PreparationError("replacement manifest hash does not match its contents")

    representations = manifest.get("representations")
    if not isinstance(representations, list) or not representations:
        raise PreparationError("replacement manifest lacks representations")
    selection_rule = manifest.get("selection_rule")
    if (
        not isinstance(selection_rule, dict)
        or selection_rule.get("supported_media_types")
        != sorted(SUPPORTED_MEDIA_TYPES.values())
        or selection_rule.get("pdf_max_bytes") != MAX_PDF_BYTES
        or selection_rule.get("other_text_max_bytes") != MAX_OTHER_BYTES
        or selection_rule.get("exact_sha256_deduplication") is not True
        or selection_rule.get("native_pdf_text_required") is not True
        or selection_rule.get("ocr_enabled") is not False
    ):
        raise PreparationError("replacement selection rule is invalid")
    paths = [
        row.get("relative_path") for row in representations if isinstance(row, dict)
    ]
    if len(paths) != len(representations) or len(set(paths)) != len(paths):
        raise PreparationError("replacement representation paths are invalid")

    counts = Counter(row.get("disposition") for row in representations)
    expected_counts = manifest.get("population_counts")
    if not isinstance(expected_counts, dict):
        raise PreparationError("replacement population counts are missing")
    if expected_counts.get("admission_and_robustness_paths") != len(representations):
        raise PreparationError("replacement path count does not match representations")
    for disposition in (ELIGIBLE_STATUS, OVERSIZE_STATUS, OCR_STATUS, DUPLICATE_STATUS):
        if expected_counts.get(disposition) != counts.get(disposition, 0):
            raise PreparationError("replacement disposition counts are inconsistent")

    by_hash: dict[str, list[dict[str, Any]]] = {}
    for row in representations:
        digest = row.get("sha256")
        size = row.get("byte_size")
        media_type = row.get("media_type")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or type(size) is not int
            or size < 0
            or media_type not in SUPPORTED_MEDIA_TYPES.values()
        ):
            raise PreparationError("replacement representation identity is invalid")
        limit = MAX_PDF_BYTES if media_type == "application/pdf" else MAX_OTHER_BYTES
        disposition = row.get("disposition")
        expected_reason = row.get("expected_reason")
        native_check = row.get("native_text_check")
        if size > limit:
            if (
                disposition != OVERSIZE_STATUS
                or expected_reason != "source_file_too_large"
            ):
                raise PreparationError(
                    "over-limit representation classification is invalid"
                )
        elif media_type == "application/pdf":
            if not isinstance(native_check, dict):
                raise PreparationError("PDF representation lacks text-screen evidence")
            classification = native_check.get("classification")
            if classification == "NO_NATIVE_TEXT":
                if disposition not in {OCR_STATUS, DUPLICATE_STATUS}:
                    raise PreparationError(
                        "OCR-required representation classification is invalid"
                    )
            elif classification in {"NATIVE_TEXT_ALL_PAGES", "NATIVE_TEXT_SOME_PAGES"}:
                if disposition not in {ELIGIBLE_STATUS, DUPLICATE_STATUS}:
                    raise PreparationError(
                        "native-text representation classification is invalid"
                    )
            else:
                raise PreparationError("PDF native-text screen result is invalid")
        elif disposition not in {ELIGIBLE_STATUS, DUPLICATE_STATUS}:
            raise PreparationError("supported text-file classification is invalid")
        by_hash.setdefault(digest, []).append(row)

    for identity_rows in by_hash.values():
        if len({row["media_type"] for row in identity_rows}) != 1:
            raise PreparationError("one byte identity has conflicting media types")
        if len({row["byte_size"] for row in identity_rows}) != 1:
            raise PreparationError("one byte identity has conflicting sizes")
        dispositions = {row["disposition"] for row in identity_rows}
        if len(identity_rows) == 1:
            if dispositions == {DUPLICATE_STATUS}:
                raise PreparationError("orphan duplicate representation")
            continue
        if dispositions == {ELIGIBLE_STATUS, DUPLICATE_STATUS}:
            canonical_rows = [
                row for row in identity_rows if row["disposition"] == ELIGIBLE_STATUS
            ]
            if len(canonical_rows) != 1:
                raise PreparationError("duplicate identity needs one canonical source")
            canonical_path = canonical_rows[0]["relative_path"]
            if any(
                row.get("canonical_relative_path") != canonical_path
                or row.get("expected_reason") != "duplicate_content_identity"
                for row in identity_rows
                if row["disposition"] == DUPLICATE_STATUS
            ):
                raise PreparationError("duplicate identity reference is inconsistent")
        elif len(dispositions) != 1 or DUPLICATE_STATUS in dispositions:
            raise PreparationError(
                "duplicate identity classifications are inconsistent"
            )

    if expected_counts.get("distinct_byte_identities") != len(by_hash):
        raise PreparationError("replacement identity count is inconsistent")
    eligible_rows = [
        row for row in representations if row["disposition"] == ELIGIBLE_STATUS
    ]
    successful_population = manifest.get("successful_ingestion_population")
    if not isinstance(successful_population, dict):
        raise PreparationError("successful-ingestion population is missing")
    source_rows = successful_population.get("sources")
    if (
        not isinstance(source_rows, list)
        or successful_population.get("source_count") != len(source_rows)
        or len(source_rows) != len(eligible_rows)
    ):
        raise PreparationError("successful-ingestion source count is inconsistent")
    eligible_by_identity = {row["sha256"]: row for row in eligible_rows}
    if len(eligible_by_identity) != len(eligible_rows):
        raise PreparationError("eligible population contains duplicate identities")
    normalized_sources = sorted(
        (
            row.get("relative_path"),
            row.get("byte_size"),
            row.get("media_type"),
            row.get("sha256"),
        )
        for row in source_rows
        if isinstance(row, dict)
    )
    normalized_eligible = sorted(
        (row["relative_path"], row["byte_size"], row["media_type"], row["sha256"])
        for row in eligible_rows
    )
    if normalized_sources != normalized_eligible:
        raise PreparationError("successful-ingestion sources differ from eligible rows")
    identity_hash = hashlib.sha256(
        "\n".join(sorted(eligible_by_identity)).encode("ascii")
    ).hexdigest()
    if successful_population.get("source_identity_sha256") != identity_hash:
        raise PreparationError("successful-ingestion identity hash is inconsistent")
    rejection_cases = manifest.get("expected_rejection_cases")
    if not isinstance(rejection_cases, dict):
        raise PreparationError("expected-rejection cases are missing")
    expected_case_rows = {
        "oversized": [
            {"relative_path": row["relative_path"], "sha256": row["sha256"]}
            for row in representations
            if row["disposition"] == OVERSIZE_STATUS
        ],
        "ocr_required": [
            {"relative_path": row["relative_path"], "sha256": row["sha256"]}
            for row in representations
            if row["disposition"] == OCR_STATUS
        ],
        "exact_duplicates": [
            {
                "relative_path": row["relative_path"],
                "sha256": row["sha256"],
                "canonical_relative_path": row["canonical_relative_path"],
            }
            for row in representations
            if row["disposition"] == DUPLICATE_STATUS
        ],
    }
    if rejection_cases != expected_case_rows:
        raise PreparationError("expected-rejection cases differ from representations")
    robustness_matrix = manifest.get("robustness_matrix")
    if (
        not isinstance(robustness_matrix, dict)
        or robustness_matrix.get("execution_status") != "PREPARED_NOT_EXECUTED"
        or not isinstance(robustness_matrix.get("scenarios"), list)
        or not robustness_matrix.get("scenarios")
    ):
        raise PreparationError("replacement robustness matrix is invalid")
    scenario_rows = robustness_matrix["scenarios"]
    scenarios_by_id = {
        row.get("scenario_id"): row
        for row in scenario_rows
        if isinstance(row, dict) and isinstance(row.get("scenario_id"), str)
    }
    if len(scenarios_by_id) != len(scenario_rows):
        raise PreparationError("replacement robustness scenario IDs are invalid")
    duplicate_hashes = {row["sha256"] for row in expected_case_rows["exact_duplicates"]}
    unpaired_eligible = next(
        (row for row in eligible_rows if row["sha256"] not in duplicate_hashes),
        None,
    )
    expected_scenario_counts = {
        "individual_oversized_admission": len(expected_case_rows["oversized"]),
        "individual_ocr_required_ingestion": len(expected_case_rows["ocr_required"]),
        "exact_duplicate_rejection": len(expected_case_rows["exact_duplicates"]),
        "mixed_valid_oversized_atomic_rejection": int(
            unpaired_eligible is not None and bool(expected_case_rows["oversized"])
        ),
        "mixed_valid_ocr_required_atomic_rejection": int(
            unpaired_eligible is not None and bool(expected_case_rows["ocr_required"])
        ),
        "mixed_valid_duplicate_atomic_rejection": int(
            unpaired_eligible is not None
            and bool(expected_case_rows["exact_duplicates"])
        ),
        "valid_retry_after_rejection": int(unpaired_eligible is not None),
        "post_publication_grounded_query": int(unpaired_eligible is not None),
    }
    if set(scenarios_by_id) != set(expected_scenario_counts) or any(
        scenarios_by_id[scenario_id].get("case_count") != expected_count
        for scenario_id, expected_count in expected_scenario_counts.items()
    ):
        raise PreparationError(
            "replacement robustness scenario counts are inconsistent"
        )
    required_error_evidence = robustness_matrix.get("required_error_evidence")
    if not isinstance(required_error_evidence, list) or not {
        "safe_error_code",
        "bounded_actionable_reason",
        "terminal_operation_or_admission_response",
    }.issubset(required_error_evidence):
        raise PreparationError("replacement robustness error evidence is incomplete")
    comparability = manifest.get("workload_comparability")
    if (
        not isinstance(comparability, dict)
        or comparability.get("comparable_to_historical_39_primary_threshold_population")
        is not False
        or comparability.get("frozen_thresholds_changed") is not False
    ):
        raise PreparationError(
            "replacement workload comparability declaration is invalid"
        )
    return sorted(source_rows, key=lambda row: row["relative_path"])


def verify_replacement_manifest_files(root: Path, manifest: dict[str, Any]) -> None:
    """Recheck every population path against its manifest identity."""
    try:
        canonical_root = root.resolve(strict=True)
    except OSError as exc:
        raise PreparationError("corpus root is unavailable") from exc
    for row in manifest["representations"]:
        path = _resolve_input(canonical_root, row["relative_path"])
        if (
            path.stat().st_size != row["byte_size"]
            or _sha256_path(path) != row["sha256"]
            or SUPPORTED_MEDIA_TYPES.get(path.suffix.lower()) != row["media_type"]
        ):
            raise PreparationError("corpus path changed after replacement manifest")


def build_replacement_acceptance_manifest(
    root: Path,
    inventory: dict[str, Any],
    native_text_checks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build a full-path robustness manifest and a derived eligible source set.

    Native-text evidence is keyed by exact source SHA-256. PDFs must be shown to
    contain native text on at least one page; supported TXT/Markdown sources do
    not require a PDF text-screen result. Every inventoried path is retained.
    """
    _verify_inventory(inventory)
    canonical_root = root.resolve(strict=True)
    representations: list[dict[str, Any]] = []
    by_hash: dict[str, list[dict[str, Any]]] = {}
    inventory_rows = inventory["files"]

    for item in inventory_rows:
        relative_path = item.get("relative_path")
        if not isinstance(relative_path, str) or not relative_path:
            raise PreparationError("inventory contains an invalid source path")
        path = _resolve_input(canonical_root, relative_path)
        size = path.stat().st_size
        digest = _sha256_path(path)
        media_type = SUPPORTED_MEDIA_TYPES.get(path.suffix.lower())
        if (
            size != item.get("byte_size")
            or digest != item.get("sha256")
            or media_type != item.get("media_type")
        ):
            raise PreparationError("source changed after inventory creation")

        limit = MAX_PDF_BYTES if media_type == "application/pdf" else MAX_OTHER_BYTES
        native_check = native_text_checks.get(digest)
        if size > limit:
            disposition = OVERSIZE_STATUS
            reason = "source_file_too_large"
        elif media_type == "application/pdf":
            if not isinstance(native_check, dict):
                raise PreparationError("PDF lacks native-text screen evidence")
            classification = native_check.get("classification")
            if classification == "NO_NATIVE_TEXT":
                disposition = OCR_STATUS
                reason = "ocr_required_while_ocr_disabled"
            elif classification in {"NATIVE_TEXT_ALL_PAGES", "NATIVE_TEXT_SOME_PAGES"}:
                disposition = ELIGIBLE_STATUS
                reason = None
            else:
                raise PreparationError("PDF native-text screen result is invalid")
        else:
            if media_type not in {"text/plain", "text/markdown"}:
                raise PreparationError("unsupported media type in supported inventory")
            disposition = ELIGIBLE_STATUS
            reason = None

        row = {
            "relative_path": relative_path,
            "byte_size": size,
            "media_type": media_type,
            "sha256": digest,
            "disposition": disposition,
            "expected_reason": reason,
            "native_text_check": native_check
            if media_type == "application/pdf"
            else None,
        }
        representations.append(row)
        by_hash.setdefault(digest, []).append(row)

    for identity_rows in by_hash.values():
        media_types = {row["media_type"] for row in identity_rows}
        if len(media_types) != 1:
            raise PreparationError(
                "identical bytes with different supported extensions need curator review"
            )
        original_disposition = identity_rows[0]["disposition"]
        if any(row["disposition"] != original_disposition for row in identity_rows):
            raise PreparationError("identical bytes have inconsistent classifications")
        if original_disposition == ELIGIBLE_STATUS:
            identity_rows.sort(key=lambda row: row["relative_path"])
            canonical_path = identity_rows[0]["relative_path"]
            for duplicate in identity_rows[1:]:
                duplicate["disposition"] = DUPLICATE_STATUS
                duplicate["expected_reason"] = "duplicate_content_identity"
                duplicate["canonical_relative_path"] = canonical_path

    representations.sort(key=lambda row: row["relative_path"])
    eligible_sources = [
        {
            key: row[key]
            for key in ("relative_path", "byte_size", "media_type", "sha256")
        }
        for row in representations
        if row["disposition"] == ELIGIBLE_STATUS
    ]
    eligible_sources.sort(key=lambda row: row["relative_path"])
    disposition_counts = Counter(row["disposition"] for row in representations)
    expected_cases = {
        "oversized": [
            {"relative_path": row["relative_path"], "sha256": row["sha256"]}
            for row in representations
            if row["disposition"] == OVERSIZE_STATUS
        ],
        "ocr_required": [
            {"relative_path": row["relative_path"], "sha256": row["sha256"]}
            for row in representations
            if row["disposition"] == OCR_STATUS
        ],
        "exact_duplicates": [
            {
                "relative_path": row["relative_path"],
                "sha256": row["sha256"],
                "canonical_relative_path": row["canonical_relative_path"],
            }
            for row in representations
            if row["disposition"] == DUPLICATE_STATUS
        ],
    }
    duplicate_hashes = {case["sha256"] for case in expected_cases["exact_duplicates"]}
    valid_source = next(
        (row for row in eligible_sources if row["sha256"] not in duplicate_hashes),
        None,
    )
    robustness_matrix = {
        "execution_status": "PREPARED_NOT_EXECUTED",
        "scenarios": [
            {
                "scenario_id": "individual_oversized_admission",
                "case_count": len(expected_cases["oversized"]),
                "expected_reason": "source_file_too_large",
                "publication_invariant": "workspace_revision_and_snapshot_unchanged",
            },
            {
                "scenario_id": "individual_ocr_required_ingestion",
                "case_count": len(expected_cases["ocr_required"]),
                "expected_reason": "actionable_ocr_required_failure",
                "publication_invariant": "workspace_revision_and_snapshot_unchanged",
            },
            {
                "scenario_id": "exact_duplicate_rejection",
                "case_count": len(expected_cases["exact_duplicates"]),
                "expected_reason": "duplicate_identity_rejected_without_second_source",
                "publication_invariant": "source_count_does_not_increase",
            },
            {
                "scenario_id": "mixed_valid_oversized_atomic_rejection",
                "case_count": 1 if valid_source and expected_cases["oversized"] else 0,
                "valid_sha256": valid_source["sha256"] if valid_source else None,
                "invalid_sha256": (
                    expected_cases["oversized"][0]["sha256"]
                    if expected_cases["oversized"]
                    else None
                ),
                "publication_invariant": "workspace_revision_snapshot_and_sources_unchanged",
            },
            {
                "scenario_id": "mixed_valid_ocr_required_atomic_rejection",
                "case_count": 1
                if valid_source and expected_cases["ocr_required"]
                else 0,
                "valid_sha256": valid_source["sha256"] if valid_source else None,
                "invalid_sha256": (
                    expected_cases["ocr_required"][0]["sha256"]
                    if expected_cases["ocr_required"]
                    else None
                ),
                "publication_invariant": "workspace_revision_snapshot_and_sources_unchanged",
            },
            {
                "scenario_id": "mixed_valid_duplicate_atomic_rejection",
                "case_count": 1
                if valid_source and expected_cases["exact_duplicates"]
                else 0,
                "valid_sha256": valid_source["sha256"] if valid_source else None,
                "duplicate_sha256": (
                    expected_cases["exact_duplicates"][0]["sha256"]
                    if expected_cases["exact_duplicates"]
                    else None
                ),
                "publication_invariant": "workspace_revision_snapshot_and_sources_unchanged",
            },
            {
                "scenario_id": "valid_retry_after_rejection",
                "case_count": 1 if valid_source else 0,
                "source_sha256": valid_source["sha256"] if valid_source else None,
                "required_result": "new_operation_succeeds_after_prior_terminal_rejection",
            },
            {
                "scenario_id": "post_publication_grounded_query",
                "case_count": 1 if valid_source else 0,
                "required_result": "answered_with_active_source_citations",
            },
        ],
        "required_error_evidence": [
            "safe_error_code",
            "bounded_actionable_reason",
            "terminal_operation_or_admission_response",
        ],
        "metric_scope": (
            "full-cold-warm metrics cover eligible sources only; rejection "
            "attempts are reported separately and excluded from workload totals"
        ),
    }
    identity_hash = hashlib.sha256(
        "\n".join(sorted(row["sha256"] for row in eligible_sources)).encode("ascii")
    ).hexdigest()
    body = {
        "schema": REPLACEMENT_MANIFEST_SCHEMA,
        "source_inventory_sha256": inventory["inventory_sha256"],
        "selection_rule": {
            "supported_media_types": sorted(SUPPORTED_MEDIA_TYPES.values()),
            "pdf_max_bytes": MAX_PDF_BYTES,
            "other_text_max_bytes": MAX_OTHER_BYTES,
            "exact_sha256_deduplication": True,
            "native_pdf_text_required": True,
            "ocr_enabled": False,
        },
        "population_counts": {
            "admission_and_robustness_paths": len(representations),
            "distinct_byte_identities": len(by_hash),
            ELIGIBLE_STATUS: disposition_counts[ELIGIBLE_STATUS],
            OVERSIZE_STATUS: disposition_counts[OVERSIZE_STATUS],
            OCR_STATUS: disposition_counts[OCR_STATUS],
            DUPLICATE_STATUS: disposition_counts[DUPLICATE_STATUS],
        },
        "successful_ingestion_population": {
            "source_count": len(eligible_sources),
            "source_identity_sha256": identity_hash,
            "sources": eligible_sources,
        },
        "expected_rejection_cases": expected_cases,
        "robustness_matrix": robustness_matrix,
        "workload_comparability": {
            "comparable_to_historical_39_primary_threshold_population": False,
            "reason": (
                "This extension/limit-selected exact-byte population is not the "
                "historical curator-selected 39 logical-primary roster."
            ),
            "frozen_thresholds_changed": False,
        },
        "representations": representations,
    }
    body["manifest_sha256"] = hashlib.sha256(_canonical_json(body)).hexdigest()
    validate_replacement_manifest(body)
    return body


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(HASH_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_input(root: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PreparationError("source path must remain relative to corpus root")
    path = root / candidate
    resolved_root = root.resolve()
    try:
        resolved_path = path.resolve(strict=True)
    except OSError as exc:
        raise PreparationError("a roster source path is unavailable") from exc
    if not resolved_path.is_relative_to(resolved_root):
        raise PreparationError("source path resolves outside corpus root")
    if not resolved_path.is_file():
        raise PreparationError("a roster source path is not a regular file")
    return resolved_path


def inventory_directory(root: Path) -> dict[str, Any]:
    """Inventory supported source files without reading whole files at once."""
    if not root.is_dir():
        raise PreparationError("corpus root must be an existing directory")

    canonical_root = root.resolve()
    files: list[dict[str, Any]] = []
    ignored_file_count = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        media_type = SUPPORTED_MEDIA_TYPES.get(path.suffix.lower())
        if media_type is None:
            ignored_file_count += 1
            continue

        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(canonical_root):
            raise PreparationError("a corpus file resolves outside corpus root")

        relative_path = path.relative_to(root).as_posix()
        byte_size = resolved_path.stat().st_size
        files.append(
            {
                "relative_path": relative_path,
                "byte_size": byte_size,
                "media_type": media_type,
                "sha256": _sha256_path(resolved_path),
            }
        )

    files.sort(key=lambda item: item["relative_path"])
    body = {
        "schema": INVENTORY_SCHEMA,
        "supported_file_count": len(files),
        "ignored_file_count": ignored_file_count,
        "supported_raw_bytes": sum(item["byte_size"] for item in files),
        "files": files,
    }
    body["inventory_sha256"] = hashlib.sha256(_canonical_json(body)).hexdigest()
    return body


def build_primary_manifest(
    root: Path,
    inventory: dict[str, Any],
    roster: dict[str, Any],
    *,
    workspace_byte_limit: int | None = None,
) -> dict[str, Any]:
    """Validate curator selections and create the frozen logical corpus view.

    The roster must classify all 45 supplied files into 39 primary documents,
    3 non-OCR alternate representations, and 3 OCR-only exclusions. Semantic
    deduplication is by ``logical_document_id``; identical bytes alone do not
    decide whether two representations are the same user document.
    """
    if inventory.get("schema") != INVENTORY_SCHEMA:
        raise PreparationError("unsupported inventory schema")
    if roster.get("schema") != ROSTER_SCHEMA:
        raise PreparationError("unsupported curator roster schema")

    inventory_by_path = {
        item["relative_path"]: item for item in inventory.get("files", [])
    }
    entries = roster.get("sources")
    if not isinstance(entries, list):
        raise PreparationError("roster sources must be a list")
    if len(entries) != EXPECTED_SUPPLIED_FILES:
        raise PreparationError("roster must contain the 45 frozen supplied files")

    seen_paths: set[str] = set()
    primary_by_logical_id: dict[str, dict[str, Any]] = {}
    alternates: list[dict[str, Any]] = []
    ocr_exclusions: list[dict[str, Any]] = []
    file_records: list[dict[str, Any]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            raise PreparationError("each roster source must be an object")
        relative_path = entry.get("relative_path")
        logical_id = entry.get("logical_document_id")
        role = entry.get("role")
        text_bearing = entry.get("text_bearing")

        if not isinstance(relative_path, str) or not relative_path:
            raise PreparationError("every roster source needs a relative path")
        if relative_path in seen_paths:
            raise PreparationError("roster source paths must be unique")
        seen_paths.add(relative_path)
        inventory_item = inventory_by_path.get(relative_path)
        if inventory_item is None:
            raise PreparationError("roster source is absent from the inventory")

        path = _resolve_input(root, relative_path)
        byte_size = path.stat().st_size
        digest = _sha256_path(path)
        if (
            byte_size != inventory_item["byte_size"]
            or digest != inventory_item["sha256"]
        ):
            raise PreparationError("source changed after inventory creation")

        record = {
            "relative_path": relative_path,
            "byte_size": byte_size,
            "media_type": inventory_item["media_type"],
            "sha256": digest,
            "logical_document_id": logical_id,
            "representation": entry.get("representation"),
            "role": role,
            "text_bearing": text_bearing,
        }
        file_records.append(record)

        if role == "primary":
            if not isinstance(logical_id, str) or not logical_id:
                raise PreparationError("primary source requires a logical ID")
            if text_bearing is not True:
                raise PreparationError(
                    "primary sources must be classified text-bearing"
                )
            if logical_id in primary_by_logical_id:
                raise PreparationError("logical document has multiple primaries")
            primary_by_logical_id[logical_id] = record
        elif role == "alternate":
            if not isinstance(logical_id, str) or not logical_id:
                raise PreparationError("alternate source requires a logical ID")
            if text_bearing is not True:
                raise PreparationError("non-OCR alternates must be text-bearing")
            alternates.append(record)
        elif role == "ocr_excluded":
            if logical_id is not None or text_bearing is not False:
                raise PreparationError(
                    "OCR-only exclusions must be marked non-text-bearing"
                )
            ocr_exclusions.append(record)
        else:
            raise PreparationError(
                "roster role must be primary, alternate, or ocr_excluded"
            )

    primary_ids = set(primary_by_logical_id)
    if any(item["logical_document_id"] not in primary_ids for item in alternates):
        raise PreparationError("every alternate must map to a selected primary")
    if len(primary_by_logical_id) != EXPECTED_PRIMARY_DOCUMENTS:
        raise PreparationError(
            "roster must select exactly 39 primary logical documents"
        )
    if len(alternates) + len(primary_by_logical_id) != EXPECTED_NON_OCR_FILES:
        raise PreparationError("roster must identify 42 non-OCR representations")
    if len(ocr_exclusions) != EXPECTED_OCR_EXCLUSIONS:
        raise PreparationError("roster must identify exactly 3 OCR-only exclusions")

    primary = sorted(
        primary_by_logical_id.values(), key=lambda item: item["logical_document_id"]
    )
    alternates.sort(key=lambda item: item["relative_path"])
    ocr_exclusions.sort(key=lambda item: item["relative_path"])
    text_bearing = primary + alternates
    within_file_limit = [
        item for item in text_bearing if item["byte_size"] <= 90 * 1024 * 1024
    ]
    largest_text_bearing = max(text_bearing, key=lambda item: item["byte_size"])
    largest_transport_eligible = (
        max(within_file_limit, key=lambda item: item["byte_size"])
        if within_file_limit
        else None
    )
    primary_raw_bytes = sum(item["byte_size"] for item in primary)

    if workspace_byte_limit is not None and workspace_byte_limit <= 0:
        raise PreparationError("workspace byte limit must be positive")

    capacity_preflight = (
        "NO_CONFIGURED_CEILING"
        if workspace_byte_limit is None
        else "PASS"
        if primary_raw_bytes <= workspace_byte_limit
        else "BLOCKED"
    )
    body = {
        "schema": MANIFEST_SCHEMA,
        "inventory_sha256": inventory["inventory_sha256"],
        "supplied_file_count": len(file_records),
        "primary_document_count": len(primary),
        "non_ocr_representation_count": len(text_bearing),
        "ocr_exclusion_count": len(ocr_exclusions),
        "primary_raw_bytes": primary_raw_bytes,
        "workspace_byte_limit": workspace_byte_limit,
        "workspace_capacity_preflight": capacity_preflight,
        "largest_text_bearing": largest_text_bearing,
        "largest_transport_eligible": largest_transport_eligible,
        "primary_sources": primary,
        "alternate_representations": alternates,
        "ocr_exclusions": ocr_exclusions,
    }
    body["manifest_sha256"] = hashlib.sha256(_canonical_json(body)).hexdigest()
    return body


def summarize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a content-free summary suitable for terminal output."""
    primary = manifest["primary_sources"]
    role_counts = Counter(item["role"] for item in primary)
    return {
        "schema": manifest["schema"],
        "manifest_sha256": manifest["manifest_sha256"],
        "supplied_file_count": manifest["supplied_file_count"],
        "primary_document_count": manifest["primary_document_count"],
        "non_ocr_representation_count": manifest["non_ocr_representation_count"],
        "ocr_exclusion_count": manifest["ocr_exclusion_count"],
        "primary_raw_bytes": manifest["primary_raw_bytes"],
        "workspace_byte_limit": manifest["workspace_byte_limit"],
        "workspace_capacity_preflight": manifest["workspace_capacity_preflight"],
        "largest_text_bearing_bytes": manifest["largest_text_bearing"]["byte_size"],
        "largest_transport_eligible_bytes": (
            manifest["largest_transport_eligible"]["byte_size"]
            if manifest["largest_transport_eligible"]
            else None
        ),
        "primary_role_counts": dict(sorted(role_counts.items())),
    }


def summarize_replacement_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return non-sensitive population counts for the replacement manifest."""
    validate_replacement_manifest(manifest)
    return {
        "schema": manifest["schema"],
        "manifest_sha256": manifest["manifest_sha256"],
        **manifest["population_counts"],
        "successful_ingestion_source_count": manifest[
            "successful_ingestion_population"
        ]["source_count"],
        "historical_16k_f_threshold_population_comparable": False,
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--corpus-dir", type=Path, required=True)
    inventory_parser.add_argument("--output", type=Path, required=True)

    manifest_parser = subparsers.add_parser("manifest")
    manifest_parser.add_argument("--corpus-dir", type=Path, required=True)
    manifest_parser.add_argument("--inventory", type=Path, required=True)
    manifest_parser.add_argument("--roster", type=Path, required=True)
    manifest_parser.add_argument("--output", type=Path, required=True)
    manifest_parser.add_argument(
        "--workspace-byte-limit",
        type=int,
        default=None,
    )
    single_parser = subparsers.add_parser("single-source")
    single_parser.add_argument("--corpus-dir", type=Path, required=True)
    single_parser.add_argument("--inventory", type=Path, required=True)
    single_parser.add_argument("--source-path", required=True)
    single_parser.add_argument("--text-bearing-confirmed", action="store_true")
    single_parser.add_argument("--output", type=Path, required=True)
    replacement_parser = subparsers.add_parser("replacement-manifest")
    replacement_parser.add_argument("--corpus-dir", type=Path, required=True)
    replacement_parser.add_argument("--inventory", type=Path, required=True)
    replacement_parser.add_argument("--native-text-evidence", type=Path, required=True)
    replacement_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inventory":
            inventory = inventory_directory(args.corpus_dir)
            _write_json(args.output, inventory)
            summary = {
                "schema": inventory["schema"],
                "inventory_sha256": inventory["inventory_sha256"],
                "supported_file_count": inventory["supported_file_count"],
                "ignored_file_count": inventory["ignored_file_count"],
                "supported_raw_bytes": inventory["supported_raw_bytes"],
            }
        elif args.command == "manifest":
            inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
            roster = json.loads(args.roster.read_text(encoding="utf-8"))
            manifest = build_primary_manifest(
                args.corpus_dir,
                inventory,
                roster,
                workspace_byte_limit=args.workspace_byte_limit,
            )
            _write_json(args.output, manifest)
            summary = summarize_manifest(manifest)
        elif args.command == "single-source":
            inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
            manifest = build_single_source_manifest(
                args.corpus_dir,
                inventory,
                relative_path=args.source_path,
                text_bearing_confirmed=args.text_bearing_confirmed,
            )
            _write_json(args.output, manifest)
            summary = {
                "schema": manifest["schema"],
                "manifest_sha256": manifest["manifest_sha256"],
                "source_count": 1,
                "source_bytes": manifest["source"]["byte_size"],
            }
        else:
            inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
            native_evidence = json.loads(
                args.native_text_evidence.read_text(encoding="utf-8")
            )
            source_rows = native_evidence.get("ingestion_sources")
            if not isinstance(source_rows, list):
                raise PreparationError("native-text evidence lacks source rows")
            native_checks: dict[str, dict[str, Any]] = {}
            for row in source_rows:
                if not isinstance(row, dict):
                    raise PreparationError("native-text evidence row is invalid")
                digest = row.get("sha256")
                check = row.get("native_text_check")
                if isinstance(digest, str) and isinstance(check, dict):
                    native_checks[digest] = check
            manifest = build_replacement_acceptance_manifest(
                args.corpus_dir,
                inventory,
                native_checks,
            )
            _write_json(args.output, manifest)
            summary = summarize_replacement_manifest(manifest)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, PreparationError) as exc:
        print(f"preparation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
