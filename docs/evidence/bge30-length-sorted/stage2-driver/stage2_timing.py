"""Shared STOP-window and native campaign deadline calculations."""

from __future__ import annotations

import math

CAMPAIGN_EXECUTION_CEILING_SECONDS = 3600
MINIMUM_MAINTENANCE_ENTRY_WINDOW_SECONDS = 6000
RESTORATION_RESERVE_SECONDS = 900
MAINTENANCE_PREPARATION_ALLOWANCE_SECONDS = (
    MINIMUM_MAINTENANCE_ENTRY_WINDOW_SECONDS
    - CAMPAIGN_EXECUTION_CEILING_SECONDS
    - RESTORATION_RESERVE_SECONDS
)
MINIMUM_POST_PREPARATION_WINDOW_SECONDS = (
    CAMPAIGN_EXECUTION_CEILING_SECONDS + RESTORATION_RESERVE_SECONDS
)


def campaign_deadline_monotonic(
    *,
    maintenance_entry_epoch: float,
    maintenance_entry_monotonic: float,
    stop_epoch: float,
) -> float:
    """Return one deadline shared by the driver and restoration watchdog."""
    values = (maintenance_entry_epoch, maintenance_entry_monotonic, stop_epoch)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("campaign timing values must be finite")
    if stop_epoch - maintenance_entry_epoch < MINIMUM_MAINTENANCE_ENTRY_WINDOW_SECONDS:
        raise ValueError("maintenance entry lacks the required STOP window")

    stop_reserve_deadline = (
        maintenance_entry_monotonic
        + stop_epoch
        - maintenance_entry_epoch
        - RESTORATION_RESERVE_SECONDS
    )
    campaign_ceiling_deadline = (
        maintenance_entry_monotonic + CAMPAIGN_EXECUTION_CEILING_SECONDS
    )
    return min(campaign_ceiling_deadline, stop_reserve_deadline)


def remaining_campaign_seconds(
    *,
    deadline_monotonic: float,
    stop_epoch: float,
    now_monotonic: float,
    now_epoch: float,
) -> float:
    """Bound remaining execution by both shared deadline and restore reserve."""
    values = (deadline_monotonic, stop_epoch, now_monotonic, now_epoch)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("campaign timing values must be finite")
    return max(
        0.0,
        min(
            CAMPAIGN_EXECUTION_CEILING_SECONDS,
            deadline_monotonic - now_monotonic,
            stop_epoch - now_epoch - RESTORATION_RESERVE_SECONDS,
        ),
    )


def require_matching_campaign_deadline(
    *,
    supplied_deadline_monotonic: float,
    maintenance_entry_epoch: float,
    maintenance_entry_monotonic: float,
    stop_epoch: float,
) -> float:
    """Validate that the external watchdog uses the shared deadline."""
    expected = campaign_deadline_monotonic(
        maintenance_entry_epoch=maintenance_entry_epoch,
        maintenance_entry_monotonic=maintenance_entry_monotonic,
        stop_epoch=stop_epoch,
    )
    if not math.isclose(supplied_deadline_monotonic, expected, rel_tol=0, abs_tol=1):
        raise ValueError("watchdog deadline differs from native campaign deadline")
    return expected
