"""Passive semantic-stage instrumentation for Slice 14A.

Default is disabled / no-op. When enabled, wraps callables with monotonic
timers without changing inputs, outputs, ordering, or exceptions.

Does not import a benchmark runner, persist artifacts, or perform network I/O.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from offline_rag.evaluation.performance_14.contracts import SEMANTIC_STAGE_IDS_V1
from offline_rag.evaluation.performance_14.timing import TimingSample, timed_call, validate_stage_id

T = TypeVar("T")


@dataclass
class PassiveStageInstrumenter:
    """Opt-in stage timer sink. Disabled by default (identity pass-through)."""

    enabled: bool = False
    samples: list[TimingSample] = field(default_factory=list)

    def observe(self, stage_id: str, fn: Callable[[], T]) -> T:
        """Run ``fn``; when enabled, record a TimingSample.

        Preserves return value and exception behavior either way.
        """
        validate_stage_id(stage_id)
        if not self.enabled:
            return fn()
        value, sample = timed_call(stage_id, fn)
        self.samples.append(sample)
        return value

    def clear(self) -> None:
        self.samples.clear()

    def recorded_stage_ids(self) -> Sequence[str]:
        return tuple(sample.stage_id for sample in self.samples)


# Process-wide default instrumenter remains disabled unless a harness enables it.
DEFAULT_INSTRUMENTER = PassiveStageInstrumenter(enabled=False)


def observe_stage(stage_id: str, fn: Callable[[], T]) -> T:
    """Module-level convenience around :data:`DEFAULT_INSTRUMENTER`."""
    return DEFAULT_INSTRUMENTER.observe(stage_id, fn)


def known_stage_ids() -> tuple[str, ...]:
    return SEMANTIC_STAGE_IDS_V1
