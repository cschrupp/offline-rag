"""Strict adversarial fixture loader (OD-13-3 / OD-13-6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from offline_rag.evaluation.security_13.contracts import (
    DESIGN_AUTHORITY_SHA_13,
    SLICE13_BASELINE_SHA,
    AdversarialFixtureV1,
    SecurityEvalError,
)
from offline_rag.evaluation.security_13.identity import compute_fixture_identity_hash
from offline_rag.evaluation.security_13.registry import require_known_invariant_ids


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SecurityEvalError(f"failed to read fixture JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SecurityEvalError(f"fixture root must be a JSON object: {path}")
    return payload


def validate_adversarial_fixture(
    payload: dict[str, Any],
    *,
    require_design_authority_sha: str = DESIGN_AUTHORITY_SHA_13,
    require_slice13_baseline_sha: str = SLICE13_BASELINE_SHA,
) -> AdversarialFixtureV1:
    """Validate fixture schema and semantic identity; fail closed on mismatch."""
    try:
        fixture = AdversarialFixtureV1.model_validate(payload)
    except ValidationError as exc:
        raise SecurityEvalError(f"adversarial fixture schema validation failed: {exc}") from exc

    require_known_invariant_ids(list(fixture.expected_invariant_ids))

    if fixture.slice13_baseline_sha != require_slice13_baseline_sha:
        raise SecurityEvalError(
            "slice13_baseline_sha mismatch: "
            f"expected {require_slice13_baseline_sha!r}, "
            f"got {fixture.slice13_baseline_sha!r}"
        )
    if fixture.design_authority_sha != require_design_authority_sha:
        raise SecurityEvalError(
            "design_authority_sha mismatch: "
            f"expected {require_design_authority_sha!r}, "
            f"got {fixture.design_authority_sha!r}"
        )

    recomputed = compute_fixture_identity_hash(fixture)
    if fixture.fixture_identity_hash != recomputed:
        raise SecurityEvalError(
            "fixture_identity_hash mismatch: "
            f"declared {fixture.fixture_identity_hash!r}, recomputed {recomputed!r}"
        )
    return fixture


def load_adversarial_fixture(path: Path | str) -> AdversarialFixtureV1:
    """Load and fail-closed-validate one adversarial fixture file."""
    return validate_adversarial_fixture(_load_json_object(Path(path)))
