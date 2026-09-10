"""Project-owned dense index backend protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class DensePointRecord:
    """One dense vector point ready for materialization."""

    point_id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DenseSearchHit:
    """Backend-agnostic search hit (no SDK types)."""

    point_id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class DenseIndexBackend(Protocol):
    """Minimal vector-store adapter for dense indexing and retrieval."""

    def collection_exists(self, collection_name: str) -> bool:
        """Return whether ``collection_name`` exists."""

    def create_collection(
        self,
        collection_name: str,
        *,
        dimension: int,
        metric: str = "cosine",
    ) -> None:
        """Create an empty collection with the given vector params."""

    def delete_collection(self, collection_name: str) -> None:
        """Delete a collection if it exists."""

    def upsert(self, collection_name: str, points: list[DensePointRecord]) -> None:
        """Insert or replace points in ``collection_name``."""

    def count(self, collection_name: str) -> int:
        """Return exact point count for ``collection_name``."""

    def search(
        self,
        collection_name: str,
        *,
        query_vector: list[float],
        top_k: int,
    ) -> list[DenseSearchHit]:
        """Return ranked hits for ``query_vector``."""

    def get_point(self, collection_name: str, point_id: str) -> DensePointRecord | None:
        """Fetch one point by ID, or None if missing."""

    def close(self) -> None:
        """Release backend resources."""
