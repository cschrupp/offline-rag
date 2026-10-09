"""Canonical GoldDataset-v1 publication and semantic-equivalent reuse (16F-C)."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import validate_campaign_id, validate_dataset_id
from offline_rag.app.gold_lab.paths import dataset_dir, datasets_root
from offline_rag.config.models import AppSettings
from offline_rag.evaluation.gold import GOLD_SCHEMA_V1, load_gold_dataset
from offline_rag.gold_authoring.finalize import FinalizePreRunError, run_gold_finalize
from offline_rag.gold_authoring.models import GoldAuthoringRun


def candidate_dataset_dir(
    settings: AppSettings, *, campaign_id: str, token: str | None = None
) -> Path:
    """Private non-authoritative staging directory under datasets/."""
    cid = validate_campaign_id(campaign_id)
    suffix = token or uuid.uuid4().hex
    return datasets_root(settings) / f".candidate.{cid}.{suffix}"


def finalize_projected_run_to_candidate(
    settings: AppSettings,
    *,
    projected_run: GoldAuthoringRun,
    projection_path: Path,
    campaign_id: str,
) -> tuple[Path, str, list[str]]:
    """Finalize validated projection into a unique candidate dataset directory.

    Returns ``(candidate_dir, dataset_id, exported_case_ids)``.
    """
    cid = validate_campaign_id(campaign_id)
    # Ensure projection bytes on disk match the in-memory validated run.
    on_disk = GoldAuthoringRun.model_validate_json(
        projection_path.read_bytes().decode("utf-8")
    )
    if on_disk.model_dump_json() != projected_run.model_dump_json():
        raise GoldLabError(
            "projection_export_mismatch",
            "projection artifact does not match export input run",
        )

    candidate = candidate_dataset_dir(settings, campaign_id=cid)
    try:
        result = run_gold_finalize(
            settings,
            run_path=projection_path,
            output=candidate,
            force=False,
        )
    except FinalizePreRunError as exc:
        _cleanup_dir(candidate)
        raise GoldLabError("gold_finalize_failed", str(exc)) from exc
    except Exception as exc:
        _cleanup_dir(candidate)
        raise GoldLabError(
            "gold_finalize_failed",
            f"GoldDataset finalization failed: {exc}",
        ) from exc

    if result.dataset_id is None or result.output_path is None:
        _cleanup_dir(candidate)
        raise GoldLabError(
            "gold_finalize_failed",
            "finalize returned incomplete result",
        )

    dataset_id = validate_dataset_id(result.dataset_id)
    try:
        loaded = load_gold_dataset(candidate)
    except Exception as exc:
        _cleanup_dir(candidate)
        raise GoldLabError(
            "candidate_dataset_invalid",
            f"candidate failed load_gold_dataset: {exc}",
        ) from exc

    if loaded.source_schema != GOLD_SCHEMA_V1:
        _cleanup_dir(candidate)
        raise GoldLabError(
            "candidate_schema_invalid",
            f"expected {GOLD_SCHEMA_V1}, got {loaded.source_schema}",
        )
    if loaded.dataset_id != dataset_id:
        _cleanup_dir(candidate)
        raise GoldLabError(
            "candidate_dataset_id_mismatch",
            "candidate dataset_id does not match finalize result",
        )

    exported = sorted({case.id for case in loaded.cases})
    if set(exported) != set(result.exported_case_ids):
        _cleanup_dir(candidate)
        raise GoldLabError(
            "candidate_exported_ids_mismatch",
            "finalize exported_case_ids do not match loaded dataset",
        )
    return candidate, dataset_id, exported


def publish_or_reuse_canonical_dataset(
    settings: AppSettings,
    *,
    dataset_id: str,
    candidate_dir: Path,
) -> tuple[Path, bool]:
    """Promote candidate or reuse existing same-semantic canonical dataset.

    Must be called while holding ``GoldLabDatasetLease(dataset_id)``.

    Returns ``(canonical_dir, reused)``.
    """
    did = validate_dataset_id(dataset_id)
    canonical = dataset_dir(settings, did)
    candidate = Path(candidate_dir)

    if not candidate.is_dir():
        raise GoldLabError(
            "candidate_staging_missing",
            f"candidate directory missing: {candidate}",
        )

    try:
        candidate_ds = load_gold_dataset(candidate)
    except Exception as exc:
        raise GoldLabError(
            "candidate_dataset_invalid",
            f"candidate failed load_gold_dataset: {exc}",
        ) from exc

    if candidate_ds.source_schema != GOLD_SCHEMA_V1:
        raise GoldLabError(
            "candidate_schema_invalid",
            f"expected {GOLD_SCHEMA_V1}",
        )
    if candidate_ds.dataset_id != did:
        raise GoldLabError(
            "candidate_dataset_id_mismatch",
            "candidate dataset_id mismatch",
        )

    if not canonical.exists():
        try:
            os.replace(candidate, canonical)
        except OSError as exc:
            raise GoldLabError(
                "dataset_publish_failed",
                f"failed to promote candidate dataset: {exc}",
            ) from exc
        try:
            published = load_gold_dataset(canonical)
        except Exception as exc:
            raise GoldLabError(
                "canonical_dataset_invalid",
                f"published dataset failed validation: {exc}",
            ) from exc
        if published.dataset_id != did or published.source_schema != GOLD_SCHEMA_V1:
            raise GoldLabError(
                "canonical_dataset_invalid",
                "published dataset identity/schema mismatch",
            )
        return canonical, False

    # Reuse path — never rewrite bytes.
    try:
        existing = load_gold_dataset(canonical)
    except Exception as exc:
        raise GoldLabError(
            "canonical_dataset_corrupt",
            f"existing canonical dataset unreadable: {exc}",
        ) from exc

    if existing.source_schema != GOLD_SCHEMA_V1:
        raise GoldLabError(
            "canonical_dataset_schema_invalid",
            f"expected {GOLD_SCHEMA_V1}",
        )
    if existing.dataset_id != did:
        raise GoldLabError(
            "canonical_dataset_id_mismatch",
            "canonical path dataset_id mismatch",
        )
    if candidate_ds.dataset_id != existing.dataset_id:
        raise GoldLabError(
            "dataset_semantic_conflict",
            "candidate and canonical dataset_id differ",
        )

    # Semantic identity is the dataset_id; differing meta.metadata is allowed.
    _cleanup_dir(candidate)
    return canonical, True


def _cleanup_dir(path: Path | None) -> None:
    if path is not None and path.exists():
        shutil.rmtree(path, ignore_errors=True)
