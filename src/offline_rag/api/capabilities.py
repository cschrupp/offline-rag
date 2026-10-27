"""Read-only product capabilities (Slice 16D-A / 16L)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from offline_rag.api.compute_settings import project_embedding_runtime_dto
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.app.workspace.capacity import (
    LARGE_PDF_QUALIFIED_PROFILE_ID,
    LARGE_PDF_QUALIFIED_PROFILE_IDS,
    LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES,
    LARGE_PDF_REFERENCE_MEM_TOTAL_BYTES,
    large_pdf_runtime_eligibility,
)
from offline_rag.gold_authoring.readiness import evaluate_authoring_readiness

router = APIRouter(tags=["capabilities"])


def _runtime(request: Request) -> ApplicationRuntime:
    return request.app.state.runtime


@router.get("/v1/capabilities")
def get_capabilities(request: Request) -> dict[str, Any]:
    """Return ACTIVE/effective runtime capabilities (no secrets, no pending)."""
    runtime = _runtime(request)
    runtime.require_ready()
    settings = runtime.settings
    gen = settings.generation
    auth = settings.authoring
    api = settings.api
    emb = settings.indexing.embedding
    readiness = evaluate_authoring_readiness(settings)
    embedding_block: dict[str, Any] = {
        "model": str(emb.model_id),
        "configured_device": str(emb.device),
        "batch_size": int(emb.batch_size),
    }
    # ACTIVE process-owned embedder only — never re-resolve, re-probe, or load.
    if runtime.resources is not None and runtime.resources.embedder is not None:
        projected = project_embedding_runtime_dto(runtime.resources.embedder)
        embedding_block.update(
            {
                "active_device": projected["active_device"],
                "cuda_available": projected["cuda_available"],
                "torch_cuda_build": projected["torch_cuda_build"],
                "selection_reason": projected["selection_reason"],
                "configured_precision": projected["configured_precision"],
                "resolved_precision": projected["resolved_precision"],
                "profile_id": projected["profile_id"],
                "representation_id": projected["representation_id"],
                "embedding_state": projected["embedding_state"],
                "backend": projected["backend"],
                "provider": projected["provider"],
                "model_revision": projected["model_revision"],
                "embedding_dimension": projected["embedding_dimension"],
                "failure_reason": projected["failure_reason"],
            }
        )
        # Prefer live model id when present (qualified runtime).
        if projected.get("model"):
            embedding_block["model"] = projected["model"]
    else:
        embedding_block.update(
            {
                "active_device": None,
                "cuda_available": None,
                "torch_cuda_build": None,
                "selection_reason": None,
                "configured_precision": None,
                "resolved_precision": None,
                "profile_id": None,
                "representation_id": None,
                "embedding_state": None,
                "backend": None,
                "provider": None,
                "model_revision": None,
                "embedding_dimension": None,
                "failure_reason": None,
            }
        )
    active_profile_id = embedding_block.get("profile_id")
    active_embedder = (
        runtime.resources.embedder
        if runtime.resources is not None
        else None
    )
    active_cuda_device = (
        getattr(active_embedder, "resolved_device", None)
        or getattr(active_embedder, "device", None)
    )
    large_pdf_eligible, large_pdf_reason = large_pdf_runtime_eligibility(
        settings,
        profile_id=active_profile_id,
        cuda_device=active_cuda_device,
    )
    # 16K-C: transport envelope vs workspace/search capacity are distinct.
    # Unset workspace ceilings project as null (no unmeasured support claim).
    active_sources = api.max_active_sources_per_workspace
    searchable_children = api.max_searchable_child_chunks_per_workspace
    return {
        "product": {
            "name": "Seneca",
            "descriptor": "Grounded knowledge workspace",
        },
        "transport_limits": {
            "max_files_per_upload_request": int(api.max_files_per_ingest),
            "max_bytes_per_uploaded_file": int(api.max_bytes_per_document),
            "max_bytes_per_upload_request": int(api.max_total_upload_bytes),
        },
        "workspace_capacity": {
            "max_active_sources": (
                int(active_sources) if active_sources is not None else None
            ),
            "max_searchable_child_chunks": (
                int(searchable_children) if searchable_children is not None else None
            ),
            "max_active_source_bytes": int(api.max_active_source_bytes_per_workspace),
        },
        "large_pdf": {
            "policy_supported": True,
            "policy_max_bytes": int(api.max_pdf_bytes_per_document),
            "qualified_profile": LARGE_PDF_QUALIFIED_PROFILE_ID,
            "qualified_profiles": list(LARGE_PDF_QUALIFIED_PROFILE_IDS),
            "reference_host_memory_bytes": LARGE_PDF_REFERENCE_MEM_TOTAL_BYTES,
            "reference_host_available_memory_bytes": LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES,
            "runtime_eligible": large_pdf_eligible,
            "effective_max_bytes": int(
                api.max_pdf_bytes_per_document
                if large_pdf_eligible
                else api.max_bytes_per_document
            ),
            "unavailable_reason": large_pdf_reason,
        },
        # Legacy projection kept for older clients: per-file / request-byte
        # fields remain transport. max_active_sources is workspace capacity
        # when configured; otherwise null (do not alias transport file count).
        "source_limits": {
            "max_active_sources": (
                int(active_sources) if active_sources is not None else None
            ),
            "max_bytes_per_source": int(api.max_bytes_per_document),
            "max_active_source_bytes": int(api.max_total_upload_bytes),
        },
        "generation": {
            "enabled": bool(gen.enabled),
            "provider": str(gen.provider),
            "base_url": str(gen.base_url),
            "model": str(gen.model),
            "timeout_seconds": int(gen.timeout_seconds),
        },
        "authoring": {
            "enabled": bool(auth.enabled),
            "provider": str(auth.provider),
            "base_url": str(auth.base_url),
            "model": auth.model,
            "timeout_seconds": int(auth.timeout_seconds),
            "ready": bool(readiness.ready),
            "reason_codes": list(readiness.reason_codes),
            "api_key_configured": bool(auth.api_key),
        },
        "embedding": embedding_block,
    }
