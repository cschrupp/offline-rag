"""Quick Play orchestration over the accepted Gold Lab data plane."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.gold_lab.application import (
    GoldLabApplicationService,
    translate_gold_lab_error,
)
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import (
    validate_campaign_id,
    validate_project_id,
)
from offline_rag.app.gold_lab.models import (
    GoldCampaign,
    GoldCampaignStatus,
    GoldProject,
    GoldProjectStatus,
    GoldProjectType,
    build_selection_policy,
)
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.app.workspace.models import (
    GoldLabBaselineBootstrapResult,
    ManagedOperationKind,
    ManagedOperationRecord,
    ManagedOperationStatus,
    WorkspaceStatus,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.core.ids import canonical_config_hash
from offline_rag.gold_authoring.chunk_access import load_chunk_set_snapshot
from offline_rag.gold_authoring.sampling import build_eligible_population

QuickPlayAction = Literal["start", "replenish"]

QUICK_PLAY_VERSION = 1
QUICK_PLAY_GENERATION_VERSION = "quick_play_baseline_v1"
QUICK_PLAY_SELECTION_POLICY_ID = "quick_play_improvement_v1"
QUICK_PLAY_SELECTION_PARAMETERS: dict[str, Any] = {
    "quick_play_version": QUICK_PLAY_VERSION,
    "selection_intent": "improvement-oriented",
}
QUICK_PLAY_PROPOSAL_COUNT = 20
QUICK_PLAY_PRELABEL_ENABLED = False
_SETUP_RECONCILE_SECONDS = 2.0
_SETUP_RETRY_INTERVAL_SECONDS = 0.01
_ELIGIBLE_POPULATION_CACHE_LIMIT = 32
_NONTERMINAL = frozenset(
    {
        ManagedOperationStatus.PENDING,
        ManagedOperationStatus.PREPARING,
        ManagedOperationStatus.RUNNING,
    }
)


@dataclass(frozen=True)
class _QuickPlayIdentity:
    workspace_id: str
    workspace_title: str
    revision: int
    snapshot_id: str
    corpus_name: str
    corpus_id: str
    chunk_set_id: str
    eligible_chunk_count: int
    proposal_count: int
    fingerprint: str
    project_id: str


class QuickPlayService:
    """Resolve or create Quick Play projects and campaigns deterministically."""

    _eligible_population_counts: ClassVar[OrderedDict[tuple[str, ...], int]] = (
        OrderedDict()
    )
    _eligible_population_lock: ClassVar[threading.RLock] = threading.RLock()

    def __init__(self, runtime: ApplicationRuntime) -> None:
        self.runtime = runtime
        self.gold: GoldLabApplicationService = runtime.gold_lab
        self.store: GoldLabStore = self.gold.store
        self.operations = ManagedOperationStore(runtime.settings)

    def get_state(self, workspace_id: str) -> dict[str, Any]:
        """Return the current Quick Play status without creating Gold objects."""
        identity, blocked = self._identity(workspace_id)
        if blocked is not None:
            return blocked
        assert identity is not None

        project = self._get_project(identity.project_id)
        base = self._base_view(identity, project)
        if identity.eligible_chunk_count == 0:
            return {
                **base,
                "status": "empty_population",
                "reason": "no_eligible_source_chunks",
            }
        if project is None:
            return {**base, "status": "needs_generation"}
        if project.status is GoldProjectStatus.ARCHIVED:
            return {**base, "status": "blocked", "reason": "project_archived"}

        campaigns = self.store.list_campaigns(project_id=project.project_id)
        matching = [
            campaign
            for campaign in campaigns
            if self._campaign_matches_identity(campaign, identity)
        ]
        matching.sort(
            key=lambda item: (item.created_at, item.campaign_id), reverse=True
        )

        for campaign in matching:
            task_state = self._task_state(campaign)
            if (
                campaign.status is GoldCampaignStatus.OPEN
                and task_state["available_games"]
            ):
                return {
                    **base,
                    **task_state,
                    "status": "playable",
                    "campaign_id": campaign.campaign_id,
                }

        baselines = self.gold.list_baselines(project.project_id)["baselines"]
        used_baselines = {item.baseline_authoring_run_id for item in campaigns}
        reusable = [
            baseline
            for baseline in baselines
            if baseline["reviewable_case_count"] > 0
            and baseline["authoring_run_id"] not in used_baselines
        ]
        reusable.sort(key=lambda item: (item["created_at"], item["authoring_run_id"]))
        if reusable:
            operation = self._operation_for_run(
                identity, reusable[-1]["authoring_run_id"]
            )
            return {
                **base,
                "status": (
                    "campaign_ready"
                    if operation is not None
                    and operation.status is ManagedOperationStatus.SUCCEEDED
                    else "baseline_available"
                ),
                "baseline_authoring_run_id": reusable[-1]["authoring_run_id"],
                "baseline_generated_by_quick_play": bool(
                    operation is not None
                    and operation.status is ManagedOperationStatus.SUCCEEDED
                ),
                "operation": self._operation_summary(operation),
            }

        operation = self._latest_operation(identity)
        if operation is not None and operation.status in _NONTERMINAL:
            return {
                **base,
                "status": "generating",
                "operation": self._operation_summary(operation),
            }
        if operation is not None and operation.status in {
            ManagedOperationStatus.FAILED,
            ManagedOperationStatus.INTERRUPTED,
        }:
            return {
                **base,
                "status": "generation_failed",
                "operation": self._operation_summary(operation),
            }

        # A baseline operation from Advanced Gold Lab also owns the workspace
        # bootstrap slot. Wait for it to finish; its output will be reconsidered
        # as a reusable baseline on the next state read.
        workspace_operation = self._active_workspace_bootstrap(workspace_id)
        if workspace_operation is not None:
            return {
                **base,
                "status": "generating",
                "operation": self._operation_summary(workspace_operation),
            }

        if matching:
            latest = matching[0]
            if latest.status is GoldCampaignStatus.CLOSED:
                task_state = self._task_state(latest)
                if not task_state["available_games"]:
                    return {
                        **base,
                        **task_state,
                        "status": "complete",
                        "campaign_id": latest.campaign_id,
                    }
                return {
                    **base,
                    **task_state,
                    "status": "blocked",
                    "campaign_id": latest.campaign_id,
                    "reason": "campaign_closed_with_no_playable_tasks",
                }
            return {
                **base,
                **self._task_state(latest),
                "status": "complete",
                "campaign_id": latest.campaign_id,
            }

        return {**base, "status": "needs_generation"}

    def prepare(
        self,
        workspace_id: str,
        *,
        action: QuickPlayAction,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Start or reconcile a deck; campaign IDs make retries idempotent."""
        if not idempotency_key.strip() or len(idempotency_key) > 256:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="idempotency_key_invalid"),
            )

        state = self.get_state(workspace_id)
        if state["status"] in {
            "blocked",
            "not_ready",
            "empty_population",
            "playable",
            "generating",
        }:
            return state
        if state["status"] == "complete" and action == "start":
            return state

        identity, blocked = self._identity(workspace_id)
        if blocked is not None:
            return blocked
        assert identity is not None
        project = self._ensure_project(identity)

        # Reconcile a baseline that already exists before considering a new
        # generation request. This recovers a lost response after generation.
        baselines = self.gold.list_baselines(project.project_id)["baselines"]
        campaigns = self.store.list_campaigns(project_id=project.project_id)
        used_baselines = {item.baseline_authoring_run_id for item in campaigns}
        reusable = [
            baseline
            for baseline in baselines
            if baseline["reviewable_case_count"] > 0
            and baseline["authoring_run_id"] not in used_baselines
        ]
        reusable.sort(key=lambda item: (item["created_at"], item["authoring_run_id"]))
        if reusable:
            return self._create_or_reuse_campaign(
                identity, project, reusable[-1]["authoring_run_id"]
            )

        operation = self._active_workspace_bootstrap(workspace_id)
        if operation is not None:
            return self.get_state(workspace_id)

        if state["status"] == "complete" and action != "replenish":
            return state

        try:
            operation = self.gold.start_baseline_bootstrap(
                project_id=project.project_id,
                proposal_count=identity.proposal_count,
                prelabel_enabled=QUICK_PLAY_PRELABEL_ENABLED,
                idempotency_key=idempotency_key,
            )
        except AppError as exc:
            # Another session may have reserved the same workspace operation
            # between the read and the call. Reconcile its durable record.
            if exc.code is ErrorCode.GOLD_BUSY:
                refreshed = self.get_state(workspace_id)
                if refreshed["status"] == "generating":
                    return refreshed
            raise

        return {
            **self._base_view(identity, project),
            "status": "generating",
            "operation": self._operation_summary(operation),
        }

    def _identity(
        self, workspace_id: str
    ) -> tuple[_QuickPlayIdentity | None, dict[str, Any] | None]:
        workspace = self.gold._call(self.gold.workspace_store.get, workspace_id)
        if (
            workspace.status is not WorkspaceStatus.ACTIVE
            or workspace.current_snapshot_id is None
        ):
            return None, {
                "schema_version": "quick-play-state-v1",
                "status": "not_ready",
                "workspace_id": workspace_id,
                "workspace_title": workspace.title,
                "reason": "workspace_has_no_published_snapshot",
            }

        try:
            snapshot = self.runtime.publication.resolve_snapshot(
                workspace.backing_corpus_name,
                workspace.current_snapshot_id,
            )
        except Exception as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id,
                    snapshot_id=workspace.current_snapshot_id,
                ),
            ) from exc

        policy = build_selection_policy(
            selection_policy_id=QUICK_PLAY_SELECTION_POLICY_ID,
            project_type=GoldProjectType.IMPROVEMENT,
            parameters=QUICK_PLAY_SELECTION_PARAMETERS,
        )
        eligible_chunk_count = self._eligible_population_count(
            workspace_id=workspace_id,
            snapshot_id=workspace.current_snapshot_id,
            corpus_name=workspace.backing_corpus_name,
            corpus_id=snapshot.identity.corpus_id,
            chunk_set_id=snapshot.identity.chunk_set_id,
            corpus_manifest_name=snapshot.identity.corpus_manifest,
        )
        proposal_count = min(QUICK_PLAY_PROPOSAL_COUNT, eligible_chunk_count)
        identity_payload = {
            "schema": "quick-play-identity-v1",
            "workspace_id": workspace_id,
            "snapshot_id": workspace.current_snapshot_id,
            "corpus_id": snapshot.identity.corpus_id,
            "chunk_set_id": snapshot.identity.chunk_set_id,
            "generation_version": QUICK_PLAY_GENERATION_VERSION,
            "proposal_count": proposal_count,
            "prelabel_enabled": QUICK_PLAY_PRELABEL_ENABLED,
            "selection_policy_id": policy.selection_policy_id,
            "selection_policy_fingerprint": policy.selection_policy_fingerprint,
        }
        fingerprint = canonical_config_hash(identity_payload)
        project_id = validate_project_id(f"goldproj_{fingerprint[4:36]}")
        return (
            _QuickPlayIdentity(
                workspace_id=workspace_id,
                workspace_title=workspace.title,
                revision=workspace.revision,
                snapshot_id=workspace.current_snapshot_id,
                corpus_name=workspace.backing_corpus_name,
                corpus_id=snapshot.identity.corpus_id,
                chunk_set_id=snapshot.identity.chunk_set_id,
                eligible_chunk_count=eligible_chunk_count,
                proposal_count=proposal_count,
                fingerprint=fingerprint,
                project_id=project_id,
            ),
            None,
        )

    def _eligible_population_count(
        self,
        *,
        workspace_id: str,
        snapshot_id: str,
        corpus_name: str,
        corpus_id: str,
        chunk_set_id: str,
        corpus_manifest_name: str,
    ) -> int:
        """Return the eligible seed count, reusing immutable snapshot results."""
        settings = self.runtime.settings
        cache_key = (
            str(settings.paths.chunk_manifests.resolve()),
            str(settings.paths.chunks.resolve()),
            corpus_name,
            snapshot_id,
            corpus_id,
            chunk_set_id,
            corpus_manifest_name,
        )
        with self._eligible_population_lock:
            cached_count = self._eligible_population_counts.get(cache_key)
            if cached_count is not None:
                self._eligible_population_counts.move_to_end(cache_key)
                return cached_count

        try:
            chunk_snapshot = load_chunk_set_snapshot(
                settings,
                corpus_name=corpus_name,
                corpus_id=corpus_id,
                chunk_set_id=chunk_set_id,
                corpus_manifest_name=corpus_manifest_name,
            )
            eligible_count = len(build_eligible_population(chunk_snapshot.chunks))
        except Exception as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id,
                    snapshot_id=snapshot_id,
                    reason="quick_play_chunk_population_unavailable",
                ),
            ) from exc

        with self._eligible_population_lock:
            # Another request may have populated this key during the disk read.
            cached_count = self._eligible_population_counts.get(cache_key)
            if cached_count is not None:
                self._eligible_population_counts.move_to_end(cache_key)
                return cached_count
            self._eligible_population_counts[cache_key] = eligible_count
            while (
                len(self._eligible_population_counts) > _ELIGIBLE_POPULATION_CACHE_LIMIT
            ):
                self._eligible_population_counts.popitem(last=False)
        return eligible_count

    def _get_project(self, project_id: str) -> GoldProject | None:
        try:
            return self.store.get_project(project_id)
        except GoldLabError as exc:
            if exc.reason == "project_not_found":
                return None
            raise translate_gold_lab_error(exc) from exc

    def _ensure_project(self, identity: _QuickPlayIdentity) -> GoldProject:
        marker = f"Quick Play identity {identity.fingerprint}"
        deadline = time.monotonic() + _SETUP_RECONCILE_SECONDS
        while True:
            project = self._get_project(identity.project_id)
            if project is not None:
                self._validate_project_identity(project, identity)
                return project

            try:
                return self.store.create_project(
                    workspace_id=identity.workspace_id,
                    title="Quick Play",
                    description=marker,
                    project_type=GoldProjectType.IMPROVEMENT,
                    project_id=identity.project_id,
                )
            except GoldLabError as exc:
                if exc.reason == "project_already_exists":
                    if time.monotonic() >= deadline:
                        raise translate_gold_lab_error(exc) from exc
                    time.sleep(_SETUP_RETRY_INTERVAL_SECONDS)
                    continue
                if exc.reason != "gold_lab_lease_held" or time.monotonic() >= deadline:
                    raise translate_gold_lab_error(exc) from exc
                time.sleep(_SETUP_RETRY_INTERVAL_SECONDS)

    @staticmethod
    def _validate_project_identity(
        project: GoldProject, identity: _QuickPlayIdentity
    ) -> None:
        expected_description = f"Quick Play identity {identity.fingerprint}"
        if (
            project.project_id != identity.project_id
            or project.workspace_id != identity.workspace_id
            or project.project_type is not GoldProjectType.IMPROVEMENT
            or project.description != expected_description
        ):
            raise AppError(
                ErrorCode.GOLD_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    project_id=identity.project_id,
                    reason="quick_play_project_identity_mismatch",
                ),
            )

    def _latest_operation(
        self, identity: _QuickPlayIdentity
    ) -> ManagedOperationRecord | None:
        matches = [
            item
            for item in self.operations.list_for_workspace(identity.workspace_id)
            if item.kind is ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP
            and item.bootstrap_authority is not None
            and item.bootstrap_authority.project_id == identity.project_id
        ]
        return max(matches, key=lambda item: item.created_at) if matches else None

    def _operation_for_run(
        self, identity: _QuickPlayIdentity, authoring_run_id: str
    ) -> ManagedOperationRecord | None:
        matches = [
            item
            for item in self.operations.list_for_workspace(identity.workspace_id)
            if item.kind is ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP
            and item.bootstrap_authority is not None
            and item.bootstrap_authority.project_id == identity.project_id
            and item.bootstrap_authority.authoring_run_id == authoring_run_id
        ]
        return max(matches, key=lambda item: item.created_at) if matches else None

    def _active_workspace_bootstrap(
        self, workspace_id: str
    ) -> ManagedOperationRecord | None:
        active = [
            item
            for item in self.operations.list_for_workspace(workspace_id)
            if item.kind is ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP
            and item.status in _NONTERMINAL
        ]
        return max(active, key=lambda item: item.created_at) if active else None

    def _campaign_matches_identity(
        self, campaign: GoldCampaign, identity: _QuickPlayIdentity
    ) -> bool:
        policy = build_selection_policy(
            selection_policy_id=QUICK_PLAY_SELECTION_POLICY_ID,
            project_type=GoldProjectType.IMPROVEMENT,
            parameters=QUICK_PLAY_SELECTION_PARAMETERS,
        )
        return (
            campaign.workspace_id == identity.workspace_id
            and campaign.snapshot_id == identity.snapshot_id
            and campaign.corpus_name == identity.corpus_name
            and campaign.corpus_id == identity.corpus_id
            and campaign.chunk_set_id == identity.chunk_set_id
            and campaign.selection_policy.selection_policy_fingerprint
            == policy.selection_policy_fingerprint
        )

    def _task_state(self, campaign: GoldCampaign) -> dict[str, Any]:
        tasks = self.gold.list_tasks(campaign.campaign_id)["tasks"]
        question_pending = sum(
            1
            for task in tasks
            if task["task_kind"] == "question_check"
            and task["state"] == "pending"
            and task["active"]
        )
        relevance_pending = sum(
            1
            for task in tasks
            if task["task_kind"] == "absolute_relevance"
            and task["state"] == "pending"
            and task["active"]
        )
        games: list[dict[str, Any]] = []
        if question_pending:
            games.append(
                {
                    "game_id": "question_check",
                    "label": "Question Check",
                    "pending_count": question_pending,
                }
            )
        if relevance_pending:
            games.append(
                {
                    "game_id": "rapid_fire",
                    "label": "Rapid Fire",
                    "pending_count": relevance_pending,
                }
            )
        next_game = (
            "question_check"
            if question_pending
            else "rapid_fire"
            if relevance_pending
            else None
        )
        return {
            "available_games": games,
            "question_check_pending": question_pending,
            "rapid_fire_pending": relevance_pending,
            "next_game": next_game,
        }

    def _create_or_reuse_campaign(
        self,
        identity: _QuickPlayIdentity,
        project: GoldProject,
        baseline_authoring_run_id: str,
    ) -> dict[str, Any]:
        existing = self._matching_campaign_for_baseline(
            identity, project.project_id, baseline_authoring_run_id
        )
        if existing is None:
            baseline = self.gold.resolve_eligible_baseline(
                project_id=project.project_id,
                baseline_authoring_run_id=baseline_authoring_run_id,
            )
            baseline_bytes = baseline.model_dump_json().encode("utf-8")
            campaign_id_digest = hashlib.sha256(
                json.dumps(
                    {
                        "schema": "quick-play-campaign-identity-v1",
                        "project_id": project.project_id,
                        "baseline_authoring_run_id": baseline_authoring_run_id,
                        "baseline_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
                        "selection_policy_id": QUICK_PLAY_SELECTION_POLICY_ID,
                        "selection_parameters": QUICK_PLAY_SELECTION_PARAMETERS,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            campaign_id = validate_campaign_id(f"goldcamp_{campaign_id_digest[:32]}")
            policy = build_selection_policy(
                selection_policy_id=QUICK_PLAY_SELECTION_POLICY_ID,
                project_type=GoldProjectType.IMPROVEMENT,
                parameters=QUICK_PLAY_SELECTION_PARAMETERS,
            )
            deadline = time.monotonic() + _SETUP_RECONCILE_SECONDS
            while existing is None:
                existing = self._matching_campaign_for_baseline(
                    identity, project.project_id, baseline_authoring_run_id
                )
                if existing is not None:
                    break
                try:
                    existing = self.gold.campaigns.create_campaign(
                        project_id=project.project_id,
                        baseline=baseline,
                        selection_policy=policy,
                        campaign_id=campaign_id,
                    )
                except GoldLabError as exc:
                    if exc.reason == "campaign_already_exists":
                        existing = self.gold._call(self.store.get_campaign, campaign_id)
                        if not self._campaign_matches_identity(existing, identity):
                            raise AppError(
                                ErrorCode.GOLD_STATE_UNAVAILABLE,
                                details=SafeErrorDetails(
                                    campaign_id=campaign_id,
                                    reason="quick_play_campaign_identity_mismatch",
                                ),
                            )
                        break
                    if (
                        exc.reason != "gold_lab_lease_held"
                        or time.monotonic() >= deadline
                    ):
                        raise translate_gold_lab_error(exc) from exc
                    time.sleep(_SETUP_RETRY_INTERVAL_SECONDS)
                except AppError as exc:
                    if (
                        exc.code is not ErrorCode.WORKSPACE_CONFLICT
                        or time.monotonic() >= deadline
                    ):
                        raise
                    time.sleep(_SETUP_RETRY_INTERVAL_SECONDS)

        task_state = self._task_state(existing)
        campaign_status = (
            "blocked"
            if existing.status is GoldCampaignStatus.CLOSED
            and task_state["available_games"]
            else "playable"
            if task_state["available_games"]
            else "complete"
        )
        return {
            **self._base_view(identity, project),
            **task_state,
            "status": campaign_status,
            "campaign_id": existing.campaign_id,
        }

    def _matching_campaign_for_baseline(
        self,
        identity: _QuickPlayIdentity,
        project_id: str,
        baseline_authoring_run_id: str,
    ) -> GoldCampaign | None:
        candidates = [
            campaign
            for campaign in self.store.list_campaigns(project_id=project_id)
            if campaign.baseline_authoring_run_id == baseline_authoring_run_id
            and self._campaign_matches_identity(campaign, identity)
        ]
        return (
            max(candidates, key=lambda item: (item.created_at, item.campaign_id))
            if candidates
            else None
        )

    def _base_view(
        self, identity: _QuickPlayIdentity, project: GoldProject | None
    ) -> dict[str, Any]:
        return {
            "schema_version": "quick-play-state-v1",
            "workspace_id": identity.workspace_id,
            "workspace_title": identity.workspace_title,
            "workspace_revision": identity.revision,
            "snapshot_id": identity.snapshot_id,
            "identity_fingerprint": identity.fingerprint,
            "proposal_count": identity.proposal_count,
            "project_id": project.project_id if project is not None else None,
        }

    @staticmethod
    def _operation_summary(
        operation: ManagedOperationRecord | None,
    ) -> dict[str, Any] | None:
        if operation is None:
            return None
        return {
            "operation_id": operation.operation_id,
            "status": str(operation.status),
            "progress_stage": (
                str(operation.progress_stage)
                if operation.progress_stage is not None
                else None
            ),
            "failure_summary": operation.failure_summary,
            "result": (
                operation.result.model_dump(mode="python", exclude_none=True)
                if isinstance(operation.result, GoldLabBaselineBootstrapResult)
                else None
            ),
        }
