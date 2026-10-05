# Container image size optimization (deferred)

**Status:** deferred technical debt — **not** a Slice 15 / 15H blocker
**Tracking:** [#1 Optimize Docker image size with CPU/CUDA variants and multi-stage builds](https://github.com/cschrupp/offline-rag/issues/1)
**Accepted 15G reference implementation:** `140350b8cc6eec6a2491c0a1696042e65b2d2b7e`
**Accepted Slice 15 closeout (15H):** `1c1d94eada502523d44ec8e9c9a6e23b1f863d49`
**Reference local test tags:** `offline-rag:15g-test`, `offline-rag:15h-test` (~10.3GB)

## Current state

The accepted Slice **15G** application image is functionally correct:

- Python 3.14 runtime
- non-root `10001:10001`
- `/data` writable root + `/models` mountpoint
- single-process / single-worker ASGI server
- external generator boundary
- no bundled model weights or private `/data` content in the image

Observed local size for `offline-rag:15g-test` is approximately **10.3 GB**
(~9.6 GiB compressed/content-reported depending on Docker tooling).

## Likely size source

Image size appears dominated by the Python ML dependency graph, especially:

- `torch`
- NVIDIA/CUDA runtime wheels (`nvidia-cudnn-*`, `nvidia-cublas`, etc.)
- related packages pulled through `sentence-transformers` / `transformers`

It is **not** dominated by bundled retrieval/generator weights or corpus data.
A diagnostic inspection of the accepted image found empty `/models` and `/data`
trees inside the image itself.

## Recommended future directions

1. **Multi-stage Docker builds**
   Builder stage for install/build tooling; copy only the runtime environment into
   a clean runtime stage. Improves hygiene; size win alone may be modest if CUDA
   libraries remain runtime dependencies.

2. **CPU release image (preferred default)**
   Candidate tag: `offline-rag:<version>-cpu`
   Use `python:3.14-slim` with explicitly CPU-only PyTorch/runtime dependencies
   where practical. Likely the best default portfolio/release image because the
   generator remains external and retrieval does not require GPU execution.

3. **CUDA release image (optional)**
   Candidate tag: `offline-rag:<version>-cuda`
   Prefer a matching NVIDIA CUDA runtime base image rather than indirectly
   installing CUDA into `python:3.14-slim`. Avoid duplicating CUDA libraries
   between the NVIDIA base image and PyTorch `nvidia-*` wheels.

## Constraints that must remain intact

- Python `>=3.14,<3.15`
- UID/GID `10001:10001`
- `/data:rw`, `/models:ro`
- one process / one ASGI worker
- external generator (no Ollama-in-image, no generator weights)
- Qdrant client with Local-mode persistence (no Qdrant server service)
- model weights and private `/data` never enter the Docker build context

## Non-goals

- Do not reopen accepted Slice 15G semantics.
- Do not treat this optimization as a prerequisite for Slice 15 integration
  testing unless a concrete blocker is discovered.
- Do not mark this work completed until a reviewed packaging change lands.
