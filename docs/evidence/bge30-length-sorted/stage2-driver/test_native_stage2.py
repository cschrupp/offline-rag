import shutil
import uuid
from pathlib import Path

import pytest
from native_stage2 import _check_arm, _check_root
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
