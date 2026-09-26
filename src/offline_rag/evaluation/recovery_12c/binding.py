"""Gold + adjudication cohort binding for Slice 12C (fail closed)."""

from __future__ import annotations

from pathlib import Path

from offline_rag.evaluation.generation_semantic.cohort import (
    CohortMapError,
    load_cohort_map,
    validate_cohort_map_for_gold,
)
from offline_rag.evaluation.generation_semantic.models import (
    GenerationCohortMapV1,
    LabelCohort,
)
from offline_rag.evaluation.gold import LoadedGoldDataset, load_gold_dataset
from offline_rag.evaluation.recovery_12c.contracts import (
    FROZEN_GOLD_DATASET_ID_12C,
    RecoveryEvalError,
)
from offline_rag.recovery.lineage import RecoveryLineageV1


def bind_cohort_map_for_gold(
    *,
    gold: LoadedGoldDataset,
    cohort_map: GenerationCohortMapV1,
    require_frozen_gold_id: bool = True,
) -> dict[str, LabelCohort]:
    """Validate cohort map against Gold; optionally require frozen 12C Gold ID."""
    if require_frozen_gold_id and gold.dataset_id != FROZEN_GOLD_DATASET_ID_12C:
        raise RecoveryEvalError(
            "12C requires exact frozen Gold dataset ID "
            f"{FROZEN_GOLD_DATASET_ID_12C}; got {gold.dataset_id}"
        )
    try:
        return validate_cohort_map_for_gold(cohort_map, gold)
    except CohortMapError as exc:
        raise RecoveryEvalError(f"cohort map binding failed: {exc}") from exc


def load_and_bind_cohort_map(
    *,
    gold: LoadedGoldDataset,
    cohort_map_path: Path,
    require_frozen_gold_id: bool = True,
) -> tuple[GenerationCohortMapV1, dict[str, LabelCohort]]:
    try:
        cohort_map = load_cohort_map(cohort_map_path)
    except CohortMapError as exc:
        raise RecoveryEvalError(f"failed to load cohort map: {exc}") from exc
    mapping = bind_cohort_map_for_gold(
        gold=gold,
        cohort_map=cohort_map,
        require_frozen_gold_id=require_frozen_gold_id,
    )
    return cohort_map, mapping


def load_frozen_gold_dataset(
    dataset_path: Path,
    *,
    require_frozen_gold_id: bool = True,
) -> LoadedGoldDataset:
    gold = load_gold_dataset(dataset_path)
    if require_frozen_gold_id and gold.dataset_id != FROZEN_GOLD_DATASET_ID_12C:
        raise RecoveryEvalError(
            "12C requires exact frozen Gold dataset ID "
            f"{FROZEN_GOLD_DATASET_ID_12C}; got {gold.dataset_id}"
        )
    return gold


def require_gold_lineage_compatible(
    *,
    gold: LoadedGoldDataset,
    lineage: RecoveryLineageV1,
) -> None:
    """Fail closed unless Gold corpus/chunk-set matches attempt lineage."""
    if gold.meta.chunk_set_id != lineage.chunk_set_id:
        raise RecoveryEvalError(
            "Gold/lineage chunk_set_id mismatch: "
            f"gold={gold.meta.chunk_set_id!r} lineage={lineage.chunk_set_id!r}"
        )
    gold_corpus = gold.meta.corpus_id
    if gold_corpus is not None and gold_corpus != lineage.corpus_id:
        raise RecoveryEvalError(
            "Gold/lineage corpus_id mismatch: "
            f"gold={gold_corpus!r} lineage={lineage.corpus_id!r}"
        )


def cohort_map_identity_payload(cohort_map: GenerationCohortMapV1) -> dict[str, object]:
    """Semantic cohort-map identity (no paths/timestamps)."""
    cases = sorted(
        (
            {"case_id": entry.case_id, "label_cohort": entry.label_cohort}
            for entry in cohort_map.cases
        ),
        key=lambda item: str(item["case_id"]),
    )
    return {
        "schema_version": cohort_map.schema_version,
        "gold_dataset_id": cohort_map.gold_dataset_id,
        "cases": cases,
    }
