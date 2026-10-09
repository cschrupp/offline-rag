"""Deterministic public Gold Lab HTTP projections (16F-D)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from offline_rag.app.gold_lab.contribution import ContributionProjection
from offline_rag.app.gold_lab.models import GoldCampaign, GoldProject, GoldRegistration
from offline_rag.app.gold_lab.mutations import MutationResult
from offline_rag.app.gold_lab.scientific_export import ScientificExportResult
from offline_rag.app.gold_lab.tasks import BlindTaskView


def rfc3339_z(value: datetime) -> str:
    if value.tzinfo is None:
        text = value.isoformat()
        return text if text.endswith("Z") else f"{text}Z"
    return value.astimezone().isoformat().replace("+00:00", "Z")


def project_view(project: GoldProject) -> dict[str, Any]:
    return {
        "project_id": project.project_id,
        "workspace_id": project.workspace_id,
        "title": project.title,
        "description": project.description,
        "project_type": project.project_type.value,
        "status": project.status.value,
        "created_at": rfc3339_z(project.created_at),
    }


def campaign_view(campaign: GoldCampaign, *, project_type: str) -> dict[str, Any]:
    return {
        "campaign_id": campaign.campaign_id,
        "project_id": campaign.project_id,
        "workspace_id": campaign.workspace_id,
        "project_type": project_type,
        "snapshot_id": campaign.snapshot_id,
        "chunk_set_id": campaign.chunk_set_id,
        "corpus_id": campaign.corpus_id,
        "corpus_name": campaign.corpus_name,
        "baseline_authoring_run_id": campaign.baseline_authoring_run_id,
        "workspace_revision_at_creation": campaign.workspace_revision_at_creation,
        "status": campaign.status.value,
        "created_at": rfc3339_z(campaign.created_at),
    }


def baseline_summary_view(
    *,
    authoring_run_id: str,
    created_at: datetime,
    corpus_id: str,
    corpus_name: str,
    chunk_set_id: str,
    case_count: int,
    reviewable_case_count: int,
) -> dict[str, Any]:
    return {
        "authoring_run_id": authoring_run_id,
        "created_at": rfc3339_z(created_at),
        "corpus_id": corpus_id,
        "corpus_name": corpus_name,
        "chunk_set_id": chunk_set_id,
        "case_count": int(case_count),
        "reviewable_case_count": int(reviewable_case_count),
    }


def task_summary_view(view: BlindTaskView) -> dict[str, Any]:
    return {
        "task_id": view.task_id,
        "task_kind": view.task_kind,
        "campaign_id": view.campaign_id,
        "case_id": view.case_id,
        "active": view.active,
        "state": view.state,
        "candidate_chunk_id": view.candidate_chunk_id,
        "effective_query": view.effective_query,
    }


def mutation_receipt_view(result: MutationResult) -> dict[str, Any]:
    record = result.record
    return {
        "campaign_id": record.campaign_id,
        "record_id": record.record_id,
        "judgment_id": record.judgment_id,
        "task_id": record.task_id,
        "record_type": record.record_type.value,
        "sequence": record.sequence,
        "created_at": rfc3339_z(record.created_at),
        "replayed": result.replayed,
    }


def contribution_view(projection: ContributionProjection) -> dict[str, Any]:
    return projection.to_dict()


def export_view(result: ScientificExportResult) -> dict[str, Any]:
    return {
        "campaign_id": result.campaign_id,
        "dataset_id": result.dataset_id,
        "dataset_path": result.dataset_path,
        "projection_sha256": result.projection_sha256,
        "exported_case_ids": list(result.exported_case_ids),
        "dataset_reused": result.dataset_reused,
        "registration_replayed": result.registration_replayed,
        "registered_at": rfc3339_z(result.registration.registered_at),
    }


def registration_list_item_view(registration: GoldRegistration) -> dict[str, Any]:
    return {
        "dataset_id": registration.dataset_id,
        "dataset_path": registration.dataset_path,
        "baseline_sha256": registration.baseline_sha256,
        "projection_sha256": registration.projection_sha256,
        "exported_case_ids": list(registration.exported_case_ids),
        "registered_at": rfc3339_z(registration.registered_at),
    }
