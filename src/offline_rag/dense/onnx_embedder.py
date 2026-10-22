"""Production Sentence Transformers ONNX CPU embedder (P1).

Reproduces the accepted scientific ST-ONNX execution family. Does not import
scientific campaign executors.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from offline_rag.core.ids import (
    RAW_QUERY_V1,
    SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT,
)
from offline_rag.dense.embedding_artifacts import RepresentationInspection


class OnnxEmbedderError(RuntimeError):
    """Fail-closed ONNX embedding errors."""


FROZEN_ORT_INTRA_OP_THREADS = 8
FROZEN_ORT_INTER_OP_THREADS = 1
FROZEN_ONNX_PROVIDER = "CPUExecutionProvider"
POSITION_IDS_SEMANTICS = "qwen3_direct_forward_zero_based_arange"


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector
    return [value / norm for value in vector]


def _finite(vec: Sequence[float]) -> bool:
    return all(math.isfinite(float(x)) for x in vec)


def _vector_norm(vec: Sequence[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def build_qwen3_direct_forward_position_ids(input_ids: Any) -> Any:
    """Zero-based arange expanded to [batch, seq]; never attention_mask.cumsum."""
    import torch

    if input_ids is None:
        raise ValueError(
            "position_ids compat requires input_ids; refusing to guess positions"
        )
    if not isinstance(input_ids, torch.Tensor):
        raise TypeError(
            f"position_ids compat requires torch.Tensor input_ids, got {type(input_ids)}"
        )
    if input_ids.ndim != 2:
        raise ValueError(
            "position_ids compat requires rank-2 input_ids [batch, sequence]; "
            f"got shape={tuple(input_ids.shape)}"
        )
    batch_size, sequence_length = int(input_ids.shape[0]), int(input_ids.shape[1])
    if batch_size < 1 or sequence_length < 1:
        raise ValueError(
            "position_ids compat requires positive batch and sequence dimensions; "
            f"got shape=({batch_size}, {sequence_length})"
        )
    return (
        torch.arange(sequence_length, dtype=torch.long, device=input_ids.device)
        .unsqueeze(0)
        .expand(batch_size, -1)
        .contiguous()
    )


def apply_seneca_onnx_position_ids_compat(
    features: dict[str, Any],
    *,
    required_onnx_inputs: Sequence[str] | set[str],
) -> dict[str, Any]:
    required = set(required_onnx_inputs)
    if "position_ids" not in required:
        return features

    out = dict(features)
    supplied = out.get("position_ids")
    input_ids = out.get("input_ids")

    if supplied is not None:
        import torch

        if not isinstance(supplied, torch.Tensor):
            raise ValueError(
                "supplied position_ids must be a torch.Tensor when present"
            )
        if input_ids is None or not isinstance(input_ids, torch.Tensor):
            raise ValueError(
                "supplied position_ids present but input_ids missing/invalid; "
                "refusing shape check"
            )
        if input_ids.ndim != 2:
            raise ValueError(
                "input_ids must be rank-2 to validate supplied position_ids; "
                f"got shape={tuple(input_ids.shape)}"
            )
        expected = (int(input_ids.shape[0]), int(input_ids.shape[1]))
        observed = tuple(int(x) for x in supplied.shape)
        if observed != expected:
            raise ValueError(
                "supplied position_ids shape incompatible with input_ids: "
                f"position_ids={observed} input_ids={expected}"
            )
        return out

    out["position_ids"] = build_qwen3_direct_forward_position_ids(input_ids)
    return out


def _resolve_st_ort_feature_model(st_model: Any) -> Any:
    module0 = st_model[0]
    for attr in ("auto_model", "model", "_model"):
        cand = getattr(module0, attr, None)
        if cand is not None and hasattr(cand, "forward"):
            return cand
    raise OnnxEmbedderError(
        "unable to locate ORT/transformers model on SentenceTransformer[0] "
        f"for position_ids compat (type={type(module0)!r})"
    )


def install_seneca_onnx_position_ids_compat(
    st_model: Any,
    *,
    required_onnx_inputs: Sequence[str],
) -> dict[str, Any]:
    """Install position_ids compat from package-owned runtime_contract metadata.

    Does not import ``onnx`` or parse the graph at product runtime (F003).
    """
    required_inputs = [str(x) for x in required_onnx_inputs]
    requires = "position_ids" in set(required_inputs)
    record: dict[str, Any] = {
        "graph_requires_position_ids": requires,
        "required_onnx_inputs": list(required_inputs),
        "source": None,
        "semantics": POSITION_IDS_SEMANTICS,
        "dtype": "int64",
        "shape_policy": "batch_x_sequence",
        "overwrites_supplied_position_ids": False,
        "adapter_installed": False,
        "note": (
            "injects torch.arange(seq).unsqueeze(0).expand(batch,-1) when required "
            "and absent; never attention_mask.cumsum; driven by package "
            "runtime_contract.required_onnx_inputs (no production graph parse)"
        ),
    }
    if not requires:
        record["source"] = "noop_contract_does_not_require_position_ids"
        return record

    ort_model = _resolve_st_ort_feature_model(st_model)
    if getattr(ort_model, "_seneca_onnx_position_ids_compat", False):
        record["source"] = "generated_by_seneca_adapter"
        record["adapter_installed"] = True
        record["already_installed"] = True
        return record

    original_forward = ort_model.forward

    def _forward_with_position_ids_compat(*args: Any, **kwargs: Any) -> Any:
        features = dict(kwargs)
        patched = apply_seneca_onnx_position_ids_compat(
            features,
            required_onnx_inputs=required_inputs,
        )
        return original_forward(*args, **patched)

    ort_model.forward = _forward_with_position_ids_compat  # type: ignore[method-assign]
    ort_model._seneca_onnx_position_ids_compat = True
    record["source"] = "generated_by_seneca_adapter"
    record["adapter_installed"] = True
    return record


def _ort_session_options() -> Any:
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = FROZEN_ORT_INTRA_OP_THREADS
    so.inter_op_num_threads = FROZEN_ORT_INTER_OP_THREADS
    return so


class SentenceTransformersOnnxEmbedder:
    """ST backend=onnx CPUExecutionProvider FP32 embedder."""

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

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        from sentence_transformers import SentenceTransformer

        onnx_path = self.model_path / self.graph_file_name
        if not onnx_path.is_file():
            raise OnnxEmbedderError(f"ONNX graph missing: {onnx_path}")
        model = SentenceTransformer(
            str(self.model_path),
            backend="onnx",
            device="cpu",
            trust_remote_code=False,
            local_files_only=True,
            model_kwargs={
                "provider": FROZEN_ONNX_PROVIDER,
                "session_options": _ort_session_options(),
                "file_name": self.graph_file_name,
            },
        )
        self.position_ids_compat = install_seneca_onnx_position_ids_compat(
            model,
            required_onnx_inputs=self.required_onnx_inputs,
        )
        self._model = model
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [self._coerce_vector(row.tolist()) for row in vectors]

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        vector = model.encode(
            text,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return self._coerce_vector(vector.tolist())

    def _coerce_vector(self, values: list[float]) -> list[float]:
        if len(values) != self.dimension:
            raise OnnxEmbedderError(
                f"ONNX embedding dimension mismatch: expected {self.dimension}, "
                f"got {len(values)} (fail closed; no pad/truncate)"
            )
        if not _finite(values):
            raise OnnxEmbedderError("ONNX embedding produced non-finite values")
        if self.normalize:
            values = _l2_normalize(values)
            if abs(_vector_norm(values) - 1.0) > 1e-3:
                raise OnnxEmbedderError("ONNX embedding failed normalization contract")
        return values

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
