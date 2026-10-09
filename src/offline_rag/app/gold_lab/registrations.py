"""Immutable Gold Lab registration persistence and contribution bridge (16F-C)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import (
    REGISTRATION_SCHEMA,
    validate_campaign_id,
    validate_dataset_id,
)
from offline_rag.app.gold_lab.models import (
    GoldCampaign,
    GoldProject,
    GoldRegistration,
)
from offline_rag.app.gold_lab.paths import (
    canonical_dataset_relpath,
    dataset_dir,
    registration_path,
    registrations_root,
)
from offline_rag.config.models import AppSettings
from offline_rag.evaluation.gold import GOLD_SCHEMA_V1, load_gold_dataset
from offline_rag.ingestion.io import atomic_write_text


def build_registration(
    *,
    campaign: GoldCampaign,
    project: GoldProject,
    dataset_id: str,
    projection_sha256: str,
    exported_case_ids: list[str],
    registered_at: datetime | None = None,
) -> GoldRegistration:
    """Derive registration provenance from trusted campaign/project state."""
    did = validate_dataset_id(dataset_id)
    if project.project_id != campaign.project_id:
        raise GoldLabError(
            "registration_project_mismatch",
            "project.project_id must equal campaign.project_id",
        )
    return GoldRegistration(
        schema_version=REGISTRATION_SCHEMA,
        dataset_id=did,
        project_id=campaign.project_id,
        campaign_id=campaign.campaign_id,
        project_type=project.project_type,
        workspace_id=campaign.workspace_id,
        snapshot_id=campaign.snapshot_id,
        chunk_set_id=campaign.chunk_set_id,
        corpus_id=campaign.corpus_id,
        corpus_name=campaign.corpus_name,
        baseline_authoring_run_id=campaign.baseline_authoring_run_id,
        baseline_sha256=campaign.baseline_sha256,
        projection_sha256=projection_sha256.strip().lower(),
        selection_policy_id=campaign.selection_policy.selection_policy_id,
        selection_policy_fingerprint=(
            campaign.selection_policy.selection_policy_fingerprint
        ),
        dataset_path=canonical_dataset_relpath(did),
        exported_case_ids=sorted(set(exported_case_ids)),
        registered_at=registered_at or datetime.now(tz=UTC),
    )


def _immutable_registration_fields(reg: GoldRegistration) -> dict[str, Any]:
    payload = reg.model_dump(mode="json")
    payload.pop("registered_at", None)
    return payload


def validate_registration_against_authority(
    settings: AppSettings,
    registration: GoldRegistration,
    *,
    campaign: GoldCampaign,
    project: GoldProject,
) -> None:
    """Fail-closed validation of an existing registration vs durable authority."""
    if registration.schema_version != REGISTRATION_SCHEMA:
        raise GoldLabError(
            "registration_schema_invalid",
            f"expected {REGISTRATION_SCHEMA}",
        )
    if registration.campaign_id != campaign.campaign_id:
        raise GoldLabError(
            "registration_campaign_mismatch",
            "registration.campaign_id mismatch",
        )
    if registration.dataset_id != validate_dataset_id(registration.dataset_id):
        raise GoldLabError("invalid_dataset_id", "registration dataset_id invalid")

    path = registration_path(
        settings, registration.dataset_id, registration.campaign_id
    )
    # Path IDs are already validated by helpers; ensure consistency with contents.
    if path.name != f"{registration.campaign_id}.json":
        raise GoldLabError(
            "registration_path_mismatch",
            "registration path campaign_id mismatch",
        )
    if path.parent.name != registration.dataset_id:
        raise GoldLabError(
            "registration_path_mismatch",
            "registration path dataset_id mismatch",
        )

    expected = build_registration(
        campaign=campaign,
        project=project,
        dataset_id=registration.dataset_id,
        projection_sha256=registration.projection_sha256,
        exported_case_ids=list(registration.exported_case_ids),
        registered_at=registration.registered_at,
    )
    # Provenance from campaign/project must match stored (except we rebuild
    # projection/exported from the stored registration for this check's shape).
    checks = (
        ("project_id", expected.project_id, registration.project_id),
        ("project_type", expected.project_type, registration.project_type),
        ("workspace_id", expected.workspace_id, registration.workspace_id),
        ("snapshot_id", expected.snapshot_id, registration.snapshot_id),
        ("chunk_set_id", expected.chunk_set_id, registration.chunk_set_id),
        ("corpus_id", expected.corpus_id, registration.corpus_id),
        ("corpus_name", expected.corpus_name, registration.corpus_name),
        (
            "baseline_authoring_run_id",
            expected.baseline_authoring_run_id,
            registration.baseline_authoring_run_id,
        ),
        ("baseline_sha256", expected.baseline_sha256, registration.baseline_sha256),
        (
            "selection_policy_id",
            expected.selection_policy_id,
            registration.selection_policy_id,
        ),
        (
            "selection_policy_fingerprint",
            expected.selection_policy_fingerprint,
            registration.selection_policy_fingerprint,
        ),
        ("dataset_path", expected.dataset_path, registration.dataset_path),
    )
    for name, want, got in checks:
        if want != got:
            raise GoldLabError(
                "registration_provenance_mismatch",
                f"registration {name} does not match campaign/project authority",
            )

    canonical = dataset_dir(settings, registration.dataset_id)
    if not canonical.is_dir():
        raise GoldLabError(
            "registration_dataset_missing",
            f"canonical dataset missing for {registration.dataset_id}",
        )
    try:
        loaded = load_gold_dataset(canonical)
    except Exception as exc:
        raise GoldLabError(
            "registration_dataset_corrupt",
            f"canonical dataset unreadable: {exc}",
        ) from exc
    if loaded.source_schema != GOLD_SCHEMA_V1:
        raise GoldLabError(
            "registration_dataset_schema_invalid",
            f"expected {GOLD_SCHEMA_V1}",
        )
    if loaded.dataset_id != registration.dataset_id:
        raise GoldLabError(
            "registration_dataset_id_mismatch",
            "loaded dataset_id does not match registration",
        )
    loaded_ids = sorted({case.id for case in loaded.cases})
    if loaded_ids != list(registration.exported_case_ids):
        raise GoldLabError(
            "registration_exported_ids_mismatch",
            "exported_case_ids do not match loaded GoldDataset cases",
        )


def create_or_reuse_registration(
    settings: AppSettings,
    *,
    campaign: GoldCampaign,
    project: GoldProject,
    dataset_id: str,
    projection_sha256: str,
    exported_case_ids: list[str],
    baseline_case_ids: set[str],
) -> tuple[GoldRegistration, bool]:
    """Create first registration or return equivalent existing (idempotent).

    Returns ``(registration, replayed)``.
    """
    did = validate_dataset_id(dataset_id)
    cid = validate_campaign_id(campaign.campaign_id)
    if set(exported_case_ids) - baseline_case_ids:
        raise GoldLabError(
            "registration_unknown_exported_case",
            "exported_case_ids must be subset of campaign baseline",
        )

    expected = build_registration(
        campaign=campaign,
        project=project,
        dataset_id=did,
        projection_sha256=projection_sha256,
        exported_case_ids=exported_case_ids,
    )
    validate_registration_against_authority(
        settings, expected, campaign=campaign, project=project
    )

    path = registration_path(settings, did, cid)
    if path.is_file():
        try:
            existing = GoldRegistration.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise GoldLabError(
                "registration_corrupt",
                f"unreadable registration: {exc}",
            ) from exc
        if existing.dataset_id != did or existing.campaign_id != cid:
            raise GoldLabError(
                "registration_path_mismatch",
                "stored registration IDs do not match path",
            )
        validate_registration_against_authority(
            settings, existing, campaign=campaign, project=project
        )
        # Rebuild expected with existing projection/exported for immutable compare;
        # current operation must match stored immutable fields.
        current = build_registration(
            campaign=campaign,
            project=project,
            dataset_id=did,
            projection_sha256=projection_sha256,
            exported_case_ids=exported_case_ids,
            registered_at=existing.registered_at,
        )
        if _immutable_registration_fields(current) != _immutable_registration_fields(
            existing
        ):
            raise GoldLabError(
                "registration_conflict",
                "existing registration conflicts with current export",
            )
        return existing, True

    # First publication — dataset must already be canonical and valid.
    validate_registration_against_authority(
        settings, expected, campaign=campaign, project=project
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, expected.model_dump_json())
    # Re-load and validate path/bytes.
    written = GoldRegistration.model_validate_json(path.read_text(encoding="utf-8"))
    if written.dataset_id != did or written.campaign_id != cid:
        raise GoldLabError(
            "registration_path_mismatch",
            "written registration IDs do not match path",
        )
    validate_registration_against_authority(
        settings, written, campaign=campaign, project=project
    )
    return written, False


def load_registration(
    settings: AppSettings, *, dataset_id: str, campaign_id: str
) -> GoldRegistration:
    did = validate_dataset_id(dataset_id)
    cid = validate_campaign_id(campaign_id)
    path = registration_path(settings, did, cid)
    if not path.is_file():
        raise GoldLabError(
            "registration_missing",
            f"registration not found for {did}/{cid}",
        )
    try:
        return GoldRegistration.model_validate_json(path.read_text(encoding="utf-8"))
    except GoldLabError:
        raise
    except Exception as exc:
        raise GoldLabError(
            "registration_corrupt",
            f"unreadable registration: {exc}",
        ) from exc


def iter_registration_paths_for_campaign(
    settings: AppSettings, campaign_id: str
) -> list[Path]:
    cid = validate_campaign_id(campaign_id)
    root = registrations_root(settings)
    if not root.is_dir():
        return []
    matches: list[Path] = []
    for path in sorted(root.glob(f"*/{cid}.json")):
        if path.is_file():
            matches.append(path)
    return matches


def valid_registered_case_ids_for_campaign(
    settings: AppSettings,
    *,
    campaign_id: str,
    campaign: GoldCampaign,
    project: GoldProject,
) -> tuple[str, ...]:
    """Unique union of exported_case_ids across all valid registrations.

    Malformed or provenance-mismatched registrations fail closed.
    """
    cid = validate_campaign_id(campaign_id)
    if campaign.campaign_id != cid:
        raise GoldLabError(
            "registration_campaign_mismatch",
            "campaign_id argument does not match campaign artifact",
        )
    union: set[str] = set()
    for path in iter_registration_paths_for_campaign(settings, cid):
        try:
            registration = GoldRegistration.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise GoldLabError(
                "registration_corrupt",
                f"unreadable registration {path}: {exc}",
            ) from exc
        if path.parent.name != registration.dataset_id:
            raise GoldLabError(
                "registration_path_mismatch",
                "registration path dataset_id mismatch",
            )
        if path.name != f"{registration.campaign_id}.json":
            raise GoldLabError(
                "registration_path_mismatch",
                "registration path campaign_id mismatch",
            )
        if registration.campaign_id != cid:
            raise GoldLabError(
                "registration_campaign_mismatch",
                "registration campaign_id mismatch",
            )
        validate_registration_against_authority(
            settings, registration, campaign=campaign, project=project
        )
        union.update(registration.exported_case_ids)
    return tuple(sorted(union))
