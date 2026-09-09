"""CLI shell tests for Slice 0 placeholders and doctor."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.cli import NOT_IMPLEMENTED_EXIT, main

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_root_help() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


@pytest.mark.parametrize(
    ("argv", "label"),
    [
        (["ingest", "--help"], "ingest"),
        (["query", "--help"], "query"),
        (["eval", "run", "--help"], "eval run"),
        (["eval", "compare", "--help"], "eval compare"),
        (["doctor", "--help"], "doctor"),
    ],
)
def test_subcommand_help(argv: list[str], label: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 0, label


@pytest.mark.parametrize(
    "argv",
    [
        ["ingest"],
        ["query"],
        ["eval", "run"],
        ["eval", "compare"],
    ],
)
def test_placeholders_terminate_cleanly(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    code = main(argv)
    assert code == NOT_IMPLEMENTED_EXIT
    err = capsys.readouterr().err
    assert "not implemented in this slice" in err


def test_doctor_ok_with_base_config(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["doctor", "--config", str(REPO_ROOT / "config" / "base.yaml")])
    captured = capsys.readouterr()
    assert code == 0
    assert "doctor: OK" in captured.out
