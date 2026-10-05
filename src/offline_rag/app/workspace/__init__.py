"""Slice 16A — workspace contracts and persistence foundation.

No HTTP routes or UI. Lifecycle orchestration is deferred to 16B.

Lock acquisition order when both resources are required (frozen for 16B):

    workspace lease → corpus lease
"""

from offline_rag.app.workspace.journal import (
    EmptyTransitionCoordinator,
    EmptyTransitionJournal,
    EmptyTransitionPhase,
)
from offline_rag.app.workspace.leases import (
    WorkspaceMutationLease,
    workspace_lease_path,
)
from offline_rag.app.workspace.models import (
    ManagedOperationKind,
    ManagedOperationRecord,
    ManagedOperationStatus,
    SourceVersionRecord,
    WorkspaceRecord,
    WorkspaceRevision,
    WorkspaceStatus,
    advance_revision,
    assert_empty_invariant,
    assert_non_empty_invariant,
    canonical_operation_fingerprint,
    new_source_id,
    new_workspace_id,
    serialize_revision,
)
from offline_rag.app.workspace.mutation_ops import (
    ManagedOperationStore,
    assert_legal_status_transition,
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
    "EmptyTransitionCoordinator",
    "EmptyTransitionJournal",
    "EmptyTransitionPhase",
    "ManagedOperationKind",
    "ManagedOperationRecord",
    "ManagedOperationStatus",
    "ManagedOperationStore",
    "PublicationRetirementRecord",
    "RawSourceVault",
    "SourceVersionRecord",
    "VaultObjectMeta",
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
    "new_source_id",
    "new_workspace_id",
    "restore_current_publication_pointer",
    "retire_current_publication",
    "serialize_revision",
    "workspace_lease_path",
]
