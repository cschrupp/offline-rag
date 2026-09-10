"""Qdrant Local persistent backend for dense indexing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from offline_rag.dense.backend import DensePointRecord, DenseSearchHit


class QdrantLocalBackend:
    """Persistent path-based Qdrant Local adapter (not :memory:)."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = Path(storage_path).expanduser().resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(path=str(self.storage_path))
        return self._client

    def collection_exists(self, collection_name: str) -> bool:
        client = self._get_client()
        existing = {item.name for item in client.get_collections().collections}
        return collection_name in existing

    def create_collection(
        self,
        collection_name: str,
        *,
        dimension: int,
        metric: str = "cosine",
    ) -> None:
        from qdrant_client.http import models

        if metric != "cosine":
            raise ValueError(f"unsupported dense metric for QdrantLocalBackend: {metric}")
        client = self._get_client()
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )

    def delete_collection(self, collection_name: str) -> None:
        if not self.collection_exists(collection_name):
            return
        self._get_client().delete_collection(collection_name=collection_name)

    def upsert(self, collection_name: str, points: list[DensePointRecord]) -> None:
        from qdrant_client.http import models

        if not points:
            return
        client = self._get_client()
        batch: list[models.PointStruct] = []
        for record in points:
            batch.append(
                models.PointStruct(
                    id=record.point_id,
                    vector=record.vector,
                    payload=dict(record.payload),
                )
            )
            if len(batch) >= 256:
                client.upsert(collection_name=collection_name, points=batch)
                batch.clear()
        if batch:
            client.upsert(collection_name=collection_name, points=batch)

    def count(self, collection_name: str) -> int:
        result = self._get_client().count(collection_name=collection_name, exact=True)
        return int(result.count)

    def search(
        self,
        collection_name: str,
        *,
        query_vector: list[float],
        top_k: int,
    ) -> list[DenseSearchHit]:
        client = self._get_client()
        # qdrant-client >=1.12 prefers query_points; keep search for compatibility.
        if hasattr(client, "query_points"):
            response = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=top_k,
                with_payload=True,
            )
            hits = response.points
        else:
            hits = client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=top_k,
                with_payload=True,
            )
        results: list[DenseSearchHit] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            results.append(
                DenseSearchHit(
                    point_id=str(hit.id),
                    score=float(hit.score),
                    payload=payload,
                )
            )
        return results

    def get_point(self, collection_name: str, point_id: str) -> DensePointRecord | None:
        client = self._get_client()
        records = client.retrieve(
            collection_name=collection_name,
            ids=[point_id],
            with_payload=True,
            with_vectors=True,
        )
        if not records:
            return None
        record = records[0]
        vector = record.vector
        if isinstance(vector, dict):
            # Named vectors are unsupported in Slice 3.
            vector = next(iter(vector.values()))
        values = list(vector) if vector is not None else []
        return DensePointRecord(
            point_id=str(record.id),
            vector=[float(item) for item in values],
            payload=dict(record.payload or {}),
        )

    def close(self) -> None:
        if self._client is not None:
            close = getattr(self._client, "close", None)
            if callable(close):
                close()
            self._client = None


def qdrant_distance_name(metric: str) -> str:
    if metric != "cosine":
        raise ValueError(f"unsupported metric: {metric}")
    return "Cosine"


def payload_without_nulls(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
