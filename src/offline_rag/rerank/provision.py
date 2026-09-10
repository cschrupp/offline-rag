"""Local reranker model provisioning and readiness checks."""

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
    BGE_RERANKER_ARTIFACT_CONTRACT,
    BGE_RERANKER_MODEL_ID,
    BGE_RERANKER_PINNED_REVISION,
    SENTENCE_TRANSFORMERS_CROSS_ENCODER_ADAPTER,
    artifact_bytes_hash,
)
from offline_rag.domain.indexing import (
    ProvisioningStatus,
    RerankerModelManifest,
    RerankerProvisionReport,
)
from offline_rag.ingestion.io import atomic_write_text

RERANKER_MANIFEST_NAME = "offline-rag-reranker.json"
DEFAULT_RERANKER_DIR_NAME = "bge-reranker-v2-m3"

REQUIRED_RERANKER_FILES: tuple[str, ...] = (
    "config.json",
    "tokenizer_config.json",
)

_TOKENIZER_CANDIDATES: tuple[str, ...] = (
    "tokenizer.json",
    "sentencepiece.bpe.model",
)

_WEIGHT_CANDIDATES: tuple[str, ...] = (
    "model.safetensors",
    "pytorch_model.bin",
    "model.safetensors.index.json",
)


class RerankerReadiness(StrEnum):
    ABSENT = "absent"
    INVALID = "invalid"
    READY = "ready"


class RerankerArtifactsUnavailableError(RuntimeError):
    """Raised when runtime reranking cannot proceed without local artifacts."""

    def __init__(self, *, artifacts_path: Path, reason: str, action: str) -> None:
        self.artifacts_path = artifacts_path
        self.reason = reason
        self.action = action
        super().__init__(
            "Reranker artifacts unavailable for offline hybrid-rerank.\n"
            f"Resolved path: {artifacts_path}\n"
            f"Reason: {reason}\n"
            "Runtime downloading is intentionally disabled.\n"
            f"Action: {action}"
        )


@dataclass(frozen=True)
class RerankerArtifactStatus:
    path: Path
    readiness: RerankerReadiness
    reason: str
    manifest: RerankerModelManifest | None = None


def default_reranker_model_dir(reranker_artifacts_root: Path) -> Path:
    return Path(reranker_artifacts_root).expanduser().resolve() / DEFAULT_RERANKER_DIR_NAME


def reranker_manifest_path(model_dir: Path) -> Path:
    return Path(model_dir) / RERANKER_MANIFEST_NAME


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


def _find_tokenizer_file(model_dir: Path) -> Path | None:
    for name in _TOKENIZER_CANDIDATES:
        candidate = model_dir / name
        if candidate.is_file():
            return candidate
    return None


def _collect_file_digests(model_dir: Path, *, required: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for name in required:
        path = model_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"missing required reranker file: {name}")
        digests[name] = _sha256_file(path)

    tokenizer = _find_tokenizer_file(model_dir)
    if tokenizer is None:
        raise FileNotFoundError(
            "missing tokenizer artifacts "
            f"(expected one of: {', '.join(_TOKENIZER_CANDIDATES)})"
        )
    digests[tokenizer.name] = _sha256_file(tokenizer)

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


def validate_reranker_artifacts(
    model_dir: Path,
    *,
    expected_model_id: str = BGE_RERANKER_MODEL_ID,
    expected_revision: str = BGE_RERANKER_PINNED_REVISION,
    expected_adapter_contract: str = SENTENCE_TRANSFORMERS_CROSS_ENCODER_ADAPTER,
) -> RerankerArtifactStatus:
    """Return ABSENT / INVALID / READY for a local reranker model directory.

    Performs filesystem and manifest checks only — no network, no model load.
    """
    resolved = Path(model_dir).expanduser().resolve()
    if not resolved.exists():
        return RerankerArtifactStatus(resolved, RerankerReadiness.ABSENT, "directory missing")
    if not resolved.is_dir():
        return RerankerArtifactStatus(resolved, RerankerReadiness.INVALID, "path is not a directory")

    manifest_file = reranker_manifest_path(resolved)
    if not manifest_file.exists():
        if not any(resolved.iterdir()):
            return RerankerArtifactStatus(resolved, RerankerReadiness.ABSENT, "directory is empty")
        return RerankerArtifactStatus(
            resolved,
            RerankerReadiness.INVALID,
            f"missing {RERANKER_MANIFEST_NAME} provisioning manifest",
        )

    try:
        manifest = RerankerModelManifest.model_validate_json(
            manifest_file.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError, ValidationError) as exc:
        return RerankerArtifactStatus(
            resolved,
            RerankerReadiness.INVALID,
            f"malformed provisioning manifest: {exc}",
        )

    if manifest.model_id != expected_model_id:
        return RerankerArtifactStatus(
            resolved,
            RerankerReadiness.INVALID,
            f"manifest model_id mismatch: {manifest.model_id}",
        )
    if (
        manifest.requested_revision != expected_revision
        and manifest.resolved_revision != expected_revision
    ):
        return RerankerArtifactStatus(
            resolved,
            RerankerReadiness.INVALID,
            f"manifest revision mismatch: {manifest.resolved_revision}",
        )
    if manifest.artifact_contract != BGE_RERANKER_ARTIFACT_CONTRACT:
        return RerankerArtifactStatus(
            resolved,
            RerankerReadiness.INVALID,
            f"unsupported artifact_contract: {manifest.artifact_contract}",
        )
    if manifest.adapter_contract != expected_adapter_contract:
        return RerankerArtifactStatus(
            resolved,
            RerankerReadiness.INVALID,
            f"adapter_contract mismatch: {manifest.adapter_contract}",
        )

    try:
        digests = _collect_file_digests(resolved, required=list(REQUIRED_RERANKER_FILES))
    except FileNotFoundError as exc:
        return RerankerArtifactStatus(resolved, RerankerReadiness.INVALID, str(exc))

    for name, expected in manifest.file_digests.items():
        actual = digests.get(name)
        if actual is None:
            path = resolved / name
            if not path.is_file():
                return RerankerArtifactStatus(
                    resolved,
                    RerankerReadiness.INVALID,
                    f"manifest lists missing file: {name}",
                )
            actual = _sha256_file(path)
        if actual != expected:
            return RerankerArtifactStatus(
                resolved,
                RerankerReadiness.INVALID,
                f"digest mismatch for {name}",
            )

    return RerankerArtifactStatus(resolved, RerankerReadiness.READY, "ok", manifest)


def require_reranker_artifacts(
    model_dir: Path,
    *,
    expected_model_id: str = BGE_RERANKER_MODEL_ID,
    expected_revision: str = BGE_RERANKER_PINNED_REVISION,
    expected_adapter_contract: str = SENTENCE_TRANSFORMERS_CROSS_ENCODER_ADAPTER,
) -> Path:
    status = validate_reranker_artifacts(
        model_dir,
        expected_model_id=expected_model_id,
        expected_revision=expected_revision,
        expected_adapter_contract=expected_adapter_contract,
    )
    if status.readiness == RerankerReadiness.READY:
        return status.path
    raise RerankerArtifactsUnavailableError(
        artifacts_path=status.path,
        reason=status.reason,
        action="Run: offline-rag provision reranker",
    )


def provision_reranker_model(
    destination: Path,
    *,
    model_id: str = BGE_RERANKER_MODEL_ID,
    revision: str = BGE_RERANKER_PINNED_REVISION,
    adapter_contract: str = SENTENCE_TRANSFORMERS_CROSS_ENCODER_ADAPTER,
    force: bool = False,
) -> RerankerProvisionReport:
    """Download a pinned HF snapshot into ``destination`` via staging publish."""
    dest = Path(destination).expanduser().resolve()
    if not force:
        status = validate_reranker_artifacts(
            dest,
            expected_model_id=model_id,
            expected_revision=revision,
            expected_adapter_contract=adapter_contract,
        )
        if status.readiness == RerankerReadiness.READY and status.manifest is not None:
            return RerankerProvisionReport(
                status=ProvisioningStatus.ALREADY_PROVISIONED,
                model_id=model_id,
                requested_revision=revision,
                resolved_revision=status.manifest.resolved_revision,
                destination=str(dest),
                artifact_id=status.manifest.artifact_id,
                manifest_path=str(reranker_manifest_path(dest)),
                files_downloaded=0,
                metadata={"readiness": RerankerReadiness.READY.value},
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
        digests = _collect_file_digests(staging, required=list(REQUIRED_RERANKER_FILES))
        artifact_id = _artifact_id_from_digests(
            model_id=model_id,
            revision=revision,
            digests=digests,
        )
        now = datetime.now(tz=UTC)
        manifest = RerankerModelManifest(
            model_id=model_id,
            requested_revision=revision,
            resolved_revision=revision,
            artifact_contract=BGE_RERANKER_ARTIFACT_CONTRACT,
            adapter_contract=adapter_contract,
            provisioned_at=now,
            required_files=list(REQUIRED_RERANKER_FILES),
            file_digests=digests,
            artifact_id=artifact_id,
            metadata={"source": "huggingface_hub.snapshot_download"},
        )
        atomic_write_text(reranker_manifest_path(staging), manifest.model_dump_json())

        staged_status = validate_reranker_artifacts(
            staging,
            expected_model_id=model_id,
            expected_revision=revision,
            expected_adapter_contract=adapter_contract,
        )
        if staged_status.readiness != RerankerReadiness.READY:
            raise RuntimeError(f"staged reranker artifact invalid: {staged_status.reason}")

        if dest.exists():
            shutil.rmtree(dest)
        staging.rename(dest)

        return RerankerProvisionReport(
            status=ProvisioningStatus.READY,
            model_id=model_id,
            requested_revision=revision,
            resolved_revision=revision,
            destination=str(dest),
            artifact_id=artifact_id,
            manifest_path=str(reranker_manifest_path(dest)),
            files_downloaded=len(digests),
            metadata={"readiness": RerankerReadiness.READY.value},
        )
    except Exception as exc:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        return RerankerProvisionReport(
            status=ProvisioningStatus.FAILED,
            model_id=model_id,
            requested_revision=revision,
            resolved_revision=None,
            destination=str(dest),
            errors=[str(exc)],
            metadata={"readiness": RerankerReadiness.INVALID.value},
        )


def resolve_reranker_model_dir(
    *,
    reranker_artifacts_root: Path,
    model_path: Path | None = None,
) -> Path:
    if model_path is not None:
        return Path(model_path).expanduser().resolve()
    return default_reranker_model_dir(reranker_artifacts_root)


def readiness_metadata(status: RerankerArtifactStatus) -> dict[str, Any]:
    return {
        "path": str(status.path),
        "readiness": status.readiness.value,
        "reason": status.reason,
        "artifact_id": status.manifest.artifact_id if status.manifest else None,
    }
