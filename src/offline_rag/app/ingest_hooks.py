"""Optional product-ingest test hooks (Phase 15D)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProductIngestHooks:
    """Optional test hooks — production leaves these unset."""

    after_lease_acquired: Callable[[str, Path], None] | None = None
    before_stage: Callable[[str], None] | None = None
    after_stage: Callable[[str], None] | None = None
