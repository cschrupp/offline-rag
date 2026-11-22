"""Rehearse transport against a disposable socket fixture, without models."""

import os
import tempfile
import uuid
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace

from docker_adapter import IMAGE, LABEL, DockerHTTPAdapter, docker, owned_container

FIXTURE = """
import json
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.path.endswith("/conversation/turn")
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ordinal = int(self.headers["X-Stage2-Ordinal"])
        if not data.get("omit"):
            row = dict(ordinal=ordinal, admission="preflight_rejected", settled=True,
                       http_status=503, reason="query_preflight_capacity_exhausted")
            journal = Path("/stage2-journal")
            pending = journal / f"{ordinal}.pending"
            pending.write_text(json.dumps(row))
            pending.rename(journal / f"{ordinal}.terminal.json")
        self.send_response(503)
        self.end_headers()
        self.wfile.write(b"{}")
server = ThreadingHTTPServer(("127.0.0.1",8080), Handler)
Path("/stage2-journal/ready").touch()
server.serve_forever()
"""


def main():
    session = uuid.uuid4().hex[:16]
    with tempfile.TemporaryDirectory(prefix="stage2-transport-") as scratch:
        os.chmod(scratch, 0o777)
        root = Path(scratch)

        def launch(name, label, strategy):
            docker(
                "run",
                "-d",
                "--network",
                "none",
                "--label",
                f"{LABEL}={label}",
                "--name",
                name,
                "--mount",
                f"type=bind,src={root},dst=/stage2-journal",
                "--mount",
                f"type=bind,src={Path(__file__).parent.resolve()},dst=/review,readonly",
                "--entrypoint",
                "python",
                IMAGE,
                "-B",
                "-c",
                FIXTURE,
            )
            deadline = monotonic() + 8
            while not (root / "ready").exists():
                if monotonic() >= deadline:
                    raise RuntimeError("fixture did not start")
                sleep(0.05)

        adapter = DockerHTTPAdapter(
            session=session,
            journal=root,
            launch=launch,
            bindings={"Recipes": {"workspace_id": "ws_" + "0" * 32, "body": {}}},
        )
        try:
            adapter.open("consecutive")
            case = SimpleNamespace(case="load", workload="Recipes", ordinal=1)
            assert (
                adapter.submit(case, timeout=3)["reason"]
                == "query_preflight_capacity_exhausted"
            )
            print("actual socket send and correlated rejection passed")
            adapter.bindings["Recipes"]["body"]["omit"] = True
            case.ordinal = 2
            try:
                adapter.submit(case, timeout=3)
            except RuntimeError as err:
                assert str(err) == "missing canonical worker settlement"
            else:
                raise AssertionError("missing record passed")
            assert (root / "2.sent").exists()
            print("missing terminal evidence failed closed; send marker retained")
        finally:
            adapter.close()
            assert owned_container(adapter.name, adapter.session) is None
            print("SIGTERM-ignoring fixture removed after bounded Docker stop")


if __name__ == "__main__":
    main()
