"""Production Sentence Transformers ONNX CPU embedder (product adapter).

Binds accepted representation metadata / runtime_contract to the shared
``st_onnx_runtime`` substrate. Does not contain an independent ST/ONNX loader.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from offline_rag.core.ids import (
    RAW_QUERY_V1,
    SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT,
)
from offline_rag.dense.embedding_artifacts import RepresentationInspection
from offline_rag.dense.st_onnx_runtime import (
    FROZEN_ONNX_PROVIDER,
    FROZEN_ORT_INTER_OP_THREADS,
    FROZEN_ORT_INTRA_OP_THREADS,
    POSITION_IDS_SEMANTICS,
    StOnnxRuntimeError,
    apply_seneca_onnx_position_ids_compat,
    build_qwen3_direct_forward_position_ids,
    create_st_onnx_model,
    encode_documents,
    encode_query,
    install_seneca_onnx_position_ids_compat,
)


class OnnxEmbedderError(StOnnxRuntimeError):
    """Fail-closed ONNX embedding errors (product surface)."""


class SentenceTransformersOnnxEmbedder:
    """Thin product adapter over the shared ST/ONNX execution core."""

    adapter_contract = SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT

    def __init__(
        self,
        *,
        representation: RepresentationInspection,
        model_id: str,
        model_revision: str,
        dimension: int = 1024,
        normalize: bool = True,
        batch_size: int = 32,
        query_text_contract: str = RAW_QUERY_V1,
    ) -> None:
        if representation.representation_id != "onnx_fp32_v1":
            raise OnnxEmbedderError(
                f"SentenceTransformersOnnxEmbedder requires onnx_fp32_v1, got "
                f"{representation.representation_id}"
            )
        if representation.instance_path is None:
            raise OnnxEmbedderError("onnx representation instance_path is required")
        if query_text_contract != RAW_QUERY_V1:
            raise OnnxEmbedderError(
                f"P1 ONNX embedder only qualifies {RAW_QUERY_V1}; got "
                f"{query_text_contract}"
            )
        self.representation = representation
        self.model_path = Path(representation.instance_path).resolve()
        self.model_id = model_id
        self.model_revision = model_revision
        self.dimension = dimension
        self.normalize = normalize
        self.batch_size = batch_size
        self.query_text_contract = query_text_contract
        self.device = "cpu"
        self.resolved_device = "cpu"
        self.resolved_precision = "fp32"
        self.provider = FROZEN_ONNX_PROVIDER
        self.graph_file_name = representation.graph_file_name or "onnx/model.onnx"
        contract = (
            dict(representation.qualification_spec.runtime_contract)
            if representation.qualification_spec is not None
            else {}
        )
        required_inputs = contract.get("required_onnx_inputs")
        if not isinstance(required_inputs, list) or not required_inputs:
            raise OnnxEmbedderError(
                "onnx representation missing package runtime_contract."
                "required_onnx_inputs"
            )
        self.required_onnx_inputs = tuple(str(x) for x in required_inputs)
        self._model: Any | None = None
        self.position_ids_compat: dict[str, Any] | None = None

    def ensure_initialized(self) -> Any:
        """Materialize the ST/ORT session via the shared core. Idempotent."""
        return self._load()

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            model, compat = create_st_onnx_model(
                self.model_path,
                file_name=self.graph_file_name,
                required_onnx_inputs=self.required_onnx_inputs,
            )
        except StOnnxRuntimeError as exc:
            raise OnnxEmbedderError(str(exc)) from exc
        self.position_ids_compat = compat
        self._model = model
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self.ensure_initialized()
        try:
            return encode_documents(
                model,
                texts,
                batch_size=self.batch_size,
                normalize=self.normalize,
                dimension=self.dimension,
            )
        except StOnnxRuntimeError as exc:
            raise OnnxEmbedderError(str(exc)) from exc

    def embed_query(self, text: str) -> list[float]:
        model = self.ensure_initialized()
        try:
            return encode_query(
                model,
                text,
                normalize=self.normalize,
                dimension=self.dimension,
            )
        except StOnnxRuntimeError as exc:
            raise OnnxEmbedderError(str(exc)) from exc

    def release(self) -> None:
        self._model = None


__all__ = [
    "FROZEN_ONNX_PROVIDER",
    "FROZEN_ORT_INTER_OP_THREADS",
    "FROZEN_ORT_INTRA_OP_THREADS",
    "POSITION_IDS_SEMANTICS",
    "OnnxEmbedderError",
    "SentenceTransformersOnnxEmbedder",
    "apply_seneca_onnx_position_ids_compat",
    "build_qwen3_direct_forward_position_ids",
    "install_seneca_onnx_position_ids_compat",
]
