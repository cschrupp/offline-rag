# Slice 18C — Candidate Build and Qualification Record

**Authority:** `S18C-UNIVERSAL-DISTRIBUTION-IMPL-001`  
**Canonical base:** `e98fc147fe754936152024aa6630a17c43aa15da`  
**Initial implementation candidate:** `2bae0a23aa9051bc0ca2b9276b421d2293423d51`
**Current corrective candidate:** `86db251e6e75253674ec9ac233a358028a71fe4e`
**Branch:** `feature/slice18c-universal-distribution`  
**Current disposition:** CUDA container qualification, the WSL CPU→CUDA→CPU
workstation round-trip, and post-restart service recovery passed. Slice 18C is
ready for independent review; it is not Human accepted or promoted.

## Historical qualification record — initial candidate `2bae0a23`

## Workstation package

The exact-candidate package builder completed from `2bae0a23` using Git archive
source, Node.js `22.23.3`, npm `12.2.0`, and the package's existing `npm ci`
and UI build steps.

| Artifact | Value |
| --- | --- |
| Package | `seneca-workstation-0.1.0-linux-x86_64-2bae0a23aa90.tar.gz` |
| Size | 2,498,355 bytes |
| SHA-256 | `60d441b0b907898df224205e4123028317e2c00dbbbfc46d6c936ba604b65b21` |
| Package source identity | `2bae0a23aa9051bc0ca2b9276b421d2293423d51` |
| UI source identity | `2bae0a23aa9051bc0ca2b9276b421d2293423d51` |

The artifact is ignored local build output under `dist/workstation/`; it is not
committed or published. The package-content closure and installer rejection
paths are covered by the workstation package tests. The installer was not run
against this host's persistent application, model, data, or systemd-user state.

`npm ci` reported 13 audit advisories (10 moderate, 3 high). No automatic
dependency update was run. Vite also emitted the existing large-chunk advisory
for the built UI. These are recorded as build observations, not addressed by
changing the dependency graph in 18C.

## Container variants

Both local image builds completed from the same candidate commit. The first
CPU build attempt timed out retrieving the PyTorch CPU wheel from
`download-r2.pytorch.org`; a retry completed successfully. The CUDA image build
also completed. No image was pushed or deployed.

| Profile | Local tag | Image ID | Size (bytes) | Torch | CUDA build | NVIDIA distributions |
| --- | --- | --- | ---: | --- | --- | ---: |
| CPU | `seneca:0.1.0-cpu` | `sha256:f42fbb7575aa3deec942f2338e903d04665741738e97e32d0e83f2feff314d66` | 2,346,645,292 | `2.14.0+cpu` | `None` | 0 |
| CUDA | `seneca:0.1.0-cuda` | `sha256:5c5956d3b095091ef1b240f7722508ee5497116baa6faa96919cbda4e128aaf4` | 9,956,336,530 | `2.14.0+cu130` | `13.0` | 15 |

Both image labels bind the source revision to
`2bae0a23aa9051bc0ca2b9276b421d2293423d51` and identify their respective
dependency profiles (`cpu-release` and `cuda-dev`). Runtime checks for both
images confirmed:

- installed `offline-rag --help` succeeds;
- `offline_rag` imports from `/app/.venv/lib/python3.14/site-packages`;
- `/app/src` is absent and `uv` is absent from the runtime image;
- the configured non-root identity is UID/GID `10001:10001`;
- `/data` and `/models` contain no pre-provisioned user data or model assets.

The CPU image returned `torch.cuda.is_available() == False` and had zero
`nvidia-*` distributions. The CUDA image had 15 `nvidia-*` distributions. It
was run without GPU device access and returned
`torch.cuda.is_available() == False`; this is not evidence that the CUDA
runtime can execute on a compatible GPU.

The existing `cuda-dev` environment feasibility result remains separate from
image execution: its isolated PyTorch reported CUDA build `13.0` and
`torch.cuda.is_available() == True`. The host's `/usr/lib/wsl/lib/nvidia-smi`
reported `Failed to initialize NVML: GPU access blocked by the operating
system`. These differing observations are not collapsed into a GPU
qualification claim.

## Verification commands

| Command | Result |
| --- | --- |
| `./.venv/bin/pytest -q tests/workstation` | 42 passed |
| `./.venv/bin/pytest -q tests/unit/dense/test_dense_execution_profile.py tests/unit/dense/test_embedding_bundle_provision.py tests/unit/dense/test_dense_embedding_runtime.py` | 55 passed |
| Ruff check on changed Python files | Passed |
| Ruff format check on changed Python files | Passed |
| `bash -n` on installer, package/container builders, and `seneca` wrapper | Passed |
| `git diff --check` | Passed |
| `scripts/workstation/build_package.sh` | Passed; artifact identity above |
| `scripts/workstation/build_container.sh cpu` | Passed on retry |
| `scripts/workstation/build_container.sh cuda` | Passed |
| Local container CLI/import/runtime-boundary smoke on both variants | Passed |

The selected existing embedding regression group is not fully green in this
worktree:

- `test_no_mid_run_cpu_fallback` fails in unchanged
  `src/offline_rag/dense/embedder.py:525` with
  `AttributeError: 'SentenceTransformersEmbedder' object has no attribute
  'effective_batch_size'`.
- A follow-up run of the rest of `test_slice16l_embedding_auto_device.py`
  emitted 15 progress dots and did not finish within 30 seconds. It was
  stopped by the timeout; no pass count is claimed for that run.
- The three dense profile/provision/runtime files listed above passed
  independently. No source under `src/offline_rag/` changed in 18C.

The accepted REL-01 CPU dependency-environment result (209 passed, 0 skipped)
remains prior evidence, not a rerun for this candidate. This tranche did not
perform a full backend suite rerun.

## Not qualified in this environment

- No local embedding or reranker inference call was made.
- No workstation install/upgrade, CUDA enable/disable transition, systemd
  service restart, or persistent user-data mutation was performed.
- The WSL NVML failure prevented a GPU-backed execution check; no GPU was
  attached to the CUDA image.
- No registry push, GitHub Release, cloud deployment, or promotion occurred.

Accordingly, these results establish the dependency profiles, build
reproducibility for the exact candidate, package/image structure, and
non-model local runtime boundaries. They do not establish workstation
installer lifecycle qualification or physical CUDA execution.

## Corrective runtime qualification — candidate `8541f8af`

The first real CUDA embedding smoke on `2bae0a23` reached the qualified
PyTorch/Triton execution path but failed because the runtime image lacked a C
compiler. Corrective commit `7cc0a26c` added GCC only to the CUDA runtime image;
the follow-up smoke then established that Triton's helper compile also requires
the standard C headers (`stdlib.h`). Final corrective candidate `8541f8af`
adds `libc6-dev` alongside GCC, still only for `cuda-dev`. The CPU image remains
without GCC. No application source, dependency lock, model identity, execution
profile, or resolver behavior changed.

Both images and the workstation package were rebuilt from `8541f8af`. The
locked Python dependency graph and CUDA versions are unchanged. The package is
an ignored local build artifact; it was not installed or published.

| Artifact | Final identity |
| --- | --- |
| Workstation package | `seneca-workstation-0.1.0-linux-x86_64-8541f8af3ce7.tar.gz` |
| Package size | 2,498,998 bytes |
| Package SHA-256 | `95726605b639d6c4019c453358831a1b6115c85ee0c183d3cc60116afb49eb6f` |
| Package and UI source SHA | `8541f8af3ce7a4b906a36f252cb1b2f0a4dbc778` |
| CPU image ID / size | `sha256:831b7b91c8ae0fb7cd095687795f2ea3aadf7cf59e07c4c570a497a3e6297b69` / 2,346,639,310 bytes |
| CUDA image ID / size | `sha256:d05883c63674d22a73c2997370a786518947c5198668eac307f9f56475ad743c` / 10,232,401,533 bytes |

Both images carry the `8541f8af` source-revision label. Runtime inspection found
GCC and `/usr/include/stdlib.h` in the CUDA image and no GCC executable in the
CPU image. Image size remains descriptive; no CUDA dependency pruning was
performed.

### Docker and CUDA-container cells

Docker GPU passthrough exposed one `NVIDIA GeForce RTX 2080 Super with Max-Q
Design` to the CUDA image. The final-image resolver contrast on that same host
was:

| Cell | Result | Observed result |
| --- | --- | --- |
| `DOCKER_GPU_PASSTHROUGH` | PASS | PyTorch CUDA initialized; one GPU identity returned |
| `CPU_IMAGE_ON_GPU_HOST` | PASS | Torch `2.14.0+cpu`; CUDA build `None`; `cuda_available=False`; resolver selected `cpu_onnx_fp32_v1` / `onnx_fp32_v1` / `sentence_transformers_onnx` / CPU / FP32 / `CPUExecutionProvider` |
| `CUDA_IMAGE_ON_GPU_HOST` | PASS | Torch `2.14.0+cu130`; CUDA build `13.0`; `cuda_available=True`; one GPU |
| `CUDA_CONTAINER_RESOLVER` | PASS | Resolver selected `cuda_fp16_v1` / `torch_st_v1` / `sentence_transformers_torch` / CUDA / FP16 |
| `CUDA_CONTAINER_EMBEDDING` | PASS | Production factory/runtime, `configured_device=auto`, CUDA available, runtime `READY`, 1,024 finite values, resolved device CUDA, FP16; no fallback |
| `CUDA_CONTAINER_RERANKER` | PASS | One finite score from the local BGE reranker, resolved device CUDA, `raw-logit-v1`, `local_files_only=True` |
| `CUDA_CONTAINER_COMPUTE_API` | PASS | With GPU, read-only models, empty disposable data, and `--network none`: `/health`, `/health/live`, `/health/ready`, `/v1/settings/compute`, `/v1/capabilities`, and `/` returned 200. API projection reported CUDA available, profile `cuda_fp16_v1`, representation `torch_st_v1`, backend `sentence_transformers_torch`, active device CUDA, FP16. |

The CUDA embedding and reranker calls used only synthetic text and the existing
qualified local model assets. The model tree was mounted read-only; the
container had no network. The API container's generation model/approval values
were set to the already-present local Ollama model solely to pass static
startup validation. The API check made no generation request and had no network
access. The API projection correctly reported `embedding_state=UNLOADED` in
that server process; the separate production-runtime smoke above performed the
actual embedding.

The first two CUDA smoke attempts are preserved as implementation diagnostics:
the initial runtime lacked a compiler; the GCC-only attempt lacked C headers.
The final `8541f8af` image passed both smokes. These failures do not get
rewritten as passes for their earlier images.

### Universal workstation transition

The workstation preflight found these normal user paths absent:
`~/.local/share/seneca`, `~/.config/seneca`, and `~/.local/bin/seneca`; there
was no `seneca.service` under the user's systemd scope. WSL-local `ollama` and
`~/.ollama` were also absent. No Seneca installation or persistent data/model/
service state was changed.

Windows PowerShell had previously confirmed a Windows Ollama model. At the
time of this historical attempt, the workstation qualification was treated as
requiring Seneca and Ollama in the same WSL Linux environment. The earlier
WSL-to-Windows API reachability check failed under that then-assumed scope.
The Human authority clarification below supersedes that topology restriction
for current 18C qualification; this historical result is retained without
rewriting what was tested.

To prepare it without changing global services, the official Ollama v0.40.16
Linux runtime was inspected for temporary installation under `/tmp`. The
published archive is 1,545,767,640 bytes. A 4 MiB ranged transfer took 43
seconds; a parallel 128 MiB transfer completed, but the full archive transfer
then stalled, completing only one additional 8 MiB chunk in over a minute.
The transfer was stopped before model download or installation. All partial
download files were removed. No Ollama binary, model, or service was installed
system-wide or in the user's home directory.

| Cell | Result | Reason |
| --- | --- | --- |
| `WORKSTATION_CPU_INSTALL` | NOT EXECUTED | The supported WSL-local Ollama topology was not prepared; the archive was built and identity-checked but not installed. |
| `WORKSTATION_CPU_INFERENCE` | NOT EXECUTED | CPU release was not installed; no workstation inference call was made. |
| `WORKSTATION_CUDA_ENABLE` | NOT EXECUTED | CPU baseline prerequisite was not installed. |
| `WORKSTATION_CUDA_INFERENCE` | NOT EXECUTED | CUDA release was not activated. |
| `WORKSTATION_CPU_RESTORE` | NOT EXECUTED | No CUDA transition was run. |
| `WORKSTATION_POST_RESTORE_INFERENCE` | NOT EXECUTED | CPU restoration was not run. |
| `DATA_PRESERVATION` | NOT EXECUTED | No workstation transition occurred; no preservation claim is made. |
| `MODEL_PRESERVATION` | NOT EXECUTED | No workstation transition occurred; the repository's original `models/` was left untouched and the temporary model copy was removed. |
| `SOURCE_IDENTITY_PRESERVATION` | NOT EXECUTED | No workstation transition occurred. |

The exact-candidate workstation archive's `RELEASE.json` binds both package
and UI source identity to `8541f8af`; the archive SHA-256 was recorded above.
Those package checks do not substitute for installation or CPU→CUDA→CPU
qualification.

### Current 18C Windows Ollama topology clarification

Human authority for current 18C qualification permits Windows-native Ollama
when WSL2 Seneca can reach it through localhost interoperability. The supported
configuration is `OFFLINE_RAG_LLM_BASE_URL=http://127.0.0.1:11434/v1` and
`OFFLINE_RAG_LLM_MODEL=qwen3.6:35b-a3b`. No Linux Ollama executable, service,
or model store is required in WSL. Do not install a duplicate runtime/model
or probe LAN addresses. The endpoint must remain local/private, the selected
model must exist, and no cloud fallback is permitted. This 18C extension does
not rewrite the narrower historical 18B workstation scope.

Two workstation defects were found and corrected during real qualification.
Commit `70b5fb04` corrected invalid Python exception syntax in `host.py` and
`runtime.py`, with a readiness-retry regression. The next service start found
that systemd rejected quoted `EnvironmentFile` and `WorkingDirectory` paths.
Commit `86db251e` now writes systemd path escapes while retaining quoted
`ExecStart`, and its regression covers paths containing spaces. The focused
service-writer tests passed.

Human enabled systemd user lingering for this qualification. Current 18C
preflight passed on WSL2 with ext4 application/data/model paths, 33.5 GB
visible memory (29.6 GB available at preflight), large-PDF memory disposition
available, the systemd user manager active, and the approved Windows-native
Ollama endpoint/model reachable at `127.0.0.1:11434`. No WSL Ollama runtime or
model was installed, and no LAN endpoint was probed.

The corrected package is
`seneca-workstation-0.1.0-linux-x86_64-86db251e6e75.tar.gz`, 2,499,100 bytes,
SHA-256 `810b49e0e09b1bab3284eac8d0d92d30ca606cb73b0aaf658f0a8c8ad82c93a7`.
Its release metadata binds source and UI identity to
`86db251e6e75253674ec9ac233a358028a71fe4e`. Installation succeeded, the
non-editable package imports from the versioned `.venv`, `/app/src` is absent,
and the installed CLI works. The generated systemd unit passed
`systemd-analyze verify` and the service reached `/health/ready` after install
and after each profile transition. `seneca doctor` returned an OK result in an
earlier check, but its displayed generation model/key status conflicted with
the effective local-only config and API state. Direct configuration loading
and the live API confirmed the approved loopback Ollama endpoint/model,
`strict_offline=true`, and no generation API key; the doctor discrepancy is
unresolved and is not treated as authoritative effective configuration.

The initial CPU release reported Torch `2.14.0+cpu`, `torch.version.cuda=None`,
`torch.cuda.is_available()=False`, and zero `nvidia-*` distributions. Under
`embedding.device=auto`, the CPU profile was `cpu_onnx_fp32_v1`,
`onnx_fp32_v1`, `sentence_transformers_onnx`, `CPUExecutionProvider`, FP32.
One synthetic query produced 1,024 finite values and the embedding runtime
reached `READY`. One local CPU reranker score was finite and retained
`raw-logit-v1` with `local_files_only=True`.

After `seneca enable-cuda --yes`, the user service restarted and the compute
projection reported Torch CUDA build `13.0`, CUDA available, and AUTO selecting
`cuda_fp16_v1` / `torch_st_v1` / `sentence_transformers_torch` / CUDA / FP16.
One synthetic query produced 1,024 finite values with runtime state `READY`;
one local CUDA reranker score was finite under the same raw-logit contract.
The observed GPU was `NVIDIA GeForce RTX 2080 Super with Max-Q Design`.

After `seneca disable-cuda`, the retained CPU release was restored and the
service again became ready. The final CPU embedding and reranker smokes passed
with the same results as the initial CPU cell. Across both transitions,
installation metadata returned to the original CPU release/source identity
`86db251e6e75253674ec9ac233a358028a71fe4e`, with `cuda_enabled=false`.
Before the distro restart, the 257-file installed model tree matched the
qualification source inventory (recorded manifest SHA-256
`2ade5cc1e0177884098d24cd974a9da796bff7c507db381b1114dc7d69e65304`), and a
synthetic data marker remained unchanged (SHA-256
`d0fe5d7d791592e19771e975eae4edb1313f061c9089baf745e9ebae4a2e54a1`). After
restart, 257 model files remained present. The temporary file-level manifest
used for the earlier comparison was not retained across the distro restart,
so no new byte-for-byte model comparison is claimed.

All three runtime smoke scripts verified `strict_offline=true`, the approved
loopback Ollama endpoint/model, no generation API key, and zero generator calls.
The service remained active and ready after its launching command exited while
the WSL distro remained running. Human then restarted the `Ubuntu-24.04` WSL
distro and restarted the Codex session. After reconnection, the enabled
`seneca.service` was active, `/health/ready` returned `{"status":"ready"}`,
and `/v1/settings/compute` reported `embedding_device=auto`, resolved CPU,
`cpu_onnx_fp32_v1` / `onnx_fp32_v1`, `CPUExecutionProvider`, Torch CUDA build
`null`, and CUDA unavailable. The installation metadata at
`~/.config/seneca/installation.json` retained the expected source SHA
`86db251e6e75253674ec9ac233a358028a71fe4e`, active CPU release identity,
`cuda_enabled=false`, and the expected data/model roots. The synthetic data
marker hash also matched its pre-restart value. This establishes recovery after
the user-reported distro restart; no model inference was run after restart.

### Corrective validation and current disposition

| Check | Result |
| --- | --- |
| `./.venv/bin/pytest -q tests/workstation` | 43 passed on final corrective candidate |
| Container-profile static regression | 2 passed on final corrective candidate |
| Ruff check and format check for changed test | Passed |
| `git diff --check` | Passed after final evidence update |
| Dense profile/provision/runtime tests | 55 passed on the original implementation candidate; not rerun because no Python application or dependency metadata changed |

The existing unrelated `test_no_mid_run_cpu_fallback` failure at
`src/offline_rag/dense/embedder.py:525` remains previously observed and was not
changed. `npm ci` also retains the previously reported 13 audit advisories and
the Vite large-chunk advisory; no dependency updates were made.

**Current result:** CUDA container distribution and CPU→CUDA→CPU workstation
qualification PASS for the supported Windows 11 + WSL2 topology using
Windows-native Ollama through loopback interoperability. Post-restart service
recovery and CPU-profile restoration also PASS based on the user's reported
Ubuntu distro restart and independently checked service/API/installation state.
No external generation calls were made. The doctor display discrepancy and
absence of a post-restart file-level model comparison are recorded limitations.
Slice 18C is ready for independent review; Human acceptance and promotion remain
pending. Historical package/image measurements and earlier failures above
remain preserved as observations of their exact candidates.
