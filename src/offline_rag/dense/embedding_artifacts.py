"""Read-only dual-backend embedding artifact inspection (P1).

Implements the Round-11 trust model:
- package-owned qualification specification (authority)
- installed representation manifest (installation state)
- installed bundle pointer (local authoritative instance selection)

Never downloads, exports, quantizes, repairs, or mutates artifacts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources
from pathlib import Path
from typing import Any

from offline_rag.core.ids import (
    QWEN3_EMBEDDING_MODEL_ID,
    QWEN3_EMBEDDING_PINNED_REVISION,
)
from offline_rag.dense.execution_profile import EmbeddingRepresentationId
from offline_rag.dense.provision import (
    EMBEDDING_MANIFEST_NAME,
    EmbeddingReadiness,
    validate_embedding_artifacts,
)

BUNDLE_MANIFEST_NAME = "offline-rag-embedding-bundle.json"
REPRESENTATION_MANIFEST_NAME = "offline-rag-embedding-representation.json"
REPRESENTATIONS_DIR_NAME = "representations"
QUALIFICATION_SCHEMA = "seneca-qualified-embedding-representation-v1"
INSTALLED_REPRESENTATION_SCHEMA = "seneca-installed-embedding-representation-v1"
BUNDLE_SCHEMA = "seneca-embedding-bundle-v1"

RepresentationReadiness = EmbeddingReadiness  # READY / ABSENT / INVALID


class RepresentationReasonCode(StrEnum):
    OK = "ok"
    ROOT_ABSENT = "root_absent"
    LEGACY_TORCH_READY = "legacy_torch_ready"
    LEGACY_ONNX_ABSENT = "legacy_onnx_absent"
    BUNDLE_ABSENT = "bundle_absent"
    BUNDLE_INVALID = "bundle_invalid"
    POINTER_ABSENT = "pointer_absent"
    INSTANCE_ABSENT = "instance_absent"
    INSTALLED_MANIFEST_INVALID = "installed_manifest_invalid"
    QUALIFICATION_MISMATCH = "qualification_mismatch"
    REQUIRED_FILE_MISSING = "required_file_missing"
    DIGEST_MISMATCH = "digest_mismatch"
    INSTALLED_DIGEST_DISAGREES = "installed_digest_disagrees"
    RUNTIME_CONTRACT_MISMATCH = "runtime_contract_mismatch"
    ORPHAN_IGNORED = "orphan_ignored"


@dataclass(frozen=True)
class QualifiedEmbeddingRepresentationSpec:
    qualification_schema: str
    representation_id: EmbeddingRepresentationId
    model_id: str
    model_revision: str
    expected_dimension: int
    runtime_family: str
    source_kind: str
    source_repo_id: str
    source_revision: str
    required_files: tuple[str, ...]
    expected_file_digests: dict[str, str]
    runtime_contract: dict[str, Any]
    qualification_evidence: dict[str, Any]
    historical_qualification_tree_sha256: str | None = None

    @classmethod
    def from_mapping(cls, data: MappingLike) -> QualifiedEmbeddingRepresentationSpec:
        payload = dict(data)
        rep_id = str(payload["representation_id"])
        if rep_id not in {"torch_st_v1", "onnx_fp32_v1"}:
            raise ValueError(f"unsupported representation_id: {rep_id}")
        digests = {
            str(k): str(v) for k, v in dict(payload["expected_file_digests"]).items()
        }
        required = tuple(str(x) for x in payload["required_files"])
        return cls(
            qualification_schema=str(payload["qualification_schema"]),
            representation_id=rep_id,  # type: ignore[arg-type]
            model_id=str(payload["model_id"]),
            model_revision=str(payload["model_revision"]),
            expected_dimension=int(payload["expected_dimension"]),
            runtime_family=str(payload["runtime_family"]),
            source_kind=str(payload["source_kind"]),
            source_repo_id=str(payload["source_repo_id"]),
            source_revision=str(payload["source_revision"]),
            required_files=required,
            expected_file_digests=digests,
            runtime_contract=dict(payload.get("runtime_contract") or {}),
            qualification_evidence=dict(payload.get("qualification_evidence") or {}),
            historical_qualification_tree_sha256=(
                str(payload["historical_qualification_tree_sha256"])
                if payload.get("historical_qualification_tree_sha256")
                else None
            ),
        )


MappingLike = dict[str, Any]


@dataclass(frozen=True)
class RepresentationInspection:
    representation_id: EmbeddingRepresentationId
    readiness: RepresentationReadiness
    reason_code: RepresentationReasonCode
    reason: str
    root: Path
    instance_path: Path | None = None
    graph_file_name: str | None = None
    qualification_spec: QualifiedEmbeddingRepresentationSpec | None = None
    installed_manifest: dict[str, Any] | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def load_package_qualification_spec(
    representation_id: EmbeddingRepresentationId,
) -> QualifiedEmbeddingRepresentationSpec:
    """Load package-owned qualification authority (not an installed manifest)."""
    if representation_id != "onnx_fp32_v1":
        raise ValueError(
            f"no package-owned qualification spec for {representation_id!r}"
        )
    package = resources.files("offline_rag.resources.embedding_representations")
    raw = package.joinpath("onnx_fp32_v1.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    spec = QualifiedEmbeddingRepresentationSpec.from_mapping(payload)
    if spec.qualification_schema != QUALIFICATION_SCHEMA:
        raise ValueError(
            f"unsupported qualification_schema: {spec.qualification_schema}"
        )
    if spec.representation_id != representation_id:
        raise ValueError("qualification resource representation_id mismatch")
    return spec


def bundle_manifest_path(model_root: Path) -> Path:
    return Path(model_root) / BUNDLE_MANIFEST_NAME


def parse_bundle_manifest(payload: MappingLike) -> dict[str, str]:
    """Return representation_id -> relative install-instance path pointers."""
    schema = str(payload.get("bundle_schema") or payload.get("schema") or "")
    if schema and schema != BUNDLE_SCHEMA:
        raise ValueError(f"unsupported bundle schema: {schema}")
    pointers_raw = payload.get("representations")
    if not isinstance(pointers_raw, dict):
        raise TypeError("bundle manifest missing representations object")
    out: dict[str, str] = {}
    for key, value in pointers_raw.items():
        if isinstance(value, str):
            out[str(key)] = value
        elif isinstance(value, dict) and "path" in value:
            out[str(key)] = str(value["path"])
        else:
            raise ValueError(f"invalid bundle pointer for {key!r}")
    return out


def parse_installed_representation_manifest(payload: MappingLike) -> dict[str, Any]:
    schema = str(
        payload.get("installed_representation_schema")
        or payload.get("schema")
        or INSTALLED_REPRESENTATION_SCHEMA
    )
    if schema != INSTALLED_REPRESENTATION_SCHEMA:
        raise ValueError(f"unsupported installed representation schema: {schema}")
    required = (
        "representation_id",
        "model_id",
        "model_revision",
        "runtime_family",
        "file_digests",
    )
    for key in required:
        if key not in payload:
            raise ValueError(f"installed representation manifest missing {key}")
    return dict(payload)


def _invalid(
    *,
    representation_id: EmbeddingRepresentationId,
    root: Path,
    reason_code: RepresentationReasonCode,
    reason: str,
    instance_path: Path | None = None,
    qualification_spec: QualifiedEmbeddingRepresentationSpec | None = None,
    installed_manifest: dict[str, Any] | None = None,
) -> RepresentationInspection:
    return RepresentationInspection(
        representation_id=representation_id,
        readiness=RepresentationReadiness.INVALID,
        reason_code=reason_code,
        reason=reason,
        root=root,
        instance_path=instance_path,
        qualification_spec=qualification_spec,
        installed_manifest=installed_manifest,
    )


def _absent(
    *,
    representation_id: EmbeddingRepresentationId,
    root: Path,
    reason_code: RepresentationReasonCode,
    reason: str,
) -> RepresentationInspection:
    return RepresentationInspection(
        representation_id=representation_id,
        readiness=RepresentationReadiness.ABSENT,
        reason_code=reason_code,
        reason=reason,
        root=root,
    )


def _validate_onnx_instance_against_qualification(
    *,
    instance_path: Path,
    root: Path,
    installed_manifest: dict[str, Any] | None,
) -> RepresentationInspection:
    spec = load_package_qualification_spec("onnx_fp32_v1")
    if installed_manifest is not None:
        if str(installed_manifest.get("representation_id")) != "onnx_fp32_v1":
            return _invalid(
                representation_id="onnx_fp32_v1",
                root=root,
                reason_code=RepresentationReasonCode.QUALIFICATION_MISMATCH,
                reason="installed representation_id mismatch",
                instance_path=instance_path,
                qualification_spec=spec,
                installed_manifest=installed_manifest,
            )
        if str(installed_manifest.get("model_id")) != spec.model_id:
            return _invalid(
                representation_id="onnx_fp32_v1",
                root=root,
                reason_code=RepresentationReasonCode.QUALIFICATION_MISMATCH,
                reason="installed model_id mismatch vs qualification",
                instance_path=instance_path,
                qualification_spec=spec,
                installed_manifest=installed_manifest,
            )
        if str(installed_manifest.get("model_revision")) != spec.model_revision:
            return _invalid(
                representation_id="onnx_fp32_v1",
                root=root,
                reason_code=RepresentationReasonCode.QUALIFICATION_MISMATCH,
                reason="installed model_revision mismatch vs qualification",
                instance_path=instance_path,
                qualification_spec=spec,
                installed_manifest=installed_manifest,
            )
        if str(installed_manifest.get("runtime_family")) != spec.runtime_family:
            return _invalid(
                representation_id="onnx_fp32_v1",
                root=root,
                reason_code=RepresentationReasonCode.QUALIFICATION_MISMATCH,
                reason="installed runtime_family mismatch vs qualification",
                instance_path=instance_path,
                qualification_spec=spec,
                installed_manifest=installed_manifest,
            )

    installed_digests = (
        {
            str(k): str(v)
            for k, v in dict(installed_manifest.get("file_digests") or {}).items()
        }
        if installed_manifest is not None
        else {}
    )

    for rel in spec.required_files:
        path = instance_path / rel
        if not path.is_file():
            return _invalid(
                representation_id="onnx_fp32_v1",
                root=root,
                reason_code=RepresentationReasonCode.REQUIRED_FILE_MISSING,
                reason=f"required loader file missing: {rel}",
                instance_path=instance_path,
                qualification_spec=spec,
                installed_manifest=installed_manifest,
            )
        actual = sha256_file(path)
        expected = spec.expected_file_digests.get(rel)
        if expected is None or actual != expected:
            return _invalid(
                representation_id="onnx_fp32_v1",
                root=root,
                reason_code=RepresentationReasonCode.DIGEST_MISMATCH,
                reason=f"digest mismatch vs package qualification for {rel}",
                instance_path=instance_path,
                qualification_spec=spec,
                installed_manifest=installed_manifest,
            )
        if rel in installed_digests and installed_digests[rel] != expected:
            return _invalid(
                representation_id="onnx_fp32_v1",
                root=root,
                reason_code=RepresentationReasonCode.INSTALLED_DIGEST_DISAGREES,
                reason=(
                    f"installed manifest digest disagrees with package "
                    f"qualification for {rel}"
                ),
                instance_path=instance_path,
                qualification_spec=spec,
                installed_manifest=installed_manifest,
            )
        if rel in installed_digests and installed_digests[rel] != actual:
            return _invalid(
                representation_id="onnx_fp32_v1",
                root=root,
                reason_code=RepresentationReasonCode.INSTALLED_DIGEST_DISAGREES,
                reason=f"installed manifest digest disagrees with local bytes for {rel}",
                instance_path=instance_path,
                qualification_spec=spec,
                installed_manifest=installed_manifest,
            )

    # Installed manifest cannot self-authorize extra unknown bytes as trusted.
    if installed_manifest is not None:
        for rel, digest in installed_digests.items():
            if rel not in spec.expected_file_digests:
                return _invalid(
                    representation_id="onnx_fp32_v1",
                    root=root,
                    reason_code=RepresentationReasonCode.INSTALLED_DIGEST_DISAGREES,
                    reason=(
                        "installed manifest lists file not present in package "
                        f"qualification authority: {rel}"
                    ),
                    instance_path=instance_path,
                    qualification_spec=spec,
                    installed_manifest=installed_manifest,
                )
            if digest != spec.expected_file_digests[rel]:
                return _invalid(
                    representation_id="onnx_fp32_v1",
                    root=root,
                    reason_code=RepresentationReasonCode.INSTALLED_DIGEST_DISAGREES,
                    reason=f"installed manifest cannot self-authorize {rel}",
                    instance_path=instance_path,
                    qualification_spec=spec,
                    installed_manifest=installed_manifest,
                )

    contract = spec.runtime_contract
    graph_name = str(contract.get("graph_file_name") or "onnx/model.onnx")
    if contract.get("provider") != "CPUExecutionProvider":
        return _invalid(
            representation_id="onnx_fp32_v1",
            root=root,
            reason_code=RepresentationReasonCode.RUNTIME_CONTRACT_MISMATCH,
            reason="qualification runtime provider mismatch",
            instance_path=instance_path,
            qualification_spec=spec,
            installed_manifest=installed_manifest,
        )

    return RepresentationInspection(
        representation_id="onnx_fp32_v1",
        readiness=RepresentationReadiness.READY,
        reason_code=RepresentationReasonCode.OK,
        reason="ok",
        root=root,
        instance_path=instance_path,
        graph_file_name=graph_name,
        qualification_spec=spec,
        installed_manifest=installed_manifest,
    )


def inspect_representation(
    model_root: Path,
    representation_id: EmbeddingRepresentationId,
    *,
    expected_model_id: str = QWEN3_EMBEDDING_MODEL_ID,
    expected_revision: str = QWEN3_EMBEDDING_PINNED_REVISION,
    expected_dimension: int = 1024,
) -> RepresentationInspection:
    """Read-only readiness for one representation under a model root."""
    root = Path(model_root).expanduser().resolve()
    if not root.exists():
        return _absent(
            representation_id=representation_id,
            root=root,
            reason_code=RepresentationReasonCode.ROOT_ABSENT,
            reason="model root missing",
        )

    bundle_path = bundle_manifest_path(root)
    if bundle_path.is_file():
        try:
            bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
            pointers = parse_bundle_manifest(bundle_payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return _invalid(
                representation_id=representation_id,
                root=root,
                reason_code=RepresentationReasonCode.BUNDLE_INVALID,
                reason=f"malformed bundle manifest: {exc}",
            )
        rel = pointers.get(representation_id)
        if not rel:
            if representation_id == "torch_st_v1":
                # Fall through to legacy torch check when bundle omits torch pointer.
                pass
            else:
                return _absent(
                    representation_id=representation_id,
                    root=root,
                    reason_code=RepresentationReasonCode.POINTER_ABSENT,
                    reason=f"bundle has no pointer for {representation_id}",
                )
        if rel:
            pointer = Path(rel)
            # Reject absolute / parent-escaping pointer strings (lexical).
            if pointer.is_absolute() or ".." in pointer.parts:
                return _invalid(
                    representation_id=representation_id,
                    root=root,
                    reason_code=RepresentationReasonCode.BUNDLE_INVALID,
                    reason="bundle pointer escapes model root",
                    instance_path=root / rel,
                )
            instance_dir = root / pointer
            if not instance_dir.is_dir():
                return _absent(
                    representation_id=representation_id,
                    root=root,
                    reason_code=RepresentationReasonCode.INSTANCE_ABSENT,
                    reason=f"bundle instance missing: {rel}",
                )
            # Resolve for IO; file-level symlinks inside the instance may point at
            # shared accepted artifact bytes outside the model root.
            instance_path = instance_dir.resolve()
            manifest_file = instance_path / REPRESENTATION_MANIFEST_NAME
            installed: dict[str, Any] | None = None
            if manifest_file.is_file():
                try:
                    installed = parse_installed_representation_manifest(
                        json.loads(manifest_file.read_text(encoding="utf-8"))
                    )
                except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    return _invalid(
                        representation_id=representation_id,
                        root=root,
                        reason_code=RepresentationReasonCode.INSTALLED_MANIFEST_INVALID,
                        reason=f"malformed installed representation manifest: {exc}",
                        instance_path=instance_path,
                    )
            if representation_id == "onnx_fp32_v1":
                return _validate_onnx_instance_against_qualification(
                    instance_path=instance_path,
                    root=root,
                    installed_manifest=installed,
                )
            # torch via bundle instance: require legacy-equivalent identity files
            status = validate_embedding_artifacts(
                instance_path,
                expected_model_id=expected_model_id,
                expected_revision=expected_revision,
                expected_dimension=expected_dimension,
            )
            if status.readiness == RepresentationReadiness.READY:
                return RepresentationInspection(
                    representation_id="torch_st_v1",
                    readiness=RepresentationReadiness.READY,
                    reason_code=RepresentationReasonCode.OK,
                    reason="ok",
                    root=root,
                    instance_path=instance_path,
                    installed_manifest=installed,
                )
            return RepresentationInspection(
                representation_id="torch_st_v1",
                readiness=status.readiness,
                reason_code=(
                    RepresentationReasonCode.INSTANCE_ABSENT
                    if status.readiness == RepresentationReadiness.ABSENT
                    else RepresentationReasonCode.INSTALLED_MANIFEST_INVALID
                ),
                reason=status.reason,
                root=root,
                instance_path=instance_path,
                installed_manifest=installed,
            )

    # No usable bundle pointer for this representation — legacy layout.
    if representation_id == "torch_st_v1":
        status = validate_embedding_artifacts(
            root,
            expected_model_id=expected_model_id,
            expected_revision=expected_revision,
            expected_dimension=expected_dimension,
        )
        if status.readiness == RepresentationReadiness.READY:
            return RepresentationInspection(
                representation_id="torch_st_v1",
                readiness=RepresentationReadiness.READY,
                reason_code=RepresentationReasonCode.LEGACY_TORCH_READY,
                reason="legacy torch root ready",
                root=root,
                instance_path=root,
            )
        if status.readiness == RepresentationReadiness.ABSENT:
            return _absent(
                representation_id="torch_st_v1",
                root=root,
                reason_code=RepresentationReasonCode.ROOT_ABSENT,
                reason=status.reason,
            )
        return _invalid(
            representation_id="torch_st_v1",
            root=root,
            reason_code=RepresentationReasonCode.INSTALLED_MANIFEST_INVALID,
            reason=status.reason,
        )

    # onnx without bundle pointer
    if (root / EMBEDDING_MANIFEST_NAME).is_file():
        return _absent(
            representation_id="onnx_fp32_v1",
            root=root,
            reason_code=RepresentationReasonCode.LEGACY_ONNX_ABSENT,
            reason="legacy torch root present; onnx_fp32_v1 absent",
        )
    return _absent(
        representation_id="onnx_fp32_v1",
        root=root,
        reason_code=RepresentationReasonCode.BUNDLE_ABSENT,
        reason="onnx_fp32_v1 requires Round-11 bundle pointer",
    )


def inspect_selected_representation(
    model_root: Path,
    representation_id: EmbeddingRepresentationId,
    **kwargs: Any,
) -> RepresentationInspection:
    """Alias used by runtime construction."""
    return inspect_representation(model_root, representation_id, **kwargs)


__all__ = [
    "BUNDLE_MANIFEST_NAME",
    "BUNDLE_SCHEMA",
    "INSTALLED_REPRESENTATION_SCHEMA",
    "QUALIFICATION_SCHEMA",
    "REPRESENTATIONS_DIR_NAME",
    "REPRESENTATION_MANIFEST_NAME",
    "QualifiedEmbeddingRepresentationSpec",
    "RepresentationInspection",
    "RepresentationReadiness",
    "RepresentationReasonCode",
    "bundle_manifest_path",
    "inspect_representation",
    "inspect_selected_representation",
    "load_package_qualification_spec",
    "parse_bundle_manifest",
    "parse_installed_representation_manifest",
    "sha256_file",
]
