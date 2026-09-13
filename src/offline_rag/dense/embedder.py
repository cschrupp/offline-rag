"""Embedder protocol and local implementations."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    MODEL_QUERY_PROMPT_V1,
    RAW_QUERY_V1,
    SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT,
)
from offline_rag.dense.provision import (
    require_embedding_artifacts,
    resolve_embedding_model_dir,
)
from offline_rag.dense.query_text import (
    MODEL_QUERY_PROMPT_NAME,
    resolve_query_text_contract,
)


class Embedder(Protocol):
    """Project-owned embedding interface."""

    model_id: str
    model_revision: str
    dimension: int
    normalize: bool
    adapter_contract: str
    query_text_contract: str

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document/passage texts."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector
    return [value / norm for value in vector]


def _digest_vector(text: str, *, dimension: int) -> list[float]:
    """Map text to a deterministic float vector via expanding SHA-256 digests."""
    if dimension <= 0:
        raise ValueError("dimension must be positive")
    values: list[float] = []
    seed = text.encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    offset = 0
    while len(values) < dimension:
        if offset >= len(digest):
            digest = hashlib.sha256(digest).digest()
            offset = 0
        # Map byte [0, 255] into [-1, 1].
        values.append((digest[offset] / 127.5) - 1.0)
        offset += 1
    return values


class FakeEmbedder:
    """Deterministic digest-based embedder for tests and CI (no Python hash())."""

    model_id = "fake"
    model_revision = "fake-v1"
    adapter_contract = "fake-embedder-v1"
    query_text_contract = RAW_QUERY_V1

    def __init__(
        self,
        *,
        dimension: int = 8,
        normalize: bool = True,
        query_text_contract: str = RAW_QUERY_V1,
    ) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        if query_text_contract != RAW_QUERY_V1:
            raise EmbedderError(
                f"FakeEmbedder only supports {RAW_QUERY_V1}; got {query_text_contract}"
            )
        self.dimension = dimension
        self.normalize = normalize
        self.query_text_contract = query_text_contract

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def _embed_one(self, text: str) -> list[float]:
        vector = _digest_vector(text, dimension=self.dimension)
        if self.normalize:
            return _l2_normalize(vector)
        return vector


class SentenceTransformersEmbedder:
    """Load SentenceTransformers exclusively from a provisioned local directory."""

    adapter_contract = SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT

    def __init__(
        self,
        *,
        model_path: Path,
        model_id: str,
        model_revision: str,
        dimension: int,
        normalize: bool = True,
        device: str = "cpu",
        batch_size: int = 32,
        query_instruction: str | None = None,
        document_instruction: str | None = None,
        expected_dimension: int | None = None,
        query_text_contract: str = RAW_QUERY_V1,
    ) -> None:
        self.model_path = Path(model_path).expanduser().resolve()
        self.model_id = model_id
        self.model_revision = model_revision
        self.dimension = dimension
        self.normalize = normalize
        self.device = device
        self.batch_size = batch_size
        self.query_instruction = query_instruction
        self.document_instruction = document_instruction
        self.query_text_contract = query_text_contract
        self._model = None
        if (
            query_text_contract == MODEL_QUERY_PROMPT_V1
            and query_instruction is not None
        ):
            raise EmbedderError(
                f"{MODEL_QUERY_PROMPT_V1} cannot be combined with "
                "indexing.embedding.query_instruction; use the model registered "
                f"{MODEL_QUERY_PROMPT_NAME!r} prompt only"
            )
        require_embedding_artifacts(
            self.model_path,
            expected_model_id=model_id,
            expected_revision=model_revision,
            expected_dimension=expected_dimension or dimension,
        )

    def _load(self):
        if self._model is not None:
            return self._model
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            str(self.model_path),
            device=self.device,
            trust_remote_code=False,
            local_files_only=True,
        )
        return self._model

    def _require_model_query_prompt(self, model) -> None:
        prompts = getattr(model, "prompts", None)
        if not isinstance(prompts, dict) or MODEL_QUERY_PROMPT_NAME not in prompts:
            raise EmbedderError(
                f"{MODEL_QUERY_PROMPT_V1} requires the provisioned embedding model "
                f"to expose prompts[{MODEL_QUERY_PROMPT_NAME!r}]; none found "
                f"(model_id={self.model_id})"
            )
        value = prompts[MODEL_QUERY_PROMPT_NAME]
        if not isinstance(value, str):
            raise EmbedderError(
                f"{MODEL_QUERY_PROMPT_V1}: prompts[{MODEL_QUERY_PROMPT_NAME!r}] "
                f"must be a string (got {type(value).__name__})"
            )

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payloads = [
            f"{self.document_instruction}{text}" if self.document_instruction else text
            for text in texts
        ]
        model = self._load()
        vectors = model.encode(
            list(payloads),
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [self._coerce_vector(row.tolist()) for row in vectors]

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        if self.query_text_contract == MODEL_QUERY_PROMPT_V1:
            self._require_model_query_prompt(model)
            vector = model.encode(
                text,
                prompt_name=MODEL_QUERY_PROMPT_NAME,
                normalize_embeddings=self.normalize,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return self._coerce_vector(vector.tolist())

        # raw-query-v1: optional legacy string prefix, then bare encode.
        payload = f"{self.query_instruction}{text}" if self.query_instruction else text
        vector = model.encode(
            payload,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return self._coerce_vector(vector.tolist())

    def _coerce_vector(self, values: list[float]) -> list[float]:
        if len(values) < self.dimension:
            values = values + [0.0] * (self.dimension - len(values))
        elif len(values) > self.dimension:
            values = values[: self.dimension]
        if self.normalize:
            return _l2_normalize(values)
        return values


class EmbedderError(RuntimeError):
    pass


def make_embedder(settings: AppSettings) -> Embedder:
    """Construct the configured embedder (fake never silently substitutes)."""
    emb = settings.indexing.embedding
    query = settings.dense.query_text
    query_contract = resolve_query_text_contract(
        strategy=query.strategy,
        contract_version=query.contract_version,
    )
    if emb.implementation == "fake":
        if query_contract != RAW_QUERY_V1:
            raise EmbedderError(
                f"{query_contract} requires sentence_transformers with a registered "
                f"{MODEL_QUERY_PROMPT_NAME!r} prompt; fake embedder cannot satisfy it"
            )
        return FakeEmbedder(
            dimension=emb.dimension,
            normalize=emb.normalize,
            query_text_contract=query_contract,
        )
    if emb.implementation != "sentence_transformers":
        raise EmbedderError(f"unsupported embedding implementation: {emb.implementation}")

    model_dir = resolve_embedding_model_dir(
        embedding_artifacts_root=settings.paths.embedding_artifacts,
        model_path=settings.dense.model_path,
    )
    return SentenceTransformersEmbedder(
        model_path=model_dir,
        model_id=emb.model_id,
        model_revision=emb.revision,
        dimension=emb.dimension,
        normalize=emb.normalize,
        device=emb.device,
        batch_size=emb.batch_size,
        query_instruction=emb.query_instruction,
        document_instruction=emb.document_instruction,
        expected_dimension=emb.dimension,
        query_text_contract=query_contract,
    )
