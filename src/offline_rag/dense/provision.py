"""Local embedding model provisioning and readiness checks."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from offline_rag.core.ids import (
    QWEN3_EMBEDDING_ARTIFACT_CONTRACT,
    QWEN3_EMBEDDING_MODEL_ID,
    QWEN3_EMBEDDING_PINNED_REVISION,
    artifact_bytes_hash,
)
from offline_rag.domain.indexing import (
    EmbeddingModelManifest,
    EmbeddingProvisionReport,
    ProvisioningStatus,
)
from offline_rag.ingestion.io import atomic_write_text

EMBEDDING_MANIFEST_NAME = "offline-rag-embedding.json"
DEFAULT_EMBEDDING_DIR_NAME = "qwen3-embedding-0.6b"
DEFAULT_EXPECTED_DIMENSION = 1024

REQUIRED_EMBEDDING_FILES: tuple[str, ...] = (
    "config.json",
    "modules.json",
    "tokenizer_config.json",
)

_WEIGHT_CANDIDATES: tuple[str, ...] = (
    "model.safetensors",
    "pytorch_model.bin",
    "model.safetensors.index.json",
)


class EmbeddingReadiness(StrEnum):
    ABSENT = "absent"
    INVALID = "invalid"
    READY = "ready"


class EmbeddingArtifactsUnavailableError(RuntimeError):
    """Raised when runtime embedding cannot proceed without local artifacts."""

    def __init__(self, *, artifacts_path: Path, reason: str, action: str) -> None:
        self.artifacts_path = artifacts_path
        self.reason = reason
        self.action = action
        super().__init__(
            "Embedding artifacts unavailable for offline dense indexing.\n"
            f"Resolved path: {artifacts_path}\n"
            f"Reason: {reason}\n"
            "Runtime downloading is intentionally disabled.\n"
            f"Action: {action}"
        )


@dataclass(frozen=True)
class EmbeddingArtifactStatus:
    path: Path
    readiness: EmbeddingReadiness
    reason: str
    manifest: EmbeddingModelManifest | None = None


def default_embedding_model_dir(embedding_artifacts_root: Path) -> Path:
    return Path(embedding_artifacts_root).expanduser().resolve() / DEFAULT_EMBEDDING_DIR_NAME


def embedding_manifest_path(model_dir: Path) -> Path:
    return Path(model_dir) / EMBEDDING_MANIFEST_NAME


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _find_weight_file(model_dir: Path) -> Path | None:
    for name in _WEIGHT_CANDIDATES:
        candidate = model_dir / name
        if candidate.is_file():
            return candidate
    return None


def _collect_file_digests(model_dir: Path, *, required: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for name in required:
        path = model_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"missing required embedding file: {name}")
        digests[name] = _sha256_file(path)
    weight = _find_weight_file(model_dir)
    if weight is None:
        raise FileNotFoundError(
            "missing model weights "
            f"(expected one of: {', '.join(_WEIGHT_CANDIDATES)})"
        )
    digests[weight.name] = _sha256_file(weight)
    return digests


def _artifact_id_from_digests(
    *,
    model_id: str,
    revision: str,
    digests: dict[str, str],
) -> str:
    payload = (
        f"{model_id}|{revision}|"
        + "|".join(f"{name}:{digests[name]}" for name in sorted(digests))
    ).encode("utf-8")
    return artifact_bytes_hash(payload)


def validate_embedding_artifacts(
    model_dir: Path,
    *,
    expected_model_id: str = QWEN3_EMBEDDING_MODEL_ID,
    expected_revision: str = QWEN3_EMBEDDING_PINNED_REVISION,
    expected_dimension: int = DEFAULT_EXPECTED_DIMENSION,
) -> EmbeddingArtifactStatus:
    """Return ABSENT / INVALID / READY for a local embedding model directory."""
    resolved = Path(model_dir).expanduser().resolve()
    if not resolved.exists():
        return EmbeddingArtifactStatus(resolved, EmbeddingReadiness.ABSENT, "directory missing")
    if not resolved.is_dir():
        return EmbeddingArtifactStatus(resolved, EmbeddingReadiness.INVALID, "path is not a directory")

    manifest_file = embedding_manifest_path(resolved)
    if not manifest_file.exists():
        if not any(resolved.iterdir()):
            return EmbeddingArtifactStatus(resolved, EmbeddingReadiness.ABSENT, "directory is empty")
        return EmbeddingArtifactStatus(
            resolved,
            EmbeddingReadiness.INVALID,
            f"missing {EMBEDDING_MANIFEST_NAME} provisioning manifest",
        )

    try:
        manifest = EmbeddingModelManifest.model_validate_json(
            manifest_file.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError, ValidationError) as exc:
        return EmbeddingArtifactStatus(
            resolved,
            EmbeddingReadiness.INVALID,
            f"malformed provisioning manifest: {exc}",
        )

    if manifest.model_id != expected_model_id:
        return EmbeddingArtifactStatus(
            resolved,
            EmbeddingReadiness.INVALID,
            f"manifest model_id mismatch: {manifest.model_id}",
        )
    if manifest.requested_revision != expected_revision and manifest.resolved_revision != expected_revision:
        return EmbeddingArtifactStatus(
            resolved,
            EmbeddingReadiness.INVALID,
            f"manifest revision mismatch: {manifest.resolved_revision}",
        )
    if manifest.expected_dimension != expected_dimension:
        return EmbeddingArtifactStatus(
            resolved,
            EmbeddingReadiness.INVALID,
            f"manifest dimension mismatch: {manifest.expected_dimension}",
        )
    if manifest.artifact_contract != QWEN3_EMBEDDING_ARTIFACT_CONTRACT:
        return EmbeddingArtifactStatus(
            resolved,
            EmbeddingReadiness.INVALID,
            f"unsupported artifact_contract: {manifest.artifact_contract}",
        )

    try:
        digests = _collect_file_digests(resolved, required=list(REQUIRED_EMBEDDING_FILES))
    except FileNotFoundError as exc:
        return EmbeddingArtifactStatus(resolved, EmbeddingReadiness.INVALID, str(exc))

    for name, expected in manifest.file_digests.items():
        actual = digests.get(name)
        if actual is None:
            path = resolved / name
            if not path.is_file():
                return EmbeddingArtifactStatus(
                    resolved,
                    EmbeddingReadiness.INVALID,
                    f"manifest lists missing file: {name}",
                )
            actual = _sha256_file(path)
        if actual != expected:
            return EmbeddingArtifactStatus(
                resolved,
                EmbeddingReadiness.INVALID,
                f"digest mismatch for {name}",
            )

    return EmbeddingArtifactStatus(resolved, EmbeddingReadiness.READY, "ok", manifest)


def require_embedding_artifacts(
    model_dir: Path,
    *,
    expected_model_id: str = QWEN3_EMBEDDING_MODEL_ID,
    expected_revision: str = QWEN3_EMBEDDING_PINNED_REVISION,
    expected_dimension: int = DEFAULT_EXPECTED_DIMENSION,
) -> Path:
    status = validate_embedding_artifacts(
        model_dir,
        expected_model_id=expected_model_id,
        expected_revision=expected_revision,
        expected_dimension=expected_dimension,
    )
    if status.readiness == EmbeddingReadiness.READY:
        return status.path
    raise EmbeddingArtifactsUnavailableError(
        artifacts_path=status.path,
        reason=status.reason,
        action="Run: offline-rag provision embedding",
    )


def provision_embedding_model(
    destination: Path,
    *,
    model_id: str = QWEN3_EMBEDDING_MODEL_ID,
    revision: str = QWEN3_EMBEDDING_PINNED_REVISION,
    expected_dimension: int = DEFAULT_EXPECTED_DIMENSION,
    force: bool = False,
) -> EmbeddingProvisionReport:
    """Download a pinned HF snapshot into ``destination`` via staging publish."""
    dest = Path(destination).expanduser().resolve()
    if not force:
        status = validate_embedding_artifacts(
            dest,
            expected_model_id=model_id,
            expected_revision=revision,
            expected_dimension=expected_dimension,
        )
        if status.readiness == EmbeddingReadiness.READY and status.manifest is not None:
            return EmbeddingProvisionReport(
                status=ProvisioningStatus.ALREADY_PROVISIONED,
                model_id=model_id,
                requested_revision=revision,
                resolved_revision=status.manifest.resolved_revision,
                destination=str(dest),
                artifact_id=status.manifest.artifact_id,
                manifest_path=str(embedding_manifest_path(dest)),
                files_downloaded=0,
                metadata={"readiness": EmbeddingReadiness.READY.value},
            )

    staging = dest.parent / f".staging-{dest.name}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=model_id,
            revision=revision,
            local_dir=str(staging),
        )
        digests = _collect_file_digests(staging, required=list(REQUIRED_EMBEDDING_FILES))
        artifact_id = _artifact_id_from_digests(
            model_id=model_id,
            revision=revision,
            digests=digests,
        )
        now = datetime.now(tz=UTC)
        manifest = EmbeddingModelManifest(
            model_id=model_id,
            requested_revision=revision,
            resolved_revision=revision,
            expected_dimension=expected_dimension,
            artifact_contract=QWEN3_EMBEDDING_ARTIFACT_CONTRACT,
            provisioned_at=now,
            required_files=list(REQUIRED_EMBEDDING_FILES),
            file_digests=digests,
            artifact_id=artifact_id,
            metadata={"source": "huggingface_hub.snapshot_download"},
        )
        atomic_write_text(embedding_manifest_path(staging), manifest.model_dump_json())

        # Validate staged tree before publish.
        staged_status = validate_embedding_artifacts(
            staging,
            expected_model_id=model_id,
            expected_revision=revision,
            expected_dimension=expected_dimension,
        )
        if staged_status.readiness != EmbeddingReadiness.READY:
            raise RuntimeError(f"staged embedding artifact invalid: {staged_status.reason}")

        if dest.exists():
            shutil.rmtree(dest)
        staging.rename(dest)

        return EmbeddingProvisionReport(
            status=ProvisioningStatus.READY,
            model_id=model_id,
            requested_revision=revision,
            resolved_revision=revision,
            destination=str(dest),
            artifact_id=artifact_id,
            manifest_path=str(embedding_manifest_path(dest)),
            files_downloaded=len(digests),
            metadata={"readiness": EmbeddingReadiness.READY.value},
        )
    except Exception as exc:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        return EmbeddingProvisionReport(
            status=ProvisioningStatus.FAILED,
            model_id=model_id,
            requested_revision=revision,
            resolved_revision=None,
            destination=str(dest),
            errors=[str(exc)],
            metadata={"readiness": EmbeddingReadiness.INVALID.value},
        )


def resolve_embedding_model_dir(
    *,
    embedding_artifacts_root: Path,
    model_path: Path | None = None,
) -> Path:
    if model_path is not None:
        return Path(model_path).expanduser().resolve()
    return default_embedding_model_dir(embedding_artifacts_root)


def readiness_metadata(status: EmbeddingArtifactStatus) -> dict[str, Any]:
    return {
        "path": str(status.path),
        "readiness": status.readiness.value,
        "reason": status.reason,
        "artifact_id": status.manifest.artifact_id if status.manifest else None,
    }
