"""Single-send HTTP transport inside the diagnostic network namespace."""

import http.client
import json
import socket
import sys
from pathlib import Path
from time import monotonic, sleep


def submit(spec):
    payload = json.dumps(spec["body"]).encode()
    ordinal = spec["ordinal"]
    endpoint = spec["path"]
    journal = Path("/stage2-journal")
    connection = socket.create_connection(("127.0.0.1", 8080), timeout=spec["timeout"])
    try:
        head = (
            f"POST {endpoint} HTTP/1.1\r\nHost: localhost\r\n"
            f"X-Stage2-Ordinal: {ordinal}\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n"
        ).encode("ascii")
        connection.sendall(head + payload)
        with (journal / f"{ordinal}.sent").open("x") as sent:
            sent.write("socket send complete\n")
        if spec.get("disconnect_at"):
            marker = journal / f"{ordinal}.{spec['disconnect_at']}"
            deadline = monotonic() + spec.get("barrier_timeout", 30)
            while not marker.exists():
                if monotonic() >= deadline:
                    raise TimeoutError("server did not reach requested barrier")
                sleep(0.01)
            connection.close()
            (journal / f"{ordinal}.transport_closed").touch(exist_ok=False)
            return {"transport": "client_disconnected", "http_status": None}
        response = http.client.HTTPResponse(connection)
        response.begin()
        body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError("response exceeds diagnostic bound")
        return {
            "transport": "response",
            "http_status": response.status,
            "body": json.loads(body) if body else {},
        }
    except (TimeoutError, OSError, http.client.HTTPException) as exc:
        return {"transport": type(exc).__name__, "http_status": None}
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(submit(json.load(sys.stdin))))
