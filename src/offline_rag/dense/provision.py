"""Local embedding model provisioning and readiness checks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
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
)

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
    return (
        Path(embedding_artifacts_root).expanduser().resolve()
        / DEFAULT_EMBEDDING_DIR_NAME
    )


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
            f"missing model weights (expected one of: {', '.join(_WEIGHT_CANDIDATES)})"
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
        return EmbeddingArtifactStatus(
            resolved, EmbeddingReadiness.ABSENT, "directory missing"
        )
    if not resolved.is_dir():
        return EmbeddingArtifactStatus(
            resolved, EmbeddingReadiness.INVALID, "path is not a directory"
        )

    manifest_file = embedding_manifest_path(resolved)
    if not manifest_file.exists():
        if not any(resolved.iterdir()):
            return EmbeddingArtifactStatus(
                resolved, EmbeddingReadiness.ABSENT, "directory is empty"
            )
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
    if (
        manifest.requested_revision != expected_revision
        and manifest.resolved_revision != expected_revision
    ):
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
        digests = _collect_file_digests(
            resolved, required=list(REQUIRED_EMBEDDING_FILES)
        )
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
    representation: str | list[str] | None = None,
    onnx_source: Path | str | None = None,
) -> EmbeddingProvisionReport:
    """Provision embedding representations via the P3 bundle-aware writer.

    Omitted ``representation`` defaults to ``torch_st_v1`` (backward compatible).
    All CLI / script routes must converge here — no whole-root destructive
    replacement of a bundle-managed model root.
    """
    from offline_rag.dense.embedding_bundle_provision import (
        provision_embedding_model as _bundle_provision,
    )

    return _bundle_provision(
        destination,
        model_id=model_id,
        revision=revision,
        expected_dimension=expected_dimension,
        force=force,
        representation=representation,
        onnx_source=onnx_source,
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
