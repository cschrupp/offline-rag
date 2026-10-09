"""Gold Lab application facade / product transport layer (16F-D)."""

from __future__ import annotations

import re
from typing import Any

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.gold_lab.baseline import assert_pristine_baseline
from offline_rag.app.gold_lab.campaigns import GoldCampaignService
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.historical_source import (
    gold_source_context,
    resolve_historical_chunk,
)
from offline_rag.app.gold_lab.ids import (
    absolute_relevance_task_id,
    hard_call_designation_id,
    new_campaign_id,
    validate_campaign_id,
    validate_project_id,
    validate_task_id,
)
from offline_rag.app.gold_lab.models import (
    GoldRegistration,
    HardCallDesignation,
    build_selection_policy,
)
from offline_rag.app.gold_lab.mutations import GoldLabMutationService
from offline_rag.app.gold_lab.registrations import (
    iter_registration_paths_for_campaign,
    validate_registration_against_authority,
)
from offline_rag.app.gold_lab.reviewable import is_reviewable_case
from offline_rag.app.gold_lab.scientific_export import GoldLabScientificExportService
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.gold_lab.views import (
    baseline_summary_view,
    campaign_view,
    contribution_view,
    export_view,
    mutation_receipt_view,
    project_view,
    registration_list_item_view,
    task_summary_view,
)
from offline_rag.app.workspace.models import WorkspaceStatus
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.gold_authoring.models import GoldAuthoringRun
from offline_rag.gold_authoring.persist import (
    default_authoring_run_path,
    default_authoring_runs_dir,
    load_authoring_run,
)

_AUTHORING_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CLASS_D_REASONS = frozenset(
    {"baseline_human_state_present", "baseline_identity_missing"}
)
_BINDING_MISMATCH_REASONS = frozenset(
    {"chunk_set_mismatch", "corpus_id_mismatch", "corpus_name_mismatch"}
)

GOLD_LAB_REASON_TO_ERROR_CODE: dict[str, ErrorCode] = {
    "absolute_relevance_invalid": ErrorCode.REQUEST_INVALID,
    "absolute_task_inactive": ErrorCode.GOLD_CONFLICT,
    "auxiliary_pair_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "auxiliary_pair_not_distinct": ErrorCode.REQUEST_INVALID,
    "auxiliary_pair_required": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "auxiliary_preference_invalid": ErrorCode.REQUEST_INVALID,
    "baseline_authoring_run_id_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "baseline_corrupt": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "baseline_hash_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "baseline_human_state_present": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "baseline_identity_missing": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "baseline_missing": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "baseline_schema_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "baseline_unreadable": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "campaign_already_closed": ErrorCode.GOLD_CONFLICT,
    "campaign_already_exists": ErrorCode.GOLD_CONFLICT,
    "campaign_closed": ErrorCode.GOLD_CONFLICT,
    "campaign_corrupt": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "campaign_identity_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "campaign_not_found": ErrorCode.GOLD_CAMPAIGN_UNKNOWN,
    "campaign_staging_missing": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "campaign_status_invalid": ErrorCode.GOLD_CONFLICT,
    "candidate_chunk_required": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "candidate_chunk_unresolved": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "candidate_dataset_id_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "candidate_dataset_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "candidate_exported_ids_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "candidate_not_in_case": ErrorCode.REQUEST_INVALID,
    "candidate_schema_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "candidate_staging_missing": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "canonical_dataset_corrupt": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "canonical_dataset_id_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "canonical_dataset_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "canonical_dataset_schema_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "case_not_found": ErrorCode.REQUEST_INVALID,
    "case_not_reviewable": ErrorCode.REQUEST_INVALID,
    "chunk_set_mismatch": ErrorCode.GOLD_CONFLICT,
    "chunk_set_unavailable": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "contribution_unknown_finalized_case": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "corpus_id_mismatch": ErrorCode.GOLD_CONFLICT,
    "corpus_name_mismatch": ErrorCode.GOLD_CONFLICT,
    "dataset_publish_failed": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "dataset_semantic_conflict": ErrorCode.GOLD_CONFLICT,
    "effective_state_absolute_inactive_question": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_absolute_missing_candidate": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_absolute_non_reviewable": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_absolute_null_fingerprint": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_absolute_payload_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_absolute_query_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_cross_basis_supersession": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_cross_task_supersession": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_duplicate_judgment_id": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_qc_edit_not_semantic": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_qc_fingerprint_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_qc_non_reviewable": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_qc_payload_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_qc_payload_noncanonical": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_supersession_branch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_supersession_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_supersession_non_current": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_supersession_unknown": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_task_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "effective_state_unknown_record_type": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "export_project_lock_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "gold_finalize_failed": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "gold_lab_lease_held": ErrorCode.GOLD_BUSY,
    "hard_call_designation_id_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "hard_call_duplicate_target": ErrorCode.REQUEST_INVALID,
    "hard_call_reason_empty": ErrorCode.REQUEST_INVALID,
    "hard_call_target_invalid": ErrorCode.REQUEST_INVALID,
    "hard_call_target_unknown": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "hard_calls_campaign_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "hard_calls_contract_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "hard_calls_corrupt": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "hard_calls_missing": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "hard_calls_schema_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_campaign_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_catalog_corrupt": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_command_kind_invalid": ErrorCode.INTERNAL_ERROR,
    "idempotency_command_kind_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_committed_missing_ledger": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_conflict": ErrorCode.IDEMPOTENCY_CONFLICT,
    "idempotency_duplicate_ledger_key": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_duplicate_record_id": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_entry_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_entry_missing": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_finalize_failed": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_key_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_orphan_ledger_key": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_reservation_exists": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_reserved_fingerprint_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_reserved_id_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_reserved_key_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_schema_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "idempotency_status_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "invalid_campaign_id": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "invalid_dataset_id": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "invalid_hard_call_designation_id": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "invalid_idempotency_path": ErrorCode.INTERNAL_ERROR,
    "invalid_judgment_id": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "invalid_project_id": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "invalid_query_fingerprint": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "invalid_record_id": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "invalid_request_fingerprint": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "invalid_selection_policy_fingerprint": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "invalid_task_id": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "lease_campaign_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "lease_not_held": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_append_failed": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_candidate_not_in_case": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_case_not_found": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_case_not_reviewable": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_duplicate_sequence": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_filename_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_filename_record_id_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_filename_sequence_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_provenance_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_record_exists": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_record_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_record_type_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_schema_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_semantic_contract_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "ledger_sequence_gap": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "project_already_archived": ErrorCode.GOLD_CONFLICT,
    "project_already_exists": ErrorCode.GOLD_CONFLICT,
    "project_archived": ErrorCode.GOLD_CONFLICT,
    "project_corrupt": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "project_identity_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "project_not_found": ErrorCode.GOLD_PROJECT_UNKNOWN,
    "project_status_invalid": ErrorCode.GOLD_CONFLICT,
    "project_type_changed": ErrorCode.GOLD_CONFLICT,
    "project_unarchive_forbidden": ErrorCode.GOLD_CONFLICT,
    "project_workspace_changed": ErrorCode.GOLD_CONFLICT,
    "projection_export_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "projection_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "projection_sha256_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "provenance_type_invalid": ErrorCode.REQUEST_INVALID,
    "question_check_case_not_reviewable": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "question_check_edit_not_semantic": ErrorCode.REQUEST_INVALID,
    "question_check_payload_invalid": ErrorCode.REQUEST_INVALID,
    "registered_dataset_missing": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_campaign_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_conflict": ErrorCode.GOLD_CONFLICT,
    "registration_corrupt": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_dataset_chunk_set_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_dataset_corpus_id_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_dataset_corpus_name_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_dataset_corrupt": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_dataset_id_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_dataset_missing": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_dataset_path_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_dataset_schema_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_exported_ids_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_path_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_project_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_project_type_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_provenance_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_schema_invalid": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "registration_unknown_exported_case": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "selection_policy_parameters_invalid": ErrorCode.REQUEST_INVALID,
    "selection_policy_project_type_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "source_seed_chunk_unresolved": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "source_seed_document_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "task_identity_mismatch": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "workspace_not_active": ErrorCode.GOLD_CONFLICT,
    "workspace_revision_changed": ErrorCode.GOLD_CONFLICT,
    "workspace_snapshot_changed": ErrorCode.GOLD_CONFLICT,
    "workspace_snapshot_missing": ErrorCode.GOLD_STATE_UNAVAILABLE,
    "workspace_stale": ErrorCode.GOLD_CONFLICT,
}


def translate_gold_lab_error(exc: GoldLabError) -> AppError:
    """Central GoldLabError → AppError translator (catalog messages only)."""
    code = GOLD_LAB_REASON_TO_ERROR_CODE.get(exc.reason)
    if code is None:
        return AppError(
            ErrorCode.INTERNAL_ERROR,
            details=SafeErrorDetails(reason="gold_lab_unmapped_error"),
        )
    return AppError(code, details=SafeErrorDetails(reason=exc.reason))


def _app_error(code: ErrorCode, reason: str, **ids: str | None) -> AppError:
    payload = {k: v for k, v in ids.items() if v is not None}
    return AppError(code, details=SafeErrorDetails(reason=reason, **payload))


class GoldLabApplicationService:
    """Thin product orchestration over accepted 16F-A/B/C services."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.settings = runtime.settings
        self.store = GoldLabStore(self.settings)
        self.workspace_store = WorkspaceStore(self.settings)
        self.campaigns = GoldCampaignService(
            self.settings,
            store=self.store,
            workspace_store=self.workspace_store,
            publication=runtime.publication,
            qdrant=None if runtime.resources is None else runtime.resources.qdrant,
        )
        self.mutations = GoldLabMutationService(self.settings, store=self.store)
        self.exports = GoldLabScientificExportService(self.settings, store=self.store)

    def _call(self, fn, /, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except AppError:
            raise
        except GoldLabError as exc:
            raise translate_gold_lab_error(exc) from exc

    # --- projects ---

    def list_projects(self, *, workspace_id: str | None = None) -> dict[str, Any]:
        projects = self._call(self.store.list_projects)
        if workspace_id is not None:
            projects = [p for p in projects if p.workspace_id == workspace_id]
        projects = sorted(
            projects, key=lambda p: (p.created_at, p.project_id)
        )
        return {"projects": [project_view(p) for p in projects]}

    def create_project(
        self,
        *,
        workspace_id: str,
        title: str,
        description: str = "",
        project_type: str,
    ) -> dict[str, Any]:
        project = self._call(
            self.store.create_project,
            workspace_id=workspace_id,
            title=title,
            description=description,
            project_type=project_type,
        )
        return project_view(project)

    def get_project(self, project_id: str) -> dict[str, Any]:
        pid = self._transport_project_id(project_id)
        return project_view(self._call(self.store.get_project, pid))

    def archive_project(self, project_id: str) -> dict[str, Any]:
        pid = self._transport_project_id(project_id)
        return project_view(self._call(self.store.archive_project, pid))

    # --- baseline eligibility ---

    def _safe_authoring_run_id(self, value: str) -> str:
        text = str(value or "").strip()
        if _AUTHORING_RUN_ID_RE.fullmatch(text) is None:
            raise _app_error(
                ErrorCode.REQUEST_INVALID,
                "transport_baseline_authoring_run_id_invalid",
            )
        if "/" in text or "\\" in text or ".." in text:
            raise _app_error(
                ErrorCode.REQUEST_INVALID,
                "transport_baseline_authoring_run_id_invalid",
            )
        return text

    def resolve_eligible_baseline(
        self,
        *,
        project_id: str,
        baseline_authoring_run_id: str,
        for_discovery: bool = False,
    ) -> GoldAuthoringRun:
        """Shared A/B/C/D baseline eligibility resolver."""
        project = self._call(self.store.get_project, project_id)
        workspace = self._call(self.workspace_store.get, project.workspace_id)
        run_id = self._safe_authoring_run_id(baseline_authoring_run_id)
        path = default_authoring_run_path(
            self.settings,
            corpus_name=workspace.backing_corpus_name,
            authoring_run_id=run_id,
        )
        if not path.is_file():
            raise _app_error(
                ErrorCode.GOLD_BASELINE_UNKNOWN,
                "gold_baseline_unknown",
                project_id=project_id,
            )
        try:
            run = load_authoring_run(path)
        except Exception as exc:
            if for_discovery:
                raise _DiscoverySkip() from exc
            raise _app_error(
                ErrorCode.GOLD_STATE_UNAVAILABLE,
                "baseline_corrupt",
                project_id=project_id,
            ) from exc

        stem = path.stem
        if run_id != stem or run.authoring_run_id != run_id:
            if for_discovery:
                raise _DiscoverySkip()
            raise _app_error(
                ErrorCode.GOLD_STATE_UNAVAILABLE,
                "baseline_authoring_run_id_mismatch",
                project_id=project_id,
            )

        try:
            assert_pristine_baseline(run)
        except GoldLabError as exc:
            if for_discovery:
                raise _DiscoverySkip() from exc
            if exc.reason in _CLASS_D_REASONS:
                raise _app_error(
                    ErrorCode.GOLD_CONFLICT,
                    exc.reason,
                    project_id=project_id,
                ) from exc
            if exc.reason == "baseline_schema_invalid":
                raise _app_error(
                    ErrorCode.GOLD_STATE_UNAVAILABLE,
                    exc.reason,
                    project_id=project_id,
                ) from exc
            raise translate_gold_lab_error(exc) from exc

        if workspace.status is not WorkspaceStatus.ACTIVE:
            if for_discovery:
                raise _DiscoverySkip()
            raise _app_error(
                ErrorCode.GOLD_CONFLICT,
                "workspace_not_active",
                project_id=project_id,
            )
        if workspace.current_snapshot_id is None:
            if for_discovery:
                raise _DiscoverySkip()
            raise _app_error(
                ErrorCode.GOLD_STATE_UNAVAILABLE,
                "workspace_snapshot_missing",
                project_id=project_id,
            )

        try:
            snapshot = self.runtime.publication.resolve_snapshot(
                workspace.backing_corpus_name,
                workspace.current_snapshot_id,
            )
        except Exception as exc:
            if for_discovery:
                raise _DiscoverySkip() from exc
            raise _app_error(
                ErrorCode.GOLD_STATE_UNAVAILABLE,
                "workspace_snapshot_missing",
                project_id=project_id,
            ) from exc

        if str(run.chunk_set_id or "").strip() != snapshot.identity.chunk_set_id:
            if for_discovery:
                raise _DiscoverySkip()
            raise _app_error(
                ErrorCode.GOLD_CONFLICT,
                "chunk_set_mismatch",
                project_id=project_id,
            )
        if str(run.corpus_id or "").strip() != snapshot.identity.corpus_id:
            if for_discovery:
                raise _DiscoverySkip()
            raise _app_error(
                ErrorCode.GOLD_CONFLICT,
                "corpus_id_mismatch",
                project_id=project_id,
            )
        if str(run.corpus_name or "").strip() != workspace.backing_corpus_name:
            if for_discovery:
                raise _DiscoverySkip()
            raise _app_error(
                ErrorCode.GOLD_CONFLICT,
                "corpus_name_mismatch",
                project_id=project_id,
            )
        return run

    def list_baselines(self, project_id: str) -> dict[str, Any]:
        pid = self._transport_project_id(project_id)
        project = self._call(self.store.get_project, pid)
        workspace = self._call(self.workspace_store.get, project.workspace_id)
        root = default_authoring_runs_dir(
            self.settings, corpus_name=workspace.backing_corpus_name
        )
        items: list[dict[str, Any]] = []
        if root.is_dir():
            for path in sorted(root.glob("*.json")):
                if not path.is_file():
                    continue
                try:
                    run = self.resolve_eligible_baseline(
                        project_id=pid,
                        baseline_authoring_run_id=path.stem,
                        for_discovery=True,
                    )
                except _DiscoverySkip:
                    continue
                except AppError as exc:
                    if exc.code in {
                        ErrorCode.GOLD_BASELINE_UNKNOWN,
                        ErrorCode.GOLD_CONFLICT,
                        ErrorCode.GOLD_STATE_UNAVAILABLE,
                        ErrorCode.REQUEST_INVALID,
                    }:
                        continue
                    raise
                reviewable = sum(1 for c in run.cases if is_reviewable_case(c))
                items.append(
                    baseline_summary_view(
                        authoring_run_id=run.authoring_run_id,
                        created_at=run.created_at,
                        corpus_id=str(run.corpus_id),
                        corpus_name=str(run.corpus_name),
                        chunk_set_id=str(run.chunk_set_id),
                        case_count=len(run.cases),
                        reviewable_case_count=reviewable,
                    )
                )
        items.sort(key=lambda row: (row["created_at"], row["authoring_run_id"]))
        return {"project_id": pid, "baselines": items}

    # --- campaigns ---

    def list_campaigns(self, project_id: str) -> dict[str, Any]:
        pid = self._transport_project_id(project_id)
        project = self._call(self.store.get_project, pid)
        campaigns = self._call(self.store.list_campaigns, project_id=pid)
        campaigns = sorted(campaigns, key=lambda c: (c.created_at, c.campaign_id))
        return {
            "project_id": pid,
            "campaigns": [
                campaign_view(c, project_type=project.project_type.value)
                for c in campaigns
            ],
        }

    def create_campaign(
        self,
        *,
        project_id: str,
        baseline_authoring_run_id: str,
        selection_policy_id: str,
        selection_policy_parameters: dict[str, Any] | None = None,
        hard_calls: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        pid = self._transport_project_id(project_id)
        project = self._call(self.store.get_project, pid)
        baseline = self.resolve_eligible_baseline(
            project_id=pid,
            baseline_authoring_run_id=baseline_authoring_run_id,
            for_discovery=False,
        )
        campaign_id = new_campaign_id()
        policy = self._call(
            build_selection_policy,
            selection_policy_id=selection_policy_id,
            project_type=project.project_type,
            parameters=selection_policy_parameters or {},
        )
        designations: list[HardCallDesignation] = []
        for item in hard_calls or []:
            case_id = str(item["case_id"])
            candidate_chunk_id = str(item["candidate_chunk_id"])
            reason_code = str(item["reason_code"])
            task_id = absolute_relevance_task_id(
                campaign_id=campaign_id,
                case_id=case_id,
                candidate_chunk_id=candidate_chunk_id,
            )
            designation_id = hard_call_designation_id(
                campaign_id=campaign_id, target_task_id=task_id
            )
            designations.append(
                HardCallDesignation(
                    designation_id=designation_id,
                    target_task_id=task_id,
                    reason_code=reason_code,
                )
            )
        try:
            campaign = self.campaigns.create_campaign(
                project_id=pid,
                baseline=baseline,
                selection_policy=policy,
                hard_call_designations=designations,
                campaign_id=campaign_id,
            )
        except GoldLabError as exc:
            raise translate_gold_lab_error(exc) from exc
        return campaign_view(campaign, project_type=project.project_type.value)

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        cid = self._transport_campaign_id(campaign_id)
        campaign = self._call(self.store.get_campaign, cid)
        project = self._call(self.store.get_project, campaign.project_id)
        return campaign_view(campaign, project_type=project.project_type.value)

    def close_campaign(self, campaign_id: str) -> dict[str, Any]:
        cid = self._transport_campaign_id(campaign_id)
        campaign = self._call(self.store.close_campaign, cid)
        project = self._call(self.store.get_project, campaign.project_id)
        return campaign_view(campaign, project_type=project.project_type.value)

    # --- tasks ---

    def list_tasks(
        self,
        campaign_id: str,
        *,
        kind: str | None = None,
        state: str | None = None,
        active: bool | None = None,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        cid = self._transport_campaign_id(campaign_id)
        self._call(self.store.get_campaign, cid)
        views = self._call(self.mutations.blind_task_views, cid)
        filtered = []
        for view in views:
            if kind is not None and view.task_kind != kind:
                continue
            if state is not None and view.state != state:
                continue
            if active is not None and view.active is not active:
                continue
            if case_id is not None and view.case_id != case_id:
                continue
            filtered.append(view)
        return {
            "campaign_id": cid,
            "tasks": [task_summary_view(v) for v in filtered],
        }

    def get_task(self, campaign_id: str, task_id: str) -> dict[str, Any]:
        cid = self._transport_campaign_id(campaign_id)
        tid = self._transport_task_id(task_id)
        campaign = self._call(self.store.get_campaign, cid)
        state = self._call(self.mutations.load_effective_state, cid)
        views = self._call(self.mutations.blind_task_views, cid)
        match = next((v for v in views if v.task_id == tid), None)
        if match is None:
            raise _app_error(
                ErrorCode.GOLD_TASK_UNKNOWN,
                "gold_task_unknown",
                campaign_id=cid,
                task_id=tid,
            )
        summary = task_summary_view(match)
        presentation, current_result = self._task_presentation(
            campaign=campaign, state=state, summary=match
        )
        return {
            **summary,
            "presentation": presentation,
            "current_result": current_result,
        }

    def _task_presentation(self, *, campaign, state, summary):
        case = next(
            (c for c in state.baseline.cases if c.draft_case_id == summary.case_id),
            None,
        )
        if case is None:
            raise _app_error(
                ErrorCode.GOLD_STATE_UNAVAILABLE,
                "historical_chunk_unavailable",
                campaign_id=campaign.campaign_id,
                task_id=summary.task_id,
            )
        if summary.task_kind == "question_check":
            source = None
            if case.source_seed is not None:
                seed = case.source_seed
                chunk, _corpus, source_name = resolve_historical_chunk(
                    self.settings,
                    campaign,
                    chunk_id=seed.chunk_id,
                    expected_document_id=seed.document_id,
                    expected_section_path=list(seed.section_path or []),
                )
                title = getattr(seed, "document_title", None)
                source = gold_source_context(
                    chunk=chunk,
                    document_title=title if title else None,
                    source_name=source_name,
                )
            presentation = {
                "kind": "question_check",
                "proposed_query": case.proposed_query,
                "proposed_category": case.proposed_category,
                "proposed_tags": list(case.proposed_tags or []),
                "source": source,
            }
            qc = state.question_by_task.get(summary.task_id)
            if qc is None:
                current = None
            else:
                current = {
                    "kind": "question_check",
                    "decision": qc.decision.value,
                    "effective_query": qc.effective_query,
                    "effective_category": qc.effective_category,
                    "effective_tags": list(qc.effective_tags or []),
                }
            return presentation, current

        # absolute relevance
        if not summary.active:
            return None, None
        candidate = next(
            (
                c
                for c in case.candidates
                if c.chunk_id == summary.candidate_chunk_id
            ),
            None,
        )
        if candidate is None:
            raise _app_error(
                ErrorCode.GOLD_STATE_UNAVAILABLE,
                "historical_chunk_unavailable",
                campaign_id=campaign.campaign_id,
                task_id=summary.task_id,
            )
        chunk, _corpus, source_name = resolve_historical_chunk(
            self.settings,
            campaign,
            chunk_id=candidate.chunk_id,
            expected_document_id=candidate.document_id,
            expected_section_path=list(candidate.section_path or []),
        )
        title = getattr(candidate, "document_title", None)
        presentation = {
            "kind": "absolute_relevance",
            "effective_query": summary.effective_query,
            "effective_category": (
                state.current_question_for_case(summary.case_id).effective_category
                if state.current_question_for_case(summary.case_id) is not None
                else None
            ),
            "effective_tags": (
                list(state.current_question_for_case(summary.case_id).effective_tags or [])
                if state.current_question_for_case(summary.case_id) is not None
                else []
            ),
            "candidate": gold_source_context(
                chunk=chunk,
                document_title=title if title else None,
                source_name=source_name,
            ),
        }
        qc = state.current_question_for_case(summary.case_id)
        current_fp = qc.query_fingerprint if qc is not None else None
        current_abs = None
        if current_fp is not None:
            current_abs = state.absolute_by_basis.get((summary.task_id, current_fp))
        if current_abs is None:
            current = None
        else:
            current = {
                "kind": "absolute_relevance",
                "relevance": int(current_abs.relevance),
            }
        return presentation, current

    # --- mutations ---

    def submit_question_check(
        self,
        *,
        campaign_id: str,
        task_id: str,
        idempotency_key: str,
        payload: dict[str, Any],
        game_id: str | None = None,
        presentation_id: str | None = None,
    ) -> dict[str, Any]:
        cid = self._transport_campaign_id(campaign_id)
        tid = self._transport_task_id(task_id)
        view = self._require_task(cid, tid, kind="question_check")
        # Transport already validated the decision-discriminated union; pass the
        # exact frozen adapter payload through to accepted 16F-B canonicalization.
        result = self._call(
            self.mutations.submit_question_check,
            campaign_id=cid,
            case_id=view.case_id,
            payload=payload,
            idempotency_key=idempotency_key,
            game_id=game_id,
            presentation_id=presentation_id,
        )
        return mutation_receipt_view(result)

    def submit_relevance(
        self,
        *,
        campaign_id: str,
        task_id: str,
        idempotency_key: str,
        relevance: int,
        game_id: str | None = None,
        presentation_id: str | None = None,
    ) -> dict[str, Any]:
        cid = self._transport_campaign_id(campaign_id)
        tid = self._transport_task_id(task_id)
        view = self._require_task(cid, tid, kind="absolute_relevance")
        result = self._call(
            self.mutations.submit_absolute_relevance,
            campaign_id=cid,
            case_id=view.case_id,
            candidate_chunk_id=str(view.candidate_chunk_id),
            relevance=relevance,
            idempotency_key=idempotency_key,
            game_id=game_id,
            presentation_id=presentation_id,
        )
        return mutation_receipt_view(result)

    def submit_preference(
        self,
        *,
        campaign_id: str,
        idempotency_key: str,
        case_id: str,
        preferred_chunk_id: str,
        other_chunk_id: str,
        game_id: str | None = None,
        presentation_id: str | None = None,
    ) -> dict[str, Any]:
        cid = self._transport_campaign_id(campaign_id)
        result = self._call(
            self.mutations.submit_auxiliary_preference,
            campaign_id=cid,
            case_id=case_id,
            preferred_chunk_id=preferred_chunk_id,
            other_chunk_id=other_chunk_id,
            idempotency_key=idempotency_key,
            game_id=game_id,
            presentation_id=presentation_id,
        )
        return mutation_receipt_view(result)

    def contribution(self, campaign_id: str) -> dict[str, Any]:
        cid = self._transport_campaign_id(campaign_id)
        return contribution_view(self._call(self.mutations.contribution, cid))

    def export_campaign(self, campaign_id: str) -> tuple[dict[str, Any], int]:
        cid = self._transport_campaign_id(campaign_id)
        result = self._call(self.exports.export_and_register, cid)
        status = 200 if result.registration_replayed else 201
        return export_view(result), status

    def list_registrations(self, campaign_id: str) -> dict[str, Any]:
        cid = self._transport_campaign_id(campaign_id)
        campaign = self._call(self.store.get_campaign, cid)
        project = self._call(self.store.get_project, campaign.project_id)
        items: list[dict[str, Any]] = []
        for path in iter_registration_paths_for_campaign(self.settings, cid):
            try:
                registration = GoldRegistration.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception as exc:
                raise _app_error(
                    ErrorCode.GOLD_STATE_UNAVAILABLE,
                    "registration_corrupt",
                    campaign_id=cid,
                ) from exc
            self._call(
                validate_registration_against_authority,
                self.settings,
                registration,
                campaign=campaign,
                project=project,
            )
            items.append(registration_list_item_view(registration))
        items.sort(key=lambda row: (row["registered_at"], row["dataset_id"]))
        return {"campaign_id": cid, "registrations": items}

    # --- helpers ---

    def _require_task(self, campaign_id: str, task_id: str, *, kind: str):
        views = self._call(self.mutations.blind_task_views, campaign_id)
        match = next((v for v in views if v.task_id == task_id), None)
        if match is None:
            raise _app_error(
                ErrorCode.GOLD_TASK_UNKNOWN,
                "gold_task_unknown",
                campaign_id=campaign_id,
                task_id=task_id,
            )
        if match.task_kind != kind:
            raise _app_error(
                ErrorCode.REQUEST_INVALID,
                "gold_task_kind_mismatch",
                campaign_id=campaign_id,
                task_id=task_id,
            )
        return match

    def _transport_project_id(self, value: str) -> str:
        try:
            return validate_project_id(value)
        except GoldLabError as exc:
            raise _app_error(
                ErrorCode.REQUEST_INVALID, "transport_project_id_invalid"
            ) from exc

    def _transport_campaign_id(self, value: str) -> str:
        try:
            return validate_campaign_id(value)
        except GoldLabError as exc:
            raise _app_error(
                ErrorCode.REQUEST_INVALID, "transport_campaign_id_invalid"
            ) from exc

    def _transport_task_id(self, value: str) -> str:
        try:
            return validate_task_id(value)
        except GoldLabError as exc:
            raise _app_error(
                ErrorCode.REQUEST_INVALID, "transport_task_id_invalid"
            ) from exc


class _DiscoverySkip(Exception):
    """Internal: suppress ineligible baseline during discovery scan."""


