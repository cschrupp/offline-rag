"""Gold Lab project / campaign persistence stores (no HTTP)."""

from __future__ import annotations

from datetime import UTC, datetime

from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import new_project_id
from offline_rag.app.gold_lab.leases import GoldLabProjectLease
from offline_rag.app.gold_lab.models import (
    GoldCampaign,
    GoldCampaignStatus,
    GoldProject,
    GoldProjectStatus,
    GoldProjectType,
)
from offline_rag.app.gold_lab.paths import (
    campaign_dir,
    campaign_json_path,
    campaigns_root,
    ensure_gold_lab_layout,
    project_dir,
    project_json_path,
    projects_root,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text


class GoldLabStore:
    """Internal create/get/list for projects and campaigns."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        ensure_gold_lab_layout(settings)

    def create_project(
        self,
        *,
        workspace_id: str,
        title: str,
        description: str = "",
        project_type: GoldProjectType | str,
        project_id: str | None = None,
    ) -> GoldProject:
        # Workspace must resolve (ownership immutability starts at create).
        WorkspaceStore(self.settings).get(workspace_id)
        pid = project_id or new_project_id()
        if not pid.startswith("goldproj_"):
            raise GoldLabError("invalid_project_id", "project_id must start with goldproj_")
        project = GoldProject(
            project_id=pid,
            workspace_id=workspace_id,
            title=title,
            description=description,
            project_type=GoldProjectType(project_type),
            created_at=datetime.now(tz=UTC),
            status=GoldProjectStatus.ACTIVE,
        )
        path = project_json_path(self.settings, pid)
        with GoldLabProjectLease(self.settings, pid):
            if path.exists():
                raise GoldLabError(
                    "project_already_exists",
                    f"project already exists: {pid}",
                )
            project_dir(self.settings, pid).mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, project.model_dump_json())
        return project

    def get_project(self, project_id: str) -> GoldProject:
        path = project_json_path(self.settings, project_id)
        if not path.exists():
            raise GoldLabError("project_not_found", f"unknown project: {project_id}")
        try:
            return GoldProject.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise GoldLabError(
                "project_corrupt",
                f"unreadable project: {project_id}",
            ) from exc

    def list_projects(self) -> list[GoldProject]:
        root = projects_root(self.settings)
        if not root.exists():
            return []
        projects: list[GoldProject] = []
        for path in sorted(root.iterdir()):
            if not path.is_dir():
                continue
            json_path = path / "project.json"
            if not json_path.exists():
                continue
            projects.append(self.get_project(path.name))
        return projects

    def archive_project(self, project_id: str) -> GoldProject:
        """Internal lifecycle primitive: active -> archived only."""
        with GoldLabProjectLease(self.settings, project_id):
            project = self.get_project(project_id)
            if project.status is GoldProjectStatus.ARCHIVED:
                raise GoldLabError(
                    "project_already_archived",
                    f"project already archived: {project_id}",
                )
            if project.status is not GoldProjectStatus.ACTIVE:
                raise GoldLabError(
                    "project_status_invalid",
                    f"cannot archive from status={project.status}",
                )
            updated = project.model_copy(update={"status": GoldProjectStatus.ARCHIVED})
            atomic_write_text(
                project_json_path(self.settings, project_id),
                updated.model_dump_json(),
            )
            return updated

    def unarchive_project(self, project_id: str) -> GoldProject:
        """Explicitly rejected — no unarchive in 16F v1."""
        raise GoldLabError(
            "project_unarchive_forbidden",
            f"unarchive is not allowed for project: {project_id}",
        )

    def get_campaign(self, campaign_id: str) -> GoldCampaign:
        path = campaign_json_path(self.settings, campaign_id)
        if not path.exists():
            raise GoldLabError("campaign_not_found", f"unknown campaign: {campaign_id}")
        # Staged/temp siblings must never be treated as authority.
        if not campaign_dir(self.settings, campaign_id).is_dir():
            raise GoldLabError("campaign_not_found", f"unknown campaign: {campaign_id}")
        try:
            return GoldCampaign.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise GoldLabError(
                "campaign_corrupt",
                f"unreadable campaign: {campaign_id}",
            ) from exc

    def list_campaigns(self, *, project_id: str | None = None) -> list[GoldCampaign]:
        root = campaigns_root(self.settings)
        if not root.exists():
            return []
        campaigns: list[GoldCampaign] = []
        for path in sorted(root.iterdir()):
            if not path.is_dir():
                continue
            name = path.name
            if name.startswith("."):
                # Abandoned staging directories are not campaign authority.
                continue
            json_path = path / "campaign.json"
            if not json_path.exists():
                continue
            campaign = self.get_campaign(name)
            if project_id is not None and campaign.project_id != project_id:
                continue
            campaigns.append(campaign)
        return campaigns

    def close_campaign(self, campaign_id: str) -> GoldCampaign:
        """Internal lifecycle primitive: open -> closed only."""
        from offline_rag.app.gold_lab.leases import GoldLabCampaignLease

        with GoldLabCampaignLease(self.settings, campaign_id):
            campaign = self.get_campaign(campaign_id)
            if campaign.status is GoldCampaignStatus.CLOSED:
                raise GoldLabError(
                    "campaign_already_closed",
                    f"campaign already closed: {campaign_id}",
                )
            if campaign.status is not GoldCampaignStatus.OPEN:
                raise GoldLabError(
                    "campaign_status_invalid",
                    f"cannot close from status={campaign.status}",
                )
            updated = campaign.model_copy(update={"status": GoldCampaignStatus.CLOSED})
            atomic_write_text(
                campaign_json_path(self.settings, campaign_id),
                updated.model_dump_json(),
            )
            return updated
