# REL-01 — CPU Release Packaging

**Status:** REL-01B/C IMPLEMENTATION COMPLETE / INDEPENDENT REVIEW PENDING
**Starting canonical `main`:** `3fb65e34f5b45ddf695d82bfd0d9badd34b9ee2d`
**Branch:** `feature/rel-01-cpu-release-packaging`

## Objective

Produce a materially smaller default Seneca application image by selecting
CPU-only PyTorch in the release container and separating Python dependency
installation from a clean runtime stage. Prove that the existing compute
resolver selects the already-qualified `cpu_onnx_fp32_v1` profile when CUDA is
unavailable.

This is release packaging, not a compute architecture change. The existing
probe, qualified profile resolver/runtime, availability snapshot, Compute API,
and UI remain authoritative. Developer installations continue to support
CUDA-capable PyTorch and `cuda_fp16_v1`.

## Bounded stages

1. **REL-01A — Current packaging baseline:** build the exact starting
   `deploy/Dockerfile`; record Docker environment, image ID/digest, image size,
   history, Python/ML package versions, NVIDIA distributions, and largest
   installed package directories.
2. **REL-01B — CPU dependency selection:** establish a reproducible locked CPU
   production dependency graph using project metadata. Prefer one root
   `pyproject.toml` and `uv.lock`, with an explicit CPU PyTorch source selected
   through a release extra. Verify the full production graph and the existing
   automatic CPU resolver before changing Docker packaging.
3. **REL-01C — Builder/runtime image:** use the UI builder, a Python dependency
   builder, and a clean Python runtime. Keep only installed runtime artifacts,
   packaged config, and UI output. Preserve the existing filesystem, identity,
   environment, secret, and process contracts.
4. **REL-01D — Container qualification:** measure the CPU-dependency
   intermediate and final image using the same host and Docker size metric;
   qualify dependency imports, resolver behavior, health/API/UI behavior, one
  embedding, one reranker operation, filesystem, image contents, and the
  required regression lanes. Any unavailable qualification step must remain
  explicitly open in the evidence report.

## Dependency selection

The root project keeps its normal PyPI-backed Torch resolution for developer
installs. `uv sync --locked` (including the default `dev` group) remains the
ordinary developer path. The release image selects the mutually exclusive
`cpu-release` extra with `uv sync --locked --no-dev --extra cpu-release`,
which pins Torch and TorchVision to the explicit PyTorch CPU index. The
`cuda-dev` extra names the existing PyPI-backed GPU-capable variant for
developers who need to select it explicitly; it cannot be combined with
`cpu-release`.

The stages are parts of one tranche, not separate projects. Commit the
documentation opening, baseline evidence, packaging implementation, and
qualification closeout separately so pre-optimization measurements remain
auditable.

## Preserved contracts

- Python `>=3.14,<3.15`; UID/GID `10001:10001`; `/data` writable and `/models`
  external/read-only.
- One application process and ASGI worker; external generator; no model weights
  or private data in the image.
- `embedding.device=auto` remains the normal configuration. Do not add a
  Docker-specific CPU override or another hardware detector/resolver.
- `cuda_fp16_v1` remains supported for local/GPU-capable installations.
- `build_ca` is temporary build-secret input only and must not persist in the
  image, trust store, environment, or application configuration.
- Keep Docling, embeddings, reranking, local retrieval, Qdrant Local, and
  accepted fail-closed startup behavior.

## Excluded work

No production Python architecture changes, new embedding/reranker backend,
model selection changes, OCR/ONNX/OpenVINO campaign, CUDA release image, Cloud
Run, Artifact Registry, Secret Manager, Qdrant server, multi-worker/replica
topology, or generator-in-container work. Slice 18 remains unopened and
unauthorized.

Do not manually delete CUDA packages after installation. The CPU dependency
graph itself must exclude `nvidia-*` distributions. Do not add an unpinned
requirements file or resolve arbitrary latest dependencies in Docker.

## Measurement and acceptance

Record three image sizes on the same Docker host using `docker image inspect
.Size`:

- **A:** current canonical image;
- **B:** CPU-only production dependency graph with the existing Docker
  structure;
- **C:** final CPU dependency graph with builder/runtime separation.

Report exact bytes and human-readable sizes, absolute and percentage reductions
for A→B, B→C, and A→C, image IDs/digests, and significant remaining size
contributors. Historical ~10.3 GB values are context only unless measured with
the same metric and conditions.

Acceptance requires explicit locked CPU dependencies, no NVIDIA/CUDA Python
runtime distributions, materially smaller image, unchanged AUTO resolver
selecting `cpu_onnx_fp32_v1`, successful production CPU embedding and reranker
smokes, preserved container invariants and UI projection, no private/model/
secret content, and passing required regression lanes. No arbitrary numerical
image-size target is introduced.

## Current qualification evidence

REL-01B and REL-01C implementation results and their evidence limits are
recorded in [the REL-01 qualification report](evidence/rel01/QUALIFICATION.md).
The report keeps measured image-size improvements separate from runtime checks
that have not been performed.

## Issue #1

CPU/default release-image optimization is the current REL-01 objective. A
separate CUDA release artifact is deferred and is not required before Slice 18.
Issue #1 remains open because its existing wording covers both topics; do not
close it automatically.
