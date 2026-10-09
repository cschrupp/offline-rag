"""Frozen Gold Lab identity helpers (16F-A)."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any

from offline_rag.gold_authoring.review_models import canonicalize_query

ABSOLUTE_RELEVANCE_CONTRACT = "gold-absolute-relevance-v1"
QUESTION_CHECK_CONTRACT = "gold-question-check-v1"
AUXILIARY_PREFERENCE_CONTRACT = "gold-auxiliary-preference-v1"
HARD_CALL_DESIGNATION_CONTRACT = "gold-hard-call-designation-v1"
LEDGER_SCHEMA = "offline-rag-gold-lab-ledger-v1"
HARD_CALLS_SCHEMA = "offline-rag-gold-hard-calls-v1"
SELECTION_POLICY_CONTRACT = "gold-selection-policy-v1"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return encoded.encode("utf-8")


def _uuid4_hex() -> str:
    return uuid.uuid4().hex


def new_project_id() -> str:
    return f"goldproj_{_uuid4_hex()}"


def new_campaign_id() -> str:
    return f"goldcamp_{_uuid4_hex()}"


def new_ledger_record_id() -> str:
    return f"goldrec_{_uuid4_hex()}"


def new_judgment_id() -> str:
    return f"goldjud_{_uuid4_hex()}"


def absolute_relevance_task_id(
    *,
    campaign_id: str,
    case_id: str,
    candidate_chunk_id: str,
) -> str:
    payload = {
        "campaign_id": campaign_id,
        "task_kind": "absolute_relevance",
        "case_id": case_id,
        "candidate_chunk_id": candidate_chunk_id,
        "semantic_contract": ABSOLUTE_RELEVANCE_CONTRACT,
    }
    return f"goldtask_{_sha256_hex(_canonical_json_bytes(payload))}"


def question_check_task_id(*, campaign_id: str, case_id: str) -> str:
    payload = {
        "campaign_id": campaign_id,
        "task_kind": "question_check",
        "case_id": case_id,
        "semantic_contract": QUESTION_CHECK_CONTRACT,
    }
    return f"goldtask_{_sha256_hex(_canonical_json_bytes(payload))}"


def auxiliary_preference_task_id(
    *,
    campaign_id: str,
    case_id: str,
    candidate_a: str,
    candidate_b: str,
) -> str:
    pair = sorted([candidate_a, candidate_b])
    payload = {
        "campaign_id": campaign_id,
        "task_kind": "auxiliary_preference",
        "case_id": case_id,
        "candidate_pair": pair,
        "semantic_contract": AUXILIARY_PREFERENCE_CONTRACT,
    }
    return f"goldtask_{_sha256_hex(_canonical_json_bytes(payload))}"


def query_fingerprint(query: str) -> str:
    canonical = canonicalize_query(query)
    return f"goldquery_{_sha256_hex(canonical.encode('utf-8'))}"


def hard_call_designation_id(*, campaign_id: str, target_task_id: str) -> str:
    payload = {
        "campaign_id": campaign_id,
        "target_task_id": target_task_id,
        "designation_contract": HARD_CALL_DESIGNATION_CONTRACT,
    }
    return f"goldhard_{_sha256_hex(_canonical_json_bytes(payload))}"
