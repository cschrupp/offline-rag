# Slice 18C — Candidate Build and Qualification Record

**Authority:** `S18C-UNIVERSAL-DISTRIBUTION-IMPL-001`  
**Canonical base:** `e98fc147fe754936152024aa6630a17c43aa15da`  
**Implementation candidate:** `2bae0a23aa9051bc0ca2b9276b421d2293423d51`  
**Branch:** `feature/slice18c-universal-distribution`  
**Disposition:** implementation and available local build checks complete; ready
for independent review. This is not Human acceptance or promotion.

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
