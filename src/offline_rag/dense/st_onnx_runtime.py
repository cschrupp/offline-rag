"""Shared Sentence-Transformers ONNX CPU execution substrate.

Single authoritative physical implementation for ST/ONNX model construction and
encoding. Production adapters and scientific harnesses must call this module
rather than maintaining parallel loaders.

Contains no campaign authority, timing gates, evidence writing, graph-science
policy, or experiment-specific artifact selection.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

FROZEN_ORT_INTRA_OP_THREADS = 8
FROZEN_ORT_INTER_OP_THREADS = 1
FROZEN_ONNX_PROVIDER = "CPUExecutionProvider"
POSITION_IDS_SEMANTICS = "qwen3_direct_forward_zero_based_arange"


class StOnnxRuntimeError(RuntimeError):
    """Fail-closed ST/ONNX execution errors."""


def ort_session_options() -> Any:
    """Frozen ORT session options for the accepted CPU ONNX profile."""
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = FROZEN_ORT_INTRA_OP_THREADS
    so.inter_op_num_threads = FROZEN_ORT_INTER_OP_THREADS
    return so


def st_onnx_model_kwargs(
    *,
    file_name: str | None = None,
    export: bool = False,
) -> dict[str, Any]:
    """SentenceTransformer model_kwargs for backend=onnx + CPUExecutionProvider."""
    kwargs: dict[str, Any] = {
        "provider": FROZEN_ONNX_PROVIDER,
        "session_options": ort_session_options(),
    }
    if export:
        kwargs["export"] = True
    if file_name is not None:
        kwargs["file_name"] = file_name
    return kwargs


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
    """Inject position_ids when required by the input contract and absent."""
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
    raise StOnnxRuntimeError(
        "unable to locate ORT/transformers model on SentenceTransformer[0] "
        f"for position_ids compat (type={type(module0)!r})"
    )


def install_seneca_onnx_position_ids_compat(
    st_model: Any,
    *,
    required_onnx_inputs: Sequence[str],
) -> dict[str, Any]:
    """Install position_ids compat from an explicit required-inputs contract.

    Callers own how ``required_onnx_inputs`` is obtained (package runtime_contract
    in production; graph inspection in scientific harnesses). This function never
    imports ``onnx`` or parses graphs.
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
            "and absent; never attention_mask.cumsum; driven by required_onnx_inputs"
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
    ort_model._seneca_onnx_position_ids_required_inputs = list(required_inputs)
    record["source"] = "generated_by_seneca_adapter"
    record["adapter_installed"] = True
    return record


def create_st_onnx_model(
    model_dir: Path | str,
    *,
    file_name: str,
    required_onnx_inputs: Sequence[str],
    export: bool = False,
    trust_remote_code: bool = False,
    local_files_only: bool = True,
) -> tuple[Any, dict[str, Any]]:
    """Construct the ST/ONNX model and install position_ids compat.

    This is the sole physical ST/ONNX construction path. Callers must supply
    ``required_onnx_inputs`` explicitly (package contract or scientific inspection).
    """
    from sentence_transformers import SentenceTransformer

    root = Path(model_dir).expanduser().resolve()
    onnx_path = root / file_name
    if not export and not onnx_path.is_file():
        raise StOnnxRuntimeError(f"ONNX graph missing: {onnx_path}")
    model = SentenceTransformer(
        str(root),
        backend="onnx",
        device="cpu",
        trust_remote_code=trust_remote_code,
        local_files_only=local_files_only,
        model_kwargs=st_onnx_model_kwargs(file_name=file_name, export=export),
    )
    position_ids_compat = install_seneca_onnx_position_ids_compat(
        model,
        required_onnx_inputs=required_onnx_inputs,
    )
    return model, position_ids_compat


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector
    return [value / norm for value in vector]


def _finite(vec: Sequence[float]) -> bool:
    return all(math.isfinite(float(x)) for x in vec)


def _vector_norm(vec: Sequence[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def coerce_embedding_vector(
    values: list[float],
    *,
    dimension: int,
    normalize: bool,
) -> list[float]:
    """Fail-closed dimension / finiteness / optional L2 normalization."""
    if len(values) != dimension:
        raise StOnnxRuntimeError(
            f"ONNX embedding dimension mismatch: expected {dimension}, "
            f"got {len(values)} (fail closed; no pad/truncate)"
        )
    if not _finite(values):
        raise StOnnxRuntimeError("ONNX embedding produced non-finite values")
    if normalize:
        values = _l2_normalize(values)
        if abs(_vector_norm(values) - 1.0) > 1e-3:
            raise StOnnxRuntimeError("ONNX embedding failed normalization contract")
    return values


def encode_documents(
    model: Any,
    texts: Sequence[str],
    *,
    batch_size: int,
    normalize: bool,
    dimension: int | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    vectors = model.encode(
        list(texts),
        batch_size=batch_size,
        normalize_embeddings=normalize,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    out: list[list[float]] = []
    for row in vectors:
        values = [float(x) for x in row.tolist()]
        if dimension is not None:
            values = coerce_embedding_vector(
                values, dimension=dimension, normalize=normalize
            )
        elif normalize:
            values = _l2_normalize(values)
        out.append(values)
    return out


def encode_query(
    model: Any,
    text: str,
    *,
    normalize: bool,
    dimension: int | None = None,
    prompt_name: str | None = None,
) -> list[float]:
    if prompt_name is not None:
        vector = model.encode(
            text,
            prompt_name=prompt_name,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    else:
        vector = model.encode(
            text,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    values = [float(x) for x in vector.tolist()]
    if dimension is not None:
        return coerce_embedding_vector(
            values, dimension=dimension, normalize=normalize
        )
    if normalize:
        return _l2_normalize(values)
    return values


__all__ = [
    "FROZEN_ONNX_PROVIDER",
    "FROZEN_ORT_INTER_OP_THREADS",
    "FROZEN_ORT_INTRA_OP_THREADS",
    "POSITION_IDS_SEMANTICS",
    "StOnnxRuntimeError",
    "apply_seneca_onnx_position_ids_compat",
    "build_qwen3_direct_forward_position_ids",
    "coerce_embedding_vector",
    "create_st_onnx_model",
    "encode_documents",
    "encode_query",
    "install_seneca_onnx_position_ids_compat",
    "ort_session_options",
    "st_onnx_model_kwargs",
]
