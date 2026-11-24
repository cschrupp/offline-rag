import hashlib
import json
import os
import sys
from pathlib import Path

from offline_rag.app.publication import (
    ProductPublicationRegistry,
    snapshot_manifest_path,
)
from offline_rag.app.query import (
    _resolve_workspace_source_scope,
    normalize_product_question,
)
from offline_rag.app.snapshot import CanonicalSnapshotManifest, compute_snapshot_id
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.vault import RawSourceVault
from offline_rag.config.loader import load_settings
from offline_rag.context.store import load_structure_store_for_chunk_manifest
from offline_rag.dense.persistence import load_index_manifest

stage = "settings"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def dispatch_preflight_validators(
    mode: str, *, recipes_validator, rich_validator, rich2_validator
):
    """Run the exact live binding validators required by this preflight mode."""
    validators = {"Recipes": recipes_validator, "Rich": rich_validator}
    if mode in {
        "rich2-stage1",
        "rich2-metadata",
        "native",
        "native-smoke",
        "native-metadata",
    }:
        return {"Recipes": recipes_validator()}, rich2_validator()
    if mode in {"metadata", "isolated", "native", "native-smoke"}:
        return {label: validator() for label, validator in validators.items()}, None
    raise ValueError("unsupported preflight mode")


def recipes(settings):
    global stage
    question = normalize_product_question(
        "What ingredients are needed for the baked French fries?"
    )
    digest = hashlib.sha256(question.encode()).hexdigest()
    stage = "incident_trace_scope"
    matches = []
    for path in (settings.paths.traces / "conversation").glob("*.json"):
        c = json.loads(path.read_bytes())
        if c.get("question_sha256") == digest and c["created_at"].startswith(
            "2026-11-21T04:"
        ):
            q = json.loads(
                (settings.paths.traces / (c["query_trace_id"] + ".json")).read_bytes()
            )
            require(
                q["request"]["question_sha256"] == digest and not c["resolver_invoked"],
                "question mismatch",
            )
            require(
                q["request"]["source_scope"] == c["source_scope"]
                and q["snapshot_id"] == c["snapshot_id"],
                "trace scope mismatch",
            )
            matches.append(c)
    require(len(matches) == 10, "expected ten matching incident traces")
    scope = matches[0]["source_scope"]
    wsid = matches[0]["workspace_id"]
    sid = matches[0]["snapshot_id"]
    require(
        all(
            (x["workspace_id"], x["snapshot_id"], x["source_scope"])
            == (wsid, sid, scope)
            for x in matches
        ),
        "incident scopes differ",
    )
    require(
        scope["mode"] == "selected" and len(scope["document_ids"]) == 1,
        "expected selected document",
    )
    store = WorkspaceStore(settings)
    ws = store.get(wsid)
    require(
        ws.status == "active" and ws.current_snapshot_id == sid,
        "workspace no longer at incident snapshot",
    )
    actual, _, docids = _resolve_workspace_source_scope(
        ws, source_ids=scope["source_ids"]
    )
    require(actual.model_dump(mode="json") == scope, "workspace source scope drift")
    stage = "snapshot_artifacts"
    m = CanonicalSnapshotManifest.model_validate_json(
        snapshot_manifest_path(
            settings.paths.corpora, ws.backing_corpus_name, sid
        ).read_bytes()
    )
    require(compute_snapshot_id(m) == sid, "snapshot hash mismatch")
    for root, name in (
        (settings.paths.manifests, m.corpus_manifest),
        (settings.paths.chunk_manifests, m.chunk_manifest),
        (settings.paths.index_manifests, m.dense_index_manifest),
        (settings.paths.lexical_index_manifests, m.lexical_index_manifest),
    ):
        require((root / Path(name).name).is_file(), "snapshot manifest missing")
    dense = load_index_manifest(
        settings.paths.index_manifests / Path(m.dense_index_manifest).name
    )
    require(
        dense.expected_child_count == dense.indexed_child_count == 603,
        "unexpected passage population",
    )
    require(
        (settings.paths.qdrant_storage / "collection" / dense.collection_name).is_dir(),
        "dense storage missing",
    )
    load_structure_store_for_chunk_manifest(settings, Path(m.chunk_manifest).name)
    stage = "managed_operations"
    active = 0
    for path in settings.paths.workspaces.glob("*/operations/by_id/*.json"):
        status = json.loads(path.read_bytes())["status"]
        if status not in (
            "succeeded",
            "failed",
            "canceled",
            "cancelled",
            "interrupted",
        ):
            active += 1
    require(active == 0, "managed operation not terminal")
    pointer_id = ProductPublicationRegistry(settings).published_snapshot_id(
        ws.backing_corpus_name
    )
    require(pointer_id == sid, "baseline corpus pointer drift")
    manifest_bytes = snapshot_manifest_path(
        settings.paths.corpora, ws.backing_corpus_name, sid
    ).read_bytes()
    result = {
        "published_pointer": pointer_id,
        "snapshot_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "workspace_id": wsid,
        "workspace_revision": ws.revision,
        "snapshot_id": sid,
        "source_inventory_sha256": hashlib.sha256(
            store.workspace_path(wsid).read_bytes()
        ).hexdigest(),
        "document_id": next(iter(docids)),
        "passages": dense.indexed_child_count,
        "identities": m.model_dump(
            mode="json",
            exclude={
                "corpus_manifest",
                "chunk_manifest",
                "dense_index_manifest",
                "lexical_index_manifest",
            },
        ),
        "science_settings_hash": hashlib.sha256(
            json.dumps(
                {
                    k: getattr(settings, k).model_dump(
                        mode="json",
                        exclude={"batching_strategy"} if k == "reranker" else None,
                    )
                    for k in (
                        "dense",
                        "reranker",
                        "fusion",
                        "context",
                        "lexical",
                        "indexing",
                    )
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }
    require(
        result["workspace_revision"] == 4
        and sid
        == "snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196",
        "previous publication mismatch",
    )
    require(
        result["science_settings_hash"]
        == "5dce337dc1875b2aa615d62ee771a0ae384559c2da14be384e067ded035f5417",
        "previous retrieval settings mismatch",
    )
    return result, ws.backing_corpus_name, actual.source_ids


def rich(settings):
    global stage
    question = normalize_product_question("Describe the naturalistic decision method")
    digest = hashlib.sha256(question.encode()).hexdigest()
    stage = "historical_trace_scope"
    historical = json.loads(
        (
            settings.paths.traces
            / "conversation"
            / "trace_5c7bcd76773a49a7a5ede5e0a32a4d30.json"
        ).read_bytes()
    )
    historical_query_id = "trace_4c701509255f474990998e3209ff620f"
    require(
        historical["query_trace_id"] == historical_query_id
        and historical["question_sha256"] == digest,
        "historical conversation binding mismatch",
    )
    historical_query = json.loads(
        (settings.paths.traces / (historical_query_id + ".json")).read_bytes()
    )
    historical_hash = historical["retrieval_question_sha256"]
    require(
        historical_hash == historical_query["request"]["question_sha256"],
        "historical retrieval hash binding mismatch",
    )
    require(
        historical["prior_turn_count"] == 2
        and historical["resolver_invoked"]
        and historical_query["status"] == "answered",
        "historical request identity mismatch",
    )
    scope = historical["source_scope"]
    wsid = historical["workspace_id"]
    sid = historical["snapshot_id"]
    require(
        wsid == "ws_73a29d6defb545e8958746d78ac80775"
        and scope["mode"] == "all_active"
        and len(scope["document_ids"]) == 1
        and historical_query["request"]["source_scope"] == scope
        and historical_query["snapshot_id"] == sid,
        "historical scope mismatch",
    )
    store = WorkspaceStore(settings)
    ws = store.get(wsid)
    require(
        ws.status == "active" and ws.current_snapshot_id == sid,
        "workspace no longer at incident snapshot",
    )
    actual, _, docids = _resolve_workspace_source_scope(ws, source_ids=None)
    require(actual.model_dump(mode="json") == scope, "workspace source scope drift")
    stage = "snapshot_artifacts"
    m = CanonicalSnapshotManifest.model_validate_json(
        snapshot_manifest_path(
            settings.paths.corpora, ws.backing_corpus_name, sid
        ).read_bytes()
    )
    require(compute_snapshot_id(m) == sid, "snapshot hash mismatch")
    for root, name in (
        (settings.paths.manifests, m.corpus_manifest),
        (settings.paths.chunk_manifests, m.chunk_manifest),
        (settings.paths.index_manifests, m.dense_index_manifest),
        (settings.paths.lexical_index_manifests, m.lexical_index_manifest),
    ):
        require((root / Path(name).name).is_file(), "snapshot manifest missing")
    dense = load_index_manifest(
        settings.paths.index_manifests / Path(m.dense_index_manifest).name
    )
    require(
        dense.expected_child_count == dense.indexed_child_count == 10,
        "unexpected passage population",
    )
    require(
        (settings.paths.qdrant_storage / "collection" / dense.collection_name).is_dir(),
        "dense storage missing",
    )
    load_structure_store_for_chunk_manifest(settings, Path(m.chunk_manifest).name)
    stage = "managed_operations"
    active = 0
    for path in settings.paths.workspaces.glob("*/operations/by_id/*.json"):
        status = json.loads(path.read_bytes())["status"]
        if status not in (
            "succeeded",
            "failed",
            "canceled",
            "cancelled",
            "interrupted",
        ):
            active += 1
    require(active == 0, "managed operation not terminal")
    pointer_id = ProductPublicationRegistry(settings).published_snapshot_id(
        ws.backing_corpus_name
    )
    require(pointer_id == sid, "Rich publication pointer drift")
    result = {
        "published_pointer": pointer_id,
        "workspace_id": wsid,
        "workspace_revision": ws.revision,
        "question_sha256": digest,
        "historical_retrieval_question_sha256": historical_hash,
        "historical_retrieval_matches": historical_hash == digest,
        "historical_context_ms": historical_query["execution"]["context_latency_ms"],
        "snapshot_id": sid,
        "source_inventory_sha256": hashlib.sha256(
            store.workspace_path(wsid).read_bytes()
        ).hexdigest(),
        "document_id": next(iter(docids)),
        "passages": dense.indexed_child_count,
        "identities": m.model_dump(
            mode="json",
            exclude={
                "corpus_manifest",
                "chunk_manifest",
                "dense_index_manifest",
                "lexical_index_manifest",
            },
        ),
        "science_settings_hash": hashlib.sha256(
            json.dumps(
                {
                    k: getattr(settings, k).model_dump(
                        mode="json",
                        exclude={"batching_strategy"} if k == "reranker" else None,
                    )
                    for k in (
                        "dense",
                        "reranker",
                        "fusion",
                        "context",
                        "lexical",
                        "indexing",
                    )
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }
    require(
        result["workspace_revision"] == 2
        and sid
        == "snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca",
        "previous publication mismatch",
    )
    require(
        result["science_settings_hash"]
        == "5dce337dc1875b2aa615d62ee771a0ae384559c2da14be384e067ded035f5417",
        "previous retrieval settings mismatch",
    )
    return result, ws.backing_corpus_name, actual.source_ids


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_rich2_binding(settings, binding: dict, *, qdrant=None) -> dict:
    """Validate Rich 2 metadata and optional physical snapshot backing."""
    require(
        binding.get("schema") == "seneca-rich2-stage1-binding-v1"
        and binding.get("status") == "prepared_not_execution_authority",
        "Rich 2 binding schema/status",
    )
    workspace_binding = binding["workspace"]
    source_binding = binding["source"]
    publication_binding = binding["publication"]
    artifacts_binding = binding["artifacts"]
    question_binding = binding["question"]

    workspace_id = workspace_binding["workspace_id"]
    store = WorkspaceStore(settings)
    workspace = store.get(workspace_id)
    workspace_path = store.workspace_path(workspace_id)
    workspace_bytes = workspace_path.read_bytes()
    inventory_sha = hashlib.sha256(workspace_bytes).hexdigest()
    require(workspace.status == "active", "Rich 2 workspace is not active")
    require(
        workspace.revision == workspace_binding["revision"]
        and workspace.current_snapshot_id == publication_binding["snapshot_id"],
        "Rich 2 workspace revision or snapshot drift",
    )
    require(
        inventory_sha
        == workspace_binding["source_inventory_sha256"]
        == workspace_binding["workspace_record_sha256"],
        "Rich 2 workspace record/inventory hash drift",
    )
    require(
        workspace.backing_corpus_name == workspace_binding["backing_corpus_name"],
        "Rich 2 corpus binding drift",
    )
    require(
        len(workspace.sources) == workspace_binding["source_count"] == 1
        and workspace.sources[0].active,
        "Rich 2 active source population drift",
    )

    source = workspace.sources[0]
    actual_source = {
        "source_id": source.source_id,
        "version": source.version,
        "document_id": source.document_id,
        "content_hash": source.content_hash,
        "byte_size": source.byte_size,
        "active": source.active,
        "active_from_revision": source.active_from_revision,
        "active_from_snapshot_id": source.active_from_snapshot_id,
    }
    require(actual_source == source_binding["identity"], "Rich 2 source identity drift")
    vault_meta = RawSourceVault(settings.paths.workspaces).verify_object(
        workspace_id, source.vault_object_id
    )
    require(
        vault_meta.content_hash == source_binding["content_sha256"]
        and vault_meta.byte_size == source_binding["byte_size"],
        "Rich 2 source bytes do not match the binding",
    )

    scope, _, document_ids = _resolve_workspace_source_scope(workspace, source_ids=None)
    expected_scope = binding["source_scope"]
    require(
        expected_scope
        == {
            "mode": "all_active",
            "source_ids": [source_binding["identity"]["source_id"]],
            "document_ids": [source_binding["identity"]["document_id"]],
        },
        "Rich 2 binding scope is malformed",
    )
    require(
        scope.workspace_id == workspace_id
        and scope.workspace_revision == workspace_binding["revision"]
        and scope.mode == expected_scope["mode"]
        and scope.source_ids == expected_scope["source_ids"]
        and scope.document_ids == expected_scope["document_ids"]
        and document_ids == frozenset(expected_scope["document_ids"]),
        "Rich 2 all-active scope drift",
    )

    question = normalize_product_question(question_binding["text"])
    question_sha = hashlib.sha256(question.encode("utf-8")).hexdigest()
    require(
        question_sha == question_binding["normalized_sha256"]
        and not question_binding["prior_turns"],
        "Rich 2 no-history question binding mismatch",
    )

    snapshot_id = publication_binding["snapshot_id"]
    manifest_path = snapshot_manifest_path(
        settings.paths.corpora, workspace.backing_corpus_name, snapshot_id
    )
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    require(
        manifest_sha == publication_binding["snapshot_manifest_sha256"],
        "Rich 2 snapshot manifest hash drift",
    )
    manifest = CanonicalSnapshotManifest.model_validate_json(manifest_bytes)
    require(
        compute_snapshot_id(manifest) == snapshot_id,
        "Rich 2 snapshot identity mismatch",
    )
    identity = manifest.model_dump(
        mode="json",
        exclude={
            "corpus_manifest",
            "chunk_manifest",
            "dense_index_manifest",
            "lexical_index_manifest",
        },
    )
    require(
        identity == publication_binding["snapshot_identity"],
        "Rich 2 scientific snapshot identity drift",
    )

    manifest_paths = {
        "corpus": settings.paths.manifests / Path(manifest.corpus_manifest).name,
        "chunk": settings.paths.chunk_manifests / Path(manifest.chunk_manifest).name,
        "dense": settings.paths.index_manifests
        / Path(manifest.dense_index_manifest).name,
        "lexical": settings.paths.lexical_index_manifests
        / Path(manifest.lexical_index_manifest).name,
    }
    for name, path in manifest_paths.items():
        require(path.is_file(), f"Rich 2 {name} manifest is missing")
        require(
            _sha256(path) == artifacts_binding["manifest_sha256"][name],
            f"Rich 2 {name} manifest hash drift",
        )

    dense = load_index_manifest(manifest_paths["dense"])
    expected_count = binding["expected_candidate_count"]
    dense_expected = artifacts_binding["dense"]
    require(
        dense.index_id == identity["dense_index_id"]
        and dense.expected_child_count
        == dense.indexed_child_count
        == dense_expected["expected_child_count"]
        == dense_expected["indexed_child_count"]
        == expected_count
        and dense.collection_name == dense_expected["collection_name"],
        "Rich 2 dense index identity/population mismatch",
    )
    require(
        (settings.paths.qdrant_storage / "collection" / dense.collection_name).is_dir(),
        "Rich 2 dense collection directory is missing",
    )

    from offline_rag.lexical.backend import LocalInvertedIndexBackend
    from offline_rag.lexical.persistence import load_lexical_index_manifest

    lexical = load_lexical_index_manifest(manifest_paths["lexical"])
    lexical_expected = artifacts_binding["lexical"]
    require(
        lexical.lexical_index_id == identity["lexical_index_id"]
        and lexical.expected_child_count
        == lexical.indexed_child_count
        == lexical_expected["expected_child_count"]
        == lexical_expected["indexed_child_count"]
        == lexical_expected["document_count"]
        == expected_count,
        "Rich 2 lexical index identity/population mismatch",
    )
    lexical_backend = LocalInvertedIndexBackend(settings.paths.lexical_indexes)
    require(
        lexical_backend.index_exists(lexical.lexical_index_id)
        and lexical_backend.validate(lexical.lexical_index_id),
        "Rich 2 lexical backing is missing or invalid",
    )
    lexical_dir = settings.paths.lexical_indexes / lexical.lexical_index_id
    lexical_files = {
        path.name: _sha256(path) for path in lexical_dir.iterdir() if path.is_file()
    }
    require(
        lexical_files == lexical_expected["lexical_files_sha256"],
        "Rich 2 lexical backing file hashes drift",
    )

    structures = load_structure_store_for_chunk_manifest(
        settings, Path(manifest.chunk_manifest).name
    )
    terminal = {"succeeded", "failed", "canceled", "cancelled", "interrupted"}
    active_operations = sum(
        json.loads(path.read_bytes()).get("status") not in terminal
        for path in settings.paths.workspaces.glob("*/operations/by_id/*.json")
    )
    require(active_operations == 0, "managed workspace operation is active")

    pointer = ProductPublicationRegistry(settings).published_snapshot_id(
        workspace.backing_corpus_name
    )
    require(
        pointer == snapshot_id == publication_binding["published_pointer"],
        "Rich 2 publication pointer mismatch",
    )
    settings_hash = hashlib.sha256(
        json.dumps(
            {
                key: getattr(settings, key).model_dump(
                    mode="json",
                    exclude={"batching_strategy"} if key == "reranker" else None,
                )
                for key in (
                    "dense",
                    "reranker",
                    "fusion",
                    "context",
                    "lexical",
                    "indexing",
                )
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    require(
        settings_hash == publication_binding["science_settings_sha256"],
        "Rich 2 scientific settings drift",
    )
    effective_config = binding["effective_config"]
    config_path = Path(os.environ.get("OFFLINE_RAG_CONFIG", effective_config["path"]))
    require(
        str(config_path) == effective_config["path"]
        and _sha256(config_path) == effective_config["sha256"],
        "Rich 2 effective configuration identity drift",
    )

    if qdrant is not None:
        resolved = ProductPublicationRegistry(settings, qdrant=qdrant).resolve_snapshot(
            workspace.backing_corpus_name, snapshot_id
        )
        resolved_identity = resolved.identity.model_dump(
            mode="json",
            exclude={
                "corpus_manifest",
                "chunk_manifest",
                "dense_index_manifest",
                "lexical_index_manifest",
            },
        )
        require(
            resolved.snapshot_id == snapshot_id and resolved_identity == identity,
            "Rich 2 physical snapshot backing mismatch",
        )

    return {
        "binding": binding,
        "workspace": workspace,
        "source_scope": scope,
        "document_ids": document_ids,
        "question": question,
        "manifest": manifest,
        "dense_manifest": dense,
        "lexical_manifest": lexical,
        "structures": structures,
        "corpus_name": workspace.backing_corpus_name,
        "settings_hash": settings_hash,
        "workspace_record_sha256": inventory_sha,
        "snapshot_manifest_sha256": manifest_sha,
    }


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_models(settings, workloads):
    from offline_rag.rerank.provision import resolve_reranker_model_dir

    models = workloads["models"]
    bge = resolve_reranker_model_dir(
        reranker_artifacts_root=settings.paths.reranker_artifacts,
        model_path=settings.reranker.model.model_path,
    )
    require(
        settings.reranker.model.revision == models["reranker"]["revision"],
        "BGE revision",
    )
    onnx = Path("/models/embeddings/qwen3-embedding-0.6b/representations/onnx_fp32_v1")
    onnx /= models["embedding"]["representation_dir"]
    for root, expected in (
        (bge, models["reranker"]["sha256"]),
        (onnx, models["embedding"]["local_reference_sha256"]),
    ):
        for name, sha in expected.items():
            require(digest(root / name) == sha, "artifact digest mismatch")


def main():
    mode = sys.argv[1]
    require(
        mode
        in {
            "metadata",
            "isolated",
            "native",
            "native-smoke",
            "native-metadata",
            "rich2-stage1",
            "rich2-metadata",
        },
        "unsupported preflight mode",
    )
    if len(sys.argv) not in {4, 5}:
        raise ValueError(
            "expected mode, workload manifest, bindings, and optional output"
        )
    manifest_path = Path(sys.argv[2])
    bindings_path = Path(sys.argv[3])
    output_bindings = Path(sys.argv[4]) if len(sys.argv) == 5 else None
    require(
        (output_bindings is None and mode not in {"native", "native-smoke"})
        or (output_bindings is not None and mode in {"native", "native-smoke"}),
        "native mode requires its binding output and other modes forbid it",
    )
    manifest = json.loads(manifest_path.read_text())
    native_manifest_path = manifest_path.parent / "NATIVE_SETTINGS_RICH2.json"
    if mode in {"native", "native-smoke", "native-metadata"}:
        from native_contract import (
            load_manifest,
            validate_scientific_settings,
            verify_config_file,
        )

        native_settings = load_manifest(manifest_path.parent)
        verify_config_file(
            native_settings, Path(os.environ.get("OFFLINE_RAG_CONFIG", ""))
        )
    require(
        digest(bindings_path) == manifest["stage1_binding_file_sha256"],
        "binding digest mismatch",
    )
    frozen = json.loads(bindings_path.read_text())
    require(
        set(os.listdir("/sys/class/net")) == {"lo"}, "network isolation unavailable"
    )
    require(
        bool(os.statvfs("/models").f_flag & os.ST_RDONLY), "model mount is writable"
    )
    data_read_only = bool(os.statvfs("/data").f_flag & os.ST_RDONLY)
    data_should_be_read_only = mode in {"metadata", "rich2-metadata", "native-metadata"}
    require(
        data_read_only == data_should_be_read_only,
        "data mount mode mismatch",
    )
    settings = load_settings()
    require(
        settings.api.max_concurrent_query == 1
        and settings.api.query_deadline_seconds == 180
        and settings.api.shutdown_grace_seconds == 30,
        "operation settings drift",
    )
    require(
        settings.reranker.input_k == 30
        and settings.reranker.batch_size == 16
        and settings.reranker.max_length == 1024,
        "scorer settings drift",
    )
    rich2_state = {}

    def validate_rich2():
        from rich2_stage1 import validate_binding_document

        rich2_binding_path = manifest_path.parent / "rich2-stage1-binding.json"
        rich2_binding = json.loads(rich2_binding_path.read_text(encoding="utf-8"))
        validate_binding_document(rich2_binding, digest(bindings_path))
        rich2_state["binding"] = rich2_binding
        return validate_rich2_binding(settings, rich2_binding)

    actual, rich2 = dispatch_preflight_validators(
        mode,
        recipes_validator=lambda: recipes(settings),
        rich_validator=lambda: rich(settings),
        rich2_validator=validate_rich2,
    )
    rich2_binding = rich2_state.get("binding")
    if mode in {"native", "native-smoke", "native-metadata"}:
        rich_workspace = rich2["workspace"]
        rich_publication = rich2_binding["publication"]
        rich_source = rich2_binding["source"]["identity"]
        actual["Rich"] = (
            {
                "workspace_id": rich_workspace.workspace_id,
                "workspace_revision": rich_workspace.revision,
                "snapshot_id": rich_publication["snapshot_id"],
                "document_id": rich_source["document_id"],
                "source_inventory_sha256": rich2["workspace_record_sha256"],
                "snapshot_manifest_sha256": rich2["snapshot_manifest_sha256"],
                "published_pointer": rich_publication["published_pointer"],
                "science_settings_hash": rich2["settings_hash"],
            },
            rich2["corpus_name"],
            None,
        )
    if mode in {"native", "native-smoke", "native-metadata"}:
        validate_scientific_settings(
            {label: binding for label, (binding, _, _) in actual.items()},
            native_settings,
        )
    require(
        all(
            binding == frozen[label]
            for label, (binding, _, _) in actual.items()
            if label != "Rich"
            or mode not in {"native", "native-smoke", "native-metadata"}
        ),
        "binding drift",
    )
    verify_models(settings, manifest)
    if mode in {"native", "native-smoke"}:
        require(
            settings.project.strict_offline is True
            and settings.deployment.qdrant_mode == "local"
            and settings.indexing.embedding.device == "auto"
            and settings.indexing.embedding.precision == "native"
            and settings.indexing.embedding.revision
            == "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
            "native scientific execution configuration mismatch",
        )
    if output_bindings is not None:
        output_bindings.parent.mkdir(parents=True, exist_ok=True)
        resolved = {}
        for label, (binding, _corpus, source_ids) in actual.items():
            spec = manifest["workloads"][label]
            resolved[label] = {
                "workspace_id": binding["workspace_id"],
                "revision": binding["workspace_revision"],
                "snapshot_id": binding["snapshot_id"],
                "document_id": binding["document_id"],
                "source_mode": spec["source_mode"],
                "source_ids": None if source_ids is None else sorted(source_ids),
            }
        native_bindings = {
            "schema": "seneca-stage2-native-bindings-v1",
            "workloads_sha256": digest(manifest_path),
            "stage1_bindings_sha256": digest(bindings_path),
            "native_settings_manifest_sha256": digest(native_manifest_path),
            "workloads": resolved,
        }
        output_bindings.write_text(
            json.dumps(native_bindings, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        # Contains only workspace/snapshot/source identifiers, no content or
        # credentials; host driver and same-UID app container must both read it.
        os.chmod(output_bindings, 0o644)
    if mode in {"isolated", "native", "native-smoke", "rich2-stage1"}:
        import torch

        from offline_rag.app.runtime import default_resource_factories
        from offline_rag.dense.st_onnx_runtime import (
            FROZEN_ORT_INTER_OP_THREADS,
            FROZEN_ORT_INTRA_OP_THREADS,
        )

        require(
            os.environ.get("SENECA_ISOLATED_COPY") == "verified",
            "isolated host gate required",
        )
        require(
            len(os.sched_getaffinity(0)) == 4 and torch.version.cuda is None,
            "CPU policy drift",
        )
        require(
            (FROZEN_ORT_INTRA_OP_THREADS, FROZEN_ORT_INTER_OP_THREADS) == (8, 1),
            "ORT policy drift",
        )
        torch.set_num_threads(2)
        torch.set_num_interop_threads(2)
        require(
            (torch.get_num_threads(), torch.get_num_interop_threads()) == (2, 2),
            "Torch policy drift",
        )
        backend = default_resource_factories().qdrant(settings)
        try:
            registry = ProductPublicationRegistry(settings, qdrant=backend)
            for binding, corpus, _ in actual.values():
                require(
                    registry.resolve_snapshot(
                        corpus, binding["snapshot_id"]
                    ).snapshot_id
                    == binding["snapshot_id"],
                    "backing resolution mismatch",
                )
            if rich2 is not None:
                rich2_snapshot = registry.resolve_snapshot(
                    rich2["corpus_name"],
                    rich2_binding["publication"]["snapshot_id"],
                )
                require(
                    rich2_snapshot.snapshot_id
                    == rich2_binding["publication"]["snapshot_id"],
                    "Rich 2 backing resolution mismatch",
                )
        finally:
            backend.close()
    output = {
        "mode": mode,
        "strategies": settings.reranker.batching_strategy,
        "bindings": {
            label: {
                "workspace_id": b["workspace_id"],
                "workspace_revision": b["workspace_revision"],
                "snapshot_id": b["snapshot_id"],
                "document_id": b["document_id"],
                "source_mode": manifest["workloads"][label]["source_mode"],
                "source_ids": ids,
                "source_inventory_sha256": b["source_inventory_sha256"],
                "snapshot_manifest_sha256": b["snapshot_manifest_sha256"],
                "published_pointer": b["published_pointer"],
            }
            for label, (b, _, ids) in actual.items()
        },
        "scientific_settings": {
            label: b["science_settings_hash"] for label, (b, _, _) in actual.items()
        },
    }
    if rich2 is not None:
        output["Rich2"] = {
            "workspace_id": rich2["workspace"].workspace_id,
            "workspace_revision": rich2["workspace"].revision,
            "source_inventory_sha256": rich2["workspace_record_sha256"],
            "source_ids": sorted(rich2["source_scope"].source_ids),
            "document_ids": sorted(rich2["document_ids"]),
            "snapshot_id": rich2_binding["publication"]["snapshot_id"],
            "snapshot_manifest_sha256": rich2["snapshot_manifest_sha256"],
            "published_pointer": rich2_binding["publication"]["published_pointer"],
            "scientific_settings_sha256": rich2["settings_hash"],
        }
        if mode in {"rich2-stage1", "rich2-metadata"}:
            output["historical_Rich"] = {
                "status": "preserved_historical_binding_not_live_resolved",
                **rich2_binding["historical_rich_binding"],
            }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
