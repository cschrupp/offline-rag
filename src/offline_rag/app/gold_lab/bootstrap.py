"""GAP-16G-02 Gold Lab baseline bootstrap orchestration."""

from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Mapping, Sequence
from typing import Any

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.gold_lab.baseline import (
    assert_pristine_baseline,
    validate_historical_chunk_identities,
)
from offline_rag.app.gold_lab.bootstrap_seed import derive_bootstrap_sampling_seed
from offline_rag.app.gold_lab.bootstrap_staging import (
    bootstrap_staging_run_path,
    cleanup_workspace_bootstrap_staging,
    delete_bootstrap_staging,
    ensure_bootstrap_staging_dir,
)
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import validate_project_id
from offline_rag.app.gold_lab.leases import GoldLabProjectLease
from offline_rag.app.gold_lab.models import GoldProjectStatus
from offline_rag.app.gold_lab.reviewable import is_reviewable_case
from offline_rag.app.gold_lab.store import GoldLabStore
from offline_rag.app.operations import OperationHandle
from offline_rag.app.progress_publish import DurableProgressPublisher
from offline_rag.app.workspace.leases import WorkspaceMutationLease
from offline_rag.app.workspace.models import (
    GoldLabBaselineBootstrapAuthority,
    GoldLabBaselineBootstrapResult,
    ManagedOperationKind,
    ManagedOperationRecord,
    ManagedOperationSafeError,
    ManagedOperationStatus,
    OperationProgressStage,
    WorkspaceStatus,
    canonical_operation_fingerprint,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.core.ids import new_execution_id
from offline_rag.gold_authoring.chunk_access import load_chunk_set_snapshot
from offline_rag.gold_authoring.models import (
    ProposalAttempt,
    ProposalFailureReason,
)
from offline_rag.gold_authoring.persist import (
    default_authoring_run_path,
    serialize_authoring_run_bytes,
    write_authoring_run_bytes,
)
from offline_rag.gold_authoring.pool import PoolPreRunError, run_gold_pool
from offline_rag.gold_authoring.pool_arms import HistoricalPoolArmExecutor
from offline_rag.gold_authoring.pool_ensure import (
    PoolEnsureError,
    ensure_pooling_artifacts,
)
from offline_rag.gold_authoring.prelabel import PrelabelPreRunError, run_gold_prelabel
from offline_rag.gold_authoring.privacy import (
    AuthoringPrivacyError,
    authorize_authoring_endpoint,
)
from offline_rag.gold_authoring.propose import (
    ProposePreRunError,
    ProposePreRunReason,
    run_gold_propose_on_snapshot,
)
from offline_rag.gold_authoring.readiness import evaluate_authoring_readiness
from offline_rag.gold_authoring.sampling import build_eligible_population

logger = logging.getLogger(__name__)

_NONTERMINAL = frozenset(
    {
        ManagedOperationStatus.PENDING,
        ManagedOperationStatus.PREPARING,
        ManagedOperationStatus.RUNNING,
    }
)

_AUTH_REASONS = frozenset({ProposalFailureReason.AUTHENTICATION_ERROR.value})
_TIMEOUT_REASONS = frozenset({ProposalFailureReason.TIMEOUT.value})
_TRANSPORT_REASONS = frozenset({ProposalFailureReason.TRANSPORT_ERROR.value})
_HTTP_REASONS = frozenset(
    {
        ProposalFailureReason.HTTP_ERROR.value,
        ProposalFailureReason.REDIRECT_NOT_ALLOWED.value,
    }
)
_CONTEXT_REASONS = frozenset(
    {ProposalFailureReason.PROPOSAL_CONTEXT_UNAVAILABLE.value}
)
_EVAL_REASONS = frozenset(
    {
        ProposalFailureReason.EMPTY_RESPONSE.value,
        ProposalFailureReason.INVALID_JSON.value,
        ProposalFailureReason.SCHEMA_INVALID.value,
        ProposalFailureReason.DEICTIC_QUERY.value,
        ProposalFailureReason.SEED_QUOTE_OVERLAP.value,
        ProposalFailureReason.DUPLICATE_QUERY_EXACT.value,
        ProposalFailureReason.DUPLICATE_QUERY_NEAR.value,
    }
)
_CLASSIFIED_REASONS = (
    _AUTH_REASONS
    | _TIMEOUT_REASONS
    | _TRANSPORT_REASONS
    | _HTTP_REASONS
    | _CONTEXT_REASONS
    | _EVAL_REASONS
)

_PRE_RUN_GOLD_CONFLICT: dict[ProposePreRunReason, str] = {
    ProposePreRunReason.AUTHORING_NOT_READY: "authoring_not_ready",
    ProposePreRunReason.AUTHORING_ENDPOINT_UNAUTHORIZED: (
        "authoring_endpoint_unauthorized"
    ),
    ProposePreRunReason.PROPOSAL_COUNT_EXCEEDS_ELIGIBLE_POPULATION: (
        "proposal_count_exceeds_eligible_population"
    ),
}


def _app(
    code: ErrorCode,
    reason: str,
    *,
    message: str | None = None,
) -> AppError:
    return AppError(
        code,
        message=message,
        details=SafeErrorDetails(reason=reason),
    )


def classify_zero_success_proposal(
    failure_reason_counts: Mapping[str, int] | None,
    attempts: Sequence[ProposalAttempt] | None,
) -> tuple[ErrorCode, str]:
    """Deterministic Q1/R4 terminal classification for successful_count == 0."""
    evidence: set[str] = set()
    if failure_reason_counts:
        for key, count in failure_reason_counts.items():
            if int(count) > 0:
                evidence.add(str(key))
    if attempts:
        for attempt in attempts:
            if attempt.failure_reason is not None:
                evidence.add(str(attempt.failure_reason))

    if not evidence:
        return ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"
    if any(reason not in _CLASSIFIED_REASONS for reason in evidence):
        return ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"

    if evidence & _AUTH_REASONS:
        return ErrorCode.GOLD_CONFLICT, "authoring_authentication_failed"
    if evidence & _TIMEOUT_REASONS:
        return ErrorCode.GOLD_CONFLICT, "authoring_request_timeout"
    if evidence & _TRANSPORT_REASONS:
        return ErrorCode.GOLD_CONFLICT, "authoring_endpoint_unreachable"
    if evidence & _HTTP_REASONS:
        return ErrorCode.GOLD_CONFLICT, "authoring_http_error"
    if evidence & _CONTEXT_REASONS:
        return ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"
    if evidence & _EVAL_REASONS:
        return ErrorCode.GOLD_CONFLICT, "zero_usable_proposals"
    return ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"


def map_propose_pre_run_error(exc: ProposePreRunError) -> tuple[ErrorCode, str]:
    """Structural R1 bootstrap mapping; never uses str(exc)."""
    reason = getattr(exc, "reason", None)
    if isinstance(reason, ProposePreRunReason):
        mapped = _PRE_RUN_GOLD_CONFLICT.get(reason)
        if mapped is not None:
            return ErrorCode.GOLD_CONFLICT, mapped
        return ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"
    return ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"


def bootstrap_request_fingerprint(
    *, project_id: str, proposal_count: int, prelabel_enabled: bool
) -> str:
    return canonical_operation_fingerprint(
        kind=ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP,
        expected_revision=None,
        payload={
            "project_id": project_id,
            "proposal_count": proposal_count,
            "prelabel_enabled": prelabel_enabled,
        },
    )


def _fail_op(
    ops: ManagedOperationStore,
    *,
    workspace_id: str,
    operation_id: str,
    error: AppError,
    progress_stage: OperationProgressStage | None = None,
    lease: WorkspaceMutationLease | None = None,
) -> ManagedOperationRecord:
    return ops.update_status(
        workspace_id,
        operation_id,
        ManagedOperationStatus.FAILED,
        failure_summary=error.message[:512],
        progress_stage=progress_stage,
        error=ManagedOperationSafeError.from_app_error(error),
        lease=lease,
    )


class GoldLabBaselineBootstrapService:
    """Project-scoped baseline bootstrap command + worker."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.settings = runtime.settings
        self.store = GoldLabStore(self.settings)
        self.workspace_store = WorkspaceStore(self.settings)
        self.operations = ManagedOperationStore(self.settings)

    @property
    def publication(self) -> Any:
        return self.runtime.publication

    def start_baseline_bootstrap(
        self,
        *,
        project_id: str,
        proposal_count: object,
        prelabel_enabled: object,
        idempotency_key: str,
    ) -> ManagedOperationRecord:
        self.runtime.require_ready()
        try:
            pid = validate_project_id(project_id)
        except GoldLabError as exc:
            raise _app(ErrorCode.GOLD_PROJECT_UNKNOWN, "project_unknown") from exc

        if not isinstance(proposal_count, int) or isinstance(proposal_count, bool):
            raise _app(
                ErrorCode.REQUEST_INVALID,
                "proposal_count_invalid",
                message="proposal_count must be a strict integer",
            )
        if proposal_count < 1 or proposal_count > 40:
            raise _app(
                ErrorCode.REQUEST_INVALID,
                "proposal_count_invalid",
                message="proposal_count must be between 1 and 40",
            )
        if not isinstance(prelabel_enabled, bool):
            raise _app(
                ErrorCode.REQUEST_INVALID,
                "prelabel_enabled_invalid",
                message="prelabel_enabled must be a boolean",
            )

        key = str(idempotency_key).strip()
        if not key or len(key) > 256:
            raise _app(ErrorCode.REQUEST_INVALID, "idempotency_key_invalid")

        fingerprint = bootstrap_request_fingerprint(
            project_id=pid,
            proposal_count=proposal_count,
            prelabel_enabled=prelabel_enabled,
        )

        # Resolve project enough to obtain workspace binding (same-key recovery).
        try:
            project = self.store.get_project(pid)
        except GoldLabError as exc:
            if exc.reason == "project_not_found":
                raise _app(ErrorCode.GOLD_PROJECT_UNKNOWN, "project_unknown") from exc
            raise

        workspace_id = project.workspace_id
        control: OperationHandle | None = None
        created = False
        record: ManagedOperationRecord | None = None

        lease = WorkspaceMutationLease(self.settings, workspace_id)
        lease.acquire(blocking=True)
        try:
            existing = self.operations.find_by_idempotency(workspace_id, key)
            if existing is not None:
                if (
                    existing.request_fingerprint != fingerprint
                    or existing.kind
                    is not ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP
                    or existing.expected_revision is not None
                ):
                    raise _app(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "idempotency_identity_mismatch",
                    )
                return existing

            # New intent — re-read project/workspace under lease.
            try:
                project = self.store.get_project(pid)
            except GoldLabError as exc:
                if exc.reason == "project_not_found":
                    raise _app(
                        ErrorCode.GOLD_PROJECT_UNKNOWN, "project_unknown"
                    ) from exc
                raise
            if project.workspace_id != workspace_id:
                raise _app(ErrorCode.GOLD_CONFLICT, "project_status_invalid")
            if project.status is GoldProjectStatus.ARCHIVED:
                raise _app(ErrorCode.GOLD_CONFLICT, "project_archived")
            if project.status is not GoldProjectStatus.ACTIVE:
                raise _app(ErrorCode.GOLD_CONFLICT, "project_status_invalid")

            readiness = evaluate_authoring_readiness(self.settings)
            if not readiness.ready:
                raise _app(ErrorCode.GOLD_CONFLICT, "authoring_not_ready")
            try:
                authorize_authoring_endpoint(self.settings)
            except AuthoringPrivacyError as exc:
                raise _app(
                    ErrorCode.GOLD_CONFLICT, "authoring_endpoint_unauthorized"
                ) from exc

            try:
                workspace = self.workspace_store.get(workspace_id)
            except AppError:
                raise
            except Exception as exc:
                raise _app(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    "workspace_state_unavailable",
                ) from exc

            if workspace.status is WorkspaceStatus.TOMBSTONED:
                raise _app(ErrorCode.WORKSPACE_UNKNOWN, "workspace_unknown")
            if workspace.status is not WorkspaceStatus.ACTIVE:
                raise _app(ErrorCode.WORKSPACE_NOT_READY, "workspace_not_ready")
            if workspace.current_snapshot_id is None:
                raise _app(ErrorCode.WORKSPACE_NOT_READY, "workspace_not_ready")

            active = [
                op
                for op in self.operations.list_for_workspace(workspace_id)
                if op.kind is ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP
                and op.status in _NONTERMINAL
            ]
            if active:
                raise _app(
                    ErrorCode.GOLD_BUSY,
                    "baseline_bootstrap_active",
                )

            try:
                control = self.runtime.operations.admit_gold_bootstrap()
            except AppError as exc:
                if exc.code is ErrorCode.SERVICE_OVERLOADED:
                    raise _app(
                        ErrorCode.SERVICE_OVERLOADED,
                        "gold_bootstrap_capacity_exhausted",
                    ) from exc
                raise

            authoring_run_id = new_execution_id(prefix="authorrun")
            try:
                record, created = self.operations.reserve(
                    workspace_id=workspace_id,
                    idempotency_key=key,
                    kind=ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP,
                    request_payload={
                        "project_id": pid,
                        "proposal_count": proposal_count,
                        "prelabel_enabled": prelabel_enabled,
                    },
                    expected_revision=None,
                    lease=lease,
                )
                if not created:
                    # Same-key race won by peer — release capacity and return peer.
                    self.runtime.operations.release(control)
                    control = None
                    return record

                # Post-admission publication capture: durable op already exists.
                try:
                    snapshot = self.publication.resolve_snapshot(
                        workspace.backing_corpus_name,
                        workspace.current_snapshot_id,
                    )
                except Exception:
                    logger.exception(
                        "bootstrap publication capture failed op=%s",
                        record.operation_id,
                    )
                    failed = _fail_op(
                        self.operations,
                        workspace_id=workspace_id,
                        operation_id=record.operation_id,
                        error=_app(
                            ErrorCode.SNAPSHOT_UNAVAILABLE,
                            "captured_chunk_set_unavailable",
                        ),
                        progress_stage=OperationProgressStage.PREPARING,
                        lease=lease,
                    )
                    self.runtime.operations.release(control)
                    control = None
                    return failed

                sampling_seed = derive_bootstrap_sampling_seed(record.operation_id)
                authority = GoldLabBaselineBootstrapAuthority(
                    project_id=pid,
                    workspace_id=workspace_id,
                    workspace_revision=workspace.revision,
                    snapshot_id=str(workspace.current_snapshot_id),
                    corpus_name=workspace.backing_corpus_name,
                    corpus_id=str(snapshot.identity.corpus_id),
                    chunk_set_id=str(snapshot.identity.chunk_set_id),
                    authoring_run_id=authoring_run_id,
                    proposal_count=proposal_count,
                    sampling_seed=sampling_seed,
                    prelabel_enabled=prelabel_enabled,
                )
                record = self.operations.update_status(
                    workspace_id,
                    record.operation_id,
                    ManagedOperationStatus.PENDING,
                    progress_stage=OperationProgressStage.PREPARING,
                    bootstrap_authority=authority,
                    lease=lease,
                )
                cleanup_workspace_bootstrap_staging(
                    self.settings,
                    workspace_id=workspace_id,
                    keep_operation_id=record.operation_id,
                )
            except Exception:
                if control is not None:
                    self.runtime.operations.release(control)
                    control = None
                raise
        finally:
            lease.release()

        assert record is not None
        assert control is not None
        thread = threading.Thread(
            target=self._worker,
            kwargs={
                "workspace_id": workspace_id,
                "operation_id": record.operation_id,
                "control": control,
            },
            name=f"gold-bootstrap-{record.operation_id}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            logger.exception(
                "bootstrap worker launch failed op=%s", record.operation_id
            )
            self.runtime.operations.release(control)
            return _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=record.operation_id,
                error=_app(
                    ErrorCode.INTERNAL_ERROR,
                    "bootstrap_internal_failure",
                ),
            )
        return record

    def _worker(
        self,
        *,
        workspace_id: str,
        operation_id: str,
        control: OperationHandle,
    ) -> None:
        try:
            self._run_pipeline(
                workspace_id=workspace_id,
                operation_id=operation_id,
                control=control,
            )
        except Exception:
            logger.exception("gold bootstrap worker fault op=%s", operation_id)
            try:
                current = self.operations.get(workspace_id, operation_id)
                if current.status in _NONTERMINAL:
                    _fail_op(
                        self.operations,
                        workspace_id=workspace_id,
                        operation_id=operation_id,
                        error=_app(
                            ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"
                        ),
                    )
            except Exception:
                logger.exception("failed to mark bootstrap FAILED")
        finally:
            self.runtime.operations.release(control)

    def _run_pipeline(
        self,
        *,
        workspace_id: str,
        operation_id: str,
        control: OperationHandle,
    ) -> None:
        record = self.operations.get(workspace_id, operation_id)
        auth = record.bootstrap_authority
        if auth is None:
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"),
            )
            return

        control.complete_lease_acquire()
        self.operations.update_status(
            workspace_id,
            operation_id,
            ManagedOperationStatus.PREPARING,
            progress_stage=OperationProgressStage.PREPARING,
        )

        ensure_bootstrap_staging_dir(
            self.settings, workspace_id=workspace_id, operation_id=operation_id
        )
        staging_path = bootstrap_staging_run_path(
            self.settings, workspace_id=workspace_id, operation_id=operation_id
        )

        # Load exact captured ChunkSet (never CURRENT).
        try:
            pub = self.publication.resolve_snapshot(auth.corpus_name, auth.snapshot_id)
            chunk_snapshot = load_chunk_set_snapshot(
                self.settings,
                corpus_name=auth.corpus_name,
                corpus_id=auth.corpus_id,
                chunk_set_id=auth.chunk_set_id,
                corpus_manifest_name=pub.identity.corpus_manifest,
            )
        except Exception:  # noqa: BLE001
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(
                    ErrorCode.SNAPSHOT_UNAVAILABLE,
                    "captured_chunk_set_unavailable",
                ),
                progress_stage=OperationProgressStage.PROPOSING,
            )
            return

        population = build_eligible_population(chunk_snapshot.chunks)
        if auth.proposal_count > len(population):
            auth = auth.model_copy(
                update={
                    "proposal_attempted": 0,
                    "proposal_succeeded": 0,
                    "proposal_failed": 0,
                }
            )
            self.operations.update_status(
                workspace_id,
                operation_id,
                ManagedOperationStatus.RUNNING,
                progress_stage=OperationProgressStage.PROPOSING,
                bootstrap_authority=auth,
            )
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(
                    ErrorCode.GOLD_CONFLICT,
                    "proposal_count_exceeds_eligible_population",
                ),
                progress_stage=OperationProgressStage.PROPOSING,
            )
            return

        # --- 9B ---
        self.operations.update_status(
            workspace_id,
            operation_id,
            ManagedOperationStatus.RUNNING,
            progress_stage=OperationProgressStage.PROPOSING,
            bootstrap_authority=auth,
        )
        progress = DurableProgressPublisher(
            operations=self.operations,
            workspace_id=workspace_id,
            operation_id=operation_id,
            progress_stage=OperationProgressStage.PROPOSING,
        )
        control.checkpoint("proposing")
        try:
            propose_result = run_gold_propose_on_snapshot(
                self.settings,
                snapshot=chunk_snapshot,
                authoring_run_id=auth.authoring_run_id,
                count=auth.proposal_count,
                seed=auth.sampling_seed,
                output=staging_path,
                force=True,
                skip_readiness=True,
                on_progress=progress,
            )
        except ProposePreRunError as exc:
            logger.info("bootstrap 9B pre-run failure op=%s: %s", operation_id, exc)
            code, reason = map_propose_pre_run_error(exc)
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(code, reason),
                progress_stage=OperationProgressStage.PROPOSING,
            )
            return

        if propose_result.output_path is None:
            logger.error(
                "bootstrap 9B persistence failure op=%s: %s",
                operation_id,
                propose_result.message,
            )
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"),
                progress_stage=OperationProgressStage.PROPOSING,
            )
            return

        run = propose_result.run
        if run is None or run.successful_count < 1:
            auth = auth.model_copy(
                update={
                    "proposal_attempted": len(run.attempts) if run else 0,
                    "proposal_succeeded": run.successful_count if run else 0,
                    "proposal_failed": (
                        (len(run.attempts) - run.successful_count) if run else 0
                    ),
                }
            )
            self.operations.update_status(
                workspace_id,
                operation_id,
                ManagedOperationStatus.RUNNING,
                bootstrap_authority=auth,
                progress_stage=OperationProgressStage.PROPOSING,
            )
            if run is None:
                code, reason = (
                    ErrorCode.INTERNAL_ERROR,
                    "bootstrap_internal_failure",
                )
            else:
                code, reason = classify_zero_success_proposal(
                    propose_result.failure_reason_counts,
                    run.attempts,
                )
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(code, reason),
                progress_stage=OperationProgressStage.PROPOSING,
            )
            return

        auth = auth.model_copy(
            update={
                "proposal_attempted": len(run.attempts),
                "proposal_succeeded": run.successful_count,
                "proposal_failed": len(run.attempts) - run.successful_count,
            }
        )

        # --- 9C ---
        self.operations.update_status(
            workspace_id,
            operation_id,
            ManagedOperationStatus.RUNNING,
            progress_stage=OperationProgressStage.POOLING,
            bootstrap_authority=auth,
        )
        progress.set_stage(OperationProgressStage.POOLING)
        control.checkpoint("pooling")
        resources = self.runtime.resources
        if (
            resources is None
            or resources.qdrant is None
            or resources.embedder is None
        ):
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"),
                progress_stage=OperationProgressStage.POOLING,
            )
            return
        try:
            ensure_pooling_artifacts(
                self.settings,
                corpus_id=auth.corpus_id,
                corpus_name=auth.corpus_name,
                chunk_set_id=auth.chunk_set_id,
                qdrant=resources.qdrant,
                embedder=resources.embedder,
                on_progress=progress,
            )
        except PoolEnsureError as exc:
            logger.info(
                "bootstrap 9C pooling artifact ensure failure op=%s subcause=%s: %s",
                operation_id,
                exc.subcause,
                exc,
            )
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(
                    ErrorCode.GOLD_STATE_UNAVAILABLE,
                    "pooling_artifact_unavailable",
                    message=(
                        "Gold Lab could not prepare the retrieval artifacts "
                        "required to assemble evidence for this baseline. "
                        "No baseline was published."
                    ),
                ),
                progress_stage=OperationProgressStage.POOLING,
            )
            return
        pool_executor = HistoricalPoolArmExecutor(
            self.settings,
            qdrant=resources.qdrant,
            reranker=resources.reranker,
        )
        try:
            try:
                pool_result = run_gold_pool(
                    self.settings,
                    run_path=staging_path,
                    force=True,
                    executor=pool_executor,
                    on_progress=progress,
                )
            except PoolPreRunError as exc:
                logger.info(
                    "bootstrap 9C pre-run failure op=%s category=%s: %s",
                    operation_id,
                    getattr(exc, "category", None),
                    exc,
                )
                if getattr(exc, "category", None) == "pooling_artifact":
                    _fail_op(
                        self.operations,
                        workspace_id=workspace_id,
                        operation_id=operation_id,
                        error=_app(
                            ErrorCode.GOLD_STATE_UNAVAILABLE,
                            "pooling_artifact_unavailable",
                            message=(
                                "Gold Lab could not prepare the retrieval artifacts "
                                "required to assemble evidence for this baseline. "
                                "No baseline was published."
                            ),
                        ),
                        progress_stage=OperationProgressStage.POOLING,
                    )
                    return
                _fail_op(
                    self.operations,
                    workspace_id=workspace_id,
                    operation_id=operation_id,
                    error=_app(ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"),
                    progress_stage=OperationProgressStage.POOLING,
                )
                return
        finally:
            pool_executor.close()

        if (
            pool_result.exit_code == 2
            or pool_result.run is None
            or pool_result.output_path is None
        ):
            logger.error(
                "bootstrap 9C persistence/infrastructure failure op=%s: %s",
                operation_id,
                pool_result.message,
            )
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"),
                progress_stage=OperationProgressStage.POOLING,
            )
            return

        run = pool_result.run
        pool_targeted = auth.proposal_succeeded
        pool_succeeded = int(run.pool_successful_case_count or 0)
        pool_failed = max(0, pool_targeted - pool_succeeded)
        reviewable = sum(1 for c in run.cases if is_reviewable_case(c))
        auth = auth.model_copy(
            update={
                "pool_targeted": pool_targeted,
                "pool_succeeded": pool_succeeded,
                "pool_failed": pool_failed,
                "reviewable_case_count": reviewable,
            }
        )
        if reviewable < 1:
            self.operations.update_status(
                workspace_id,
                operation_id,
                ManagedOperationStatus.RUNNING,
                bootstrap_authority=auth,
                progress_stage=OperationProgressStage.POOLING,
            )
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(ErrorCode.GOLD_CONFLICT, "zero_reviewable_cases"),
                progress_stage=OperationProgressStage.POOLING,
            )
            return

        # --- optional 9D ---
        if auth.prelabel_enabled:
            self.operations.update_status(
                workspace_id,
                operation_id,
                ManagedOperationStatus.RUNNING,
                progress_stage=OperationProgressStage.PRELABELING,
                bootstrap_authority=auth,
            )
            progress.set_stage(OperationProgressStage.PRELABELING)
            control.checkpoint("prelabeling")
            try:
                pre_result = run_gold_prelabel(
                    self.settings,
                    run_path=staging_path,
                    force=True,
                    on_progress=progress,
                )
            except PrelabelPreRunError as exc:
                logger.info("bootstrap 9D pre-run failure op=%s: %s", operation_id, exc)
                _fail_op(
                    self.operations,
                    workspace_id=workspace_id,
                    operation_id=operation_id,
                    error=_app(
                        ErrorCode.GOLD_CONFLICT,
                        "prelabel_stage_cannot_start",
                    ),
                    progress_stage=OperationProgressStage.PRELABELING,
                )
                return
            if (
                pre_result.exit_code == 2
                or pre_result.run is None
                or pre_result.output_path is None
            ):
                logger.error(
                    "bootstrap 9D persistence/infrastructure failure op=%s: %s",
                    operation_id,
                    pre_result.message,
                )
                _fail_op(
                    self.operations,
                    workspace_id=workspace_id,
                    operation_id=operation_id,
                    error=_app(ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"),
                    progress_stage=OperationProgressStage.PRELABELING,
                )
                return
            run = pre_result.run
            stage = run.prelabeling
            targeted = int(stage.targeted_case_count) if stage is not None else 0
            succeeded = int(stage.successful_case_count) if stage is not None else 0
            failed = int(stage.failed_case_count) if stage is not None else 0
            if stage is None:
                logger.error(
                    "bootstrap 9D completed without durable prelabeling stage op=%s",
                    operation_id,
                )
                _fail_op(
                    self.operations,
                    workspace_id=workspace_id,
                    operation_id=operation_id,
                    error=_app(ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure"),
                    progress_stage=OperationProgressStage.PRELABELING,
                )
                return
            auth = auth.model_copy(
                update={
                    "prelabel_targeted": targeted,
                    "prelabel_succeeded": succeeded,
                    "prelabel_failed": failed,
                    "reviewable_case_count": sum(
                        1 for c in run.cases if is_reviewable_case(c)
                    ),
                }
            )
        else:
            auth = auth.model_copy(
                update={
                    "prelabel_targeted": 0,
                    "prelabel_succeeded": 0,
                    "prelabel_failed": 0,
                }
            )

        auth = auth.model_copy(
            update={
                "reviewable_case_count": sum(
                    1 for c in run.cases if is_reviewable_case(c)
                )
            }
        )
        if auth.reviewable_case_count < 1:
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(ErrorCode.GOLD_CONFLICT, "zero_reviewable_cases"),
            )
            return

        # --- final validation + hash + publish ---
        self.operations.update_status(
            workspace_id,
            operation_id,
            ManagedOperationStatus.RUNNING,
            progress_stage=OperationProgressStage.PUBLISHING,
            bootstrap_authority=auth,
        )
        try:
            assert_pristine_baseline(run)
        except GoldLabError:
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(ErrorCode.GOLD_STATE_UNAVAILABLE, "staged_run_invalid"),
            )
            return

        if run.authoring_run_id != auth.authoring_run_id:
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(ErrorCode.GOLD_STATE_UNAVAILABLE, "staged_run_invalid"),
            )
            return
        if (
            str(run.corpus_name) != auth.corpus_name
            or str(run.corpus_id) != auth.corpus_id
            or str(run.chunk_set_id) != auth.chunk_set_id
        ):
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(ErrorCode.GOLD_STATE_UNAVAILABLE, "staged_run_invalid"),
            )
            return

        try:
            pub = self.publication.resolve_snapshot(auth.corpus_name, auth.snapshot_id)
            validate_historical_chunk_identities(
                self.settings,
                run,
                corpus_name=auth.corpus_name,
                corpus_id=auth.corpus_id,
                chunk_set_id=auth.chunk_set_id,
                corpus_manifest_name=pub.identity.corpus_manifest,
            )
        except GoldLabError:
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(
                    ErrorCode.GOLD_STATE_UNAVAILABLE, "historical_identity_failure"
                ),
            )
            return
        except Exception:  # noqa: BLE001
            _fail_op(
                self.operations,
                workspace_id=workspace_id,
                operation_id=operation_id,
                error=_app(
                    ErrorCode.SNAPSHOT_UNAVAILABLE, "captured_chunk_set_unavailable"
                ),
            )
            return

        final_bytes = serialize_authoring_run_bytes(run)
        expected_sha = hashlib.sha256(final_bytes).hexdigest()
        auth = auth.model_copy(update={"expected_final_artifact_sha256": expected_sha})
        self.operations.update_status(
            workspace_id,
            operation_id,
            ManagedOperationStatus.RUNNING,
            progress_stage=OperationProgressStage.PUBLISHING,
            bootstrap_authority=auth,
        )

        control.enter_publication()
        canonical = default_authoring_run_path(
            self.settings,
            corpus_name=auth.corpus_name,
            authoring_run_id=auth.authoring_run_id,
        )

        ws_lease = WorkspaceMutationLease(self.settings, workspace_id)
        ws_lease.acquire(blocking=True)
        try:
            proj_lease = GoldLabProjectLease(self.settings, auth.project_id)
            proj_lease.acquire(blocking=True)
            try:

                def fail(err: AppError) -> None:
                    self.operations.update_status(
                        workspace_id,
                        operation_id,
                        ManagedOperationStatus.FAILED,
                        failure_summary=err.message[:512],
                        error=ManagedOperationSafeError.from_app_error(err),
                        lease=ws_lease,
                    )

                try:
                    project = self.store.get_project(auth.project_id)
                except GoldLabError:
                    fail(_app(ErrorCode.GOLD_CONFLICT, "project_drift_before_commit"))
                    return
                if (
                    project.status is not GoldProjectStatus.ACTIVE
                    or project.workspace_id != auth.workspace_id
                ):
                    fail(_app(ErrorCode.GOLD_CONFLICT, "project_drift_before_commit"))
                    return
                workspace = self.workspace_store.get(workspace_id)
                if (
                    workspace.status is not WorkspaceStatus.ACTIVE
                    or workspace.revision != auth.workspace_revision
                    or workspace.current_snapshot_id != auth.snapshot_id
                    or workspace.backing_corpus_name != auth.corpus_name
                ):
                    fail(
                        _app(
                            ErrorCode.WORKSPACE_CONFLICT,
                            "publication_drift_before_commit",
                        )
                    )
                    return
                try:
                    live = self.publication.resolve_snapshot(
                        auth.corpus_name, auth.snapshot_id
                    )
                except Exception:  # noqa: BLE001
                    fail(
                        _app(
                            ErrorCode.WORKSPACE_CONFLICT,
                            "publication_drift_before_commit",
                        )
                    )
                    return
                if (
                    str(live.identity.corpus_id) != auth.corpus_id
                    or str(live.identity.chunk_set_id) != auth.chunk_set_id
                ):
                    fail(
                        _app(
                            ErrorCode.WORKSPACE_CONFLICT,
                            "publication_drift_before_commit",
                        )
                    )
                    return

                if canonical.exists():
                    existing = canonical.read_bytes()
                    existing_sha = hashlib.sha256(existing).hexdigest()
                    if existing_sha != expected_sha:
                        fail(
                            _app(
                                ErrorCode.GOLD_STATE_UNAVAILABLE,
                                "canonical_destination_conflict",
                            )
                        )
                        return
                else:
                    canonical.parent.mkdir(parents=True, exist_ok=True)
                    write_authoring_run_bytes(canonical, final_bytes)

                self.operations.update_status(
                    workspace_id,
                    operation_id,
                    ManagedOperationStatus.RUNNING,
                    progress_stage=OperationProgressStage.FINALIZING,
                    bootstrap_authority=auth,
                    lease=ws_lease,
                )
                try:
                    admitted = self.runtime.gold_lab.resolve_eligible_baseline(
                        project_id=auth.project_id,
                        baseline_authoring_run_id=auth.authoring_run_id,
                        for_discovery=False,
                    )
                except Exception:  # noqa: BLE001
                    fail(
                        _app(
                            ErrorCode.GOLD_STATE_UNAVAILABLE,
                            "staged_run_invalid",
                        )
                    )
                    return

                reviewable = sum(1 for c in admitted.cases if is_reviewable_case(c))
                if reviewable < 1:
                    fail(_app(ErrorCode.GOLD_CONFLICT, "zero_reviewable_cases"))
                    return
                result = GoldLabBaselineBootstrapResult(
                    project_id=auth.project_id,
                    workspace_id=auth.workspace_id,
                    workspace_revision=auth.workspace_revision,
                    snapshot_id=auth.snapshot_id,
                    corpus_id=auth.corpus_id,
                    chunk_set_id=auth.chunk_set_id,
                    authoring_run_id=auth.authoring_run_id,
                    proposal_count=auth.proposal_count,
                    sampling_seed=auth.sampling_seed,
                    prelabel_enabled=auth.prelabel_enabled,
                    proposal_attempted=auth.proposal_attempted,
                    proposal_succeeded=auth.proposal_succeeded,
                    proposal_failed=auth.proposal_failed,
                    pool_targeted=auth.pool_targeted,
                    pool_succeeded=auth.pool_succeeded,
                    pool_failed=auth.pool_failed,
                    prelabel_targeted=auth.prelabel_targeted,
                    prelabel_succeeded=auth.prelabel_succeeded,
                    prelabel_failed=auth.prelabel_failed,
                    reviewable_case_count=reviewable,
                    baseline_eligible=True,
                )
                self.operations.update_status(
                    workspace_id,
                    operation_id,
                    ManagedOperationStatus.SUCCEEDED,
                    progress_stage=OperationProgressStage.READY,
                    result=result,
                    result_summary="Baseline ready.",
                    bootstrap_authority=auth,
                    lease=ws_lease,
                )
            finally:
                proj_lease.release()
        finally:
            ws_lease.release()

        # Best-effort staging cleanup after success (must not revoke success).
        try:
            delete_bootstrap_staging(
                self.settings, workspace_id=workspace_id, operation_id=operation_id
            )
        except Exception:
            logger.warning(
                "bootstrap staging cleanup failed op=%s", operation_id, exc_info=True
            )


def reconcile_gold_bootstrap_operations(runtime: Any) -> dict[str, Any]:
    """Startup reconciliation before generic interrupt_all_nonterminal()."""
    settings = runtime.settings
    ops = ManagedOperationStore(settings)
    store = GoldLabStore(settings)
    workspace_store = WorkspaceStore(settings)
    succeeded: list[str] = []
    conflicts: list[str] = []
    deferred: list[str] = []

    for workspace_id in ops._workspace_ids():
        for record in ops.list_for_workspace(workspace_id):
            if record.kind is not ManagedOperationKind.GOLD_LAB_BASELINE_BOOTSTRAP:
                continue
            if record.status not in _NONTERMINAL:
                continue
            auth = record.bootstrap_authority
            if auth is None:
                deferred.append(record.operation_id)
                continue
            canonical = default_authoring_run_path(
                settings,
                corpus_name=auth.corpus_name,
                authoring_run_id=auth.authoring_run_id,
            )
            if not canonical.is_file():
                deferred.append(record.operation_id)
                continue
            if not auth.expected_final_artifact_sha256:
                ops.update_status(
                    workspace_id,
                    record.operation_id,
                    ManagedOperationStatus.FAILED,
                    error=ManagedOperationSafeError.from_app_error(
                        _app(
                            ErrorCode.GOLD_STATE_UNAVAILABLE,
                            "canonical_recovery_conflict",
                        )
                    ),
                    failure_summary="canonical present without expected hash",
                )
                conflicts.append(record.operation_id)
                continue
            raw = canonical.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != auth.expected_final_artifact_sha256:
                ops.update_status(
                    workspace_id,
                    record.operation_id,
                    ManagedOperationStatus.FAILED,
                    error=ManagedOperationSafeError.from_app_error(
                        _app(
                            ErrorCode.GOLD_STATE_UNAVAILABLE,
                            "canonical_recovery_conflict",
                        )
                    ),
                    failure_summary="canonical hash mismatch",
                )
                conflicts.append(record.operation_id)
                continue
            # Exact hash — check current eligibility.
            try:
                project = store.get_project(auth.project_id)
                workspace = workspace_store.get(auth.workspace_id)
                if (
                    project.status is not GoldProjectStatus.ACTIVE
                    or project.workspace_id != auth.workspace_id
                    or workspace.status is not WorkspaceStatus.ACTIVE
                    or workspace.revision != auth.workspace_revision
                    or workspace.current_snapshot_id != auth.snapshot_id
                ):
                    deferred.append(record.operation_id)
                    continue
                admitted = runtime.gold_lab.resolve_eligible_baseline(
                    project_id=auth.project_id,
                    baseline_authoring_run_id=auth.authoring_run_id,
                    for_discovery=False,
                )
            except Exception:  # noqa: BLE001
                deferred.append(record.operation_id)
                continue
            reviewable = sum(1 for c in admitted.cases if is_reviewable_case(c))
            if reviewable < 1:
                # Preserve canonical historical artifact; generic interrupt follows.
                deferred.append(record.operation_id)
                continue
            result = GoldLabBaselineBootstrapResult(
                project_id=auth.project_id,
                workspace_id=auth.workspace_id,
                workspace_revision=auth.workspace_revision,
                snapshot_id=auth.snapshot_id,
                corpus_id=auth.corpus_id,
                chunk_set_id=auth.chunk_set_id,
                authoring_run_id=auth.authoring_run_id,
                proposal_count=auth.proposal_count,
                sampling_seed=auth.sampling_seed,
                prelabel_enabled=auth.prelabel_enabled,
                proposal_attempted=auth.proposal_attempted,
                proposal_succeeded=auth.proposal_succeeded,
                proposal_failed=auth.proposal_failed,
                pool_targeted=auth.pool_targeted,
                pool_succeeded=auth.pool_succeeded,
                pool_failed=auth.pool_failed,
                prelabel_targeted=auth.prelabel_targeted,
                prelabel_succeeded=auth.prelabel_succeeded,
                prelabel_failed=auth.prelabel_failed,
                reviewable_case_count=reviewable,
                baseline_eligible=True,
            )
            ops.mark_bootstrap_reconciled_succeeded(
                workspace_id,
                record.operation_id,
                result=result,
                result_summary="Baseline ready.",
                bootstrap_authority=auth,
            )
            succeeded.append(record.operation_id)

    return {
        "reconciled_succeeded": succeeded,
        "recovery_conflicts": conflicts,
        "left_for_interrupt": deferred,
    }
