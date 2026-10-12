"""Canonical candidate-pooling-v1 Arm-H settings and index identity (pure)."""

from __future__ import annotations

from dataclasses import dataclass

from offline_rag.config.models import (
    AppSettings,
    DenseQueryTextSettings,
    DenseSearchableUnitsSettings,
)
from offline_rag.core.ids import (
    EXCLUDE_HEADING_ONLY_V1,
    MODEL_QUERY_PROMPT_V1,
    dense_collection_name,
    dense_index_id,
)
from offline_rag.dense.config_hash import build_index_config_hash
from offline_rag.dense.searchable_units import EXCLUDE_HEADING_ONLY_STRATEGY


def settings_query_prompt(settings: AppSettings) -> AppSettings:
    """Apply model-query-prompt query contract (query-side only)."""
    return settings.model_copy(
        update={
            "dense": settings.dense.model_copy(
                update={
                    "query_text": DenseQueryTextSettings(
                        strategy="model_query_prompt",
                        contract_version=MODEL_QUERY_PROMPT_V1,
                    )
                }
            )
        }
    )


def settings_arm_h(settings: AppSettings) -> AppSettings:
    """Canonical Arm-H settings: query-prompt + exclude_heading_only searchable units."""
    qp = settings_query_prompt(settings)
    return qp.model_copy(
        update={
            "indexing": qp.indexing.model_copy(
                update={
                    "searchable_units": DenseSearchableUnitsSettings(
                        strategy=EXCLUDE_HEADING_ONLY_STRATEGY,
                        contract_version=EXCLUDE_HEADING_ONLY_V1,
                    )
                }
            )
        }
    )


@dataclass(frozen=True, slots=True)
class ArmHIndexIdentity:
    settings: AppSettings
    index_config_hash: str
    index_id: str
    collection_name: str


def arm_h_index_identity(settings: AppSettings, *, chunk_set_id: str) -> ArmHIndexIdentity:
    """Derive the immutable Arm-H dense index identity for an exact chunk_set_id."""
    arm_settings = settings_arm_h(settings)
    cfg = build_index_config_hash(arm_settings)
    index_id = dense_index_id(chunk_set_id, cfg)
    return ArmHIndexIdentity(
        settings=arm_settings,
        index_config_hash=cfg,
        index_id=index_id,
        collection_name=dense_collection_name(index_id),
    )
