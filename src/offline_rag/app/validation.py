"""Bounded validation-error projection into D08 request_invalid envelopes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from offline_rag.app.errors import AppError, ErrorCode

_MAX_FIELDS = 32
_MAX_LOC_PARTS = 16
_MAX_MSG_CHARS = 200
_MAX_TYPE_CHARS = 64

# Field names that must never be echoed via validation details.
_SECRET_LOC_TOKENS = frozenset(
    {
        "api_key",
        "authorization",
        "password",
        "secret",
        "token",
        "credential",
        "private_key",
    }
)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _loc_parts(loc: object) -> list[str]:
    if not isinstance(loc, (list, tuple)):
        return []
    parts: list[str] = []
    for item in loc[:_MAX_LOC_PARTS]:
        parts.append(str(item))
    return parts


def _loc_is_secret_bearing(parts: Sequence[str]) -> bool:
    for part in parts:
        token = part.lower().replace("-", "_")
        if token in _SECRET_LOC_TOKENS or any(
            secret in token for secret in _SECRET_LOC_TOKENS
        ):
            return True
    return False


def project_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Allowlisted projection: loc / msg / type only — never input values."""
    fields: list[dict[str, str | list[str]]] = []
    for err in list(errors)[:_MAX_FIELDS]:
        loc_parts = _loc_parts(err.get("loc"))
        msg = _truncate(str(err.get("msg", "invalid")), _MAX_MSG_CHARS)
        err_type = _truncate(str(err.get("type", "value_error")), _MAX_TYPE_CHARS)
        if _loc_is_secret_bearing(loc_parts):
            msg = "Invalid value"
        fields.append({"loc": loc_parts, "msg": msg, "type": err_type})
    return {"fields": fields}


def app_error_from_validation_errors(
    errors: Sequence[Mapping[str, Any]],
    *,
    message: str = "Request validation failed",
) -> AppError:
    """Build the canonical request_invalid AppError for framework validation."""
    return AppError(
        code=ErrorCode.REQUEST_INVALID,
        message=message,
        details=project_validation_errors(errors),
    )
