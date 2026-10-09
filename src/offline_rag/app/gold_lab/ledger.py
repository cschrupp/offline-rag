"""Append-only Gold Lab ledger primitive (not a product mutation service)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.app.gold_lab.baseline import (
    load_sealed_baseline_run,
    resolve_ledger_task_id,
)
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import (
    ABSOLUTE_RELEVANCE_CONTRACT,
    AUXILIARY_PREFERENCE_CONTRACT,
    QUESTION_CHECK_CONTRACT,
    new_judgment_id,
    new_ledger_record_id,
    validate_campaign_id,
    validate_judgment_id,
    validate_record_id,
    validate_request_fingerprint,
    validate_selection_policy_fingerprint,
    validate_task_id,
)
from offline_rag.app.gold_lab.leases import GoldLabCampaignLease
from offline_rag.app.gold_lab.models import (
    GoldCampaign,
    GoldCampaignStatus,
    GoldLedgerRecord,
    GoldLedgerRecordType,
    GoldProjectStatus,
)
from offline_rag.app.gold_lab.paths import campaign_dir, ledger_dir
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

_LEDGER_FILENAME = re.compile(
    r"^(?P<seq>\d{12})_(?P<record_id>goldrec_[0-9a-f]{32})\.json$"
)
_TEMP_SUFFIXES = (".tmp", ".partial", ".staging")


def ledger_record_filename(*, sequence: int, record_id: str) -> str:
    validate_record_id(record_id)
    return f"{sequence:012d}_{record_id}.json"


class GoldLabLedger:
    """Low-level append-only ledger storage for one campaign."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        store: GoldLabStore | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or GoldLabStore(settings)

    def append(
        self,
        campaign_id: str,
        *,
        record_type: GoldLedgerRecordType | str,
        case_id: str,
        payload: dict,
        idempotency_key: str,
        request_fingerprint: str,
        query_fingerprint: str | None = None,
        candidate_chunk_id: str | None = None,
        game_id: str | None = None,
        presentation_id: str | None = None,
        supersedes_judgment_id: str | None = None,
        task_id: str | None = None,
        judgment_id: str | None = None,
        record_id: str | None = None,
        created_at: object | None = None,
        preferred_chunk_id: str | None = None,
        other_chunk_id: str | None = None,
    ) -> GoldLedgerRecord:
        """Append exactly one immutable ledger record under campaign lease."""
        cid = validate_campaign_id(campaign_id)
        rtype = GoldLedgerRecordType(record_type)
        validate_request_fingerprint(request_fingerprint)

        with GoldLabCampaignLease(self.settings, cid):
            campaign = self.store.get_campaign(cid)
            project = self.store.get_project(campaign.project_id)
            if project.status is GoldProjectStatus.ARCHIVED:
                raise GoldLabError(
                    "project_archived",
                    "cannot append ledger through archived project",
                )
            if campaign.status is GoldCampaignStatus.CLOSED:
                raise GoldLabError(
                    "campaign_closed",
                    "cannot append ledger to closed campaign",
                )

            baseline = load_sealed_baseline_run(
                self.settings,
                campaign_id=cid,
                baseline_authoring_run_id=campaign.baseline_authoring_run_id,
                baseline_sha256=campaign.baseline_sha256,
            )

            a = preferred_chunk_id
            b = other_chunk_id
            if rtype is GoldLedgerRecordType.AUXILIARY_PREFERENCE:
                if a is None:
                    raw_a = payload.get("preferred_chunk_id")
                    a = raw_a if isinstance(raw_a, str) else None
                if b is None:
                    raw_b = payload.get("other_chunk_id")
                    b = raw_b if isinstance(raw_b, str) else None

            expected_task = resolve_ledger_task_id(
                campaign_id=cid,
                record_type=rtype.value,
                case_id=case_id,
                baseline=baseline,
                candidate_chunk_id=candidate_chunk_id,
                preferred_chunk_id=a,
                other_chunk_id=b,
            )
            tid = task_id or expected_task
            validate_task_id(tid)
            if tid != expected_task:
                raise GoldLabError(
                    "task_identity_mismatch",
                    "task_id does not match deterministic identity",
                )

            rid = validate_record_id(record_id or new_ledger_record_id())
            jid = validate_judgment_id(judgment_id or new_judgment_id())
            validate_selection_policy_fingerprint(
                campaign.selection_policy.selection_policy_fingerprint
            )

            semantic = {
                GoldLedgerRecordType.ABSOLUTE_RELEVANCE: ABSOLUTE_RELEVANCE_CONTRACT,
                GoldLedgerRecordType.QUESTION_CHECK: QUESTION_CHECK_CONTRACT,
                GoldLedgerRecordType.AUXILIARY_PREFERENCE: AUXILIARY_PREFERENCE_CONTRACT,
            }[rtype]

            existing = self.list_records(cid)
            next_sequence = (existing[-1].sequence + 1) if existing else 1
            ts = created_at or datetime.now(tz=UTC)

            try:
                record = GoldLedgerRecord(
                    sequence=next_sequence,
                    record_id=rid,
                    record_type=rtype,
                    judgment_id=jid,
                    task_id=tid,
                    project_id=campaign.project_id,
                    campaign_id=campaign.campaign_id,
                    workspace_id=campaign.workspace_id,
                    snapshot_id=campaign.snapshot_id,
                    chunk_set_id=campaign.chunk_set_id,
                    authoring_run_id=campaign.baseline_authoring_run_id,
                    case_id=case_id,
                    query_fingerprint=query_fingerprint,
                    candidate_chunk_id=candidate_chunk_id,
                    semantic_contract=semantic,
                    selection_policy_id=campaign.selection_policy.selection_policy_id,
                    selection_policy_fingerprint=(
                        campaign.selection_policy.selection_policy_fingerprint
                    ),
                    game_id=game_id,
                    presentation_id=presentation_id,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    created_at=ts,  # type: ignore[arg-type]
                    supersedes_judgment_id=supersedes_judgment_id,
                    payload=payload,
                )
            except GoldLabError:
                raise
            except Exception as exc:
                raise GoldLabError(
                    "ledger_record_invalid",
                    f"invalid ledger record: {exc}",
                ) from exc

            self._assert_campaign_provenance(record, campaign)

            path = ledger_dir(self.settings, cid) / ledger_record_filename(
                sequence=record.sequence,
                record_id=record.record_id,
            )
            if path.exists():
                raise GoldLabError(
                    "ledger_record_exists",
                    f"ledger path already exists: {path.name}",
                )
            ledger_dir(self.settings, cid).mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, record.model_dump_json())
            committed = self.list_records(cid)
            if not committed or committed[-1].record_id != record.record_id:
                raise GoldLabError(
                    "ledger_append_failed",
                    "appended record not visible after publish",
                )
            return committed[-1]

    def list_records(self, campaign_id: str) -> list[GoldLedgerRecord]:
        """Load ledger in ascending sequence; fail closed on integrity errors."""
        cid = validate_campaign_id(campaign_id)
        if not campaign_dir(self.settings, cid).is_dir():
            raise GoldLabError("campaign_not_found", f"unknown campaign: {cid}")
        root = ledger_dir(self.settings, cid)
        if not root.exists():
            return []

        campaign = self.store.get_campaign(cid)
        entries: list[tuple[int, str, Path]] = []
        for path in root.iterdir():
            if not path.is_file():
                continue
            name = path.name
            if name.startswith(".") or name.endswith(_TEMP_SUFFIXES):
                continue
            if name.endswith(".tmp") or ".tmp." in name:
                continue
            match = _LEDGER_FILENAME.match(name)
            if match is None:
                raise GoldLabError(
                    "ledger_filename_invalid",
                    f"invalid ledger filename: {name}",
                )
            entries.append((int(match.group("seq")), match.group("record_id"), path))

        entries.sort(key=lambda item: item[0])
        records: list[GoldLedgerRecord] = []
        expected = 1
        seen_sequences: set[int] = set()
        for seq, record_id, path in entries:
            if seq in seen_sequences:
                raise GoldLabError(
                    "ledger_duplicate_sequence",
                    f"duplicate ledger sequence: {seq}",
                )
            seen_sequences.add(seq)
            if seq != expected:
                raise GoldLabError(
                    "ledger_sequence_gap",
                    f"ledger sequence gap: expected {expected}, found {seq}",
                )
            expected += 1
            try:
                text = path.read_text(encoding="utf-8")
                record = GoldLedgerRecord.model_validate_json(text)
            except GoldLabError:
                raise
            except Exception as exc:
                raise GoldLabError(
                    "ledger_record_invalid",
                    f"invalid ledger record: {path.name}",
                ) from exc
            if record.sequence != seq:
                raise GoldLabError(
                    "ledger_filename_sequence_mismatch",
                    f"filename/record.sequence mismatch for {path.name}",
                )
            if record.record_id != record_id:
                raise GoldLabError(
                    "ledger_filename_record_id_mismatch",
                    f"filename/record_id mismatch for {path.name}",
                )
            self._assert_campaign_provenance(record, campaign)
            records.append(record)
        return records

    def _assert_campaign_provenance(
        self,
        record: GoldLedgerRecord,
        campaign: GoldCampaign,
    ) -> None:
        checks = (
            ("campaign_id", record.campaign_id, campaign.campaign_id),
            ("project_id", record.project_id, campaign.project_id),
            ("workspace_id", record.workspace_id, campaign.workspace_id),
            ("snapshot_id", record.snapshot_id, campaign.snapshot_id),
            ("chunk_set_id", record.chunk_set_id, campaign.chunk_set_id),
            (
                "authoring_run_id",
                record.authoring_run_id,
                campaign.baseline_authoring_run_id,
            ),
            (
                "selection_policy_id",
                record.selection_policy_id,
                campaign.selection_policy.selection_policy_id,
            ),
            (
                "selection_policy_fingerprint",
                record.selection_policy_fingerprint,
                campaign.selection_policy.selection_policy_fingerprint,
            ),
        )
        for name, got, expected in checks:
            if got != expected:
                raise GoldLabError(
                    "ledger_provenance_mismatch",
                    f"ledger {name} does not match campaign.json",
                )
