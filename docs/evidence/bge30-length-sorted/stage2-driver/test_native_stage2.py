import shutil
import uuid
from pathlib import Path

import pytest
from driver import schedule
from native_stage2 import _check_arm, _check_root, _validate_lifecycle_campaign
from stage2_settings import configure_fixture_generation

from offline_rag.config.models import AppSettings


def test_native_arm_names_map_to_independent_data_directories():
    session = uuid.uuid4().hex[:16]
    root = Path("/var/tmp") / f"seneca-stage2-native-{session}"
    root.mkdir(mode=0o700)
    try:
        (root / "A" / "data").mkdir(parents=True)
        (root / "B" / "data").mkdir(parents=True)

        _check_root(root, session)

        assert _check_arm(root, "A") == root / "A" / "data"
        assert _check_arm(root, "B") == root / "B" / "data"
        assert not (root / "A" / "data").samefile(root / "B" / "data")
    finally:
        shutil.rmtree(root)


def test_native_root_rejects_group_or_world_access(tmp_path):
    session = uuid.uuid4().hex[:16]
    root = Path("/var/tmp") / f"seneca-stage2-native-{session}"
    root.mkdir(mode=0o700)
    root.chmod(0o750)

    try:
        with pytest.raises(ValueError, match="permissions must be 0700"):
            _check_root(root, session)
    finally:
        shutil.rmtree(root)


def test_native_arm_rejects_symlinked_data(tmp_path):
    root = tmp_path / "root"
    (root / "A").mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    (root / "A" / "data").symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="missing or unsafe"):
        _check_arm(root, "A")


def test_native_fixture_generation_is_valid_under_strict_offline_policy():
    settings = AppSettings()
    configured = configure_fixture_generation(settings)

    assert configured.project.strict_offline is True
    assert configured.generation.base_url == "http://127.0.0.1:9/v1"
    assert configured.generation.model == "stage2-synthetic-provider"
    assert configured.generation.api_key is None


def test_lifecycle_campaign_requires_all_eight_correlated_settlements(tmp_path):
    import json
    from dataclasses import asdict

    rows = []
    for wave in schedule("lifecycle"):
        case = wave[0]
        terminal = "timed_out" if case.case == "deadline" else "cancelled"
        reason = {
            "disconnect_before": "client_disconnect",
            "disconnect_during": "client_disconnect",
            "deadline": "query_deadline_exceeded",
            "drain": "shutdown",
        }[case.case]
        transport = (
            "client_disconnected" if case.case.startswith("disconnect") else "response"
        )
        rows.extend(
            (
                {"event": "send_attempt", **asdict(case)},
                {
                    "event": "settled",
                    "ordinal": case.ordinal,
                    "settled": True,
                    "admission": "accepted",
                    "operation": f"op-{case.ordinal}",
                    "terminal": terminal,
                    "reason": reason,
                    "worker_returned": True,
                    "http_status": 504 if case.case == "deadline" else None,
                    "transport": transport,
                },
            )
        )
    journal = tmp_path / "driver-events.jsonl"
    journal.write_text("".join(json.dumps(row) + "\n" for row in rows))

    summary = _validate_lifecycle_campaign(journal)

    assert summary["classification"] == "NATIVE_STAGE2_LIFECYCLE_COMPLETE"
    assert summary["submission_count"] == 8
    assert len(summary["outcomes"]) == 8

    journal.write_text("".join(json.dumps(row) + "\n" for row in rows[:-2]))
    with pytest.raises(RuntimeError, match="coverage differs"):
        _validate_lifecycle_campaign(journal)
