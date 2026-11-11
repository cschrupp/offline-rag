# Slice 18B Workstation Installation

This is the user-facing procedure for the Linux x86-64 and Windows 11 + WSL2
CPU workstation package. Native Windows is not an installation target. It is a
separate portability spike and has no installer or Windows service.

## Prerequisites

- Ubuntu 24.04 x86-64 (native Linux or an Ubuntu 24.04 WSL2 distribution).
- A functioning systemd user manager. WSL distributions must have systemd
  enabled and the distro restarted before installation.
- Ollama running in the same Linux environment on `127.0.0.1:11434`, with the
  chosen model already present. Pulling a model is an explicit operator action;
  Seneca never pulls it or falls back to a cloud endpoint.
- A local copy of the already-qualified `onnx_fp32_v1` bundle for explicit
  provisioning. It is not generated from another representation.
- Internet access during initial dependency and artifact provisioning only.

Check the Ollama model name and service before running the installer. The
installer preflight verifies the local API and selected model. It also requires
the Linux service, archive, hashing, and filesystem tools used by the bounded
install. The install command verifies the pinned uv release archive before
extracting or executing it.

## Install from a source checkout

From the Seneca repository root:

```bash
bash scripts/workstation/install.sh --ollama-model qwen3.5:14b
```

Custom persistent roots may be supplied explicitly:

```bash
bash scripts/workstation/install.sh --ollama-model qwen3.5:14b \
  --data-dir "$HOME/seneca-state" --models-dir "$HOME/seneca-models"
```

On WSL2, each configured root must resolve to the distro's Linux filesystem.
The application and configuration locations continue to follow their XDG
defaults.

The frontend uses the committed/prebuilt `ui/dist` when available. Otherwise,
the installer requires Node.js 22 and runs `npm ci` and the production build in
the staged application copy. It never runs Vite development mode as the
installed UI.

The installer uses the locked CPU release dependency extra and a uv-managed
Python 3.14 environment. It stages and validates an installed, non-editable
package before replacing the prior application. Previous app versions are
retained for recovery. Reinstallation does not remove Seneca data or models.
Install from a clean, committed Git checkout so `installation.json` identifies
the exact source revision. The installer rejects a dirty or non-Git source
tree before it creates the installation roots.

## State locations

The defaults follow XDG roots:

- Application: `~/.local/share/seneca/app`
- Durable workspace state: `~/.local/share/seneca/data`
- Seneca-managed model artifacts: `~/.local/share/seneca/models`
- Private environment and bounded install metadata:
  `~/.config/seneca/workstation.env` and `installation.json`
- Command: `~/.local/bin/seneca`

`workstation.env` is created with mode `0600`. It binds the API to loopback,
enables strict-offline runtime behavior, and approves only the selected local
Ollama endpoint/model. Review that file before making local configuration
changes. Installation metadata contains paths and versions, not an environment
dump or credentials.

On WSL2, keep mutable Seneca data and models inside the distribution's Linux
filesystem, not under `/mnt/c` or another Windows-mounted filesystem. Removing
or unregistering the WSL distribution removes that Linux filesystem. Export or
copy valuable data before removing a distribution; this package does not add a
backup/restore command.

## Service commands

Add `~/.local/bin` to `PATH` if it is not already present, then use:

```bash
seneca start
seneca status
seneca logs
seneca restart
seneca stop
seneca doctor
```

The single systemd user service runs the existing API module with one worker,
loopback binding, and the existing SIGTERM/runtime-drain behavior. If the user
service manager is unavailable, installation fails with setup guidance; there
is no `nohup`, PID-file, or custom-supervisor fallback. Open the UI at
`http://127.0.0.1:8080` after the service reports ready.

## Explicit model/artifact provisioning

Provisioning is a separate network-enabled operator action. Give the qualified
ONNX bundle as a local directory:

```bash
bash "${XDG_DATA_HOME:-$HOME/.local/share}/seneca/app/scripts/workstation/provision.sh" \
  --onnx-source /path/to/onnx_fp32_v1
```

This invokes the existing Docling, tiktoken, embedding, and reranker
provisioners, then runs `offline-rag doctor`. It does not download, convert,
host, or place Ollama generator weights in Seneca's `/models` tree. The
existing provisioners validate configured model IDs, revisions, manifests,
and representation contracts. Keep a record of the selected model IDs,
revisions, and their applicable licenses with the local deployment records.
After provisioning, ordinary application runtime is strict-offline and uses
local-files-only model behavior.

The currently configured retrieval assets are:

| Asset | Model ID | Pinned revision | Declared model license |
| --- | --- | --- | --- |
| Embedding | `Qwen/Qwen3-Embedding-0.6B` | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | Apache-2.0 ([model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)) |
| Reranker | `BAAI/bge-reranker-v2-m3` | `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` | Apache-2.0 ([model card](https://huggingface.co/BAAI/bge-reranker-v2-m3)) |

The model identifiers above are separate from Seneca's provisioned artifact
manifests. Retain the generated manifests/digests for the actual installed
Docling, tokenizer, embedding, and reranker artifacts. The Ollama generator is
operator-selected and separately managed; review its model card and license
before pulling it. No generator model is bundled by this package.

The default Docling PDF pipeline also provisions these model repositories
through locked Docling 2.126.0. The revisions below are the revisions selected
by that Docling release; `main` is a moving reference, so retain the resolved
artifact manifest/digest for each actual provisioning event.

| Docling asset | Repository | Docling-selected revision | Declared model license |
| --- | --- | --- | --- |
| Layout (Transformers) | `docling-project/docling-layout-heron` | `main` | Apache-2.0 ([model card](https://huggingface.co/docling-project/docling-layout-heron)) |
| Layout (ONNX Runtime) | `docling-project/docling-layout-heron-onnx` | `main` | Apache-2.0 ([model card](https://huggingface.co/docling-project/docling-layout-heron-onnx)) |
| Table structure (TableFormer) | `docling-project/docling-models` | `v2.3.0` | Apache-2.0 and CDLA-Permissive-2.0 ([model repository](https://huggingface.co/docling-project/docling-models/tree/v2.3.0)) |
| Code and formula recognition | `docling-project/CodeFormulaV2` | `main` | CDLA-Permissive-2.0 ([model card](https://huggingface.co/docling-project/CodeFormulaV2)) |
| Figure classification | `docling-project/DocumentFigureClassifier-v2.5` | `main` | MIT ([model card](https://huggingface.co/docling-project/DocumentFigureClassifier-v2.5)) |
| OCR (default RapidOCR ONNX assets) | `RapidAI/RapidOCR`, PP-OCRv6 | Package default for locked RapidOCR | Apache-2.0 for upstream PP-OCRv6 assets; retain the [RapidOCR attribution and asset notice](https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/) |

The local tokenizer artifact is `tiktoken`'s `cl100k_base` encoding. The
`tiktoken` package is MIT-licensed; retain its
[license](https://github.com/openai/tiktoken/blob/main/LICENSE) and the
provisioned tokenizer manifest/digest. The provisioning manifest identifies
the encoding and package version but does not make a separate license claim
for the downloaded encoding bytes; review the upstream artifact terms before
redistributing those bytes. License labels above describe upstream
declarations and do not replace review of notices shipped with the resolved
artifacts.

## WSL memory and large PDFs

The installer reports WSL-visible `MemTotal` and `MemAvailable`. When those
values do not meet the existing large-PDF resource profile, installation still
works and ordinary 25 MiB sources remain supported; the larger-source path is
reported unavailable. The installer does not edit `.wslconfig` or alter any
accepted capacity gate. WSL memory may be adjusted outside Seneca, followed by
restarting the distribution.

## Qualification status

Installing from a checkout is not the clean-machine 18B-1 qualification. The
Ubuntu and Windows 11 + WSL2 qualification cells must use the same reviewed
candidate on clean environments and record the required install, provisioning,
Ollama, doctor, API/UI, ingestion, grounded-query, restart-persistence,
terminal-independence, strict-offline, CPU-profile, WSL-path/memory, and
descriptive latency observations. No latency SLO is introduced.

## Uninstall

To stop and remove only the installed application/service/wrapper while keeping
workspace state and provisioned models:

```bash
systemctl --user disable --now seneca.service
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/seneca.service"
systemctl --user daemon-reload
rm -f "${XDG_BIN_HOME:-$HOME/.local/bin}/seneca"
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/seneca/app"
```

This leaves `seneca/data` and `seneca/models` intact. It also leaves the
installation configuration/metadata and pinned uv tool available for a future
reinstall. Removing workspaces, source files, indexes, or model assets is a
separate destructive action; do not remove those persistent roots unless you
intentionally want to delete that state and have secured any needed copy.
