"""Diagnostic transport. Missing server evidence fails closed."""

import json
import re
import subprocess
from pathlib import Path
from time import monotonic, sleep

IMAGE = "sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04"
LABEL = "io.seneca.stage2.session"


def docker(*args, timeout=15, input_text=None):
    return subprocess.run(
        ["docker", *args],
        timeout=timeout,
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def owned_container(name, session):
    ids = docker(
        "ps",
        "-aq",
        "--filter",
        f"label={LABEL}={session}",
        "--filter",
        f"name=^{name}$",
    ).split()
    if not ids:
        return None
    if len(ids) != 1:
        raise RuntimeError("ambiguous diagnostic ownership")
    (item,) = json.loads(docker("inspect", ids[0]))
    if item["Name"] != "/" + name or item["Config"]["Labels"][LABEL] != session:
        raise RuntimeError("diagnostic identity mismatch")
    return item


def terminate(name, session):
    item = owned_container(name, session)
    if item is None:
        return
    container = item["Id"]
    if item["State"]["Running"]:
        try:
            docker("stop", "--timeout", "5", container, timeout=10)
        except subprocess.TimeoutExpired, subprocess.CalledProcessError:
            current = owned_container(name, session)
            if current and current["State"]["Running"]:
                docker("kill", container, timeout=10)
    current = owned_container(name, session)
    if current and current["State"]["Running"]:
        raise RuntimeError("diagnostic container did not terminate")
    if current:
        docker("rm", container)
    if owned_container(name, session):
        raise RuntimeError("diagnostic container still present")


class DockerHTTPAdapter:
    def __init__(self, *, session, journal, launch, bindings):
        if not re.fullmatch(r"[a-f0-9]{16}", session):
            raise ValueError("invalid diagnostic session identity")
        self.session = session
        self.name = "seneca-stage2-" + session
        self.journal = Path(journal).resolve(strict=True)
        self.launch = launch
        self.bindings = bindings
        self.container = None

    def open(self, strategy):
        if strategy not in {"consecutive", "length_sorted_8"}:
            raise ValueError("unsupported strategy")
        if owned_container(self.name, self.session):
            raise RuntimeError("diagnostic name already occupied")
        self.launch(self.name, self.session, strategy)
        item = owned_container(self.name, self.session)
        if not item or not item["State"]["Running"]:
            raise RuntimeError("diagnostic launch did not produce a running container")
        if item["Image"] != IMAGE or item["HostConfig"]["NetworkMode"] != "none":
            raise RuntimeError("diagnostic image or network differs")
        self.container = item["Id"]

    def submit(self, case, timeout):
        if case.case != "load":
            raise RuntimeError("lifecycle control adapter is not wired")
        if self.container is None:
            raise RuntimeError("diagnostic session is not open")
        binding = self.bindings[case.workload]
        workspace = binding["workspace_id"]
        if not re.fullmatch(r"ws_[a-f0-9]{32}", workspace):
            raise ValueError("malformed workspace identity")
        spec = {
            "ordinal": case.ordinal,
            "path": f"/v1/workspaces/{workspace}/conversation/turn",
            "body": binding["body"],
            "timeout": timeout,
        }
        raw = docker(
            "exec",
            "-i",
            self.container,
            "python",
            "-B",
            "/review/socket_client.py",
            timeout=timeout + 5,
            input_text=json.dumps(spec),
        )
        transport = json.loads(raw)
        marker = self.journal / f"{case.ordinal}.sent"
        if not marker.is_file():
            raise RuntimeError("socket send was not attested")
        deadline = monotonic() + 5
        path = self.journal / f"{case.ordinal}.terminal.json"
        while not path.is_file() and monotonic() < deadline:
            sleep(0.025)
        if not path.is_file():
            raise RuntimeError("missing canonical worker settlement")
        record = json.loads(path.read_text())
        if (
            record["ordinal"] != case.ordinal
            or record["http_status"] != transport["http_status"]
        ):
            raise RuntimeError("worker and socket records disagree")
        if (
            record["admission"] == "accepted"
            and record.get("slot_released") is not True
        ):
            raise RuntimeError("query capacity release was not attested")
        return record | {"transport": transport["transport"]}

    def abort(self):
        terminate(self.name, self.session)
        self.container = None

    def close(self):
        self.abort()
