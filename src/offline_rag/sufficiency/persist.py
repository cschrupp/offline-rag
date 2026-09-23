"""Filesystem persistence for sufficiency snapshots and manifests (11A-2)."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.ingestion.io import atomic_write_text
from offline_rag.sufficiency.artifacts import (
    SufficiencyArtifactError,
    SufficiencyEvalContextManifestV1,
    SufficiencyEvalContextSnapshotV1,
    build_suffctxrun_semantic_payload,
)
from offline_rag.sufficiency.contracts import (
    SufficiencyErrorCodeV1,
    SufficiencyErrorDetailsV1,
)
from offline_rag.sufficiency.ids import (
    build_suffctx_id,
    build_suffctx_semantic_payload,
    build_suffctxrun_id,
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
    left_payload = build_suffctxrun_semantic_payload(
        shared_lineage=left.shared_lineage,
        attempt_groups=left.attempt_groups,
        failures=left.failures,
        expected_case_ids=list(left.expected_case_ids),
    )
    right_payload = build_suffctxrun_semantic_payload(
        shared_lineage=right.shared_lineage,
        attempt_groups=right.attempt_groups,
        failures=right.failures,
        expected_case_ids=list(right.expected_case_ids),
    )
    return (
        left.suffctxrun_id == right.suffctxrun_id
        and left.authoritative_for_11b == right.authoritative_for_11b
        and left_payload == right_payload
    )


def persist_sufficiency_snapshot(
    snapshot: SufficiencyEvalContextSnapshotV1,
    *,
    path: Path,
) -> Path:
    """Atomically persist a snapshot; identical rewrite is idempotent."""
    expected_id = build_suffctx_id(
        build_suffctx_semantic_payload(snapshot.provenance, snapshot.observation)
    )
    if snapshot.suffctx_id != expected_id:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "refusing to persist snapshot with mismatched suffctx_id",
            details=SufficiencyErrorDetailsV1(
                field_name="suffctx_id",
                expected=expected_id,
                actual=snapshot.suffctx_id,
            ),
        )

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

    # Persist without rewriting content-addressed semantic fields through audit noise.
    atomic_write_text(out, snapshot.model_dump_json())
    return out


def load_sufficiency_snapshot(path: Path) -> SufficiencyEvalContextSnapshotV1:
    """Load a snapshot and verify content-addressed identity."""
    try:
        snapshot = SufficiencyEvalContextSnapshotV1.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise SufficiencyPersistenceError(
            f"failed to load snapshot artifact: {exc}"
        ) from exc
    expected_id = build_suffctx_id(
        build_suffctx_semantic_payload(snapshot.provenance, snapshot.observation)
    )
    if snapshot.suffctx_id != expected_id:
        raise SufficiencyPersistenceError(
            "loaded snapshot suffctx_id does not match semantic payload"
        )
    return snapshot


def persist_sufficiency_manifest(
    manifest: SufficiencyEvalContextManifestV1,
    *,
    path: Path,
) -> Path:
    """Atomically persist a manifesto; identical rewrite is idempotent."""
    expected_id = build_suffctxrun_id(
        build_suffctxrun_semantic_payload(
            shared_lineage=manifest.shared_lineage,
            attempt_groups=manifest.attempt_groups,
            failures=manifest.failures,
            expected_case_ids=list(manifest.expected_case_ids),
        )
    )
    if manifest.suffctxrun_id != expected_id:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "refusing to persist manifesto with mismatched suffctxrun_id",
            details=SufficiencyErrorDetailsV1(
                field_name="suffctxrun_id",
                expected=expected_id,
                actual=manifest.suffctxrun_id,
            ),
        )

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
    """Load a manifesto and verify content-addressed identity."""
    try:
        manifest = SufficiencyEvalContextManifestV1.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise SufficiencyPersistenceError(
            f"failed to load manifesto artifact: {exc}"
        ) from exc
    expected_id = build_suffctxrun_id(
        build_suffctxrun_semantic_payload(
            shared_lineage=manifest.shared_lineage,
            attempt_groups=manifest.attempt_groups,
            failures=manifest.failures,
            expected_case_ids=list(manifest.expected_case_ids),
        )
    )
    if manifest.suffctxrun_id != expected_id:
        raise SufficiencyPersistenceError(
            "loaded manifesto suffctxrun_id does not match semantic payload"
        )
    return manifest
