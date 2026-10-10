"""GAP-16G-01 — immutable Training / Calibration package read (registration-time)."""

from __future__ import annotations

import hashlib
from typing import Any

from offline_rag.app.errors import AppError
from offline_rag.app.gold_lab.baseline import load_sealed_baseline_run
from offline_rag.app.gold_lab.effective_state import fold_effective_state
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.historical_source import (
    gold_source_context,
    resolve_historical_chunk,
)
from offline_rag.app.gold_lab.ids import validate_campaign_id, validate_dataset_id
from offline_rag.app.gold_lab.ledger import GoldLabLedger
from offline_rag.app.gold_lab.models import GoldCampaign, GoldRegistration
from offline_rag.app.gold_lab.paths import dataset_dir, projection_authoring_run_path
from offline_rag.app.gold_lab.projection import project_authoring_run, projection_text
from offline_rag.app.gold_lab.registrations import (
    load_registration,
    validate_registration_against_authority,
)
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.gold_lab.views import rfc3339_z
from offline_rag.config.models import AppSettings
from offline_rag.evaluation.gold import GOLD_SCHEMA_V1, load_gold_dataset
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase
from offline_rag.gold_authoring.review_models import HumanReviewStatus, tags_equal

PACKAGE_SCHEMA_VERSION = (
    "offline-rag-gold-lab-training-calibration-package-v1"
)

_FINALIZED = frozenset(
    {
        HumanReviewStatus.ACCEPTED,
        HumanReviewStatus.EDITED,
        HumanReviewStatus.REJECTED,
    }
)

_QC_DISPOSITION = {
    HumanReviewStatus.ACCEPTED: "accept",
    HumanReviewStatus.EDITED: "edit",
    HumanReviewStatus.REJECTED: "reject",
}


class GoldLabTrainingPackageService:
    """Read-only package binding dataset + projection_sha256 + historical sources."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        store: GoldLabStore | None = None,
        ledger: GoldLabLedger | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or GoldLabStore(settings)
        self.ledger = ledger or GoldLabLedger(settings, store=self.store)

    def get_training_package(
        self, *, campaign_id: str, dataset_id: str
    ) -> dict[str, Any]:
        cid = validate_campaign_id(campaign_id)
        did = validate_dataset_id(dataset_id)

        campaign = self.store.get_campaign(cid)
        project = self.store.get_project(campaign.project_id)
        registration = load_registration(
            self.settings, dataset_id=did, campaign_id=cid
        )
        validate_registration_against_authority(
            self.settings,
            registration,
            campaign=campaign,
            project=project,
        )

        registered_dataset = self._load_registered_dataset_section(registration)
        projected = self._recover_projection(
            campaign=campaign,
            registration=registration,
        )
        adjudication_cases = self._build_adjudication_cases(
            campaign=campaign,
            projected=projected,
            registration=registration,
            registered_dataset=registered_dataset,
        )
        return {
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "campaign_id": cid,
            "dataset_id": did,
            "registration": self._registration_section(registration),
            "registered_dataset": registered_dataset,
            "adjudication": {
                "projection_sha256": registration.projection_sha256,
                "cases": adjudication_cases,
            },
        }

    def _registration_section(self, registration: GoldRegistration) -> dict[str, Any]:
        return {
            "dataset_id": registration.dataset_id,
            "project_id": registration.project_id,
            "campaign_id": registration.campaign_id,
            "project_type": registration.project_type.value
            if hasattr(registration.project_type, "value")
            else str(registration.project_type),
            "workspace_id": registration.workspace_id,
            "snapshot_id": registration.snapshot_id,
            "chunk_set_id": registration.chunk_set_id,
            "corpus_id": registration.corpus_id,
            "corpus_name": registration.corpus_name,
            "baseline_authoring_run_id": registration.baseline_authoring_run_id,
            "baseline_sha256": registration.baseline_sha256,
            "projection_sha256": registration.projection_sha256,
            "selection_policy_id": registration.selection_policy_id,
            "selection_policy_fingerprint": (
                registration.selection_policy_fingerprint
            ),
            "exported_case_ids": list(registration.exported_case_ids),
            "registered_at": rfc3339_z(registration.registered_at),
        }

    def _load_registered_dataset_section(
        self, registration: GoldRegistration
    ) -> dict[str, Any]:
        canonical = dataset_dir(self.settings, registration.dataset_id)
        try:
            loaded = load_gold_dataset(canonical)
        except Exception as exc:
            raise GoldLabError(
                "registration_dataset_corrupt",
                f"canonical dataset unreadable: {exc}",
            ) from exc
        if loaded.source_schema != GOLD_SCHEMA_V1:
            raise GoldLabError(
                "registration_dataset_schema_invalid",
                f"expected {GOLD_SCHEMA_V1}",
            )
        if loaded.dataset_id != registration.dataset_id:
            raise GoldLabError(
                "registration_dataset_id_mismatch",
                "loaded dataset_id does not match registration",
            )
        cases: list[dict[str, Any]] = []
        for case in sorted(loaded.cases, key=lambda item: item.id):
            judgments = [
                {
                    "chunk_id": judgment.chunk_id,
                    "relevance": int(judgment.relevance),
                }
                for judgment in sorted(
                    case.judgments, key=lambda item: item.chunk_id
                )
            ]
            cases.append(
                {
                    "case_id": case.id,
                    "query": case.query,
                    "category": case.category,
                    "tags": list(case.tags),
                    "judgments": judgments,
                }
            )
        return {
            "schema_version": GOLD_SCHEMA_V1,
            "dataset_id": loaded.dataset_id,
            "chunk_set_id": loaded.meta.chunk_set_id,
            "corpus_id": loaded.meta.corpus_id,
            "corpus_name": loaded.meta.corpus_name,
            "cases": cases,
        }

    def _recover_projection(
        self,
        *,
        campaign: GoldCampaign,
        registration: GoldRegistration,
    ) -> GoldAuthoringRun:
        target = registration.projection_sha256.strip().lower()
        path = projection_authoring_run_path(
            self.settings, campaign.campaign_id
        )
        if path.is_file():
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest == target:
                try:
                    parsed = GoldAuthoringRun.model_validate_json(
                        raw.decode("utf-8")
                    )
                except Exception as exc:
                    raise GoldLabError(
                        "training_package_adjudication_invalid",
                        f"projection artifact invalid: {exc}",
                    ) from exc
                canon = projection_text(parsed).encode("utf-8")
                if canon != raw:
                    raise GoldLabError(
                        "training_package_adjudication_invalid",
                        "projection canonical serialization mismatch",
                    )
                self._assert_projection_campaign_coherence(
                    campaign=campaign, projected=parsed
                )
                return parsed

        recovered = self._reconstruct_from_ledger(
            campaign=campaign, target_sha256=target
        )
        if recovered is None:
            raise GoldLabError(
                "training_package_projection_unavailable",
                "registration-time projection could not be recovered",
            )
        return recovered

    def _reconstruct_from_ledger(
        self,
        *,
        campaign: GoldCampaign,
        target_sha256: str,
    ) -> GoldAuthoringRun | None:
        baseline = load_sealed_baseline_run(
            self.settings,
            campaign_id=campaign.campaign_id,
            baseline_authoring_run_id=campaign.baseline_authoring_run_id,
            baseline_sha256=campaign.baseline_sha256,
        )
        records = self.ledger.list_records(campaign.campaign_id)
        for prefix_length in range(len(records), -1, -1):
            state = fold_effective_state(
                campaign_id=campaign.campaign_id,
                baseline=baseline,
                records=records[:prefix_length],
            )
            projected = project_authoring_run(state)
            raw = projection_text(projected).encode("utf-8")
            if hashlib.sha256(raw).hexdigest() == target_sha256:
                self._assert_projection_campaign_coherence(
                    campaign=campaign, projected=projected
                )
                return projected
        return None

    def _assert_projection_campaign_coherence(
        self, *, campaign: GoldCampaign, projected: GoldAuthoringRun
    ) -> None:
        if projected.authoring_run_id != campaign.baseline_authoring_run_id:
            raise GoldLabError(
                "training_package_adjudication_invalid",
                "projected authoring_run_id does not match campaign baseline",
            )
        if projected.chunk_set_id != campaign.chunk_set_id:
            raise GoldLabError(
                "training_package_adjudication_invalid",
                "projected chunk_set_id does not match campaign",
            )
        if projected.corpus_id != campaign.corpus_id:
            raise GoldLabError(
                "training_package_adjudication_invalid",
                "projected corpus_id does not match campaign",
            )
        if projected.corpus_name != campaign.corpus_name:
            raise GoldLabError(
                "training_package_adjudication_invalid",
                "projected corpus_name does not match campaign",
            )

    def _build_adjudication_cases(
        self,
        *,
        campaign: GoldCampaign,
        projected: GoldAuthoringRun,
        registration: GoldRegistration,
        registered_dataset: dict[str, Any],
    ) -> list[dict[str, Any]]:
        finalized: list[SilverCase] = []
        for case in projected.cases:
            status = case.human_status
            if status in _FINALIZED:
                finalized.append(case)

        accepted_edited = [
            case
            for case in finalized
            if case.human_status
            in (HumanReviewStatus.ACCEPTED, HumanReviewStatus.EDITED)
        ]
        projected_ids = {case.draft_case_id for case in accepted_edited}
        exported_ids = set(registration.exported_case_ids)
        dataset_ids = {row["case_id"] for row in registered_dataset["cases"]}
        if projected_ids != exported_ids or projected_ids != dataset_ids:
            raise GoldLabError(
                "training_package_dataset_projection_mismatch",
                "accepted/edited case IDs do not match registration/dataset",
            )

        dataset_by_id = {
            row["case_id"]: row for row in registered_dataset["cases"]
        }
        out: list[dict[str, Any]] = []
        for case in sorted(finalized, key=lambda item: item.draft_case_id):
            status = case.human_status
            if status is HumanReviewStatus.REJECTED:
                if case.draft_case_id in dataset_ids:
                    raise GoldLabError(
                        "training_package_dataset_projection_mismatch",
                        "rejected case must not appear in GoldDataset",
                    )
                out.append(
                    self._reject_case_dto(campaign=campaign, case=case)
                )
                continue

            gold_row = dataset_by_id[case.draft_case_id]
            out.append(
                self._accept_edit_case_dto(
                    campaign=campaign,
                    case=case,
                    gold_row=gold_row,
                )
            )
        return out

    def _reject_case_dto(
        self, *, campaign: GoldCampaign, case: SilverCase
    ) -> dict[str, Any]:
        question_source = self._resolve_question_source(
            campaign=campaign, case=case
        )
        # Reject still resolves candidate historical sources for pedagogy.
        candidates = self._candidate_sources(campaign=campaign, case=case)
        return {
            "case_id": case.draft_case_id,
            "qc_disposition": "reject",
            "proposed_query": case.proposed_query,
            "proposed_category": case.proposed_category,
            "proposed_tags": list(case.proposed_tags or []),
            "effective_query": None,
            "effective_category": None,
            "effective_tags": [],
            "question_source": question_source,
            "candidates": candidates,
            "relevance_judgments": [],
        }

    def _accept_edit_case_dto(
        self,
        *,
        campaign: GoldCampaign,
        case: SilverCase,
        gold_row: dict[str, Any],
    ) -> dict[str, Any]:
        status = case.human_status
        if status not in (
            HumanReviewStatus.ACCEPTED,
            HumanReviewStatus.EDITED,
        ):
            raise GoldLabError(
                "training_package_adjudication_invalid",
                "expected accepted/edited case",
            )
        if not case.candidates:
            raise GoldLabError(
                "training_package_adjudication_invalid",
                "accepted/edited case requires nonempty candidates",
            )
        if not case.review_complete():
            raise GoldLabError(
                "training_package_adjudication_invalid",
                "accepted/edited case relevance map incomplete",
            )
        if case.human_positive_count() < 1:
            raise GoldLabError(
                "training_package_adjudication_invalid",
                "accepted/edited case requires at least one positive grade",
            )

        judgment_map = case.human_judgment_map()
        for grade in judgment_map.values():
            if grade not in (0, 1, 2):
                raise GoldLabError(
                    "training_package_adjudication_invalid",
                    "relevance grades must be 0|1|2",
                )

        effective_query = case.effective_query()
        effective_category = case.effective_category()
        effective_tags = list(case.effective_tags())
        if effective_query is None:
            raise GoldLabError(
                "training_package_adjudication_invalid",
                "accepted/edited case missing effective query",
            )

        if gold_row["query"] != effective_query:
            raise GoldLabError(
                "training_package_dataset_projection_mismatch",
                "GoldDataset query does not match projected effective query",
            )
        if gold_row["category"] != effective_category:
            raise GoldLabError(
                "training_package_dataset_projection_mismatch",
                "GoldDataset category does not match projected effective category",
            )
        if not tags_equal(gold_row["tags"], effective_tags):
            raise GoldLabError(
                "training_package_dataset_projection_mismatch",
                "GoldDataset tags do not match projected effective tags",
            )

        gold_positives = {
            item["chunk_id"]: int(item["relevance"])
            for item in gold_row["judgments"]
        }
        projected_positives = {
            chunk_id: grade
            for chunk_id, grade in judgment_map.items()
            if grade >= 1
        }
        if gold_positives != projected_positives:
            raise GoldLabError(
                "training_package_dataset_projection_mismatch",
                "GoldDataset positives do not match projected judgments >0",
            )

        relevance_judgments = [
            {"chunk_id": chunk_id, "relevance": judgment_map[chunk_id]}
            for chunk_id in sorted(judgment_map)
        ]
        return {
            "case_id": case.draft_case_id,
            "qc_disposition": _QC_DISPOSITION[status],
            "proposed_query": case.proposed_query,
            "proposed_category": case.proposed_category,
            "proposed_tags": list(case.proposed_tags or []),
            "effective_query": effective_query,
            "effective_category": effective_category,
            "effective_tags": effective_tags,
            "question_source": self._resolve_question_source(
                campaign=campaign, case=case
            ),
            "candidates": self._candidate_sources(
                campaign=campaign, case=case
            ),
            "relevance_judgments": relevance_judgments,
        }

    def _resolve_question_source(
        self, *, campaign: GoldCampaign, case: SilverCase
    ) -> dict[str, Any] | None:
        seed = case.source_seed
        if seed is None:
            return None
        try:
            chunk, _corpus, source_name = resolve_historical_chunk(
                self.settings,
                campaign,
                chunk_id=seed.chunk_id,
                expected_document_id=seed.document_id,
                expected_section_path=list(seed.section_path or []),
            )
        except AppError:
            raise
        except Exception as exc:
            raise GoldLabError(
                "historical_chunk_unavailable",
                "question source historical chunk unavailable",
            ) from exc
        title = getattr(seed, "document_title", None)
        return gold_source_context(
            chunk=chunk,
            document_title=title if title else None,
            source_name=source_name,
        )

    def _candidate_sources(
        self, *, campaign: GoldCampaign, case: SilverCase
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for candidate in sorted(case.candidates, key=lambda item: item.chunk_id):
            try:
                chunk, _corpus, source_name = resolve_historical_chunk(
                    self.settings,
                    campaign,
                    chunk_id=candidate.chunk_id,
                    expected_document_id=candidate.document_id,
                    expected_section_path=list(candidate.section_path or []),
                )
            except AppError:
                raise
            except Exception as exc:
                raise GoldLabError(
                    "historical_chunk_unavailable",
                    "candidate historical chunk unavailable",
                ) from exc
            title = getattr(candidate, "document_title", None)
            rows.append(
                {
                    "chunk_id": candidate.chunk_id,
                    "source": gold_source_context(
                        chunk=chunk,
                        document_title=title if title else None,
                        source_name=source_name,
                    ),
                }
            )
        return rows
