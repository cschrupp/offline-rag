"""CPU-only reconstruction of the frozen 32-item R04 workload.

The command reads local immutable artifacts and an already-provisioned tokenizer.
It never constructs a SentenceTransformer, imports PyTorch, creates CUDA state, or
serializes embedding text / tokenizer IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from offline_rag.chunking.persistence import (
    chunk_artifact_path,
    load_chunk_artifact,
    load_chunk_set_manifest,
)
from offline_rag.config.loader import load_settings
from offline_rag.core.document_metadata import resolve_document_title_v1
from offline_rag.core.ids import (
    embedding_id_from_parts,
    embedding_text_hash,
)
from offline_rag.dense.cache import try_load_reusable_embedding_artifact
from offline_rag.dense.config_hash import build_embedding_config_hash
from offline_rag.dense.provision import resolve_embedding_model_dir
from offline_rag.dense.searchable_units import (
    filter_dense_searchable_children,
)
from offline_rag.dense.text import (
    PlainEmbeddingTextBuilder,
    TitleSectionEmbeddingTextBuilder,
)
from offline_rag.ingestion.persistence import load_corpus_manifest
from offline_rag.retrieval.ranking_text import ranking_inputs_for_chunk

if __package__:
    from .contract import (
        EXPECTED_BATCH_SIZE,
        EXPECTED_MODEL_ID,
        EXPECTED_MODEL_REVISION,
        MODEL_QUERY_PROMPT_V1,
        RAW_QUERY_V1,
        FrozenItem,
        build_workload_manifest,
    )
    from .runtime import require_local_untracked_path
else:
    from contract import (
        EXPECTED_BATCH_SIZE,
        EXPECTED_MODEL_ID,
        EXPECTED_MODEL_REVISION,
        MODEL_QUERY_PROMPT_V1,
        RAW_QUERY_V1,
        FrozenItem,
        build_workload_manifest,
    )
    from runtime import require_local_untracked_path


class WorkloadFreezeError(RuntimeError):
    """Raised when the exact workload cannot be reconstructed safely."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _builder_for_settings(settings: Any) -> Any:
    pair = (
        settings.indexing.embedding_text.strategy,
        settings.indexing.embedding_text.contract_version,
    )
    if pair == (
        PlainEmbeddingTextBuilder.strategy,
        PlainEmbeddingTextBuilder.contract_version,
    ):
        return PlainEmbeddingTextBuilder()
    if pair == (
        TitleSectionEmbeddingTextBuilder.strategy,
        TitleSectionEmbeddingTextBuilder.contract_version,
    ):
        return TitleSectionEmbeddingTextBuilder()
    raise WorkloadFreezeError("unsupported embedding-text contract")


def _qwen_tokenizer_counts(
    *, model_dir: Path, texts: list[str], max_length: int
) -> list[int]:
    """Load only the local tokenizer and immediately discard token IDs."""
    try:
        from transformers import AutoTokenizer
    except Exception as exc:
        raise WorkloadFreezeError("local Qwen tokenizer is unavailable") from exc

    tokenizer = AutoTokenizer.from_pretrained(
        str(model_dir),
        local_files_only=True,
        trust_remote_code=False,
    )
    counts: list[int] = []
    for text in texts:
        encoded = tokenizer(
            text,
            add_special_tokens=True,
            truncation=True,
            max_length=max_length,
            padding=False,
            return_attention_mask=False,
            return_token_type_ids=False,
        )
        input_ids = encoded.get("input_ids")
        if input_ids is None:
            raise WorkloadFreezeError("tokenizer returned no input_ids")
        counts.append(len(input_ids))
        del encoded, input_ids
    del tokenizer
    return counts


def reconstruct_workload_with_texts(
    *,
    chunk_manifest_path: Path,
    corpus_manifest_path: Path,
    chunks_root: Path,
    embeddings_root: Path,
    model_dir: Path,
    settings: Any,
    source_document_id: str,
    expected_source_sha256: str,
    incident_identity: dict[str, Any] | None = None,
    expected_reused_count: int = 893,
    expected_desired_count: int = 1498,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Reconstruct production pending order and emit only safe identities."""
    if (
        settings.indexing.embedding.model_id != EXPECTED_MODEL_ID
        or settings.indexing.embedding.revision != EXPECTED_MODEL_REVISION
    ):
        raise WorkloadFreezeError("configured embedding model/revision mismatch")
    if not source_document_id.startswith("doc_"):
        raise WorkloadFreezeError("source document identity is malformed")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha256):
        raise WorkloadFreezeError("source SHA-256 must be lowercase hexadecimal")
    if source_document_id != f"doc_{expected_source_sha256}":
        raise WorkloadFreezeError("source document ID and source SHA-256 disagree")

    corpus = load_corpus_manifest(corpus_manifest_path)
    source_entries = {
        entry.document_id: entry
        for entry in corpus.documents
        if entry.document_id == source_document_id
    }
    source_entry = source_entries.get(source_document_id)
    if (
        source_entry is None
        or source_entry.source_content_hash != expected_source_sha256
    ):
        raise WorkloadFreezeError("incident source is absent or hash-mismatched")

    chunk_set = load_chunk_set_manifest(chunk_manifest_path)
    if corpus.corpus_id != chunk_set.corpus_id:
        raise WorkloadFreezeError("corpus and chunk-set identities disagree")
    entries = {entry.document_id: entry for entry in chunk_set.documents}
    if source_document_id not in entries:
        raise WorkloadFreezeError("incident source is absent from the chunk set")

    jobs: list[tuple[Any, str]] = []
    for entry in sorted(chunk_set.documents, key=lambda value: value.document_id):
        artifact_path = chunk_artifact_path(chunks_root, entry.chunk_artifact_id)
        if not artifact_path.is_file():
            raise WorkloadFreezeError("chunk artifact is missing")
        if f"art_{_sha256_file(artifact_path)}" != entry.chunk_artifact_hash:
            raise WorkloadFreezeError("chunk artifact digest mismatch")
        artifact = load_chunk_artifact(artifact_path)
        if (
            artifact.chunk_artifact_id != entry.chunk_artifact_id
            or artifact.document_id != entry.document_id
            or artifact.chunk_config_hash != chunk_set.chunk_config_hash
        ):
            raise WorkloadFreezeError("chunk artifact identity mismatch")
        jobs.extend(
            (chunk, artifact.chunk_artifact_id)
            for chunk in artifact.children
            if chunk.kind == "child"
        )
    jobs.sort(key=lambda item: item[0].chunk_id)
    if len(jobs) != chunk_set.total_child_count:
        raise WorkloadFreezeError("chunk-set child count mismatch")
    eligible, _excluded = filter_dense_searchable_children(jobs, settings.indexing)

    source_names = {entry.document_id: entry.source_name for entry in corpus.documents}
    builder = _builder_for_settings(settings)
    emb_cfg_hash = build_embedding_config_hash(settings)
    embedding = settings.indexing.embedding
    query_contract = settings.dense.query_text.contract_version
    if query_contract not in {RAW_QUERY_V1, MODEL_QUERY_PROMPT_V1}:
        raise WorkloadFreezeError("unsupported query-text contract")
    if query_contract == MODEL_QUERY_PROMPT_V1 and embedding.query_instruction:
        raise WorkloadFreezeError(
            "model query prompt cannot be combined with query_instruction"
        )
    model_ids: dict[str, tuple[str, str, str]] = {}
    pending_texts: list[str] = []
    pending_query_texts: list[str] = []
    reused_count = 0
    for chunk, _chunk_artifact_id in eligible:
        source_name = source_names.get(chunk.document_id)
        document_title = (
            resolve_document_title_v1(source_name)
            if builder.strategy == TitleSectionEmbeddingTextBuilder.strategy
            and source_name
            else None
        )
        inputs = ranking_inputs_for_chunk(
            chunk_text=chunk.text,
            section_path=list(chunk.section_path or []),
            document_title=document_title,
        )
        embedding_text = builder.build(inputs)
        artifact_text_hash = embedding_text_hash(embedding_text)
        embedding_text_for_encode = embedding_text
        if embedding.document_instruction:
            embedding_text_for_encode = (
                f"{embedding.document_instruction}{embedding_text_for_encode}"
            )
        artifact_id = embedding_id_from_parts(
            chunk.chunk_id,
            embedding_text_digest=artifact_text_hash,
            emb_cfg_hash=emb_cfg_hash,
        )
        reusable = try_load_reusable_embedding_artifact(
            embeddings_root,
            artifact_id,
            expected_chunk_id=chunk.chunk_id,
            expected_embedding_text_hash=artifact_text_hash,
            expected_embedding_config_hash=emb_cfg_hash,
            expected_dimension=embedding.dimension,
            expected_normalize=embedding.normalize,
            expected_model_id=embedding.model_id,
            expected_model_revision=embedding.revision,
            expected_adapter_contract=embedding.adapter_contract,
        )
        if reusable is not None:
            reused_count += 1
            continue
        encode_text_hash = hashlib.sha256(
            embedding_text_for_encode.encode("utf-8")
        ).hexdigest()
        query_input_text = embedding_text
        if query_contract == RAW_QUERY_V1 and embedding.query_instruction:
            query_input_text = f"{embedding.query_instruction}{query_input_text}"
        query_text_hash = hashlib.sha256(query_input_text.encode("utf-8")).hexdigest()
        model_ids[chunk.chunk_id] = (
            artifact_text_hash,
            encode_text_hash,
            query_text_hash,
        )
        pending_texts.append(embedding_text_for_encode)
        pending_query_texts.append(embedding_text)

    incident_identity_matches = bool(
        incident_identity
        and incident_identity.get("workspace_id")
        == "ws_464d92440ba343bf9372216e508e81b4"
        and incident_identity.get("pre_submit_revision") == 2
        and incident_identity.get("pre_submit_source_count") == 1
        and incident_identity.get("source_document_id") == source_document_id
        and incident_identity.get("source_sha256") == expected_source_sha256
        and incident_identity.get("corpus_id") == corpus.corpus_id
        and incident_identity.get("chunk_set_id") == chunk_set.chunk_set_id
        and incident_identity.get("desired_count") == len(eligible)
        and incident_identity.get("desired_count") == expected_desired_count
        and incident_identity.get("reused_count") == reused_count
        and incident_identity.get("reused_count") == expected_reused_count
        and incident_identity.get("first_pending_batch_count") == EXPECTED_BATCH_SIZE
    )
    if incident_identity_matches:
        workload_kind = "EXACT_INCIDENT_BATCH"
    else:
        workload_kind = "INCIDENT_ADJACENT_SUBSTITUTE"
    if len(pending_texts) < EXPECTED_BATCH_SIZE:
        raise WorkloadFreezeError("fewer than 32 pending embedding inputs found")

    selected_ids = list(model_ids.items())[:EXPECTED_BATCH_SIZE]
    selected_texts = pending_texts[:EXPECTED_BATCH_SIZE]
    selected_query_texts = pending_query_texts[:EXPECTED_BATCH_SIZE]
    config_path = model_dir / "config.json"
    if not config_path.is_file():
        raise WorkloadFreezeError("local Qwen config.json is missing")
    model_config = json.loads(config_path.read_text(encoding="utf-8"))
    max_length = int(model_config.get("max_position_embeddings", 0))
    if max_length <= 0:
        raise WorkloadFreezeError("Qwen max_position_embeddings is unavailable")
    token_counts = _qwen_tokenizer_counts(
        model_dir=model_dir,
        texts=selected_texts,
        max_length=max_length,
    )
    items = [
        FrozenItem(
            chunk_id=chunk_id,
            embedding_text_sha256=encode_hash,
            qwen_token_count=count,
            embedding_artifact_text_sha256=artifact_hash,
            query_input_sha256=query_hash,
        )
        for (chunk_id, (artifact_hash, encode_hash, query_hash)), count in zip(
            selected_ids, token_counts, strict=True
        )
    ]
    payload = build_workload_manifest(
        items=items,
        workload_kind=workload_kind,
        source_document_id=source_document_id,
        source_sha256=expected_source_sha256,
        corpus_id=corpus.corpus_id,
        chunk_set_id=chunk_set.chunk_set_id,
        embedding_config_hash=emb_cfg_hash,
        query_text_contract=query_contract,
        workspace_identity=(
            {
                "workspace_id": incident_identity["workspace_id"],
                "pre_submit_revision": incident_identity["pre_submit_revision"],
                "pre_submit_source_count": incident_identity["pre_submit_source_count"],
            }
            if incident_identity
            and {"workspace_id", "pre_submit_revision", "pre_submit_source_count"}
            <= set(incident_identity)
            else None
        ),
        model_id=embedding.model_id,
        model_revision=embedding.revision,
        reused_count=reused_count,
        desired_count=len(eligible),
    )
    return payload, selected_texts, selected_query_texts


def reconstruct_workload(
    **kwargs: Any,
) -> dict[str, Any]:
    """Return only the non-sensitive frozen workload manifest."""
    manifest, _private_texts, _private_query_texts = reconstruct_workload_with_texts(
        **kwargs
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-manifest", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--chunks-root", required=True, type=Path)
    parser.add_argument("--embeddings-root", required=True, type=Path)
    parser.add_argument("--source-document-id", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--incident-identity", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        settings = load_settings(yaml_paths=[args.settings] if args.settings else None)
        model_dir = resolve_embedding_model_dir(
            embedding_artifacts_root=settings.paths.embedding_artifacts,
            model_path=args.model_dir,
        )
        incident_identity = (
            json.loads(args.incident_identity.read_text(encoding="utf-8"))
            if args.incident_identity
            else None
        )
        payload = reconstruct_workload(
            chunk_manifest_path=args.chunk_manifest,
            corpus_manifest_path=args.corpus_manifest,
            chunks_root=args.chunks_root,
            embeddings_root=args.embeddings_root,
            model_dir=model_dir,
            settings=settings,
            source_document_id=args.source_document_id,
            expected_source_sha256=args.source_sha256,
            incident_identity=incident_identity,
        )
        output_path = require_local_untracked_path(args.out, repo_root=ROOT)
        if output_path.exists():
            raise WorkloadFreezeError(
                "workload output already exists; refusing overwrite"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        # Exception text may include private input material; do not print it.
        print(f"WORKLOAD_FREEZE_FAILED: {type(exc).__name__}", file=sys.stderr)
        return 10
    print(
        json.dumps(
            {
                "status": "FROZEN",
                "workload_kind": payload["workload_kind"],
                "item_count": payload["item_count"],
                "workload_sha256": payload["workload_sha256"],
                "execution_authorized": False,
                "output": str(output_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
