#!/usr/bin/env python3
"""16H Family H — production container/static delivery smoke.

Builds deploy/Dockerfile, runs one Seneca/OfflineRAG container, verifies:
- non-root UID
- process live (/health)
- / and SPA deep-link serve HTML
- same-origin /v1 JSON surface (200 ready OR structured not-ready error)
- /data writable + /models present under accepted mount contract
- static assets served
- no second frontend service required
- true no-egress static probe via docker exec on --network none helper

Does NOT require /health/ready == 200 (model-ready) for static/API topology PASS.
When Docker is unavailable: exit 2 with ENVIRONMENT BLOCKED.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGE_TAG = "offline-rag:16h-smoke"
CONTAINER_NAME = "offline-rag-16h-smoke"
NETWORK_NONE_PROBE = "offline-rag-16h-netnone-probe"
# Optional BuildKit secret sources (never COPY'd into the image).
_BUILD_CA_CANDIDATES = (
    REPO_ROOT / "deploy" / "certs" / "norton-web-mail-shield-root.crt",
    REPO_ROOT / "deploy" / "certs" / "build_ca.pem",
    REPO_ROOT / "deploy" / "certs" / "build_ca.crt",
)


def _docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(REPO_ROOT), check=True, text=True, **kwargs)


def _http_get(url: str, timeout: float = 5.0) -> tuple[int, str, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ctype = resp.headers.get("Content-Type", "")
            return resp.status, body, ctype
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        ctype = exc.headers.get("Content-Type", "") if exc.headers else ""
        return exc.code, body, ctype


def _wait_live(base: str, timeout_s: float = 120.0) -> None:
    """Wait until the process answers /health (live), not necessarily model-ready."""
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            status, body, _ = _http_get(f"{base}/health")
            if status == 200 and "live" in body:
                return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(1.0)
    raise TimeoutError(f"container not live: {last_err}")


def _v1_same_origin_ok(status: int, body: str, ctype: str) -> bool:
    if not ctype.startswith("application/json"):
        return False
    if status == 200:
        return True
    # Fresh image without full /models may be not-ready; still same-origin JSON API.
    if status in {503, 409}:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return False
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict) and err.get("code"):
            return True
    return False


def _network_none_static_probe(image: str) -> dict:
    """Prove static HTML can be served with no container network at all."""
    subprocess.run(
        ["docker", "rm", "-f", NETWORK_NONE_PROBE],
        cwd=str(REPO_ROOT),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                NETWORK_NONE_PROBE,
                "--network",
                "none",
                "-e",
                "OFFLINE_RAG_STRICT_OFFLINE=true",
                "-e",
                "OFFLINE_RAG_ALLOW_NON_LOOPBACK=true",
                image,
            ]
        )
        # Give the process a moment to bind localhost inside the netns.
        time.sleep(3.0)
        probe = subprocess.run(
            [
                "docker",
                "exec",
                NETWORK_NONE_PROBE,
                "python",
                "-c",
                (
                    "import urllib.request;\n"
                    "r=urllib.request.urlopen('http://127.0.0.1:8080/', timeout=10);\n"
                    "b=r.read().decode('utf-8','replace');\n"
                    "print(r.status);\n"
                    "print('ROOT_OK' if ('<div id=\"root\">' in b or 'Seneca' in b) else 'ROOT_BAD');\n"
                ),
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        out = (probe.stdout or "") + (probe.stderr or "")
        return {
            "exit_code": probe.returncode,
            "stdout": (probe.stdout or "")[-500:],
            "stderr": (probe.stderr or "")[-500:],
            "ok": probe.returncode == 0
            and "200" in out
            and "ROOT_OK" in out,
            "method": "docker run --network none + docker exec urllib GET /",
        }
    finally:
        subprocess.run(
            ["docker", "rm", "-f", NETWORK_NONE_PROBE],
            cwd=str(REPO_ROOT),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=REPO_ROOT / "docs" / "evidence" / "slice16h_container_smoke.json",
    )
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args(argv)

    report: dict = {
        "contract": "slice16h-container-smoke-v3",
        "ok": False,
        "disposition": None,
        "checks": {},
        "model_ready_required_for_pass": False,
        "build_ca_transport": "BUILDKIT_SECRET / BUILD-TIME ONLY",
        "note": (
            "Static/API topology PASS does not require /health/ready. "
            "Model-ready is recorded separately when available. "
            "Optional build_ca BuildKit secret assists npm/pip only and must not "
            "persist in the final runtime trust store."
        ),
    }

    if not _docker_available():
        report["disposition"] = "16H ENVIRONMENT BLOCKED — Docker unavailable"
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return 2

    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        cwd=str(REPO_ROOT),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        if not args.skip_build:
            build_cmd = [
                "docker",
                "build",
                "-f",
                "deploy/Dockerfile",
                "-t",
                IMAGE_TAG,
                ".",
            ]
            build_ca = next((p for p in _BUILD_CA_CANDIDATES if p.is_file()), None)
            if build_ca is not None:
                build_cmd[2:2] = [
                    "--secret",
                    f"id=build_ca,src={build_ca}",
                ]
                report["checks"]["build_ca_secret"] = {
                    "provided": True,
                    "src_basename": build_ca.name,
                    "note": "BuildKit secret only; not in build context / image COPY",
                }
            else:
                report["checks"]["build_ca_secret"] = {
                    "provided": False,
                    "note": "Normal build; no optional build_ca secret",
                }
            print("+", " ".join(build_cmd), flush=True)
            build_env = {**os.environ, "DOCKER_BUILDKIT": "1"}
            build = subprocess.run(
                build_cmd,
                cwd=str(REPO_ROOT),
                text=True,
                capture_output=True,
                check=False,
                env=build_env,
            )
            if build.stdout:
                print(build.stdout[-4000:], flush=True)
            if build.stderr:
                print(build.stderr[-4000:], flush=True)
            if build.returncode != 0:
                combined = (build.stdout or "") + "\n" + (build.stderr or "")
                env_blocked = any(
                    marker in combined
                    for marker in (
                        "CERTIFICATE_VERIFY_FAILED",
                        "unable to get local issuer certificate",
                        "Could not fetch URL https://pypi.org",
                        "No matching distribution found for hatchling",
                    )
                )
                report["ok"] = False
                report["error"] = combined[-2000:]
                report["disposition"] = (
                    "16H ENVIRONMENT BLOCKED — Docker build cannot reach "
                    "PyPI/TLS trust store in this environment"
                    if env_blocked
                    else "FAIL"
                )
                args.json_out.parent.mkdir(parents=True, exist_ok=True)
                args.json_out.write_text(
                    json.dumps(report, indent=2, sort_keys=True) + "\n"
                )
                print(json.dumps(report, indent=2, sort_keys=True))
                return 2 if env_blocked else 1

        data_host = Path("/tmp/offline-rag-16h-smoke-data")
        models_host = Path("/tmp/offline-rag-16h-smoke-models")
        data_host.mkdir(parents=True, exist_ok=True)
        models_host.mkdir(parents=True, exist_ok=True)

        _run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                CONTAINER_NAME,
                "-p",
                "127.0.0.1:18080:8080",
                "-e",
                "OFFLINE_RAG_STRICT_OFFLINE=true",
                "-e",
                "OFFLINE_RAG_ALLOW_NON_LOOPBACK=true",
                "-v",
                f"{data_host}:/data",
                "-v",
                f"{models_host}:/models:ro",
                IMAGE_TAG,
            ]
        )
        base = "http://127.0.0.1:18080"
        _wait_live(base)

        inspect = subprocess.check_output(
            ["docker", "inspect", CONTAINER_NAME], text=True
        )
        meta = json.loads(inspect)[0]
        user = meta["Config"].get("User") or ""
        report["checks"]["container_user"] = user
        report["checks"]["non_root"] = user.startswith("10001") or user == "10001:10001"

        mounts = meta.get("Mounts") or []
        mount_by_dest = {m.get("Destination"): m for m in mounts if isinstance(m, dict)}
        data_m = mount_by_dest.get("/data") or {}
        models_m = mount_by_dest.get("/models") or {}
        report["checks"]["data_mount"] = {
            "present": bool(data_m),
            "rw": bool(data_m.get("RW")),
            "destination": data_m.get("Destination"),
        }
        report["checks"]["models_mount"] = {
            "present": bool(models_m),
            "rw": bool(models_m.get("RW")),
            "readonly": models_m.get("RW") is False,
            "destination": models_m.get("Destination"),
        }

        status, body, ctype = _http_get(f"{base}/health")
        report["checks"]["health_live"] = {"status": status, "body": body[:200]}

        ready_status, ready_body, _ = _http_get(f"{base}/health/ready")
        report["checks"]["health_ready_observed"] = {
            "status": ready_status,
            "body": ready_body[:300],
            "model_ready": ready_status == 200 and "ready" in ready_body,
        }

        status, body, ctype = _http_get(f"{base}/")
        report["checks"]["root_html"] = {
            "status": status,
            "content_type": ctype,
            "has_seneca_title": "Seneca" in body
            or "OfflineRAG" in body
            or '<div id="root">' in body,
        }

        status, body, ctype = _http_get(f"{base}/workspaces/demo")
        report["checks"]["spa_fallback"] = {
            "status": status,
            "serves_index": '<div id="root">' in body or "Seneca" in body,
        }

        status, body, ctype = _http_get(f"{base}/v1/workspaces")
        report["checks"]["api_same_origin"] = {
            "status": status,
            "content_type": ctype,
            "json_surface_ok": _v1_same_origin_ok(status, body, ctype),
            "body_preview": body[:240],
        }

        status, index_html, _ = _http_get(f"{base}/")
        asset_match = re.search(r'src="(/assets/[^"]+\.js)"', index_html)
        if asset_match:
            a_status, _a_body, a_ctype = _http_get(f"{base}{asset_match.group(1)}")
            report["checks"]["static_js_asset"] = {
                "path": asset_match.group(1),
                "status": a_status,
                "content_type": a_ctype,
            }
        else:
            report["checks"]["static_js_asset"] = {"status": "missing_ref_in_index"}

        report["checks"]["network_none_static_probe"] = _network_none_static_probe(
            IMAGE_TAG
        )

        # Runtime trust store must not contain build-host interception CA markers.
        trust_probe = subprocess.run(
            [
                "docker",
                "exec",
                CONTAINER_NAME,
                "python",
                "-c",
                (
                    "from pathlib import Path\n"
                    "blob=''\n"
                    "p=Path('/etc/ssl/certs/ca-certificates.crt')\n"
                    "blob += p.read_text(encoding='utf-8', errors='replace') if p.is_file() else ''\n"
                    "extra=Path('/usr/local/share/ca-certificates')\n"
                    "names=list(extra.glob('*.crt')) if extra.is_dir() else []\n"
                    "for f in names: blob += f.read_text(encoding='utf-8', errors='replace')\n"
                    "markers=['Norton Web/Mail Shield Root',"
                    "'generated by Norton Antivirus for SSL/TLS scanning',"
                    "'OFFLINERAG-16H-TEST-CA-NOT-FOR-RUNTIME']\n"
                    "hit=[m for m in markers if m in blob]\n"
                    "print('EXTRA_CRT_COUNT', len(names))\n"
                    "print('TRUST_HIT', ','.join(hit) if hit else 'NONE')\n"
                ),
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        trust_out = (trust_probe.stdout or "") + (trust_probe.stderr or "")
        report["checks"]["runtime_trust_store"] = {
            "exit_code": trust_probe.returncode,
            "stdout": (trust_probe.stdout or "")[-500:],
            "ok": trust_probe.returncode == 0
            and "TRUST_HIT NONE" in trust_out
            and "EXTRA_CRT_COUNT 0" in trust_out,
        }

        ok = all(
            [
                report["checks"].get("non_root"),
                report["checks"]["health_live"]["status"] == 200,
                report["checks"]["root_html"]["status"] == 200,
                report["checks"]["root_html"]["has_seneca_title"],
                report["checks"]["spa_fallback"]["serves_index"],
                report["checks"]["api_same_origin"]["json_surface_ok"],
                report["checks"]["data_mount"]["present"]
                and report["checks"]["data_mount"]["rw"],
                report["checks"]["models_mount"]["present"]
                and report["checks"]["models_mount"]["readonly"],
                report["checks"]["static_js_asset"].get("status") == 200,
                report["checks"]["network_none_static_probe"]["ok"],
                report["checks"]["runtime_trust_store"]["ok"],
            ]
        )
        report["ok"] = bool(ok)
        report["disposition"] = "PASS" if ok else "FAIL"
        report["image"] = IMAGE_TAG
        report["single_container"] = True
        report["second_frontend_service"] = False
        report["built_from"] = "deploy/Dockerfile"
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["disposition"] = "FAIL"
        report["error"] = str(exc)
    finally:
        subprocess.run(
            ["docker", "rm", "-f", CONTAINER_NAME],
            cwd=str(REPO_ROOT),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
