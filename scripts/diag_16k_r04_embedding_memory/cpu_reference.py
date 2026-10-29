"""Separately authorized one-process CPU ONNX parity reference executor.

This entry point never probes CUDA. It is included for the later execution
tranche and is not invoked by harness implementation validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

if __package__:
    from .contract import (
        ACCEPTED_DESIGN_SUBJECT,
        EXPECTED_BATCH_SIZE,
        EXPECTED_MODEL_REVISION,
    )
    from .freeze_workload import reconstruct_workload_with_texts
    from .runtime import (
        claim_single_cell_process,
        complete_cell_process_claim,
        require_local_untracked_path,
        safe_cell_evidence,
        verify_execution_authority,
    )
else:
    from contract import (
        ACCEPTED_DESIGN_SUBJECT,
        EXPECTED_BATCH_SIZE,
        EXPECTED_MODEL_REVISION,
    )
    from freeze_workload import reconstruct_workload_with_texts
    from runtime import (
        claim_single_cell_process,
        complete_cell_process_claim,
        require_local_untracked_path,
        safe_cell_evidence,
        verify_execution_authority,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _deadline_handler(_signum: int, _frame: Any) -> None:
    raise TimeoutError("campaign deadline exceeded during CPU reference")


def run_reference(
    *,
    authority_path: Path,
    cell_spec_path: Path,
    workload_path: Path,
    output_path: Path,
    vectors_output_path: Path,
    chunk_manifest_path: Path,
    corpus_manifest_path: Path,
    chunks_root: Path,
    embeddings_root: Path,
    incident_identity_path: Path | None,
    source_document_id: str,
    source_sha256: str,
    settings_path: Path | None = None,
    model_dir_arg: Path | None = None,
) -> dict[str, Any]:
    current_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    spec = json.loads(cell_spec_path.read_text(encoding="utf-8"))
    workload = json.loads(workload_path.read_text(encoding="utf-8"))
    if spec.get("cell_id") != "CPU_ONNX_REFERENCE" or spec.get("replicate") != 1:
        raise ValueError("CPU reference requires its single frozen cell spec")
    if spec.get("workload_sha256") != workload.get("workload_sha256"):
        raise ValueError("CPU reference workload digest mismatch")
    if spec.get("expected_model_revision") != EXPECTED_MODEL_REVISION:
        raise ValueError("CPU reference model revision mismatch")
    spec_digest = _sha256_file(cell_spec_path)
    verified = verify_execution_authority(
        authority_path,
        current_commit=current_commit,
        cell_id="CPU_ONNX_REFERENCE",
        replicate=1,
        cell_spec_sha256=spec_digest,
    )
    if authority.get("workload_sha256") != workload.get("workload_sha256"):
        raise PermissionError("execution authority does not bind this workload")
    output_paths = [
        require_local_untracked_path(path, repo_root=ROOT)
        for path in (output_path, vectors_output_path)
    ]
    if len(set(output_paths)) != len(output_paths):
        raise ValueError("CPU reference evidence and vector paths must be distinct")
    if any(path.exists() for path in output_paths):
        raise FileExistsError("CPU reference output already exists; retry is forbidden")

    from offline_rag.config.loader import load_settings
    from offline_rag.dense.embedding_artifacts import inspect_selected_representation
    from offline_rag.dense.onnx_embedder import (
        FROZEN_ONNX_PROVIDER,
        SentenceTransformersOnnxEmbedder,
    )
    from offline_rag.dense.provision import resolve_embedding_model_dir

    settings = load_settings(yaml_paths=[settings_path] if settings_path else None)
    model_dir = resolve_embedding_model_dir(
        embedding_artifacts_root=settings.paths.embedding_artifacts,
        model_path=model_dir_arg,
    )
    identity = (
        json.loads(incident_identity_path.read_text(encoding="utf-8"))
        if incident_identity_path
        else None
    )
    reconstructed, texts, query_texts = reconstruct_workload_with_texts(
        chunk_manifest_path=chunk_manifest_path,
        corpus_manifest_path=corpus_manifest_path,
        chunks_root=chunks_root,
        embeddings_root=embeddings_root,
        model_dir=model_dir,
        settings=settings,
        source_document_id=source_document_id,
        expected_source_sha256=source_sha256,
        incident_identity=identity,
    )
    if reconstructed["workload_sha256"] != workload["workload_sha256"]:
        raise ValueError("reconstructed CPU reference workload digest mismatch")
    if len(texts) != EXPECTED_BATCH_SIZE:
        raise ValueError("CPU reference input count mismatch")

    claim_path = claim_single_cell_process(
        authority_path=authority_path,
        campaign_id=str(authority.get("campaign_id", "")),
        cell_id="CPU_ONNX_REFERENCE",
        replicate=1,
        spec_sha256=spec_digest,
        spec_path=cell_spec_path,
        workload_path=workload_path,
        authority=authority,
        workload=workload,
        cell_spec=spec,
        implementation_subject=current_commit,
    )
    signal.signal(signal.SIGALRM, _deadline_handler)
    remaining_deadline = claim_path.deadline_seconds - (
        time.monotonic() - claim_path.claimed_monotonic
    )
    if remaining_deadline <= 0:
        raise TimeoutError("campaign deadline elapsed before CPU reference start")
    signal.setitimer(signal.ITIMER_REAL, remaining_deadline)
    representation = inspect_selected_representation(
        model_dir,
        "onnx_fp32_v1",
        expected_model_id=settings.indexing.embedding.model_id,
        expected_revision=settings.indexing.embedding.revision,
        expected_dimension=settings.indexing.embedding.dimension,
    )
    if representation.readiness.value != "READY":
        raise RuntimeError("qualified CPU ONNX representation is not ready")
    embedder = SentenceTransformersOnnxEmbedder(
        representation=representation,
        model_id=settings.indexing.embedding.model_id,
        model_revision=settings.indexing.embedding.revision,
        dimension=settings.indexing.embedding.dimension,
        normalize=settings.indexing.embedding.normalize,
        batch_size=EXPECTED_BATCH_SIZE,
        query_text_contract="raw-query-v1",
    )
    if (
        embedder.provider != FROZEN_ONNX_PROVIDER
        or embedder.provider != "CPUExecutionProvider"
    ):
        raise RuntimeError("CPU ONNX reference selected an unexpected provider")
    started = time.monotonic()
    try:
        document_vectors = embedder.embed_documents(texts)
        query_vectors = [embedder.embed_query(text) for text in query_texts[:16]]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"CPU ONNX reference failed: {type(exc).__name__}") from None
    duration = time.monotonic() - started
    signal.setitimer(signal.ITIMER_REAL, 0.0)
    vector_payload = json.dumps(
        {"documents": document_vectors, "queries": query_vectors},
        separators=(",", ":"),
        allow_nan=False,
    )
    vectors_output_path.parent.mkdir(parents=True, exist_ok=True)
    vectors_output_path.write_text(vector_payload + "\n", encoding="utf-8")
    result = safe_cell_evidence(
        {
            "schema": "seneca-16k-r04-embedding-memory-cell-v1",
            "authority": verified["authority"],
            "design_subject": ACCEPTED_DESIGN_SUBJECT,
            "implementation_subject": current_commit,
            "cell_id": "CPU_ONNX_REFERENCE",
            "replicate": 1,
            "cell_spec_sha256": spec_digest,
            "effective_controls": {
                "dtype_mode": "cpu_onnx_fp32",
                "disable_cache": False,
                "attention_backend": None,
                "batch_strategy": "fixed32",
                "profiler_characterization": False,
            },
            "workload_sha256": workload["workload_sha256"],
            "model_revision": workload["model"]["revision"],
            "runtime_versions": {
                "provider": embedder.provider,
                "profile": "cpu_onnx_fp32_v1",
            },
            "encode_result": {
                "status": "SUCCESS",
                "document_vector_count": len(document_vectors),
                "query_vector_count": len(query_vectors),
                "vector_dimension": settings.indexing.embedding.dimension,
                "ordered_chunk_ids_sha256": workload["ordered_chunk_ids_sha256"],
                "vectors_sha256": hashlib.sha256(
                    vector_payload.encode("utf-8")
                ).hexdigest(),
                "vectors_path": str(vectors_output_path),
            },
            "duration_seconds": duration,
            "status": "SUCCESS",
        },
        private_texts=texts,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    complete_cell_process_claim(
        claim_path,
        duration_seconds=duration,
        result_status="SUCCESS",
        evidence_path=output_path,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority", required=True, type=Path)
    parser.add_argument("--cell-spec", required=True, type=Path)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vectors-output", required=True, type=Path)
    parser.add_argument("--chunk-manifest", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--chunks-root", required=True, type=Path)
    parser.add_argument("--embeddings-root", required=True, type=Path)
    parser.add_argument("--incident-identity", type=Path)
    parser.add_argument("--source-document-id", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--model-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        run_reference(
            authority_path=args.authority,
            cell_spec_path=args.cell_spec,
            workload_path=args.workload,
            output_path=args.output,
            vectors_output_path=args.vectors_output,
            chunk_manifest_path=args.chunk_manifest,
            corpus_manifest_path=args.corpus_manifest,
            chunks_root=args.chunks_root,
            embeddings_root=args.embeddings_root,
            incident_identity_path=args.incident_identity,
            source_document_id=args.source_document_id,
            source_sha256=args.source_sha256,
            settings_path=args.settings,
            model_dir_arg=args.model_dir,
        )
    except PermissionError:
        print(
            "EXECUTION_BLOCKED: separate CPU reference authority required",
            file=sys.stderr,
        )
        return 20
    except Exception as exc:  # noqa: BLE001
        print(f"CPU_REFERENCE_FAILED: {type(exc).__name__}", file=sys.stderr)
        return 10
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
