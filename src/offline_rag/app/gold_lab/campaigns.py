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
)
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
from offline_rag.app.gold_lab.publish import atomic_publish_nested_directory
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.publication import ProductPublicationRegistry
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
        before_promote: object | None = None,
    ) -> GoldCampaign:
        """Publish an immutable campaign package atomically.

        ``before_promote`` is a test-only hook invoked immediately before the
        final directory rename (after staging). Production callers omit it.
        """
        cid = campaign_id or new_campaign_id()
        if not cid.startswith("goldcamp_"):
            raise GoldLabError(
                "invalid_campaign_id",
                "campaign_id must start with goldcamp_",
            )
        if campaign_dir(self.settings, cid).exists():
            raise GoldLabError(
                "campaign_already_exists",
                f"campaign already exists: {cid}",
            )

        # 1. validate project
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

        # 2–3. capture ACTIVE workspace revision + snapshot; resolve exact snapshot
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

        snapshot = self.publication.resolve_snapshot(
            workspace.backing_corpus_name,
            captured_snapshot_id,
        )

        # 4–5. validate baseline + pristine human state
        assert_pristine_baseline(baseline)

        # 6. validate corpus/chunk identity equalities
        baseline_chunk = str(baseline.chunk_set_id).strip()
        baseline_corpus_id = str(baseline.corpus_id).strip()
        baseline_corpus_name = str(baseline.corpus_name).strip()
        if baseline_chunk != snapshot.identity.chunk_set_id:
            raise GoldLabError(
                "chunk_set_mismatch",
                "baseline.chunk_set_id does not match resolved snapshot",
            )
        if baseline_corpus_id != snapshot.identity.corpus_id:
            raise GoldLabError(
                "corpus_id_mismatch",
                "baseline.corpus_id does not match resolved snapshot",
            )
        if baseline_corpus_name != workspace.backing_corpus_name:
            raise GoldLabError(
                "corpus_name_mismatch",
                "baseline.corpus_name does not match workspace.backing_corpus_name",
            )
        if snapshot.corpus_name != workspace.backing_corpus_name:
            raise GoldLabError(
                "corpus_name_mismatch",
                "resolved snapshot corpus_name does not match workspace",
            )

        # 7. validate candidates/source seeds against historical chunk set
        validate_historical_chunk_identities(
            self.settings,
            baseline,
            corpus_name=workspace.backing_corpus_name,
            corpus_id=snapshot.identity.corpus_id,
            chunk_set_id=snapshot.identity.chunk_set_id,
            corpus_manifest_name=snapshot.identity.corpus_manifest,
        )

        # 8. validate Hard Calls
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
            atomic_write_text(
                staged / "campaign.json",
                campaign.model_dump_json(),
            )
            atomic_write_text(
                staged / "hard_calls.json",
                hard_calls.model_dump_json(),
            )

        def _preflight() -> None:
            if before_promote is not None:
                assert callable(before_promote)
                before_promote()
            # 12–13. re-read workspace immediately before publication
            latest = self.workspace_store.get(project.workspace_id)
            if latest.status is not WorkspaceStatus.ACTIVE:
                raise GoldLabError(
                    "workspace_stale",
                    "workspace no longer ACTIVE before campaign publication",
                )
            if latest.revision != captured_revision:
                raise GoldLabError(
                    "workspace_revision_changed",
                    "workspace revision changed before campaign publication",
                )
            if latest.current_snapshot_id != captured_snapshot_id:
                raise GoldLabError(
                    "workspace_snapshot_changed",
                    "workspace current_snapshot_id changed before publication",
                )

        destination = campaign_dir(self.settings, cid)
        atomic_publish_nested_directory(
            destination,
            _populate,
            preflight=_preflight,
        )
        return self.store.get_campaign(cid)
