"""P3 dual-backend embedding provisioning: durable transactional installer.

Authority: S16-K-D-DUAL-BACKEND-P3-PROVISIONING-ACQUISITION-IMPLEMENTATION-AUTH-001

Installs already-qualified ``torch_st_v1`` / ``onnx_fp32_v1`` representations via
one bundle-aware writer. Does not establish scientific validity, regenerate ONNX,
or mutate P1 qualification / P2 runtime semantics.

Crash / power-loss durability applies only under supported local filesystem
assumptions: same filesystem for staging and publication, POSIX-style atomic
rename/replace, working file fsync, and working directory fsync. Equivalent
power-loss behavior is not claimed for arbitrary network/cloud/FUSE filesystems.

Post-publication rollback cannot undo observations a reader may have made
between forward bundle publication and restoration. That limitation is bounded
by P2 process-start frozen availability.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from offline_rag.core.ids import (
    QWEN3_EMBEDDING_ARTIFACT_CONTRACT,
    QWEN3_EMBEDDING_MODEL_ID,
    QWEN3_EMBEDDING_PINNED_REVISION,
)
from offline_rag.dense.embedding_artifacts import (
    BUNDLE_MANIFEST_NAME,
    BUNDLE_SCHEMA,
    INSTALLED_REPRESENTATION_SCHEMA,
    REPRESENTATION_MANIFEST_NAME,
    REPRESENTATIONS_DIR_NAME,
    RepresentationReadiness,
    bundle_manifest_path,
    inspect_representation,
    load_package_qualification_spec,
    parse_bundle_manifest,
)
from offline_rag.dense.provision import (
    DEFAULT_EXPECTED_DIMENSION,
    EMBEDDING_MANIFEST_NAME,
    REQUIRED_EMBEDDING_FILES,
    EmbeddingReadiness,
    _artifact_id_from_digests,
    _collect_file_digests,
    embedding_manifest_path,
    validate_embedding_artifacts,
)
from offline_rag.domain.indexing import (
    EmbeddingModelManifest,
    EmbeddingProvisionReport,
    ProvisioningStatus,
)

P3_METADATA_SCHEMA = "seneca-p3-embedding-provision-v1"
RepresentationId = Literal["torch_st_v1", "onnx_fp32_v1"]
ALL_REPRESENTATIONS: tuple[RepresentationId, ...] = ("torch_st_v1", "onnx_fp32_v1")

OUTCOME_ALREADY_PROVISIONED = "already_provisioned"
OUTCOME_INSTALLED = "installed"
OUTCOME_REPLACED = "replaced"
OUTCOME_ADOPTED_LEGACY = "adopted_legacy"
OUTCOME_SOURCE_REQUIRED = "source_required"
OUTCOME_SOURCE_INVALID = "source_invalid"
OUTCOME_QUALIFICATION_MISMATCH = "qualification_mismatch"
OUTCOME_MALFORMED_BUNDLE = "malformed_bundle"
OUTCOME_LOCK_UNAVAILABLE = "lock_unavailable"
OUTCOME_WRITE_FAILED = "write_failed"
OUTCOME_PUBLISH_FAILED = "publish_failed"
OUTCOME_POST_PUBLISH_VALIDATION_FAILED = "post_publish_validation_failed"
OUTCOME_ROLLBACK_FAILED = "rollback_failed"


class BundleProvisionError(RuntimeError):
    """Bounded provisioning failure with stable outcome_code."""

    def __init__(self, outcome_code: str, message: str) -> None:
        self.outcome_code = outcome_code
        super().__init__(message)


@dataclass
class _RepPlan:
    representation_id: RepresentationId
    action: Literal["preserve", "install", "replace", "adopt_legacy"]
    readiness: str
    reason: str


@dataclass
class _PreviousBundleState:
    kind: Literal["absent", "present_valid"]
    bytes: bytes | None = None


class BundlePublicationState(StrEnum):
    """Selection-transition state for forward bundle publication (F001)."""

    NOT_REPLACED = "not_replaced"
    REPLACED_NOT_CONFIRMED_DURABLE = "replaced_not_confirmed_durable"
    REPLACED_DURABLE = "replaced_durable"


@dataclass
class _TxCounters:
    bundle_publications: int = 0
    onnx_files_copied: int = 0
    files_downloaded: int = 0
    torch_files_persisted: int = 0
    bundle_publication_state: BundlePublicationState = BundlePublicationState.NOT_REPLACED
    hooks: dict[str, Any] = field(default_factory=dict)

    @property
    def selection_may_be_live(self) -> bool:
        return self.bundle_publication_state is not BundlePublicationState.NOT_REPLACED


def normalize_representation_request(
    representation: str | Sequence[str] | None,
) -> list[RepresentationId]:
    if representation is None:
        return ["torch_st_v1"]
    if isinstance(representation, str):
        raw = representation.strip().lower()
        if raw == "all":
            return list(ALL_REPRESENTATIONS)
        if raw in ALL_REPRESENTATIONS:
            return [raw]  # type: ignore[list-item]
        raise ValueError(f"unsupported representation: {representation!r}")
    out: list[RepresentationId] = []
    for item in representation:
        normalized = normalize_representation_request(item)
        for rep in normalized:
            if rep not in out:
                out.append(rep)
    if not out:
        return ["torch_st_v1"]
    return out


def _reject_escaping_ancestry_symlinks(dest: Path) -> None:
    """Reject destination chains that redirect outside their parent via symlink."""
    prefixes: list[Path] = []
    cur = dest
    while True:
        prefixes.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    for prefix in reversed(prefixes):
        if not prefix.exists() or not prefix.is_symlink():
            continue
        parent_real = prefix.parent.resolve(strict=True)
        target_real = prefix.resolve(strict=True)
        try:
            target_real.relative_to(parent_real)
        except ValueError as exc:
            raise BundleProvisionError(
                OUTCOME_WRITE_FAILED,
                f"destination ancestry symlink escapes base: {prefix}",
            ) from exc


def _durable_mkdir_ancestry(path: Path) -> Path:
    """Create ``path`` and missing parents; fsync each containing directory (F003).

    Each newly created directory entry is persisted by syncing its parent.
    Rejects ancestry that resolves through a symlink escaping its parent.
    """
    dest = Path(path).expanduser()
    _reject_escaping_ancestry_symlinks(dest)
    if dest.exists():
        if not dest.is_dir():
            raise BundleProvisionError(
                OUTCOME_WRITE_FAILED, f"model root exists but is not a directory: {dest}"
            )
        return dest.resolve(strict=True)

    existing = dest
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.exists():
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED,
            f"cannot locate existing ancestor for model root: {dest}",
        )
    try:
        existing_real = existing.resolve(strict=True)
    except OSError as exc:
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED, f"cannot resolve existing ancestor: {existing}"
        ) from exc

    try:
        rel = dest.relative_to(existing)
    except ValueError as exc:
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED,
            f"model root is not under existing ancestor {existing}: {dest}",
        ) from exc
    if ".." in rel.parts:
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED, f"unsafe model-root relative ancestry: {rel}"
        )

    cursor = existing
    for part in rel.parts:
        nxt = cursor / part
        if nxt.exists():
            if nxt.is_symlink():
                resolved = nxt.resolve(strict=True)
                try:
                    resolved.relative_to(existing_real)
                except ValueError as exc:
                    raise BundleProvisionError(
                        OUTCOME_WRITE_FAILED,
                        f"destination ancestry symlink escapes base: {nxt}",
                    ) from exc
            cursor = nxt
            continue
        nxt.mkdir(exist_ok=True)
        _fsync_dir(cursor)  # persist the new directory entry in its parent
        cursor = nxt
    return dest.resolve(strict=True)


def _canonical_model_root(destination: Path) -> Path:
    return _durable_mkdir_ancestry(Path(destination).expanduser())


def _assert_physically_inside(root: Path, path: Path) -> Path:
    """Require ``path`` (existing or to-be-created parent) under canonical root."""
    root_real = root.resolve(strict=True)
    candidate = Path(path)
    # Resolve existing ancestors; reject symlink escape.
    probe = candidate if candidate.exists() else candidate.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    resolved_probe = probe.resolve(strict=True)
    try:
        resolved_probe.relative_to(root_real)
    except ValueError as exc:
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED,
            f"path escapes canonical model root: {path}",
        ) from exc
    # Lexical check on remaining relative suffix.
    try:
        rel = candidate.relative_to(root)
    except ValueError as exc:
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED,
            f"path not under model root: {path}",
        ) from exc
    if rel.is_absolute() or ".." in rel.parts:
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED,
            f"unsafe relative path under model root: {rel}",
        )
    return candidate


def _validate_relative_pointer(pointer: str) -> str:
    raw = str(pointer).strip()
    if not raw:
        raise BundleProvisionError(OUTCOME_WRITE_FAILED, "empty bundle pointer")
    if raw == ".":
        return raw
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED,
            f"invalid bundle pointer: {raw!r}",
        )
    return raw.replace("\\", "/")


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _durable_mkdir(path: Path, *, root: Path) -> None:
    _assert_physically_inside(root, path)
    parts: list[Path] = []
    cur = path
    while cur != root and not cur.exists():
        parts.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    for directory in reversed(parts):
        _assert_physically_inside(root, directory)
        directory.mkdir(exist_ok=True)
        _fsync_dir(directory.parent)


def _durable_write_bytes(path: Path, data: bytes, *, root: Path) -> None:
    _assert_physically_inside(root, path)
    _durable_mkdir(path.parent, root=root)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _fsync_file(path)
        _fsync_dir(path.parent)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _durable_write_text(path: Path, text: str, *, root: Path) -> None:
    _durable_write_bytes(path, text.encode("utf-8"), root=root)


def _same_filesystem(a: Path, b: Path) -> bool:
    return os.stat(a).st_dev == os.stat(b).st_dev


def _copy_regular_file(src: Path, dest: Path, *, root: Path) -> str:
    """Copy source object to independent regular file under root; return sha256."""
    _assert_physically_inside(root, dest)
    _durable_mkdir(dest.parent, root=root)
    if src.is_symlink():
        target = src.resolve(strict=True)
        if not target.is_file() or target.is_symlink():
            # After resolve, is_file on symlink-following path; reject non-files.
            raise BundleProvisionError(
                OUTCOME_SOURCE_INVALID,
                f"source symlink does not resolve to a regular file: {src}",
            )
        st = target.stat()
        if not stat.S_ISREG(st.st_mode):
            raise BundleProvisionError(
                OUTCOME_SOURCE_INVALID,
                f"source symlink target is not a regular file: {src}",
            )
        src_file = target
    else:
        if not src.is_file():
            raise BundleProvisionError(
                OUTCOME_SOURCE_INVALID,
                f"source path is not a readable file: {src}",
            )
        st = src.stat()
        if not stat.S_ISREG(st.st_mode):
            raise BundleProvisionError(
                OUTCOME_SOURCE_INVALID,
                f"source path is not a regular file: {src}",
            )
        src_file = src

    # Materialize as independent regular file (never preserve symlink).
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.",
        suffix=".tmp",
        dir=str(dest.parent),
    )
    tmp_path = Path(tmp_name)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as out_handle, src_file.open("rb") as in_handle:
            while True:
                chunk = in_handle.read(1024 * 1024)
                if not chunk:
                    break
                out_handle.write(chunk)
                digest.update(chunk)
            out_handle.flush()
            os.fsync(out_handle.fileno())
        os.replace(tmp_path, dest)
        _fsync_file(dest)
        _fsync_dir(dest.parent)
        if dest.is_symlink():
            raise BundleProvisionError(
                OUTCOME_WRITE_FAILED,
                f"installed target must be a regular file, got symlink: {dest}",
            )
        return digest.hexdigest()
    except BundleProvisionError:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED, f"failed copying {src}: {exc}"
        ) from exc


def _durable_publish_directory(staging: Path, final: Path, *, root: Path) -> None:
    _assert_physically_inside(root, staging)
    _assert_physically_inside(root, final)
    _durable_mkdir(final.parent, root=root)
    if not _same_filesystem(staging, root) or not _same_filesystem(final.parent, root):
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED,
            "staging/final must reside on the same filesystem as the model root",
        )
    if final.exists():
        raise BundleProvisionError(
            OUTCOME_PUBLISH_FAILED,
            f"immutable instance already exists: {final}",
        )
    os.rename(staging, final)
    _fsync_dir(final.parent)


def _durable_replace_file(
    tmp_path: Path,
    final_path: Path,
    *,
    root: Path,
    counters: _TxCounters | None = None,
    mark_bundle_selection: bool = False,
) -> None:
    """Atomic replace with optional selection-transition tracking (F001).

    Once ``os.replace`` succeeds, ``counters.bundle_publication_state`` advances
    to ``REPLACED_NOT_CONFIRMED_DURABLE`` before file/directory fsync. Any
    subsequent failure must be treated as a possible live forward publication.
    """
    hooks = counters.hooks if counters is not None else {}
    _assert_physically_inside(root, tmp_path)
    _assert_physically_inside(root, final_path)
    _fsync_file(tmp_path)
    os.replace(tmp_path, final_path)
    if mark_bundle_selection and counters is not None:
        counters.bundle_publication_state = (
            BundlePublicationState.REPLACED_NOT_CONFIRMED_DURABLE
        )
        counters.bundle_publications += 1
        fail_after_replace = hooks.get("fail_after_bundle_replace")
        if callable(fail_after_replace):
            fail_after_replace()
    _fsync_file(final_path)
    if mark_bundle_selection and counters is not None:
        fail_after_file = hooks.get("fail_after_bundle_file_fsync")
        if callable(fail_after_file):
            fail_after_file()
    _fsync_dir(final_path.parent)
    if mark_bundle_selection and counters is not None:
        counters.bundle_publication_state = BundlePublicationState.REPLACED_DURABLE
        fail_after_dir = hooks.get("fail_after_bundle_dir_fsync")
        if callable(fail_after_dir):
            fail_after_dir()


@contextmanager
def _provisioning_lock(model_root: Path) -> Iterator[None]:
    lock_path = model_root / ".offline-rag-embedding-provision.lock"
    _assert_physically_inside(model_root, lock_path)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise BundleProvisionError(
                OUTCOME_LOCK_UNAVAILABLE,
                "another provisioning writer holds the model-root lock",
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    except BundleProvisionError:
        raise
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _read_previous_bundle(model_root: Path) -> _PreviousBundleState:
    path = bundle_manifest_path(model_root)
    if not path.exists():
        return _PreviousBundleState(kind="absent")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        parse_bundle_manifest(payload)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise BundleProvisionError(
            OUTCOME_MALFORMED_BUNDLE,
            f"malformed embedding bundle: {exc}",
        ) from exc
    return _PreviousBundleState(kind="present_valid", bytes=raw)


def _inspect(
    model_root: Path,
    representation_id: RepresentationId,
    *,
    model_id: str,
    revision: str,
    expected_dimension: int,
) -> Any:
    return inspect_representation(
        model_root,
        representation_id,
        expected_model_id=model_id,
        expected_revision=revision,
        expected_dimension=expected_dimension,
    )


def _plan_representation(
    inspection: Any,
    *,
    representation_id: RepresentationId,
    force: bool,
    need_bundle: bool,
) -> _RepPlan:
    readiness = str(inspection.readiness)
    reason = str(inspection.reason)
    if readiness == RepresentationReadiness.READY and not force:
        if (
            representation_id == "torch_st_v1"
            and need_bundle
            and inspection.reason_code.value == "legacy_torch_ready"
        ):
            return _RepPlan(
                representation_id,
                "adopt_legacy",
                readiness,
                reason,
            )
        return _RepPlan(representation_id, "preserve", readiness, reason)
    if readiness == RepresentationReadiness.READY and force:
        return _RepPlan(representation_id, "replace", readiness, reason)
    if readiness == RepresentationReadiness.ABSENT:
        return _RepPlan(representation_id, "install", readiness, reason)
    # INVALID (or unexpected) → repair via replace/install path
    return _RepPlan(representation_id, "replace", readiness, reason)


def _instance_dir_name(*, representation_id: RepresentationId, digest_key: str) -> str:
    """Content-derived prefix plus uniqueness suffix (replacements never reuse dirs)."""
    short = hashlib.sha256(digest_key.encode("utf-8")).hexdigest()[:16]
    nonce = os.urandom(4).hex()
    return f"{representation_id}-{short}-{nonce}"


def _write_torch_manifest(
    model_dir: Path,
    *,
    model_id: str,
    revision: str,
    expected_dimension: int,
    root: Path,
) -> tuple[str, int]:
    digests = _collect_file_digests(model_dir, required=list(REQUIRED_EMBEDDING_FILES))
    artifact_id = _artifact_id_from_digests(
        model_id=model_id, revision=revision, digests=digests
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
        metadata={"source": "p3_bundle_provision"},
    )
    _durable_write_text(
        embedding_manifest_path(model_dir),
        manifest.model_dump_json(),
        root=root,
    )
    return artifact_id, len(digests)


def _persist_staging_tree(
    staging: Path, *, root: Path, hooks: Mapping[str, Any]
) -> int:
    """Fsync every regular file and directory under staging (F002)."""
    fail = hooks.get("fail_before_torch_persist")
    if callable(fail):
        fail()
    files_persisted = 0
    for path in sorted(staging.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        _assert_physically_inside(root, path)
        if path.is_symlink():
            raise BundleProvisionError(
                OUTCOME_WRITE_FAILED,
                f"staged tree still contains symlink before publish: {path}",
            )
        if path.is_file():
            st = path.stat()
            if not stat.S_ISREG(st.st_mode):
                raise BundleProvisionError(
                    OUTCOME_WRITE_FAILED,
                    f"staged tree contains non-regular file: {path}",
                )
            _fsync_file(path)
            files_persisted += 1
            fail_file = hooks.get("fail_after_torch_file_persist")
            if callable(fail_file):
                fail_file(str(path.relative_to(staging)))
        elif path.is_dir():
            _fsync_dir(path)
    _fsync_dir(staging)
    fail_done = hooks.get("fail_after_torch_persist")
    if callable(fail_done):
        fail_done()
    return files_persisted


def _acquire_torch_into_staging(
    staging: Path,
    *,
    model_id: str,
    revision: str,
    expected_dimension: int,
    root: Path,
    counters: _TxCounters,
) -> tuple[str, int]:
    hooks = counters.hooks
    _durable_mkdir(staging, root=root)
    fail = hooks.get("fail_before_torch_download")
    if callable(fail):
        fail()
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=model_id, revision=revision, local_dir=str(staging))
    # Materialize HF symlinks to independent regular files under the model root.
    for path in staging.rglob("*"):
        if path.is_symlink():
            target = path.resolve(strict=True)
            if not target.is_file():
                raise BundleProvisionError(
                    OUTCOME_SOURCE_INVALID,
                    f"torch snapshot symlink is not a regular file: {path}",
                )
            data = target.read_bytes()
            path.unlink()
            _durable_write_bytes(path, data, root=root)
    artifact_id, n_files = _write_torch_manifest(
        staging,
        model_id=model_id,
        revision=revision,
        expected_dimension=expected_dimension,
        root=root,
    )
    # F002: persist every regular file P3 intends to publish (HF does not own this).
    counters.torch_files_persisted = _persist_staging_tree(
        staging, root=root, hooks=hooks
    )
    fail_v = hooks.get("fail_after_torch_stage_validate_setup")
    if callable(fail_v):
        fail_v()
    status = validate_embedding_artifacts(
        staging,
        expected_model_id=model_id,
        expected_revision=revision,
        expected_dimension=expected_dimension,
    )
    if status.readiness != EmbeddingReadiness.READY:
        raise BundleProvisionError(
            OUTCOME_QUALIFICATION_MISMATCH,
            f"staged torch invalid: {status.reason}",
        )
    fail_sv = hooks.get("fail_after_torch_stage_validate")
    if callable(fail_sv):
        fail_sv()
    return artifact_id, n_files


def _copy_onnx_into_staging(
    staging: Path,
    *,
    onnx_source: Path,
    root: Path,
    counters: _TxCounters,
) -> str:
    hooks = counters.hooks
    fail = hooks.get("fail_before_onnx_copy")
    if callable(fail):
        fail()
    spec = load_package_qualification_spec("onnx_fp32_v1")
    source_root = Path(onnx_source).expanduser().resolve(strict=True)
    if not source_root.is_dir():
        raise BundleProvisionError(
            OUTCOME_SOURCE_INVALID,
            f"onnx source is not a directory: {source_root}",
        )
    _durable_mkdir(staging, root=root)
    copied_digests: dict[str, str] = {}
    for rel in spec.required_files:
        src = source_root / rel
        dest = staging / rel
        digest = _copy_regular_file(src, dest, root=root)
        expected = spec.expected_file_digests.get(rel)
        if expected is None or digest != expected:
            raise BundleProvisionError(
                OUTCOME_QUALIFICATION_MISMATCH,
                f"copied digest mismatch for {rel}",
            )
        copied_digests[rel] = digest
        counters.onnx_files_copied += 1
        fail_file = hooks.get("fail_after_onnx_file_copy")
        if callable(fail_file):
            fail_file(rel)

    installed = {
        "installed_representation_schema": INSTALLED_REPRESENTATION_SCHEMA,
        "representation_id": "onnx_fp32_v1",
        "model_id": spec.model_id,
        "model_revision": spec.model_revision,
        "expected_dimension": spec.expected_dimension,
        "runtime_family": spec.runtime_family,
        "qualification_id": "onnx_fp32_v1",
        "required_files": list(spec.required_files),
        "file_digests": dict(spec.expected_file_digests),
        "runtime_contract": dict(spec.runtime_contract),
    }
    _durable_write_text(
        staging / REPRESENTATION_MANIFEST_NAME,
        json.dumps(installed, indent=2, sort_keys=True) + "\n",
        root=root,
    )
    fail_v = hooks.get("fail_after_onnx_stage")
    if callable(fail_v):
        fail_v()
    key = "|".join(f"{k}:{copied_digests[k]}" for k in sorted(copied_digests))
    return key


def _publish_bundle(
    model_root: Path,
    pointers: dict[str, str],
    *,
    counters: _TxCounters,
) -> None:
    hooks = counters.hooks
    fail = hooks.get("fail_before_bundle_tmp")
    if callable(fail):
        fail()
    for pointer in pointers.values():
        _validate_relative_pointer(pointer)
    payload = {
        "bundle_schema": BUNDLE_SCHEMA,
        "representations": {k: pointers[k] for k in sorted(pointers)},
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    final = bundle_manifest_path(model_root)
    _assert_physically_inside(model_root, final)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{BUNDLE_MANIFEST_NAME}.",
        suffix=".tmp",
        dir=str(model_root),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        fail_persist = hooks.get("fail_before_bundle_tmp_fsync_done")
        if callable(fail_persist):
            fail_persist()
        fail_replace = hooks.get("fail_before_bundle_replace")
        if callable(fail_replace):
            fail_replace()
        # Selection becomes potentially live at os.replace inside this helper.
        _durable_replace_file(
            tmp_path,
            final,
            root=model_root,
            counters=counters,
            mark_bundle_selection=True,
        )
    except BundleProvisionError:
        if not counters.selection_may_be_live:
            tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if not counters.selection_may_be_live:
            tmp_path.unlink(missing_ok=True)
        raise BundleProvisionError(
            OUTCOME_PUBLISH_FAILED, f"bundle publish failed: {exc}"
        ) from exc


def _restore_previous_bundle(
    model_root: Path,
    previous: _PreviousBundleState,
    *,
    counters: _TxCounters,
) -> None:
    hooks = counters.hooks
    fail = hooks.get("fail_before_rollback_write")
    if callable(fail):
        fail()
    final = bundle_manifest_path(model_root)
    try:
        if previous.kind == "absent":
            if final.exists():
                # Restore absence: replace with delete + dir fsync.
                fail_rep = hooks.get("fail_before_rollback_replace")
                if callable(fail_rep):
                    fail_rep()
                final.unlink()
                _fsync_dir(model_root)
        else:
            assert previous.bytes is not None
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{BUNDLE_MANIFEST_NAME}.rollback.",
                suffix=".tmp",
                dir=str(model_root),
            )
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(previous.bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
                fail_rep = hooks.get("fail_before_rollback_replace")
                if callable(fail_rep):
                    fail_rep()
                _durable_replace_file(tmp_path, final, root=model_root)
                fail_dir = hooks.get("fail_after_rollback_dir_fsync")
                if callable(fail_dir):
                    fail_dir()
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
    except BundleProvisionError:
        raise
    except Exception as exc:
        raise BundleProvisionError(
            OUTCOME_ROLLBACK_FAILED, f"bundle rollback failed: {exc}"
        ) from exc


def _current_pointers(model_root: Path) -> dict[str, str]:
    path = bundle_manifest_path(model_root)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_bundle_manifest(payload)


def _action_outcome(action: str) -> str:
    if action == "preserve":
        return OUTCOME_ALREADY_PROVISIONED
    if action == "adopt_legacy":
        return OUTCOME_ADOPTED_LEGACY
    if action == "replace":
        return OUTCOME_REPLACED
    return OUTCOME_INSTALLED


def _legacy_torch_manifest_path(
    model_root: Path, resulting_pointers: Mapping[str, str]
) -> str | None:
    """Frozen EmbeddingProvisionReport.manifest_path semantics (F004).

    Identifies an applicable Torch ``offline-rag-embedding.json`` when present.
    Never silently redefined as the bundle manifest path.
    """
    pointer = resulting_pointers.get("torch_st_v1")
    if pointer == ".":
        path = embedding_manifest_path(model_root)
        return str(path) if path.is_file() else None
    if pointer:
        path = model_root / pointer / EMBEDDING_MANIFEST_NAME
        return str(path) if path.is_file() else None
    # Legacy root / no bundle torch pointer yet.
    path = embedding_manifest_path(model_root)
    return str(path) if path.is_file() else None


def provision_embedding_representations(
    destination: Path,
    *,
    representations: str | Sequence[str] | None = None,
    model_id: str = QWEN3_EMBEDDING_MODEL_ID,
    revision: str = QWEN3_EMBEDDING_PINNED_REVISION,
    expected_dimension: int = DEFAULT_EXPECTED_DIMENSION,
    force: bool = False,
    onnx_source: Path | str | None = None,
    test_hooks: Mapping[str, Any] | None = None,
) -> EmbeddingProvisionReport:
    """Bundle-aware provisioning transaction for requested representations."""
    requested = normalize_representation_request(representations)
    dest = Path(destination).expanduser()
    counters = _TxCounters(hooks=dict(test_hooks or {}))
    metadata: dict[str, Any] = {
        "p3_schema": P3_METADATA_SCHEMA,
        "requested_representations": list(requested),
        "representation_results": {},
        "bundle_changed": False,
        "bundle_manifest": None,
        "restart_required": False,
        "outcome_code": None,
        "onnx_files_copied": 0,
    }

    try:
        model_root = _canonical_model_root(dest)
    except (BundleProvisionError, OSError) as exc:
        outcome = (
            exc.outcome_code
            if isinstance(exc, BundleProvisionError)
            else OUTCOME_WRITE_FAILED
        )
        return EmbeddingProvisionReport(
            status=ProvisioningStatus.FAILED,
            model_id=model_id,
            requested_revision=revision,
            destination=str(dest),
            errors=[str(exc)],
            metadata={
                **metadata,
                "outcome_code": outcome,
            },
        )

    try:
        with _provisioning_lock(model_root):
            return _run_transaction(
                model_root,
                requested=requested,
                model_id=model_id,
                revision=revision,
                expected_dimension=expected_dimension,
                force=force,
                onnx_source=Path(onnx_source) if onnx_source is not None else None,
                counters=counters,
                metadata=metadata,
            )
    except BundleProvisionError as exc:
        return EmbeddingProvisionReport(
            status=ProvisioningStatus.FAILED,
            model_id=model_id,
            requested_revision=revision,
            destination=str(model_root),
            errors=[str(exc)],
            metadata={
                **metadata,
                "outcome_code": exc.outcome_code,
                "onnx_files_copied": counters.onnx_files_copied,
            },
        )


def _run_transaction(
    model_root: Path,
    *,
    requested: list[RepresentationId],
    model_id: str,
    revision: str,
    expected_dimension: int,
    force: bool,
    onnx_source: Path | None,
    counters: _TxCounters,
    metadata: dict[str, Any],
) -> EmbeddingProvisionReport:
    # Authoritative inspect after lock.
    try:
        previous = _read_previous_bundle(model_root)
    except BundleProvisionError as exc:
        metadata["outcome_code"] = exc.outcome_code
        raise

    inspections = {
        rep: _inspect(
            model_root,
            rep,
            model_id=model_id,
            revision=revision,
            expected_dimension=expected_dimension,
        )
        for rep in requested
    }

    # Need a bundle when ONNX is involved or torch must leave legacy-only mode.
    need_bundle = (
        "onnx_fp32_v1" in requested
        or previous.kind == "present_valid"
        or any(
            inspections[r].readiness != RepresentationReadiness.READY or force
            for r in requested
        )
    )
    # If only torch and legacy ready and no force and no existing bundle → already
    if (
        requested == ["torch_st_v1"]
        and not force
        and previous.kind == "absent"
        and inspections["torch_st_v1"].readiness == RepresentationReadiness.READY
    ):
        insp = inspections["torch_st_v1"]
        metadata.update(
            {
                "outcome_code": OUTCOME_ALREADY_PROVISIONED,
                "bundle_changed": False,
                "representation_results": {
                    "torch_st_v1": {
                        "action": "preserve",
                        "readiness": str(insp.readiness),
                        "outcome": OUTCOME_ALREADY_PROVISIONED,
                    }
                },
                "restart_required": False,
            }
        )
        artifact_id = None
        if insp.instance_path is not None:
            status = validate_embedding_artifacts(
                insp.instance_path,
                expected_model_id=model_id,
                expected_revision=revision,
                expected_dimension=expected_dimension,
            )
            artifact_id = status.manifest.artifact_id if status.manifest else None
        return EmbeddingProvisionReport(
            status=ProvisioningStatus.ALREADY_PROVISIONED,
            model_id=model_id,
            requested_revision=revision,
            resolved_revision=revision,
            destination=str(model_root),
            artifact_id=artifact_id,
            manifest_path=str(embedding_manifest_path(model_root)),
            files_downloaded=0,
            metadata=metadata,
        )

    plans = [
        _plan_representation(
            inspections[rep],
            representation_id=rep,
            force=force,
            need_bundle=need_bundle
            or ("onnx_fp32_v1" in requested and previous.kind == "absent"),
        )
        for rep in requested
    ]

    # If ONNX install/replace and torch is legacy READY, adopt legacy into bundle.
    if "onnx_fp32_v1" in requested and previous.kind == "absent":
        torch_insp = _inspect(
            model_root,
            "torch_st_v1",
            model_id=model_id,
            revision=revision,
            expected_dimension=expected_dimension,
        )
        if (
            torch_insp.readiness == RepresentationReadiness.READY
            and torch_insp.reason_code.value == "legacy_torch_ready"
            and "torch_st_v1" not in requested
        ):
            plans.append(
                _RepPlan(
                    "torch_st_v1",
                    "adopt_legacy",
                    str(torch_insp.readiness),
                    torch_insp.reason,
                )
            )
        elif "torch_st_v1" in requested and any(
            p.representation_id == "torch_st_v1" for p in plans
        ):
            for plan in plans:
                if (
                    plan.representation_id == "torch_st_v1"
                    and plan.action == "preserve"
                    and inspections["torch_st_v1"].reason_code.value
                    == "legacy_torch_ready"
                ):
                    plan.action = "adopt_legacy"

    if all(p.action == "preserve" for p in plans):
        metadata.update(
            {
                "outcome_code": OUTCOME_ALREADY_PROVISIONED,
                "bundle_changed": False,
                "representation_results": {
                    p.representation_id: {
                        "action": "preserve",
                        "readiness": p.readiness,
                        "outcome": OUTCOME_ALREADY_PROVISIONED,
                    }
                    for p in plans
                },
                "bundle_manifest": str(bundle_manifest_path(model_root))
                if previous.kind == "present_valid"
                else None,
                "restart_required": False,
            }
        )
        return EmbeddingProvisionReport(
            status=ProvisioningStatus.ALREADY_PROVISIONED,
            model_id=model_id,
            requested_revision=revision,
            resolved_revision=revision,
            destination=str(model_root),
            artifact_id=None,
            manifest_path=_legacy_torch_manifest_path(
                model_root,
                _current_pointers(model_root) if previous.kind == "present_valid" else {},
            ),
            files_downloaded=0,
            metadata=metadata,
        )

    # ONNX source requirement
    onnx_plans = [
        p
        for p in plans
        if p.representation_id == "onnx_fp32_v1" and p.action in {"install", "replace"}
    ]
    if onnx_plans and onnx_source is None:
        raise BundleProvisionError(
            OUTCOME_SOURCE_REQUIRED,
            "onnx_fp32_v1 install/replace requires --onnx-source",
        )

    # Build resulting pointers starting from previous valid / empty.
    if previous.kind == "present_valid":
        resulting = _current_pointers(model_root)
    else:
        resulting = {}

    staging_root = model_root / ".p3-staging"
    _durable_mkdir(staging_root, root=model_root)
    if not _same_filesystem(staging_root, model_root):
        raise BundleProvisionError(
            OUTCOME_WRITE_FAILED,
            "staging is not on the same filesystem as the model root",
        )

    published_instances: dict[str, Path] = {}
    artifact_id: str | None = None

    try:
        for plan in plans:
            if plan.action == "preserve":
                continue
            if plan.action == "adopt_legacy":
                resulting["torch_st_v1"] = "."
                metadata["representation_results"][plan.representation_id] = {
                    "action": plan.action,
                    "readiness": plan.readiness,
                    "outcome": OUTCOME_ADOPTED_LEGACY,
                    "pointer": ".",
                }
                continue

            if plan.representation_id == "torch_st_v1":
                stage = staging_root / f"torch-{os.getpid()}-{os.urandom(4).hex()}"
                art_id, n_files = _acquire_torch_into_staging(
                    stage,
                    model_id=model_id,
                    revision=revision,
                    expected_dimension=expected_dimension,
                    root=model_root,
                    counters=counters,
                )
                counters.files_downloaded += n_files
                artifact_id = art_id
                inst_name = _instance_dir_name(
                    representation_id="torch_st_v1", digest_key=art_id
                )
                final = (
                    model_root / REPRESENTATIONS_DIR_NAME / "torch_st_v1" / inst_name
                )
                fail_pub = counters.hooks.get("fail_before_instance_publish")
                if callable(fail_pub):
                    fail_pub("torch_st_v1")
                _durable_publish_directory(stage, final, root=model_root)
                published_instances["torch_st_v1"] = final
                pointer = str(final.relative_to(model_root)).replace("\\", "/")
                resulting["torch_st_v1"] = _validate_relative_pointer(pointer)
                metadata["representation_results"]["torch_st_v1"] = {
                    "action": plan.action,
                    "readiness": plan.readiness,
                    "outcome": _action_outcome(plan.action),
                    "pointer": resulting["torch_st_v1"],
                }

            elif plan.representation_id == "onnx_fp32_v1":
                assert onnx_source is not None
                stage = staging_root / f"onnx-{os.getpid()}-{os.urandom(4).hex()}"
                digest_key = _copy_onnx_into_staging(
                    stage,
                    onnx_source=onnx_source,
                    root=model_root,
                    counters=counters,
                )
                # Pre-publish qualification via temporary bundle is not used;
                # validate files + installed manifest shape, then publish instance,
                # then single bundle commit, then P1 inspect.
                inst_name = _instance_dir_name(
                    representation_id="onnx_fp32_v1", digest_key=digest_key
                )
                final = (
                    model_root / REPRESENTATIONS_DIR_NAME / "onnx_fp32_v1" / inst_name
                )
                fail_pub = counters.hooks.get("fail_before_instance_publish")
                if callable(fail_pub):
                    fail_pub("onnx_fp32_v1")
                _durable_publish_directory(stage, final, root=model_root)
                published_instances["onnx_fp32_v1"] = final
                pointer = str(final.relative_to(model_root)).replace("\\", "/")
                resulting["onnx_fp32_v1"] = _validate_relative_pointer(pointer)
                metadata["representation_results"]["onnx_fp32_v1"] = {
                    "action": plan.action,
                    "readiness": plan.readiness,
                    "outcome": _action_outcome(plan.action),
                    "pointer": resulting["onnx_fp32_v1"],
                }

        # Preserve unrequested existing pointers from previous valid bundle.
        if previous.kind == "present_valid":
            for key, value in _current_pointers(model_root).items():
                resulting.setdefault(key, value)

        for plan in plans:
            if plan.action == "preserve":
                if plan.representation_id not in resulting:
                    # Should already be present from previous bundle
                    insp = inspections[plan.representation_id]
                    if (
                        insp.instance_path is not None
                        and insp.instance_path != model_root
                    ):
                        pointer = str(
                            Path(insp.instance_path).resolve().relative_to(model_root)
                        ).replace("\\", "/")
                        resulting[plan.representation_id] = _validate_relative_pointer(
                            pointer
                        )
                metadata["representation_results"][plan.representation_id] = {
                    "action": "preserve",
                    "readiness": plan.readiness,
                    "outcome": OUTCOME_ALREADY_PROVISIONED,
                    "pointer": resulting.get(plan.representation_id),
                }

        _publish_bundle(model_root, resulting, counters=counters)
        metadata["bundle_changed"] = True
        metadata["bundle_manifest"] = str(bundle_manifest_path(model_root))

        fail_post = counters.hooks.get("fail_after_post_publish_validation")
        # Post-publication P1 inspect for every requested representation.
        final_results: dict[str, Any] = {}
        for rep in requested:
            insp = _inspect(
                model_root,
                rep,
                model_id=model_id,
                revision=revision,
                expected_dimension=expected_dimension,
            )
            final_results[rep] = {
                "readiness": str(insp.readiness),
                "reason": insp.reason,
            }
            if insp.readiness != RepresentationReadiness.READY:
                raise BundleProvisionError(
                    OUTCOME_POST_PUBLISH_VALIDATION_FAILED,
                    f"post-publish validation failed for {rep}: {insp.reason}",
                )
        if callable(fail_post):
            fail_post()

        metadata["final_observed_state"] = final_results
        metadata["onnx_files_copied"] = counters.onnx_files_copied
        metadata["restart_required"] = True
        metadata["outcome_code"] = (
            OUTCOME_REPLACED
            if any(p.action == "replace" for p in plans)
            else OUTCOME_INSTALLED
        )
        # Prefer installed when any install/adopt without replace
        if any(p.action == "adopt_legacy" for p in plans) and all(
            p.action in {"preserve", "adopt_legacy", "install"} for p in plans
        ):
            if any(p.action == "install" for p in plans):
                metadata["outcome_code"] = OUTCOME_INSTALLED
            else:
                metadata["outcome_code"] = OUTCOME_ADOPTED_LEGACY

        metadata["bundle_publication_state"] = counters.bundle_publication_state.value
        metadata["torch_files_persisted"] = counters.torch_files_persisted
        return EmbeddingProvisionReport(
            status=ProvisioningStatus.READY,
            model_id=model_id,
            requested_revision=revision,
            resolved_revision=revision,
            destination=str(model_root),
            artifact_id=artifact_id,
            manifest_path=_legacy_torch_manifest_path(model_root, resulting),
            files_downloaded=counters.files_downloaded,
            metadata=metadata,
        )
    except Exception as raw_exc:  # noqa: BLE001 — fail closed; map to bounded outcome
        if isinstance(raw_exc, BundleProvisionError):
            exc = raw_exc
        else:
            exc = BundleProvisionError(OUTCOME_WRITE_FAILED, str(raw_exc))
        # F001: any failure after os.replace must attempt recovery.
        if counters.selection_may_be_live:
            try:
                _restore_previous_bundle(model_root, previous, counters=counters)
                metadata["rollback"] = {
                    "attempted": True,
                    "restored": previous.kind,
                    "ok": True,
                    "publication_state": counters.bundle_publication_state.value,
                }
            except BundleProvisionError as rollback_exc:
                metadata["rollback"] = {
                    "attempted": True,
                    "ok": False,
                    "outcome_code": rollback_exc.outcome_code,
                    "error": str(rollback_exc),
                }
                metadata["outcome_code"] = OUTCOME_ROLLBACK_FAILED
                observed: dict[str, Any] = {}
                for rep in requested:
                    try:
                        insp = _inspect(
                            model_root,
                            rep,
                            model_id=model_id,
                            revision=revision,
                            expected_dimension=expected_dimension,
                        )
                        observed[rep] = {
                            "readiness": str(insp.readiness),
                            "reason": insp.reason,
                        }
                    except Exception as observe_exc:  # noqa: BLE001
                        observed[rep] = {"error": str(observe_exc)}
                metadata["final_observed_state"] = observed
                metadata["onnx_files_copied"] = counters.onnx_files_copied
                return EmbeddingProvisionReport(
                    status=ProvisioningStatus.FAILED,
                    model_id=model_id,
                    requested_revision=revision,
                    destination=str(model_root),
                    errors=[str(exc), str(rollback_exc)],
                    metadata=metadata,
                )
            observed = {}
            for rep in requested:
                insp = _inspect(
                    model_root,
                    rep,
                    model_id=model_id,
                    revision=revision,
                    expected_dimension=expected_dimension,
                )
                observed[rep] = {
                    "readiness": str(insp.readiness),
                    "reason": insp.reason,
                }
            metadata["final_observed_state"] = observed
        elif not counters.selection_may_be_live:
            metadata["rollback"] = {
                "attempted": False,
                "reason": "no_forward_bundle_publication",
            }
        metadata["outcome_code"] = exc.outcome_code
        metadata["onnx_files_copied"] = counters.onnx_files_copied
        metadata["bundle_publication_state"] = counters.bundle_publication_state.value
        metadata["bundle_changed"] = False
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
        raise exc
    finally:
        if staging_root.exists():
            for child in list(staging_root.iterdir()):
                shutil.rmtree(child, ignore_errors=True)
            try:
                staging_root.rmdir()
            except OSError:
                pass


def provision_embedding_model(
    destination: Path,
    *,
    model_id: str = QWEN3_EMBEDDING_MODEL_ID,
    revision: str = QWEN3_EMBEDDING_PINNED_REVISION,
    expected_dimension: int = DEFAULT_EXPECTED_DIMENSION,
    force: bool = False,
    representation: str | Sequence[str] | None = None,
    onnx_source: Path | str | None = None,
    test_hooks: Mapping[str, Any] | None = None,
) -> EmbeddingProvisionReport:
    """Compatibility entry: all embedding provision routes converge here."""
    return provision_embedding_representations(
        destination,
        representations=representation,
        model_id=model_id,
        revision=revision,
        expected_dimension=expected_dimension,
        force=force,
        onnx_source=onnx_source,
        test_hooks=test_hooks,
    )


__all__ = [
    "ALL_REPRESENTATIONS",
    "P3_METADATA_SCHEMA",
    "BundleProvisionError",
    "normalize_representation_request",
    "provision_embedding_model",
    "provision_embedding_representations",
]
