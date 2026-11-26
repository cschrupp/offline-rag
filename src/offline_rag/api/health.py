"""Liveness / readiness probes (D09)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Request, Response

from offline_rag.app.runtime import ApplicationRuntime

router = APIRouter(tags=["health"])


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise TypeError("application runtime is not configured")
    return runtime


@router.get("/health")
@router.get("/health/live")
def health_live(request: Request) -> dict[str, str]:
    """Cheap process liveness — no model/generator/storage work."""
    _ = _runtime(request)  # ensure runtime object exists; do not touch resources
    return {"status": "live"}


@router.get("/health/ready")
def health_ready(request: Request) -> dict[str, str]:
    """Cached runtime readiness — no model load or generator probe."""
    runtime = _runtime(request)
    runtime.require_ready()
    return {"status": "ready"}


@router.get("/v1/runtime/revision")
def runtime_revision(response: Response) -> dict[str, str | None]:
    """Report the release revision without exposing local file paths."""
    revision = os.environ.get("SENECA_SOURCE_SHA")
    if revision is None:
        try:
            manifest = json.loads(
                Path(".seneca-release.json").read_text(encoding="utf-8")
            )
            revision = (
                manifest.get("source_sha") if isinstance(manifest, dict) else None
            )
        except OSError, ValueError:
            revision = None
    response.headers["Cache-Control"] = "no-store"
    return {
        "source_sha": revision
        if isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision)
        else None
    }
