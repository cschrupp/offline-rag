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
    question = normalize_product_question("What ingredients are needed for the baked French fries?")
    digest = hashlib.sha256(question.encode()).hexdigest()
    stage = "incident_trace_scope"
    matches = []
    for path in (settings.paths.traces / "conversation").glob("*.json"):
        c = json.loads(path.read_bytes())
        if c.get("question_sha256") == digest and c["created_at"].startswith("2026-11-21T04:"):
            q = json.loads((settings.paths.traces / (c["query_trace_id"] + ".json")).read_bytes())
            require(q["request"]["question_sha256"] == digest and not c["resolver_invoked"], "question mismatch")
            require(q["request"]["source_scope"] == c["source_scope"] and q["snapshot_id"] == c["snapshot_id"], "trace scope mismatch")
            matches.append(c)
    require(len(matches) == 10, "expected ten matching incident traces")
    scope = matches[0]["source_scope"]
    wsid = matches[0]["workspace_id"]
    sid = matches[0]["snapshot_id"]
    require(all((x["workspace_id"], x["snapshot_id"], x["source_scope"]) == (wsid,sid,scope) for x in matches), "incident scopes differ")
    require(scope["mode"] == "selected" and len(scope["document_ids"]) == 1, "expected selected document")
    store = WorkspaceStore(settings)
    ws = store.get(wsid)
    require(ws.status == "active" and ws.current_snapshot_id == sid, "workspace no longer at incident snapshot")
    actual, _, docids = _resolve_workspace_source_scope(ws, source_ids=scope["source_ids"])
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
    require(dense.expected_child_count == dense.indexed_child_count == 603, "unexpected passage population")
    require((settings.paths.qdrant_storage / "collection" / dense.collection_name).is_dir(), "dense storage missing")
    structures = load_structure_store_for_chunk_manifest(settings, Path(m.chunk_manifest).name)
    stage = "managed_operations"
    active = 0
    for path in settings.paths.workspaces.glob("*/operations/by_id/*.json"):
        status = json.loads(path.read_bytes())["status"]
        if status not in ("succeeded","failed","canceled","cancelled","interrupted"):
            active += 1
    require(active == 0, "managed operation not terminal")
    pointer_id = ProductPublicationRegistry(settings).published_snapshot_id(ws.backing_corpus_name)
    require(pointer_id==sid, "baseline corpus pointer drift")
    manifest_bytes = snapshot_manifest_path(settings.paths.corpora, ws.backing_corpus_name, sid).read_bytes()
    result = {
        "published_pointer":pointer_id, "snapshot_manifest_sha256":hashlib.sha256(manifest_bytes).hexdigest(),
        "workspace_id": wsid, "workspace_revision": ws.revision,
        "snapshot_id": sid, "source_inventory_sha256": hashlib.sha256(
            store.workspace_path(wsid).read_bytes()).hexdigest(),
        "document_id": next(iter(docids)), "passages": dense.indexed_child_count,
        "identities": m.model_dump(mode="json", exclude={"corpus_manifest","chunk_manifest","dense_index_manifest","lexical_index_manifest"}),
        "science_settings_hash": hashlib.sha256(json.dumps({
            k: getattr(settings,k).model_dump(mode="json") for k in (
                "dense","reranker","fusion","context","lexical","indexing"
            )}, sort_keys=True).encode()).hexdigest(),
    }
    require(result["workspace_revision"] == 4 and sid == "snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196", "previous publication mismatch")
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
    from offline_rag.app.errors import AppError
    from offline_rag.app.runtime import default_resource_factories
    from offline_rag.config.models import RerankerSettings
    from offline_rag.rerank.config_hash import build_reranker_config_hash
    from offline_rag.context.assemble import HybridRerankContextAssembler
    from offline_rag.dense.retrieve import DenseRetriever
    from offline_rag.evaluation.performance_14.resources import capture_resource_observation
    from offline_rag.hybrid.retrieve import HybridRetriever
    from offline_rag.rerank.retrieve import HybridRerankRetriever
    factories = default_resource_factories()
    qdrant = factories.qdrant(settings)
    try:
        registry30 = ProductPublicationRegistry(settings,qdrant=qdrant)
        snapshot30 = registry30.resolve_snapshot(ws.backing_corpus_name,sid)
        require(registry30.published_snapshot_id(ws.backing_corpus_name)==sid, "original copied pointer mismatch")
        original_path = snapshot_manifest_path(settings.paths.corpora, ws.backing_corpus_name, sid)
        original_bytes = original_path.read_bytes()
        rr15 = RerankerSettings.model_validate(settings.reranker.model_dump() | {"input_k":15})
        settings15 = settings.model_copy(update={"reranker":rr15})
        registry15 = ProductPublicationRegistry(settings15,qdrant=qdrant)
        candidate = snapshot30.identity.model_copy(update={"reranker_config_hash":build_reranker_config_hash(settings15)})
        require(compute_snapshot_id(candidate)!=sid, "depth does not change immutable identity")
        stage = "publish_isolated_bge15"
        sid15 = registry15.publish(ws.backing_corpus_name,candidate)
        snapshot15 = registry15.resolve_snapshot(ws.backing_corpus_name,sid15)
        require(registry30.resolve_snapshot(ws.backing_corpus_name,sid).snapshot_id==sid
                and original_path.read_bytes()==original_bytes, "original snapshot changed")
        require(store.get(wsid)==ws, "copied workspace unexpectedly changed")
        require(snapshot15.identity.model_dump(exclude={"reranker_config_hash"})==
                snapshot30.identity.model_dump(exclude={"reranker_config_hash"}), "backing changed")
        for registry, wrong in ((registry30,sid15),(registry15,sid)):
            try:
                registry.resolve_snapshot(ws.backing_corpus_name,wrong)
            except AppError as exc:
                require(exc.details.get("reason")=="reranker_config_stale", "wrong mismatch reason")
            else:
                require(False,"mismatched settings unexpectedly resolved")
        print(json.dumps({"publication_validated":True,"snapshot_30":sid,"snapshot_15":sid15,
            "reranker_hash_30":snapshot30.identity.reranker_config_hash,
            "reranker_hash_15":snapshot15.identity.reranker_config_hash,
            "cross_profile_rejections":2,"real_qdrant_and_lexical_validation":True,
            "original_manifest_sha256":hashlib.sha256(original_bytes).hexdigest(),
            "copied_workspace_unchanged":True}),flush=True)
        bindings = {30:build_snapshot_query_binding(settings,snapshot30),
                    15:build_snapshot_query_binding(settings15,snapshot15)}
        embedder = factories.embedder(settings)
        reranker = factories.reranker(settings)
        from offline_rag.rerank import cross_encoder
        require(hashlib.sha256(Path(cross_encoder.__file__).read_bytes()).hexdigest()
                == "9ac4a617c7e07de8f962e02fce54a4e04e529cf7581580027bf1746094c6d3a7", "instrumentation byte mismatch")
        reranker.cpu_diagnostic_samples = []
        assemblers = {}
        for depth, arm_settings in ((30,settings),(15,settings15)):
            hybrid = HybridRetriever(arm_settings,dense=DenseRetriever(arm_settings,embedder=embedder,backend=qdrant))
            rr = HybridRerankRetriever(arm_settings,hybrid=hybrid,reranker=reranker)
            assemblers[depth] = HybridRerankContextAssembler(arm_settings,retriever=rr,store=structures)
        import torch
        from offline_rag.dense.st_onnx_runtime import FROZEN_ORT_INTRA_OP_THREADS, FROZEN_ORT_INTER_OP_THREADS

        def read_cgroup(name):
            path = Path("/sys/fs/cgroup") / name
            return path.read_text().strip() if path.is_file() else None

        require(len(os.sched_getaffinity(0))==4 and read_cgroup("cpu.max")=="max 100000", "CPU allocation changed")
        require((FROZEN_ORT_INTRA_OP_THREADS,FROZEN_ORT_INTER_OP_THREADS)==(8,1)
                and (settings.fusion.dense_top_k,settings.fusion.lexical_top_k)==(30,30)
                and settings.reranker.output_k==10 and settings.context.anchor_k==5
                and reranker.device=="cpu" and reranker.batch_size==16 and reranker.max_length==1024, "baseline policy drift")
        print(json.dumps({
            "torch_version":torch.__version__,
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
                require(all(x.dtype == torch.float32 for x in model.parameters()), "model parameters not FP32")
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

        def record(context, sample, depth):
            ids, scores = captured["input_ids"], captured["logits"]
            require(len(ids) == len(set(ids)) == len(scores) == depth, "score association count mismatch")
            require(set(captured["document_ids"]) == set(docids), "document scope mismatch")
            require(captured["ranked_ids"] == [cid for cid, _ in sorted(zip(ids, scores), key=lambda item: (-item[1], item[0]))],
                    "unexpected tie break or score association")
            by_candidate = {}
            for kwargs, positions, batch in zip(captured["inputs"], captured["positions"], sample["batches"], strict=True):
                require(set(kwargs) == {"input_ids", "attention_mask"}, "unexpected model inputs")
                for j, ordinal in enumerate(batch["ordinals"]):
                    require(ordinal not in by_candidate, "duplicate batch ordinal")
                    mask = kwargs["attention_mask"][j].bool()
                    require(mask.tolist() == [True]*int(mask.sum()) + [False]*int((~mask).sum()), "non-right padding")
                    by_candidate[ordinal] = {
                        "input_ids": tensor_fingerprint(kwargs["input_ids"][j, mask]),
                        "attention_mask": tensor_fingerprint(kwargs["attention_mask"][j, mask]),
                        "positions": tensor_fingerprint(positions[j, mask]),
                    }
            require(set(by_candidate) == set(range(depth)), "missing batch ordinals")
            return {
                "candidate_ids": ids, "document_ids": captured["document_ids"],
                "encoded": [by_candidate[i] for i in range(depth)],
                "ranked_ids": captured["ranked_ids"],
                "anchors": [a.chunk_id for a in context.anchors],
                "evidence": [hashlib.sha256(u.model_dump_json().encode()).hexdigest() for u in context.evidence_units],
                "packed_context": hashlib.sha256(context.assembled_text.encode()).hexdigest(),
                "context_tokens": context.context_token_count, "logits": scores,
            }

        schedule = ("ABCD","ABDC","BCAD","CDBA","DACB")
        arms = {"A":(30,False,[16,14]),"B":(15,False,[15]),
                "C":(30,True,[8,8,8,6]),"D":(15,True,[8,7])}
        records = {}
        original_order = None
        parity_pass = True
        for block, order in enumerate(schedule):
            for arm in order:
                depth, length_sort, shapes = arms[arm]
                phase = f"{block}_{arm}"
                reranker.length_sort = length_sort
                b = bindings[depth]
                assembler = assemblers[depth]
                rss = capture_resource_observation("end_to_end").ram_rss_bytes_before
                reranker.cpu_diagnostic_samples.clear()
                captured.clear()
                captured.update(inputs=[], positions=[])
                start_ns = time.time_ns()
                before = resource.getrusage(resource.RUSAGE_SELF)
                stage = phase + "_assembler"
                context = assembler.assemble(
                    query=question, corpus_name=b.corpus_name, check_ready=False,
                    dense_index_id=b.dense_index_id, dense_collection_name=b.dense_collection_name,
                    lexical_index_id=b.lexical_index_id, chunk_set_id=b.chunk_set_id,
                    corpus_id=b.corpus_id, document_ids=docids,
                )
                after = resource.getrusage(resource.RUSAGE_SELF)
                end_ns = time.time_ns()
                stage = phase + "_parity"
                stage = phase + "_timing_projection"
                require(len(reranker.cpu_diagnostic_samples) == 1, "expected one scorer sample")
                sample = reranker.cpu_diagnostic_samples[0]
                require([b["batch_size"] for b in sample["batches"]] == shapes, "batch shape drift")
                require(sample["cold_at_entry"] == int(block == 0 and arm == "A"), "unexpected load state")
                ordinals = [i for batch in sample["batches"] for i in batch["ordinals"]]
                actual_lengths = dict(zip(ordinals, (n for batch in sample["batches"] for n in batch["lengths"]), strict=True))
                expected_order = list(range(depth)) if not length_sort else sorted(range(depth), key=lambda i:(actual_lengths[i],i))
                require(ordinals == expected_order, "unexpected stable batch order")
                records[block,arm] = record(context,sample,depth)
                pool = records[block,arm]["candidate_ids"]
                if original_order is None:
                    require(phase=="0_A", "first baseline missing")
                    original_order = pool
                require(pool == original_order[:depth], "arm input is not the original fused prefix")
                current = records[block,arm]
                print(json.dumps({"record":phase, **{k:v for k,v in current.items() if k not in ("logits","encoded")}}),flush=True)
                print(json.dumps({"bge_phase":phase,"profile":sample}),flush=True)
                meta = context.metadata
                t = meta["latency_ms"]
                r = t["hybrid_rerank_breakdown"]
                h = r["hybrid_breakdown"]
                print(json.dumps({
                    "phase":phase,"start_epoch_ns":start_ns,"end_epoch_ns":end_ns,"depth":depth,"dense_ms":h["dense"],"lexical_ms":h["lexical"],"fusion_ms":h["fusion"],
                    "pair_build_ms":r["pair_build"],"rerank_infer_ms":r["rerank_infer"],
                    "sort_ms":r["sort"],"context_expand_ms":t["context_expand"],"assembler_total_ms":t["total"],
                    "candidate_count":meta["input_pool_size"],"evidence_unit_count":context.diagnostics.evidence_unit_count,
                    "context_token_count":context.context_token_count,"process_wall_ms":round((time.perf_counter()-started)*1000),
                    "rss_before_bytes":rss,"rss_after_bytes":capture_resource_observation("end_to_end").ram_rss_bytes_before,"peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "cpu_user_s":after.ru_utime-before.ru_utime,
                    "cpu_system_s":after.ru_stime-before.ru_stime,
                    "host_available_kib":int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))),
                    "embedding_profile":embedder.profile.profile_id,"reranker_device":reranker.device,
                }),flush=True)
            for control_arm, treatment_arm in (("A","C"),("B","D")):
                control,treatment = records[block,control_arm],records[block,treatment_arm]
                deltas = [y-x for x,y in zip(control["logits"],treatment["logits"],strict=True)]
                matches = {k:control[k]==treatment[k] for k in control if k!="logits"}
                numerical = all(abs(delta)<=1e-4+1e-5*abs(x) for delta,x in zip(deltas,control["logits"],strict=True))
                passed = all(matches.values()) and numerical
                parity_pass = parity_pass and passed
                print(json.dumps({"parity_block":block,"pair":treatment_arm+control_arm,"pass":passed,"numerical_pass":numerical,
                    "matches":matches,"signed_deltas":deltas,"max_abs_delta":max(map(abs,deltas))}),flush=True)
            for control_arm, treatment_arm in (("A","B"),("C","D")):
                high,low = records[block,control_arm],records[block,treatment_arm]
                common = set(high["ranked_ids"]) & set(low["ranked_ids"])
                high_common = [i for i in high["ranked_ids"] if i in common]
                low_common = [i for i in low["ranked_ids"] if i in common]
                print(json.dumps({"depth_block":block,"pair":treatment_arm+control_arm,
                    "fused_prefix_matches":low["candidate_ids"]==high["candidate_ids"][:15],
                    "reordered_common_candidates":high_common!=low_common,
                    "top5_overlap":len(set(high["ranked_ids"][:5]) & set(low["ranked_ids"][:5])),
                    "anchor_overlap":len(set(high["anchors"]) & set(low["anchors"])),
                    "anchor_order_matches":high["anchors"]==low["anchors"],
                    "evidence_overlap":len(set(high["evidence"]) & set(low["evidence"])),
                    "evidence_order_matches":high["evidence"]==low["evidence"],
                    "packed_context_matches":high["packed_context"]==low["packed_context"],
                    "context_tokens_high":high["context_tokens"],"context_tokens_low":low["context_tokens"]}),flush=True)
        print(json.dumps({"all_batching_parity_pass":parity_pass,"assembler_calls":len(records)}),flush=True)
    finally:
        qdrant.close()

try:
    main()
except Exception as exc:
    print(json.dumps({"failed_stage":stage,"exception_class":type(exc).__name__,"reason":str(exc) if type(exc) is ValueError else None}),flush=True)
    sys.exit(1)
