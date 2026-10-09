"""Gold Lab durable path helpers (strict ID grammar at the boundary)."""

from __future__ import annotations

from pathlib import Path

from offline_rag.app.gold_lab.ids import (
    validate_campaign_id,
    validate_dataset_id,
    validate_project_id,
)
from offline_rag.config.models import AppSettings, PathSettings


def gold_lab_root(settings: AppSettings | PathSettings) -> Path:
    paths = settings.paths if isinstance(settings, AppSettings) else settings
    return paths.gold_lab


def projects_root(settings: AppSettings | PathSettings) -> Path:
    return gold_lab_root(settings) / "projects"


def campaigns_root(settings: AppSettings | PathSettings) -> Path:
    return gold_lab_root(settings) / "campaigns"


def datasets_root(settings: AppSettings | PathSettings) -> Path:
    return gold_lab_root(settings) / "datasets"


def registrations_root(settings: AppSettings | PathSettings) -> Path:
    return gold_lab_root(settings) / "registrations"


def project_dir(settings: AppSettings | PathSettings, project_id: str) -> Path:
    pid = validate_project_id(project_id)
    return projects_root(settings) / pid


def project_json_path(settings: AppSettings | PathSettings, project_id: str) -> Path:
    return project_dir(settings, project_id) / "project.json"


def campaign_dir(settings: AppSettings | PathSettings, campaign_id: str) -> Path:
    cid = validate_campaign_id(campaign_id)
    return campaigns_root(settings) / cid


def campaign_json_path(settings: AppSettings | PathSettings, campaign_id: str) -> Path:
    return campaign_dir(settings, campaign_id) / "campaign.json"


def hard_calls_path(settings: AppSettings | PathSettings, campaign_id: str) -> Path:
    return campaign_dir(settings, campaign_id) / "hard_calls.json"


def baseline_dir(settings: AppSettings | PathSettings, campaign_id: str) -> Path:
    return campaign_dir(settings, campaign_id) / "baseline"


def baseline_authoring_run_path(
    settings: AppSettings | PathSettings, campaign_id: str
) -> Path:
    return baseline_dir(settings, campaign_id) / "authoring_run.json"


def ledger_dir(settings: AppSettings | PathSettings, campaign_id: str) -> Path:
    return campaign_dir(settings, campaign_id) / "ledger"


def projection_dir(settings: AppSettings | PathSettings, campaign_id: str) -> Path:
    return campaign_dir(settings, campaign_id) / "projection"


def idempotency_dir(settings: AppSettings | PathSettings, campaign_id: str) -> Path:
    return campaign_dir(settings, campaign_id) / "idempotency"


def idempotency_entry_path(
    settings: AppSettings | PathSettings, campaign_id: str, entry_filename: str
) -> Path:
    name = entry_filename.strip()
    if (
        not name
        or "/" in name
        or "\\" in name
        or ".." in name
        or not name.startswith("idem_")
        or not name.endswith(".json")
    ):
        from offline_rag.app.gold_lab.errors import GoldLabError

        raise GoldLabError(
            "invalid_idempotency_path",
            f"invalid idempotency filename: {entry_filename!r}",
        )
    return idempotency_dir(settings, campaign_id) / name


def projection_authoring_run_path(
    settings: AppSettings | PathSettings, campaign_id: str
) -> Path:
    return projection_dir(settings, campaign_id) / "authoring_run.json"


def dataset_dir(settings: AppSettings | PathSettings, dataset_id: str) -> Path:
    did = validate_dataset_id(dataset_id)
    return datasets_root(settings) / did


def registration_dir(settings: AppSettings | PathSettings, dataset_id: str) -> Path:
    did = validate_dataset_id(dataset_id)
    return registrations_root(settings) / did


def registration_path(
    settings: AppSettings | PathSettings, dataset_id: str, campaign_id: str
) -> Path:
    did = validate_dataset_id(dataset_id)
    cid = validate_campaign_id(campaign_id)
    return registration_dir(settings, did) / f"{cid}.json"


def canonical_dataset_relpath(dataset_id: str) -> str:
    did = validate_dataset_id(dataset_id)
    return f"datasets/{did}"


def ensure_gold_lab_layout(settings: AppSettings | PathSettings) -> None:
    """Ensure Gold Lab root role directories exist (empty datasets/registrations OK)."""
    for path in (
        gold_lab_root(settings),
        projects_root(settings),
        campaigns_root(settings),
        datasets_root(settings),
        registrations_root(settings),
    ):
        path.mkdir(parents=True, exist_ok=True)
