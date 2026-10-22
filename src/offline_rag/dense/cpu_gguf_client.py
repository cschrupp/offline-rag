"""HTTP client for llama.cpp OpenAI-compatible /v1/embeddings (CPU-GGUF-01).

Authority: S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-AUTH-001

Uses httpx (already a Seneca dependency). No OpenAI SDK.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import httpx

from offline_rag.dense.cpu_gguf_feasibility import (
    EXPECTED_DIMENSION,
    FROZEN_BATCH_SIZE,
    FROZEN_NORMALIZE,
)


def _finite(vec: Sequence[float]) -> bool:
    return all(math.isfinite(float(x)) for x in vec)


def _l2(vec: Sequence[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def _normalize_vector(vec: list[float]) -> list[float]:
    n = _l2(vec)
    if n <= 0.0:
        return vec
    return [float(x) / n for x in vec]


class LlamaCppEmbeddingClient:
    """Application-level embedder over llama-server ``POST /v1/embeddings``."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float = 600.0,
        request_batch_size: int = FROZEN_BATCH_SIZE,
        require_normalize: bool = FROZEN_NORMALIZE,
        expected_dimension: int = EXPECTED_DIMENSION,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.request_batch_size = int(request_batch_size)
        self.require_normalize = bool(require_normalize)
        self.expected_dimension = int(expected_dimension)
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> LlamaCppEmbeddingClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        response = self._client.get(f"{self.base_url}/health")
        response.raise_for_status()
        try:
            return dict(response.json())
        except Exception:  # noqa: BLE001
            return {"status_code": response.status_code, "text": response.text[:500]}

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for start in range(0, len(texts), self.request_batch_size):
            chunk = list(texts[start : start + self.request_batch_size])
            out.extend(self._embed_batch(chunk))
        if len(out) != len(texts):
            raise RuntimeError(
                f"embed_documents length mismatch: got {len(out)} expected {len(texts)}"
            )
        return out

    def embed_query(self, text: str) -> list[float]:
        rows = self._embed_batch([text])
        if len(rows) != 1:
            raise RuntimeError(f"embed_query expected 1 vector, got {len(rows)}")
        return rows[0]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"input": texts}
        response = self._client.post(
            f"{self.base_url}/v1/embeddings",
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        data = body.get("data")
        if not isinstance(data, list):
            raise ValueError("embeddings response missing data list")
        if len(data) != len(texts):
            raise ValueError(
                f"embeddings count mismatch: got {len(data)} expected {len(texts)}"
            )

        by_index: dict[int, list[float]] = {}
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("embeddings data item must be an object")
            if "index" not in item:
                raise ValueError("embeddings data item missing index")
            idx = int(item["index"])
            if idx in by_index:
                raise ValueError(f"duplicate embeddings index {idx}")
            emb = item.get("embedding")
            if not isinstance(emb, list):
                raise ValueError(f"embeddings[{idx}] missing embedding list")
            vec = [float(x) for x in emb]
            if len(vec) != self.expected_dimension:
                raise ValueError(
                    f"embeddings[{idx}] dim {len(vec)} != {self.expected_dimension}"
                )
            if not _finite(vec):
                raise ValueError(f"embeddings[{idx}] contains non-finite values")
            if self.require_normalize:
                vec = _normalize_vector(vec)
                n = _l2(vec)
                if not (0.99 <= n <= 1.01):
                    raise ValueError(
                        f"embeddings[{idx}] norm {n} outside normalize tolerance"
                    )
            by_index[idx] = vec

        missing = [i for i in range(len(texts)) if i not in by_index]
        if missing:
            raise ValueError(f"missing embeddings indices: {missing[:8]}")
        return [by_index[i] for i in range(len(texts))]


__all__ = ["LlamaCppEmbeddingClient"]
