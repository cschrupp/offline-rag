"""Filesystem persistence for sufficiency snapshots and manifests (11A-2)."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.ingestion.io import atomic_write_text
from offline_rag.sufficiency.artifacts import (
    SufficiencyEvalContextManifestV1,
    SufficiencyEvalContextSnapshotV1,
    validate_sufficiency_manifest,
    validate_sufficiency_snapshot,
)


class SufficiencyPersistenceError(RuntimeError):
    """Filesystem persistence / ID-collision failures."""


def default_snapshot_artifact_path(artifacts_root: Path, suffctx_id: str) -> Path:
    return Path(artifacts_root) / "sufficiency" / "snapshots" / f"{suffctx_id}.json"


def default_manifest_artifact_path(artifacts_root: Path, suffctxrun_id: str) -> Path:
    return Path(artifacts_root) / "sufficiency" / "manifests" / f"{suffctxrun_id}.json"


def _snapshot_semantic_equal(
    left: SufficiencyEvalContextSnapshotV1,
    right: SufficiencyEvalContextSnapshotV1,
) -> bool:
    return (
        left.suffctx_id == right.suffctx_id
        and left.contract == right.contract
        and left.provenance.model_dump(mode="json")
        == right.provenance.model_dump(mode="json")
        and left.observation.model_dump(mode="json")
        == right.observation.model_dump(mode="json")
    )


def _manifest_semantic_equal(
    left: SufficiencyEvalContextManifestV1,
    right: SufficiencyEvalContextManifestV1,
) -> bool:
    left_dump = left.model_dump(mode="json", exclude={"audit"})
    right_dump = right.model_dump(mode="json", exclude={"audit"})
    return left_dump == right_dump


def persist_sufficiency_snapshot(
    snapshot: SufficiencyEvalContextSnapshotV1,
    *,
    path: Path,
) -> Path:
    """Atomically persist a snapshot; identical rewrite is idempotent."""
    validate_sufficiency_snapshot(snapshot)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        try:
            existing = SufficiencyEvalContextSnapshotV1.model_validate_json(
                out.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise SufficiencyPersistenceError(
                f"failed to load existing snapshot artifact: {exc}"
            ) from exc
        validate_sufficiency_snapshot(existing)
        if existing.suffctx_id != snapshot.suffctx_id:
            raise SufficiencyPersistenceError(
                "existing snapshot artifact ID mismatch at path"
            )
        if _snapshot_semantic_equal(existing, snapshot):
            return out
        raise SufficiencyPersistenceError(
            "suffctx_id collision with differing semantic contents: "
            f"{snapshot.suffctx_id}"
        )

    atomic_write_text(out, snapshot.model_dump_json())
    return out


def load_sufficiency_snapshot(path: Path) -> SufficiencyEvalContextSnapshotV1:
    """Load a snapshot and enforce OD-11-14 recomputation before returning."""
    try:
        snapshot = SufficiencyEvalContextSnapshotV1.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise SufficiencyPersistenceError(
            f"failed to load snapshot artifact: {exc}"
        ) from exc
    validate_sufficiency_snapshot(snapshot)
    return snapshot


def persist_sufficiency_manifest(
    manifest: SufficiencyEvalContextManifestV1,
    *,
    path: Path,
) -> Path:
    """Atomically persist a manifesto; identical rewrite is idempotent."""
    validate_sufficiency_manifest(manifest)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        try:
            existing = SufficiencyEvalContextManifestV1.model_validate_json(
                out.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise SufficiencyPersistenceError(
                f"failed to load existing manifesto artifact: {exc}"
            ) from exc
        validate_sufficiency_manifest(existing)
        if existing.suffctxrun_id != manifest.suffctxrun_id:
            raise SufficiencyPersistenceError(
                "existing manifesto artifact ID mismatch at path"
            )
        if _manifest_semantic_equal(existing, manifest):
            return out
        raise SufficiencyPersistenceError(
            "suffctxrun_id collision with differing semantic contents: "
            f"{manifest.suffctxrun_id}"
        )

    atomic_write_text(out, manifest.model_dump_json())
    return out


def load_sufficiency_manifest(path: Path) -> SufficiencyEvalContextManifestV1:
    """Load a manifesto and recompute/validate derived accounting before return."""
    try:
        manifest = SufficiencyEvalContextManifestV1.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise SufficiencyPersistenceError(
            f"failed to load manifesto artifact: {exc}"
        ) from exc
    validate_sufficiency_manifest(manifest)
    return manifest
