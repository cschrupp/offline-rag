"""Single-use, isolated Rich 2 Stage 1 assembler diagnostic.

This script is intentionally not part of the frozen Stage 2 workload. Its
execution requires a separate authorization token and a verified scratch copy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import signal
import threading
import time
from pathlib import Path
from typing import Any

DRIVER_DIR = Path(__file__).resolve().parent
STAGE2_INPUTS = DRIVER_DIR.parent / "stage2-integration"
RICH2_BINDING_PATH = STAGE2_INPUTS / "rich2-stage1-binding.json"
STAGE1_BINDINGS_PATH = STAGE2_INPUTS / "stage1-bindings.json"
RICH2_EXPECTED_CANDIDATES = 10
CALL_DEADLINE_SECONDS = 180
PROCESS_RSS_LIMIT_BYTES = 6 * 1024**3
MIN_HOST_AVAILABLE_BYTES = 2 * 1024**3
ONE_SHOT_CLAIM_PATH = Path("/stage1/rich2-stage1.claimed")
ONE_SHOT_OUTPUT_PATH = Path("/stage1/rich2-stage1.json")
CHUNK_ID_ASC_TIE_BREAK = "chunk-id-asc-v1"


class Rich2Stage1Error(RuntimeError):
    """A Rich 2 Stage 1 input or observation failed closed validation."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(encoded)


def validate_binding_document(
    binding: dict[str, Any], historical_bindings_sha256: str
) -> None:
    """Check fixed Rich 2 identity and prove historical Rich is untouched."""
    workspace = binding.get("workspace", {})
    source = binding.get("source", {}).get("identity", {})
    publication = binding.get("publication", {})
    artifacts = binding.get("artifacts", {})
    question = binding.get("question", {})
    scope = binding.get("source_scope", {})
    historical = binding.get("historical_rich_binding", {})

    expected_historical = {
        "preserved_file": "stage1-bindings.json",
        "preserved_sha256": historical_bindings_sha256,
        "workspace_id": "ws_73a29d6defb545e8958746d78ac80775",
        "revision": 2,
        "source_inventory_sha256": (
            "bd55ee4c43af654179d951eea04af237812bc453fb904226a41820936e1a02bb"
        ),
    }
    if binding.get("schema") != "seneca-rich2-stage1-binding-v1":
        raise Rich2Stage1Error("Rich 2 binding schema differs")
    if binding.get("status") != "prepared_not_execution_authority":
        raise Rich2Stage1Error("Rich 2 binding is not marked preparation-only")
    if historical != expected_historical:
        raise Rich2Stage1Error("historical Rich binding provenance differs")
    if (
        workspace.get("workspace_id") != "ws_ee9ddd1e51354be1b7981282cc1dd240"
        or workspace.get("revision") != 2
        or workspace.get("status") != "active"
        or workspace.get("source_count") != 1
        or workspace.get("source_inventory_sha256")
        != "3fef97218820b06e65baa48468923f7ac23166c286b648722f5db468c4accfad"
        or workspace.get("workspace_record_sha256")
        != workspace.get("source_inventory_sha256")
        or workspace.get("backing_corpus_name")
        != "wsc_ee9ddd1e51354be1b7981282cc1dd240"
    ):
        raise Rich2Stage1Error("Rich 2 workspace identity differs")
    if (
        source.get("source_id") != "src_e5f3f9cf065a468397d85e4c97f7f6f5"
        or source.get("version") != 1
        or source.get("document_id")
        != "doc_c3084e336e87f2bbcc915a3c12b0e9bbd6128d8c34298637abbfb0ea6ac390cc"
        or source.get("content_hash")
        != "c3084e336e87f2bbcc915a3c12b0e9bbd6128d8c34298637abbfb0ea6ac390cc"
        or source.get("byte_size") != 59777
        or binding.get("source", {}).get("content_sha256") != source.get("content_hash")
        or binding.get("source", {}).get("byte_size") != source.get("byte_size")
        or not source.get("active")
        or source.get("active_from_revision") != 2
        or source.get("active_from_snapshot_id")
        != "snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca"
    ):
        raise Rich2Stage1Error("Rich 2 source identity differs")
    if (
        publication.get("snapshot_id")
        != "snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca"
        or publication.get("published_pointer") != publication.get("snapshot_id")
        or publication.get("science_settings_sha256")
        != "5dce337dc1875b2aa615d62ee771a0ae384559c2da14be384e067ded035f5417"
    ):
        raise Rich2Stage1Error("Rich 2 publication or settings identity differs")
    expected_snapshot_identity = {
        "schema_version": "offline-rag-corpus-read-snapshot-v1",
        "product_mode_id": "grounded_v1",
        "corpus_id": "corpus_514e8eaae936a36f0862897eaf66be4a72694fae0d80d15f6e438b27148bcf61",
        "chunk_set_id": "chunkset_7d67681e970b61c0911ee1312172156a7e325279cd4a7e4acf438d2b6e33fd66",
        "dense_index_id": "denseindex_0260f9a1b37c14e45cb15d2af0372b0c21b01462584830e50b8f54e4d7cb2c90",
        "lexical_index_id": "lexical_7b35bba27873a98170d1606fd6a5a7b905064a4b9b2aef49b027df3b8437d1e9",
        "embedding_config_hash": "embcfg_e7861b5986785eba0fb6725a3d1e40f2d461f33e2dcd66d2c75ad3875f9a5d3f",
        "index_config_hash": "idxcfg_45b7b17026e085b4f721de7031819b3b72d99db3966e1b77fc9dcc8203d41862",
        "lexical_config_hash": "lexcfg_054978dd1ca7528bf5c6363dd223e891507d7f4d84286a3ab9b701fa85d427ee",
        "fusion_config_hash": "fuscfg_fa8a567966bfa7676166b2689fec631d8a9cee0fd0739cdb1688854df92755a9",
        "reranker_config_hash": "rrkcfg_68c77803ed7dc09ef0b5df50b3c09b6ee1c388bdccd0b8c29ca4c2161d57bb3e",
        "context_config_hash": "ctxcfg_b1742f41ecc03defbcf7c4e270fe22b4aa72db4a1af2c02a70d5560cd2ac8876",
    }
    expected_manifest_hashes = {
        "corpus": "bda41f37af50c7d2dd44a920c937c0c8c3afcc7fd9ce15dd40d6872a5378bf94",
        "chunk": "f7df70ac0c4f019c367f1bacb0dcdc37ac54bbce033f5a7d66424792216e8324",
        "dense": "f48f1b78d4f5b35d251544f53e55f752f74c6e14b580381ecaee7d331371300a",
        "lexical": "d697d59c4d8022ece68077e6568c5ef3fce7894cf686c9ac802c113e3b078a92",
    }
    if (
        publication.get("snapshot_identity") != expected_snapshot_identity
        or publication.get("snapshot_manifest_sha256")
        != "866cb5040778debf1235f0d86c065c47efeca770ed0d258bb9f0c44e732eebfa"
        or artifacts.get("manifest_sha256") != expected_manifest_hashes
    ):
        raise Rich2Stage1Error("Rich 2 snapshot or manifest provenance differs")
    expected_lexical_files = {
        "documents.json": "74e1f589c998c1bda0dc2d1c8d5f8b623d8dbf2d2ef9b9023321ccc98d1beb62",
        "metadata.json": "0ca27ca08a71f29e5e1c977bc9d17d88a355bff60af94944f249e842b3021c72",
        "postings.json": "8827941438b8c2f0a01b33d5a18946bcb81ca67cc3d9607c5d5dbb426c8439a6",
    }
    if (
        artifacts.get("dense", {}).get("expected_child_count") != 10
        or artifacts.get("dense", {}).get("indexed_child_count") != 10
        or artifacts.get("dense", {}).get("collection_name")
        != "dense_0260f9a1b37c14e45cb15d2af0372b0c21b01462584830e5"
        or artifacts.get("lexical", {}).get("expected_child_count") != 10
        or artifacts.get("lexical", {}).get("indexed_child_count") != 10
        or artifacts.get("lexical", {}).get("document_count") != 10
        or artifacts.get("lexical", {}).get("lexical_files_sha256")
        != expected_lexical_files
    ):
        raise Rich2Stage1Error("Rich 2 physical artifact binding differs")
    if (
        question.get("text") != "Describe the naturalistic decision method"
        or question.get("normalized_sha256")
        != "68078feb74268f2e867cc4b97a38dd4f7f6fd047f2068b24c0ec3d35c079a825"
        or question.get("prior_turns") != []
    ):
        raise Rich2Stage1Error("Rich 2 question binding differs")
    if scope != {
        "mode": "all_active",
        "source_ids": [source.get("source_id")],
        "document_ids": [source.get("document_id")],
    }:
        raise Rich2Stage1Error("Rich 2 source scope differs")
    if binding.get("expected_candidate_count") != RICH2_EXPECTED_CANDIDATES:
        raise Rich2Stage1Error("Rich 2 expected candidate count differs")
    effective_config = binding.get("effective_config", {})
    if (
        effective_config.get("path") != "/app/config/base.yaml"
        or effective_config.get("sha256")
        != "dc45247f1c807237cf09e8570d26b2600e685f637f967b7f162ed84cf9db77f0"
    ):
        raise Rich2Stage1Error("Rich 2 effective configuration binding differs")


def validate_observation(
    *,
    candidate_ids: list[str],
    candidate_document_ids: list[str],
    expected_document_id: str,
    score_pairs: list[dict[str, Any]],
    ranked_ids: list[str],
    anchor_ids: list[str],
    evidence_unit_ids: list[str],
    expected_candidate_ids: set[str] | None = None,
    expected_count: int = RICH2_EXPECTED_CANDIDATES,
) -> None:
    """Fail closed on incomplete, unexpected, or internally inconsistent output."""
    if (
        len(candidate_ids) != expected_count
        or len(set(candidate_ids)) != expected_count
    ):
        raise Rich2Stage1Error("fused candidate population differs")
    if len(candidate_document_ids) != expected_count or any(
        document_id != expected_document_id for document_id in candidate_document_ids
    ):
        raise Rich2Stage1Error("candidate escaped the bound document scope")
    if any(
        not isinstance(candidate_id, str) or not candidate_id
        for candidate_id in candidate_ids
    ):
        raise Rich2Stage1Error("fused candidate identity is malformed")
    if (
        expected_candidate_ids is not None
        and set(candidate_ids) != expected_candidate_ids
    ):
        raise Rich2Stage1Error(
            "fused candidates differ from the frozen chunk inventory"
        )
    associated_ids = [item.get("candidate_id") for item in score_pairs]
    if associated_ids != candidate_ids or len(score_pairs) != expected_count:
        raise Rich2Stage1Error("candidate-score association is incomplete or reordered")
    for item in score_pairs:
        score = item.get("raw_logit")
        pair_hash = item.get("pair_input_sha256")
        if (
            not isinstance(score, (float, int))
            or isinstance(score, bool)
            or not math.isfinite(float(score))
            or not isinstance(pair_hash, str)
            or len(pair_hash) != 64
            or any(character not in "0123456789abcdef" for character in pair_hash)
        ):
            raise Rich2Stage1Error("score instrumentation is incomplete or non-finite")
    if len(ranked_ids) != expected_count or set(ranked_ids) != set(candidate_ids):
        raise Rich2Stage1Error("ranked candidate population differs")
    expected_ranking = [
        item["candidate_id"]
        for item in sorted(
            score_pairs,
            key=lambda item: (-float(item["raw_logit"]), item["candidate_id"]),
        )
    ]
    if ranked_ids != expected_ranking:
        raise Rich2Stage1Error("ranked candidates violate raw-logit/chunk-ID ordering")
    if not anchor_ids or any(
        candidate_id not in ranked_ids for candidate_id in anchor_ids
    ):
        raise Rich2Stage1Error("anchor identity instrumentation is incomplete")
    if not evidence_unit_ids or len(set(evidence_unit_ids)) != len(evidence_unit_ids):
        raise Rich2Stage1Error("evidence-unit identity instrumentation is incomplete")


def _safe_resource_preflight() -> None:
    """Enforce per-process/container checks before loading either model."""
    if os.environ.get("SENECA_ISOLATED_COPY") != "verified":
        raise Rich2Stage1Error("verified isolated data copy is required")
    if os.environ.get("SENECA_RICH2_STAGE1_EXECUTION_AUTHORIZED") != "one-call":
        raise Rich2Stage1Error("explicit one-call execution authorization is required")
    if set(os.listdir("/sys/class/net")) != {"lo"}:
        raise Rich2Stage1Error("network isolation is not active")
    if os.statvfs("/models").f_flag & os.ST_RDONLY == 0:
        raise Rich2Stage1Error("model mount must be read-only")
    if os.statvfs("/data").f_flag & os.ST_RDONLY:
        raise Rich2Stage1Error("isolated data mount must be writable")
    if len(os.sched_getaffinity(0)) != 4:
        raise Rich2Stage1Error("effective CPU allocation differs from four CPUs")
    if hasattr(resource, "RLIMIT_AS"):
        soft, _ = resource.getrlimit(resource.RLIMIT_AS)
        if soft != resource.RLIM_INFINITY and soft > PROCESS_RSS_LIMIT_BYTES:
            raise Rich2Stage1Error(
                "process address-space limit exceeds the approved cap"
            )
    mem_available = None
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            mem_available = int(line.split()[1]) * 1024
            break
    if mem_available is None or mem_available < MIN_HOST_AVAILABLE_BYTES:
        raise Rich2Stage1Error("host available memory is below the approved minimum")
    memory_max = Path("/sys/fs/cgroup/memory.max")
    memory_swap_max = Path("/sys/fs/cgroup/memory.swap.max")
    if not memory_max.is_file() or not memory_swap_max.is_file():
        raise Rich2Stage1Error("cgroup memory policy is not verifiable")
    memory_limit = memory_max.read_text().strip()
    swap_limit = memory_swap_max.read_text().strip()
    if (
        not memory_limit.isdigit()
        or int(memory_limit) > PROCESS_RSS_LIMIT_BYTES
        or swap_limit != "0"
    ):
        raise Rich2Stage1Error(
            "cgroup memory/swap policy differs from the approved cap"
        )


def _mem_available_bytes() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise Rich2Stage1Error("host available memory is not observable")


def _sample_available_memory(
    stop: threading.Event, minimum: list[int], failures: list[str]
) -> None:
    """Track host memory throughout the bounded assembler call."""
    while not stop.is_set():
        try:
            minimum[0] = min(minimum[0], _mem_available_bytes())
        except (OSError, ValueError, Rich2Stage1Error) as exc:
            failures.append(type(exc).__name__)
            return
        stop.wait(0.25)


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _claim_single_use(claim_path: Path, binding_sha256: str) -> None:
    """Permanently claim this copied data tree before model construction."""
    _write_once(
        claim_path,
        {
            "schema": "seneca-rich2-stage1-one-shot-claim-v1",
            "binding_sha256": binding_sha256,
            "claimed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )


def _require_single_use_paths_available(claim_path: Path, output_path: Path) -> None:
    """Reject reused diagnostic storage before constructing model resources."""
    if claim_path.exists() or output_path.exists():
        raise Rich2Stage1Error("single-use claim or output already exists")


def _deadline_handler(_signum: int, _frame: Any) -> None:
    raise TimeoutError("Rich 2 Stage 1 assembler deadline exceeded")


def execute_one_call(
    binding: dict[str, Any], *, output_path: Path = ONE_SHOT_OUTPUT_PATH
) -> dict[str, Any]:
    """Run one canonical assembler call and return sanitized identities only."""
    _safe_resource_preflight()
    from native_contract import load_manifest, verify_config_file
    from preflight import validate_rich2_binding

    from offline_rag.app.publication import ProductPublicationRegistry
    from offline_rag.app.query_binding import build_snapshot_query_binding
    from offline_rag.app.runtime import default_resource_factories
    from offline_rag.config.loader import load_settings
    from offline_rag.context.assemble import HybridRerankContextAssembler
    from offline_rag.core.ids import CHUNK_ID_ASC_TIE_BREAK
    from offline_rag.dense.retrieve import DenseRetriever
    from offline_rag.hybrid.retrieve import HybridRetriever
    from offline_rag.lexical.retrieve import LexicalRetriever
    from offline_rag.rerank import retrieve as rerank_retrieve
    from offline_rag.rerank.cross_encoder import CrossEncoderReranker
    from offline_rag.rerank.retrieve import HybridRerankRetriever

    settings = load_settings()
    settings_path = Path(os.environ.get("OFFLINE_RAG_CONFIG", "/app/config/base.yaml"))
    native_manifest = load_manifest(STAGE2_INPUTS)
    verify_config_file(native_manifest, settings_path)
    binding_sha256 = sha256_bytes(RICH2_BINDING_PATH.read_bytes())
    historical_sha256 = sha256_bytes(STAGE1_BINDINGS_PATH.read_bytes())
    validate_binding_document(binding, historical_sha256)
    committed_binding = json.loads(RICH2_BINDING_PATH.read_bytes())
    if binding != committed_binding:
        raise Rich2Stage1Error("Rich 2 binding differs from committed identity")
    preflight = validate_rich2_binding(settings, binding)
    from preflight import verify_models

    workloads = json.loads((STAGE2_INPUTS / "workloads.json").read_text())
    verify_models(settings, workloads)
    if (
        settings.project.strict_offline is not True
        or settings.deployment.qdrant_mode != "local"
        or settings.api.query_deadline_seconds != CALL_DEADLINE_SECONDS
        or settings.api.shutdown_grace_seconds != 30
        or settings.api.max_concurrent_query != 1
        or settings.reranker.input_k != 30
        or settings.reranker.output_k != 10
        or settings.reranker.batch_size != 16
        or settings.reranker.max_length != 1024
        or settings.reranker.batching_strategy != "consecutive"
        or settings.reranker.score_transform != "raw-logit-v1"
        or settings.reranker.tie_break != CHUNK_ID_ASC_TIE_BREAK
        or settings.indexing.embedding.device != "auto"
        or settings.indexing.embedding.precision != "native"
    ):
        raise Rich2Stage1Error("effective runtime/scientific settings differ")

    if output_path != ONE_SHOT_OUTPUT_PATH:
        raise Rich2Stage1Error("only the fixed single-use output path is accepted")
    _require_single_use_paths_available(ONE_SHOT_CLAIM_PATH, output_path)
    _claim_single_use(ONE_SHOT_CLAIM_PATH, binding_sha256)
    _safe_resource_preflight()

    import torch

    from offline_rag.dense.st_onnx_runtime import (
        FROZEN_ORT_INTER_OP_THREADS,
        FROZEN_ORT_INTRA_OP_THREADS,
    )

    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    if (
        torch.version.cuda is not None
        or (torch.get_num_threads(), torch.get_num_interop_threads()) != (2, 2)
        or (FROZEN_ORT_INTRA_OP_THREADS, FROZEN_ORT_INTER_OP_THREADS) != (8, 1)
    ):
        raise Rich2Stage1Error("CPU/ORT/PyTorch execution profile differs")

    factories = default_resource_factories()
    qdrant = factories.qdrant(settings)
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    snapshot = registry.resolve_snapshot(
        preflight["corpus_name"], preflight["binding"]["publication"]["snapshot_id"]
    )
    if registry.published_snapshot_id(preflight["corpus_name"]) != snapshot.snapshot_id:
        raise Rich2Stage1Error("Rich 2 publication pointer changed after preflight")
    query_binding = build_snapshot_query_binding(settings, snapshot)
    identity = snapshot.identity.model_dump(
        mode="json",
        exclude={
            "corpus_manifest",
            "chunk_manifest",
            "dense_index_manifest",
            "lexical_index_manifest",
        },
    )
    if identity != preflight["binding"]["publication"]["snapshot_identity"]:
        raise Rich2Stage1Error("resolved Rich 2 snapshot differs from its binding")

    embedder = factories.embedder(settings)
    reranker = factories.reranker(settings)
    if not isinstance(reranker, CrossEncoderReranker):
        raise Rich2Stage1Error("production BGE cross-encoder was not selected")

    dense = DenseRetriever(settings, embedder=embedder, backend=qdrant)
    lexical = LexicalRetriever(settings)
    hybrid = HybridRetriever(settings, dense=dense, lexical=lexical)
    retriever = HybridRerankRetriever(settings, hybrid=hybrid, reranker=reranker)
    assembler = HybridRerankContextAssembler(
        settings, retriever=retriever, store=preflight["structures"]
    )
    observation: dict[str, Any] = {"score_pairs_calls": 0, "sort_calls": 0}
    original_score_pairs = CrossEncoderReranker.score_pairs
    original_sort = rerank_retrieve._sort_scored

    def observed_score_pairs(scorer, pairs):
        observation["score_pairs_calls"] += 1
        observation["pairs"] = pairs
        scores = original_score_pairs(scorer, pairs)
        observation["raw_logits"] = [float(score) for score in scores]
        return scores

    def observed_sort(candidates, scores):
        observation["sort_calls"] += 1
        if observation["sort_calls"] != 1:
            raise Rich2Stage1Error("reranker sort instrumentation ran more than once")
        ordered = original_sort(candidates, scores)
        observation["fused_pool_ids"] = [candidate.chunk_id for candidate in candidates]
        observation["candidate_document_ids"] = [
            candidate.document_id for candidate in candidates
        ]
        observation["ranked_ids"] = [
            candidate.chunk_id for candidate, _score in ordered
        ]
        return ordered

    CrossEncoderReranker.score_pairs = observed_score_pairs
    rerank_retrieve._sort_scored = observed_sort
    signal.signal(signal.SIGALRM, _deadline_handler)
    signal.alarm(CALL_DEADLINE_SECONDS)
    min_available_memory = [_mem_available_bytes()]
    memory_sample_failures: list[str] = []
    memory_sampler_stop = threading.Event()
    memory_sampler = threading.Thread(
        target=_sample_available_memory,
        args=(memory_sampler_stop, min_available_memory, memory_sample_failures),
        name="rich2-stage1-memory-sampler",
        daemon=True,
    )
    memory_sampler.start()
    try:
        assembler_wall_started = time.perf_counter()
        assembler_cpu_started = time.process_time()
        result = assembler.assemble(
            query=preflight["question"],
            corpus_name=query_binding.corpus_name,
            check_ready=False,
            dense_index_id=query_binding.dense_index_id,
            dense_collection_name=query_binding.dense_collection_name,
            lexical_index_id=query_binding.lexical_index_id,
            chunk_set_id=query_binding.chunk_set_id,
            corpus_id=query_binding.corpus_id,
            document_ids=preflight["document_ids"],
        )
        assembler_wall_s = time.perf_counter() - assembler_wall_started
        assembler_cpu_s = time.process_time() - assembler_cpu_started
    finally:
        memory_sampler_stop.set()
        memory_sampler.join(timeout=1)
        signal.alarm(0)
        CrossEncoderReranker.score_pairs = original_score_pairs
        rerank_retrieve._sort_scored = original_sort
        assembler.close()
        retriever.close()
        lexical.close()
        qdrant.close()
        for owned in (embedder, reranker):
            close = getattr(owned, "close", None)
            if callable(close):
                close()

    if memory_sample_failures or min_available_memory[0] < MIN_HOST_AVAILABLE_BYTES:
        raise Rich2Stage1Error("host memory policy was violated during the call")

    if (
        observation["score_pairs_calls"] != 1
        or observation["sort_calls"] != 1
        or len(observation.get("pairs", [])) != RICH2_EXPECTED_CANDIDATES
    ):
        raise Rich2Stage1Error("required reranker instrumentation is incomplete")
    fused_ids = result.metadata.get("input_pool_chunk_ids")
    if not isinstance(fused_ids, list):
        raise Rich2Stage1Error("assembler omitted fused candidate identities")
    pairs = observation["pairs"]
    pair_ids = [pair.chunk_id for pair in pairs]
    candidate_documents = observation["candidate_document_ids"]
    expected_document_id = next(iter(preflight["document_ids"]))
    expected_candidate_ids = {
        chunk_id
        for chunk_id, child in preflight["structures"].children.items()
        if child.document_id == expected_document_id
    }
    if len(expected_candidate_ids) != RICH2_EXPECTED_CANDIDATES:
        raise Rich2Stage1Error(
            "bound snapshot child inventory differs from ten candidates"
        )
    for candidate_id in fused_ids:
        child = preflight["structures"].get_child(candidate_id)
        if child.document_id != expected_document_id:
            raise Rich2Stage1Error(
                "fused candidate is not in the bound snapshot/document"
            )
    score_associations = [
        {
            "candidate_id": pair.chunk_id,
            "candidate_id_sha256": sha256_bytes(pair.chunk_id.encode("utf-8")),
            "pair_input_sha256": sha256_bytes(
                (pair.query_text + "\0" + pair.passage_text).encode("utf-8")
            ),
            "raw_logit": score,
        }
        for pair, score in zip(pairs, observation["raw_logits"], strict=True)
    ]
    anchor_ids = [anchor.chunk_id for anchor in result.anchors]
    evidence_unit_ids = [unit.evidence_unit_id for unit in result.evidence_units]
    validate_observation(
        candidate_ids=fused_ids,
        candidate_document_ids=candidate_documents,
        expected_document_id=expected_document_id,
        score_pairs=score_associations,
        ranked_ids=observation["ranked_ids"],
        anchor_ids=anchor_ids,
        evidence_unit_ids=evidence_unit_ids,
        expected_candidate_ids=expected_candidate_ids,
    )
    if pair_ids != fused_ids:
        raise Rich2Stage1Error("scorer input order differs from fused candidate order")
    if observation.get("fused_pool_ids") != fused_ids:
        raise Rich2Stage1Error("reranker pool differs from fused candidate identities")
    if any(pair.query_text != preflight["question"] for pair in pairs):
        raise Rich2Stage1Error(
            "scorer query differs from the frozen no-history question"
        )
    if (
        len(anchor_ids) != settings.context.anchor_k
        or anchor_ids != observation["ranked_ids"][: settings.context.anchor_k]
    ):
        raise Rich2Stage1Error(
            "assembler anchors differ from canonical reranker output"
        )
    latency = result.metadata.get("latency_ms", {})
    if not isinstance(latency, dict) or any(
        not isinstance(latency.get(key), (float, int))
        or isinstance(latency[key], bool)
        or not math.isfinite(float(latency[key]))
        or latency[key] < 0
        for key in ("hybrid_rerank", "context_expand", "total")
    ):
        raise Rich2Stage1Error("assembler latency instrumentation is incomplete")
    rerank_latency = latency.get("hybrid_rerank_breakdown")
    hybrid_latency = (
        rerank_latency.get("hybrid_breakdown")
        if isinstance(rerank_latency, dict)
        else None
    )
    if (
        not isinstance(rerank_latency, dict)
        or not isinstance(hybrid_latency, dict)
        or any(
            not isinstance(rerank_latency.get(key), (float, int))
            or not math.isfinite(float(rerank_latency[key]))
            or rerank_latency[key] < 0
            for key in ("hybrid", "pair_build", "rerank_infer", "sort", "total")
        )
        or any(
            not isinstance(hybrid_latency.get(key), (float, int))
            or not math.isfinite(float(hybrid_latency[key]))
            or hybrid_latency[key] < 0
            for key in ("dense", "lexical", "fusion", "total")
        )
    ):
        raise Rich2Stage1Error("retrieval stage timing instrumentation is incomplete")
    rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    if rss_bytes > PROCESS_RSS_LIMIT_BYTES:
        raise Rich2Stage1Error("diagnostic process exceeded the RSS ceiling")
    profile = getattr(embedder, "profile", None)
    if (
        getattr(profile, "profile_id", None) != "cpu_onnx_fp32_v1"
        or getattr(profile, "representation_id", None) != "onnx_fp32_v1"
        or getattr(profile, "provider", None) != "CPUExecutionProvider"
        or getattr(profile, "device", None) != "cpu"
        or getattr(profile, "precision", None) != "fp32"
        or getattr(profile, "backend_family", None) != "sentence_transformers_onnx"
    ):
        raise Rich2Stage1Error("resolved Qwen3 execution profile differs")
    _tokenizer, reranker_model = reranker._load()
    import torch

    floating_tensors = [
        tensor
        for tensor in (*reranker_model.parameters(), *reranker_model.buffers())
        if tensor.is_floating_point()
    ]
    if (
        reranker.device != "cpu"
        or reranker_model.training
        or not floating_tensors
        or any(
            tensor.device.type != "cpu" or tensor.dtype != torch.float32
            for tensor in floating_tensors
        )
    ):
        raise Rich2Stage1Error("resolved BGE execution profile differs")

    payload = {
        "schema": "seneca-rich2-stage1-observation-v1",
        "status": "executed_single_assembler_call",
        "binding_sha256": binding_sha256,
        "workspace_id": preflight["workspace"].workspace_id,
        "workspace_revision": preflight["workspace"].revision,
        "source_inventory_sha256": preflight["workspace_record_sha256"],
        "source_ids": sorted(preflight["source_scope"].source_ids),
        "document_ids": sorted(preflight["document_ids"]),
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_manifest_sha256": preflight["snapshot_manifest_sha256"],
        "scientific_settings_sha256": preflight["settings_hash"],
        "embedding_profile": "cpu_onnx_fp32_v1",
        "embedding_representation": "onnx_fp32_v1",
        "embedding_provider": "CPUExecutionProvider",
        "reranker": {
            "model_id": settings.reranker.model.model_id,
            "revision": settings.reranker.model.revision,
            "device": reranker.device,
            "precision": "fp32",
        },
        "question_sha256": preflight["binding"]["question"]["normalized_sha256"],
        "source_scope": "all_active",
        "fused_candidate_count": len(fused_ids),
        "fused_candidate_ids": fused_ids,
        "fused_candidate_ids_sha256": sha256_json(fused_ids),
        "candidate_score_associations": score_associations,
        "ranked_candidate_ids": observation["ranked_ids"],
        "ranking_tie_break": CHUNK_ID_ASC_TIE_BREAK,
        "anchor_ids": anchor_ids,
        "anchor_ids_sha256": sha256_json(anchor_ids),
        "evidence_unit_ids": evidence_unit_ids,
        "evidence_unit_ids_sha256": sha256_json(evidence_unit_ids),
        "evidence_unit_count": len(evidence_unit_ids),
        "context_token_count": result.context_token_count,
        "packed_context_sha256": sha256_bytes(result.assembled_text.encode("utf-8")),
        "latency_ms": latency,
        "assembler_wall_ms": assembler_wall_s * 1000,
        "process_cpu_ms": assembler_cpu_s * 1000,
        "peak_rss_bytes": rss_bytes,
        "external_network": False,
        "generation_invoked": False,
    }
    _write_once(output_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-one-call", action="store_true")
    parser.add_argument("--binding", type=Path, default=RICH2_BINDING_PATH)
    parser.add_argument("--output", type=Path, default=ONE_SHOT_OUTPUT_PATH)
    arguments = parser.parse_args()
    if not arguments.execute_one_call:
        raise SystemExit("refusing: --execute-one-call is required")
    historical_sha = hashlib.sha256(STAGE1_BINDINGS_PATH.read_bytes()).hexdigest()
    if (
        historical_sha
        != "7bfc80f1ab7455077e41672d547b3b9938b18fd630f1615e80822477796af9f7"
    ):
        raise Rich2Stage1Error("frozen historical Stage 1 binding changed")
    binding_bytes = arguments.binding.read_bytes()
    binding = json.loads(binding_bytes)
    validate_binding_document(binding, historical_sha)
    if arguments.binding != RICH2_BINDING_PATH:
        raise Rich2Stage1Error("only the committed Rich 2 binding is accepted")
    if arguments.output != ONE_SHOT_OUTPUT_PATH:
        raise Rich2Stage1Error("only the fixed single-use output path is accepted")
    execute_one_call(binding, output_path=arguments.output)


if __name__ == "__main__":
    main()
