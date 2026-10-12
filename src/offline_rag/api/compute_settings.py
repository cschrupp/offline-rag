"""Seneca Compute Settings API (Slice 16L)."""

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
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.dense.device import cuda_availability_reason
from offline_rag.dense.embedder import embedder_runtime_view

router = APIRouter(tags=["settings"])

EmbeddingDevicePolicy = Literal["auto", "cpu", "cuda"]


def _runtime(request: Request) -> ApplicationRuntime:
    return request.app.state.runtime


def _runtime_block(runtime: ApplicationRuntime) -> dict[str, Any]:
    runtime.require_ready()
    if runtime.resources is None or runtime.resources.embedder is None:
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(reason="embedder_unavailable"),
        )
    view = embedder_runtime_view(runtime.resources.embedder)
    return {
        "active_device": view["active_device"],
        "cuda_available": view["cuda_available"],
        "torch_cuda_build": view["torch_cuda_build"],
        "selection_reason": view["selection_reason"],
    }


def _availability(runtime_view: dict[str, Any]) -> dict[str, Any]:
    cuda_available = runtime_view.get("cuda_available")
    reason = cuda_availability_reason(
        cuda_available=cuda_available if isinstance(cuda_available, bool) else None,
        torch_cuda_build=(
            str(runtime_view["torch_cuda_build"])
            if runtime_view.get("torch_cuda_build") is not None
            else None
        ),
        selection_reason=(
            str(runtime_view["selection_reason"])
            if runtime_view.get("selection_reason") is not None
            else None
        ),
    )
    return {
        "auto": {"available": True},
        "cpu": {"available": True},
        "cuda": {
            "available": cuda_available is True,
            "reason": reason,
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
        "availability": _availability(runtime_view),
    }


class ComputeSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_device: EmbeddingDevicePolicy


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
        "availability": _availability(runtime_view),
    }
