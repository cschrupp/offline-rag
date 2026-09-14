"""Historical retrieval-artifact preflight for candidate-pooling-v1."""

from __future__ import annotations

from dataclasses import dataclass

from offline_rag.config.models import AppSettings, DenseQueryTextSettings, DenseSearchableUnitsSettings
from offline_rag.core.ids import (
    EXCLUDE_HEADING_ONLY_V1,
    MODEL_QUERY_PROMPT_V1,
    dense_index_id,
    lexical_index_id,
)
from offline_rag.dense.config_hash import build_index_config_hash
from offline_rag.dense.persistence import try_load_index_manifest
from offline_rag.dense.searchable_units import EXCLUDE_HEADING_ONLY_STRATEGY
from offline_rag.gold_authoring.chunk_access import ChunkAccessError, load_chunk_set_snapshot
from offline_rag.gold_authoring.contracts import (
    POOLING_CONTRACT,
    POOLING_DEPTHS,
    POOLING_RETRIEVER_IDS,
    RETRIEVER_DENSE_ARM_H_V1,
    RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1,
    RETRIEVER_DENSE_PLAIN_V1,
    RETRIEVER_HYBRID_RERANK_V1,
    RETRIEVER_HYBRID_RRF_V1,
    RETRIEVER_LEXICAL_PLAIN_V1,
)
from offline_rag.gold_authoring.models import GoldAuthoringRun
from offline_rag.gold_authoring.pooling_models import PoolingProvenance
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.persistence import try_load_lexical_index_manifest


class PoolPreflightError(RuntimeError):
    """Global preflight failure (CLI exit 2)."""


@dataclass(frozen=True, slots=True)
class ResolvedPoolingArtifacts:
    chunk_set_id: str
    corpus_id: str
    corpus_name: str
    lexical_index_id: str
    dense_baseline_index_id: str
    dense_arm_h_index_id: str
    provenance: PoolingProvenance


def _settings_query_prompt(settings: AppSettings) -> AppSettings:
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


def _settings_arm_h(settings: AppSettings) -> AppSettings:
    qp = _settings_query_prompt(settings)
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


def preflight_pooling_artifacts(
    settings: AppSettings,
    run: GoldAuthoringRun,
) -> ResolvedPoolingArtifacts:
    if run.chunk_set_id is None or not str(run.chunk_set_id).strip():
        raise PoolPreflightError("authoring run missing chunk_set_id")
    if run.corpus_id is None or not str(run.corpus_id).strip():
        raise PoolPreflightError("authoring run missing corpus_id")
    chunk_set_id = str(run.chunk_set_id)
    corpus_id = str(run.corpus_id)
    corpus_name = str(run.corpus_name or "default")

    # Ensure historical ChunkSet exists.
    try:
        load_chunk_set_snapshot(
            settings,
            corpus_name=corpus_name,
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            corpus_manifest_name=None,
        )
    except ChunkAccessError as exc:
        raise PoolPreflightError(str(exc)) from exc

    lex_cfg = build_lexical_config_hash(settings)
    lex_id = lexical_index_id(
        chunk_set_id,
        lex_cfg,
        backend_contract=settings.lexical.backend_contract,
    )
    lex_manifest = try_load_lexical_index_manifest(
        settings.paths.lexical_index_manifests, lex_id
    )
    if lex_manifest is None or lex_manifest.chunk_set_id != chunk_set_id:
        raise PoolPreflightError(
            f"lexical artifact missing/mismatched for chunk_set_id={chunk_set_id}"
        )

    baseline_cfg = build_index_config_hash(settings)
    baseline_id = dense_index_id(chunk_set_id, baseline_cfg)
    baseline_manifest = try_load_index_manifest(settings.paths.index_manifests, baseline_id)
    if baseline_manifest is None or baseline_manifest.chunk_set_id != chunk_set_id:
        raise PoolPreflightError(
            f"dense baseline artifact missing/mismatched for chunk_set_id={chunk_set_id}"
        )

    # Query-prompt reuses baseline passage index (query contract only).
    qp_settings = _settings_query_prompt(settings)
    qp_cfg = build_index_config_hash(qp_settings)
    if qp_cfg != baseline_cfg:
        # Should match when only query_text differs; fail closed if not.
        raise PoolPreflightError(
            "query-prompt dense index identity unexpectedly differs from baseline"
        )

    arm_h_settings = _settings_arm_h(settings)
    arm_h_cfg = build_index_config_hash(arm_h_settings)
    arm_h_id = dense_index_id(chunk_set_id, arm_h_cfg)
    arm_h_manifest = try_load_index_manifest(settings.paths.index_manifests, arm_h_id)
    if arm_h_manifest is None or arm_h_manifest.chunk_set_id != chunk_set_id:
        raise PoolPreflightError(
            f"Arm H dense artifact missing/mismatched for chunk_set_id={chunk_set_id}"
        )

    # Hybrid / hybrid-rerank depend on lexical + baseline dense both matching A.
    # Already validated above.

    artifact_ids = {
        RETRIEVER_LEXICAL_PLAIN_V1: lex_id,
        RETRIEVER_DENSE_PLAIN_V1: baseline_id,
        RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1: baseline_id,
        RETRIEVER_DENSE_ARM_H_V1: arm_h_id,
        RETRIEVER_HYBRID_RRF_V1: f"hybrid({lex_id}+{baseline_id})",
        RETRIEVER_HYBRID_RERANK_V1: f"hybrid-rerank({lex_id}+{baseline_id})",
    }
    provenance = PoolingProvenance(
        pooling_contract=POOLING_CONTRACT,
        source_chunk_set_id=chunk_set_id,
        retrievers=list(POOLING_RETRIEVER_IDS),
        retrieval_depths=dict(POOLING_DEPTHS),
        artifact_ids=artifact_ids,
    )
    return ResolvedPoolingArtifacts(
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
        corpus_name=corpus_name,
        lexical_index_id=lex_id,
        dense_baseline_index_id=baseline_id,
        dense_arm_h_index_id=arm_h_id,
        provenance=provenance,
    )
