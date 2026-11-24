"""Deterministic tests for the prepared Rich 2 Stage 1 path."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field

DRIVER_DIR = Path(__file__).parent
sys.path.insert(0, str(DRIVER_DIR))

import docker_watchdog
import native_host_control
from rich2_stage1 import (
    Rich2Stage1Error,
    _claim_single_use,
    _require_single_use_paths_available,
    resolve_stage2_inputs,
    validate_binding_document,
    validate_observation,
)

INPUTS = DRIVER_DIR.parent / "stage2-integration"
BINDING_PATH = INPUTS / "rich2-stage1-binding.json"
HISTORICAL_PATH = INPUTS / "stage1-bindings.json"


def load_binding() -> tuple[dict, str]:
    binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
    historical_sha = hashlib.sha256(HISTORICAL_PATH.read_bytes()).hexdigest()
    return binding, historical_sha


def load_preflight_with_deterministic_dependencies(monkeypatch):
    """Load preflight without importing the app's provider/model modules."""
    package_names = (
        "offline_rag.app",
        "offline_rag.app.workspace",
        "offline_rag.config",
        "offline_rag.context",
        "offline_rag.dense",
        "offline_rag.lexical",
    )
    for name in package_names:
        package = types.ModuleType(name)
        package.__path__ = []
        monkeypatch.setitem(sys.modules, name, package)

    stubs = {
        "offline_rag.app.publication": {
            "ProductPublicationRegistry": object,
            "snapshot_manifest_path": lambda *_args: None,
        },
        "offline_rag.app.query": {
            "_resolve_workspace_source_scope": None,
            "normalize_product_question": lambda value: value,
        },
        "offline_rag.app.snapshot": {
            "CanonicalSnapshotManifest": object,
            "compute_snapshot_id": lambda _manifest: "",
        },
        "offline_rag.app.workspace.store": {"WorkspaceStore": object},
        "offline_rag.app.workspace.vault": {"RawSourceVault": object},
        "offline_rag.config.loader": {"load_settings": lambda: None},
        "offline_rag.context.store": {
            "load_structure_store_for_chunk_manifest": lambda *_args: None
        },
        "offline_rag.dense.persistence": {"load_index_manifest": lambda _path: None},
        "offline_rag.lexical.backend": {"LocalInvertedIndexBackend": object},
        "offline_rag.lexical.persistence": {
            "load_lexical_index_manifest": lambda _path: None
        },
    }
    for name, attributes in stubs.items():
        module_stub = types.ModuleType(name)
        for key, value in attributes.items():
            setattr(module_stub, key, value)
        monkeypatch.setitem(sys.modules, name, module_stub)

    path = DRIVER_DIR / "preflight.py"
    spec = importlib.util.spec_from_file_location("rich2_preflight_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_observation() -> dict:
    candidate_ids = [f"chunk-{index:02d}" for index in range(10)]
    logits = [float(10 - index) for index in range(10)]
    return {
        "candidate_ids": candidate_ids,
        "candidate_document_ids": ["rich2-doc"] * 10,
        "expected_document_id": "rich2-doc",
        "score_pairs": [
            {
                "candidate_id": candidate_id,
                "pair_input_sha256": hashlib.sha256(
                    f"pair-{index}".encode()
                ).hexdigest(),
                "raw_logit": logits[index],
            }
            for index, candidate_id in enumerate(candidate_ids)
        ],
        "ranked_ids": list(candidate_ids),
        "anchor_ids": list(candidate_ids),
        "evidence_unit_ids": ["evidence-unit-1"],
        "expected_candidate_ids": set(candidate_ids),
    }


def test_rich2_binding_is_distinct_and_historical_binding_is_unchanged():
    binding, historical_sha = load_binding()
    validate_binding_document(binding, historical_sha)
    assert (
        binding["workspace"]["workspace_id"]
        != binding["historical_rich_binding"]["workspace_id"]
    )
    assert binding["workspace"]["revision"] == 2
    assert binding["historical_rich_binding"]["preserved_sha256"] == historical_sha


def test_one_shot_uses_the_actual_read_only_container_input_mount():
    inputs = resolve_stage2_inputs(Path("/review/driver"))
    preflight_source = (DRIVER_DIR / "preflight_host.sh").read_text()
    runbook = (
        DRIVER_DIR.parent / "stage2-integration" / "RICH2_STAGE2_AMENDMENT_PROPOSAL.md"
    ).read_text()

    assert resolve_stage2_inputs(DRIVER_DIR) == INPUTS
    assert inputs == Path("/review/inputs")
    assert "dst=/review/driver,readonly" in preflight_source
    assert "dst=/review/inputs,readonly" in preflight_source
    assert "src=$INPUTS,dst=/review/inputs,readonly" in runbook
    assert inputs / "rich2-stage1-binding.json" == Path(
        "/review/inputs/rich2-stage1-binding.json"
    )
    assert inputs / "stage1-bindings.json" == Path(
        "/review/inputs/stage1-bindings.json"
    )
    assert inputs / "workloads.json" == Path("/review/inputs/workloads.json")
    assert inputs / "provider_fixture.py" == Path("/review/inputs/provider_fixture.py")
    assert inputs / "NATIVE_SETTINGS_MANIFEST.json" == Path(
        "/review/inputs/NATIVE_SETTINGS_MANIFEST.json"
    )


def test_committed_binding_passes_complete_deterministic_preflight(
    tmp_path, monkeypatch
):
    trace_path = DRIVER_DIR.parents[3] / "src/offline_rag/app/traces.py"
    trace_module = ast.parse(trace_path.read_text(encoding="utf-8"))
    scope_class = next(
        node
        for node in trace_module.body
        if isinstance(node, ast.ClassDef) and node.name == "ProductTraceSourceScope"
    )
    namespace = {
        "BaseModel": BaseModel,
        "ConfigDict": ConfigDict,
        "Field": Field,
        "Literal": Literal,
    }
    exec(  # noqa: S102 - load the repository schema without provider imports
        compile(
            ast.Module(body=[scope_class], type_ignores=[]), str(trace_path), "exec"
        ),
        namespace,
    )
    ProductTraceSourceScope = namespace["ProductTraceSourceScope"]
    ProductTraceSourceScope.model_rebuild(_types_namespace=namespace)

    binding, historical_sha = load_binding()
    validate_binding_document(binding, historical_sha)
    preflight = load_preflight_with_deterministic_dependencies(monkeypatch)
    publication = binding["publication"]
    artifact_binding = binding["artifacts"]
    workspace_binding = binding["workspace"]
    source_identity = binding["source"]["identity"]
    snapshot_identity = publication["snapshot_identity"]

    roots = {
        name: tmp_path / name
        for name in (
            "workspaces",
            "corpora",
            "manifests",
            "chunk_manifests",
            "index_manifests",
            "lexical_index_manifests",
            "qdrant",
            "lexical_indexes",
            "chunks",
        )
    }
    for root in roots.values():
        root.mkdir()
    settings = types.SimpleNamespace(
        paths=types.SimpleNamespace(
            workspaces=roots["workspaces"],
            corpora=roots["corpora"],
            manifests=roots["manifests"],
            chunk_manifests=roots["chunk_manifests"],
            index_manifests=roots["index_manifests"],
            lexical_index_manifests=roots["lexical_index_manifests"],
            qdrant_storage=roots["qdrant"],
            lexical_indexes=roots["lexical_indexes"],
            chunks=roots["chunks"],
        ),
        **{
            name: types.SimpleNamespace(model_dump=lambda **_kwargs: {})
            for name in (
                "dense",
                "reranker",
                "fusion",
                "context",
                "lexical",
                "indexing",
            )
        },
    )

    source = types.SimpleNamespace(
        **source_identity,
        vault_object_id="vault-object-fixture",
    )
    workspace = types.SimpleNamespace(
        status="active",
        revision=workspace_binding["revision"],
        current_snapshot_id=publication["snapshot_id"],
        backing_corpus_name=workspace_binding["backing_corpus_name"],
        sources=[source],
    )

    class FakeWorkspaceStore:
        def __init__(self, _settings):
            pass

        def get(self, _workspace_id):
            return workspace

        def workspace_path(self, _workspace_id):
            return types.SimpleNamespace(read_bytes=lambda: b"workspace fixture")

    class FakeVault:
        def __init__(self, _root):
            pass

        def verify_object(self, _workspace_id, _object_id):
            return types.SimpleNamespace(
                content_hash=binding["source"]["content_sha256"],
                byte_size=binding["source"]["byte_size"],
            )

    class FakeManifest:
        corpus_manifest = "corpus-fixture.json"
        chunk_manifest = "chunk-fixture.json"
        dense_index_manifest = "dense-fixture.json"
        lexical_index_manifest = "lexical-fixture.json"

        @classmethod
        def model_validate_json(cls, _data):
            return cls()

        def model_dump(self, **_kwargs):
            return snapshot_identity

    class FakeDenseBackend:
        def __init__(self, _root):
            pass

        def index_exists(self, _index_id):
            return True

        def validate(self, _index_id):
            return True

    monkeypatch.setattr(preflight, "WorkspaceStore", FakeWorkspaceStore)
    monkeypatch.setattr(preflight, "RawSourceVault", FakeVault)
    monkeypatch.setattr(preflight, "CanonicalSnapshotManifest", FakeManifest)
    monkeypatch.setattr(
        preflight,
        "_resolve_workspace_source_scope",
        lambda _workspace, source_ids: (
            ProductTraceSourceScope(
                workspace_id=workspace_binding["workspace_id"],
                workspace_revision=workspace_binding["revision"],
                **binding["source_scope"],
            ),
            None,
            frozenset(binding["source_scope"]["document_ids"]),
        ),
    )
    monkeypatch.setattr(
        preflight,
        "compute_snapshot_id",
        lambda _manifest: publication["snapshot_id"],
    )
    snapshot_file = roots["corpora"] / "snapshot.json"
    snapshot_file.write_bytes(b"snapshot fixture")
    monkeypatch.setattr(
        preflight,
        "snapshot_manifest_path",
        lambda *_args: snapshot_file,
    )

    manifest_paths = {
        "corpus": roots["manifests"] / FakeManifest.corpus_manifest,
        "chunk": roots["chunk_manifests"] / FakeManifest.chunk_manifest,
        "dense": roots["index_manifests"] / FakeManifest.dense_index_manifest,
        "lexical": roots["lexical_index_manifests"]
        / FakeManifest.lexical_index_manifest,
    }
    for path in manifest_paths.values():
        path.write_bytes(b"manifest fixture")
    expected_dense = artifact_binding["dense"]
    expected_lexical = artifact_binding["lexical"]
    monkeypatch.setattr(
        preflight,
        "load_index_manifest",
        lambda _path: types.SimpleNamespace(
            index_id=snapshot_identity["dense_index_id"],
            expected_child_count=10,
            indexed_child_count=10,
            collection_name=expected_dense["collection_name"],
        ),
    )
    lexical_backend_module = sys.modules["offline_rag.lexical.backend"]
    monkeypatch.setattr(
        lexical_backend_module,
        "LocalInvertedIndexBackend",
        FakeDenseBackend,
    )
    lexical_persistence = sys.modules["offline_rag.lexical.persistence"]
    monkeypatch.setattr(
        lexical_persistence,
        "load_lexical_index_manifest",
        lambda _path: types.SimpleNamespace(
            lexical_index_id=snapshot_identity["lexical_index_id"],
            expected_child_count=10,
            indexed_child_count=10,
            document_count=10,
        ),
    )
    lexical_dir = roots["lexical_indexes"] / snapshot_identity["lexical_index_id"]
    lexical_dir.mkdir()
    for filename in expected_lexical["lexical_files_sha256"]:
        (lexical_dir / filename).write_bytes(b"lexical fixture")
    dense_collection = (
        roots["qdrant"] / "collection" / expected_dense["collection_name"]
    )
    dense_collection.mkdir(parents=True)
    structures = object()
    monkeypatch.setattr(
        sys.modules["offline_rag.context.store"],
        "load_structure_store_for_chunk_manifest",
        lambda *_args: structures,
    )
    monkeypatch.setattr(
        preflight,
        "load_structure_store_for_chunk_manifest",
        lambda *_args: structures,
    )

    class FakeRegistry:
        def __init__(self, _settings, **_kwargs):
            pass

        def published_snapshot_id(self, _corpus):
            return publication["snapshot_id"]

    monkeypatch.setattr(
        sys.modules["offline_rag.app.publication"],
        "ProductPublicationRegistry",
        FakeRegistry,
    )
    monkeypatch.setattr(preflight, "ProductPublicationRegistry", FakeRegistry)

    expected_settings_hash_payload = json.dumps(
        {
            name: {}
            for name in (
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
    real_sha256 = hashlib.sha256

    class FakeDigest:
        def __init__(self, value):
            self.value = value

        def hexdigest(self):
            return self.value

    def deterministic_sha256(value=b""):
        if value == b"workspace fixture":
            return FakeDigest(workspace_binding["workspace_record_sha256"])
        if value == b"snapshot fixture":
            return FakeDigest(publication["snapshot_manifest_sha256"])
        if value == expected_settings_hash_payload:
            return FakeDigest(publication["science_settings_sha256"])
        return real_sha256(value)

    monkeypatch.setattr(preflight.hashlib, "sha256", deterministic_sha256)
    expected_by_name = {
        path.name: artifact_binding["manifest_sha256"][name]
        for name, path in manifest_paths.items()
    }
    expected_by_name.update(expected_lexical["lexical_files_sha256"])

    def deterministic_file_hash(path):
        if path == snapshot_file:
            return publication["snapshot_manifest_sha256"]
        if path == Path("/app/config/base.yaml"):
            return binding["effective_config"]["sha256"]
        return expected_by_name[path.name]

    monkeypatch.setattr(preflight, "_sha256", deterministic_file_hash)
    monkeypatch.setenv("OFFLINE_RAG_CONFIG", "/app/config/base.yaml")
    monkeypatch.setattr(
        sys.modules["offline_rag.lexical.backend"],
        "LocalInvertedIndexBackend",
        FakeDenseBackend,
    )

    actual_bindings, validated = preflight.dispatch_preflight_validators(
        "rich2-stage1",
        recipes_validator=lambda: "recipes binding fixture",
        rich_validator=lambda: pytest.fail(
            "Rich 2 preflight attempted live historical Rich validation"
        ),
        rich2_validator=lambda: preflight.validate_rich2_binding(settings, binding),
    )

    assert actual_bindings == {"Recipes": "recipes binding fixture"}
    assert validated["corpus_name"] == workspace_binding["backing_corpus_name"]
    assert validated["workspace"] is workspace
    assert validated["structures"] is structures
    assert validated["document_ids"] == frozenset(
        binding["source_scope"]["document_ids"]
    )

    workspace.backing_corpus_name = "unexpected-corpus"
    with pytest.raises(ValueError, match="corpus binding drift"):
        preflight.validate_rich2_binding(settings, binding)
    workspace.backing_corpus_name = workspace_binding["backing_corpus_name"]

    dense_collection.rmdir()
    with pytest.raises(ValueError, match="dense collection directory is missing"):
        preflight.validate_rich2_binding(settings, binding)


@pytest.mark.parametrize("mode", ["metadata", "isolated"])
def test_original_preflight_modes_do_not_require_rich2(mode, monkeypatch):
    calls = []
    preflight = load_preflight_with_deterministic_dependencies(monkeypatch)
    actual, rich2 = preflight.dispatch_preflight_validators(
        mode,
        recipes_validator=lambda: calls.append("Recipes") or "recipes",
        rich_validator=lambda: calls.append("Rich") or "rich",
        rich2_validator=lambda: pytest.fail("original mode dispatched Rich 2"),
    )

    assert actual == {"Recipes": "recipes", "Rich": "rich"}
    assert calls == ["Recipes", "Rich"]
    assert rich2 is None


@pytest.mark.parametrize(
    "mode",
    [
        "rich2-metadata",
        "rich2-stage1",
        "native",
        "native-smoke",
        "native-metadata",
    ],
)
def test_rich2_preflight_modes_use_recipes_and_rich2_not_live_historical_rich(
    mode, monkeypatch
):
    calls = []
    preflight = load_preflight_with_deterministic_dependencies(monkeypatch)
    actual, rich2 = preflight.dispatch_preflight_validators(
        mode,
        recipes_validator=lambda: calls.append("Recipes") or "recipes",
        rich_validator=lambda: pytest.fail("Rich 2 mode dispatched historical Rich"),
        rich2_validator=lambda: calls.append("Rich2") or "rich2",
    )

    assert actual == {"Recipes": "recipes"}
    assert calls == ["Recipes", "Rich2"]
    assert rich2 == "rich2"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("workspace", "workspace_id"), "ws_wrong"),
        (("workspace", "revision"), 3),
        (("workspace", "source_inventory_sha256"), "0" * 64),
        (("source", "identity", "source_id"), "src_wrong"),
        (("source", "identity", "content_hash"), "0" * 64),
        (("publication", "published_pointer"), "snap_wrong"),
        (("publication", "science_settings_sha256"), "0" * 64),
        (("publication", "snapshot_manifest_sha256"), "0" * 64),
        (("question", "normalized_sha256"), "0" * 64),
        (("source_scope", "mode"), "selected"),
        (("expected_candidate_count",), 9),
        (("effective_config", "sha256"), "0" * 64),
        (("artifacts", "dense", "indexed_child_count"), 9),
        (("artifacts", "lexical", "lexical_files_sha256", "postings.json"), "0" * 64),
        (("status",), "execution_authorized"),
    ],
)
def test_rich2_binding_identity_drift_fails_closed(path, value):
    binding, historical_sha = load_binding()
    changed = copy.deepcopy(binding)
    target = changed
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(Rich2Stage1Error):
        validate_binding_document(changed, historical_sha)


def test_wrong_historical_binding_digest_fails_closed():
    binding, _historical_sha = load_binding()
    with pytest.raises(Rich2Stage1Error, match="historical Rich binding provenance"):
        validate_binding_document(binding, "0" * 64)


def test_candidate_score_ranking_and_scope_are_validated_together():
    observation = valid_observation()
    validate_observation(**observation)


def test_ranking_uses_chunk_id_ascending_for_equal_raw_logits():
    observation = valid_observation()
    observation["candidate_ids"] = ["chunk-z", "chunk-a"] + [
        f"chunk-{index:02d}" for index in range(8)
    ]
    observation["expected_candidate_ids"] = set(observation["candidate_ids"])
    observation["score_pairs"] = [
        {
            "candidate_id": candidate_id,
            "pair_input_sha256": hashlib.sha256(f"pair-{index}".encode()).hexdigest(),
            "raw_logit": 1.0 if index < 2 else 0.0,
        }
        for index, candidate_id in enumerate(observation["candidate_ids"])
    ]
    observation["ranked_ids"] = [
        "chunk-a",
        "chunk-z",
        *observation["candidate_ids"][2:],
    ]
    observation["anchor_ids"] = list(observation["ranked_ids"])

    validate_observation(**observation)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("candidate_count", "fused candidate population"),
        ("candidate_duplicate", "fused candidate population"),
        ("unexpected_candidate", "frozen chunk inventory"),
        ("scope_escape", "candidate escaped"),
        ("score_order", "candidate-score association"),
        ("missing_score", "candidate-score association"),
        ("nonfinite_score", "non-finite"),
        ("malformed_pair_hash", "incomplete or non-finite"),
        ("rank_order", "raw-logit/chunk-ID ordering"),
        ("missing_anchor", "anchor identity instrumentation"),
        ("missing_evidence", "evidence-unit identity instrumentation"),
    ],
)
def test_incomplete_or_unexpected_observation_fails_closed(change, message):
    observation = valid_observation()
    if change == "candidate_count":
        observation["candidate_ids"].pop()
    elif change == "candidate_duplicate":
        observation["candidate_ids"][-1] = observation["candidate_ids"][0]
    elif change == "unexpected_candidate":
        observation["candidate_ids"][-1] = "chunk-outside-snapshot"
        observation["score_pairs"][-1]["candidate_id"] = "chunk-outside-snapshot"
        observation["ranked_ids"][-1] = "chunk-outside-snapshot"
        observation["anchor_ids"][-1] = "chunk-outside-snapshot"
    elif change == "scope_escape":
        observation["candidate_document_ids"][-1] = "other-document"
    elif change == "score_order":
        observation["score_pairs"][0], observation["score_pairs"][1] = (
            observation["score_pairs"][1],
            observation["score_pairs"][0],
        )
    elif change == "missing_score":
        observation["score_pairs"].pop()
    elif change == "nonfinite_score":
        observation["score_pairs"][0]["raw_logit"] = float("nan")
    elif change == "malformed_pair_hash":
        observation["score_pairs"][0]["pair_input_sha256"] = "not-a-hash"
    elif change == "rank_order":
        observation["ranked_ids"][0], observation["ranked_ids"][1] = (
            observation["ranked_ids"][1],
            observation["ranked_ids"][0],
        )
    elif change == "missing_anchor":
        observation["anchor_ids"] = []
    elif change == "missing_evidence":
        observation["evidence_unit_ids"] = []

    with pytest.raises(Rich2Stage1Error, match=message):
        validate_observation(**observation)


def test_single_use_claim_cannot_be_reused(tmp_path):
    claim = tmp_path / "rich2.claimed"
    _claim_single_use(claim, "binding-digest")
    with pytest.raises(FileExistsError):
        _claim_single_use(claim, "binding-digest")
    assert json.loads(claim.read_text())["binding_sha256"] == "binding-digest"


@pytest.mark.parametrize("existing_path", ["claim", "output"])
def test_existing_single_use_artifact_rejected_before_model_work(
    tmp_path, existing_path
):
    claim = tmp_path / "rich2.claimed"
    output = tmp_path / "rich2.json"
    (claim if existing_path == "claim" else output).write_text("occupied")

    with pytest.raises(Rich2Stage1Error, match="already exists"):
        _require_single_use_paths_available(claim, output)


def test_rich2_restoration_layout_checks_its_only_qdrant_copy(tmp_path, monkeypatch):
    qdrant = tmp_path / "data" / "qdrant"
    qdrant.mkdir(parents=True)
    observed = []
    monkeypatch.setattr(
        native_host_control,
        "assert_qdrant_unowned",
        lambda path: observed.append(path),
    )

    native_host_control.verify_scratch_unowned(
        tmp_path, layout="rich2-stage1", allow_missing_qdrant=True
    )

    assert observed == [qdrant]


def test_aborted_restore_without_scratch_data_still_verifies_original_first(
    tmp_path, monkeypatch
):
    snapshot = tmp_path / "baseline.json"
    metadata = tmp_path / "metadata.json"
    scratch = tmp_path / "session"
    scratch.mkdir()
    abort = tmp_path / "abort"
    abort.touch()
    baseline = {
        "id": "original-id",
        "image_id": "image-id",
        "image_ref": "seneca-review:9c92e706c4b9",
        "restart_policy": {"Name": "unless-stopped"},
        "network_mode": "bridge",
        "mounts": [{"destination": "/data", "source": "/srv/seneca/data"}],
        "running": True,
    }
    metadata_baseline = {"publication": "unchanged"}
    snapshot.write_text(json.dumps(baseline), encoding="utf-8")
    metadata.write_text(json.dumps(metadata_baseline), encoding="utf-8")
    events = []
    monkeypatch.setattr(
        native_host_control,
        "inspect_named",
        lambda _name: {
            "id": "original-id",
            "image_id": "image-id",
            "image_ref": "seneca-review:9c92e706c4b9",
            "restart_policy": {"Name": "unless-stopped"},
            "network_mode": "bridge",
            "mounts": [{"destination": "/data", "source": "/srv/seneca/data"}],
            "running": True,
        },
    )
    monkeypatch.setattr(
        native_host_control,
        "health",
        lambda container_id: events.append(("health", container_id)),
    )

    def run_preflight(*_args, **_kwargs):
        events.append(("publication",))
        return types.SimpleNamespace(stdout=json.dumps(metadata_baseline))

    monkeypatch.setattr(native_host_control.subprocess, "run", run_preflight)
    original_verify = native_host_control.verify

    def observe_verify(*args, **kwargs):
        events.append(("original", kwargs["start_if_stopped"]))
        return original_verify(*args, **kwargs)

    monkeypatch.setattr(native_host_control, "verify", observe_verify)
    monkeypatch.setattr(
        native_host_control,
        "docker",
        lambda *args: events.append(("docker", args)) or "",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "native_host_control.py",
            "verify",
            str(snapshot),
            "--scratch",
            str(scratch),
            "--abort",
            str(abort),
            "--metadata-baseline",
            str(metadata),
            "--metadata-mode",
            "rich2-metadata",
            "--cpuset",
            "0-3",
            "--scratch-layout",
            "rich2-stage1",
        ],
    )

    native_host_control.main()

    assert not (scratch / "data" / "qdrant").exists()
    assert events[0] == ("original", False)
    assert events[1] == ("health", "original-id")
    assert events[2] == ("publication",)
    assert events[3][0] == "docker"  # scratch-container ownership scan


def test_restoration_health_checks_both_endpoints(monkeypatch):
    calls = []
    monkeypatch.setattr(
        native_host_control,
        "docker",
        lambda *args, **kwargs: calls.append(args) or "",
    )

    native_host_control.health("original-id")

    assert len(calls) == 2
    assert calls[0][-1] == "health/live"
    assert calls[1][-1] == "health/ready"


def test_restoration_health_retries_startup(monkeypatch):
    import subprocess

    attempts = []

    def probe(*args, **_kwargs):
        attempts.append(args[-1])
        if len(attempts) == 1:
            raise subprocess.CalledProcessError(1, args)
        return ""

    monkeypatch.setattr(native_host_control, "docker", probe)
    monkeypatch.setattr(native_host_control.time, "sleep", lambda _seconds: None)
    native_host_control.health("original-id", timeout=10)
    assert attempts == ["health/live", "health/live", "health/ready"]


def test_restoration_health_fails_after_deadline(monkeypatch):
    import subprocess

    def unavailable(*args, **_kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(native_host_control, "docker", unavailable)
    with pytest.raises(subprocess.CalledProcessError):
        native_host_control.health("original-id", timeout=0)


def test_stage2_completion_record_accepted_and_fail_closed(tmp_path):
    done = tmp_path / "done"
    done.write_text(
        json.dumps(
            {"session": "0123456789abcdef", "exit_code": 0, "ended_at_unix": 1.0}
        )
    )
    native_host_control.validate_completion_record(
        done, session="0123456789abcdef", layout="stage2"
    )
    with pytest.raises(RuntimeError, match="completion record is invalid"):
        native_host_control.validate_completion_record(
            done, session="fedcba9876543210", layout="stage2"
        )


def test_qdrant_ownership_uses_privileged_lsof(tmp_path, monkeypatch):
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return types.SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(native_host_control.subprocess, "run", run)
    native_host_control.assert_qdrant_unowned(tmp_path)
    assert commands == [["sudo", "-n", "lsof", "+D", str(tmp_path)]]


def test_completed_rich2_session_requires_qdrant_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(native_host_control, "docker", lambda *_args: "")

    with pytest.raises(RuntimeError, match="Qdrant storage is missing"):
        native_host_control.verify_scratch_unowned(
            tmp_path, layout="rich2-stage1", allow_missing_qdrant=False
        )


def test_aborted_stage2_accepts_missing_scratch_but_completed_does_not(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(native_host_control, "docker", lambda *_args: "")
    native_host_control.verify_scratch_unowned(
        tmp_path, layout="stage2", allow_missing_qdrant=True
    )
    with pytest.raises(RuntimeError, match="Qdrant storage is missing"):
        native_host_control.verify_scratch_unowned(tmp_path, layout="stage2")


def test_aborted_session_still_rejects_surviving_scratch_container(
    tmp_path, monkeypatch
):
    container = {"Mounts": [{"Source": str(tmp_path / "data"), "Destination": "/data"}]}
    monkeypatch.setattr(
        native_host_control,
        "docker",
        lambda *args: (
            "container-id" if args == ("ps", "-aq") else json.dumps([container])
        ),
    )

    with pytest.raises(RuntimeError, match="still mounts native scratch"):
        native_host_control.verify_scratch_unowned(
            tmp_path, layout="rich2-stage1", allow_missing_qdrant=True
        )


def test_rich2_qdrant_owner_is_rejected_even_for_aborted_session(tmp_path, monkeypatch):
    qdrant = tmp_path / "data" / "qdrant"
    qdrant.mkdir(parents=True)
    monkeypatch.setattr(native_host_control, "docker", lambda *_args: "")
    monkeypatch.setattr(
        native_host_control.subprocess,
        "run",
        lambda *_args, **_kwargs: types.SimpleNamespace(
            returncode=0,
            stdout="COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\nseneca 42 user 3r DIR 8,1 0 1 /qdrant\n",
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="already holds isolated Qdrant"):
        native_host_control.verify_scratch_unowned(
            tmp_path, layout="rich2-stage1", allow_missing_qdrant=True
        )


def test_rich2_completion_record_is_session_bound_and_fail_closed(tmp_path):
    done = tmp_path / "done.json"
    result = tmp_path / "rich2-stage1.json"
    observation = valid_completion_observation()
    result.write_text(json.dumps(observation), encoding="utf-8")
    native_host_control.write_completion_record(
        done=done,
        session="0123456789abcdef",
        exit_code=0,
        diagnostic_result=result,
    )
    record = json.loads(done.read_text(encoding="utf-8"))
    assert record["schema"] == "seneca-rich2-stage1-completion-v1"
    assert record["session"] == "0123456789abcdef"
    native_host_control.validate_completion_record(done, session="0123456789abcdef")

    with pytest.raises(RuntimeError, match="completion record is invalid"):
        native_host_control.validate_completion_record(done, session="fedcba9876543210")
    with pytest.raises(ValueError, match="only a successful diagnostic"):
        native_host_control.write_completion_record(
            done=tmp_path / "failed.json",
            session="0123456789abcdef",
            exit_code=1,
            diagnostic_result=result,
        )


def valid_completion_observation() -> dict:
    binding_bytes = BINDING_PATH.read_bytes()
    binding = json.loads(binding_bytes)
    candidate_ids = [f"chunk-{index:02d}" for index in range(10)]
    score_associations = [
        {
            "candidate_id": candidate_id,
            "candidate_id_sha256": hashlib.sha256(candidate_id.encode()).hexdigest(),
            "pair_input_sha256": hashlib.sha256(f"pair-{index}".encode()).hexdigest(),
            "raw_logit": float(10 - index),
        }
        for index, candidate_id in enumerate(candidate_ids)
    ]
    anchors = candidate_ids[:3]
    evidence_ids = ["evidence-unit-1"]
    return {
        "schema": "seneca-rich2-stage1-observation-v1",
        "status": "executed_single_assembler_call",
        "binding_sha256": hashlib.sha256(binding_bytes).hexdigest(),
        "workspace_id": binding["workspace"]["workspace_id"],
        "workspace_revision": binding["workspace"]["revision"],
        "source_inventory_sha256": binding["workspace"]["source_inventory_sha256"],
        "source_ids": binding["source_scope"]["source_ids"],
        "document_ids": binding["source_scope"]["document_ids"],
        "snapshot_id": binding["publication"]["snapshot_id"],
        "snapshot_manifest_sha256": binding["publication"]["snapshot_manifest_sha256"],
        "scientific_settings_sha256": binding["publication"]["science_settings_sha256"],
        "question_sha256": binding["question"]["normalized_sha256"],
        "source_scope": "all_active",
        "generation_invoked": False,
        "external_network": False,
        "fused_candidate_count": 10,
        "fused_candidate_ids": candidate_ids,
        "candidate_document_ids": binding["source_scope"]["document_ids"] * 10,
        "fused_candidate_ids_sha256": hashlib.sha256(
            json.dumps(candidate_ids, separators=(",", ":")).encode()
        ).hexdigest(),
        "candidate_score_associations": score_associations,
        "ranked_candidate_ids": candidate_ids,
        "ranking_tie_break": "chunk-id-asc-v1",
        "anchor_ids": anchors,
        "anchor_ids_sha256": hashlib.sha256(
            json.dumps(anchors, separators=(",", ":")).encode()
        ).hexdigest(),
        "evidence_unit_ids": evidence_ids,
        "evidence_unit_ids_sha256": hashlib.sha256(
            json.dumps(evidence_ids, separators=(",", ":")).encode()
        ).hexdigest(),
        "evidence_unit_count": len(evidence_ids),
        "context_token_count": 123,
        "packed_context_sha256": "a" * 64,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "four_fields_only",
        "missing_candidate",
        "missing_score",
        "wrong_association",
        "wrong_document",
        "wrong_rank",
        "missing_context",
        "wrong_binding",
    ],
)
def test_incomplete_or_inconsistent_observation_cannot_complete(tmp_path, mutation):
    observation = valid_completion_observation()
    if mutation == "four_fields_only":
        observation = {
            key: observation[key]
            for key in (
                "schema",
                "status",
                "generation_invoked",
                "external_network",
            )
        }
    elif mutation == "missing_candidate":
        observation["fused_candidate_ids"].pop()
    elif mutation == "missing_score":
        observation["candidate_score_associations"].pop()
    elif mutation == "wrong_association":
        observation["candidate_score_associations"].reverse()
    elif mutation == "wrong_document":
        observation["candidate_document_ids"][0] = "out-of-scope-document"
    elif mutation == "wrong_rank":
        observation["ranked_candidate_ids"] = list(
            reversed(observation["ranked_candidate_ids"])
        )
    elif mutation == "missing_context":
        observation["packed_context_sha256"] = ""
    else:
        observation["binding_sha256"] = "0" * 64
    result = tmp_path / "observation.json"
    result.write_text(json.dumps(observation), encoding="utf-8")

    with pytest.raises(RuntimeError):
        native_host_control.write_completion_record(
            done=tmp_path / "done.json",
            session="0123456789abcdef",
            exit_code=0,
            diagnostic_result=result,
        )


def test_supervise_requires_session_owned_diagnostic_name(tmp_path, monkeypatch):
    root = tmp_path / "session"
    root.mkdir()
    snapshot = root / "baseline.json"
    metadata = root / "metadata.json"
    snapshot.write_text("{}", encoding="utf-8")
    metadata.write_text("{}", encoding="utf-8")
    called = []
    monkeypatch.setattr(
        native_host_control,
        "supervise_docker_session",
        lambda **kwargs: called.append(kwargs) or 124,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "native_host_control.py",
            "supervise",
            "--session",
            "0123456789abcdef",
            "--container",
            "seneca-stage2-0123456789abcdef",
            "--scratch",
            str(root),
            "--snapshot",
            str(snapshot),
            "--done",
            "done.json",
            "--abort",
            "abort",
            "--ceiling-epoch",
            "9999999999",
            "--metadata-baseline",
            str(metadata),
            "--metadata-mode",
            "rich2-metadata",
            "--cpuset",
            "0-3",
            "--scratch-layout",
            "rich2-stage1",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        native_host_control.main()

    assert exc.value.code == 124
    assert len(called) == 1
    assert called[0]["name"] == "seneca-stage2-0123456789abcdef"
    assert called[0]["session"] == "0123456789abcdef"
    verify_command = called[0]["verify"]
    assert "--abort" in verify_command
    assert str(root / "abort") in verify_command


def test_rich2_identity_cli_matches_preflight_scratch_and_watchdog_label(
    monkeypatch, capsys
):
    from docker_adapter import LABEL

    name, label = native_host_control.rich2_stage1_container_identity(
        "0123456789abcdef"
    )
    scratch = native_host_control.rich2_stage1_scratch_root("0123456789abcdef")

    assert name == "seneca-stage2-0123456789abcdef"
    assert label == f"{LABEL}=0123456789abcdef"
    assert scratch == Path("/var/tmp/seneca-rich2-stage1-0123456789abcdef")
    preflight_source = (DRIVER_DIR / "preflight_host.sh").read_text()
    assert "[[ $data == /var/tmp/seneca-rich2-stage1-*/data ]]" in preflight_source
    monkeypatch.setattr(
        sys,
        "argv",
        ["native_host_control.py", "rich2-identity", "0123456789abcdef"],
    )

    native_host_control.main()

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "name": name,
        "label": label,
        "scratch_root": str(scratch),
    }


def test_preflight_failure_releases_watchdog_to_restore_original(tmp_path, monkeypatch):
    done = tmp_path / "done"
    abort = tmp_path / "abort"
    native_host_control.mark_watchdog_failure(done=done, abort=abort)
    calls = []
    monkeypatch.setattr(docker_watchdog, "owned_container", lambda *_args: None)
    monkeypatch.setattr(
        docker_watchdog, "terminate", lambda *args, **kwargs: calls.append("terminate")
    )
    monkeypatch.setattr(
        docker_watchdog.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command[0]),
    )

    result = docker_watchdog.supervise(
        name="seneca-stage2-0123456789abcdef",
        session="0123456789abcdef",
        deadline=1e20,
        done=done,
        abort=abort,
        restore=["restore-original"],
        verify=["verify-restoration"],
    )

    assert abort.exists() and done.exists()
    assert calls == ["terminate", "restore-original", "verify-restoration"]
    assert result == 124


def test_existing_stage2_restoration_layout_keeps_both_qdrant_checks(
    tmp_path, monkeypatch
):
    for arm in ("A", "B"):
        (tmp_path / arm / "data" / "qdrant").mkdir(parents=True)
    observed = []
    monkeypatch.setattr(native_host_control, "docker", lambda *_args: "")
    monkeypatch.setattr(
        native_host_control,
        "assert_qdrant_unowned",
        lambda path: observed.append(path),
    )

    native_host_control.verify_scratch_unowned(tmp_path)

    assert observed == [
        tmp_path / "A" / "data" / "qdrant",
        tmp_path / "B" / "data" / "qdrant",
    ]
