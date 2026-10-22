"""Local llama-server subprocess manager for CPU-GGUF-01.

Authority: S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-AUTH-001
Rework: S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-REWORK-AUTH-001

Does not download artifacts. Requires pre-existing pinned llama-server binary
and exact Q8_0 GGUF path with SHA verification before launch.

F001: screen/parity pin expected_llama_server_sha256 before launch.
F002: file-backed stdout/stderr (never unread PIPE).
F003: --version probe is fail-closed with recorded exit code.
"""

from __future__ import annotations

import hashlib
import platform
import socket
import subprocess
import tempfile
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

_LOG_TAIL_CHARS = 4000


@dataclass(frozen=True)
class LlamaServerIdentity:
    absolute_path: str
    binary_sha256: str
    version_output: str
    version_exit_code: int
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
    stdout_log_path: str
    stderr_log_path: str


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
    """Fail-closed binary identity: SHA256 + successful nonempty --version."""
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
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"llama-server --version probe failed with exception: {exc}"
        ) from exc

    version_output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    if completed.returncode != 0:
        raise RuntimeError(
            "llama-server --version exited non-zero: "
            f"code={completed.returncode} output={version_output[:500]!r}"
        )
    if not version_output:
        raise RuntimeError(
            "llama-server --version produced empty stdout/stderr "
            f"(exit={completed.returncode})"
        )

    return LlamaServerIdentity(
        absolute_path=str(resolved),
        binary_sha256=digest.lower(),
        version_output=version_output[:4000],
        version_exit_code=int(completed.returncode),
        cpu_architecture=platform.machine(),
    )


def require_llama_server_sha256(
    path: Path,
    *,
    expected_llama_server_sha256: str,
) -> LlamaServerIdentity:
    """Fail closed before launch if binary SHA does not match Stage-0 pin."""
    expected = str(expected_llama_server_sha256 or "").strip().lower()
    if not expected:
        raise ValueError(
            "expected_llama_server_sha256 is required "
            "(accepted Stage-0 llama-server binary SHA)"
        )
    identity = probe_llama_server_binary(path)
    if identity.binary_sha256 != expected:
        raise ValueError(
            "llama-server binary SHA mismatch: "
            f"got {identity.binary_sha256} expected {expected}"
        )
    return identity


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


def _read_tail(path: Path | None, *, max_chars: int = _LOG_TAIL_CHARS) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"<log read failed: {exc}>"
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


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
        log_dir: Path | None = None,
        expected_llama_server_sha256: str | None = None,
    ) -> None:
        self.binary_path = Path(binary_path)
        self.gguf_path = Path(gguf_path)
        self.host = host
        self.port = int(port) if port is not None else _pick_free_port()
        self.threads = int(threads)
        self.threads_batch = int(threads_batch)
        self.ready_timeout_s = float(ready_timeout_s)
        self.poll_interval_s = float(poll_interval_s)
        self._log_dir_arg = Path(log_dir) if log_dir is not None else None
        self.expected_llama_server_sha256 = (
            str(expected_llama_server_sha256).strip().lower()
            if expected_llama_server_sha256 is not None
            else None
        )
        self._proc: subprocess.Popen[str] | None = None
        self.launch_record: LlamaServerLaunchRecord | None = None
        self.log_dir: Path | None = None
        self.stdout_path: Path | None = None
        self.stderr_path: Path | None = None
        self._stdout_fh: Any | None = None
        self._stderr_fh: Any | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> LlamaServerLaunchRecord:
        if self._proc is not None:
            raise RuntimeError("llama-server already started")

        if self.expected_llama_server_sha256 is not None:
            binary = require_llama_server_sha256(
                self.binary_path,
                expected_llama_server_sha256=self.expected_llama_server_sha256,
            )
        else:
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

        if self._log_dir_arg is not None:
            self.log_dir = self._log_dir_arg
            self.log_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.log_dir = Path(tempfile.mkdtemp(prefix="cpu_gguf_llama_"))
        self.stdout_path = self.log_dir / "llama-server.stdout.log"
        self.stderr_path = self.log_dir / "llama-server.stderr.log"
        self._stdout_fh = self.stdout_path.open("w", encoding="utf-8")
        self._stderr_fh = self.stderr_path.open("w", encoding="utf-8")

        self._proc = subprocess.Popen(
            command,
            stdout=self._stdout_fh,
            stderr=self._stderr_fh,
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
            stdout_log_path=str(self.stdout_path),
            stderr_log_path=str(self.stderr_path),
        )
        self.launch_record = record
        try:
            self.wait_until_ready()
        except Exception:
            # Preserve log tails for startup failures before re-raising.
            self.flush_logs()
            raise
        return record

    def wait_until_ready(self) -> None:
        if self._proc is None:
            raise RuntimeError("llama-server not started")
        deadline = time.monotonic() + self.ready_timeout_s
        last_error: str | None = None
        with httpx.Client(timeout=2.0) as client:
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    diag = self.log_diagnostics()
                    raise RuntimeError(
                        "llama-server exited before ready: "
                        f"code={self._proc.returncode} "
                        f"stderr_tail={diag.get('stderr_tail', '')[-2000:]!r} "
                        f"stderr_log={diag.get('stderr_log_path')}"
                    )
                try:
                    response = client.get(f"{self.base_url}/health")
                    if response.status_code == 200:
                        return
                    last_error = f"health status {response.status_code}"
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                time.sleep(self.poll_interval_s)
        diag = self.log_diagnostics()
        raise TimeoutError(
            f"llama-server not ready within {self.ready_timeout_s}s "
            f"(last_error={last_error}; "
            f"stderr_tail={diag.get('stderr_tail', '')[-1000:]!r}; "
            f"stderr_log={diag.get('stderr_log_path')})"
        )

    def flush_logs(self) -> None:
        for fh in (self._stdout_fh, self._stderr_fh):
            if fh is not None:
                try:
                    fh.flush()
                except Exception:  # noqa: BLE001
                    pass

    def log_diagnostics(self) -> dict[str, Any]:
        self.flush_logs()
        return {
            "stdout_log_path": str(self.stdout_path) if self.stdout_path else None,
            "stderr_log_path": str(self.stderr_path) if self.stderr_path else None,
            "stdout_tail": _read_tail(self.stdout_path),
            "stderr_tail": _read_tail(self.stderr_path),
        }

    def stop(self, *, timeout_s: float = 30.0) -> int | None:
        if self._proc is None:
            self._close_log_handles()
            return None
        proc = self._proc
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=timeout_s)
        self.flush_logs()
        code = proc.returncode
        self._proc = None
        self._close_log_handles()
        return code

    def _close_log_handles(self) -> None:
        for attr in ("_stdout_fh", "_stderr_fh"):
            fh = getattr(self, attr)
            if fh is not None:
                try:
                    fh.close()
                except Exception:  # noqa: BLE001
                    pass
                setattr(self, attr, None)

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
    "require_llama_server_sha256",
    "sha256_file",
    "verify_official_gguf",
]
