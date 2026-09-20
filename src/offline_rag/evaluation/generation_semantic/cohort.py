"""Generation cohort-map load/validate (Slice 10B)."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_COHORT_MAP_V1,
    GenerationCohortMapV1,
    LabelCohort,
)
from offline_rag.evaluation.gold import LoadedGoldDataset


class CohortMapError(ValueError):
    """Fail-closed cohort map validation error."""


def load_cohort_map(path: Path) -> GenerationCohortMapV1:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CohortMapError(f"failed to read cohort map: {exc}") from exc
    try:
        return GenerationCohortMapV1.model_validate_json(payload)
    except ValidationError as exc:
        raise CohortMapError(f"invalid cohort map: {exc}") from exc


def validate_cohort_map_for_gold(
    cohort_map: GenerationCohortMapV1,
    gold: LoadedGoldDataset,
) -> dict[str, LabelCohort]:
    if cohort_map.schema_version != GENERATION_COHORT_MAP_V1:
        raise CohortMapError(
            f"unsupported cohort map schema_version: {cohort_map.schema_version}"
        )
    if cohort_map.gold_dataset_id != gold.dataset_id:
        raise CohortMapError(
            "cohort map gold_dataset_id mismatch: "
            f"map={cohort_map.gold_dataset_id} gold={gold.dataset_id}"
        )

    gold_ids = {case.id for case in gold.cases}
    mapping: dict[str, LabelCohort] = {}
    for entry in cohort_map.cases:
        if entry.case_id in mapping:
            raise CohortMapError(f"duplicate case_id in cohort map: {entry.case_id}")
        mapping[entry.case_id] = entry.label_cohort

    missing = sorted(gold_ids - set(mapping))
    if missing:
        raise CohortMapError("cohort map missing case_id(s): " + ", ".join(missing))
    unknown = sorted(set(mapping) - gold_ids)
    if unknown:
        raise CohortMapError("cohort map has unknown case_id(s): " + ", ".join(unknown))
    if len(mapping) != len(gold_ids):
        raise CohortMapError("cohort map case count does not match GoldDataset")
    return mapping
