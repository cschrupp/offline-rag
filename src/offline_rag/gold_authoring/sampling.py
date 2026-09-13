"""Deterministic source sampling (source-sampling-random-v1)."""

from __future__ import annotations

from dataclasses import dataclass

from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.gold_authoring.contracts import SAMPLING_CONTRACT


class SamplingError(ValueError):
    """Invalid sampling request (count / population)."""


@dataclass(frozen=True, slots=True)
class EligibleChild:
    chunk_id: str
    document_id: str
    section_path: tuple[str, ...]
    text: str


def is_eligible_proposal_seed(chunk: Chunk) -> bool:
    """9B-2 eligibility: child, non-heading, nonempty text."""
    if chunk.kind != ChunkKind.CHILD:
        return False
    if chunk.content_type == "heading":
        return False
    if not str(chunk.text).strip():
        return False
    return True


def build_eligible_population(chunks: list[Chunk]) -> list[EligibleChild]:
    eligible = [
        EligibleChild(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            section_path=tuple(chunk.section_path),
            text=chunk.text,
        )
        for chunk in chunks
        if is_eligible_proposal_seed(chunk)
    ]
    eligible.sort(key=lambda item: item.chunk_id)
    return eligible


class SamplingPRNG:
    """Code-owned SplitMix64 PRNG for source-sampling-random-v1."""

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = int(seed) & 0xFFFFFFFFFFFFFFFF
        if self._state == 0:
            self._state = 0x9E3779B97F4A7C15

    def next_u64(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self._state
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9 & 0xFFFFFFFFFFFFFFFF
        z = (z ^ (z >> 27)) * 0x94D049BB133111EB & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def randint_inclusive(self, lo: int, hi: int) -> int:
        if hi < lo:
            raise ValueError("hi must be >= lo")
        span = hi - lo + 1
        # Rejection sampling to avoid modulo bias for large spans.
        limit = (1 << 64) - ((1 << 64) % span)
        while True:
            value = self.next_u64()
            if value < limit:
                return lo + (value % span)


def sample_source_seeds(
    population: list[EligibleChild],
    *,
    count: int,
    seed: int,
) -> list[EligibleChild]:
    """Fisher–Yates shuffle then take first ``count`` (without replacement)."""
    if count <= 0:
        raise SamplingError(f"requested count must be > 0; got {count}")
    if count > len(population):
        raise SamplingError(
            f"requested count {count} exceeds eligible population {len(population)}"
        )
    # Canonicalize again so callers cannot leak incidental ordering.
    items = sorted(population, key=lambda item: item.chunk_id)
    rng = SamplingPRNG(seed)
    n = len(items)
    for i in range(n - 1, 0, -1):
        j = rng.randint_inclusive(0, i)
        items[i], items[j] = items[j], items[i]
    return items[:count]


def sampling_contract_id() -> str:
    return SAMPLING_CONTRACT
