"""Campaign-local durable idempotency catalog (16F-B)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import (
    IDEMPOTENCY_SCHEMA,
    validate_campaign_id,
    validate_judgment_id,
    validate_record_id,
    validate_request_fingerprint,
)
from offline_rag.app.gold_lab.models import (
    GoldLedgerRecord,
    IdempotencyCommandKind,
    IdempotencyEntry,
    IdempotencyStatus,
)
from offline_rag.app.gold_lab.paths import idempotency_dir, idempotency_entry_path
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

_MAX_KEY_LEN = 256


def normalize_idempotency_key(raw: str) -> str:
    if not isinstance(raw, str):
        raise GoldLabError(
            "idempotency_key_invalid",
            "idempotency_key must be a string",
        )
    key = raw.strip()
    if not key or len(key) > _MAX_KEY_LEN:
        raise GoldLabError(
            "idempotency_key_invalid",
            "idempotency_key must be length 1..256 after trim",
        )
    return key


def idempotency_entry_filename(normalized_key: str) -> str:
    digest = hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()
    return f"idem_{digest}.json"


class GoldLabIdempotencyCatalog:
    """Durable pending/committed reservation catalog under campaign lease."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def entry_path(self, campaign_id: str, normalized_key: str):
        cid = validate_campaign_id(campaign_id)
        return idempotency_entry_path(
            self.settings, cid, idempotency_entry_filename(normalized_key)
        )

    def load_entry(
        self, campaign_id: str, normalized_key: str
    ) -> IdempotencyEntry | None:
        path = self.entry_path(campaign_id, normalized_key)
        if not path.exists():
            return None
        try:
            entry = IdempotencyEntry.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except GoldLabError:
            raise
        except Exception as exc:
            raise GoldLabError(
                "idempotency_catalog_corrupt",
                f"malformed idempotency catalog entry: {path.name}",
            ) from exc
        if entry.schema_version != IDEMPOTENCY_SCHEMA:
            raise GoldLabError(
                "idempotency_schema_invalid",
                f"expected {IDEMPOTENCY_SCHEMA}",
            )
        if entry.campaign_id != validate_campaign_id(campaign_id):
            raise GoldLabError(
                "idempotency_campaign_mismatch",
                "catalog campaign_id mismatch",
            )
        if entry.idempotency_key != normalized_key:
            raise GoldLabError(
                "idempotency_key_mismatch",
                "catalog key disagrees with lookup key",
            )
        validate_request_fingerprint(entry.request_fingerprint)
        validate_record_id(entry.record_id)
        validate_judgment_id(entry.judgment_id)
        return entry

    def write_pending(
        self,
        *,
        campaign_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        command_kind: str,
        record_id: str,
        judgment_id: str,
        created_at: datetime | None = None,
    ) -> IdempotencyEntry:
        cid = validate_campaign_id(campaign_id)
        key = normalize_idempotency_key(idempotency_key)
        validate_request_fingerprint(request_fingerprint)
        rid = validate_record_id(record_id)
        jid = validate_judgment_id(judgment_id)
        try:
            kind = IdempotencyCommandKind(command_kind)
        except Exception as exc:
            raise GoldLabError(
                "idempotency_command_kind_invalid",
                f"unsupported command_kind: {command_kind!r}",
            ) from exc
        entry = IdempotencyEntry(
            campaign_id=cid,
            idempotency_key=key,
            request_fingerprint=request_fingerprint,
            command_kind=kind,
            status=IdempotencyStatus.PENDING,
            record_id=rid,
            judgment_id=jid,
            created_at=created_at or datetime.now(tz=UTC),
            committed_at=None,
        )
        path = self.entry_path(cid, key)
        if path.exists():
            raise GoldLabError(
                "idempotency_reservation_exists",
                "idempotency reservation already exists",
            )
        idempotency_dir(self.settings, cid).mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, entry.model_dump_json())
        return entry

    def mark_committed(
        self,
        *,
        campaign_id: str,
        idempotency_key: str,
        committed_at: datetime | None = None,
    ) -> IdempotencyEntry:
        key = normalize_idempotency_key(idempotency_key)
        entry = self.load_entry(campaign_id, key)
        if entry is None:
            raise GoldLabError(
                "idempotency_entry_missing",
                "cannot commit missing idempotency reservation",
            )
        if entry.status is IdempotencyStatus.COMMITTED:
            return entry
        updated = entry.model_copy(
            update={
                "status": IdempotencyStatus.COMMITTED,
                "committed_at": committed_at or datetime.now(tz=UTC),
            }
        )
        path = self.entry_path(campaign_id, key)
        atomic_write_text(path, updated.model_dump_json())
        return updated

    def assert_no_orphan_ledger_key(
        self,
        *,
        campaign_id: str,
        normalized_key: str,
        records: list[GoldLedgerRecord],
    ) -> None:
        """Fail closed if ledger already uses key without a matching catalog entry."""
        matching = [r for r in records if r.idempotency_key == normalized_key]
        if not matching:
            return
        entry = self.load_entry(campaign_id, normalized_key)
        if entry is None:
            raise GoldLabError(
                "idempotency_orphan_ledger_key",
                "ledger uses idempotency key without catalog entry",
            )
        if len(matching) > 1:
            raise GoldLabError(
                "idempotency_duplicate_ledger_key",
                "multiple ledger rows claim the same idempotency key",
            )

    def find_reserved_record(
        self,
        *,
        entry: IdempotencyEntry,
        records: list[GoldLedgerRecord],
    ) -> GoldLedgerRecord | None:
        matches = [r for r in records if r.record_id == entry.record_id]
        if not matches:
            return None
        if len(matches) != 1:
            raise GoldLabError(
                "idempotency_duplicate_record_id",
                "multiple ledger rows share reserved record_id",
            )
        record = matches[0]
        if record.judgment_id != entry.judgment_id:
            raise GoldLabError(
                "idempotency_reserved_id_mismatch",
                "ledger record judgment_id disagrees with reservation",
            )
        if record.idempotency_key != entry.idempotency_key:
            raise GoldLabError(
                "idempotency_reserved_key_mismatch",
                "ledger record idempotency_key disagrees with reservation",
            )
        if record.request_fingerprint != entry.request_fingerprint:
            raise GoldLabError(
                "idempotency_reserved_fingerprint_mismatch",
                "ledger request_fingerprint disagrees with reservation",
            )
        if record.record_type.value != entry.command_kind.value:
            raise GoldLabError(
                "idempotency_command_kind_mismatch",
                "ledger record_type disagrees with catalog command_kind",
            )
        return record

    def validate_committed_against_ledger(
        self,
        *,
        entry: IdempotencyEntry,
        records: list[GoldLedgerRecord],
    ) -> GoldLedgerRecord:
        if entry.status is not IdempotencyStatus.COMMITTED:
            raise GoldLabError(
                "idempotency_status_invalid",
                "expected COMMITTED catalog entry",
            )
        record = self.find_reserved_record(entry=entry, records=records)
        if record is None:
            raise GoldLabError(
                "idempotency_committed_missing_ledger",
                "COMMITTED catalog references missing ledger record",
            )
        return record

    @staticmethod
    def require_command_kind(
        entry: IdempotencyEntry, command_kind: str | IdempotencyCommandKind
    ) -> None:
        expected = IdempotencyCommandKind(command_kind)
        if entry.command_kind is not expected:
            raise GoldLabError(
                "idempotency_command_kind_mismatch",
                "catalog command_kind disagrees with invoked command",
            )
