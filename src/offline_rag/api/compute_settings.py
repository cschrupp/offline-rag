"""Seneca Compute Settings API (Slice 16L / 16K-D P2)."""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from offline_rag.app.compute_product_settings import (
    SenecaComputeBody,
    SenecaComputeSettingsFile,
    compute_field_locks,
    read_product_compute_settings,
    write_product_compute_settings,
)
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.runtime import (
    ApplicationRuntime,
    EmbeddingAvailabilitySnapshot,
)
from offline_rag.dense.device import cuda_availability_reason
from offline_rag.dense.embedder import EmbedderError, embedder_runtime_view
from offline_rag.dense.embedding_runtime import RuntimeFailureKind
from offline_rag.dense.execution_profile import resolve_qualified_embedding_profile

router = APIRouter(tags=["settings"])

EmbeddingDevicePolicy = Literal["auto", "cpu", "cuda"]


def _runtime(request: Request) -> ApplicationRuntime:
    return request.app.state.runtime


def _product_failure_reason(embedder: object) -> str | None:
    """Map typed P1 failure_kind to bounded D05 product reasons (no string parse)."""
    kind = getattr(embedder, "failure_kind", None)
    if kind is RuntimeFailureKind.INITIALIZATION or kind == RuntimeFailureKind.INITIALIZATION:
        return "runtime_initialization_failed"
    if kind is RuntimeFailureKind.EXECUTION or kind == RuntimeFailureKind.EXECUTION:
        return "runtime_execution_failed"
    return None


def _backend_provider(embedder: object) -> tuple[str | None, str | None]:
    profile = getattr(embedder, "profile", None)
    if profile is None:
        return None, None
    backend = getattr(profile, "backend_family", None)
    provider = getattr(profile, "provider", None)
    return (
        str(backend) if backend is not None else None,
        str(provider) if provider is not None else None,
    )


def project_embedding_runtime_dto(embedder: object) -> dict[str, Any]:
    """Additive process-owned embedding runtime projection (D03)."""
    view = embedder_runtime_view(embedder)
    backend, provider = _backend_provider(embedder)
    state = view.get("runtime_state")
    embedding_state = str(state) if state else None
    model = getattr(embedder, "model_id", None)
    revision = getattr(embedder, "model_revision", None)
    dimension = getattr(embedder, "dimension", None)
    return {
        # Legacy 16L fields retained.
        "active_device": view.get("active_device"),
        "cuda_available": view.get("cuda_available"),
        "torch_cuda_build": view.get("torch_cuda_build"),
        "selection_reason": view.get("selection_reason"),
        # Additive P2 facts.
        "configured_device": view.get("configured_device"),
        "configured_precision": view.get("configured_precision"),
        "resolved_device": view.get("active_device"),
        "resolved_precision": view.get("resolved_precision"),
        "profile_id": view.get("profile_id"),
        "representation_id": view.get("representation_id"),
        "embedding_state": embedding_state,
        "backend": backend,
        "provider": provider,
        "model": str(model) if model is not None else None,
        "model_revision": str(revision) if revision is not None else None,
        "embedding_dimension": int(dimension) if isinstance(dimension, int) else None,
        "failure_reason": _product_failure_reason(embedder),
    }


def _runtime_block(runtime: ApplicationRuntime) -> dict[str, Any]:
    runtime.require_ready()
    if runtime.resources is None or runtime.resources.embedder is None:
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(reason="embedder_unavailable"),
        )
    return project_embedding_runtime_dto(runtime.resources.embedder)


def _frozen_probe(snapshot: EmbeddingAvailabilitySnapshot):
    def probe() -> tuple[bool, str | None, bool]:
        if snapshot.cuda_probe_failed:
            return False, snapshot.torch_cuda_build, True
        return snapshot.cuda_available, snapshot.torch_cuda_build, False

    return probe


def _rep_fact(snapshot: EmbeddingAvailabilitySnapshot, representation_id: str):
    if representation_id == "torch_st_v1":
        return snapshot.torch_st_v1
    return snapshot.onnx_fp32_v1


def evaluate_device_candidate(
    *,
    snapshot: EmbeddingAvailabilitySnapshot,
    device_policy: str,
    precision: str,
) -> tuple[bool, str | None]:
    """Next-start eligibility using frozen probe + cached readiness (D04)."""
    if not snapshot.qualified:
        # Legacy/fake path: auto/cpu always available; CUDA follows witness.
        if device_policy in {"auto", "cpu"}:
            return True, None
        if snapshot.cuda_available and not snapshot.cuda_probe_failed:
            return True, None
        reason = cuda_availability_reason(
            cuda_available=snapshot.cuda_available if not snapshot.cuda_probe_failed else False,
            torch_cuda_build=snapshot.torch_cuda_build,
            selection_reason=(
                "cuda_probe_failed" if snapshot.cuda_probe_failed else None
            ),
        )
        return False, reason or "cuda_unavailable"

    try:
        resolution = resolve_qualified_embedding_profile(
            device_policy,
            precision,
            probe=_frozen_probe(snapshot),
        )
    except EmbedderError as exc:
        message = str(exc).lower()
        if "fp16" in message and ("cpu" in message or "auto" in message):
            return False, "precision_requires_cuda"
        if snapshot.cuda_probe_failed:
            return False, "cuda_probe_failed"
        reason = cuda_availability_reason(
            cuda_available=False,
            torch_cuda_build=snapshot.torch_cuda_build,
            selection_reason=None,
        )
        return False, reason or "cuda_unavailable"
    except ValueError:
        return False, "settings_invalid"

    fact = _rep_fact(snapshot, resolution.profile.representation_id)
    if fact.readiness == "READY":
        return True, None
    if device_policy == "auto":
        return False, "auto_selected_profile_unavailable"
    return False, fact.bounded_reason or "representation_absent"


def _availability(
    runtime: ApplicationRuntime,
) -> dict[str, Any]:
    snapshot = runtime.embedding_availability
    if snapshot is None:
        # Should not happen while READY; fail closed to cuda-unavailable posture.
        return {
            "auto": {"available": False, "reason": "availability_snapshot_missing"},
            "cpu": {"available": False, "reason": "availability_snapshot_missing"},
            "cuda": {"available": False, "reason": "availability_snapshot_missing"},
        }
    precision = str(runtime.settings.indexing.embedding.precision)
    auto_ok, auto_reason = evaluate_device_candidate(
        snapshot=snapshot, device_policy="auto", precision=precision
    )
    cpu_ok, cpu_reason = evaluate_device_candidate(
        snapshot=snapshot, device_policy="cpu", precision=precision
    )
    cuda_ok, cuda_reason = evaluate_device_candidate(
        snapshot=snapshot, device_policy="cuda", precision=precision
    )
    return {
        "auto": {
            "available": auto_ok,
            **({"reason": auto_reason} if not auto_ok and auto_reason else {}),
        },
        "cpu": {
            "available": cpu_ok,
            **({"reason": cpu_reason} if not cpu_ok and cpu_reason else {}),
        },
        "cuda": {
            "available": cuda_ok,
            "reason": None if cuda_ok else cuda_reason,
        },
    }


def _pending_view(
    *,
    active_device: str,
    product: SenecaComputeSettingsFile | None,
    locks: dict[str, bool],
) -> dict[str, Any] | None:
    if product is None or locks.get("embedding_device"):
        return None
    pending_device = product.compute.embedding_device
    if pending_device == active_device:
        return None
    return {"embedding_device": pending_device}


def _require_snapshot(runtime: ApplicationRuntime) -> EmbeddingAvailabilitySnapshot:
    snapshot = runtime.embedding_availability
    if snapshot is None:
        raise AppError(
            ErrorCode.SETTINGS_INVALID,
            details=SafeErrorDetails(reason="availability_snapshot_missing"),
        )
    return snapshot


@router.get("/v1/settings/compute")
def get_compute_settings(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    runtime.require_ready()
    settings = runtime.settings
    locks = compute_field_locks(os.environ)
    try:
        product = read_product_compute_settings(settings.paths.product_settings)
    except ValueError as exc:
        raise AppError(
            ErrorCode.SETTINGS_INVALID,
            details=SafeErrorDetails(reason="malformed_product_settings"),
        ) from exc
    active_device = str(settings.indexing.embedding.device)
    pending = _pending_view(
        active_device=active_device, product=product, locks=locks
    )
    runtime_view = _runtime_block(runtime)
    return {
        "active": {"embedding_device": active_device},
        "pending": pending,
        "restart_required": pending is not None,
        "locks": locks,
        "runtime": runtime_view,
        "availability": _availability(runtime),
    }


class ComputeSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_device: EmbeddingDevicePolicy


def _assert_candidate_save_allowed(
    runtime: ApplicationRuntime, device_policy: EmbeddingDevicePolicy
) -> None:
    """Reject unavailable/unauthorized next-start policies (D04); no write side effects."""
    snapshot = _require_snapshot(runtime)
    precision = str(runtime.settings.indexing.embedding.precision)
    ok, reason = evaluate_device_candidate(
        snapshot=snapshot,
        device_policy=device_policy,
        precision=precision,
    )
    if ok:
        return
    raise AppError(
        ErrorCode.SETTINGS_INVALID,
        details=SafeErrorDetails(reason=reason or "settings_invalid"),
    )


@router.put("/v1/settings/compute")
def save_compute_settings(
    request: Request, body: ComputeSaveRequest
) -> dict[str, Any]:
    runtime = _runtime(request)
    runtime.require_ready()
    settings = runtime.settings
    locks = compute_field_locks(os.environ)
    if locks.get("embedding_device"):
        raise AppError(
            ErrorCode.SETTINGS_LOCKED,
            details=SafeErrorDetails(
                field="embedding_device", reason="operator_locked"
            ),
        )
    _assert_candidate_save_allowed(runtime, body.embedding_device)
    record = SenecaComputeSettingsFile(
        compute=SenecaComputeBody(embedding_device=body.embedding_device)
    )
    write_product_compute_settings(settings.paths.product_settings, record)
    active_device = str(settings.indexing.embedding.device)
    pending = _pending_view(
        active_device=active_device, product=record, locks=locks
    )
    runtime_view = _runtime_block(runtime)
    return {
        "saved": True,
        "restart_required": pending is not None,
        "active": {"embedding_device": active_device},
        "pending": pending,
        "locks": locks,
        "runtime": runtime_view,
        "availability": _availability(runtime),
    }
