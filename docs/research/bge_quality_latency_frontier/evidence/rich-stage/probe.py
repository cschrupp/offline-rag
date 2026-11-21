import hashlib
import json
import os
import resource
import sys
import time
from pathlib import Path

from offline_rag.app.publication import ProductPublicationRegistry, snapshot_manifest_path
from offline_rag.app.query import _resolve_workspace_source_scope, normalize_product_question
from offline_rag.app.query_binding import build_snapshot_query_binding
from offline_rag.app.snapshot import CanonicalSnapshotManifest, compute_snapshot_id
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config.loader import load_settings
from offline_rag.context.store import load_structure_store_for_chunk_manifest
from offline_rag.dense.persistence import load_index_manifest

stage = "settings"
def require(ok, message):
    if not ok:
        raise ValueError(message)

def main():
    global stage
    mode = sys.argv[1]
    started = time.perf_counter()
    if mode == "measure":
        import torch
        os.umask(0o077)
        torch.set_num_interop_threads(2)
        torch.set_num_threads(2)
        require((torch.get_num_threads(), torch.get_num_interop_threads()) == (2, 2),
                "thread setting mismatch")
    settings = load_settings()
    question = normalize_product_question("Describe the naturalistic decision method")
    digest = hashlib.sha256(question.encode()).hexdigest()
    stage = "historical_trace_scope"
    historical = json.loads((settings.paths.traces / "conversation" / "trace_5c7bcd76773a49a7a5ede5e0a32a4d30.json").read_bytes())
    historical_query_id = "trace_4c701509255f474990998e3209ff620f"
    require(historical["query_trace_id"] == historical_query_id and historical["question_sha256"] == digest,
            "historical conversation binding mismatch")
    historical_query = json.loads((settings.paths.traces / (historical_query_id + ".json")).read_bytes())
    historical_hash = historical["retrieval_question_sha256"]
    require(historical_hash == historical_query["request"]["question_sha256"], "historical retrieval hash binding mismatch")
    require(historical["prior_turn_count"] == 2 and historical["resolver_invoked"] and historical_query["status"] == "answered",
            "historical request identity mismatch")
    scope = historical["source_scope"]
    wsid = historical["workspace_id"]
    sid = historical["snapshot_id"]
    require(wsid == "ws_73a29d6defb545e8958746d78ac80775" and scope["mode"] == "all_active"
            and len(scope["document_ids"]) == 1 and historical_query["request"]["source_scope"] == scope
            and historical_query["snapshot_id"] == sid, "historical scope mismatch")
    store = WorkspaceStore(settings)
    ws = store.get(wsid)
    require(ws.status == "active" and ws.current_snapshot_id == sid, "workspace no longer at incident snapshot")
    actual, _, docids = _resolve_workspace_source_scope(ws, source_ids=None)
    require(actual.model_dump(mode="json") == scope, "workspace source scope drift")
    stage = "snapshot_artifacts"
    m = CanonicalSnapshotManifest.model_validate_json(
        snapshot_manifest_path(settings.paths.corpora, ws.backing_corpus_name, sid).read_bytes()
    )
    require(compute_snapshot_id(m) == sid, "snapshot hash mismatch")
    for root, name in ((settings.paths.manifests,m.corpus_manifest),
                       (settings.paths.chunk_manifests,m.chunk_manifest),
                       (settings.paths.index_manifests,m.dense_index_manifest),
                       (settings.paths.lexical_index_manifests,m.lexical_index_manifest)):
        require((root / Path(name).name).is_file(), "snapshot manifest missing")
    dense = load_index_manifest(settings.paths.index_manifests / Path(m.dense_index_manifest).name)
    require(dense.expected_child_count == dense.indexed_child_count == 10, "unexpected passage population")
    require((settings.paths.qdrant_storage / "collection" / dense.collection_name).is_dir(), "dense storage missing")
    structures = load_structure_store_for_chunk_manifest(settings, Path(m.chunk_manifest).name)
    stage = "managed_operations"
    active = 0
    for path in settings.paths.workspaces.glob("*/operations/by_id/*.json"):
        status = json.loads(path.read_bytes())["status"]
        if status not in ("succeeded","failed","canceled","cancelled","interrupted"):
            active += 1
    require(active == 0, "managed operation not terminal")
    result = {
        "workspace_id": wsid, "workspace_revision": ws.revision,
        "question_sha256": digest, "historical_retrieval_question_sha256": historical_hash,
        "historical_retrieval_matches": historical_hash == digest,
        "historical_context_ms": historical_query["execution"]["context_latency_ms"],
        "snapshot_id": sid, "source_inventory_sha256": hashlib.sha256(
            store.workspace_path(wsid).read_bytes()).hexdigest(),
        "document_id": next(iter(docids)), "passages": dense.indexed_child_count,
        "identities": m.model_dump(mode="json", exclude={"corpus_manifest","chunk_manifest","dense_index_manifest","lexical_index_manifest"}),
        "science_settings_hash": hashlib.sha256(json.dumps({
            k: getattr(settings,k).model_dump(mode="json") for k in (
                "dense","reranker","fusion","context","lexical","indexing"
            )}, sort_keys=True).encode()).hexdigest(),
    }
    require(result["workspace_revision"] == 2 and sid == "snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca", "previous publication mismatch")
    require(result["science_settings_hash"] == "5dce337dc1875b2aa615d62ee771a0ae384559c2da14be384e067ded035f5417", "previous retrieval settings mismatch")
    if mode == "inspect":
        from offline_rag.rerank.provision import resolve_reranker_model_dir
        model_dir = resolve_reranker_model_dir(reranker_artifacts_root=settings.paths.reranker_artifacts,
                                               model_path=settings.reranker.model.model_path)
        require(settings.reranker.model.revision == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e", "checkpoint revision mismatch")
        for name, expected_hash in {'config.json': '13dcd6c31d9fec9d1d8e158702072f62d7fa7d312a64b9fe057bec9a08cfe41a', 'model.safetensors': 'd9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286', 'tokenizer.json': '69564b696052886ed0ac63fa393e928384e0f8caada38c1f4864a9bfbf379c15', 'tokenizer_config.json': '7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4', 'sentencepiece.bpe.model': 'cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865', 'special_tokens_map.json': '8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835'}.items():
            with (model_dir / name).open("rb") as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == expected_hash, "checkpoint file hash mismatch")
        print(json.dumps(result, sort_keys=True))
        return
    expected = json.loads(Path("/diagnostic/before.json").read_bytes())
    require(result == expected, "copied state or settings mismatch")
    stage = "isolated_binding_validation"
    from offline_rag.app.runtime import default_resource_factories
    from offline_rag.context.assemble import HybridRerankContextAssembler
    from offline_rag.dense.retrieve import DenseRetriever
    from offline_rag.evaluation.performance_14.resources import capture_resource_observation
    from offline_rag.hybrid.retrieve import HybridRetriever
    from offline_rag.rerank.retrieve import HybridRerankRetriever
    factories = default_resource_factories()
    qdrant = factories.qdrant(settings)
    try:
        snapshot = ProductPublicationRegistry(settings,qdrant=qdrant).resolve_snapshot(ws.backing_corpus_name,sid)
        b = build_snapshot_query_binding(settings,snapshot)
        embedder = factories.embedder(settings)
        reranker = factories.reranker(settings)
        from offline_rag.rerank import cross_encoder
        require(hashlib.sha256(Path(cross_encoder.__file__).read_bytes()).hexdigest()
                == "44899205c24cb7275d4cedf6355b6e5aabb2c2887a392f7ec69da70b5ec39f75", "instrumentation byte mismatch")
        require(hasattr(reranker, "cpu_diagnostic_samples"), "instrumentation not active")
        reranker.cpu_diagnostic_samples = []
        hybrid = HybridRetriever(settings,dense=DenseRetriever(settings,embedder=embedder,backend=qdrant))
        rr = HybridRerankRetriever(settings,hybrid=hybrid,reranker=reranker)
        assembler = HybridRerankContextAssembler(settings,retriever=rr,store=structures)
        import torch
        from offline_rag.dense.st_onnx_runtime import FROZEN_ORT_INTRA_OP_THREADS, FROZEN_ORT_INTER_OP_THREADS

        def read_cgroup(name):
            path = Path("/sys/fs/cgroup") / name
            return path.read_text().strip() if path.is_file() else None

        print(json.dumps({
            "ort_intra_configured":FROZEN_ORT_INTRA_OP_THREADS,
            "ort_inter_configured":FROZEN_ORT_INTER_OP_THREADS,
            "torch_intra":torch.get_num_threads(),
            "torch_inter":torch.get_num_interop_threads(),
            "visible_cpus":os.cpu_count(),
            "affinity_cpus":len(os.sched_getaffinity(0)),
            "cpu_max":read_cgroup("cpu.max"),
            "cpuset_effective":read_cgroup("cpuset.cpus.effective"),
        }),flush=True)
        from offline_rag.rerank import retrieve as rerank_retrieve

        from types import SimpleNamespace
        fixtures = [SimpleNamespace(chunk_id="b"), SimpleNamespace(chunk_id="a")]
        def fixture_order(scores):
            return [x.chunk_id for x,_ in rerank_retrieve._sort_scored(fixtures,scores)]
        require(fixture_order([0.0,0.0]) == ["a","b"] and
                fixture_order([5e-6,0.0]) == ["b","a"], "exact/near-tie comparator failure")
        captured = {}
        hooked = set()
        original_load = reranker._load
        original_sort = rerank_retrieve._sort_scored

        def capture_inputs(module, args, kwargs):
            captured["inputs"].append(dict(kwargs))

        def capture_positions(module, args):
            captured["positions"].append(args[0])


        def observed_load():
            tokenizer, model = original_load()
            if id(model) not in hooked:
                require(all(x.dtype == torch.float32 for x in model.parameters()), "unexpected model dtype")
                position_modules = [m for name, m in model.named_modules()
                                    if name.endswith(".embeddings.position_embeddings")]
                require(len(position_modules) == 1, "expected one position embedding module")
                model.register_forward_pre_hook(capture_inputs, with_kwargs=True)
                position_modules[0].register_forward_pre_hook(capture_positions)
                hooked.add(id(model))
            return tokenizer, model

        def observed_sort(candidates, scores):
            ranked = original_sort(candidates, scores)
            captured["input_ids"] = [c.chunk_id for c in candidates]
            captured["document_ids"] = [c.document_id for c in candidates]
            captured["logits"] = list(scores)
            captured["ranked_ids"] = [c.chunk_id for c, _ in ranked]
            return ranked

        reranker._load = observed_load
        rerank_retrieve._sort_scored = observed_sort

        def tensor_fingerprint(tensor):
            return [str(tensor.dtype), list(tensor.shape),
                    hashlib.sha256(tensor.detach().contiguous().numpy().tobytes()).hexdigest()]

        baseline = None

        def record_parity(context, phase):
            nonlocal baseline
            require(all(v.dtype == torch.int64 for x in captured["inputs"] for v in x.values()), "encoded input dtype")
            require(len(captured["inputs"]) == len(captured["positions"]) >= 1, "missing input or position capture")
            ids, scores = captured["input_ids"], captured["logits"]
            require(len(ids) == len(set(ids)) == len(scores) and 1 <= len(scores) <= 10, "score association count mismatch")
            require(set(captured["document_ids"]) == set(docids), "document scope mismatch")
            require(sum(x["input_ids"].shape[0] for x in captured["inputs"]) == len(ids), "input count mismatch")
            require(captured["ranked_ids"] == [cid for cid, _ in sorted(zip(ids, scores), key=lambda item: (-item[1], item[0]))],
                    "unexpected tie break or score association")
            record = {
                "input_ids": ids,
                "document_ids": captured["document_ids"],
                "encoded": [{k:tensor_fingerprint(v) for k,v in x.items()} for x in captured["inputs"]],
                "positions": [tensor_fingerprint(p) for p in captured["positions"]],
                "ranked_ids": captured["ranked_ids"],
                "anchors": [a.chunk_id for a in context.anchors],
                "evidence": [hashlib.sha256(u.model_dump_json().encode()).hexdigest() for u in context.evidence_units],
                "packed_context": hashlib.sha256(context.assembled_text.encode()).hexdigest(),
                "context_tokens": context.context_token_count,
                "logits": scores,
            }
            identity = {
                key:hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
                for key,value in record.items() if key not in ("packed_context","context_tokens")
            } | {"packed_context": record["packed_context"],"context_tokens": record["context_tokens"]}
            print(json.dumps({"phase":phase,"scientific_identity":identity}),flush=True)
            if phase == "cold":
                baseline = identity
            else:
                print(json.dumps({"cold_warm_exact_match":baseline == identity}),flush=True)
                require(baseline == identity, "cold/warm scientific identities differ")

        for phase in ("cold","warm"):
            rss = capture_resource_observation("end_to_end").ram_rss_bytes_before
            reranker.cpu_diagnostic_samples.clear()
            captured.clear()
            captured.update(inputs=[], positions=[])
            before = resource.getrusage(resource.RUSAGE_SELF)
            stage = phase + "_assembler"
            context = assembler.assemble(
                query=question, corpus_name=b.corpus_name, check_ready=False,
                dense_index_id=b.dense_index_id, dense_collection_name=b.dense_collection_name,
                lexical_index_id=b.lexical_index_id, chunk_set_id=b.chunk_set_id,
                corpus_id=b.corpus_id, document_ids=docids,
            )
            after = resource.getrusage(resource.RUSAGE_SELF)
            stage = phase + "_parity"
            record_parity(context,phase)
            stage = phase + "_timing_projection"
            require(len(reranker.cpu_diagnostic_samples) == 1, "expected one scorer sample")
            sample = reranker.cpu_diagnostic_samples[0]
            require([b["batch_size"] for b in sample["batches"]] == [len(captured["input_ids"])], "batch shape mismatch")
            require(sample["cold_at_entry"] == int(phase == "cold"), "unexpected load state")
            print(json.dumps({"bge_phase":phase,"profile":sample}),flush=True)
            meta = context.metadata
            t = meta["latency_ms"]
            r = t["hybrid_rerank_breakdown"]
            h = r["hybrid_breakdown"]
            print(json.dumps({
                "phase":phase,"dense_ms":h["dense"],"lexical_ms":h["lexical"],"fusion_ms":h["fusion"],
                "pair_build_ms":r["pair_build"],"rerank_infer_ms":r["rerank_infer"],
                "sort_ms":r["sort"],"context_expand_ms":t["context_expand"],"assembler_total_ms":t["total"],
                "reranker_input_count":len(captured["input_ids"]),"candidate_count":meta["input_pool_size"],"evidence_unit_count":context.diagnostics.evidence_unit_count,
                "context_token_count":context.context_token_count,"process_wall_ms":round((time.perf_counter()-started)*1000),
                "rss_before_bytes":rss,"rss_after_bytes":capture_resource_observation("end_to_end").ram_rss_bytes_before,"peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "cpu_user_s":after.ru_utime-before.ru_utime,
                "cpu_system_s":after.ru_stime-before.ru_stime,
                "host_available_kib":int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))),
                "embedding_profile":embedder.profile.profile_id,"reranker_device":reranker.device,
            }),flush=True)
    finally:
        qdrant.close()

try:
    main()
except Exception as exc:
    print(json.dumps({"failed_stage":stage,"exception_class":type(exc).__name__,"reason":str(exc) if type(exc) is ValueError else None}),flush=True)
    sys.exit(1)
