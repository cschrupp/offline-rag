"""CPU-ONNX-01 ONNX Runtime scientific executor (callable only when unlocked).

Authority: S16-K-D-POST-CPUOV-CPU-ONNX-FEASIBILITY-IMPLEMENTATION-AUTH-001

Implements local-pinned ST ONNX FP32 export, AVX2 QINT8 derivative quantization,
fail-closed ONNX INT8 identity inspection, 128-child screen timing, and
d2-retrieval-parity-v1 scaffolding.

Must not be invoked while ``EXECUTION_AUTHORIZED`` is False.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from offline_rag.core.ids import (
    MODEL_QUERY_PROMPT_V1,
    PLAIN_EMBEDDING_TEXT_CONTRACT,
    SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT,
    embedding_text_hash,
)
from offline_rag.dense.cpu_onnx_feasibility import (
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_SET_ID,
    EXPECTED_DIMENSION,
    EXPECTED_MODEL_ID,
    EXPECTED_MODEL_REVISION,
    EXPECTED_SCREEN_CHUNK_IDS_DIGEST,
    EXPERIMENT_ID,
    FROZEN_BATCH_SIZE,
    FROZEN_NORMALIZE,
    FROZEN_ONNX_PROVIDER,
    FROZEN_ORT_INTER_OP_THREADS,
    FROZEN_ORT_INTRA_OP_THREADS,
    FROZEN_QINT8_TARGET,
    IMPLEMENTATION_AUTH,
    PARITY_CONTRACT_ID,
    PARITY_THRESHOLDS,
    WeightFormat,
    parity_thresholds_pass,
    project_full_minutes,
)
from offline_rag.dense.cpu_onnx_harness import (
    find_onnx_model_files,
    hash_export_tree,
    select_parity_populations,
    select_screen_chunk_ids,
    sha256_text,
    verify_local_model_identity,
)
from offline_rag.dense.provision import require_embedding_artifacts
from offline_rag.dense.query_text import MODEL_QUERY_PROMPT_NAME
from offline_rag.dense.text import PlainEmbeddingTextBuilder
from offline_rag.domain.documents import Chunk
from offline_rag.retrieval.ranking_text import ranking_inputs_for_chunk


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _finite(vec: Sequence[float]) -> bool:
    return all(math.isfinite(float(x)) for x in vec)


def _l2(vec: Sequence[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def _normalize_vector(vec: list[float]) -> list[float]:
    n = _l2(vec)
    if n <= 0.0:
        return vec
    return [float(x) / n for x in vec]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch {len(a)} != {len(b)}")
    dot = sum(float(x) * float(y) for x, y in zip(a, b, strict=True))
    na = _l2(list(a))
    nb = _l2(list(b))
    if na == 0.0 or nb == 0.0:
        return float("nan")
    return float(dot / (na * nb))


def _ort_session_options() -> Any:
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = FROZEN_ORT_INTRA_OP_THREADS
    so.inter_op_num_threads = FROZEN_ORT_INTER_OP_THREADS
    return so


def _st_onnx_model_kwargs(
    *,
    export: bool = False,
    file_name: str | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "provider": FROZEN_ONNX_PROVIDER,
        "session_options": _ort_session_options(),
    }
    if export:
        kwargs["export"] = True
    if file_name is not None:
        kwargs["file_name"] = file_name
    return kwargs


def _relative_onnx_file_name(export_dir: Path, onnx_path: Path) -> str:
    return str(onnx_path.resolve().relative_to(export_dir.resolve())).replace("\\", "/")


def select_onnx_artifact_for_weight_format(
    *,
    export_dir: Path,
    weight_format: WeightFormat,
) -> tuple[Path, dict[str, Any]]:
    """Select ONNX file by observed graph quantization — never by filename alone."""
    identity = build_onnx_precision_identity(
        requested_weight_format=weight_format,
        export_dir=export_dir,
        quantization_target=FROZEN_QINT8_TARGET
        if weight_format == "qint8_avx2"
        else None,
    )
    inspections = list(identity["onnx_inspections"])
    if not inspections:
        raise FileNotFoundError(f"no ONNX inspections under {export_dir}")

    if weight_format == "qint8_avx2":
        verified = [
            i
            for i in inspections
            if (i.get("observed_ONNX_INT8_quantization") or {}).get("verified")
        ]
        if not verified:
            raise ValueError(
                "requested_weight_format=qint8_avx2 but no ONNX file under "
                f"{export_dir} demonstrates observed_ONNX_INT8_quantization; "
                "refusing filename/label-only INT8 claims"
            )
        primary = max(verified, key=lambda i: int(i.get("bytes") or 0))
    else:
        non_quant = [
            i
            for i in inspections
            if not (i.get("observed_ONNX_INT8_quantization") or {}).get("verified")
        ]
        pool = non_quant or inspections
        primary = max(pool, key=lambda i: int(i.get("bytes") or 0))
        if (primary.get("observed_ONNX_INT8_quantization") or {}).get("verified"):
            raise RuntimeError(
                "FP32 ONNX selection unexpectedly chose a quantized graph"
            )

    onnx_path = Path(primary["onnx_path"])
    identity = dict(identity)
    identity["selected_onnx_path"] = str(onnx_path)
    identity["selected_onnx_file_name"] = _relative_onnx_file_name(export_dir, onnx_path)
    identity["primary_onnx_path"] = str(onnx_path)
    identity["observed_ONNX_INT8_quantization"] = dict(
        primary["observed_ONNX_INT8_quantization"]
    )
    if weight_format == "qint8_avx2":
        identity["observed_ONNX_INT8_quantization"]["quantization_target"] = (
            FROZEN_QINT8_TARGET
        )
    return onnx_path, identity


def inspect_onnx_quantization(onnx_path: Path) -> dict[str, Any]:
    """Observe ONNX INT8/quantization evidence from the graph (fail-closed input).

    Never trusts filename suffixes (``_qint8``, ``avx2``) or request labels.
    """
    import onnx
    from onnx import TensorProto

    if not onnx_path.is_file():
        raise FileNotFoundError(f"ONNX model missing: {onnx_path}")
    model = onnx.load(str(onnx_path))
    int8_initializers = 0
    uint8_initializers = 0
    float_initializers = 0
    other_initializers = 0
    for init in model.graph.initializer:
        if init.data_type == TensorProto.INT8:
            int8_initializers += 1
        elif init.data_type == TensorProto.UINT8:
            uint8_initializers += 1
        elif init.data_type in {
            TensorProto.FLOAT,
            TensorProto.FLOAT16,
            TensorProto.BFLOAT16,
            TensorProto.DOUBLE,
        }:
            float_initializers += 1
        else:
            other_initializers += 1

    quant_ops = 0
    quant_op_types: dict[str, int] = {}
    for node in model.graph.node:
        name = node.op_type
        if name in {
            "QuantizeLinear",
            "DequantizeLinear",
            "QLinearMatMul",
            "QLinearAdd",
            "MatMulInteger",
            "DynamicQuantizeLinear",
        } or name.startswith("QLinear"):
            quant_ops += 1
            quant_op_types[name] = quant_op_types.get(name, 0) + 1

    integer_weights = int8_initializers + uint8_initializers
    # F002: verified requires demonstrable INT8/UINT8 weight initializers.
    # Quantization operators are supporting evidence only — never sufficient alone.
    verified = integer_weights > 0
    return {
        "onnx_path": str(onnx_path),
        "bytes": onnx_path.stat().st_size,
        "int8_initializer_count": int8_initializers,
        "uint8_initializer_count": uint8_initializers,
        "float_initializer_count": float_initializers,
        "other_initializer_count": other_initializers,
        "quantization_op_count": quant_ops,
        "quantization_op_types": quant_op_types,
        "observed_ONNX_INT8_quantization": {
            "verified": verified,
            "demonstrable_integer_initializers": integer_weights > 0,
            "demonstrable_quantization_ops": quant_ops > 0,
            "int8_initializer_count": int8_initializers,
            "uint8_initializer_count": uint8_initializers,
            "quantization_op_count": quant_ops,
            "authority": IMPLEMENTATION_AUTH,
            "note": (
                "verified iff INT8/UINT8 initializers are present; "
                "quantization ops are supporting evidence only; "
                "never from request label or filename"
            ),
        },
        "inspection_method": "onnx_protobuf_initializer_and_op_scan",
    }


def assert_requested_onnx_quantization(
    *,
    requested_weight_format: WeightFormat,
    observed_ONNX_INT8_quantization: dict[str, Any] | None,
) -> None:
    if requested_weight_format == "qint8_avx2":
        oc = observed_ONNX_INT8_quantization or {}
        if not oc.get("verified"):
            raise ValueError(
                "requested_weight_format=qint8_avx2 but "
                "observed_ONNX_INT8_quantization is not verified "
                "(requires demonstrable INT8/UINT8 weight initializers; "
                "quantization ops alone are insufficient); "
                "refusing filename/label/op-only INT8 claims"
            )
        if not oc.get("demonstrable_integer_initializers"):
            raise ValueError(
                "requested_weight_format=qint8_avx2 but no demonstrable "
                "INT8/UINT8 weight initializers were observed"
            )


def build_onnx_precision_identity(
    *,
    requested_weight_format: WeightFormat,
    export_dir: Path,
    quantization_target: str | None = None,
    transformation: str | None = None,
) -> dict[str, Any]:
    onnx_files = find_onnx_model_files(export_dir)
    if not onnx_files:
        raise FileNotFoundError(f"no .onnx files under {export_dir}")
    inspections = [inspect_onnx_quantization(p) for p in onnx_files]
    if requested_weight_format == "qint8_avx2":
        verified = [
            i
            for i in inspections
            if (i.get("observed_ONNX_INT8_quantization") or {}).get("verified")
        ]
        primary = (
            max(verified, key=lambda i: int(i.get("bytes") or 0))
            if verified
            else max(inspections, key=lambda i: int(i.get("bytes") or 0))
        )
    else:
        non_quant = [
            i
            for i in inspections
            if not (i.get("observed_ONNX_INT8_quantization") or {}).get("verified")
        ]
        pool = non_quant or inspections
        primary = max(pool, key=lambda i: int(i.get("bytes") or 0))
    oc = dict(primary["observed_ONNX_INT8_quantization"])
    if quantization_target:
        oc["quantization_target"] = quantization_target
    if transformation:
        oc["transformation"] = transformation
    any_verified = any(
        (i.get("observed_ONNX_INT8_quantization") or {}).get("verified")
        for i in inspections
    )
    if requested_weight_format == "qint8_avx2":
        # Aggregate fact: at least one inspected ONNX file demonstrates INT8.
        oc["verified"] = bool(any_verified and oc.get("verified"))
        if any_verified and not oc.get("verified"):
            # Primary lacked evidence but another file has it — promote aggregate.
            for item in inspections:
                cand = item.get("observed_ONNX_INT8_quantization") or {}
                if cand.get("verified"):
                    oc = dict(cand)
                    if quantization_target:
                        oc["quantization_target"] = quantization_target
                    if transformation:
                        oc["transformation"] = transformation
                    primary = item
                    break
    return {
        "requested_weight_format": requested_weight_format,
        "onnx_files": [str(p) for p in onnx_files],
        "primary_onnx_path": primary["onnx_path"],
        "onnx_inspections": inspections,
        "observed_ONNX_INT8_quantization": oc,
        "authority": IMPLEMENTATION_AUTH,
    }


def export_onnx_fp32(
    *,
    model_dir: Path,
    export_dir: Path,
) -> dict[str, Any]:
    """Export local pinned checkpoint to ST ONNX (FP32 provenance artifact)."""
    from sentence_transformers import SentenceTransformer

    require_embedding_artifacts(
        model_dir,
        expected_model_id=EXPECTED_MODEL_ID,
        expected_revision=EXPECTED_MODEL_REVISION,
        expected_dimension=EXPECTED_DIMENSION,
    )
    if export_dir.exists():
        raise FileExistsError(f"export dir already exists: {export_dir}")
    export_dir.mkdir(parents=True, exist_ok=False)

    model = SentenceTransformer(
        str(model_dir),
        backend="onnx",
        device="cpu",
        trust_remote_code=False,
        local_files_only=True,
        model_kwargs=_st_onnx_model_kwargs(export=True),
    )
    model.save_pretrained(str(export_dir))
    identity = build_onnx_precision_identity(
        requested_weight_format="fp32",
        export_dir=export_dir,
    )
    # FP32 source must NOT look like an INT8-quantized graph.
    if identity["observed_ONNX_INT8_quantization"].get("verified"):
        raise RuntimeError(
            "FP32 ONNX export unexpectedly contains INT8 quantization evidence"
        )
    tree = hash_export_tree(export_dir)
    return {
        "requested_weight_format": "fp32",
        "weight_format": "fp32",
        "model_dir": str(model_dir),
        "export_dir": str(export_dir),
        "export_method": ["sentence_transformers_onnx_backend", "CPUExecutionProvider"],
        "provider": FROZEN_ONNX_PROVIDER,
        "ort_intra_op_threads": FROZEN_ORT_INTRA_OP_THREADS,
        "ort_inter_op_threads": FROZEN_ORT_INTER_OP_THREADS,
        "precision_identity": identity,
        "export_tree": tree,
        "backend": "onnx",
        "device": "cpu",
        "authority": IMPLEMENTATION_AUTH,
    }


def materialize_qint8_avx2_derivative(
    *,
    source_export_dir: Path,
    export_dir: Path,
    expected_source_tree_sha256: str,
) -> dict[str, Any]:
    """Derive AVX2 dynamic QINT8 ONNX from an accepted FP32 ST/ONNX export.

    F001: ``expected_source_tree_sha256`` is mandatory. Wrong/missing SHA fails
    before copy or quantization.
    """
    source = Path(source_export_dir).resolve()
    dest = Path(export_dir).resolve()
    if source == dest:
        raise ValueError("source_export_dir must differ from export_dir")
    if not source.is_dir():
        raise FileNotFoundError(f"source export missing: {source}")
    if dest.exists():
        raise FileExistsError(f"QINT8 export dir already exists: {dest}")

    expected = str(expected_source_tree_sha256 or "").strip()
    if not expected:
        raise ValueError(
            "expected_source_tree_sha256 is required for QINT8 AVX2 derivative "
            "(accepted FP32 Stage-0 export tree SHA); refusing unpinned source"
        )

    # Fail closed on identity before any ST import, copy, or quantization.
    source_tree = hash_export_tree(source)
    if source_tree.get("tree_sha256") != expected:
        raise ValueError(
            "ONNX QINT8 source tree SHA256 mismatch: "
            f"observed={source_tree.get('tree_sha256')} expected={expected}"
        )
    source_identity = build_onnx_precision_identity(
        requested_weight_format="fp32",
        export_dir=source,
    )
    if source_identity["observed_ONNX_INT8_quantization"].get("verified"):
        raise ValueError(
            "ONNX QINT8 source already appears quantized; refusing stacked quantize"
        )

    from sentence_transformers import SentenceTransformer

    try:
        from sentence_transformers.backend import export_dynamic_quantized_onnx_model
    except ImportError:  # pragma: no cover - older ST layout
        from sentence_transformers import (  # type: ignore[attr-defined]
            export_dynamic_quantized_onnx_model,
        )

    shutil.copytree(source, dest)
    model = SentenceTransformer(
        str(dest),
        backend="onnx",
        device="cpu",
        trust_remote_code=False,
        local_files_only=True,
        model_kwargs=_st_onnx_model_kwargs(export=False),
    )
    # Write quantized ONNX beside the copied ST tree (non-aliasing via ST helper).
    export_dynamic_quantized_onnx_model(
        model,
        quantization_config=FROZEN_QINT8_TARGET,
        model_name_or_path=str(dest),
        push_to_hub=False,
    )
    precision_identity = build_onnx_precision_identity(
        requested_weight_format="qint8_avx2",
        export_dir=dest,
        quantization_target=FROZEN_QINT8_TARGET,
        transformation=(
            "sentence_transformers.backend.export_dynamic_quantized_onnx_model"
            f"/quantization_config={FROZEN_QINT8_TARGET}"
        ),
    )
    assert_requested_onnx_quantization(
        requested_weight_format="qint8_avx2",
        observed_ONNX_INT8_quantization=precision_identity[
            "observed_ONNX_INT8_quantization"
        ],
    )
    source_after = hash_export_tree(source)
    if source_after.get("tree_sha256") != source_tree.get("tree_sha256"):
        raise RuntimeError("ONNX FP32 source export mutated during QINT8 derivative")
    tree = hash_export_tree(dest)
    return {
        "requested_weight_format": "qint8_avx2",
        "weight_format": "qint8_avx2",
        "source_export_dir": str(source),
        "export_dir": str(dest),
        "export_method": [
            "derivative_copy_st_onnx_export",
            "export_dynamic_quantized_onnx_model_avx2",
        ],
        "quantization_target": FROZEN_QINT8_TARGET,
        "provider": FROZEN_ONNX_PROVIDER,
        "source_export_tree": source_tree,
        "source_tree_sha256_before": source_tree.get("tree_sha256"),
        "source_tree_sha256_after": source_after.get("tree_sha256"),
        "source_precision_identity": source_identity,
        "precision_identity": precision_identity,
        "export_tree": tree,
        "backend": "onnx",
        "device": "cpu",
        "no_hf_redownload": True,
        "authority": IMPLEMENTATION_AUTH,
    }


def load_onnx_st_model(
    *,
    model_or_export_dir: Path,
    weight_format: WeightFormat,
    require_quant_match: bool = True,
) -> tuple[Any, dict[str, Any]]:
    from sentence_transformers import SentenceTransformer

    selected_path, precision_identity = select_onnx_artifact_for_weight_format(
        export_dir=model_or_export_dir,
        weight_format=weight_format,
    )
    if require_quant_match:
        assert_requested_onnx_quantization(
            requested_weight_format=weight_format,
            observed_ONNX_INT8_quantization=precision_identity[
                "observed_ONNX_INT8_quantization"
            ],
        )
    file_name = precision_identity["selected_onnx_file_name"]
    model = SentenceTransformer(
        str(model_or_export_dir),
        backend="onnx",
        device="cpu",
        trust_remote_code=False,
        local_files_only=True,
        model_kwargs=_st_onnx_model_kwargs(export=False, file_name=file_name),
    )
    precision_identity = dict(precision_identity)
    precision_identity["loaded_onnx_path"] = str(selected_path)
    precision_identity["loaded_onnx_file_name"] = file_name
    return model, precision_identity


def _st_encode_documents(model: Any, texts: Sequence[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = model.encode(
        list(texts),
        batch_size=FROZEN_BATCH_SIZE,
        normalize_embeddings=FROZEN_NORMALIZE,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    out: list[list[float]] = []
    for row in vectors:
        vec = [float(x) for x in row.tolist()]
        if FROZEN_NORMALIZE:
            vec = _normalize_vector(vec)
        out.append(vec)
    return out


def _st_encode_query(model: Any, text: str, *, query_text_contract: str) -> list[float]:
    if query_text_contract == MODEL_QUERY_PROMPT_V1:
        prompts = getattr(model, "prompts", None)
        if not isinstance(prompts, dict) or MODEL_QUERY_PROMPT_NAME not in prompts:
            raise RuntimeError(
                f"{MODEL_QUERY_PROMPT_V1} requires prompts[{MODEL_QUERY_PROMPT_NAME!r}]"
            )
        vector = model.encode(
            text,
            prompt_name=MODEL_QUERY_PROMPT_NAME,
            normalize_embeddings=FROZEN_NORMALIZE,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    else:
        vector = model.encode(
            text,
            normalize_embeddings=FROZEN_NORMALIZE,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    vec = [float(x) for x in vector.tolist()]
    if FROZEN_NORMALIZE:
        vec = _normalize_vector(vec)
    return vec


def resolve_production_query_contract() -> str:
    from offline_rag.config import load_settings
    from offline_rag.dense.query_text import resolve_query_text_contract

    settings = load_settings()
    query = settings.dense.query_text
    return resolve_query_text_contract(
        strategy=query.strategy,
        contract_version=query.contract_version,
    )


def smoke_encode_compat(model: Any, *, query_text_contract: str) -> dict[str, Any]:
    doc_vecs = _st_encode_documents(model, ["cpu-onnx stage0 document smoke"])
    q_vec = _st_encode_query(
        model,
        "cpu-onnx stage0 query smoke",
        query_text_contract=query_text_contract,
    )
    issues: list[str] = []
    if len(doc_vecs) != 1 or len(doc_vecs[0]) != EXPECTED_DIMENSION:
        issues.append("document_dim")
    if len(q_vec) != EXPECTED_DIMENSION:
        issues.append("query_dim")
    if not _finite(doc_vecs[0]):
        issues.append("document_non_finite")
    if not _finite(q_vec):
        issues.append("query_non_finite")
    if FROZEN_NORMALIZE:
        dn = _l2(doc_vecs[0])
        qn = _l2(q_vec)
        if not (0.99 <= dn <= 1.01):
            issues.append(f"document_norm={dn}")
        if not (0.99 <= qn <= 1.01):
            issues.append(f"query_norm={qn}")
    return {
        "ok": not issues,
        "issues": issues,
        "document_dim": len(doc_vecs[0]) if doc_vecs else None,
        "query_dim": len(q_vec),
        "query_text_contract": query_text_contract,
    }


def _maybe_write_evidence(
    payload: dict[str, Any],
    *,
    evidence_dir: Path | None,
    stem: str,
) -> dict[str, Any]:
    if evidence_dir is None:
        return payload
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"{stem}_{int(time.time())}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = dict(payload)
    payload["evidence_path"] = str(path)
    payload["evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return payload


def _environment_fingerprint() -> dict[str, Any]:
    import sys
    from importlib.metadata import version as pkg_version

    versions: dict[str, Any] = {
        "python": (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        ),
    }
    for name in (
        "sentence-transformers",
        "onnxruntime",
        "onnx",
        "optimum",
        "transformers",
    ):
        try:
            versions[name] = pkg_version(name)
        except Exception:  # noqa: BLE001
            versions[name] = None
    return versions


def capture_cpu_host_runtime_facts() -> dict[str, Any]:
    facts: dict[str, Any] = {
        "cpu_count_os": os.cpu_count(),
        "ort_intra_op_threads": FROZEN_ORT_INTRA_OP_THREADS,
        "ort_inter_op_threads": FROZEN_ORT_INTER_OP_THREADS,
        "provider": FROZEN_ONNX_PROVIDER,
    }
    try:
        import resource

        facts["peak_rss_bytes"] = int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        ) * (1024 if os.name != "nt" else 1)
    except Exception as exc:  # noqa: BLE001
        facts["peak_rss_error"] = f"{type(exc).__name__}: {exc}"
    try:
        import subprocess

        out = subprocess.check_output(["lscpu"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            if key in {"Model name", "Architecture", "CPU(s)", "Vendor ID"}:
                facts[key] = val.strip()
    except Exception as exc:  # noqa: BLE001
        facts["lscpu_error"] = f"{type(exc).__name__}: {exc}"
    return facts


def load_children_by_id(
    *,
    repo_root: Path,
    chunk_ids: Sequence[str] | None = None,
) -> dict[str, Chunk]:
    """Load child chunks keyed by id; verifies manifest identity via harness."""
    from offline_rag.dense.cpu_onnx_harness import load_chunk_ids_from_manifest

    all_ids = load_chunk_ids_from_manifest(repo_root=repo_root)
    wanted = set(chunk_ids) if chunk_ids is not None else set(all_ids)

    manifest_path = (
        repo_root / "data" / "chunk-manifests" / f"{EXPECTED_CHUNK_SET_ID}.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    out: dict[str, Chunk] = {}
    for doc in payload["documents"]:
        rel = doc["chunk_artifact"]
        path = repo_root / "data" / rel
        if not path.is_file():
            path = repo_root / rel
        art = json.loads(path.read_text(encoding="utf-8"))
        for child in art["children"]:
            cid = str(child["chunk_id"])
            if cid in wanted:
                out[cid] = Chunk.model_validate(child)
    missing = wanted - set(out)
    if missing:
        raise ValueError(f"missing {len(missing)} chunk ids from artifacts")
    return out


def document_embedding_texts(chunks: Sequence[Chunk]) -> list[tuple[str, str, str]]:
    """plain-v1: embedding text is exact chunk.text."""
    builder = PlainEmbeddingTextBuilder()
    rows: list[tuple[str, str, str]] = []
    for chunk in chunks:
        inputs = ranking_inputs_for_chunk(
            chunk_text=chunk.text,
            section_path=list(chunk.section_path or []),
            document_title=None,
        )
        text = builder.build(inputs)
        if text != chunk.text:
            raise RuntimeError("plain-v1 contract violation: text != chunk.text")
        if builder.contract_version != PLAIN_EMBEDDING_TEXT_CONTRACT:
            raise RuntimeError("unexpected embedding text contract")
        rows.append((chunk.chunk_id, embedding_text_hash(text), text))
    return rows


class OnnxSTEmbedder:
    adapter_contract = SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT

    def __init__(
        self,
        model: Any,
        *,
        weight_format: WeightFormat,
        query_text_contract: str,
        precision_identity: dict[str, Any] | None = None,
    ) -> None:
        self._model = model
        self.model_id = EXPECTED_MODEL_ID
        self.model_revision = EXPECTED_MODEL_REVISION
        self.dimension = EXPECTED_DIMENSION
        self.normalize = FROZEN_NORMALIZE
        self.batch_size = FROZEN_BATCH_SIZE
        self.query_text_contract = query_text_contract
        self.weight_format = weight_format
        self.requested_weight_format = weight_format
        self.precision_identity = dict(precision_identity or {})
        self.device = "cpu"
        self.resolved_device = "cpu"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return _st_encode_documents(self._model, texts)

    def embed_query(self, text: str) -> list[float]:
        return _st_encode_query(
            self._model, text, query_text_contract=self.query_text_contract
        )


def execute_export_fp32(
    *,
    export_dir: Path,
    model_dir: Path,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    identity = verify_local_model_identity(model_dir)
    export_meta = export_onnx_fp32(model_dir=model_dir, export_dir=export_dir)
    model, precision_identity = load_onnx_st_model(
        model_or_export_dir=export_dir,
        weight_format="fp32",
        require_quant_match=False,
    )
    query_contract = resolve_production_query_contract()
    smoke = smoke_encode_compat(model, query_text_contract=query_contract)
    payload = {
        "status": "ok" if smoke["ok"] else "failed",
        "stage_id": "export_fp32",
        "ok": bool(smoke["ok"]),
        "authority": IMPLEMENTATION_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "requested_weight_format": "fp32",
        "local_model_identity": identity,
        "export": export_meta,
        "precision_identity": precision_identity,
        "smoke": smoke,
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
        "repo_root": str(repo_root) if repo_root else None,
    }
    return _maybe_write_evidence(payload, evidence_dir=evidence_dir, stem="export_fp32")


def execute_export_qint8_avx2(
    *,
    export_dir: Path,
    source_export_dir: Path,
    model_dir: Path,
    expected_source_tree_sha256: str,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    identity = verify_local_model_identity(model_dir)
    export_meta = materialize_qint8_avx2_derivative(
        source_export_dir=source_export_dir,
        export_dir=export_dir,
        expected_source_tree_sha256=expected_source_tree_sha256,
    )
    model, precision_identity = load_onnx_st_model(
        model_or_export_dir=export_dir,
        weight_format="qint8_avx2",
        require_quant_match=True,
    )
    query_contract = resolve_production_query_contract()
    smoke = smoke_encode_compat(model, query_text_contract=query_contract)
    payload = {
        "status": "ok" if smoke["ok"] else "failed",
        "stage_id": "export_qint8_avx2",
        "ok": bool(smoke["ok"]),
        "authority": IMPLEMENTATION_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "requested_weight_format": "qint8_avx2",
        "local_model_identity": identity,
        "export": export_meta,
        "precision_identity": precision_identity,
        "observed_ONNX_INT8_quantization": precision_identity.get(
            "observed_ONNX_INT8_quantization"
        ),
        "smoke": smoke,
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
        "repo_root": str(repo_root) if repo_root else None,
    }
    return _maybe_write_evidence(
        payload, evidence_dir=evidence_dir, stem="export_qint8_avx2"
    )


def execute_screen(
    *,
    export_dir: Path,
    repo_root: Path,
    expected_candidate_tree_sha256: str,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """128-child screen against an immutable QINT8 candidate tree (F003)."""
    expected = str(expected_candidate_tree_sha256 or "").strip()
    if not expected:
        raise ValueError(
            "expected_candidate_tree_sha256 is required for screen "
            "(accepted QINT8 Stage-0B candidate tree SHA)"
        )

    children_by_id = load_children_by_id(repo_root=repo_root)
    selected_ids = select_screen_chunk_ids(sorted(children_by_id.keys()))
    digest = sha256_text("\n".join(selected_ids))
    if digest != EXPECTED_SCREEN_CHUNK_IDS_DIGEST:
        raise ValueError(
            f"screen digest mismatch: observed={digest} "
            f"expected={EXPECTED_SCREEN_CHUNK_IDS_DIGEST}"
        )
    chunks = [children_by_id[cid] for cid in selected_ids]
    rows = document_embedding_texts(chunks)
    texts = [t for _, _, t in rows]

    tree_before = hash_export_tree(export_dir)
    if tree_before.get("tree_sha256") != expected:
        raise ValueError(
            "QINT8 candidate tree SHA256 mismatch before screen: "
            f"observed={tree_before.get('tree_sha256')} expected={expected}"
        )
    model, precision_identity = load_onnx_st_model(
        model_or_export_dir=export_dir,
        weight_format="qint8_avx2",
        require_quant_match=True,
    )
    query_contract = resolve_production_query_contract()
    embedder = OnnxSTEmbedder(
        model,
        weight_format="qint8_avx2",
        query_text_contract=query_contract,
        precision_identity=precision_identity,
    )
    cpu_before = capture_cpu_host_runtime_facts()
    started = time.perf_counter()
    vectors = embedder.embed_documents(texts)
    encode_s = time.perf_counter() - started
    cpu_after = capture_cpu_host_runtime_facts()
    if len(vectors) != len(texts):
        raise RuntimeError("screen encode length mismatch")
    for vec in vectors:
        if len(vec) != EXPECTED_DIMENSION or not _finite(vec):
            raise RuntimeError("screen vector validation failed")
    tree_after = hash_export_tree(export_dir)
    if tree_after.get("tree_sha256") != expected:
        raise ValueError(
            "QINT8 candidate tree mutated during screen: "
            f"before={expected} after={tree_after.get('tree_sha256')}"
        )
    chunks_per_sec = float(len(texts)) / encode_s if encode_s > 0 else float("inf")
    projected = project_full_minutes(chunks_per_sec)
    payload = {
        "status": "ok",
        "stage_id": "screen_qint8_avx2",
        "ok": True,
        "authority": IMPLEMENTATION_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "requested_weight_format": "qint8_avx2",
        "precision_identity": precision_identity,
        "screen_child_count": len(texts),
        "screen_chunk_ids_digest": digest,
        "encode_wall_s": encode_s,
        "chunks_per_sec": chunks_per_sec,
        "projected_full_minutes": projected,
        "full_wall_minutes": None,
        "dimension": EXPECTED_DIMENSION,
        "batch_size": FROZEN_BATCH_SIZE,
        "normalize": FROZEN_NORMALIZE,
        "ort_intra_op_threads": FROZEN_ORT_INTRA_OP_THREADS,
        "ort_inter_op_threads": FROZEN_ORT_INTER_OP_THREADS,
        "provider": FROZEN_ONNX_PROVIDER,
        "export_dir": str(export_dir),
        "expected_candidate_tree_sha256": expected,
        "candidate_tree_sha256_before": tree_before.get("tree_sha256"),
        "candidate_tree_sha256_after": tree_after.get("tree_sha256"),
        "cpu_host_runtime_before": cpu_before,
        "cpu_host_runtime_after": cpu_after,
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
        "note": "projected_full_minutes is screening only; not confirmation evidence",
    }
    return _maybe_write_evidence(
        payload, evidence_dir=evidence_dir, stem="screen_qint8_avx2"
    )


def execute_parity(
    *,
    export_dir: Path,
    repo_root: Path,
    evidence_dir: Path | None = None,
    reference_embedder: Any | None = None,
    reference_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """d2-retrieval-parity-v1 scaffolding against CUDA FP16 reference (not executed locked)."""
    children_by_id = load_children_by_id(repo_root=repo_root)
    all_ids = sorted(children_by_id.keys())
    doc_ids, query_ids = select_parity_populations(all_ids)
    docs = [children_by_id[cid] for cid in doc_ids]
    queries = [children_by_id[cid] for cid in query_ids]
    doc_rows = document_embedding_texts(docs)
    query_contract = resolve_production_query_contract()

    if reference_embedder is None:
        from offline_rag.config import load_settings
        from offline_rag.dense.embedder import make_embedder, observe_embedder_execution_facts

        environ = dict(os.environ)
        environ["OFFLINE_RAG_EMBEDDING_DEVICE"] = "cuda"
        environ["OFFLINE_RAG_EMBEDDING_PRECISION"] = "fp16"
        environ["OFFLINE_RAG_EMBEDDING_BATCH_SIZE"] = str(FROZEN_BATCH_SIZE)
        settings = load_settings(environ=environ)
        reference_embedder = make_embedder(settings)
        load = getattr(reference_embedder, "_load", None)
        if callable(load):
            load()
        reference_facts = observe_embedder_execution_facts(reference_embedder)
    elif reference_facts is None:
        reference_facts = {}

    ref_docs = {
        cid: list(vec)
        for (cid, _, _), vec in zip(
            doc_rows,
            reference_embedder.embed_documents([t for _, _, t in doc_rows]),
            strict=True,
        )
    }
    ref_queries = {
        chunk.chunk_id: list(reference_embedder.embed_query(chunk.text))
        for chunk in queries
    }
    cand_model, precision_identity = load_onnx_st_model(
        model_or_export_dir=export_dir,
        weight_format="qint8_avx2",
        require_quant_match=True,
    )
    cand_docs = {
        cid: vec
        for (cid, _, _), vec in zip(
            doc_rows,
            _st_encode_documents(cand_model, [t for _, _, t in doc_rows]),
            strict=True,
        )
    }
    cand_queries = {
        chunk.chunk_id: _st_encode_query(
            cand_model, chunk.text, query_text_contract=query_contract
        )
        for chunk in queries
    }

    doc_cos = [
        _cosine(ref_docs[cid], cand_docs[cid]) for cid in doc_ids if cid in ref_docs
    ]
    query_cos = [
        _cosine(ref_queries[cid], cand_queries[cid])
        for cid in query_ids
        if cid in ref_queries
    ]

    def _topk(
        q: list[float], docs: dict[str, list[float]], order: list[str], k: int = 10
    ) -> list[str]:
        scored = [(_cosine(q, docs[cid]), cid) for cid in order]
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [cid for _, cid in scored[:k]]

    top1 = 0
    overlaps: list[float] = []
    for qid in query_ids:
        ref_top = _topk(ref_queries[qid], ref_docs, doc_ids)
        cand_top = _topk(cand_queries[qid], cand_docs, doc_ids)
        if ref_top and cand_top and ref_top[0] == cand_top[0]:
            top1 += 1
        overlaps.append(len(set(ref_top) & set(cand_top)) / 10.0)
    import statistics

    metrics = {
        "median_document_vector_cosine": float(statistics.median(doc_cos))
        if doc_cos
        else 0.0,
        "min_document_vector_cosine": float(min(doc_cos)) if doc_cos else 0.0,
        "median_query_vector_cosine": float(statistics.median(query_cos))
        if query_cos
        else 0.0,
        "min_query_vector_cosine": float(min(query_cos)) if query_cos else 0.0,
        "top1_agreement": top1,
        "mean_top10_set_overlap": float(statistics.mean(overlaps)) if overlaps else 0.0,
        "min_top10_set_overlap": float(min(overlaps)) if overlaps else 0.0,
    }
    ok = parity_thresholds_pass(metrics)
    payload = {
        "status": "ok" if ok else "failed",
        "stage_id": "parity_qint8_avx2",
        "ok": ok,
        "parity_ok": ok,
        "authority": IMPLEMENTATION_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "parity_contract": PARITY_CONTRACT_ID,
        "parity_thresholds": PARITY_THRESHOLDS,
        "metrics": metrics,
        "precision_identity": precision_identity,
        "reference_facts": reference_facts,
        "document_count": len(doc_ids),
        "query_count": len(query_ids),
        "export_dir": str(export_dir),
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
    }
    return _maybe_write_evidence(
        payload, evidence_dir=evidence_dir, stem="parity_qint8_avx2"
    )


__all__ = [
    "OnnxSTEmbedder",
    "assert_requested_onnx_quantization",
    "build_onnx_precision_identity",
    "capture_cpu_host_runtime_facts",
    "execute_export_fp32",
    "execute_export_qint8_avx2",
    "execute_parity",
    "execute_screen",
    "export_onnx_fp32",
    "inspect_onnx_quantization",
    "load_onnx_st_model",
    "materialize_qint8_avx2_derivative",
    "select_onnx_artifact_for_weight_format",
    "smoke_encode_compat",
]
