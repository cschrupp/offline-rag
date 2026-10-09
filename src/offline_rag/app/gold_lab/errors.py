"""Internal Gold Lab foundation errors (no product HTTP surface in 16F-A)."""

from __future__ import annotations


class GoldLabError(Exception):
    """Fail-closed Gold Lab persistence/contract error."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        self.reason = reason
        self.message = message or reason
        super().__init__(self.message)
