"""Canonical serialization / identity helpers for Slice 14A."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from offline_rag.evaluation.performance_14.contracts import (
    PERFORMANCE_BENCHMARK_CASE_V1,
    PERFORMANCE_BENCHMARK_RUN_MANIFEST_V1,
    PERFORMANCE_BENCHMARK_SUITE_V1,
    PERFORMANCE_MACHINE_PROFILE_V1,
    Performance14Error,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkRunManifestV1,
    PerformanceBenchmarkSuiteV1,
    PerformanceMachineProfileV1,
)

_JSON_PRIMITIVES = (str, int, float, bool, type(None))


def _assert_json_canonical(value: Any, *, path: str = "$") -> None:
    """Fail closed unless ``value`` is JSON-canonical (no silent stringification)."""
    if isinstance(value, _JSON_PRIMITIVES):
        if isinstance(value, float) and not math.isfinite(value):
            raise Performance14Error(
                f"non-finite float is not JSON-canonical at {path}"
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise Performance14Error(
                    f"mapping keys must be strings at {path} (got {type(key)!r})"
                )
            _assert_json_canonical(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_canonical(item, path=f"{path}[{index}]")
        return
    raise Performance14Error(
        f"unsupported identity value type {type(value)!r} at {path}; "
        "canonical JSON accepts only object/array/string/number/bool/null"
    )


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    """UTF-8 JSON with sorted keys and stable separators (no pretty-print).

    Rejects sets, custom objects, and other non-JSON values instead of using
    ``default=str`` (which would invent implementation-dependent serialization).
    """
    _assert_json_canonical(payload)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return encoded.encode("utf-8")


def _prefixed_hash(prefix: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"{prefix}{digest}"


def suite_semantic_payload(suite: PerformanceBenchmarkSuiteV1) -> dict[str, Any]:
    """Identity-bearing suite payload (excludes suite_identity_hash)."""
    raw = suite.model_dump(mode="json")
    raw.pop("suite_identity_hash", None)
    raw["contract"] = PERFORMANCE_BENCHMARK_SUITE_V1
    raw["case_ids"] = sorted(raw["case_ids"])
    raw["variants"] = sorted(raw["variants"])
    return raw


def compute_suite_identity_hash(suite: PerformanceBenchmarkSuiteV1) -> str:
    """Return ``perfsuite_<sha256>`` for a validated suite body."""
    return _prefixed_hash("perfsuite_", suite_semantic_payload(suite))


def case_semantic_payload(case: PerformanceBenchmarkCaseV1) -> dict[str, Any]:
    """Identity-bearing case payload (excludes observations and derived stats)."""
    return {
        "contract": PERFORMANCE_BENCHMARK_CASE_V1,
        "case_kind": case.case_kind,
        "benchmark_level": case.benchmark_level,
        "stage_or_path": case.stage_or_path,
        "subject_identity": case.subject_identity,
        "variant": case.variant,
        "cold_warm": case.cold_warm,
    }


def compute_case_identity_hash(case: PerformanceBenchmarkCaseV1) -> str:
    """Return ``perfcase_<sha256>`` (excludes observations)."""
    return _prefixed_hash("perfcase_", case_semantic_payload(case))


def machine_semantic_payload(profile: PerformanceMachineProfileV1) -> dict[str, Any]:
    raw = profile.model_dump(mode="json")
    raw["contract"] = PERFORMANCE_MACHINE_PROFILE_V1
    return raw


def compute_machine_profile_hash(profile: PerformanceMachineProfileV1) -> str:
    """Return ``perfhost_<sha256>`` for a machine profile body."""
    return _prefixed_hash("perfhost_", machine_semantic_payload(profile))


def compute_config_identity_hash(config_payload: Mapping[str, Any]) -> str:
    """Return ``perfcfg_<sha256>`` for an effective configuration mapping."""
    return _prefixed_hash("perfcfg_", dict(config_payload))


def run_semantic_payload(manifest: PerformanceBenchmarkRunManifestV1) -> dict[str, Any]:
    """Pre-measurement run identity payload (includes nonce for legitimate reruns).

    Excludes terminalization fields that must not flip identity after execution:
    ``run_identity_hash``, embedded ``machine_profile`` body, and ``run_status``.
    ``machine_profile_id`` remains identity-bearing.
    """
    raw = manifest.model_dump(mode="json")
    raw.pop("run_identity_hash", None)
    raw.pop("machine_profile", None)
    raw.pop("run_status", None)
    raw["contract"] = PERFORMANCE_BENCHMARK_RUN_MANIFEST_V1
    return raw


def compute_run_identity_hash(manifest: PerformanceBenchmarkRunManifestV1) -> str:
    """Return ``perfrun_<sha256>`` for a concrete execution manifest + nonce."""
    if not manifest.run_nonce:
        raise ValueError("run_nonce is required to compute perfrun_ identity")
    return _prefixed_hash("perfrun_", run_semantic_payload(manifest))
