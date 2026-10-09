"""Internal Gold Lab mutation service (16F-B; Rework 1 hardened)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from offline_rag.app.gold_lab.baseline import load_sealed_baseline_run
from offline_rag.app.gold_lab.contribution import (
    ContributionProjection,
    project_contribution,
)
from offline_rag.app.gold_lab.effective_state import (
    EffectiveCampaignState,
    assert_no_duplicate_ledger_idempotency_keys,
    fold_effective_state,
)
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.idempotency import (
    GoldLabIdempotencyCatalog,
    normalize_idempotency_key,
)
from offline_rag.app.gold_lab.ids import (
    absolute_relevance_task_id,
    auxiliary_preference_task_id,
    new_judgment_id,
    new_ledger_record_id,
    question_check_task_id,
    validate_campaign_id,
)
from offline_rag.app.gold_lab.leases import GoldLabCampaignLease, GoldLabProjectLease
from offline_rag.app.gold_lab.ledger import GoldLabLedger
from offline_rag.app.gold_lab.models import (
    AbsoluteRelevancePayload,
    AuxiliaryPreferencePayload,
    GoldCampaign,
    GoldCampaignStatus,
    GoldLedgerRecord,
    GoldLedgerRecordType,
    GoldProjectStatus,
    HardCallsArtifact,
    IdempotencyCommandKind,
    IdempotencyStatus,
)
from offline_rag.app.gold_lab.paths import hard_calls_path
from offline_rag.app.gold_lab.question_check import (
    canonical_question_check_request_payload,
    canonicalize_question_check_payload,
    durable_question_check_payload,
    question_check_query_fingerprint,
)
from offline_rag.app.gold_lab.reviewable import is_reviewable_case
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.gold_lab.tasks import (
    BlindTaskView,
    blind_task_views,
    project_tasks,
)
from offline_rag.app.workspace.models import canonical_request_fingerprint
from offline_rag.config.models import AppSettings
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase


@dataclass(frozen=True)
class MutationResult:
    record: GoldLedgerRecord
    replayed: bool


class GoldLabMutationService:
    """Durable idempotent mutation commands under project+campaign leases."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        store: GoldLabStore | None = None,
        ledger: GoldLabLedger | None = None,
        catalog: GoldLabIdempotencyCatalog | None = None,
        under_lease_hook: Callable[[], None] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or GoldLabStore(settings)
        self.ledger = ledger or GoldLabLedger(settings, store=self.store)
        self.catalog = catalog or GoldLabIdempotencyCatalog(settings)
        self._under_lease_hook = under_lease_hook

    def load_effective_state(self, campaign_id: str) -> EffectiveCampaignState:
        cid = validate_campaign_id(campaign_id)
        campaign = self.store.get_campaign(cid)
        baseline = load_sealed_baseline_run(
            self.settings,
            campaign_id=cid,
            baseline_authoring_run_id=campaign.baseline_authoring_run_id,
            baseline_sha256=campaign.baseline_sha256,
        )
        records = self.ledger.list_records(cid)
        return fold_effective_state(
            campaign_id=cid, baseline=baseline, records=records
        )

    def load_hard_calls(self, campaign_id: str) -> HardCallsArtifact:
        cid = validate_campaign_id(campaign_id)
        path = hard_calls_path(self.settings, cid)
        if not path.is_file():
            raise GoldLabError(
                "hard_calls_missing",
                f"missing hard_calls.json for {cid}",
            )
        try:
            artifact = HardCallsArtifact.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except GoldLabError:
            raise
        except Exception as exc:
            raise GoldLabError(
                "hard_calls_corrupt",
                f"unreadable hard_calls.json: {cid}",
            ) from exc
        if artifact.campaign_id != cid:
            raise GoldLabError(
                "hard_calls_campaign_mismatch",
                "hard_calls.json campaign_id mismatch",
            )
        return artifact

    def project_tasks(self, campaign_id: str):
        return project_tasks(self.load_effective_state(campaign_id))

    def blind_task_views(self, campaign_id: str) -> list[BlindTaskView]:
        return blind_task_views(self.load_effective_state(campaign_id))

    def contribution(self, campaign_id: str) -> ContributionProjection:
        """Live application contribution; gold_finalized is always 0 until 16F-C."""
        state = self.load_effective_state(campaign_id)
        hard_calls = self.load_hard_calls(campaign_id)
        return project_contribution(
            state, hard_calls=hard_calls, finalized_case_ids=()
        )

    def submit_question_check(
        self,
        *,
        campaign_id: str,
        case_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
        game_id: str | None = None,
        presentation_id: str | None = None,
    ) -> MutationResult:
        cid = validate_campaign_id(campaign_id)

        def prepare(campaign: GoldCampaign, state: EffectiveCampaignState, reserved):
            baseline = self._load_baseline(campaign)
            case = self._require_reviewable_case(baseline, case_id)
            canonical_payload = canonicalize_question_check_payload(
                payload, case=case
            )
            return {
                "record_type": GoldLedgerRecordType.QUESTION_CHECK,
                "case_id": case_id,
                "payload": durable_question_check_payload(canonical_payload),
                "idempotency_key": normalize_idempotency_key(idempotency_key),
                "request_fingerprint": canonical_request_fingerprint(
                    {
                        "kind": "question_check",
                        "campaign_id": cid,
                        "case_id": case_id,
                        "payload": canonical_question_check_request_payload(
                            canonical_payload
                        ),
                        "game_id": game_id,
                        "presentation_id": presentation_id,
                    }
                ),
                "query_fingerprint": question_check_query_fingerprint(
                    canonical_payload, case
                ),
                "game_id": game_id,
                "presentation_id": presentation_id,
                "supersedes_judgment_id": self._qc_supersedes(state, case_id),
                "task_id": question_check_task_id(campaign_id=cid, case_id=case_id),
                "record_id": reserved["record_id"],
                "judgment_id": reserved["judgment_id"],
            }

        # Request fingerprint for idempotency uses canonicalized payload; compute
        # under lease with the same prepare path via a lightweight precompute.
        return self._execute_mutation(
            campaign_id=cid,
            command_kind=IdempotencyCommandKind.QUESTION_CHECK,
            idempotency_key=idempotency_key,
            request_fingerprint_factory=lambda campaign: self._qc_request_fp(
                campaign,
                case_id=case_id,
                payload=payload,
                game_id=game_id,
                presentation_id=presentation_id,
            ),
            append_kwargs_factory=prepare,
        )

    def submit_absolute_relevance(
        self,
        *,
        campaign_id: str,
        case_id: str,
        candidate_chunk_id: str,
        relevance: object,
        idempotency_key: str,
        game_id: str | None = None,
        presentation_id: str | None = None,
    ) -> MutationResult:
        cid = validate_campaign_id(campaign_id)
        try:
            abs_payload = AbsoluteRelevancePayload.model_validate(
                {"relevance": relevance}
            )
        except Exception as exc:
            raise GoldLabError(
                "absolute_relevance_invalid",
                f"relevance must be strict int 0|1|2: {exc}",
            ) from exc

        request_fp = canonical_request_fingerprint(
            {
                "kind": "absolute_relevance",
                "campaign_id": cid,
                "case_id": case_id,
                "candidate_chunk_id": candidate_chunk_id,
                "relevance": abs_payload.relevance,
                "game_id": game_id,
                "presentation_id": presentation_id,
            }
        )

        def prepare(campaign: GoldCampaign, state: EffectiveCampaignState, reserved):
            baseline = self._load_baseline(campaign)
            case = self._require_reviewable_case(baseline, case_id)
            self._require_candidate(case, candidate_chunk_id)
            qc = state.question_active_accept_or_edit(case_id)
            if qc is None or qc.query_fingerprint is None:
                raise GoldLabError(
                    "absolute_task_inactive",
                    "absolute relevance requires current QC accept/edit",
                )
            task_id = absolute_relevance_task_id(
                campaign_id=cid,
                case_id=case_id,
                candidate_chunk_id=candidate_chunk_id,
            )
            current = state.current_absolute_for_task(
                task_id, query_fingerprint=qc.query_fingerprint
            )
            supersedes = None if current is None else current.record.judgment_id
            return {
                "record_type": GoldLedgerRecordType.ABSOLUTE_RELEVANCE,
                "case_id": case_id,
                "candidate_chunk_id": candidate_chunk_id,
                "payload": abs_payload.model_dump(),
                "idempotency_key": normalize_idempotency_key(idempotency_key),
                "request_fingerprint": request_fp,
                "query_fingerprint": qc.query_fingerprint,
                "game_id": game_id,
                "presentation_id": presentation_id,
                "supersedes_judgment_id": supersedes,
                "task_id": task_id,
                "record_id": reserved["record_id"],
                "judgment_id": reserved["judgment_id"],
            }

        return self._execute_mutation(
            campaign_id=cid,
            command_kind=IdempotencyCommandKind.ABSOLUTE_RELEVANCE,
            idempotency_key=idempotency_key,
            request_fingerprint_factory=lambda _campaign: request_fp,
            append_kwargs_factory=prepare,
        )

    def submit_auxiliary_preference(
        self,
        *,
        campaign_id: str,
        case_id: str,
        preferred_chunk_id: str,
        other_chunk_id: str,
        idempotency_key: str,
        game_id: str | None = None,
        presentation_id: str | None = None,
    ) -> MutationResult:
        cid = validate_campaign_id(campaign_id)
        if preferred_chunk_id == other_chunk_id:
            raise GoldLabError(
                "auxiliary_pair_not_distinct",
                "preferred and other chunk ids must be distinct",
            )
        try:
            aux = AuxiliaryPreferencePayload(
                preferred_chunk_id=preferred_chunk_id,
                other_chunk_id=other_chunk_id,
            )
        except Exception as exc:
            raise GoldLabError(
                "auxiliary_preference_invalid",
                f"invalid auxiliary preference payload: {exc}",
            ) from exc

        request_fp = canonical_request_fingerprint(
            {
                "kind": "auxiliary_preference",
                "campaign_id": cid,
                "case_id": case_id,
                "preferred_chunk_id": preferred_chunk_id,
                "other_chunk_id": other_chunk_id,
                "game_id": game_id,
                "presentation_id": presentation_id,
            }
        )
        task_id = auxiliary_preference_task_id(
            campaign_id=cid,
            case_id=case_id,
            candidate_a=preferred_chunk_id,
            candidate_b=other_chunk_id,
        )

        def prepare(campaign: GoldCampaign, _state: EffectiveCampaignState, reserved):
            baseline = self._load_baseline(campaign)
            case = self._require_reviewable_case(baseline, case_id)
            self._require_candidate(case, preferred_chunk_id)
            self._require_candidate(case, other_chunk_id)
            return {
                "record_type": GoldLedgerRecordType.AUXILIARY_PREFERENCE,
                "case_id": case_id,
                "payload": aux.model_dump(),
                "idempotency_key": normalize_idempotency_key(idempotency_key),
                "request_fingerprint": request_fp,
                "query_fingerprint": None,
                "game_id": game_id,
                "presentation_id": presentation_id,
                "supersedes_judgment_id": None,
                "task_id": task_id,
                "preferred_chunk_id": preferred_chunk_id,
                "other_chunk_id": other_chunk_id,
                "record_id": reserved["record_id"],
                "judgment_id": reserved["judgment_id"],
            }

        return self._execute_mutation(
            campaign_id=cid,
            command_kind=IdempotencyCommandKind.AUXILIARY_PREFERENCE,
            idempotency_key=idempotency_key,
            request_fingerprint_factory=lambda _campaign: request_fp,
            append_kwargs_factory=prepare,
        )

    def _qc_request_fp(
        self,
        campaign: GoldCampaign,
        *,
        case_id: str,
        payload: dict[str, Any],
        game_id: str | None,
        presentation_id: str | None,
    ) -> str:
        baseline = self._load_baseline(campaign)
        case = self._require_reviewable_case(baseline, case_id)
        canonical_payload = canonicalize_question_check_payload(payload, case=case)
        return canonical_request_fingerprint(
            {
                "kind": "question_check",
                "campaign_id": campaign.campaign_id,
                "case_id": case_id,
                "payload": canonical_question_check_request_payload(canonical_payload),
                "game_id": game_id,
                "presentation_id": presentation_id,
            }
        )

    def _execute_mutation(
        self,
        *,
        campaign_id: str,
        command_kind: IdempotencyCommandKind,
        idempotency_key: str,
        request_fingerprint_factory: Callable[[GoldCampaign], str],
        append_kwargs_factory: Callable[
            [GoldCampaign, EffectiveCampaignState, dict[str, str]], dict[str, Any]
        ],
    ) -> MutationResult:
        cid = validate_campaign_id(campaign_id)
        key = normalize_idempotency_key(idempotency_key)

        campaign_probe = self.store.get_campaign(cid)
        project_id = campaign_probe.project_id

        with (
            GoldLabProjectLease(self.settings, project_id),
            GoldLabCampaignLease(self.settings, cid) as lease,
        ):
            campaign = self.store.get_campaign(cid)
            if campaign.project_id != project_id:
                raise GoldLabError(
                    "project_identity_mismatch",
                    "campaign.project_id changed under lease",
                )
            if self._under_lease_hook is not None:
                self._under_lease_hook()

            request_fingerprint = request_fingerprint_factory(campaign)
            records = self.ledger.list_records(cid)
            # Duplicate-key fail-closed on every supported mutation path.
            assert_no_duplicate_ledger_idempotency_keys(records)

            entry = self.catalog.load_entry(cid, key)

            if entry is not None:
                self.catalog.require_command_kind(entry, command_kind)
                if entry.request_fingerprint != request_fingerprint:
                    raise GoldLabError(
                        "idempotency_conflict",
                        "same idempotency key with different request fingerprint",
                    )
                if entry.status is IdempotencyStatus.COMMITTED:
                    record = self.catalog.validate_committed_against_ledger(
                        entry=entry, records=records
                    )
                    return MutationResult(record=record, replayed=True)

                # PENDING
                reserved_record = self.catalog.find_reserved_record(
                    entry=entry, records=records
                )
                if reserved_record is not None:
                    finalized = self.catalog.mark_committed(
                        campaign_id=cid, idempotency_key=key
                    )
                    if finalized.status is not IdempotencyStatus.COMMITTED:
                        raise GoldLabError(
                            "idempotency_finalize_failed",
                            "failed to mark reservation COMMITTED",
                        )
                    return MutationResult(record=reserved_record, replayed=True)

                # PENDING + no ledger: reapply lifecycle / effective gates; same IDs.
                self._require_open_lifecycle(campaign)
                state = fold_effective_state(
                    campaign_id=cid,
                    baseline=self._load_baseline(campaign),
                    records=records,
                )
                reserved = {
                    "record_id": entry.record_id,
                    "judgment_id": entry.judgment_id,
                }
                kwargs = append_kwargs_factory(campaign, state, reserved)
                record = self.ledger.append_under_lease(lease, cid, **kwargs)
                self.catalog.mark_committed(campaign_id=cid, idempotency_key=key)
                return MutationResult(record=record, replayed=False)

            # New key
            self.catalog.assert_no_orphan_ledger_key(
                campaign_id=cid, normalized_key=key, records=records
            )
            self._require_open_lifecycle(campaign)
            baseline = self._load_baseline(campaign)
            state = fold_effective_state(
                campaign_id=cid, baseline=baseline, records=records
            )
            reserved = {
                "record_id": new_ledger_record_id(),
                "judgment_id": new_judgment_id(),
            }
            # Build + validate complete append intent BEFORE PENDING reservation.
            kwargs = append_kwargs_factory(campaign, state, reserved)
            self.catalog.write_pending(
                campaign_id=cid,
                idempotency_key=key,
                request_fingerprint=request_fingerprint,
                command_kind=command_kind.value,
                record_id=reserved["record_id"],
                judgment_id=reserved["judgment_id"],
            )
            record = self.ledger.append_under_lease(lease, cid, **kwargs)
            self.catalog.mark_committed(campaign_id=cid, idempotency_key=key)
            return MutationResult(record=record, replayed=False)

    def _qc_supersedes(
        self, state: EffectiveCampaignState, case_id: str
    ) -> str | None:
        current = state.current_question_for_case(case_id)
        if current is None:
            return None
        return current.record.judgment_id

    def _require_open_lifecycle(self, campaign: GoldCampaign) -> None:
        project = self.store.get_project(campaign.project_id)
        if project.status is GoldProjectStatus.ARCHIVED:
            raise GoldLabError(
                "project_archived",
                "cannot mutate through archived project",
            )
        if campaign.status is GoldCampaignStatus.CLOSED:
            raise GoldLabError(
                "campaign_closed",
                "cannot mutate closed campaign",
            )

    def _load_baseline(self, campaign: GoldCampaign) -> GoldAuthoringRun:
        return load_sealed_baseline_run(
            self.settings,
            campaign_id=campaign.campaign_id,
            baseline_authoring_run_id=campaign.baseline_authoring_run_id,
            baseline_sha256=campaign.baseline_sha256,
        )

    @staticmethod
    def _require_reviewable_case(
        baseline: GoldAuthoringRun, case_id: str
    ) -> SilverCase:
        for case in baseline.cases:
            if case.draft_case_id == case_id:
                if not is_reviewable_case(case):
                    raise GoldLabError(
                        "case_not_reviewable",
                        f"case is not reviewable: {case_id}",
                    )
                return case
        raise GoldLabError("case_not_found", f"unknown case_id: {case_id}")

    @staticmethod
    def _require_candidate(case: SilverCase, chunk_id: str) -> None:
        if not any(c.chunk_id == chunk_id for c in case.candidates):
            raise GoldLabError(
                "candidate_not_in_case",
                f"chunk {chunk_id} is not a candidate of {case.draft_case_id}",
            )
