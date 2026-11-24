"""Read-only baseline capture and isolated-session restoration for native Stage 2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from docker_adapter import LABEL, docker
from docker_watchdog import supervise as supervise_docker_session
from stage2_timing import require_matching_campaign_deadline

APP_NAME = "seneca-review"
EXPECTED_APP_IMAGE_REF = "seneca-review:9c92e706c4b9"
STAGE2_CONTAINER_PREFIX = "seneca-stage2-"
COMPLETION_SCHEMA = "seneca-rich2-stage1-completion-v1"
RICH2_BINDING_SHA256 = (
    "b3e2fcae6140ca3d1e87c3d925f3ec281d8c48889ff44723739def4cbd0db7a1"
)


def rich2_stage1_container_identity(session: str) -> tuple[str, str]:
    """Return the exact name and ownership label watched by the Stage 2 tools."""
    if re.fullmatch(r"[a-f0-9]{16}", session) is None:
        raise ValueError("invalid diagnostic session identity")
    return (
        STAGE2_CONTAINER_PREFIX + session,
        f"{LABEL}={session}",
    )


def rich2_stage1_scratch_root(session: str) -> Path:
    """Return the preflight-compatible scratch root for a valid session."""
    rich2_stage1_container_identity(session)
    return Path("/var/tmp") / f"seneca-rich2-stage1-{session}"


def mark_watchdog_failure(*, done: Path, abort: Path) -> None:
    """Release a preflight-failed session to the independent restore watchdog."""
    abort.touch(exist_ok=True)
    done.touch(exist_ok=True)


def write_completion_record(
    *, done: Path, session: str, exit_code: int, diagnostic_result: Path
) -> None:
    """Atomically publish a successful one-shot completion for the watchdog."""
    rich2_stage1_container_identity(session)
    if type(exit_code) is not int or exit_code != 0:
        raise ValueError("only a successful diagnostic can complete the session")
    result = json.loads(diagnostic_result.read_text(encoding="utf-8"))
    validate_rich2_completion_observation(result)
    record = {
        "schema": COMPLETION_SCHEMA,
        "session": session,
        "exit_code": exit_code,
        "ended_at_unix": time.time(),
    }
    temporary = done.with_name(done.name + ".tmp")
    if done.exists() or temporary.exists():
        raise FileExistsError("completion record already exists")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, done)
        temporary.unlink()
        directory_fd = os.open(done.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def validate_rich2_completion_observation(result: object) -> None:
    """Validate the committed binding and essential one-shot result evidence."""
    if not isinstance(result, dict):
        raise TypeError("diagnostic result is not a valid Rich 2 observation")
    driver_dir = Path(__file__).resolve().parent
    binding_path = (
        driver_dir.parent / "stage2-integration" / "rich2-stage1-binding.json"
    )
    binding_bytes = binding_path.read_bytes()
    binding_sha256 = hashlib.sha256(binding_bytes).hexdigest()
    if binding_sha256 != RICH2_BINDING_SHA256:
        raise RuntimeError("committed Rich 2 binding identity changed")
    binding = json.loads(binding_bytes)
    expected_identity = {
        "binding_sha256": binding_sha256,
        "workspace_id": binding["workspace"]["workspace_id"],
        "workspace_revision": binding["workspace"]["revision"],
        "source_inventory_sha256": binding["workspace"]["source_inventory_sha256"],
        "source_ids": sorted(binding["source_scope"]["source_ids"]),
        "document_ids": sorted(binding["source_scope"]["document_ids"]),
        "snapshot_id": binding["publication"]["snapshot_id"],
        "snapshot_manifest_sha256": binding["publication"]["snapshot_manifest_sha256"],
        "scientific_settings_sha256": binding["publication"]["science_settings_sha256"],
        "question_sha256": binding["question"]["normalized_sha256"],
        "source_scope": "all_active",
    }
    if any(result.get(key) != value for key, value in expected_identity.items()):
        raise RuntimeError(
            "diagnostic result differs from the committed Rich 2 binding"
        )
    candidate_ids = result.get("fused_candidate_ids")
    candidate_document_ids = result.get("candidate_document_ids")
    score_pairs = result.get("candidate_score_associations")
    ranked_ids = result.get("ranked_candidate_ids")
    anchor_ids = result.get("anchor_ids")
    evidence_unit_ids = result.get("evidence_unit_ids")
    if (
        result.get("schema") != "seneca-rich2-stage1-observation-v1"
        or result.get("status") != "executed_single_assembler_call"
        or result.get("generation_invoked") is not False
        or result.get("external_network") is not False
        or binding.get("expected_candidate_count") != 10
        or result.get("fused_candidate_count") != 10
        or not isinstance(candidate_ids, list)
        or len(candidate_ids) != 10
        or not isinstance(candidate_document_ids, list)
        or not isinstance(score_pairs, list)
        or not isinstance(ranked_ids, list)
        or not isinstance(anchor_ids, list)
        or not isinstance(evidence_unit_ids, list)
        or result.get("ranking_tie_break") != "chunk-id-asc-v1"
        or type(result.get("context_token_count")) is not int
        or result["context_token_count"] < 0
        or type(result.get("evidence_unit_count")) is not int
        or result.get("evidence_unit_count") != len(evidence_unit_ids)
        or not _is_sha256(result.get("packed_context_sha256"))
    ):
        raise RuntimeError(
            "diagnostic result is incomplete or not a successful Rich 2 probe"
        )
    if result.get("fused_candidate_ids_sha256") != _sha256_json(candidate_ids):
        raise RuntimeError("diagnostic candidate identity hash is inconsistent")
    if result.get("anchor_ids_sha256") != _sha256_json(anchor_ids):
        raise RuntimeError("diagnostic anchor identity hash is inconsistent")
    if result.get("evidence_unit_ids_sha256") != _sha256_json(evidence_unit_ids):
        raise RuntimeError("diagnostic evidence identity hash is inconsistent")
    expected_document_id = binding["source_scope"]["document_ids"][0]
    for association in score_pairs:
        if (
            not isinstance(association, dict)
            or association.get("candidate_id_sha256")
            != hashlib.sha256(
                str(association.get("candidate_id", "")).encode()
            ).hexdigest()
        ):
            raise RuntimeError("diagnostic candidate-score association is incomplete")
    from rich2_stage1 import validate_observation

    validate_observation(
        candidate_ids=candidate_ids,
        candidate_document_ids=candidate_document_ids,
        expected_document_id=expected_document_id,
        score_pairs=score_pairs,
        ranked_ids=ranked_ids,
        anchor_ids=anchor_ids,
        evidence_unit_ids=evidence_unit_ids,
        expected_count=10,
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _sha256_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_completion_record(
    path: Path, *, session: str, layout: str = "rich2-stage1"
) -> None:
    """Require a complete, session-bound success record before accepting done."""
    rich2_stage1_container_identity(session)
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise TypeError("watchdog completion record is invalid")
    ended_at = record.get("ended_at_unix")
    expected_keys = {"session", "exit_code", "ended_at_unix"}
    if layout == "rich2-stage1":
        expected_keys.add("schema")
    if (
        set(record) != expected_keys
        or (layout == "rich2-stage1" and record.get("schema") != COMPLETION_SCHEMA)
        or record.get("session") != session
        or type(record.get("exit_code")) is not int
        or record["exit_code"] != 0
        or isinstance(ended_at, bool)
        or not isinstance(ended_at, (int, float))
        or not math.isfinite(ended_at)
        or ended_at <= 0
    ):
        raise RuntimeError("watchdog completion record is invalid")


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


def health(container_id: str, *, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    health_errors = (subprocess.CalledProcessError, subprocess.TimeoutExpired)
    for endpoint in ("/health/live", "/health/ready"):
        while True:
            try:
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
                break
            except health_errors:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)


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
    metadata_mode: str = "metadata",
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
                metadata_mode,
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


def verify_scratch_unowned(
    root: Path,
    *,
    layout: str = "stage2",
    allow_missing_qdrant: bool = False,
) -> None:
    containers = docker("ps", "-aq").split()
    if containers:
        for item in json.loads(docker("inspect", *containers)):
            for mount in item.get("Mounts", []):
                source = Path(mount.get("Source", "/")).resolve()
                if source == root or root in source.parents:
                    raise RuntimeError("a Docker container still mounts native scratch")
    if layout == "rich2-stage1":
        qdrant_path = root / "data" / "qdrant"
        if qdrant_path.exists() or qdrant_path.is_symlink():
            assert_qdrant_unowned(qdrant_path)
        elif not allow_missing_qdrant:
            raise RuntimeError("isolated Qdrant storage is missing")
    elif layout == "stage2":
        for strategy in ("A", "B"):
            qdrant_path = root / strategy / "data" / "qdrant"
            if qdrant_path.exists() or qdrant_path.is_symlink():
                assert_qdrant_unowned(qdrant_path)
            elif not allow_missing_qdrant:
                raise RuntimeError("isolated Qdrant storage is missing")
    else:
        raise ValueError("unsupported scratch layout")


def assert_qdrant_unowned(path: Path) -> None:
    if not path.is_dir():
        raise RuntimeError("isolated Qdrant storage is missing")
    try:
        lsof = subprocess.run(
            ["sudo", "-n", "lsof", "+D", str(path)],
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
    verify_parser.add_argument("--abort", type=Path)
    verify_parser.add_argument("--metadata-baseline", type=Path)
    verify_parser.add_argument(
        "--metadata-mode",
        choices=("metadata", "rich2-metadata", "native-metadata"),
        default="metadata",
    )
    verify_parser.add_argument("--cpuset")
    verify_parser.add_argument(
        "--scratch-layout", choices=("stage2", "rich2-stage1"), default="stage2"
    )
    qdrant_parser = commands.add_parser("check-qdrant")
    qdrant_parser.add_argument("path", type=Path)
    failure_parser = commands.add_parser("signal-failure")
    failure_parser.add_argument("--done", type=Path, required=True)
    failure_parser.add_argument("--abort", type=Path, required=True)
    complete_parser = commands.add_parser("complete")
    complete_parser.add_argument("--done", type=Path, required=True)
    complete_parser.add_argument("--session", required=True)
    complete_parser.add_argument("--exit-code", type=int, required=True)
    complete_parser.add_argument("--diagnostic-result", type=Path, required=True)
    identity_parser = commands.add_parser("rich2-identity")
    identity_parser.add_argument("session")
    if len(sys.argv) > 1 and sys.argv[1] == "supervise":
        supervise_parser = commands.add_parser("supervise")
        supervise_parser.add_argument("--session", required=True)
        supervise_parser.add_argument("--container", required=True)
        supervise_parser.add_argument("--scratch", type=Path, required=True)
        supervise_parser.add_argument("--snapshot", type=Path, required=True)
        supervise_parser.add_argument("--done", type=Path, required=True)
        supervise_parser.add_argument("--abort", type=Path, required=True)
        supervise_parser.add_argument("--ceiling-epoch", type=float, required=True)
        supervise_parser.add_argument("--stop-epoch", type=float)
        supervise_parser.add_argument("--maintenance-entry-epoch", type=float)
        supervise_parser.add_argument("--maintenance-entry-monotonic", type=float)
        supervise_parser.add_argument("--metadata-baseline", type=Path, required=True)
        supervise_parser.add_argument(
            "--metadata-mode",
            choices=("metadata", "rich2-metadata", "native-metadata"),
            default="metadata",
        )
        supervise_parser.add_argument("--cpuset", required=True)
        supervise_parser.add_argument(
            "--scratch-layout", choices=("stage2", "rich2-stage1"), default="stage2"
        )
    options = parser.parse_args()
    if options.command == "capture":
        capture(options.snapshot)
    elif options.command == "restore":
        verify(options.snapshot, start_if_stopped=True)
    elif options.command == "verify":
        verify(
            options.snapshot,
            start_if_stopped=False,
            metadata_baseline=options.metadata_baseline,
            cpuset=options.cpuset,
            metadata_mode=options.metadata_mode,
        )
        verify_scratch_unowned(
            options.scratch.resolve(),
            layout=options.scratch_layout,
            allow_missing_qdrant=bool(options.abort and options.abort.exists()),
        )
    elif options.command == "check-qdrant":
        assert_qdrant_unowned(options.path.resolve(strict=True))
    elif options.command == "signal-failure":
        mark_watchdog_failure(done=options.done, abort=options.abort)
    elif options.command == "complete":
        write_completion_record(
            done=options.done,
            session=options.session,
            exit_code=options.exit_code,
            diagnostic_result=options.diagnostic_result,
        )
    elif options.command == "rich2-identity":
        name, label = rich2_stage1_container_identity(options.session)
        print(
            json.dumps(
                {
                    "name": name,
                    "label": label,
                    "scratch_root": str(rich2_stage1_scratch_root(options.session)),
                },
                sort_keys=True,
            )
        )
    else:
        expected_name, _ = rich2_stage1_container_identity(options.session)
        if options.container != expected_name:
            raise RuntimeError("watchdog container name does not match its session")
        if options.scratch_layout == "stage2":
            required_timing = (
                options.stop_epoch,
                options.maintenance_entry_epoch,
                options.maintenance_entry_monotonic,
            )
            if any(value is None for value in required_timing):
                raise RuntimeError("Stage 2 watchdog timing inputs are required")
            require_matching_campaign_deadline(
                supplied_deadline_monotonic=options.ceiling_epoch,
                maintenance_entry_epoch=options.maintenance_entry_epoch,
                maintenance_entry_monotonic=options.maintenance_entry_monotonic,
                stop_epoch=options.stop_epoch,
            )
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
            "--abort",
            str((root / options.abort).resolve()),
            "--scratch-layout",
            options.scratch_layout,
            "--metadata-baseline",
            str(options.metadata_baseline.resolve(strict=True)),
            "--metadata-mode",
            options.metadata_mode,
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
            validate_completion_record(
                root / options.done,
                session=options.session,
                layout=options.scratch_layout,
            )
        raise SystemExit(status)


if __name__ == "__main__":
    main()
