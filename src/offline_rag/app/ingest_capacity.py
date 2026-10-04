"""Process-scoped ingest-class capacity gate (Phase 15D / D18).

15F generalizes the implementation to ``CapacityGate``; this module keeps the
historical import path and name for accepted 15D callers/tests.
"""

from __future__ import annotations

from offline_rag.app.capacity import CapacityGate

# Backward-compatible alias — semantics unchanged from 15D.
IngestCapacityGate = CapacityGate

__all__ = ["CapacityGate", "IngestCapacityGate"]
