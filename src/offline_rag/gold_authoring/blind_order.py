"""blind-order-v1: deterministic retrieval-blind pass execution orders."""

from __future__ import annotations

import hashlib
import json

from offline_rag.gold_authoring.contracts import BLIND_ORDER_CONTRACT, PASS_1, PASS_2
from offline_rag.gold_authoring.sampling import SamplingPRNG


class BlindOrderError(ValueError):
    """Invalid blind-order inputs."""


def _seed_integer(material: list[str]) -> int:
    encoded = json.dumps(material, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _deterministic_shuffle(ids: list[str], *, seed: int) -> list[str]:
    items = list(ids)
    rng = SamplingPRNG(seed)
    n = len(items)
    for i in range(n - 1, 0, -1):
        j = rng.randint_inclusive(0, i)
        items[i], items[j] = items[j], items[i]
    return items


def _rotate_left(ids: list[str], positions: int = 1) -> list[str]:
    if not ids:
        return []
    k = positions % len(ids)
    if k == 0:
        return list(ids)
    return ids[k:] + ids[:k]


def derive_blind_orders(
    *,
    authoring_run_id: str,
    draft_case_id: str,
    candidate_ids: list[str],
) -> tuple[list[str], list[str]]:
    """Return (pass_1_order, pass_2_order) under blind-order-v1."""
    if not candidate_ids:
        raise BlindOrderError("candidate membership is empty")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise BlindOrderError("duplicate candidate chunk_ids")

    base = sorted(candidate_ids)
    seed1 = _seed_integer(
        [BLIND_ORDER_CONTRACT, authoring_run_id, draft_case_id, PASS_1]
    )
    seed2 = _seed_integer(
        [BLIND_ORDER_CONTRACT, authoring_run_id, draft_case_id, PASS_2]
    )
    order1 = _deterministic_shuffle(base, seed=seed1)
    order2 = _deterministic_shuffle(base, seed=seed2)
    if len(base) > 1 and order1 == order2:
        order2 = _rotate_left(order2, 1)
    if len(base) > 1 and order1 == order2:
        raise BlindOrderError("unable to derive distinct pass orders")
    if set(order1) != set(base) or set(order2) != set(base):
        raise BlindOrderError("blind order membership mismatch")
    if len(order1) != len(base) or len(order2) != len(base):
        raise BlindOrderError("blind order cardinality mismatch")
    return order1, order2


def blind_order_contract_id() -> str:
    return BLIND_ORDER_CONTRACT
