"""Deterministic GAP-16G-02 sampling-seed derivation."""

from __future__ import annotations

import hashlib


SEED_CONTRACT = "baseline-bootstrap-sampling-seed-v1"


def derive_bootstrap_sampling_seed(operation_id: str) -> int:
    """Return ``0 <= seed < 2**63`` from the durable operation identity."""
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError("operation_id required for seed derivation")
    material = f"{SEED_CONTRACT}|{operation_id}"
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[0:8], "big") % (2**63)
