"""CPU-OV-01 OpenVINO scientific executor (callable only when unlocked).

Authority: S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-REWORK-AUTH-001

Implements real local-pinned export/load, ST OpenVINO encode, 128-child screen
timing, d2-retrieval-parity-v1 computation, and 1296 confirmation machinery.

This module must not be invoked while ``EXECUTION_AUTHORIZED`` is False.
Harness entrypoints enforce that gate before calling here.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from offline_rag.core.ids import (
    MODEL_QUERY_PROMPT_V1,
    PLAIN_EMBEDDING_TEXT_CONTRACT,
    SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT,
    embedding_text_hash,
)
from offline_rag.dense.cpu_ov_feasibility import (
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_SET_ID,
    EXPECTED_DIMENSION,
    EXPECTED_MODEL_ID,
    EXPECTED_MODEL_REVISION,
    EXPERIMENT_ID,
    FROZEN_BATCH_SIZE,
    FROZEN_NORMALIZE,
    IMPLEMENTATION_REWORK2_AUTH,
    IMPLEMENTATION_REWORK3_AUTH,
    IMPLEMENTATION_REWORK_AUTH,
    PARITY_CONTRACT_ID,
    PARITY_THRESHOLDS,
    WORKLOAD_LABEL,
    WeightFormat,
    parity_thresholds_pass,
    project_full_minutes,
)
from offline_rag.dense.cpu_ov_harness import (
    hash_export_tree,
    select_parity_populations,
    select_screen_chunk_ids,
    sha256_file,
    sha256_text,
    verify_local_model_identity,
)
from offline_rag.dense.provision import require_embedding_artifacts
from offline_rag.dense.query_text import MODEL_QUERY_PROMPT_NAME
from offline_rag.dense.text import PlainEmbeddingTextBuilder
from offline_rag.domain.documents import Chunk
from offline_rag.retrieval.ranking_text import ranking_inputs_for_chunk

EncodeFn = Callable[[Sequence[str]], list[list[float]]]
QueryEncodeFn = Callable[[str], list[float]]


class OpenVinoSTEmbedder:
    """Embedder protocol adapter over a SentenceTransformer OpenVINO model.

    Injected into ``run_indexing`` for production-like full confirmation (F006).
    """

    adapter_contract = SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT

    def __init__(
        self,
        model: Any,
        *,
        weight_format: WeightFormat,
        query_text_contract: str,
        batch_size: int = FROZEN_BATCH_SIZE,
        normalize: bool = FROZEN_NORMALIZE,
        precision_identity: dict[str, Any] | None = None,
    ) -> None:
        self._model = model
        self.model_id = EXPECTED_MODEL_ID
        self.model_revision = EXPECTED_MODEL_REVISION
        self.dimension = EXPECTED_DIMENSION
        self.normalize = normalize
        self.batch_size = batch_size
        self.query_text_contract = query_text_contract
        self.weight_format = weight_format
        self.requested_weight_format = weight_format
        self.precision_identity = dict(precision_identity or {})
        self.device = "cpu"
        self.resolved_device = "cpu"
        self.configured_device = "cpu"
        # Configured = request; resolved = observed IR when known (F008).
        self.configured_precision = weight_format
        observed_ir = self.precision_identity.get("observed_IR_weight_precision")
        self.resolved_precision = (
            observed_ir if isinstance(observed_ir, str) else None
        )
        self.precision_selection_reason = "cpu_ov_export_observed"
        self.device_selection_reason = "cpu_ov_feasibility"
        self.cuda_available = False
        self.torch_cuda_build = None

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return _st_encode_documents(
            self._model,
            texts,
            batch_size=self.batch_size,
            normalize=self.normalize,
        )

    def embed_query(self, text: str) -> list[float]:
        return _st_encode_query(
            self._model,
            text,
            query_text_contract=self.query_text_contract,
            normalize=self.normalize,
        )

    def observe_execution_facts(self) -> dict[str, str | None]:
        """Return observed precision only — never invent from requested label (F008)."""
        observed_ir = self.precision_identity.get("observed_IR_weight_precision")
        observed_inf = self.precision_identity.get(
            "observed_CPU_inference_precision"
        )
        dtype: str | None = None
        if isinstance(observed_ir, str):
            dtype = f"openvino_ir_{observed_ir}"
        return {
            "dtype": dtype,
            "attention_backend": "openvino",
            "requested_weight_format": str(self.requested_weight_format),
            "observed_IR_weight_precision": (
                observed_ir if isinstance(observed_ir, str) else None
            ),
            "observed_CPU_inference_precision": (
                observed_inf if isinstance(observed_inf, str) else None
            ),
        }


def capture_cpu_host_runtime_facts(
    *,
    embedder: Any | None = None,
    batch_size: int | None = FROZEN_BATCH_SIZE,
) -> dict[str, Any]:
    """Observational CPU/host facts for screen/full evidence (F007; no tuning)."""
    from offline_rag.dense.d2_observability import capture_cpu_baseline_facts

    facts = capture_cpu_baseline_facts(embedder=embedder, batch_size=batch_size)
    facts["cpu_model_name"] = None
    facts["cpu_architecture"] = None
    facts["cpu_vendor"] = None
    facts["hypervisor_vendor"] = None
    facts["virtualization_type"] = None
    facts["cpu_sockets"] = None
    facts["threads_per_core"] = None
    facts["cores_per_socket"] = None
    try:
        import subprocess

        out = subprocess.check_output(
            ["lscpu"], text=True, stderr=subprocess.DEVNULL
        )
        mapping = {
            "Model name": "cpu_model_name",
            "Architecture": "cpu_architecture",
            "Vendor ID": "cpu_vendor",
            "Hypervisor vendor": "hypervisor_vendor",
            "Virtualization type": "virtualization_type",
            "Socket(s)": "cpu_sockets",
            "Thread(s) per core": "threads_per_core",
            "Core(s) per socket": "cores_per_socket",
            "CPU(s)": "cpu_logical_count_lscpu",
        }
        for line in out.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            if key in mapping:
                facts[mapping[key]] = val.strip()
        # Prefer lscpu physical derivation when psutil absent.
        if facts.get("cpu_physical_count") is None:
            try:
                cores = int(facts.get("cores_per_socket") or 0)
                sockets = int(facts.get("cpu_sockets") or 0)
                if cores > 0 and sockets > 0:
                    facts["cpu_physical_count"] = cores * sockets
            except (TypeError, ValueError):
                pass
    except Exception as exc:  # noqa: BLE001
        facts["lscpu_error"] = f"{type(exc).__name__}: {exc}"
    return facts


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch {len(a)} != {len(b)}")
    dot = sum(float(x) * float(y) for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(float(x) * float(x) for x in a))
    nb = math.sqrt(sum(float(y) * float(y) for y in b))
    if na == 0.0 or nb == 0.0:
        return float("nan")
    return float(dot / (na * nb))


def _l2(vec: Sequence[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def _finite(vec: Sequence[float]) -> bool:
    return all(math.isfinite(float(x)) for x in vec)


def _normalize_vector(vec: list[float]) -> list[float]:
    n = _l2(vec)
    if n <= 0.0:
        return vec
    return [float(x) / n for x in vec]


def load_children_by_id(
    *,
    repo_root: Path,
    chunk_ids: Sequence[str] | None = None,
) -> dict[str, Chunk]:
    """Load child chunks keyed by id; verifies manifest identity via harness."""
    from offline_rag.dense.cpu_ov_harness import load_chunk_ids_from_manifest

    # Provenance gate first (count + frozen SHA256).
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


def find_openvino_ir_xml(export_dir: Path) -> Path:
    """Locate the primary OpenVINO IR XML under an ST export tree."""
    candidates = [
        export_dir / "openvino" / "openvino_model.xml",
        export_dir / "openvino_model.xml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted(export_dir.rglob("openvino_model*.xml"))
    if not matches:
        raise FileNotFoundError(f"no OpenVINO IR XML under {export_dir}")
    return matches[0]


def classify_ir_weight_precision(
    *,
    f16_constant_count: int,
    f32_constant_count: int,
) -> str:
    """Classify IR storage precision from Constant element-type counts (F008)."""
    if f16_constant_count <= 0 and f32_constant_count <= 0:
        return "unknown"
    if f16_constant_count <= 0 and f32_constant_count > 0:
        return "fp32"
    if f16_constant_count > 0 and f32_constant_count <= 0:
        return "fp16"
    # Residual f32 constants are common after FP16 compression; majority wins.
    if f16_constant_count >= f32_constant_count:
        return "fp16"
    return "fp32"


def inspect_openvino_ir_weight_precision(xml_path: Path) -> dict[str, Any]:
    """Observe IR/storage weight precision from the exported artifact (F008).

    Primary signal is IR XML ``element_type`` counts (no OpenVINO import required).
    When OpenVINO is importable, Constant-op counts are recorded as a cross-check.
    """
    if not xml_path.is_file():
        raise FileNotFoundError(f"IR XML missing: {xml_path}")
    bin_path = xml_path.with_suffix(".bin")
    text = xml_path.read_text(encoding="utf-8", errors="replace")
    f16 = text.count('element_type="f16"')
    f32 = text.count('element_type="f32"')
    counts: dict[str, int] = {
        'element_type="f16"': f16,
        'element_type="f32"': f32,
    }
    method = "xml_element_type_scan"
    ov_constant_counts: dict[str, int] | None = None
    try:
        import openvino as ov

        core = ov.Core()
        model = core.read_model(str(xml_path))
        ov_constant_counts = {}
        for op in model.get_ordered_ops():
            if op.get_type_name() != "Constant":
                continue
            for out in op.outputs():
                key = str(out.get_element_type())
                ov_constant_counts[key] = ov_constant_counts.get(key, 0) + 1
        method = "xml_element_type_scan+openvino_constant_crosscheck"
    except Exception:  # noqa: BLE001
        ov_constant_counts = None

    observed = classify_ir_weight_precision(
        f16_constant_count=f16, f32_constant_count=f32
    )
    return {
        "xml_path": str(xml_path),
        "bin_path": str(bin_path) if bin_path.is_file() else None,
        "bin_bytes": bin_path.stat().st_size if bin_path.is_file() else None,
        "inspection_method": method,
        "xml_element_type_counts": counts,
        "openvino_constant_element_type_counts": ov_constant_counts,
        "f16_constant_count": f16,
        "f32_constant_count": f32,
        "observed_IR_weight_precision": observed,
    }


def inspect_compiled_cpu_inference_precision(
    xml_path: Path,
    *,
    inference_precision_hint: str | None = None,
) -> dict[str, Any]:
    """Observe compiled CPU inference precision when OpenVINO exposes it (F008)."""
    import openvino as ov

    core = ov.Core()
    model = core.read_model(str(xml_path))
    config: dict[str, Any] = {}
    if inference_precision_hint:
        config["INFERENCE_PRECISION_HINT"] = inference_precision_hint
    compiled = core.compile_model(model, "CPU", config) if config else core.compile_model(
        model, "CPU"
    )
    observed: str | None = None
    raw: str | None = None
    try:
        value = compiled.get_property("INFERENCE_PRECISION_HINT")
        raw = str(value)
        lowered = raw.lower().replace(" ", "")
        if "f16" in lowered or "float16" in lowered:
            observed = "fp16"
        elif "bf16" in lowered:
            observed = "bf16"
        elif "f32" in lowered or "float32" in lowered:
            observed = "fp32"
        else:
            observed = raw
    except Exception as exc:  # noqa: BLE001
        return {
            "observed_CPU_inference_precision": None,
            "inference_precision_hint_raw": None,
            "inference_precision_error": f"{type(exc).__name__}: {exc}",
            "requested_inference_precision_hint": inference_precision_hint,
        }
    return {
        "observed_CPU_inference_precision": observed,
        "inference_precision_hint_raw": raw,
        "requested_inference_precision_hint": inference_precision_hint,
    }


def build_precision_identity(
    *,
    requested_weight_format: WeightFormat,
    export_dir: Path,
    inference_precision_hint: str | None = None,
) -> dict[str, Any]:
    """Assemble requested vs observed IR vs observed CPU inference precision."""
    xml_path = find_openvino_ir_xml(export_dir)
    ir = inspect_openvino_ir_weight_precision(xml_path)
    cpu = inspect_compiled_cpu_inference_precision(
        xml_path,
        inference_precision_hint=inference_precision_hint,
    )
    identity = {
        "requested_weight_format": requested_weight_format,
        "observed_IR_weight_precision": ir["observed_IR_weight_precision"],
        "observed_CPU_inference_precision": cpu.get(
            "observed_CPU_inference_precision"
        ),
        "ir_inspection": ir,
        "cpu_inference_inspection": cpu,
        "authority": IMPLEMENTATION_REWORK3_AUTH,
    }
    return identity


def assert_requested_ir_precision(
    *,
    requested_weight_format: WeightFormat,
    observed_IR_weight_precision: str,
) -> None:
    """Fail closed: requested fp16 must not silently accept FP32 IR (F008)."""
    if requested_weight_format == "fp16" and observed_IR_weight_precision != "fp16":
        raise ValueError(
            "requested_weight_format=fp16 but observed_IR_weight_precision="
            f"{observed_IR_weight_precision!r}; refusing to label FP32 IR as OV-FP16"
        )
    if requested_weight_format == "int8" and observed_IR_weight_precision not in {
        "int8",
        "fp16",
        "fp32",
    }:
        # INT8 path still records observation; strict int8 element typing varies.
        return


def _compress_openvino_ir_to_fp16(xml_path: Path) -> Path:
    """Rewrite IR weights with OpenVINO compress_to_fp16 storage transform."""
    import openvino as ov

    core = ov.Core()
    model = core.read_model(str(xml_path))
    # Overwrite in place — same basename expected by ST openvino backend.
    ov.save_model(model, str(xml_path), compress_to_fp16=True)
    return xml_path


def export_openvino_model(
    *,
    model_dir: Path,
    export_dir: Path,
    weight_format: WeightFormat,
    calibration_texts: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Export local pinned checkpoint to OpenVINO via Sentence Transformers.

    Pooling/normalization remain on the ST path after reload — this does not
    ship raw token-embedding export alone as the encode surface.

    For ``fp16``, Optimum ``OVConfig(dtype="fp16")`` is requested and the saved
    IR is verified (and FP16-compressed via ``ov.save_model`` if needed).
    ``INFERENCE_PRECISION_HINT`` alone is never treated as proof of FP16 IR.
    """
    from sentence_transformers import SentenceTransformer

    require_embedding_artifacts(
        model_dir,
        expected_model_id=EXPECTED_MODEL_ID,
        expected_revision=EXPECTED_MODEL_REVISION,
        expected_dimension=EXPECTED_DIMENSION,
    )
    export_dir.mkdir(parents=True, exist_ok=True)

    model_kwargs: dict[str, Any] = {"export": True}
    quant_note: str | None = None
    export_method: list[str] = ["sentence_transformers_openvino_backend"]

    if weight_format == "fp16":
        # Sentence Transformers forwards model_kwargs["ov_config"] as an OpenVINO
        # *runtime* dict or JSON path — not optimum.intel.OVConfig. Passing OVConfig
        # raises TypeError. FP16 *IR storage* is established after save via
        # ov.save_model(..., compress_to_fp16=True) below (fail-closed by inspection).
        export_method.append("openvino_compress_to_fp16_after_export")
    elif weight_format == "int8":
        try:
            from optimum.intel import OVWeightQuantizationConfig

            model_kwargs["quantization_config"] = OVWeightQuantizationConfig(bits=8)
            quant_note = "ov_weight_quantization_int8"
            export_method.append("ov_weight_quantization_int8")
        except Exception:  # noqa: BLE001
            quant_note = "static_quantized_openvino_fallback"
            export_method.append("static_quantized_openvino_fallback")

    model = SentenceTransformer(
        str(model_dir),
        backend="openvino",
        device="cpu",
        trust_remote_code=False,
        local_files_only=True,
        model_kwargs=model_kwargs,
    )
    model.save_pretrained(str(export_dir))

    if weight_format == "int8" and quant_note == "static_quantized_openvino_fallback":
        from sentence_transformers import export_static_quantized_openvino_model

        kwargs: dict[str, Any] = {
            "model": model,
            "quantization_config": None,
            "model_name_or_path": str(export_dir),
        }
        if calibration_texts:
            kwargs["dataset_name"] = None
        try:
            export_static_quantized_openvino_model(**kwargs)
        except TypeError:
            export_static_quantized_openvino_model(
                model,
                quantization_config=None,
                model_name_or_path=str(export_dir),
            )

    xml_path = find_openvino_ir_xml(export_dir)
    pre_ir = inspect_openvino_ir_weight_precision(xml_path)
    compressed = False
    if (
        weight_format == "fp16"
        and pre_ir["observed_IR_weight_precision"] != "fp16"
    ):
        _compress_openvino_ir_to_fp16(xml_path)
        compressed = True
        export_method.append("openvino_save_model_compress_to_fp16")

    precision_identity = build_precision_identity(
        requested_weight_format=weight_format,
        export_dir=export_dir,
        inference_precision_hint="f16" if weight_format == "fp16" else None,
    )
    assert_requested_ir_precision(
        requested_weight_format=weight_format,
        observed_IR_weight_precision=str(
            precision_identity["observed_IR_weight_precision"]
        ),
    )

    tree = hash_export_tree(export_dir)
    return {
        "requested_weight_format": weight_format,
        # Backward-compatible alias — means requested, not observed.
        "weight_format": weight_format,
        "model_dir": str(model_dir),
        "export_dir": str(export_dir),
        "quantization": quant_note,
        "export_method": export_method,
        "fp16_storage_compression_applied": compressed,
        "precision_identity": precision_identity,
        "pre_compress_ir_inspection": pre_ir,
        "export_tree": tree,
        "backend": "openvino",
        "device": "cpu",
    }


def load_openvino_st_model(
    *,
    model_or_export_dir: Path,
    weight_format: WeightFormat,
    require_ir_match: bool = True,
) -> tuple[Any, dict[str, Any]]:
    """Load ST OpenVINO backend and return (model, precision_identity) (F008)."""
    from sentence_transformers import SentenceTransformer

    precision_identity = build_precision_identity(
        requested_weight_format=weight_format,
        export_dir=model_or_export_dir,
        inference_precision_hint="f16" if weight_format == "fp16" else None,
    )
    if require_ir_match:
        assert_requested_ir_precision(
            requested_weight_format=weight_format,
            observed_IR_weight_precision=str(
                precision_identity["observed_IR_weight_precision"]
            ),
        )

    model_kwargs: dict[str, Any] = {}
    if weight_format == "int8":
        candidates = [
            "openvino/openvino_model_qint8_quantized.xml",
            "openvino_model_qint8_quantized.xml",
            "openvino/openvino_model_qint8_avg_pool.xml",
            "openvino/openvino_model.xml",
            "openvino_model.xml",
        ]
        for rel in candidates:
            if (model_or_export_dir / rel).is_file() or (
                model_or_export_dir / Path(rel).name
            ).is_file():
                model_kwargs["file_name"] = rel
                break

    kwargs: dict[str, Any] = {
        "backend": "openvino",
        "device": "cpu",
        "trust_remote_code": False,
        "local_files_only": True,
    }
    if model_kwargs:
        kwargs["model_kwargs"] = model_kwargs
    model = SentenceTransformer(str(model_or_export_dir), **kwargs)
    return model, precision_identity


def _st_encode_documents(
    model: Any,
    texts: Sequence[str],
    *,
    batch_size: int = FROZEN_BATCH_SIZE,
    normalize: bool = FROZEN_NORMALIZE,
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
        vec = [float(x) for x in row.tolist()]
        if normalize:
            vec = _normalize_vector(vec)
        out.append(vec)
    return out


def _st_encode_query(
    model: Any,
    text: str,
    *,
    query_text_contract: str,
    normalize: bool = FROZEN_NORMALIZE,
) -> list[float]:
    if query_text_contract == MODEL_QUERY_PROMPT_V1:
        prompts = getattr(model, "prompts", None)
        if not isinstance(prompts, dict) or MODEL_QUERY_PROMPT_NAME not in prompts:
            raise RuntimeError(
                f"{MODEL_QUERY_PROMPT_V1} requires prompts[{MODEL_QUERY_PROMPT_NAME!r}]"
            )
        vector = model.encode(
            text,
            prompt_name=MODEL_QUERY_PROMPT_NAME,
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
    vec = [float(x) for x in vector.tolist()]
    if normalize:
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


def smoke_encode_compat(
    model: Any,
    *,
    query_text_contract: str,
) -> dict[str, Any]:
    """Stage-0 embed smoke: one document + one query, dim/finite/normalize."""
    doc_vecs = _st_encode_documents(model, ["cpu-ov stage0 document smoke"])
    q_vec = _st_encode_query(
        model,
        "cpu-ov stage0 query smoke",
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


def execute_export_compat(
    *,
    export_dir: Path,
    model_dir: Path,
    weight_format: WeightFormat = "fp16",
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    if weight_format != "fp16":
        raise ValueError(
            "Stage-0 export_compat is FP16-only; use execute_export_int8 after "
            "INT8 eligibility opens"
        )
    identity = verify_local_model_identity(model_dir)
    export_meta = export_openvino_model(
        model_dir=model_dir,
        export_dir=export_dir,
        weight_format="fp16",
    )
    model, precision_identity = load_openvino_st_model(
        model_or_export_dir=export_dir,
        weight_format="fp16",
    )
    query_contract = resolve_production_query_contract()
    smoke = smoke_encode_compat(model, query_text_contract=query_contract)
    payload = {
        "status": "ok" if smoke["ok"] else "failed",
        "stage_id": "export_compat",
        "ok": bool(smoke["ok"]),
        "authority": IMPLEMENTATION_REWORK_AUTH,
        "rework3_authority": IMPLEMENTATION_REWORK3_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "requested_weight_format": "fp16",
        "weight_format": "fp16",
        "precision_identity": precision_identity,
        "local_model_identity": identity,
        "export": export_meta,
        "smoke": smoke,
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
        "repo_root": str(repo_root) if repo_root else None,
    }
    return _maybe_write_evidence(
        payload,
        evidence_dir=evidence_dir,
        stem="export_compat_fp16",
    )


def execute_export_int8(
    *,
    export_dir: Path,
    model_dir: Path,
    calibration_texts: Sequence[str] | None = None,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    identity = verify_local_model_identity(model_dir)
    export_meta = export_openvino_model(
        model_dir=model_dir,
        export_dir=export_dir,
        weight_format="int8",
        calibration_texts=calibration_texts,
    )
    model, precision_identity = load_openvino_st_model(
        model_or_export_dir=export_dir,
        weight_format="int8",
        require_ir_match=False,
    )
    query_contract = resolve_production_query_contract()
    smoke = smoke_encode_compat(model, query_text_contract=query_contract)
    payload = {
        "status": "ok" if smoke["ok"] else "failed",
        "stage_id": "export_int8",
        "ok": bool(smoke["ok"]),
        "authority": IMPLEMENTATION_REWORK_AUTH,
        "rework3_authority": IMPLEMENTATION_REWORK3_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "requested_weight_format": "int8",
        "weight_format": "int8",
        "precision_identity": precision_identity,
        "local_model_identity": identity,
        "export": export_meta,
        "smoke": smoke,
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
        "repo_root": str(repo_root) if repo_root else None,
    }
    return _maybe_write_evidence(
        payload,
        evidence_dir=evidence_dir,
        stem="export_int8",
    )


def execute_screen(
    *,
    export_dir: Path,
    weight_format: WeightFormat,
    repo_root: Path,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    children_by_id = load_children_by_id(repo_root=repo_root)
    all_ids = list(children_by_id.keys())
    # Stable order from harness selection (sha256 ascending).
    selected_ids = select_screen_chunk_ids(sorted(all_ids))
    chunks = [children_by_id[cid] for cid in selected_ids]
    rows = document_embedding_texts(chunks)
    texts = [t for _, _, t in rows]

    model, precision_identity = load_openvino_st_model(
        model_or_export_dir=export_dir,
        weight_format=weight_format,
    )
    query_contract = resolve_production_query_contract()
    embedder = OpenVinoSTEmbedder(
        model,
        weight_format=weight_format,
        query_text_contract=query_contract,
        precision_identity=precision_identity,
    )
    cpu_before = capture_cpu_host_runtime_facts(
        embedder=embedder, batch_size=FROZEN_BATCH_SIZE
    )
    started = time.perf_counter()
    vectors = embedder.embed_documents(texts)
    encode_s = time.perf_counter() - started
    cpu_after = capture_cpu_host_runtime_facts(
        embedder=embedder, batch_size=FROZEN_BATCH_SIZE
    )
    if len(vectors) != len(texts):
        raise RuntimeError("screen encode length mismatch")
    for vec in vectors:
        if len(vec) != EXPECTED_DIMENSION or not _finite(vec):
            raise RuntimeError("screen vector validation failed")

    chunks_per_sec = float(len(texts)) / encode_s if encode_s > 0 else float("inf")
    projected = project_full_minutes(chunks_per_sec)
    stage_id = "screen_fp16" if weight_format == "fp16" else "screen_int8"
    payload = {
        "status": "ok",
        "stage_id": stage_id,
        "ok": True,
        "authority": IMPLEMENTATION_REWORK_AUTH,
        "rework2_authority": IMPLEMENTATION_REWORK2_AUTH,
        "rework3_authority": IMPLEMENTATION_REWORK3_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "requested_weight_format": weight_format,
        "precision_identity": precision_identity,
        "weight_format": weight_format,
        "screen_child_count": len(texts),
        "screen_chunk_ids_digest": sha256_text("\n".join(selected_ids)),
        "encode_wall_s": encode_s,
        "chunks_per_sec": chunks_per_sec,
        "projected_full_minutes": projected,
        "full_wall_minutes": None,  # never fill from projection
        "dimension": EXPECTED_DIMENSION,
        "batch_size": FROZEN_BATCH_SIZE,
        "normalize": FROZEN_NORMALIZE,
        "export_dir": str(export_dir),
        "document_embedding_text_digests": [
            {"chunk_id": cid, "embedding_text_sha256": th} for cid, th, _ in rows
        ],
        "cpu_host_runtime_before": cpu_before,
        "cpu_host_runtime_after": cpu_after,
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
        "note": "projected_full_minutes is screening only; not confirmation evidence",
    }
    return _maybe_write_evidence(
        payload,
        evidence_dir=evidence_dir,
        stem=stage_id,
    )


def _load_cuda_fp16_reference_embedder() -> tuple[Any, dict[str, Any]]:
    """D2 G1 selected candidate: CUDA / FP16 / batch 32."""
    from offline_rag.config import load_settings
    from offline_rag.dense.embedder import make_embedder, observe_embedder_execution_facts

    environ = dict(os.environ)
    environ["OFFLINE_RAG_EMBEDDING_DEVICE"] = "cuda"
    environ["OFFLINE_RAG_EMBEDDING_PRECISION"] = "fp16"
    environ["OFFLINE_RAG_EMBEDDING_BATCH_SIZE"] = str(FROZEN_BATCH_SIZE)
    settings = load_settings(environ=environ)
    embedder = make_embedder(settings)
    load = getattr(embedder, "_load", None)
    if callable(load):
        load()
    facts = observe_embedder_execution_facts(embedder)
    return embedder, facts


def _topk_ids(
    query_vec: list[float],
    doc_vecs: dict[str, list[float]],
    doc_order: list[str],
    *,
    k: int = 10,
) -> list[str]:
    scored = [(_cosine(query_vec, doc_vecs[cid]), cid) for cid in doc_order]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [cid for _, cid in scored[:k]]


def execute_parity(
    *,
    export_dir: Path,
    weight_format: WeightFormat,
    repo_root: Path,
    evidence_dir: Path | None = None,
    reference_embedder: Any | None = None,
    reference_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    children_by_id = load_children_by_id(repo_root=repo_root)
    all_ids = sorted(children_by_id.keys())
    doc_ids, query_ids = select_parity_populations(all_ids)
    docs = [children_by_id[cid] for cid in doc_ids]
    queries = [children_by_id[cid] for cid in query_ids]
    doc_rows = document_embedding_texts(docs)
    query_contract = resolve_production_query_contract()

    if reference_embedder is None:
        reference_embedder, reference_facts = _load_cuda_fp16_reference_embedder()
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

    cand_model, precision_identity = load_openvino_st_model(
        model_or_export_dir=export_dir,
        weight_format=weight_format,
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
            cand_model,
            chunk.text,
            query_text_contract=query_contract,
        )
        for chunk in queries
    }

    issues: list[str] = []
    for label, vectors in (
        ("ref_doc", ref_docs),
        ("cand_doc", cand_docs),
        ("ref_query", ref_queries),
        ("cand_query", cand_queries),
    ):
        for cid, vec in vectors.items():
            if len(vec) != EXPECTED_DIMENSION:
                issues.append(f"{label}:{cid}:dim")
            if not _finite(vec):
                issues.append(f"{label}:{cid}:non_finite")
            if FROZEN_NORMALIZE:
                n = _l2(vec)
                if not (0.99 <= n <= 1.01):
                    issues.append(f"{label}:{cid}:norm={n}")

    doc_cosines = [_cosine(ref_docs[cid], cand_docs[cid]) for cid in doc_ids]
    query_cosines = [_cosine(ref_queries[cid], cand_queries[cid]) for cid in query_ids]

    top1_agree = 0
    top10_overlaps: list[float] = []
    per_query: list[dict[str, Any]] = []
    for qid in query_ids:
        ref_top = _topk_ids(ref_queries[qid], ref_docs, doc_ids, k=10)
        cand_top = _topk_ids(cand_queries[qid], cand_docs, doc_ids, k=10)
        agree = ref_top[0] == cand_top[0]
        if agree:
            top1_agree += 1
        overlap = len(set(ref_top) & set(cand_top)) / 10.0
        top10_overlaps.append(overlap)
        per_query.append(
            {
                "query_chunk_id": qid,
                "top1_agree": agree,
                "top10_set_overlap": overlap,
                "ref_top1_chunk_id": ref_top[0],
                "cand_top1_chunk_id": cand_top[0],
            }
        )

    metrics = {
        "median_document_vector_cosine": float(statistics.median(doc_cosines)),
        "min_document_vector_cosine": float(min(doc_cosines)),
        "median_query_vector_cosine": float(statistics.median(query_cosines)),
        "min_query_vector_cosine": float(min(query_cosines)),
        "top1_agreement": top1_agree,
        "top1_agreement_of": 16,
        "mean_top10_set_overlap": float(statistics.fmean(top10_overlaps)),
        "min_top10_set_overlap": float(min(top10_overlaps)),
    }
    parity_ok = parity_thresholds_pass(metrics) and not issues
    stage_id = "parity_fp16" if weight_format == "fp16" else "parity_int8"
    payload = {
        "status": "ok" if parity_ok else "failed",
        "stage_id": stage_id,
        "ok": True,  # stage completed; parity_ok is the semantic gate
        "parity_ok": parity_ok,
        "authority": IMPLEMENTATION_REWORK_AUTH,
        "rework3_authority": IMPLEMENTATION_REWORK3_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "parity_contract": PARITY_CONTRACT_ID,
        "requested_weight_format": weight_format,
        "precision_identity": precision_identity,
        "weight_format": weight_format,
        "thresholds": PARITY_THRESHOLDS,
        "metrics": metrics,
        "vector_validation_issues": issues,
        "per_query": per_query,
        "reference_lane": {
            "device": "cuda",
            "precision": "fp16",
            "batch_size": FROZEN_BATCH_SIZE,
            "observed": reference_facts,
        },
        "candidate_lane": {
            "backend": "openvino",
            "device": "cpu",
            "weight_format": weight_format,
            "batch_size": FROZEN_BATCH_SIZE,
            "export_dir": str(export_dir),
        },
        "query_text_contract": query_contract,
        "document_embedding_text_digests": [
            {"chunk_id": cid, "embedding_text_sha256": th} for cid, th, _ in doc_rows
        ],
        "selection": {
            "document_chunk_ids_digest": sha256_text("\n".join(doc_ids)),
            "query_chunk_ids_digest": sha256_text("\n".join(query_ids)),
            "document_count": len(doc_ids),
            "query_count": len(query_ids),
        },
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
        "note": "No private chunk text is included in this evidence artifact.",
    }
    return _maybe_write_evidence(
        payload,
        evidence_dir=evidence_dir,
        stem=stage_id,
    )


def execute_full_confirm(
    *,
    export_dir: Path,
    weight_format: WeightFormat,
    repo_root: Path,
    evidence_dir: Path | None = None,
    work_root: Path | None = None,
) -> dict[str, Any]:
    """Production-like 1296 confirmation via isolated ``run_indexing`` (F006).

    Injects the OpenVINO ST embedder into Seneca's dense indexing path on a
    cold isolated tree. Counts and practical_timing come from indexing output —
    not a synthesized encode-only benchmark.
    """
    from offline_rag.config import load_settings
    from offline_rag.dense.d2_campaign import CORPUS_NAME
    from offline_rag.dense.d2_execution import prepare_isolated_tree
    from offline_rag.dense.pipeline import run_indexing
    from offline_rag.domain.indexing import IndexingStatus

    isolation = work_root or (
        repo_root / "data" / "16k_d_cpu_ov_work" / f"full_confirm_{weight_format}"
    )
    prepare_isolated_tree(isolation, repo_root=repo_root)

    environ = dict(os.environ)
    environ["OFFLINE_RAG_DATA_DIR"] = str(isolation.resolve())
    environ["OFFLINE_RAG_EMBEDDING_DEVICE"] = "cpu"
    environ["OFFLINE_RAG_EMBEDDING_BATCH_SIZE"] = str(FROZEN_BATCH_SIZE)
    environ.pop("OFFLINE_RAG_DIAG_DENSE_PROFILE", None)

    settings = load_settings(environ=environ)
    model, precision_identity = load_openvino_st_model(
        model_or_export_dir=export_dir,
        weight_format=weight_format,
    )
    query_contract = resolve_production_query_contract()
    embedder = OpenVinoSTEmbedder(
        model,
        weight_format=weight_format,
        query_text_contract=query_contract,
        precision_identity=precision_identity,
    )
    cpu_before = capture_cpu_host_runtime_facts(
        embedder=embedder, batch_size=FROZEN_BATCH_SIZE
    )
    started = time.perf_counter()
    report = run_indexing(
        settings=settings,
        corpus_name=CORPUS_NAME,
        embedder=embedder,
    )
    wall_s = time.perf_counter() - started
    cpu_after = capture_cpu_host_runtime_facts(
        embedder=embedder, batch_size=FROZEN_BATCH_SIZE
    )

    meta = report.metadata or {}
    practical_timing = meta.get("practical_timing")
    execution = meta.get("dense_execution") or {}
    dimension = int(
        execution.get("embedding_dimension")
        or getattr(embedder, "dimension", EXPECTED_DIMENSION)
    )
    generated = int(report.embeddings_generated)
    reused = int(report.embeddings_reused)
    failed = int(report.embeddings_failed)
    vectors_materialized = int(report.vectors_materialized)
    full_wall_minutes = wall_s / 60.0
    ok = (
        report.status is IndexingStatus.SUCCESS
        and generated == EXPECTED_CHILD_COUNT
        and reused == 0
        and failed == 0
        and vectors_materialized == EXPECTED_CHILD_COUNT
        and dimension == EXPECTED_DIMENSION
    )

    payload = {
        "status": "ok" if ok else "failed",
        "stage_id": "full_confirm",
        "ok": ok,
        "authority": IMPLEMENTATION_REWORK_AUTH,
        "rework2_authority": IMPLEMENTATION_REWORK2_AUTH,
        "rework3_authority": IMPLEMENTATION_REWORK3_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "selected_candidate": weight_format,
        "requested_weight_format": weight_format,
        "precision_identity": precision_identity,
        "confirmation_mode": "production_indexing_isolated_cold_tree",
        "workload": WORKLOAD_LABEL,
        "chunk_set_id": EXPECTED_CHUNK_SET_ID,
        "corpus_name": CORPUS_NAME,
        "work_root": str(isolation),
        "indexing_status": str(report.status),
        "embeddings_generated": generated,
        "embeddings_reused": reused,
        "embeddings_failed": failed,
        "vectors_materialized": vectors_materialized,
        "children_total": int(report.children_total),
        "dimension": dimension,
        "full_wall_minutes": full_wall_minutes,
        "wall_clock_s": wall_s,
        "duration_ms": report.duration_ms,
        "practical_timing": practical_timing,
        "dense_execution": execution,
        "projected_full_minutes": None,
        "batch_size": FROZEN_BATCH_SIZE,
        "normalize": FROZEN_NORMALIZE,
        "export_dir": str(export_dir),
        "query_text_contract": query_contract,
        "cpu_host_runtime_before": cpu_before,
        "cpu_host_runtime_after": cpu_after,
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
        "note": (
            "Production-like confirmation via run_indexing on an isolated cold "
            "tree with OpenVINO embedder injected. Counts and practical_timing "
            "are indexing outputs; projections are never confirmation evidence."
        ),
    }
    return _maybe_write_evidence(
        payload,
        evidence_dir=evidence_dir,
        stem=f"full_confirm_{weight_format}",
    )


def _environment_fingerprint() -> dict[str, Any]:
    import sys

    versions: dict[str, Any] = {
        "python": (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        ),
        "sentence_transformers": None,
        "openvino": None,
        "optimum": None,
        "optimum_intel": None,
    }
    for mod_name, key in (
        ("sentence_transformers", "sentence_transformers"),
        ("openvino", "openvino"),
        ("optimum", "optimum"),
        ("optimum_intel", "optimum_intel"),
    ):
        try:
            mod = __import__(mod_name)
            versions[key] = getattr(mod, "__version__", "present_unknown_version")
        except Exception:  # noqa: BLE001
            versions[key] = None
    return versions


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
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    payload = dict(payload)
    payload["evidence_path"] = str(path)
    payload["evidence_sha256"] = sha256_file(path)
    return payload


__all__ = [
    "OpenVinoSTEmbedder",
    "assert_requested_ir_precision",
    "build_precision_identity",
    "capture_cpu_host_runtime_facts",
    "classify_ir_weight_precision",
    "document_embedding_texts",
    "execute_export_compat",
    "execute_export_int8",
    "execute_full_confirm",
    "execute_parity",
    "execute_screen",
    "export_openvino_model",
    "find_openvino_ir_xml",
    "inspect_compiled_cpu_inference_precision",
    "inspect_openvino_ir_weight_precision",
    "load_children_by_id",
    "load_openvino_st_model",
    "smoke_encode_compat",
]
