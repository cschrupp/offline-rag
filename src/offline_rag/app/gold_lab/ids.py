"""Frozen Gold Lab identity helpers (16F-A / Rework 1)."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from typing import Any

from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.gold_authoring.review_models import canonicalize_query

ABSOLUTE_RELEVANCE_CONTRACT = "gold-absolute-relevance-v1"
QUESTION_CHECK_CONTRACT = "gold-question-check-v1"
AUXILIARY_PREFERENCE_CONTRACT = "gold-auxiliary-preference-v1"
HARD_CALL_DESIGNATION_CONTRACT = "gold-hard-call-designation-v1"
LEDGER_SCHEMA = "offline-rag-gold-lab-ledger-v1"
HARD_CALLS_SCHEMA = "offline-rag-gold-hard-calls-v1"
SELECTION_POLICY_CONTRACT = "gold-selection-policy-v1"
IDEMPOTENCY_SCHEMA = "offline-rag-gold-idempotency-v1"
CONTRIBUTION_CONTRACT = "gold-contribution-v1"
REGISTRATION_SCHEMA = "offline-rag-gold-registration-v1"

_DATASET_ID_RE = re.compile(r"^gold_[0-9a-f]{64}$")

_PROJECT_ID_RE = re.compile(r"^goldproj_[0-9a-f]{32}$")
_CAMPAIGN_ID_RE = re.compile(r"^goldcamp_[0-9a-f]{32}$")
_RECORD_ID_RE = re.compile(r"^goldrec_[0-9a-f]{32}$")
_JUDGMENT_ID_RE = re.compile(r"^goldjud_[0-9a-f]{32}$")
_TASK_ID_RE = re.compile(r"^goldtask_[0-9a-f]{64}$")
_QUERY_FP_RE = re.compile(r"^goldquery_[0-9a-f]{64}$")
_HARD_CALL_ID_RE = re.compile(r"^goldhard_[0-9a-f]{64}$")
_REQFP_RE = re.compile(r"^reqfp_[0-9a-f]{64}$")
_CFG_FP_RE = re.compile(r"^cfg_[0-9a-f]{64}$")


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


def _require_match(pattern: re.Pattern[str], value: str, *, reason: str, label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise GoldLabError(reason, f"invalid {label}: {value!r}")
    return value


def validate_project_id(value: str) -> str:
    return _require_match(
        _PROJECT_ID_RE, value, reason="invalid_project_id", label="project_id"
    )


def validate_campaign_id(value: str) -> str:
    return _require_match(
        _CAMPAIGN_ID_RE, value, reason="invalid_campaign_id", label="campaign_id"
    )


def validate_record_id(value: str) -> str:
    return _require_match(
        _RECORD_ID_RE, value, reason="invalid_record_id", label="record_id"
    )


def validate_judgment_id(value: str) -> str:
    return _require_match(
        _JUDGMENT_ID_RE, value, reason="invalid_judgment_id", label="judgment_id"
    )


def validate_task_id(value: str) -> str:
    return _require_match(
        _TASK_ID_RE, value, reason="invalid_task_id", label="task_id"
    )


def validate_query_fingerprint(value: str) -> str:
    return _require_match(
        _QUERY_FP_RE,
        value,
        reason="invalid_query_fingerprint",
        label="query_fingerprint",
    )


def validate_hard_call_designation_id(value: str) -> str:
    return _require_match(
        _HARD_CALL_ID_RE,
        value,
        reason="invalid_hard_call_designation_id",
        label="designation_id",
    )


def validate_request_fingerprint(value: str) -> str:
    return _require_match(
        _REQFP_RE,
        value,
        reason="invalid_request_fingerprint",
        label="request_fingerprint",
    )


def validate_selection_policy_fingerprint(value: str) -> str:
    return _require_match(
        _CFG_FP_RE,
        value,
        reason="invalid_selection_policy_fingerprint",
        label="selection_policy_fingerprint",
    )


def validate_dataset_id(value: str) -> str:
    return _require_match(
        _DATASET_ID_RE,
        value,
        reason="invalid_dataset_id",
        label="dataset_id",
    )


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
