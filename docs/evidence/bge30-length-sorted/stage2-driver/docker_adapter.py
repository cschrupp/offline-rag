"""Fail-closed Docker/socket adapter for the disposable Stage 2 app."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from pathlib import Path
from time import monotonic, monotonic_ns, sleep

IMAGE = "sha256:59252d0655267001c4c9ac42e5a2045131b4086bb1ab84e10dbfd98f2e831dee"
SOURCE = "1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e"
LABEL = "io.seneca.stage2.session"
NATIVE_READY_TIMEOUT_S = 120
SYNTHETIC_READY_TIMEOUT_S = 30
NATIVE_FORWARD_ENTRY_TIMEOUT_S = 180
SYNTHETIC_FORWARD_ENTRY_TIMEOUT_S = 10


def forward_entry_timeout(mode):
    """Bound lifecycle waits by the actual mode's inference deadline."""
    return (
        NATIVE_FORWARD_ENTRY_TIMEOUT_S
        if mode == "native"
        else SYNTHETIC_FORWARD_ENTRY_TIMEOUT_S
    )


def disconnect_entry_timeout(case, mode):
    """Wait for the stage targeted by a disconnect case in the active mode."""
    if case == "disconnect_during":
        return forward_entry_timeout(mode)
    if case == "disconnect_before":
        return 10
    raise ValueError(f"unsupported disconnect case: {case}")


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
    if item["Name"] != "/" + name or item["Config"]["Labels"].get(LABEL) != session:
        raise RuntimeError("diagnostic identity mismatch")
    return item


def session_containers(session):
    ids = docker("ps", "-aq", "--filter", f"label={LABEL}={session}").split()
    if not ids:
        return []
    return json.loads(docker("inspect", *ids))


def terminate(name, session, *, stop_timeout=3):
    """Stop and remove only the exact session-owned container."""
    item = owned_container(name, session)
    if item is None:
        return
    container = item["Id"]
    if item["State"]["Running"]:
        try:
            docker(
                "stop",
                "--timeout",
                str(stop_timeout),
                container,
                timeout=stop_timeout + 5,
            )
        except subprocess.SubprocessError:
            current = owned_container(name, session)
            if current and current["State"]["Running"]:
                docker("kill", container, timeout=8)
    current = owned_container(name, session)
    if current and current["State"]["Running"]:
        docker("kill", container, timeout=8)
        current = owned_container(name, session)
    if current and current["State"]["Running"]:
        raise RuntimeError("diagnostic container did not terminate")
    if current:
        docker("rm", container, timeout=8)
    if owned_container(name, session):
        raise RuntimeError("diagnostic container still present")


def copy_seeded_worktree(*, source: Path, target: Path, session: str) -> None:
    """Copy the synthetic arm input as its owning UID, preserving file modes."""
    if session_containers(session):
        raise RuntimeError("refusing to copy while an app container is active")
    if any(target.iterdir()):
        raise RuntimeError("target arm directory is not empty")
    os.chmod(target, 0o777)
    docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "10001:10001",
        "--cpus",
        "1",
        "--memory",
        "512m",
        "--label",
        f"{LABEL}={session}",
        "--mount",
        f"type=bind,src={source},dst=/copy-source,readonly",
        "--mount",
        f"type=bind,src={target},dst=/copy-target",
        "--entrypoint",
        "python",
        IMAGE,
        "-B",
        "-c",
        "from pathlib import Path; import shutil; s=Path('/copy-source'); d=Path('/copy-target'); shutil.copytree(s/'data', d/'data'); shutil.copytree(s/'models', d/'models'); shutil.copy2(s/'bindings.json', d/'bindings.json')",
        timeout=120,
    )
    for required in (target / "data", target / "models", target / "bindings.json"):
        if not required.exists():
            raise RuntimeError("second arm copy is incomplete")


def read_events(journal: Path) -> list[dict]:
    path = journal / "events.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("event"), str):
                raise RuntimeError("malformed server event")
            rows.append(row)
    return rows


def events_for(journal: Path, ordinal: int) -> list[dict]:
    return [row for row in read_events(journal) if row.get("ordinal") == ordinal]


def wait_for_http_ready(container: str, timeout: int) -> None:
    """Wait for the diagnostic app's readiness endpoint within a fixed bound."""
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        try:
            docker(
                "exec",
                container,
                "python",
                "-B",
                "-c",
                "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=1).status == 200",
                timeout=3,
            )
            return
        except subprocess.SubprocessError:
            sleep(0.05)
    raise TimeoutError("real app did not become ready")


def readiness_timeout(mode: str) -> int:
    if mode == "native":
        return NATIVE_READY_TIMEOUT_S
    if mode == "synthetic":
        return SYNTHETIC_READY_TIMEOUT_S
    raise ValueError("unsupported adapter mode")


def wait_for_event(
    journal: Path,
    ordinal: int | None,
    name: str,
    timeout: float,
    *,
    after_monotonic_ns: int | None = None,
):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        matches = [
            row
            for row in read_events(journal)
            if row.get("event") == name
            and row.get("ordinal") == ordinal
            and (
                after_monotonic_ns is None
                or row.get("monotonic_ns", 0) > after_monotonic_ns
            )
        ]
        if matches:
            if len(matches) != 1:
                raise RuntimeError(f"duplicate {name} event for {ordinal}")
            return matches[0]
        sleep(0.01)
    raise TimeoutError(f"missing {name} for ordinal {ordinal}")


def wait_for_worker_release(journal: Path, ordinal: int, timeout: float) -> None:
    """Wait for disconnected work to terminate and relinquish query capacity."""
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        events = events_for(journal, ordinal)
        terminals = [
            row
            for row in events
            if row.get("event") in {"worker_returned", "worker_failed"}
        ]
        releases = [row for row in events if row.get("event") == "slot_released"]
        if len(terminals) > 1 or len(releases) > 1:
            raise RuntimeError("duplicate worker terminal or slot release event")
        if terminals and releases:
            return
        sleep(0.01)
    raise TimeoutError(f"worker or slot release did not settle for ordinal {ordinal}")


def project_submission(case, transport, events, expected_path):
    """Create a canonical envelope only from corroborated server evidence."""
    ordinal = case.ordinal
    if sum(row["event"] == "http_received" for row in events) != 1:
        raise RuntimeError("missing or duplicate HTTP request correlation")
    responses = [row for row in events if row["event"] == "http_response"]
    if len(responses) > 1:
        raise RuntimeError("duplicate server HTTP response correlation")
    receive = next(row for row in events if row["event"] == "http_received")
    if receive.get("method") != "POST" or receive.get("path") != expected_path:
        raise RuntimeError("request reached an unexpected route")

    preflight_ok = [row for row in events if row["event"] == "preflight_admitted"]
    preflight_no = [row for row in events if row["event"] == "preflight_rejected"]
    if len(preflight_ok) + len(preflight_no) != 1:
        raise RuntimeError("missing or duplicate preflight decision")

    if preflight_no:
        row = preflight_no[0]
        forbidden = {
            "query_admitted",
            "worker_started",
            "worker_returned",
            "worker_failed",
            "turn_result",
            "scorer_entered",
            "forward_entered",
            "synthetic_generator_invoked",
        }
        if any(item["event"] in forbidden for item in events):
            raise RuntimeError("preflight rejection reached execution")
        if row.get("reason") != "query_preflight_capacity_exhausted":
            raise RuntimeError("unexpected preflight rejection reason")
        if not responses or responses[0].get("status") != 503:
            raise RuntimeError("preflight rejection lacks HTTP 503")
        body = transport.get("body") or {}
        if (body.get("details") or {}).get("reason") != row["reason"]:
            raise RuntimeError("client did not receive the server preflight reason")
        result = {
            "ordinal": ordinal,
            "settled": True,
            "admission": "preflight_rejected",
            "operation": None,
            "terminal": None,
            "reason": row["reason"],
            "http_status": 503,
            "server_http_status": 503,
            "transport": transport["transport"],
            "worker_returned": False,
            "slot_released": False,
            "scientific_trace_ids": [],
            "server_events": events,
        }
    else:
        operation_id = preflight_ok[0].get("operation_id")
        if not isinstance(operation_id, str) or not operation_id.startswith("opq_"):
            raise RuntimeError("preflight event has no operation identity")
        linked = [
            row
            for row in events
            if row.get("operation_id") == operation_id
            and row["event"]
            in {
                "query_admitted",
                "terminal_claimed",
                "worker_started",
                "worker_returned",
                "worker_failed",
                "slot_released",
                "cancel_signaled",
            }
        ]
        operation_events = {
            "query_admitted",
            "terminal_claimed",
            "worker_started",
            "worker_returned",
            "worker_failed",
            "slot_released",
            "cancel_signaled",
        }
        observed_operation_rows = [
            row for row in events if row["event"] in operation_events
        ]
        if any(
            row.get("operation_id") != operation_id for row in observed_operation_rows
        ):
            raise RuntimeError("operation correlation mismatch")
        worker_terms = [
            row
            for row in linked
            if row["event"] in {"worker_returned", "worker_failed"}
        ]
        releases = [row for row in linked if row["event"] == "slot_released"]
        if len(worker_terms) != 1 or len(releases) != 1:
            raise RuntimeError("accepted operation lacks unique worker/release event")
        worker_index = events.index(worker_terms[0])
        release_index = events.index(releases[0])
        if release_index <= worker_index:
            raise RuntimeError("capacity release preceded actual worker return")
        admitted = any(row["event"] == "query_admitted" for row in linked)
        if (
            releases[0].get("worker_returned") is not True
            or releases[0].get("operation_released") is not True
        ):
            raise RuntimeError("operation release was not independently observed")
        if admitted and releases[0].get("global_query_capacity_empty") is not True:
            raise RuntimeError(
                "query capacity remained held after admitted worker return"
            )
        status = responses[0].get("status") if responses else None
        if worker_terms[0]["event"] == "worker_returned":
            terminal = "completed"
            admission = "accepted"
            trace_ids = [worker_terms[0].get("query_trace_id")]
            if (
                worker_terms[0].get("result_status") != "answered"
                or worker_terms[0].get("query_trace_present") is not True
                or worker_terms[0].get("conversation_trace_present") is not True
            ):
                raise RuntimeError("completed result lacks durable trace evidence")
            if status != 200:
                raise RuntimeError("completed operation lacks matching HTTP 200")
            if transport.get("http_status") != status:
                raise RuntimeError("client/server HTTP status mismatch")
            reason = None
            worker_returned = True
        else:
            worker = worker_terms[0]
            reason = worker.get("reason")
            if reason is None and worker.get("error_code") == "request_cancelled":
                signals = [row for row in linked if row["event"] == "cancel_signaled"]
                if len(signals) == 1:
                    reason = signals[0].get("reason")
            trace_id = worker.get("trace_id")
            trace_ids = [trace_id] if trace_id else []
            if trace_id and worker.get("query_trace_present") is not True:
                raise RuntimeError("error trace identity is not persisted")
            if reason in {"client_disconnect", "shutdown", "shutdown_abort"}:
                terminal = "cancelled"
            elif reason == "query_deadline_exceeded":
                terminal = "timed_out"
            else:
                terminal = "failed"
            if admitted:
                admission = "accepted"
            elif reason == "query_capacity_exhausted":
                admission = "query_rejected"
            else:
                admission = "preparation_failed"
            if transport["transport"] != "client_disconnected" and status is None:
                raise RuntimeError("server response missing for connected client")
            worker_returned = True

        if transport["transport"] == "client_disconnected":
            # Server response attempt and client delivery are separate facts.
            client_status = None
        else:
            client_status = transport.get("http_status")
        if not admitted and admission == "query_rejected":
            if status != 503 or reason != "query_capacity_exhausted":
                raise RuntimeError("query-slot rejection is not correctly classified")
            if trace_ids:
                raise RuntimeError("query-slot rejection allocated a scientific trace")
            body = transport.get("body") or {}
            if (body.get("details") or {}).get("reason") != reason:
                raise RuntimeError("client/server query-slot rejection differs")
        result = {
            "ordinal": ordinal,
            "settled": True,
            "admission": admission,
            "operation": operation_id,
            "terminal": terminal,
            "reason": reason,
            "http_status": client_status,
            "server_http_status": status,
            "transport": transport["transport"],
            "worker_returned": worker_returned,
            "slot_released": releases[0].get("operation_released") is True,
            "global_query_capacity_empty": releases[0].get(
                "global_query_capacity_empty"
            ),
            "scientific_trace_ids": trace_ids,
            "server_events": events,
        }

    if (
        transport.get("http_status") is not None
        and result["server_http_status"] != transport["http_status"]
    ):
        raise RuntimeError("client/server response status differs")
    return result


class DockerHTTPAdapter:
    """Bounded exact-image app launcher with single-send HTTP submissions."""

    def __init__(
        self,
        *,
        session,
        journal,
        control,
        inputs,
        driver_dir,
        work_roots,
        bindings=None,
        mode="synthetic",
        native_models=None,
        native_bindings=None,
        shutdown_grace_seconds=1,
    ):
        if not re.fullmatch(r"[a-f0-9]{16}", session):
            raise ValueError("invalid diagnostic session identity")
        self.session = session
        self.name = "seneca-stage2-" + session
        self.journal = Path(journal).resolve(strict=True)
        self.control = Path(control).resolve(strict=True)
        self.inputs = Path(inputs).resolve(strict=True)
        self.driver_dir = Path(driver_dir).resolve(strict=True)
        self.work_roots = work_roots
        self.bindings = bindings or {}
        if mode not in {"synthetic", "native"}:
            raise ValueError("unsupported adapter mode")
        self.mode = mode
        if shutdown_grace_seconds not in {1, 30}:
            raise ValueError("unsupported application shutdown grace")
        if mode == "native" and shutdown_grace_seconds != 30:
            raise ValueError("native mode requires the accepted 30-second grace")
        if mode == "synthetic" and shutdown_grace_seconds != 1:
            raise ValueError("synthetic rehearsal retains its accelerated grace")
        self.shutdown_grace_seconds = shutdown_grace_seconds
        self.native_models = (
            None if native_models is None else Path(native_models).resolve(strict=True)
        )
        self.native_bindings = (
            None
            if native_bindings is None
            else Path(native_bindings).resolve(strict=True)
        )
        if self.mode == "native" and (
            self.native_models is None or self.native_bindings is None
        ):
            raise ValueError("native adapter requires model and binding roots")
        self.container = None
        self.strategy = None
        self._send_lock = threading.Lock()
        self._sent: set[int] = set()

    def open(self, strategy):
        if strategy not in {"consecutive", "length_sorted_8"}:
            raise ValueError("unsupported strategy")
        if self.mode == "synthetic" and strategy == "length_sorted_8":
            source = Path(self.work_roots["consecutive"]).resolve(strict=True)
            target = Path(self.work_roots[strategy]).resolve(strict=True)
            if not (target / "bindings.json").exists():
                if not (source / "bindings.json").is_file():
                    raise RuntimeError("baseline synthetic bindings missing")
                copy_seeded_worktree(source=source, target=target, session=self.session)
        if owned_container(self.name, self.session):
            raise RuntimeError("diagnostic name already occupied")
        work_root = Path(self.work_roots[strategy]).resolve(strict=True)
        if self.mode == "native":
            if not (work_root / "data").is_dir():
                raise RuntimeError("native arm data copy is missing")
            if (
                not self.native_models.is_dir()
                or not (self.native_models / "rerankers").is_dir()
            ):
                raise RuntimeError("native read-only model tree is incomplete")
            if not self.native_bindings.is_file():
                raise RuntimeError("native preflight binding file is missing")
        allowed_cpus = sorted(os.sched_getaffinity(0))
        if len(allowed_cpus) < 4:
            raise RuntimeError("host does not expose four allowed CPUs")
        cpuset = ",".join(str(cpu) for cpu in allowed_cpus[:4])
        os.chmod(work_root, 0o777)
        os.chmod(self.journal, 0o777)
        os.chmod(self.control, 0o777)
        mounts = [
            "--mount",
            f"type=bind,src={self.journal},dst=/stage2-journal",
            "--mount",
            f"type=bind,src={self.control},dst=/stage2-control",
            "--mount",
            f"type=bind,src={self.inputs},dst=/review/inputs,readonly",
            "--mount",
            f"type=bind,src={self.driver_dir},dst=/review/driver,readonly",
        ]
        if self.mode == "native":
            mounts.extend(
                [
                    "--mount",
                    f"type=bind,src={work_root / 'data'},dst=/data",
                    "--mount",
                    f"type=bind,src={self.native_models},dst=/models,readonly",
                    "--mount",
                    f"type=bind,src={self.native_bindings},dst=/stage2-native/native-bindings.json,readonly",
                ]
            )
        else:
            mounts.extend(["--mount", f"type=bind,src={work_root},dst=/stage2-work"])
        docker(
            "run",
            "-d",
            "--network",
            "none",
            "--cpus",
            "4",
            "--cpuset-cpus",
            cpuset,
            "--memory",
            "6g",
            "--memory-swap",
            "6g",
            "--label",
            f"{LABEL}={self.session}",
            "--name",
            self.name,
            "--env",
            "OFFLINE_RAG_CONFIG=/app/config/base.yaml",
            "--env",
            "OFFLINE_RAG_DATA_DIR=/data"
            if self.mode == "native"
            else "OFFLINE_RAG_DATA_DIR=/stage2-work/data",
            "--env",
            "OFFLINE_RAG_MODELS_DIR=/models"
            if self.mode == "native"
            else "OFFLINE_RAG_MODELS_DIR=/stage2-work/models",
            "--env",
            "OFFLINE_RAG_STRICT_OFFLINE=true",
            "--env",
            "HF_HUB_OFFLINE=1",
            "--env",
            "TRANSFORMERS_OFFLINE=1",
            *mounts,
            "--entrypoint",
            "python",
            IMAGE,
            "-B",
            "/review/driver/stage2_app_server.py",
            "--mode",
            self.mode,
            "--strategy",
            strategy,
            *(
                ["--native-bindings", "/stage2-native/native-bindings.json"]
                if self.mode == "native"
                else []
            ),
        )
        item = owned_container(self.name, self.session)
        if (
            not item
            or not item["State"]["Running"]
            or item["Image"] != IMAGE
            or item["HostConfig"]["NetworkMode"] != "none"
            or item["HostConfig"]["NanoCpus"] != 4_000_000_000
            or item["HostConfig"]["CpusetCpus"] != cpuset
            or item["HostConfig"]["Memory"] != 6 * 1024**3
        ):
            terminate(self.name, self.session)
            raise RuntimeError("diagnostic container isolation mismatch")
        mounted = {
            mount["Destination"]: (Path(mount["Source"]).resolve(), mount["RW"])
            for mount in item.get("Mounts", [])
        }
        expected_mounts = {
            "/stage2-journal": (self.journal, True),
            "/stage2-control": (self.control, True),
            "/review/inputs": (self.inputs, False),
            "/review/driver": (self.driver_dir, False),
        }
        if self.mode == "native":
            expected_mounts.update(
                {
                    "/data": ((work_root / "data").resolve(), True),
                    "/models": (self.native_models, False),
                    "/stage2-native/native-bindings.json": (
                        self.native_bindings,
                        False,
                    ),
                }
            )
        else:
            expected_mounts["/stage2-work"] = (work_root, True)
        if any(
            mounted.get(dest) != identity for dest, identity in expected_mounts.items()
        ):
            terminate(self.name, self.session)
            raise RuntimeError("diagnostic mount identity mismatch")
        self.container = item["Id"]
        self.strategy = strategy
        deadline = monotonic() + 120
        while True:
            identities = [
                row
                for row in read_events(self.journal)
                if row["event"] == "server_ready_identity"
                and row.get("strategy") == strategy
                and row.get("mode", "synthetic") == self.mode
            ]
            if identities:
                if len(identities) != 1:
                    raise RuntimeError("duplicate server-ready identity")
                break
            current = owned_container(self.name, self.session)
            if current is None or not current["State"]["Running"]:
                try:
                    logs = docker("logs", self.container, timeout=5)
                except (OSError, subprocess.SubprocessError) as exc:
                    logs = f"unavailable ({type(exc).__name__})"
                raise RuntimeError(
                    f"diagnostic app exited before ready: {logs[-2000:]}"
                )
            if monotonic() >= deadline:
                raise TimeoutError("server readiness identity missing")
            sleep(0.02)
        wait_for_http_ready(self.container, readiness_timeout(self.mode))
        identity = identities[0]
        if (
            identity.get("strategy") != strategy
            or identity.get("effective_cpus") != 4
            or identity.get("mode", "synthetic") != self.mode
        ):
            raise RuntimeError("effective server identity mismatch")
        if self.mode == "native":
            raw_identity = docker(
                "exec",
                self.container,
                "python",
                "-B",
                "-c",
                "import json,urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/__stage2/identity', timeout=2).read().decode())",
                timeout=5,
            )
            resolved = json.loads(raw_identity)
            required = {
                "mode": "native",
                "strategy": strategy,
                "source_revision": SOURCE,
                "reranker_model_id": "BAAI/bge-reranker-v2-m3",
                "reranker_revision": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
                "reranker_input_k": 30,
                "reranker_max_length": 1024,
                "reranker_resolved_device": "cpu",
                "reranker_precision": "fp32",
                "reranker_score_transform": "raw-logit-v1",
                "embedding_model_id": "Qwen/Qwen3-Embedding-0.6B",
                "embedding_revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
                "embedding_profile_id": "cpu_onnx_fp32_v1",
                "embedding_representation_id": "onnx_fp32_v1",
                "embedding_backend_family": "sentence_transformers_onnx",
                "embedding_resolved_device": "cpu",
                "embedding_resolved_precision": "fp32",
                "embedding_provider": "CPUExecutionProvider",
                "configured_query_deadline_s": 180,
                "configured_shutdown_grace_s": 30,
                "effective_cpus": 4,
                "torch_intra": 2,
                "torch_inter": 2,
                "ort_intra": 8,
                "ort_inter": 1,
                "provider_fixture": True,
                "external_network": False,
                "runtime_ready": True,
            }
            if any(resolved.get(key) != value for key, value in required.items()):
                raise RuntimeError("native runtime identity differs from manifest")
            self.bindings = json.loads(
                (self.journal / "bindings.json").read_text(encoding="utf-8")
            )
        bindings_path = self.journal / "bindings.json"
        deadline = monotonic() + 30
        while not bindings_path.exists() and monotonic() < deadline:
            sleep(0.02)
        if not bindings_path.exists():
            raise RuntimeError("server workspace bindings missing")
        self.bindings = json.loads(bindings_path.read_text(encoding="utf-8"))

    def submit(self, case, timeout):
        if self.container is None or self.strategy != case.strategy:
            raise RuntimeError("submission has no matching active session")
        with self._send_lock:
            if case.ordinal in self._sent or len(self._sent) >= 36:
                raise RuntimeError("duplicate or over-budget adapter send")
            self._sent.add(case.ordinal)
        if case.case not in {
            "load",
            "disconnect_before",
            "disconnect_during",
            "deadline",
            "drain",
        }:
            raise RuntimeError("unsupported diagnostic case")

        binding = self.bindings[case.workload]
        workspace = binding["workspace_id"]
        if not re.fullmatch(r"ws_[a-f0-9]{32}", workspace):
            raise ValueError("malformed synthetic workspace identity")
        body = {
            "question": (
                "What ingredients are needed for the baked French fries?"
                if case.workload == "Recipes"
                else "Describe the naturalistic decision method"
            ),
            "prior_turns": [],
            "source_ids": binding["source_ids"],
        }
        mode = "response"
        disconnect_at = None
        hold = None
        if case.case == "disconnect_before":
            mode, disconnect_at, hold = (
                "disconnect",
                "checkpoint_entered",
                "before_rerank",
            )
        elif case.case == "disconnect_during":
            mode, disconnect_at, hold = "disconnect", "forward_entered", "forward"
        elif case.case in {"deadline", "drain"}:
            hold = "forward"

        if hold:
            (self.control / f"{case.ordinal}.json").write_text(
                json.dumps(
                    {"case": case.case, "hold": hold, "strategy": case.strategy}
                ),
                encoding="utf-8",
            )
        spec = {
            "ordinal": case.ordinal,
            "path": f"/v1/workspaces/{workspace}/conversation/turn",
            "body": body,
            "timeout": timeout,
            "disconnect_at": disconnect_at,
            "mode": mode,
        }
        client = subprocess.Popen(
            [
                "docker",
                "exec",
                "-i",
                self.container,
                "python",
                "-B",
                "/review/driver/socket_client.py",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert client.stdin is not None
        client.stdin.write(json.dumps(spec))
        client.stdin.close()
        client.stdin = None

        try:
            if case.case in {"disconnect_before", "disconnect_during"}:
                entered = (
                    "checkpoint_hold_entered"
                    if case.case == "disconnect_before"
                    else "forward_entered"
                )
                wait_for_event(
                    self.journal,
                    case.ordinal,
                    entered,
                    disconnect_entry_timeout(case.case, self.mode),
                )
                wait_for_path(self.journal / f"{case.ordinal}.transport_closed", 10)
                wait_for_event(self.journal, case.ordinal, "cancel_signaled", 10)
                if case.case == "disconnect_before":
                    if any(
                        row["event"]
                        in {
                            "scorer_entered",
                            "forward_entered",
                            "synthetic_generator_invoked",
                        }
                        for row in events_for(self.journal, case.ordinal)
                    ):
                        raise RuntimeError("pre-rerank disconnect executed inference")
                else:
                    rows = events_for(self.journal, case.ordinal)
                    forward = next(
                        row for row in rows if row["event"] == "forward_entered"
                    )
                    if forward.get("query_capacity_held") != 1:
                        raise RuntimeError("held forward did not retain query capacity")
                    if any(row["event"] == "slot_released" for row in rows):
                        raise RuntimeError("query slot released while forward was held")
                (self.journal / f"{case.ordinal}.release").touch(exist_ok=False)
            elif case.case == "deadline":
                admitted = wait_for_event(
                    self.journal, case.ordinal, "query_admitted", 10
                )
                wait_for_event(
                    self.journal,
                    case.ordinal,
                    "forward_entered",
                    forward_entry_timeout(self.mode),
                )
                remaining = float(admitted["deadline_mono"]) - monotonic()
                if remaining > 0:
                    sleep(remaining + 0.05)
                (self.journal / f"{case.ordinal}.release").touch(exist_ok=False)
            elif case.case == "drain":
                wait_for_event(
                    self.journal,
                    case.ordinal,
                    "forward_entered",
                    forward_entry_timeout(self.mode),
                )
                drain_requested_after = monotonic_ns()
                drain_timeout = 195 if self.mode == "native" else 40
                drain = subprocess.Popen(
                    [
                        "docker",
                        "exec",
                        self.container,
                        "python",
                        "-B",
                        "-c",
                        (
                            "import urllib.request; req=urllib.request.Request('http://127.0.0.1:8080/__stage2/drain', method='POST'); print(urllib.request.urlopen(req, timeout="
                            f"{drain_timeout}).read().decode())"
                        ),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                grace = wait_for_event(
                    self.journal,
                    None,
                    "drain_grace_exhausted",
                    35 if self.mode == "native" else 5,
                    after_monotonic_ns=drain_requested_after,
                )
                if (
                    grace.get("active_count") != 1
                    or grace.get("query_capacity_held") != 1
                    or grace.get("resources_open") is not True
                ):
                    raise RuntimeError("drain did not preserve owned resources")
                if any(
                    row["event"] == "resources_closed"
                    and row["monotonic_ns"] > grace["monotonic_ns"]
                    for row in read_events(self.journal)
                ):
                    raise RuntimeError("resources closed before held worker returned")
                (self.journal / f"{case.ordinal}.release").touch(exist_ok=False)
                _drain_out, drain_err = drain.communicate(
                    timeout=205 if self.mode == "native" else 20
                )
                if drain.returncode != 0:
                    raise RuntimeError(f"diagnostic drain failed: {drain_err}")

            stdout, stderr = client.communicate(timeout=timeout + 10)
            if client.returncode != 0:
                raise RuntimeError(f"socket client failed: {stderr[-1000:]}")
            transport = json.loads(stdout)
            if not (self.journal / f"{case.ordinal}.sent").is_file():
                raise RuntimeError("actual socket send marker missing")
            wait_for_event(self.journal, case.ordinal, "http_received", 5)
            if case.case in {"disconnect_before", "disconnect_during"}:
                wait_for_worker_release(
                    self.journal,
                    case.ordinal,
                    195 if self.mode == "native" else 5,
                )
            else:
                if not any(
                    row["event"]
                    in {"worker_returned", "worker_failed", "preflight_rejected"}
                    for row in events_for(self.journal, case.ordinal)
                ):
                    raise RuntimeError("no backend terminal worker evidence")
                wait_for_event(self.journal, case.ordinal, "http_response", 5)
            if case.case == "drain":
                wait_for_event(
                    self.journal,
                    None,
                    "runtime_stopped",
                    195 if self.mode == "native" else 5,
                    after_monotonic_ns=grace["monotonic_ns"],
                )
                full_events = read_events(self.journal)
                case_events = events_for(self.journal, case.ordinal)
                if any(
                    row["event"] == "resource_close_while_owned"
                    and row["monotonic_ns"] > grace["monotonic_ns"]
                    for row in full_events
                ):
                    raise RuntimeError(
                        "runtime closed resources while operation active"
                    )
                drain_worker = [
                    row
                    for row in case_events
                    if row["event"] in {"worker_returned", "worker_failed"}
                ]
                drain_release = [
                    row for row in case_events if row["event"] == "slot_released"
                ]
                later_events = [
                    row
                    for row in full_events
                    if row["monotonic_ns"] > grace["monotonic_ns"]
                ]
                closed = [
                    row for row in later_events if row["event"] == "resources_closed"
                ]
                stopped = [
                    row for row in later_events if row["event"] == "runtime_stopped"
                ]
                if (
                    len(drain_worker) != 1
                    or len(drain_release) != 1
                    or len(closed) != 1
                    or len(stopped) != 1
                    or not (
                        case_events.index(drain_worker[0])
                        < case_events.index(drain_release[0])
                    )
                    or not (
                        drain_release[0]["monotonic_ns"]
                        < closed[0]["monotonic_ns"]
                        < stopped[0]["monotonic_ns"]
                    )
                ):
                    raise RuntimeError(
                        "drain did not retain resources through worker release"
                    )
            events = events_for(self.journal, case.ordinal)
            result = project_submission(case, transport, events, spec["path"])
            if case.case == "deadline":
                if result["reason"] != "query_deadline_exceeded":
                    raise RuntimeError("cooperative deadline was not recognized")
                if any(row["event"] == "synthetic_generator_invoked" for row in events):
                    raise RuntimeError("generator ran after expired deadline")
            self._record_terminal(result)
            return result
        except BaseException:
            if client.poll() is None:
                client.kill()
                client.wait(timeout=5)
            raise

    def _record_terminal(self, result):
        path = self.journal / f"{result['ordinal']}.terminal.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def abort(self):
        if self.container is not None:
            terminate(
                self.name,
                self.session,
                stop_timeout=self.shutdown_grace_seconds,
            )
            self.container = None
            if session_containers(self.session):
                raise RuntimeError("diagnostic session container remains after abort")

    def close(self):
        self.abort()


def wait_for_path(path: Path, timeout: float):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if path.exists():
            return
        sleep(0.01)
    raise TimeoutError(f"missing marker {path.name}")
