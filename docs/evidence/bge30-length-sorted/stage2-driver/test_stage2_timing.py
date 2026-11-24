import pytest
from stage2_timing import (
    CAMPAIGN_EXECUTION_CEILING_SECONDS,
    MAINTENANCE_PREPARATION_ALLOWANCE_SECONDS,
    MINIMUM_MAINTENANCE_ENTRY_WINDOW_SECONDS,
    RESTORATION_RESERVE_SECONDS,
    campaign_deadline_monotonic,
    remaining_campaign_seconds,
    require_matching_campaign_deadline,
)


def test_maintenance_preparation_consumes_campaign_ceiling():
    deadline = campaign_deadline_monotonic(
        maintenance_entry_epoch=1000,
        maintenance_entry_monotonic=50,
        stop_epoch=7000,
    )

    assert deadline == 3650
    assert (
        remaining_campaign_seconds(
            deadline_monotonic=deadline,
            stop_epoch=7000,
            now_monotonic=950,
            now_epoch=1900,
        )
        == 2700
    )


def test_stop_reserve_can_tighten_campaign_deadline():
    deadline = campaign_deadline_monotonic(
        maintenance_entry_epoch=1000,
        maintenance_entry_monotonic=50,
        stop_epoch=7000,
    )

    assert deadline == 3650
    assert (
        remaining_campaign_seconds(
            deadline_monotonic=deadline,
            stop_epoch=7000,
            now_monotonic=3550,
            now_epoch=7000 - RESTORATION_RESERVE_SECONDS - 100,
        )
        == 100
    )


def test_maintenance_entry_requires_full_stop_window():
    with pytest.raises(ValueError, match="required STOP window"):
        campaign_deadline_monotonic(
            maintenance_entry_epoch=1000,
            maintenance_entry_monotonic=50,
            stop_epoch=1000 + MINIMUM_MAINTENANCE_ENTRY_WINDOW_SECONDS - 1,
        )


def test_watchdog_must_use_driver_campaign_deadline():
    expected = campaign_deadline_monotonic(
        maintenance_entry_epoch=1000,
        maintenance_entry_monotonic=50,
        stop_epoch=7000,
    )
    assert (
        require_matching_campaign_deadline(
            supplied_deadline_monotonic=expected,
            maintenance_entry_epoch=1000,
            maintenance_entry_monotonic=50,
            stop_epoch=7000,
        )
        == expected
    )

    with pytest.raises(ValueError, match="differs"):
        require_matching_campaign_deadline(
            supplied_deadline_monotonic=expected + 2,
            maintenance_entry_epoch=1000,
            maintenance_entry_monotonic=50,
            stop_epoch=7000,
        )


def test_campaign_timing_contract_constants_are_explicit():
    assert CAMPAIGN_EXECUTION_CEILING_SECONDS == 3600
    assert MINIMUM_MAINTENANCE_ENTRY_WINDOW_SECONDS == 6000
    assert RESTORATION_RESERVE_SECONDS == 900
    assert MAINTENANCE_PREPARATION_ALLOWANCE_SECONDS == 1500
