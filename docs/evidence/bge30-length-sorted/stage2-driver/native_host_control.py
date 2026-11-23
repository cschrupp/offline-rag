"""Read-only baseline capture and isolated-session restoration for native Stage 2."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from docker_adapter import docker
from docker_watchdog import supervise as supervise_docker_session

APP_NAME = "seneca-review"
EXPECTED_APP_IMAGE_REF = "seneca-review:9c92e706c4b9"


def inspect_named(name: str) -> dict:
    rows = json.loads(docker("inspect", name))
    if len(rows) != 1 or rows[0]["Name"] != "/" + name:
        raise RuntimeError("container identity is missing or ambiguous")
    row = rows[0]
    # Deliberately omit Config.Env, command arguments, and labels from evidence.
    return {
        "name": name,
        "id": row["Id"],
        "image_id": row["Image"],
        "image_ref": row["Config"]["Image"],
        "running": bool(row["State"]["Running"]),
        "restart_policy": row["HostConfig"]["RestartPolicy"],
        "network_mode": row["HostConfig"]["NetworkMode"],
        "mounts": sorted(
            [
                {
                    "type": item["Type"],
                    "source": str(Path(item["Source"]).resolve()),
                    "destination": item["Destination"],
                    "rw": bool(item["RW"]),
                }
                for item in row.get("Mounts", [])
            ],
            key=lambda item: item["destination"],
        ),
    }


def health(container_id: str) -> None:
    for endpoint in ("/health/live", "/health/ready"):
        docker(
            "exec",
            container_id,
            "python",
            "-B",
            "-c",
            "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/' + sys.argv[1], timeout=3).status == 200 else 1)",
            endpoint.lstrip("/"),
            timeout=8,
        )


def capture(path: Path) -> None:
    baseline = inspect_named(APP_NAME)
    if not baseline["running"]:
        raise RuntimeError("original Seneca container is not running")
    if baseline["image_ref"] != EXPECTED_APP_IMAGE_REF:
        raise RuntimeError("original Seneca image is not the accepted deployment")
    mounts = {mount["destination"]: mount for mount in baseline["mounts"]}
    data_mount = mounts.get("/data")
    models_mount = mounts.get("/models")
    if (
        data_mount is None
        or data_mount["source"] != "/srv/seneca/data"
        or not data_mount["rw"]
        or models_mount is None
        or models_mount["source"] != "/srv/seneca/models"
        or models_mount["rw"]
    ):
        raise RuntimeError("original Seneca data/model mounts are incomplete")
    health(baseline["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError("refusing to overwrite an existing baseline snapshot")
    path.write_text(json.dumps(baseline, sort_keys=True, indent=2) + "\n")
    os.chmod(path, 0o600)


def verify(
    path: Path,
    *,
    start_if_stopped: bool,
    metadata_baseline: Path | None = None,
    cpuset: str | None = None,
) -> None:
    baseline = json.loads(path.read_text(encoding="utf-8"))
    current = inspect_named(APP_NAME)
    if current["id"] != baseline["id"]:
        raise RuntimeError("original container identity changed")
    identity_keys = (
        "image_id",
        "image_ref",
        "restart_policy",
        "network_mode",
        "mounts",
    )
    if any(current[key] != baseline[key] for key in identity_keys):
        raise RuntimeError("original image, mounts, or restart policy changed")
    if not current["running"] and start_if_stopped:
        docker("start", baseline["id"], timeout=60)
        current = inspect_named(APP_NAME)
    if not current["running"]:
        raise RuntimeError("original service is not running")
    health(current["id"])
    if metadata_baseline is not None:
        if not cpuset:
            raise ValueError("publication verification requires its CPU set")
        repository_root = Path(__file__).resolve().parents[4]
        script = (
            repository_root
            / "docs/evidence/bge30-length-sorted/stage2-driver/preflight_host.sh"
        )
        result = subprocess.run(
            [
                "bash",
                str(script),
                "metadata",
                "/srv/seneca/data",
                "/srv/seneca/models",
                cpuset,
            ],
            cwd=repository_root,
            capture_output=True,
            text=True,
            timeout=180,
            check=True,
        )
        observed = json.loads(result.stdout)
        expected = json.loads(metadata_baseline.read_text(encoding="utf-8"))
        if observed != expected:
            raise RuntimeError("published workspace/snapshot metadata changed")


def verify_scratch_unowned(root: Path) -> None:
    containers = docker("ps", "-aq").split()
    if containers:
        for item in json.loads(docker("inspect", *containers)):
            for mount in item.get("Mounts", []):
                source = Path(mount.get("Source", "/")).resolve()
                if source == root or root in source.parents:
                    raise RuntimeError("a Docker container still mounts native scratch")
    for strategy in ("A", "B"):
        assert_qdrant_unowned(root / strategy / "data" / "qdrant")


def assert_qdrant_unowned(path: Path) -> None:
    if not path.is_dir():
        raise RuntimeError("isolated Qdrant storage is missing")
    try:
        lsof = subprocess.run(
            ["lsof", "+D", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "lsof is required; do not install it in this tranche"
        ) from exc
    if lsof.returncode not in {0, 1} or lsof.stderr.strip():
        raise RuntimeError("lsof Qdrant ownership check could not complete")
    lines = [line for line in lsof.stdout.splitlines() if line.strip()]
    if len(lines) > 1:
        raise RuntimeError("a process already holds isolated Qdrant storage")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("snapshot", type=Path)
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("snapshot", type=Path)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("snapshot", type=Path)
    verify_parser.add_argument("--scratch", type=Path, required=True)
    verify_parser.add_argument("--metadata-baseline", type=Path)
    verify_parser.add_argument("--cpuset")
    qdrant_parser = commands.add_parser("check-qdrant")
    qdrant_parser.add_argument("path", type=Path)
    if len(sys.argv) > 1 and sys.argv[1] == "supervise":
        supervise_parser = commands.add_parser("supervise")
        supervise_parser.add_argument("--session", required=True)
        supervise_parser.add_argument("--container", required=True)
        supervise_parser.add_argument("--scratch", type=Path, required=True)
        supervise_parser.add_argument("--snapshot", type=Path, required=True)
        supervise_parser.add_argument("--done", type=Path, required=True)
        supervise_parser.add_argument("--abort", type=Path, required=True)
        supervise_parser.add_argument("--ceiling-epoch", type=float, required=True)
        supervise_parser.add_argument("--metadata-baseline", type=Path, required=True)
        supervise_parser.add_argument("--cpuset", required=True)
    options = parser.parse_args()
    if options.command == "capture":
        capture(options.snapshot)
    elif options.command == "restore":
        verify(options.snapshot, start_if_stopped=True)
    elif options.command == "verify":
        verify_scratch_unowned(options.scratch.resolve(strict=True))
        verify(
            options.snapshot,
            start_if_stopped=False,
            metadata_baseline=options.metadata_baseline,
            cpuset=options.cpuset,
        )
    elif options.command == "check-qdrant":
        assert_qdrant_unowned(options.path.resolve(strict=True))
    else:
        root = options.scratch.resolve(strict=True)
        snapshot = options.snapshot.resolve(strict=True)
        restore = [sys.executable, __file__, "restore", str(snapshot)]
        verify_command = [
            sys.executable,
            __file__,
            "verify",
            str(snapshot),
            "--scratch",
            str(root),
            "--metadata-baseline",
            str(options.metadata_baseline.resolve(strict=True)),
            "--cpuset",
            options.cpuset,
        ]
        deadline = options.ceiling_epoch
        if deadline <= 0:
            raise ValueError("watchdog deadline must be a monotonic epoch")
        status = supervise_docker_session(
            name=options.container,
            session=options.session,
            deadline=deadline,
            done=root / options.done,
            abort=root / options.abort,
            restore=restore,
            verify=verify_command,
            stop_timeout=30,
        )
        if status == 0:
            done_record = json.loads((root / options.done).read_text(encoding="utf-8"))
            if done_record.get("exit_code") != 0:
                status = 1
        raise SystemExit(status)


if __name__ == "__main__":
    main()
