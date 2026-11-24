"""Run the native Stage 2 campaign or a one-request engineering smoke."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

from docker_adapter import IMAGE, LABEL, DockerHTTPAdapter, docker
from driver import Driver
from host_watchdog import available_kib
from native_contract import load_manifest, validate_bindings
from native_parity import validate as validate_native_parity

DRIVER_DIR = Path(__file__).resolve().parent
INPUTS = DRIVER_DIR.parent / "stage2-integration"
MIN_AVAILABLE_KIB = 2 * 1024 * 1024
RESTORATION_RESERVE_S = 900
EXECUTION_CEILING_S = 2400
ENGINEERING_SMOKE_EXECUTION_CEILING_S = 300
ENGINEERING_SMOKE_MIN_STOP_REMAINING_S = (
    ENGINEERING_SMOKE_EXECUTION_CEILING_S + RESTORATION_RESERVE_S
)


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _write_done(path: Path, *, status: int, session: str) -> None:
    temporary = path.with_suffix(".json.tmp")
    record = (
        json.dumps(
            {"exit_code": status, "session": session, "ended_at_unix": time.time()},
            sort_keys=True,
        )
        + "\n"
    )
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(record)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _read_baseline(snapshot_path: Path, manifest: dict) -> dict:
    baseline = json.loads(snapshot_path.read_text(encoding="utf-8"))
    current = json.loads(docker("inspect", "seneca-review"))[0]
    host = manifest["host_contract"]
    mounts = {row["destination"]: row for row in baseline.get("mounts", [])}
    if (
        baseline.get("name") != host["original_container"]
        or baseline.get("image_ref") != host["original_image_ref"]
        or mounts.get("/data", {}).get("source") != host["original_data_mount"]
        or mounts.get("/data", {}).get("rw") is not True
        or mounts.get("/models", {}).get("source") != host["model_mount"]
        or mounts.get("/models", {}).get("rw") is not False
        or current["Id"] != baseline.get("id")
        or current["State"]["Running"]
    ):
        raise RuntimeError("original container is not the captured stopped container")
    return baseline


def _check_root(root: Path, session: str) -> None:
    if not root.is_relative_to(Path("/var/tmp")):
        raise ValueError("native scratch must be under /var/tmp")
    if root.name != f"seneca-stage2-native-{session}":
        raise ValueError("native scratch name must bind to the session id")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("native scratch root is not a real directory")
    if root.stat().st_mode & 0o077:
        raise ValueError("native scratch root permissions must be 0700")


def _check_arm(root: Path, arm_name: str) -> Path:
    arm = root / arm_name
    data = arm / "data"
    if not arm.is_dir() or not data.is_dir() or arm.is_symlink() or data.is_symlink():
        raise ValueError(f"native {arm_name} arm data is missing or unsafe")
    return data


def run(options) -> dict:
    if options.root.is_symlink():
        raise ValueError("native scratch root must not be a symlink")
    root = options.root.resolve(strict=True)
    session = options.session
    if not all(char in "0123456789abcdef" for char in session) or len(session) != 16:
        raise ValueError("session must be a 16-character lowercase hex identity")
    _check_root(root, session)
    done = root / "driver_done.json"
    if done.exists() or done.with_suffix(".json.tmp").exists():
        raise RuntimeError("native session result file already exists")
    status = 1
    try:
        manifest = load_manifest(INPUTS)
        if options.models.resolve(strict=True) != Path("/srv/seneca/models"):
            raise RuntimeError(
                "native model source is not the approved host model tree"
            )
        expected_bindings = root / "A" / "preflight" / "native-bindings.json"
        if options.bindings.resolve(strict=True) != expected_bindings.resolve(
            strict=True
        ):
            raise RuntimeError("native bindings are not the verified A-arm output")
        bindings = validate_bindings(
            json.loads(options.bindings.read_text(encoding="utf-8")),
            inputs=INPUTS,
        )
        other_bindings = root / "B" / "preflight" / "native-bindings.json"
        if (
            not other_bindings.is_file()
            or other_bindings.read_bytes() != options.bindings.read_bytes()
        ):
            raise RuntimeError("independent arm preflight bindings differ")
        baseline = _read_baseline(
            options.baseline_snapshot.resolve(strict=True), manifest
        )
        if baseline.get("running") is not True:
            raise RuntimeError("captured original service state was not running")
        minimum_stop_remaining = (
            ENGINEERING_SMOKE_MIN_STOP_REMAINING_S
            if options.engineering_smoke
            else 4800
        )
        if options.stop_epoch - time.time() < minimum_stop_remaining:
            raise RuntimeError("automatic STOP reserve is below the mode minimum")
        if available_kib() < MIN_AVAILABLE_KIB:
            raise RuntimeError("host available memory is below 2 GiB")
        if shutil.disk_usage(root).free < options.minimum_free_bytes:
            raise RuntimeError("native scratch filesystem lacks required disk reserve")
        image_info = json.loads(docker("image", "inspect", IMAGE))[0]
        if image_info.get("Id") != IMAGE:
            raise RuntimeError("pinned diagnostic image is missing or differs")
        if manifest["diagnostic_image_digest"] != IMAGE:
            raise RuntimeError("native settings and adapter image identities differ")
        if docker("ps", "-aq", "--filter", f"label={LABEL}").split():
            raise RuntimeError("another Stage 2 diagnostic container is present")
        work_roots = {
            "consecutive": root / "A",
            "length_sorted_8": root / "B",
        }
        arm_data = {name: _check_arm(root, name) for name in ("A", "B")}
        if arm_data["A"].samefile(arm_data["B"]):
            raise RuntimeError("native arms do not have independent data copies")
        journal = root / "journal"
        control = root / "control"
        journal.mkdir(mode=0o700, exist_ok=True)
        control.mkdir(mode=0o700, exist_ok=True)
        driver_events = root / "driver-events.jsonl"
        heartbeat = root / "driver.heartbeat"
        if any(path.exists() for path in (driver_events, heartbeat)):
            raise RuntimeError("native session result files already exist")
        heartbeat.touch(mode=0o600, exist_ok=False)
        adapter = DockerHTTPAdapter(
            session=session,
            journal=journal,
            control=control,
            inputs=INPUTS,
            driver_dir=DRIVER_DIR,
            work_roots=work_roots,
            mode="native",
            native_models=options.models,
            native_bindings=options.bindings,
            bindings=bindings,
            shutdown_grace_seconds=30,
        )
        started = time.monotonic()

        def host_safe() -> bool:
            return (
                time.monotonic()
                < started
                + (
                    ENGINEERING_SMOKE_EXECUTION_CEILING_S
                    if options.engineering_smoke
                    else EXECUTION_CEILING_S
                )
                and options.stop_epoch - time.time() >= RESTORATION_RESERVE_S
                and available_kib() >= MIN_AVAILABLE_KIB
            )

        def emit(row: dict) -> None:
            _append_jsonl(driver_events, row)
            heartbeat.touch()

        driver = Driver(
            adapter,
            host_safe,
            emit,
            duration=(
                ENGINEERING_SMOKE_EXECUTION_CEILING_S
                if options.engineering_smoke
                else EXECUTION_CEILING_S
            ),
        )
        if options.engineering_smoke:
            driver.run_engineering_smoke()
            status = 0
            return {
                "classification": "NATIVE_ENGINEERING_SMOKE_PASS",
                "session": session,
                "submission_count": 1,
                "scientific_campaign": False,
                "retries": 0,
            }

        driver.run()
        parity = validate_native_parity(driver_events)
        parity_path = root / "native-parity.json"
        parity_path.write_text(json.dumps(parity, sort_keys=True, indent=2) + "\n")
        os.chmod(parity_path, 0o600)
        status = 0
        return {
            "classification": "NATIVE_STAGE2_COMPLETE",
            "session": session,
            "submission_count": 36,
            "retries": 0,
            "parity": parity,
        }
    finally:
        _write_done(done, status=status, session=session)
        heartbeat.touch()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--baseline-snapshot", type=Path, required=True)
    parser.add_argument("--stop-epoch", type=float, required=True)
    parser.add_argument("--minimum-free-bytes", type=int, required=True)
    parser.add_argument(
        "--engineering-smoke",
        action="store_true",
        help="run one isolated native request to qualify observer wiring only",
    )
    options = parser.parse_args()
    result = run(options)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
