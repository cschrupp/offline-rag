"""Slice 16A — workspace contracts and persistence foundation.

No HTTP routes or UI. Lifecycle orchestration is deferred to 16B.
"""

from offline_rag.app.workspace.journal import (
    EmptyTransitionCoordinator,
    EmptyTransitionJournal,
    EmptyTransitionPhase,
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
    new_source_id,
    new_workspace_id,
    serialize_revision,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.retirement import (
    PublicationRetirementRecord,
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
    "WorkspaceRecord",
    "WorkspaceRevision",
    "WorkspaceStatus",
    "WorkspaceStore",
    "advance_revision",
    "assert_empty_invariant",
    "assert_non_empty_invariant",
    "new_source_id",
    "new_workspace_id",
    "restore_current_publication_pointer",
    "retire_current_publication",
    "serialize_revision",
]
