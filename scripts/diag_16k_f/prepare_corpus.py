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
        else:
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
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, PreparationError) as exc:
        print(f"preparation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
