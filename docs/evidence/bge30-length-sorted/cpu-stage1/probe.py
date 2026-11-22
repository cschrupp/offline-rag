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

def recipes(settings):
    global stage
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
            k: getattr(settings,k).model_dump(mode="json", exclude={"batching_strategy"} if k == "reranker" else None) for k in (
                "dense","reranker","fusion","context","lexical","indexing"
            )}, sort_keys=True).encode()).hexdigest(),
    }
    require(result["workspace_revision"] == 4 and sid == "snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196", "previous publication mismatch")
    require(result["science_settings_hash"] == "5dce337dc1875b2aa615d62ee771a0ae384559c2da14be384e067ded035f5417", "previous retrieval settings mismatch")
    return result, question, docids, structures, ws.backing_corpus_name

def rich(settings):
    global stage
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
    pointer_id = ProductPublicationRegistry(settings).published_snapshot_id(ws.backing_corpus_name)
    require(pointer_id == sid, "Rich publication pointer drift")
    result = {
        "published_pointer": pointer_id,
        "workspace_id": wsid, "workspace_revision": ws.revision,
        "question_sha256": digest, "historical_retrieval_question_sha256": historical_hash,
        "historical_retrieval_matches": historical_hash == digest,
        "historical_context_ms": historical_query["execution"]["context_latency_ms"],
        "snapshot_id": sid, "source_inventory_sha256": hashlib.sha256(
            store.workspace_path(wsid).read_bytes()).hexdigest(),
        "document_id": next(iter(docids)), "passages": dense.indexed_child_count,
        "identities": m.model_dump(mode="json", exclude={"corpus_manifest","chunk_manifest","dense_index_manifest","lexical_index_manifest"}),
        "science_settings_hash": hashlib.sha256(json.dumps({
            k: getattr(settings,k).model_dump(mode="json", exclude={"batching_strategy"} if k == "reranker" else None) for k in (
                "dense","reranker","fusion","context","lexical","indexing"
            )}, sort_keys=True).encode()).hexdigest(),
    }
    require(result["workspace_revision"] == 2 and sid == "snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca", "previous publication mismatch")
    require(result["science_settings_hash"] == "5dce337dc1875b2aa615d62ee771a0ae384559c2da14be384e067ded035f5417", "previous retrieval settings mismatch")
    return result, question, docids, structures, ws.backing_corpus_name

def audit_model(settings):
    from offline_rag.rerank.provision import resolve_reranker_model_dir
    model_dir = resolve_reranker_model_dir(reranker_artifacts_root=settings.paths.reranker_artifacts,
                                           model_path=settings.reranker.model.model_path)
    require(settings.reranker.model.revision == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e", "checkpoint revision mismatch")
    for name, expected_hash in {'config.json': '13dcd6c31d9fec9d1d8e158702072f62d7fa7d312a64b9fe057bec9a08cfe41a', 'model.safetensors': 'd9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286', 'tokenizer.json': '69564b696052886ed0ac63fa393e928384e0f8caada38c1f4864a9bfbf379c15', 'tokenizer_config.json': '7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4', 'sentencepiece.bpe.model': 'cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865', 'special_tokens_map.json': '8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835'}.items():
        with (model_dir / name).open("rb") as stream:
            require(hashlib.file_digest(stream, "sha256").hexdigest() == expected_hash, "checkpoint file hash mismatch")

def measure(settings, workloads):
    import signal
    import torch
    from offline_rag.app.runtime import default_resource_factories
    from offline_rag.context.assemble import HybridRerankContextAssembler
    from offline_rag.dense.retrieve import DenseRetriever
    from offline_rag.hybrid.retrieve import HybridRetriever
    from offline_rag.rerank import retrieve as rerank_retrieve
    from offline_rag.rerank.retrieve import HybridRerankRetriever

    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    require(len(os.sched_getaffinity(0)) == 4 and settings.reranker.input_k == 30, "CPU or depth mismatch")
    require((torch.get_num_threads(), torch.get_num_interop_threads()) == (2, 2), "thread mismatch")
    factory = default_resource_factories()
    qdrant = factory.qdrant(settings)
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    embedder = factory.embedder(settings)
    arms = {}
    for code, strategy in (("A", "consecutive"), ("B", "length_sorted_8")):
        rr = settings.reranker.model_copy(update={"batching_strategy": strategy})
        effective = settings.model_copy(update={"reranker": rr})
        arms[code] = (effective, factory.reranker(effective))
    tok, model = arms["A"][1]._load()
    require(all(s.device == "cpu" for _, s in arms.values()), "reranker device drift")
    require(all(x.dtype == torch.float32 for x in model.parameters()), "model dtype drift")
    require(embedder.profile.profile_id == "cpu_onnx_fp32_v1", "embedding profile drift")
    print(json.dumps({"runtime": {"torch": torch.__version__, "threads": [2, 2],
          "effective_cpus": len(os.sched_getaffinity(0)), "embedder": embedder.profile.profile_id,
          "reranker_device": "cpu"}}), flush=True)
    sample = {}
    class ObservedTokenizer:
        def __getattr__(self, name):
            return getattr(tok, name)
        def __call__(self, **kwargs):
            start = time.perf_counter()
            result = tok(**kwargs)
            if not kwargs["padding"]:
                sample["prepass_s"] += time.perf_counter() - start
            return result
    for _, scorer in arms.values():
        scorer._loaded = (ObservedTokenizer(), model)
    position_modules = [m for n, m in model.named_modules() if n.endswith(".embeddings.position_embeddings")]
    require(len(position_modules) == 1, "position module missing")
    def before_forward(_, args, kwargs):
        sample["tensors"].append(kwargs)
        sample["started"] = time.perf_counter()
    def after_forward(_, args, result):
        sample["forward_s"].append(time.perf_counter() - sample["started"])
        require(result.logits.dtype == torch.float32, "logit dtype drift")
        sample["forward_logits"].extend(result.logits.view(-1).tolist())
    model.register_forward_pre_hook(before_forward, with_kwargs=True)
    model.register_forward_hook(after_forward)
    position_modules[0].register_forward_pre_hook(lambda _, args: sample["positions"].append(args[0]))
    original_sort = rerank_retrieve._sort_scored
    def observe_sort(candidates, scores):
        ordered = original_sort(candidates, scores)
        sample.update(ids=[c.chunk_id for c in candidates], logits=list(scores),
                      ranked=[c.chunk_id for c, _ in ordered])
        return ordered
    rerank_retrieve._sort_scored = observe_sort
    for _, scorer in arms.values():
        score_pairs = scorer.score_pairs
        def observe_pairs(pairs, run=score_pairs):
            sample["pairs"] = pairs
            start = time.perf_counter()
            scores = run(pairs)
            sample["scorer_s"] = time.perf_counter() - start
            return scores
        scorer.score_pairs = observe_pairs
    observations = 0
    try:
        for label, (identity, question, scope, structures, corpus) in workloads.items():
            snapshot = registry.resolve_snapshot(corpus, identity["snapshot_id"])
            require(registry.published_snapshot_id(corpus) == identity["snapshot_id"], "isolated publication mismatch")
            assemblers = {}
            for arm, (effective, scorer) in arms.items():
                binding = build_snapshot_query_binding(effective, snapshot)
                hybrid = HybridRetriever(effective, dense=DenseRetriever(effective, embedder=embedder, backend=qdrant))
                retriever = HybridRerankRetriever(effective, hybrid=hybrid, reranker=scorer)
                assemblers[arm] = (binding, HybridRerankContextAssembler(effective, retriever=retriever, store=structures))
            baseline_identity = None
            reference_records = {}
            expected_count = 30 if label == "Recipes" else 10
            schedule = ("AB", "AB", "BA", "AB") if label == "Recipes" else ("BA", "BA", "AB", "BA")
            for block, order in enumerate(schedule):
                entries = {}
                for arm in order:
                    observations += 1
                    require(observations <= 16, "call budget exceeded")
                    print(json.dumps({"start": observations, "workload": label, "block": block, "arm": arm}), flush=True)
                    sample.clear()
                    sample.update(tensors=[], positions=[], forward_s=[], forward_logits=[], prepass_s=0.0)
                    binding, assembler = assemblers[arm]
                    wall, cpu = time.perf_counter(), time.process_time()
                    signal.alarm(180)
                    context = assembler.assemble(
                        query=question, corpus_name=binding.corpus_name, check_ready=False,
                        dense_index_id=binding.dense_index_id, dense_collection_name=binding.dense_collection_name,
                        lexical_index_id=binding.lexical_index_id, chunk_set_id=binding.chunk_set_id,
                        corpus_id=binding.corpus_id, document_ids=scope,
                    )
                    signal.alarm(0)
                    total_s, cpu_s = time.perf_counter() - wall, time.process_time() - cpu
                    pairs = sample["pairs"]
                    ids = sample["ids"]
                    require(ids == [pair.chunk_id for pair in pairs] and len(set(ids)) == expected_count, "input identity mismatch")
                    original = tok(text=[p.query_text for p in pairs], text_pair=[p.passage_text for p in pairs],
                                   max_length=1024, truncation="only_second", padding=False)["input_ids"]
                    ordinals = list(range(expected_count))
                    if arm == "B":
                        ordinals.sort(key=lambda i: (len(original[i]), i))
                    shapes, active_ids, offset = [], {}, 0
                    for batch, positions in zip(sample["tensors"], sample["positions"], strict=True):
                        rows, width = batch["input_ids"].shape
                        lengths = []
                        for index in range(rows):
                            ordinal = ordinals[offset + index]
                            mask = batch["attention_mask"][index].bool()
                            token_ids = batch["input_ids"][index, mask].tolist()
                            length = len(token_ids)
                            require(token_ids == original[ordinal], "active encoded input drift")
                            require(mask.tolist() == [True]*length + [False]*(width-length), "non-right padding")
                            require(sample["forward_logits"][offset + index] == sample["logits"][ordinal], "score scatter mismatch")
                            active_ids[ordinal] = hashlib.sha256(json.dumps(
                                [token_ids, mask[:length].tolist(), positions[index, mask].tolist()]
                            ).encode()).hexdigest()
                            lengths.append(length)
                        shapes.append({"shape": [rows, width], "lengths": lengths,
                                       "padded_slots": rows*width-sum(lengths)})
                        offset += rows
                    size = 16 if arm == "A" else 8
                    require([x["shape"][0] for x in shapes] == [
                        min(size, expected_count-i) for i in range(0, expected_count, size)], "batch shape drift")
                    ranked = [cid for cid, _ in sorted(zip(ids, sample["logits"], strict=True), key=lambda x: (-x[1], x[0]))]
                    require(sample["ranked"] == ranked, "canonical tie-break drift")
                    state = {"candidates": ids, "ranking": ranked,
                             "active_inputs": [active_ids[i] for i in range(expected_count)],
                             "anchors": [a.chunk_id for a in context.anchors],
                             "evidence": [hashlib.sha256(u.model_dump_json().encode()).hexdigest() for u in context.evidence_units],
                             "packed_sha256": hashlib.sha256(context.assembled_text.encode()).hexdigest()}
                    if baseline_identity is None:
                        baseline_identity = state
                    logits_by_id = dict(zip(ids, sample["logits"], strict=True))
                    margins = [logits_by_id[x]-logits_by_id[y] for x,y in zip(ranked, ranked[1:])]
                    entries[arm] = (sample["logits"], state == baseline_identity)
                    row = {"completed": observations, "workload": label, "block": block, "arm": arm,
                           "assembler_s": total_s, "cpu_s": cpu_s, "scorer_s": sample["scorer_s"],
                           "forward_s": sample["forward_s"], "prepass_s": sample["prepass_s"], "batches": shapes,
                           "rss_peak_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                           "min_adjacent_logit_margin": min(margins), "near_tie_count":sum(m <= 1e-4 for m in margins),
                           "candidate_count": len(ids), "context_tokens": context.context_token_count,
                           "identity": state, "identity_matches": state == baseline_identity}
                    print(json.dumps(row), flush=True)
                a, b = entries["A"][0], entries["B"][0]
                delta = [y-x for x,y in zip(a,b,strict=True)]
                numerical = all(abs(d) <= 1e-4+1e-5*abs(x) for x,d in zip(a,delta,strict=True))
                print(json.dumps({"workload":label,"parity_block":block,"numerical":numerical,
                                  "identity":all(ok for _,ok in entries.values()),"logit_deltas":delta}), flush=True)
                reference_records[block] = numerical and all(ok for _,ok in entries.values())
            print(json.dumps({"workload":label,"all_parity":all(reference_records.values())}),flush=True)
    finally:
        qdrant.close()
    require(observations == 16, "incomplete experiment")


def main():
    settings = load_settings()
    workloads = {"Recipes": recipes(settings), "Rich": rich(settings)}
    identities = {key: data[0] for key, data in workloads.items()}
    if sys.argv[1] == "inspect":
        audit_model(settings)
        print(json.dumps(identities, sort_keys=True), flush=True)
        return
    require(identities == json.loads(Path("/diagnostic/before.json").read_bytes()), "copied state mismatch")
    measure(settings, workloads)

try:
    main()
except Exception as exc:
    print(json.dumps({"failure_stage":stage, "exception_type":type(exc).__name__,
                      "controlled_reason":None}), flush=True)
    raise SystemExit(1) from None
