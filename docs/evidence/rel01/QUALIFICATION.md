# REL-01B/C — CPU Release Packaging Qualification

**Status:** Implementation and packaging checks complete; independent review
pending. Runtime embedding/reranking qualification remains open.

**Source baseline:** `3fb65e34f5b45ddf695d82bfd0d9badd34b9ee2d`

**Implementation branch:** `feature/rel-01-cpu-release-packaging`

**REL-01B commit:** `b48f85ed659f47ace5e74c60cabb43d6e96d2225`

**Measured:** 2026-11-09 on the same Docker Desktop / WSL2 host as
[REL-01A](BASELINE.md), using `docker image inspect .Size`.

## A/B/C image measurements

| Stage | Tag | Image ID | Size (bytes) | Human-readable |
| --- | --- | --- | ---: | ---: |
| A — original packaging | `offline-rag:rel01-baseline` | `sha256:8dd5b8d21621eee44902d5373064224be6503ff3b563165b70e01ed02f49e43d` | 10,436,722,883 | 9.72 GiB / 10.44 GB |
| B — CPU dependencies, single-stage Python packaging | `offline-rag:rel01-cpu-deps` | `sha256:6bc044c24f6b3888e04b31611be1fd6b4da35cab0a730bdf11bbc02e0fc5deee` | 2,356,896,193 | 2.20 GiB / 2.36 GB |
| C — CPU dependencies, Python builder/runtime | `offline-rag:rel01-final` | `sha256:49ad624da8dba70e66a5c4f0c6c691ae9f39057ab3ba71c2b69c01ec323a2ff2` | 2,346,522,455 | 2.18 GiB / 2.35 GB |

| Comparison | Reduction (bytes) | Reduction |
| --- | ---: | ---: |
| A → B | 8,079,826,690 | 77.42% |
| B → C | 10,373,738 | 0.44% |
| A → C | 8,090,200,428 | 77.52% |

The CPU dependency selection accounts for nearly all the size reduction.
The multi-stage Python packaging removes builder-only tooling and packages
from the final image; it yields a smaller additional reduction. The final
image remains dominated by the installed production Python environment.

## Dependency and runtime checks

The `cpu-release` extra resolves Torch `2.14.0+cpu` and TorchVision
`0.29.0+cpu` from the explicit PyTorch CPU index. The normal developer
resolution remains CUDA-capable through the default PyPI source; `cpu-release`
and `cuda-dev` are mutually exclusive. The lock was updated without broad
framework upgrades, and `uv lock --check` passed.

The final image was run as UID/GID `10001:10001`. A runtime check imported and
reported:

| Package/check | Result |
| --- | --- |
| Torch | `2.14.0+cpu`; CPU tensor arithmetic passed |
| `torch.version.cuda` | `None` |
| `torch.cuda.is_available()` | `False` |
| Installed `nvidia-*` distributions | 0 |
| ONNX Runtime | `1.31.0`, import passed |
| Sentence Transformers | `5.7.0`, import passed |
| Transformers | `4.57.6`, import passed |
| Docling | `2.126.0`, import passed |
| `uv` in final image | Absent |
| Application source, config and built UI | Present |

The container permission check confirmed `/data` writable and a supplied
read-only `/models` mount readable but not writable. The runtime image
contains the application virtual environment, application source/config,
certificates and UI output. Its history shows no copied uv binary or Python
builder installation layer. The existing UI builder remains in use.

In the temporary CPU dependency environment, the required backend regression
population completed with **209 passed, 0 skipped, 1 deprecation warning**.
The sandbox invocation reproduced the previously recorded TestClient
cross-thread wake-socket `EPERM`; the same suite was then run outside that
sandbox and completed successfully. The focused AUTO resolver matrix and
AUTO-without-CUDA runtime startup regressions also passed using fake artifacts
and no inference.

The Dockerfile passed `docker build --check`. Both B and C image builds
completed. The C image build installed the locked CPU graph and copied the
resulting virtual environment into the clean runtime stage.

## Qualification limits

No model weights were downloaded or invoked. No live API health/readiness
check, production CPU embedding, reranker operation, or browser/API UI smoke
was performed. Imports and tensor arithmetic establish that the packaged
libraries load and that Torch executes CPU operations; they do not establish
that a provisioned local model embeds or reranks correctly in this image.
Those checks remain open for the next authorized qualification step.

The image was not pushed to a registry. No production source under
`src/offline_rag/` was changed. No release promotion was performed.
