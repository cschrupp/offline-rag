"""Internal Gold Lab scientific projection / export / registration (16F-C)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from offline_rag.app.gold_lab.baseline import load_sealed_baseline_run
from offline_rag.app.gold_lab.datasets import (
    finalize_projected_run_to_candidate,
    publish_or_reuse_canonical_dataset,
)
from offline_rag.app.gold_lab.effective_state import fold_effective_state
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import validate_campaign_id
from offline_rag.app.gold_lab.leases import (
    GoldLabCampaignLease,
    GoldLabDatasetLease,
    GoldLabProjectLease,
)
from offline_rag.app.gold_lab.ledger import GoldLabLedger
from offline_rag.app.gold_lab.models import GoldCampaign, GoldProject, GoldRegistration
from offline_rag.app.gold_lab.paths import (
    canonical_dataset_relpath,
    projection_authoring_run_path,
    projection_dir,
)
from offline_rag.app.gold_lab.projection import project_authoring_run, projection_text
from offline_rag.app.gold_lab.registrations import create_or_reuse_registration
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.config.models import AppSettings
from offline_rag.gold_authoring.models import GoldAuthoringRun
from offline_rag.ingestion.io import atomic_write_text


@dataclass(frozen=True)
class ScientificExportResult:
    campaign_id: str
    dataset_id: str
    dataset_path: str
    registration: GoldRegistration
    projection_sha256: str
    exported_case_ids: tuple[str, ...]
    dataset_reused: bool
    registration_replayed: bool


class GoldLabScientificExportService:
    """Derive GoldDataset-v1 + immutable registration from campaign effective state.

    Not an adjudication mutation: does not require OPEN lifecycle, does not append
    ledger rows, and does not alter task state.
    """

    def __init__(
        self,
        settings: AppSettings,
        *,
        store: GoldLabStore | None = None,
        ledger: GoldLabLedger | None = None,
        after_dataset_hook: Callable[[], None] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or GoldLabStore(settings)
        self.ledger = ledger or GoldLabLedger(settings, store=self.store)
        self._after_dataset_hook = after_dataset_hook

    def export_and_register(self, campaign_id: str) -> ScientificExportResult:
        cid = validate_campaign_id(campaign_id)
        campaign = self.store.get_campaign(cid)
        project = self.store.get_project(campaign.project_id)

        with (
            GoldLabProjectLease(self.settings, campaign.project_id),
            GoldLabCampaignLease(self.settings, cid),
        ):
            return self._export_under_campaign_leases(
                campaign_id=cid,
                campaign=campaign,
                project=project,
            )

    def _export_under_campaign_leases(
        self,
        *,
        campaign_id: str,
        campaign: GoldCampaign,
        project: GoldProject,
    ) -> ScientificExportResult:
        # Re-load campaign under lease for durable authority.
        campaign = self.store.get_campaign(campaign_id)
        project = self.store.get_project(campaign.project_id)
        if project.project_id != campaign.project_id:
            raise GoldLabError(
                "registration_project_mismatch",
                "project/campaign binding mismatch",
            )

        baseline = load_sealed_baseline_run(
            self.settings,
            campaign_id=campaign_id,
            baseline_authoring_run_id=campaign.baseline_authoring_run_id,
            baseline_sha256=campaign.baseline_sha256,
        )
        records = self.ledger.list_records(campaign_id)
        state = fold_effective_state(
            campaign_id=campaign_id, baseline=baseline, records=records
        )

        projected = project_authoring_run(state)
        projection_sha256 = self._materialize_projection(
            campaign_id=campaign_id, projected=projected
        )
        # Re-load exact bytes used for this export transaction.
        proj_path = projection_authoring_run_path(self.settings, campaign_id)
        file_bytes = proj_path.read_bytes()
        digest = hashlib.sha256(file_bytes).hexdigest()
        if digest != projection_sha256:
            raise GoldLabError(
                "projection_sha256_mismatch",
                "projection file hash changed during export",
            )
        validated = GoldAuthoringRun.model_validate_json(file_bytes.decode("utf-8"))

        candidate, dataset_id, exported = finalize_projected_run_to_candidate(
            self.settings,
            projected_run=validated,
            projection_path=proj_path,
            campaign_id=campaign_id,
        )

        with GoldLabDatasetLease(self.settings, dataset_id):
            _canonical, reused = publish_or_reuse_canonical_dataset(
                self.settings,
                dataset_id=dataset_id,
                candidate_dir=candidate,
            )
            if self._after_dataset_hook is not None:
                self._after_dataset_hook()
            registration, replayed = create_or_reuse_registration(
                self.settings,
                campaign=campaign,
                project=project,
                dataset_id=dataset_id,
                projection_sha256=projection_sha256,
                exported_case_ids=exported,
                baseline_case_ids={c.draft_case_id for c in baseline.cases},
            )

        return ScientificExportResult(
            campaign_id=campaign_id,
            dataset_id=dataset_id,
            dataset_path=canonical_dataset_relpath(dataset_id),
            registration=registration,
            projection_sha256=projection_sha256,
            exported_case_ids=tuple(exported),
            dataset_reused=reused,
            registration_replayed=replayed,
        )

    def _materialize_projection(
        self, *, campaign_id: str, projected: GoldAuthoringRun
    ) -> str:
        text = projection_text(projected)
        data = text.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        path = projection_authoring_run_path(self.settings, campaign_id)
        projection_dir(self.settings, campaign_id).mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, text)
        on_disk = path.read_bytes()
        if hashlib.sha256(on_disk).hexdigest() != digest:
            raise GoldLabError(
                "projection_sha256_mismatch",
                "written projection bytes do not match digest",
            )
        GoldAuthoringRun.model_validate_json(on_disk.decode("utf-8"))
        return digest
