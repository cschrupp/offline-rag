"""Local llama-server subprocess manager for CPU-GGUF-01.

Authority: S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-AUTH-001

Does not download artifacts. Requires pre-existing pinned llama-server binary
and exact Q8_0 GGUF path with SHA verification before launch.
"""

from __future__ import annotations

import hashlib
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from offline_rag.dense.cpu_gguf_feasibility import (
    EXPECTED_GGUF_FILENAME,
    EXPECTED_GGUF_REPO_ID,
    EXPECTED_GGUF_REVISION,
    EXPECTED_GGUF_SHA256,
    FROZEN_N_GPU_LAYERS,
    FROZEN_POOLING,
    FROZEN_THREADS,
    FROZEN_THREADS_BATCH,
)


@dataclass(frozen=True)
class LlamaServerIdentity:
    absolute_path: str
    binary_sha256: str
    version_output: str
    cpu_architecture: str


@dataclass(frozen=True)
class GgufArtifactIdentity:
    path: str
    sha256: str
    size_bytes: int
    repo: str
    revision: str
    filename: str


@dataclass(frozen=True)
class LlamaServerLaunchRecord:
    command: list[str]
    host: str
    port: int
    base_url: str
    n_gpu_layers: int
    pooling: str
    threads: int
    threads_batch: int
    embeddings: bool
    no_webui: bool
    model_path: str
    binary: LlamaServerIdentity
    gguf: GgufArtifactIdentity


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def verify_official_gguf(path: Path) -> GgufArtifactIdentity:
    if not path.is_file():
        raise FileNotFoundError(f"GGUF not found: {path}")
    digest = sha256_file(path)
    if digest.lower() != EXPECTED_GGUF_SHA256.lower():
        raise ValueError(
            "GGUF SHA mismatch: "
            f"got {digest} expected {EXPECTED_GGUF_SHA256} "
            f"(repo={EXPECTED_GGUF_REPO_ID} rev={EXPECTED_GGUF_REVISION} "
            f"file={EXPECTED_GGUF_FILENAME})"
        )
    return GgufArtifactIdentity(
        path=str(path.resolve()),
        sha256=digest.lower(),
        size_bytes=int(path.stat().st_size),
        repo=EXPECTED_GGUF_REPO_ID,
        revision=EXPECTED_GGUF_REVISION,
        filename=EXPECTED_GGUF_FILENAME,
    )


def probe_llama_server_binary(path: Path) -> LlamaServerIdentity:
    if not path.is_file():
        raise FileNotFoundError(f"llama-server not found: {path}")
    resolved = path.resolve()
    digest = sha256_file(resolved)
    try:
        completed = subprocess.run(
            [str(resolved), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        version_output = (
            (completed.stdout or "") + (completed.stderr or "")
        ).strip()
    except Exception as exc:  # noqa: BLE001
        version_output = f"<version probe failed: {exc}>"
    # uname -m via Python
    import platform

    return LlamaServerIdentity(
        absolute_path=str(resolved),
        binary_sha256=digest.lower(),
        version_output=version_output[:4000],
        cpu_architecture=platform.machine(),
    )


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def build_llama_server_command(
    *,
    binary: Path,
    model: Path,
    host: str,
    port: int,
    threads: int = FROZEN_THREADS,
    threads_batch: int = FROZEN_THREADS_BATCH,
    n_gpu_layers: int = FROZEN_N_GPU_LAYERS,
    pooling: str = FROZEN_POOLING,
) -> list[str]:
    if int(n_gpu_layers) != 0:
        raise ValueError("CPU-GGUF-01 requires --n-gpu-layers 0")
    if pooling != "last":
        raise ValueError("CPU-GGUF-01 requires --pooling last")
    return [
        str(binary.resolve()),
        "--model",
        str(model.resolve()),
        "--host",
        host,
        "--port",
        str(int(port)),
        "--embeddings",
        "--pooling",
        pooling,
        "--n-gpu-layers",
        str(int(n_gpu_layers)),
        "--threads",
        str(int(threads)),
        "--threads-batch",
        str(int(threads_batch)),
        "--no-webui",
    ]


class LlamaServerProcess:
    """Manage a local llama-server subprocess for embedding experiments."""

    def __init__(
        self,
        *,
        binary_path: Path,
        gguf_path: Path,
        host: str = "127.0.0.1",
        port: int | None = None,
        threads: int = FROZEN_THREADS,
        threads_batch: int = FROZEN_THREADS_BATCH,
        ready_timeout_s: float = 300.0,
        poll_interval_s: float = 0.5,
    ) -> None:
        self.binary_path = Path(binary_path)
        self.gguf_path = Path(gguf_path)
        self.host = host
        self.port = int(port) if port is not None else _pick_free_port()
        self.threads = int(threads)
        self.threads_batch = int(threads_batch)
        self.ready_timeout_s = float(ready_timeout_s)
        self.poll_interval_s = float(poll_interval_s)
        self._proc: subprocess.Popen[str] | None = None
        self.launch_record: LlamaServerLaunchRecord | None = None
        self.stdout_log: list[str] = []
        self.stderr_log: list[str] = []

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> LlamaServerLaunchRecord:
        if self._proc is not None:
            raise RuntimeError("llama-server already started")

        binary = probe_llama_server_binary(self.binary_path)
        gguf = verify_official_gguf(self.gguf_path)
        command = build_llama_server_command(
            binary=self.binary_path,
            model=self.gguf_path,
            host=self.host,
            port=self.port,
            threads=self.threads,
            threads_batch=self.threads_batch,
            n_gpu_layers=FROZEN_N_GPU_LAYERS,
            pooling=FROZEN_POOLING,
        )
        if "--n-gpu-layers" not in command or "0" not in command:
            raise RuntimeError("fail-closed: --n-gpu-layers 0 missing from command")

        self._proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        record = LlamaServerLaunchRecord(
            command=list(command),
            host=self.host,
            port=self.port,
            base_url=self.base_url,
            n_gpu_layers=FROZEN_N_GPU_LAYERS,
            pooling=FROZEN_POOLING,
            threads=self.threads,
            threads_batch=self.threads_batch,
            embeddings=True,
            no_webui=True,
            model_path=gguf.path,
            binary=binary,
            gguf=gguf,
        )
        self.launch_record = record
        self.wait_until_ready()
        return record

    def wait_until_ready(self) -> None:
        if self._proc is None:
            raise RuntimeError("llama-server not started")
        deadline = time.monotonic() + self.ready_timeout_s
        last_error: str | None = None
        with httpx.Client(timeout=2.0) as client:
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    self._drain_pipes()
                    raise RuntimeError(
                        "llama-server exited before ready: "
                        f"code={self._proc.returncode} "
                        f"stderr={''.join(self.stderr_log)[-2000:]}"
                    )
                try:
                    response = client.get(f"{self.base_url}/health")
                    if response.status_code == 200:
                        return
                    last_error = f"health status {response.status_code}"
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                time.sleep(self.poll_interval_s)
        raise TimeoutError(
            f"llama-server not ready within {self.ready_timeout_s}s "
            f"(last_error={last_error})"
        )

    def stop(self, *, timeout_s: float = 30.0) -> int | None:
        if self._proc is None:
            return None
        proc = self._proc
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=timeout_s)
        self._drain_pipes()
        code = proc.returncode
        self._proc = None
        return code

    def _drain_pipes(self) -> None:
        if self._proc is None:
            return
        if self._proc.stdout is not None:
            try:
                out = self._proc.stdout.read()
                if out:
                    self.stdout_log.append(out)
            except Exception:  # noqa: BLE001
                pass
        if self._proc.stderr is not None:
            try:
                err = self._proc.stderr.read()
                if err:
                    self.stderr_log.append(err)
            except Exception:  # noqa: BLE001
                pass

    def launch_record_dict(self) -> dict[str, Any]:
        if self.launch_record is None:
            return {}
        return asdict(self.launch_record)


__all__ = [
    "GgufArtifactIdentity",
    "LlamaServerIdentity",
    "LlamaServerLaunchRecord",
    "LlamaServerProcess",
    "build_llama_server_command",
    "probe_llama_server_binary",
    "sha256_file",
    "verify_official_gguf",
]
