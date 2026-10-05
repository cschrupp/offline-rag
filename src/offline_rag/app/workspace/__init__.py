"""Slice 16A/16B — workspace contracts, persistence, and lifecycle core.

16A froze the durable contracts. 16B adds the application-layer lifecycle:
publication/workspace transition coordination, source lineage history, revision
ETag parsing, create idempotency, and desired-set projection onto Slice-15
ingest. No HTTP routes or UI live here.

Lock acquisition order when both resources are required (frozen in 16A):

    workspace lease → corpus lease
"""

from offline_rag.app.workspace.create_idempotency import (
    WorkspaceCreateCatalog,
    WorkspaceCreateReservation,
    create_request_fingerprint,
)
from offline_rag.app.workspace.etag import format_etag, parse_if_match
from offline_rag.app.workspace.history import SourceHistoryStore
from offline_rag.app.workspace.journal import (
    EmptyTransitionCoordinator,
    EmptyTransitionJournal,
    EmptyTransitionPhase,
)
from offline_rag.app.workspace.leases import (
    WorkspaceMutationLease,
    workspace_lease_path,
)
from offline_rag.app.workspace.lifecycle import (
    SourceUpload,
    WorkspaceLifecycleService,
)
from offline_rag.app.workspace.models import (
    ManagedOperationKind,
    ManagedOperationRecord,
    ManagedOperationResult,
    ManagedOperationSafeError,
    ManagedOperationStatus,
    OperationProgressStage,
    SourceVersionRecord,
    WorkspaceRecord,
    WorkspaceRevision,
    WorkspaceStatus,
    advance_revision,
    assert_empty_invariant,
    assert_non_empty_invariant,
    canonical_operation_fingerprint,
    new_empty_workspace,
    new_source_id,
    new_workspace_id,
    serialize_revision,
)
from offline_rag.app.workspace.mutation_ops import (
    ManagedOperationStore,
    OperationLocator,
    assert_legal_status_transition,
)
from offline_rag.app.workspace.projection import (
    DesiredSetMaterialization,
    MaterializedSource,
    enforce_desired_set_limits,
    materialize_desired_sources,
    upload_source_name,
)
from offline_rag.app.workspace.publication_journal import (
    LineageDelta,
    NonEmptyPublicationCoordinator,
    NonEmptyPublicationJournal,
    NonEmptyPublicationPhase,
    PublicationMutationKind,
    SourceVersionRef,
)
from offline_rag.app.workspace.retirement import (
    PublicationRetirementRecord,
    clear_retirement_marker,
    restore_current_publication_pointer,
    retire_current_publication,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.vault import RawSourceVault, VaultObjectMeta

__all__ = [
    "DesiredSetMaterialization",
    "EmptyTransitionCoordinator",
    "EmptyTransitionJournal",
    "EmptyTransitionPhase",
    "LineageDelta",
    "ManagedOperationKind",
    "ManagedOperationRecord",
    "ManagedOperationResult",
    "ManagedOperationSafeError",
    "ManagedOperationStatus",
    "ManagedOperationStore",
    "MaterializedSource",
    "NonEmptyPublicationCoordinator",
    "NonEmptyPublicationJournal",
    "NonEmptyPublicationPhase",
    "OperationLocator",
    "OperationProgressStage",
    "PublicationMutationKind",
    "PublicationRetirementRecord",
    "RawSourceVault",
    "SourceHistoryStore",
    "SourceUpload",
    "SourceVersionRecord",
    "SourceVersionRef",
    "VaultObjectMeta",
    "WorkspaceCreateCatalog",
    "WorkspaceCreateReservation",
    "WorkspaceLifecycleService",
    "WorkspaceMutationLease",
    "WorkspaceRecord",
    "WorkspaceRevision",
    "WorkspaceStatus",
    "WorkspaceStore",
    "advance_revision",
    "assert_empty_invariant",
    "assert_legal_status_transition",
    "assert_non_empty_invariant",
    "canonical_operation_fingerprint",
    "clear_retirement_marker",
    "create_request_fingerprint",
    "enforce_desired_set_limits",
    "format_etag",
    "materialize_desired_sources",
    "new_empty_workspace",
    "new_source_id",
    "new_workspace_id",
    "parse_if_match",
    "restore_current_publication_pointer",
    "retire_current_publication",
    "serialize_revision",
    "upload_source_name",
    "workspace_lease_path",
]
