# Slice 18B — Workstation Distribution

**Authority:** `S18B-WORKSTATION-DISTRIBUTION-IMPL-001`
**Revision:** `S18B-WORKSTATION-DISTRIBUTION-REV2-001`
**Starting point:** `8431c134d2f85e74afe80febd0ca75ac451f65f1`
**Implementation branch:** `feature/slice18b-workstation-distribution`
**Native-Windows spike branch:** `spike/slice18b-native-windows-portability`

## Objective and supported boundary

Deliver the existing Seneca API and compiled React UI as a non-Docker, user-owned
workstation installation on Linux x86-64 and Windows 11 + WSL2 x86-64. Both
supported targets use the locked CPU dependency selection and the existing
`AUTO` compute resolver. Native Windows is a separate feasibility spike only.
CUDA packaging, macOS, ARM, hosted deployment, and a Windows installer/service
remain deferred.

The installer reuses the existing FastAPI server, `ApplicationRuntime`,
configuration loader, `/data` and `/models` environment overrides, model
provisioners/validators, `offline-rag doctor`, strict-offline behavior, and
compiled-UI static serving. It does not create another application, API,
configuration model, persistence model, retrieval path, or runtime selector.

## Dependency and network contract

The release builder creates a versioned workstation `.tar.gz` and detached
SHA-256 file. Git and Node.js 22 are builder-only requirements. The end-user
archive carries `RELEASE.json`, an internal `SHA256SUMS`, the locked Python
payload, support scripts, and compiled UI. Installation requires no repository
checkout or frontend build on the target host.

Install the runtime with the existing locked CPU graph only:

```sh
uv sync --locked --no-dev --extra cpu-release --no-editable
```

Use the same uv release as the accepted REL-01 image (`0.11.18`), and download
the official x86-64 Linux archive only when no suitable uv is already present.
For the official `uv-x86_64-unknown-linux-gnu.tar.gz` release archive, the pinned SHA-256 is `588f3e360f69ce02b6982aa99f2240e803933a6b7e176ac01617830adf955add`. Verify it before extraction or execution. Use uv-managed Python
3.14 rather than the host's default interpreter. Do not install `cuda-dev`,
NVIDIA Python distributions, or another lockfile; do not force
`indexing.embedding.device` away from `auto`.

Seneca binds only to `127.0.0.1`; non-loopback access is never enabled. Both
ordinary Linux and WSL use Ollama on `http://127.0.0.1:11434/v1` in the same
Linux environment as Seneca. The endpoint and selected model must be in both
the generation configuration and approved allowlists. No cloud fallback or
automatic generator-model pull is permitted.

Provisioning is an explicit online operation. After it completes, tokenizer,
Docling, embedding, and reranker assets are validated through their existing
contracts. Runtime uses the existing local-files-only behavior. The qualified
`onnx_fp32_v1` embedding representation is copied from a locally supplied
accepted source and installed by the existing bundle-aware provisioner; it is
not regenerated from Torch and no model hosting service is added. Ollama owns
generator weights separately from Seneca's model directory.

## Filesystem and state

Default roots follow XDG conventions:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/seneca/
├── app -> releases/<release-id>  stable active-release link
├── releases/                     immutable versioned app and venv releases
├── data/      durable Seneca state from OFFLINE_RAG_DATA_DIR
└── models/    provisioned non-generator assets from OFFLINE_RAG_MODELS_DIR

${XDG_CONFIG_HOME:-$HOME/.config}/seneca/
├── workstation.env
└── installation.json

${XDG_BIN_HOME:-$HOME/.local/bin}/seneca
```

An installer rerun creates a versioned release in its final location, validates
the non-editable venv, package, CLI, config and UI there, then atomically
switches the stable `app` link. It never moves a created virtual environment.
Previous releases remain available for recovery, while `data/` and `models/`
are preserved. Do not place credentials in repository-controlled files.

On WSL2, mutable Seneca data must be on the distro's Linux filesystem. Reject
Windows-mounted/drvfs data roots such as `/mnt/c`. Source files selected for
explicit ingestion may remain on a Windows mount. Explain that unregistering a
WSL distro deletes its Linux filesystem and that valuable data must be exported
or copied before distro removal. No backup/restore command is added.

Report WSL-visible `MemTotal` and `MemAvailable`; do not alter `.wslconfig` or
change the accepted large-PDF gate. A visible environment that fails the
existing >25 MiB PDF profile/resource requirements may still install and use
the ordinary 25 MiB source envelope; warn that the larger-PDF path is
unavailable and that WSL memory can be changed outside Seneca.

## Application, frontend, provisioning

Install only the application runtime inputs (package source, `pyproject.toml`,
`uv.lock`, `config/`, compiled UI, and required support files). The resulting
package must be non-editable and import from its installed virtual environment.
Build the UI from files tracked by the exact candidate commit using Node.js 22,
`npm ci`, and the production build. Never consume a source-checkout `ui/dist`;
it may be ignored or stale and has no candidate-bound provenance. Vite dev mode
is not a workstation runtime.

Use the existing commands and validators for Docling, tiktoken, Qwen ONNX,
and BGE reranker. Provision into `models/`; fail closed for missing, corrupt,
wrong-revision, or invalid artifacts. Record model IDs/revisions and licensing
for included/provisioned assets. Do not provision CUDA or Ollama generator
weights into `/models`.

## Service lifecycle and metadata

Use one systemd user service contract on Linux and WSL. It launches exactly:

```text
<app>/.venv/bin/python -m offline_rag.api.server
```

with the installation environment file. Require the user service manager; if
unavailable, fail the service-install step with clear setup guidance. Do not
fall back to `nohup`, PID files, a Python supervisor, or another daemon.
Provide `seneca start|stop|restart|status|logs|doctor ...` as a thin command
wrapper. Preserve one worker, loopback binding, SIGTERM shutdown, and current
runtime drain/grace semantics. Require systemd user-manager lingering so the
service outlives the installer/launching shell while its Linux environment is
running. For WSL, the distro may still stop according to Windows/WSL lifecycle
policy; reopening or restarting the distro and its enabled service restores
availability. Do not add a Windows-side keepalive or lifecycle integration in
Slice 18B. No TLS/authentication changes are in scope.

`installation.json` is bounded support metadata only: schema, source SHA,
install time, target/architecture, Python/uv versions, application/data/models/UI
roots, service mechanism, local generator endpoint/model and WSL-visible memory
when relevant. It must not contain prompts, source names/content, credentials,
or environment dumps.

## Native-Windows feasibility spike

The spike is kept on `spike/slice18b-native-windows-portability` and separate
from Linux/WSL workstation acceptance. It may introduce one project-owned lock
abstraction preserving live-owner exclusivity, process-death release, blocking
and nonblocking acquisition, no timeout theft, and existing acquisition order
and error mapping. A persistent lock file alone is not ownership. POSIX uses
`fcntl.flock`; Windows may use a standard-library mechanism only if it meets
the same contract. No new locking dependency is authorized without a blocker
handoff.

POSIX-only telemetry imports must not prevent native-Windows import/startup;
unsupported measurements stay unavailable rather than fabricated. Run native
W0–W3 (imports, doctor, runtime construction, lease semantics) and report one
of the authorized spike dispositions. Do not build an installer or Windows
service. This spike does not delay Linux/WSL delivery.

## Qualification and evidence

Qualification has two cells: **18B-R** uses the existing Docker release for
runtime/API/UI, local model, ingestion/query, strict-offline, and persistence
checks; **18B-P** builds and verifies the workstation archive, package contents,
integrity checks, provenance, and installer semantics. The sandbox does not
expose a systemd user manager, so dynamic service lifecycle testing is deferred
to a real host. WSL distro lifecycle behavior is also deferred; no Windows-side
keepalive is in scope. These limitations must be reported as deferred, not
passed. No latency SLO is created. Evidence must be observed, sanitized, and
stored under
`docs/evidence/slice18b_workstation/`; never commit user corpus/model bytes,
secrets, or unsanitized machine logs.

No CUDA release artifact, cloud deployment, authentication/TLS, mirrored WSL
networking, `.wslconfig` edits, Windows-host Ollama topology, backup/restore,
offline bundle, model-hosting service, auto-update, telemetry service, or
product behavior change is authorized. Do not promote to `main` under this
authority.
