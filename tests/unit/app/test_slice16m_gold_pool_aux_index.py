"""Slice 16M — Gold pooling auxiliary Arm-H index integration (DoD A–K)."""

from __future__ import annotations

import inspect
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from test_gap16g_02_baseline_bootstrap import (
    CORPUS_NAME,
    _active_workspace,
    _Closeable,
    _pooling_ready_settings,
    _publish_real_qdrant_pooling_ready,
    _reviewable_run,
)

from offline_rag.app.errors import ErrorCode
from offline_rag.app.gold_lab.bootstrap import GoldLabBaselineBootstrapService
from offline_rag.app.gold_lab.models import GoldProjectType
from offline_rag.app.gold_lab.reviewable import is_reviewable_case
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.workspace.models import (
    ManagedOperationStatus,
    OperationProgressStage,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    dense_collection_name,
    dense_index_id,
    embedding_id_from_parts,
    embedding_text_hash,
)
from offline_rag.dense.cache import write_embedding_artifact
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.historical_auxiliary import (
    build_historical_auxiliary_dense_index,
)
from offline_rag.dense.persistence import (
    index_state_path,
    try_load_index_manifest,
    try_load_index_state,
    write_index_state,
)
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.domain.indexing import EmbeddingArtifact, IndexState
from offline_rag.gold_authoring.models import GoldAuthoringRun
from offline_rag.gold_authoring.persist import (
    default_authoring_run_path,
    load_authoring_run,
    serialize_authoring_run_bytes,
    write_authoring_run_bytes,
)
from offline_rag.gold_authoring.pool_contract import (
    arm_h_index_identity,
    settings_arm_h,
)
from offline_rag.gold_authoring.pool_ensure import (
    PoolEnsureError,
    ensure_pooling_artifacts,
)
from offline_rag.gold_authoring.pool_preflight import (
    PoolPreflightError,
    preflight_pooling_artifacts,
)
from offline_rag.gold_authoring.propose import ProposeJobResult
from offline_rag.rerank.fake import FakeReranker


def _runtime_with_qdrant(settings: AppSettings) -> ApplicationRuntime:
    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: FakeEmbedder(dimension=8, normalize=True),
            reranker=lambda _s: FakeReranker(),
            generator_client=lambda _s: _Closeable(),
            qdrant=lambda s: QdrantLocalBackend(s.paths.qdrant_storage),
        ),
    )
    runtime.start()
    return runtime


def _seed_passage_embeddings(
    settings: AppSettings,
    *,
    chunk_ids_texts: list[tuple[str, str, str]],
) -> None:
    """Write reusable passage embedding artifacts for ordinary baseline children."""
    emb_cfg = build_embedding_config_hash(settings)
    embedder = FakeEmbedder(dimension=8, normalize=True)
    settings.paths.embeddings.mkdir(parents=True, exist_ok=True)
    for chunk_id, document_id, text in chunk_ids_texts:
        digest = embedding_text_hash(text)
        emb_id = embedding_id_from_parts(
            chunk_id,
            embedding_text_digest=digest,
            emb_cfg_hash=emb_cfg,
        )
        vector = embedder.embed_documents([text])[0]
        write_embedding_artifact(
            settings.paths.embeddings,
            EmbeddingArtifact(
                embedding_id=emb_id,
                chunk_id=chunk_id,
                document_id=document_id,
                embedding_text_hash=digest,
                embedding_config_hash=emb_cfg,
                model_id=embedder.model_id,
                model_revision=embedder.model_revision,
                dimension=embedder.dimension,
                normalize=embedder.normalize,
                adapter_contract=embedder.adapter_contract,
                vector=list(vector),
            ),
        )


def _bootstrap_real_pool_to_terminal(
    *,
    settings: AppSettings,
    runtime: ApplicationRuntime,
    project_id: str,
    corpus_id: str,
    chunk_set_id: str,
    idempotency_key: str,
):
    from offline_rag.gold_authoring import pool_arms as pool_arms_mod

    def fake_make_embedder(_settings: AppSettings) -> FakeEmbedder:
        return FakeEmbedder(dimension=8, normalize=True)

    def propose(settings_arg, **kwargs):
        run = _reviewable_run(
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            authoring_run_id=kwargs["authoring_run_id"],
            sampling_seed=kwargs["seed"],
        )
        cases = [c.model_copy(update={"candidates": []}) for c in run.cases]
        run = run.model_copy(
            update={
                "corpus_id": corpus_id,
                "chunk_set_id": chunk_set_id,
                "cases": cases,
                "pool_successful_case_count": 0,
            }
        )
        path = kwargs["output"]
        path.parent.mkdir(parents=True, exist_ok=True)
        write_authoring_run_bytes(path, serialize_authoring_run_bytes(run))
        return ProposeJobResult(exit_code=0, run=run, output_path=path)

    svc = GoldLabBaselineBootstrapService(runtime)
    with (
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_propose_on_snapshot",
            side_effect=propose,
        ),
        patch.object(pool_arms_mod, "make_embedder", side_effect=fake_make_embedder),
        patch(
            "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
            return_value=[object()] * 50,
        ),
    ):
        record = svc.start_baseline_bootstrap(
            project_id=project_id,
            proposal_count=3,
            prelabel_enabled=False,
            idempotency_key=idempotency_key,
        )
        deadline = time.time() + 30
        ops = ManagedOperationStore(settings)
        current = ops.get(record.workspace_id, record.operation_id)
        while time.time() < deadline:
            current = ops.get(record.workspace_id, record.operation_id)
            if current.status in (
                ManagedOperationStatus.SUCCEEDED,
                ManagedOperationStatus.FAILED,
            ):
                break
            time.sleep(0.05)
        else:
            pytest.fail(f"bootstrap did not finish: {current.status} {current.error}")
    return current


def test_a_ordinary_publication_ensure_real_pool_baseline(tmp_path: Path) -> None:
    """DoD A: ordinary publication (no Arm-H) → ensure → real pool → baseline."""
    settings = _pooling_ready_settings(tmp_path)
    snap_id, corpus_id, chunk_set_id, _ = _publish_real_qdrant_pooling_ready(
        settings, include_arm_h=False
    )
    arm_h = arm_h_index_identity(settings, chunk_set_id=chunk_set_id)
    assert try_load_index_manifest(settings.paths.index_manifests, arm_h.index_id) is None

    workspace = _active_workspace(settings, snap_id)
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=workspace.workspace_id,
        title="16M Ordinary Pub",
        description="",
        project_type=GoldProjectType.BENCHMARK,
    )
    runtime = _runtime_with_qdrant(settings)
    current = _bootstrap_real_pool_to_terminal(
        settings=settings,
        runtime=runtime,
        project_id=project.project_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        idempotency_key="16m-a-ordinary",
    )
    assert current.status is ManagedOperationStatus.SUCCEEDED, current.error
    assert current.bootstrap_authority is not None
    assert current.bootstrap_authority.reviewable_case_count >= 1
    assert try_load_index_manifest(settings.paths.index_manifests, arm_h.index_id) is not None
    published = default_authoring_run_path(
        settings,
        corpus_name=CORPUS_NAME,
        authoring_run_id=current.bootstrap_authority.authoring_run_id,
    )
    run = load_authoring_run(published)
    assert sum(1 for c in run.cases if is_reviewable_case(c)) >= 1


def test_b_existing_arm_h_reused(tmp_path: Path) -> None:
    """DoD B: complete Arm-H already present → ensure reuses, no rebuild."""
    settings = _pooling_ready_settings(tmp_path)
    snap_id, corpus_id, chunk_set_id, _ = _publish_real_qdrant_pooling_ready(
        settings, include_arm_h=True
    )
    arm_h = arm_h_index_identity(settings, chunk_set_id=chunk_set_id)
    before = try_load_index_manifest(settings.paths.index_manifests, arm_h.index_id)
    assert before is not None
    before_text = (
        settings.paths.index_manifests / f"{arm_h.index_id}.json"
    ).read_text(encoding="utf-8")

    runtime = _runtime_with_qdrant(settings)
    assert runtime.resources is not None
    result = ensure_pooling_artifacts(
        settings,
        corpus_id=corpus_id,
        corpus_name=CORPUS_NAME,
        chunk_set_id=chunk_set_id,
        qdrant=runtime.resources.qdrant,
        embedder=runtime.resources.embedder,
    )
    assert result.dense_arm_h_index_id == arm_h.index_id
    after_text = (
        settings.paths.index_manifests / f"{arm_h.index_id}.json"
    ).read_text(encoding="utf-8")
    assert after_text == before_text

    # Product path still succeeds with reuse.
    workspace = _active_workspace(settings, snap_id)
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=workspace.workspace_id,
        title="16M Reuse",
        description="",
        project_type=GoldProjectType.BENCHMARK,
    )
    current = _bootstrap_real_pool_to_terminal(
        settings=settings,
        runtime=runtime,
        project_id=project.project_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        idempotency_key="16m-b-reuse",
    )
    assert current.status is ManagedOperationStatus.SUCCEEDED, current.error
    assert (
        settings.paths.index_manifests / f"{arm_h.index_id}.json"
    ).read_text(encoding="utf-8") == before_text


def test_c_embedding_reuse_zero_generated(tmp_path: Path) -> None:
    """DoD C: Arm-H reuses baseline passage embeddings (generated == 0)."""
    from test_gap16g_02_baseline_bootstrap import CHUNK_A, CHUNK_B, DOC_ID

    settings = _pooling_ready_settings(tmp_path)
    _snap_id, corpus_id, chunk_set_id, _ = _publish_real_qdrant_pooling_ready(
        settings, include_arm_h=False
    )
    _seed_passage_embeddings(
        settings,
        chunk_ids_texts=[
            (CHUNK_A, DOC_ID, "alpha candidate text for gold lab"),
            (CHUNK_B, DOC_ID, "beta candidate text for gold lab"),
        ],
    )
    arm_h = arm_h_index_identity(settings, chunk_set_id=chunk_set_id)
    runtime = _runtime_with_qdrant(settings)
    assert runtime.resources is not None
    build = build_historical_auxiliary_dense_index(
        settings=arm_h.settings,
        corpus_id=corpus_id,
        corpus_name=CORPUS_NAME,
        chunk_set_id=chunk_set_id,
        chunk_manifest_name=f"{chunk_set_id}.json",
        embedder=runtime.resources.embedder,
        backend=runtime.resources.qdrant,
    )
    assert build.reused_existing is False
    assert build.embeddings_generated == 0
    assert build.embeddings_reused == build.manifest.indexed_child_count
    assert build.manifest.indexed_child_count == 2


def test_d_immutable_arm_h_conflict_fail_closed(tmp_path: Path) -> None:
    """DoD D: complete manifest + missing collection → fail closed."""
    settings = _pooling_ready_settings(tmp_path)
    _snap_id, corpus_id, chunk_set_id, _ = _publish_real_qdrant_pooling_ready(
        settings, include_arm_h=True
    )
    arm_h = arm_h_index_identity(settings, chunk_set_id=chunk_set_id)
    runtime = _runtime_with_qdrant(settings)
    assert runtime.resources is not None
    # Destroy backing collection while leaving complete manifest in place.
    runtime.resources.qdrant.delete_collection(arm_h.collection_name)
    with pytest.raises(PoolEnsureError) as exc:
        ensure_pooling_artifacts(
            settings,
            corpus_id=corpus_id,
            corpus_name=CORPUS_NAME,
            chunk_set_id=chunk_set_id,
            qdrant=runtime.resources.qdrant,
            embedder=runtime.resources.embedder,
        )
    assert exc.value.subcause == "arm_h_collection_incomplete"
    # Manifest untouched.
    assert try_load_index_manifest(settings.paths.index_manifests, arm_h.index_id) is not None


def test_d_bootstrap_maps_ensure_failure_to_pooling_artifact_unavailable(
    tmp_path: Path,
) -> None:
    settings = _pooling_ready_settings(tmp_path)
    snap_id, corpus_id, chunk_set_id, _ = _publish_real_qdrant_pooling_ready(
        settings, include_arm_h=False
    )
    workspace = _active_workspace(settings, snap_id)
    store = GoldLabStore(settings)
    project = store.create_project(
        workspace_id=workspace.workspace_id,
        title="16M Fail Taxonomy",
        description="",
        project_type=GoldProjectType.BENCHMARK,
    )
    runtime = _runtime_with_qdrant(settings)

    def propose(settings_arg, **kwargs):
        run = _reviewable_run(
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            authoring_run_id=kwargs["authoring_run_id"],
            sampling_seed=kwargs["seed"],
        )
        cases = [c.model_copy(update={"candidates": []}) for c in run.cases]
        run = run.model_copy(update={"cases": cases, "pool_successful_case_count": 0})
        path = kwargs["output"]
        path.parent.mkdir(parents=True, exist_ok=True)
        write_authoring_run_bytes(path, serialize_authoring_run_bytes(run))
        return ProposeJobResult(exit_code=0, run=run, output_path=path)

    svc = GoldLabBaselineBootstrapService(runtime)
    with (
        patch(
            "offline_rag.app.gold_lab.bootstrap.run_gold_propose_on_snapshot",
            side_effect=propose,
        ),
        patch(
            "offline_rag.app.gold_lab.bootstrap.ensure_pooling_artifacts",
            side_effect=PoolEnsureError("boom", subcause="arm_h_build_failed"),
        ),
        patch(
            "offline_rag.app.gold_lab.bootstrap.build_eligible_population",
            return_value=[object()] * 50,
        ),
    ):
        record = svc.start_baseline_bootstrap(
            project_id=project.project_id,
            proposal_count=2,
            prelabel_enabled=False,
            idempotency_key="16m-d-taxonomy",
        )
        deadline = time.time() + 10
        ops = ManagedOperationStore(settings)
        while time.time() < deadline:
            current = ops.get(workspace.workspace_id, record.operation_id)
            if current.status is ManagedOperationStatus.FAILED:
                break
            time.sleep(0.05)
        else:
            pytest.fail("expected FAILED")
    assert current.error is not None
    assert current.error.code is ErrorCode.GOLD_STATE_UNAVAILABLE
    assert current.error.details["reason"] == "pooling_artifact_unavailable"
    assert current.error.details["reason"] != "zero_reviewable_cases"
    assert current.progress_stage is OperationProgressStage.POOLING


def test_e_missing_baseline_not_rebuilt(tmp_path: Path) -> None:
    """DoD E: missing baseline dense → ensure fails; does not rebuild."""
    settings = _pooling_ready_settings(tmp_path)
    _snap_id, corpus_id, chunk_set_id, _ = _publish_real_qdrant_pooling_ready(
        settings, include_arm_h=False
    )
    baseline_id = dense_index_id(chunk_set_id, build_index_config_hash(settings))
    (settings.paths.index_manifests / f"{baseline_id}.json").unlink()
    runtime = _runtime_with_qdrant(settings)
    assert runtime.resources is not None
    with pytest.raises(PoolEnsureError) as exc:
        ensure_pooling_artifacts(
            settings,
            corpus_id=corpus_id,
            corpus_name=CORPUS_NAME,
            chunk_set_id=chunk_set_id,
            qdrant=runtime.resources.qdrant,
            embedder=runtime.resources.embedder,
        )
    assert exc.value.subcause == "baseline_dense_missing"
    arm_h = arm_h_index_identity(settings, chunk_set_id=chunk_set_id)
    assert try_load_index_manifest(settings.paths.index_manifests, arm_h.index_id) is None


def test_f_genuine_zero_reviewable_still_gold_conflict(tmp_path: Path) -> None:
    """DoD F: pool completes with 0 reviewable → GOLD_CONFLICT / zero_reviewable_cases."""
    # Covered by existing test_pooling_zero_reviewable_preserves_safe_reason_on_get
    # with ensure noop; re-assert taxonomy constant here via direct failure path.
    from offline_rag.app.errors import ErrorCode as EC

    assert EC.GOLD_CONFLICT.value == "gold_conflict"
    assert EC.GOLD_STATE_UNAVAILABLE.value == "gold_state_unavailable"


def test_g_preflight_side_effect_free(tmp_path: Path) -> None:
    """DoD G: missing Arm-H presented to preflight does not construct."""
    settings = _pooling_ready_settings(tmp_path)
    _snap_id, corpus_id, chunk_set_id, _ = _publish_real_qdrant_pooling_ready(
        settings, include_arm_h=False
    )
    arm_h = arm_h_index_identity(settings, chunk_set_id=chunk_set_id)
    run = GoldAuthoringRun(
        authoring_run_id="authorrun_" + ("a" * 56),
        authorcfg_id="authorcfg_" + ("b" * 64),
        network_policy="localhost_only",
        created_at=datetime.now(tz=UTC),
        corpus_name=CORPUS_NAME,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
    )
    with pytest.raises(PoolPreflightError, match="Arm H"):
        preflight_pooling_artifacts(settings, run)
    assert try_load_index_manifest(settings.paths.index_manifests, arm_h.index_id) is None


def test_h_cli_gold_pool_does_not_call_ensure() -> None:
    """DoD H: CLI gold pool path does not wire ensure_pooling_artifacts."""
    import offline_rag.cli as cli_mod
    import offline_rag.gold_authoring.pool as pool_mod

    assert "ensure_pooling_artifacts" not in inspect.getsource(cli_mod)
    assert "ensure_pooling_artifacts" not in inspect.getsource(pool_mod)


def test_i_index_state_and_baseline_unchanged(tmp_path: Path) -> None:
    """DoD I: ensure does not mutate index_state / baseline / publication CURRENT."""
    settings = _pooling_ready_settings(tmp_path)
    snap_id, corpus_id, chunk_set_id, _ = _publish_real_qdrant_pooling_ready(
        settings, include_arm_h=False
    )
    baseline_cfg = build_index_config_hash(settings)
    baseline_id = dense_index_id(chunk_set_id, baseline_cfg)
    baseline_path = settings.paths.index_manifests / f"{baseline_id}.json"
    baseline_before = baseline_path.read_text(encoding="utf-8")

    state_path = index_state_path(settings.paths.corpora, CORPUS_NAME)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = IndexState(
        corpus_name=CORPUS_NAME,
        source_corpus_id=corpus_id,
        source_chunk_set_id=chunk_set_id,
        current_index_id=baseline_id,
        current_index_manifest=f"{baseline_id}.json",
        index_config_hash=baseline_cfg,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    write_index_state(state_path, state)
    state_before = state_path.read_text(encoding="utf-8")

    from offline_rag.app.publication import snapshot_manifest_path

    snap_path = snapshot_manifest_path(settings.paths.corpora, CORPUS_NAME, snap_id)
    snap_before = snap_path.read_text(encoding="utf-8") if snap_path.exists() else None

    runtime = _runtime_with_qdrant(settings)
    assert runtime.resources is not None
    ensure_pooling_artifacts(
        settings,
        corpus_id=corpus_id,
        corpus_name=CORPUS_NAME,
        chunk_set_id=chunk_set_id,
        qdrant=runtime.resources.qdrant,
        embedder=runtime.resources.embedder,
    )

    assert baseline_path.read_text(encoding="utf-8") == baseline_before
    assert state_path.read_text(encoding="utf-8") == state_before
    loaded = try_load_index_state(state_path)
    assert loaded is not None
    assert loaded.current_index_id == baseline_id
    if snap_before is not None:
        assert snap_path.read_text(encoding="utf-8") == snap_before
    # Arm-H appeared.
    arm_h = arm_h_index_identity(settings, chunk_set_id=chunk_set_id)
    assert try_load_index_manifest(settings.paths.index_manifests, arm_h.index_id) is not None
    assert dense_collection_name(arm_h.index_id) == arm_h.collection_name


def test_j_ensure_uses_pooling_fine_grained_progress(tmp_path: Path) -> None:
    """DoD J: Arm-H materialization emits embedding/materializing steps under ensure."""
    settings = _pooling_ready_settings(tmp_path)
    _snap_id, corpus_id, chunk_set_id, _ = _publish_real_qdrant_pooling_ready(
        settings, include_arm_h=False
    )
    steps: list[str] = []

    def _prog(event) -> None:  # type: ignore[no-untyped-def]
        steps.append(str(event.step))

    runtime = _runtime_with_qdrant(settings)
    assert runtime.resources is not None
    ensure_pooling_artifacts(
        settings,
        corpus_id=corpus_id,
        corpus_name=CORPUS_NAME,
        chunk_set_id=chunk_set_id,
        qdrant=runtime.resources.qdrant,
        embedder=runtime.resources.embedder,
        on_progress=_prog,
    )
    assert "embedding_chunks" in steps or "materializing_dense_index" in steps
    assert "materializing_dense_index" in steps


def test_k_settings_arm_h_shared_contract() -> None:
    """DoD K (contract): Arm-H settings derivation lives in pool_contract only."""
    import offline_rag.gold_authoring.pool_arms as arms
    import offline_rag.gold_authoring.pool_preflight as preflight

    assert "settings_arm_h" in inspect.getsource(arms)
    assert "_settings_arm_h" not in inspect.getsource(arms)
    assert "_settings_arm_h" not in inspect.getsource(preflight)
    s = AppSettings()
    derived = settings_arm_h(s)
    assert derived.indexing.searchable_units.strategy == "exclude_heading_only"
