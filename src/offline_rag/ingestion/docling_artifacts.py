"""Docling local artifact provisioning/validation boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ARTIFACT_MANIFEST_NAME = "offline-rag-artifacts.json"
ARTIFACT_SCHEMA_VERSION = 1
DEFAULT_ARTIFACT_GROUP = "default_pdf_pipeline"


class DoclingArtifactsUnavailableError(RuntimeError):
    """Raised when PDF parsing cannot proceed without local Docling artifacts."""

    def __init__(self, *, artifacts_path: Path, reason: str, action: str) -> None:
        self.artifacts_path = artifacts_path
        self.reason = reason
        self.action = action
        super().__init__(
            "Docling artifacts unavailable for offline PDF parsing.\n"
            f"Resolved path: {artifacts_path}\n"
            f"Reason: {reason}\n"
            "Runtime downloading is intentionally disabled.\n"
            f"Action: {action}\n"
            "Configure paths.docling_artifacts or OFFLINE_RAG_DOCLING_ARTIFACTS_PATH."
        )


@dataclass(frozen=True)
class ArtifactStatus:
    path: Path
    ready: bool
    reason: str
    manifest: dict[str, Any] | None = None


def artifact_manifest_path(artifacts_path: Path) -> Path:
    return artifacts_path / ARTIFACT_MANIFEST_NAME


def validate_docling_artifacts(artifacts_path: Path) -> ArtifactStatus:
    """Lightweight readiness check using OfflineRAG's provisioning manifest."""
    resolved = artifacts_path.expanduser().resolve()
    if not resolved.exists():
        return ArtifactStatus(resolved, False, "directory missing")
    if not resolved.is_dir():
        return ArtifactStatus(resolved, False, "path is not a directory")
    if not any(resolved.iterdir()):
        return ArtifactStatus(resolved, False, "directory is empty")

    manifest_file = artifact_manifest_path(resolved)
    if not manifest_file.exists():
        return ArtifactStatus(resolved, False, "missing offline-rag-artifacts.json provisioning manifest")

    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ArtifactStatus(resolved, False, f"malformed provisioning manifest: {exc}")

    if not isinstance(payload, dict):
        return ArtifactStatus(resolved, False, "provisioning manifest root must be an object")
    if payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        return ArtifactStatus(resolved, False, "unsupported provisioning manifest schema_version")
    if payload.get("provider") != "docling":
        return ArtifactStatus(resolved, False, "provisioning manifest provider must be 'docling'")
    groups = payload.get("artifact_groups")
    if not isinstance(groups, list) or DEFAULT_ARTIFACT_GROUP not in groups:
        return ArtifactStatus(
            resolved,
            False,
            f"artifact_groups must include '{DEFAULT_ARTIFACT_GROUP}'",
        )
    return ArtifactStatus(resolved, True, "ok", payload)


def require_docling_artifacts(artifacts_path: Path) -> Path:
    status = validate_docling_artifacts(artifacts_path)
    if status.ready:
        return status.path
    raise DoclingArtifactsUnavailableError(
        artifacts_path=status.path,
        reason=status.reason,
        action="Run: uv run python scripts/provision_docling.py",
    )


def write_provisioning_manifest(
    artifacts_path: Path,
    *,
    docling_version: str,
    artifact_groups: list[str] | None = None,
) -> Path:
    artifacts_path.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "provider": "docling",
        "docling_version": docling_version,
        "provisioned_at": datetime.now(tz=UTC).isoformat(),
        "artifact_groups": artifact_groups or [DEFAULT_ARTIFACT_GROUP],
    }
    target = artifact_manifest_path(artifacts_path)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
