"""Deterministic authoring configuration hash (``authorcfg_``)."""

from __future__ import annotations

from typing import Any

from offline_rag.config.models import AppSettings, AuthoringSettings
from offline_rag.core.ids import authoring_config_hash
from offline_rag.gold_authoring.contracts import (
    ADAPTER_CONTRACT,
    AUTHORING_ARTIFACT_CONTRACT,
    QUESTION_PROPOSAL_CONTRACT,
    RELEVANCE_PRELABEL_CONTRACT,
)


def build_authoring_semantic_payload(
    settings: AppSettings | AuthoringSettings,
) -> dict[str, Any]:
    auth = settings.authoring if isinstance(settings, AppSettings) else settings
    return {
        "provider": auth.provider,
        "adapter_contract": auth.adapter_contract,
        "model": auth.model,
        "temperature": float(auth.temperature),
        "max_output_tokens": int(auth.max_output_tokens),
        "question_proposal_contract": auth.contracts.question_proposal,
        "relevance_prelabel_contract": auth.contracts.relevance_prelabel,
        "authoring_artifact_contract": auth.contracts.artifact,
    }


def build_authoring_config_hash(settings: AppSettings | AuthoringSettings) -> str:
    return authoring_config_hash(build_authoring_semantic_payload(settings))


def default_contract_ids() -> dict[str, str]:
    return {
        "adapter_contract": ADAPTER_CONTRACT,
        "question_proposal_contract": QUESTION_PROPOSAL_CONTRACT,
        "relevance_prelabel_contract": RELEVANCE_PRELABEL_CONTRACT,
        "authoring_artifact_contract": AUTHORING_ARTIFACT_CONTRACT,
    }
