"""Campaign creation with exact binding and atomic nested publication."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.app.gold_lab.baseline import (
    assert_pristine_baseline,
    validate_hard_call_targets,
    validate_historical_chunk_identities,
)
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import (
    HARD_CALL_DESIGNATION_CONTRACT,
    HARD_CALLS_SCHEMA,
    new_campaign_id,
    validate_campaign_id,
)
from offline_rag.app.gold_lab.leases import GoldLabProjectLease
from offline_rag.app.gold_lab.models import (
    GoldCampaign,
    GoldCampaignStatus,
    GoldProjectStatus,
    GoldSelectionPolicy,
    HardCallDesignation,
    HardCallsArtifact,
)
from offline_rag.app.gold_lab.paths import (
    campaign_dir,
    ensure_gold_lab_layout,
)
from offline_rag.app.gold_lab.publish import (
    cleanup_staged_directory,
    promote_staged_directory,
    stage_nested_directory,
)
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.publication import ProductPublicationRegistry
from offline_rag.app.workspace.leases import WorkspaceMutationLease
from offline_rag.app.workspace.models import WorkspaceStatus
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config.models import AppSettings
from offline_rag.gold_authoring.models import GoldAuthoringRun
from offline_rag.ingestion.io import atomic_write_text


class GoldCampaignService:
    """Internal campaign publication service (no product mutation commands)."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        store: GoldLabStore | None = None,
        workspace_store: WorkspaceStore | None = None,
        publication: ProductPublicationRegistry | None = None,
        qdrant: object | None = None,
    ) -> None:
        self.settings = settings
        ensure_gold_lab_layout(settings)
        self.store = store or GoldLabStore(settings)
        self.workspace_store = workspace_store or WorkspaceStore(settings)
        self.publication = publication or ProductPublicationRegistry(
            settings, qdrant=qdrant
        )

    def create_campaign(
        self,
        *,
        project_id: str,
        baseline: GoldAuthoringRun,
        selection_policy: GoldSelectionPolicy,
        hard_call_designations: list[HardCallDesignation] | None = None,
        campaign_id: str | None = None,
        after_stage: object | None = None,
        before_commit: object | None = None,
        before_promote: object | None = None,
    ) -> GoldCampaign:
        """Publish an immutable campaign package atomically.

        Final commit holds ``WorkspaceMutationLease`` then ``GoldLabProjectLease``
        across revalidation and ``os.replace``.

        Test hooks:
        - ``after_stage``: after staging, before lease acquisition (stale races)
        - ``before_commit`` / ``before_promote``: under both leases, before rename
        """
        under_lease_hook = (
            before_commit if before_commit is not None else before_promote
        )
        cid = validate_campaign_id(campaign_id or new_campaign_id())
        destination = campaign_dir(self.settings, cid)
        if destination.exists():
            raise GoldLabError(
                "campaign_already_exists",
                f"campaign already exists: {cid}",
            )

        # Early validation (not the final commit boundary).
        project = self.store.get_project(project_id)
        if project.status is GoldProjectStatus.ARCHIVED:
            raise GoldLabError(
                "project_archived",
                f"cannot create campaign under archived project: {project_id}",
            )
        if project.status is not GoldProjectStatus.ACTIVE:
            raise GoldLabError(
                "project_status_invalid",
                f"project not active: {project_id}",
            )
        if selection_policy.project_type != project.project_type:
            raise GoldLabError(
                "selection_policy_project_type_mismatch",
                "selection_policy.project_type must match GoldProject.project_type",
            )

        workspace = self.workspace_store.get(project.workspace_id)
        if workspace.status is not WorkspaceStatus.ACTIVE:
            raise GoldLabError(
                "workspace_not_active",
                f"workspace must be ACTIVE: {project.workspace_id}",
            )
        if workspace.current_snapshot_id is None:
            raise GoldLabError(
                "workspace_snapshot_missing",
                "ACTIVE workspace missing current_snapshot_id",
            )
        captured_revision = workspace.revision
        captured_snapshot_id = workspace.current_snapshot_id
        captured_workspace_id = project.workspace_id
        captured_project_type = project.project_type

        snapshot = self.publication.resolve_snapshot(
            workspace.backing_corpus_name,
            captured_snapshot_id,
        )

        assert_pristine_baseline(baseline)

        if str(baseline.chunk_set_id).strip() != snapshot.identity.chunk_set_id:
            raise GoldLabError(
                "chunk_set_mismatch",
                "baseline.chunk_set_id does not match resolved snapshot",
            )
        if str(baseline.corpus_id).strip() != snapshot.identity.corpus_id:
            raise GoldLabError(
                "corpus_id_mismatch",
                "baseline.corpus_id does not match resolved snapshot",
            )
        if str(baseline.corpus_name).strip() != workspace.backing_corpus_name:
            raise GoldLabError(
                "corpus_name_mismatch",
                "baseline.corpus_name does not match workspace.backing_corpus_name",
            )
        if snapshot.corpus_name != workspace.backing_corpus_name:
            raise GoldLabError(
                "corpus_name_mismatch",
                "resolved snapshot corpus_name does not match workspace",
            )

        validate_historical_chunk_identities(
            self.settings,
            baseline,
            corpus_name=workspace.backing_corpus_name,
            corpus_id=snapshot.identity.corpus_id,
            chunk_set_id=snapshot.identity.chunk_set_id,
            corpus_manifest_name=snapshot.identity.corpus_manifest,
        )

        designations = list(hard_call_designations or [])
        validate_hard_call_targets(
            campaign_id=cid,
            run=baseline,
            target_task_ids=[d.target_task_id for d in designations],
        )
        hard_calls = HardCallsArtifact(
            schema_version=HARD_CALLS_SCHEMA,
            campaign_id=cid,
            designation_contract=HARD_CALL_DESIGNATION_CONTRACT,
            designations=designations,
        )

        baseline_text = baseline.model_dump_json()
        created_at = datetime.now(tz=UTC)

        def _populate(staged: Path) -> None:
            (staged / "baseline").mkdir(parents=True, exist_ok=True)
            (staged / "ledger").mkdir(parents=True, exist_ok=True)
            (staged / "projection").mkdir(parents=True, exist_ok=True)
            baseline_path = staged / "baseline" / "authoring_run.json"
            atomic_write_text(baseline_path, baseline_text)
            staged_baseline = baseline_path.read_bytes()
            baseline_sha256 = hashlib.sha256(staged_baseline).hexdigest()
            campaign = GoldCampaign(
                campaign_id=cid,
                project_id=project.project_id,
                workspace_id=project.workspace_id,
                snapshot_id=captured_snapshot_id,
                chunk_set_id=snapshot.identity.chunk_set_id,
                corpus_id=snapshot.identity.corpus_id,
                corpus_name=workspace.backing_corpus_name,
                selection_policy=selection_policy,
                baseline_authoring_run_id=baseline.authoring_run_id,
                baseline_sha256=baseline_sha256,
                workspace_revision_at_creation=captured_revision,
                created_at=created_at,
                status=GoldCampaignStatus.OPEN,
            )
            atomic_write_text(staged / "campaign.json", campaign.model_dump_json())
            atomic_write_text(staged / "hard_calls.json", hard_calls.model_dump_json())

        staged: Path | None = None
        try:
            staged = stage_nested_directory(destination, _populate)
            if after_stage is not None:
                assert callable(after_stage)
                after_stage()

            # Frozen lock order: workspace lease -> project lease.
            with (
                WorkspaceMutationLease(self.settings, captured_workspace_id),
                GoldLabProjectLease(self.settings, project.project_id),
            ):
                if under_lease_hook is not None:
                    assert callable(under_lease_hook)
                    under_lease_hook()

                latest_project = self.store.get_project(project.project_id)
                if latest_project.status is not GoldProjectStatus.ACTIVE:
                    raise GoldLabError(
                        "project_archived",
                        "project not active at campaign commit",
                    )
                if latest_project.workspace_id != captured_workspace_id:
                    raise GoldLabError(
                        "project_workspace_changed",
                        "project workspace_id changed at campaign commit",
                    )
                if latest_project.project_type != captured_project_type:
                    raise GoldLabError(
                        "project_type_changed",
                        "project_type changed at campaign commit",
                    )
                if selection_policy.project_type != latest_project.project_type:
                    raise GoldLabError(
                        "selection_policy_project_type_mismatch",
                        "selection_policy.project_type must match project",
                    )

                latest_ws = self.workspace_store.get(captured_workspace_id)
                if latest_ws.status is not WorkspaceStatus.ACTIVE:
                    raise GoldLabError(
                        "workspace_stale",
                        "workspace no longer ACTIVE before campaign publication",
                    )
                if latest_ws.revision != captured_revision:
                    raise GoldLabError(
                        "workspace_revision_changed",
                        "workspace revision changed before campaign publication",
                    )
                if latest_ws.current_snapshot_id != captured_snapshot_id:
                    raise GoldLabError(
                        "workspace_snapshot_changed",
                        "workspace current_snapshot_id changed before publication",
                    )

                if destination.exists():
                    raise GoldLabError(
                        "campaign_already_exists",
                        f"campaign already exists: {cid}",
                    )
                promote_staged_directory(staged, destination)
                staged = None
        finally:
            cleanup_staged_directory(staged)

        return self.store.get_campaign(cid)
