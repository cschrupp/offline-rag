"""Exercise the unchanged conversation HTTP route through a loopback Uvicorn server."""

import json
import re
import socket
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/unit/app"))
import test_slice16d_b3_conversation as fixture


def until(predicate, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if result := predicate():
            return result
        time.sleep(0.025)
    raise AssertionError("bounded observation timed out")


def serve(directory, port, tokenizer):
    fixture.TIKTOKEN_SRC = tokenizer
    settings = fixture._query_settings(directory)
    settings = settings.model_copy(
        update={"api": settings.api.model_copy(update={"max_concurrent_query": 1})}
    )

    def fake_response(request):
        handles = re.findall(
            r"\[EVIDENCE (E[1-9][0-9]*)\]",
            "\n".join(message.content for message in request.messages),
        )
        assert handles
        return json.dumps(
            {
                "abstain": False,
                "blocks": [
                    {
                        "text": "Synthetic grounded answer.",
                        "evidence_handles": handles[:1],
                    }
                ],
                "abstention_reason": None,
            }
        )

    class HeldReranker(fixture.FakeReranker):
        def close(self):
            (directory / "scorer-closed").touch()

        def score_pairs(self, pairs):
            if (directory / "hold").exists():
                with tempfile.NamedTemporaryFile(
                    dir=directory, prefix="entered-", delete=False
                ):
                    pass
                with (directory / "active-counts").open("a") as stream:
                    print(runtime.operations.active_count(), file=stream)
                until(lambda: not (directory / "hold").exists(), seconds=12)
                with tempfile.NamedTemporaryFile(
                    dir=directory, prefix="returned-", delete=False
                ):
                    pass
            return super().score_pairs(pairs)

    runtime = fixture.ApplicationRuntime(
        settings=settings,
        factories=fixture.ResourceFactories(
            embedder=lambda _: fixture.FakeEmbedder(dimension=8, normalize=True),
            reranker=lambda _: HeldReranker(),
            generator_client=lambda _: fixture.FakeGenerator(response_fn=fake_response),
            qdrant=lambda s: fixture.QdrantLocalBackend(s.paths.qdrant_storage),
        ),
    )
    uvicorn.run(
        fixture.create_app(runtime=runtime),
        host="127.0.0.1",
        port=port,
        timeout_graceful_shutdown=8,
        log_level="warning",
    )


def run(directory, tokenizer):
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    server = subprocess.Popen(
        [sys.executable, __file__, str(directory), str(port), str(tokenizer)]
    )
    base = f"http://127.0.0.1:{port}"
    hold = directory / "hold"

    def ready():
        try:
            return httpx.get(base + "/health/ready", timeout=0.3).status_code == 200
        except httpx.TransportError:
            return False

    try:
        until(ready, seconds=20)
        with httpx.Client(base_url=base, timeout=8) as client:
            workspace, source, _, _ = fixture._seed_workspace(client)
        path = f"/v1/workspaces/{workspace}/conversation/turn"
        payload = {
            "question": "What is supervised learning?",
            "prior_turns": [],
            "source_ids": [source],
        }

        def post():
            response = httpx.post(base + path, json=payload, timeout=10)
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "answered", response.text
            assert response.json()["citations"]
            return response.status_code

        def count(prefix):
            return len(list(directory.glob(prefix + "-*")))

        def traces():
            return len(
                list((directory / "data" / "traces" / "conversation").glob("*.json"))
            )

        print("normal:", post(), flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            hold.touch()
            first = pool.submit(post)
            until(lambda: count("entered") == 1)
            second = pool.submit(post)
            until(lambda: count("entered") == 2)
            assert count("returned") == 0
            hold.unlink()
            print("competing:", first.result(), second.result(), flush=True)

            hold.touch()
            data = json.dumps(payload).encode()
            with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                client.sendall(
                    (
                        f"POST {path} HTTP/1.1\r\nHost: localhost\r\n"
                        f"Content-Type: application/json\r\nContent-Length: {len(data)}\r\n\r\n"
                    ).encode()
                    + data
                )
                until(lambda: count("entered") == 3)
            competing = pool.submit(post)
            until(lambda: count("entered") == 4)
            assert count("returned") == 2
            hold.unlink()
            assert competing.result() == 200
            until(lambda: traces() == 5)
            print(
                "disconnect: second request entered before abandoned worker returned; both traces persisted",
                flush=True,
            )

            hold.touch()
            last = pool.submit(post)
            until(lambda: count("entered") == 5)
            server.terminate()
            time.sleep(0.3)
            assert server.poll() is None and count("returned") == 4
            assert not (directory / "scorer-closed").exists()
            hold.unlink()
            print(
                "shutdown: response",
                last.result(),
                "exit",
                server.wait(timeout=10),
                "trace count",
                traces(),
                flush=True,
            )
            assert traces() == 6
            trace_dir = directory / "data" / "traces" / "conversation"
            records = [json.loads(p.read_text()) for p in trace_dir.glob("*.json")]
            assert all(
                r["status"] == "answered" and r["query_trace_id"] for r in records
            )
            assert len({r["query_trace_id"] for r in records}) == 6
            assert (directory / "scorer-closed").exists()
            print("shutdown: lifespan closed scorer after fixture release")
        counts = (directory / "active-counts").read_text().splitlines()
        assert counts == ["0"] * 5, counts
        print("operation registry active counts at held scorer entries:", counts)
    finally:
        hold.unlink(missing_ok=True)
        if server.poll() is None:
            server.kill()
        server.wait(timeout=5)


if __name__ == "__main__":
    if len(sys.argv) == 4:
        serve(Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3]))
    else:
        with tempfile.TemporaryDirectory(prefix="seneca-lifecycle-") as temp:
            run(Path(temp), Path(sys.argv[1]).resolve())
