# REL-01A — Current Docker Baseline

**Baseline source:** `3fb65e34f5b45ddf695d82bfd0d9badd34b9ee2d`

**Documentation opening commit:** `36cc0a63a767000e96080ef03de6f686c680279f`

**Measured:** 2026-11-09

**Image tag:** `offline-rag:rel01-baseline`

## Build conditions

The source was materialized from the exact baseline commit with `git archive`
into `/tmp/rel01-baseline-src`. The unchanged baseline Dockerfile was built
from that source tree:

```sh
docker build -f deploy/Dockerfile -t offline-rag:rel01-baseline .
```

Docker reported client `29.1.3`, server `29.9.2`, Buildx `v0.38.1`, and the
image platform is `linux/amd64`. The build used the Docker Desktop engine on
the WSL2 host. The UI stage completed `npm ci` and `npm run build`.

The baseline Dockerfile runs `pip install .` without a committed Python lock
file. Therefore this measurement includes the versions PyPI resolved on the
measurement date; it is a measurement of the current packaging process, not a
reproducible dependency lock.

## Image identity and size

| Measurement | Value |
| --- | --- |
| Image ID | `sha256:8dd5b8d21621eee44902d5373064224be6503ff3b563165b70e01ed02f49e43d` |
| Local manifest-list digest | `sha256:8dd5b8d21621eee44902d5373064224be6503ff3b563165b70e01ed02f49e43d` |
| `docker image inspect .Size` | **10,436,722,883 bytes** (about 9.72 GiB / 10.44 GB) |
| Largest history layer | **6.82 GB**, dependency installation layer |
| Dependency installation elapsed time | 4,842.9 seconds, as reported by BuildKit step `#23` |
| Image export elapsed time | 479.0 seconds, as reported by BuildKit step `#24` |

The baseline is intentionally measured using Docker's image `.Size` value.
Later REL-01 image comparisons must use this same host and metric.

## Runtime package inspection

The finished image reports Python `3.14.10`, Torch `2.15.0+cu132` with CUDA
build `13.2`, ONNX Runtime `1.31.1`, Sentence Transformers `5.7.0`,
Transformers `4.57.6`, and Docling `2.149.0`. `torch.cuda.is_available()` was
`False` in the Docker Desktop/WSL2 environment used for inspection; this is
not evidence of resolver selection or CPU embedding qualification.

The image contains these NVIDIA distributions:

```text
nvidia-cublas 13.4.1.3
nvidia-cuda-cccl 13.3.5.0.6
nvidia-cuda-cupti 13.2.86
nvidia-cuda-nvrtc 13.2.86
nvidia-cuda-runtime 13.2.86
nvidia-cudnn-cu13 9.26.0.51
nvidia-cufft 12.2.0.57
nvidia-cufile 1.17.1.22
nvidia-cusolver 12.2.0.11
nvidia-cusparse 12.7.10.12
nvidia-cusparselt-cu13 0.8.1
nvidia-nccl-cu13 2.30.7
nvidia-nvjitlink 13.5.37
nvidia-nvshmem-cu13 3.7.2
nvidia-nvtx 13.2.86
```

Largest inspected Python package directories, from `du -x -k` inside the
container:

| Directory | KiB |
| --- | ---: |
| `site-packages/nvidia` | 3,127,692 |
| `site-packages/torch` | 1,218,476 |
| `site-packages/triton` | 1,022,632 |
| `site-packages/scipy` | 111,804 |
| `site-packages/pandas` | 84,140 |
| `site-packages/cv2` | 73,076 |
| `site-packages/onnxruntime` | 68,968 |
| `site-packages/sklearn` | 49,636 |

These directory sizes are filesystem usage, not additive image-layer sizes.
The `docker history` dependency-installation layer is 6.82 GB, showing that
the installed Python runtime is the dominant layer.

## Scope and limitations

- The UI build completed. npm reported 13 existing advisories (10 moderate,
  3 high), and Vite reported a chunk over 500 kB.
- No model was downloaded or invoked. No API health, resolver-selection,
  embedding, reranker, filesystem, or production behavior qualification was
  performed in this baseline stage.
- The installed CUDA build and NVIDIA distributions establish the packaging
  baseline; they do not imply that CUDA is usable in the tested host.
- No source, dependency metadata, lockfile, or Dockerfile was changed to make
  this measurement.
