# REL-01B/C — CPU Release Packaging Qualification

**Qualification handoff status at record creation:** REL-01D qualification
complete; ready for independent final review.
**Current tranche disposition:** REL-01 COMPLETE / INDEPENDENTLY ACCEPTED /
HUMAN ACCEPTED / PROMOTED with evidence closeout at `0a1b5a45`.

**Source baseline:** `3fb65e34f5b45ddf695d82bfd0d9badd34b9ee2d`

**Implementation branch:** `feature/rel-01-cpu-release-packaging`

**REL-01B commit:** `b48f85ed659f47ace5e74c60cabb43d6e96d2225`

**IR-001 corrective candidate:** `f639493cc1b1647096440fbf24167df929a52bf7`

**Measured:** 2026-11-09 on the same Docker Desktop / WSL2 host as
[REL-01A](BASELINE.md), using `docker image inspect .Size`.

## A/B/C image measurements

| Stage | Tag | Image ID | Size (bytes) | Human-readable |
| --- | --- | --- | ---: | ---: |
| A — original packaging | `offline-rag:rel01-baseline` | `sha256:8dd5b8d21621eee44902d5373064224be6503ff3b563165b70e01ed02f49e43d` | 10,436,722,883 | 9.72 GiB / 10.44 GB |
| B — CPU dependencies, single-stage Python packaging | `offline-rag:rel01-cpu-deps` | `sha256:6bc044c24f6b3888e04b31611be1fd6b4da35cab0a730bdf11bbc02e0fc5deee` | 2,356,896,193 | 2.20 GiB / 2.36 GB |
| C — CPU dependencies, non-editable install, Python builder/runtime | `offline-rag:rel01-final` | `sha256:a2f0a5a5262e173c2b1efc39f83bdd972e26c8928cf09c4b3950d89935d534fb` | 2,346,582,188 | 2.18 GiB / 2.35 GB |

| Comparison | Reduction (bytes) | Reduction |
| --- | ---: | ---: |
| A → B | 8,079,826,690 | 77.42% |
| B → C | 10,314,005 | 0.44% |
| A → C | 8,090,140,695 | 77.52% |

The A→B difference measures both selecting the CPU-only release dependency
graph and moving from the baseline's unconstrained `pip install .` resolution
to the committed lock. It must not be attributed entirely to CUDA removal.
The baseline's NVIDIA, Triton, and CUDA Torch directories establish that
removing the CUDA stack is a major contributor, but no locked-CUDA control
image was built to isolate its exact contribution. The multi-stage Python
packaging removes builder-only tooling and packages from the final image; it
yields a smaller additional reduction. The final image remains dominated by
the installed production Python environment.

## Dependency and runtime checks

The `cpu-release` extra resolves Torch `2.14.0+cpu` and TorchVision
`0.29.0+cpu` from the explicit PyTorch CPU index. The normal developer
resolution remains CUDA-capable through the default PyPI source; `cpu-release`
and `cuda-dev` are mutually exclusive. The lock was updated without broad
framework upgrades, and `uv lock --check` passed. The Python builder runs
`uv sync --locked --no-dev --extra cpu-release --no-editable --no-cache`.

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
| Installed `offline_rag` package | `offline_rag.__file__` is under `/app/.venv/lib/python3.14/site-packages`; `/app/src` absent |
| Installed `offline-rag` console command | `offline-rag --help` exits successfully |

The final container runs as UID/GID `10001:10001`, starts with
`python -m offline_rag.api.server`, and has no `/app/src`. Import resolution
uses the installed wheel in the virtual environment, with no `PYTHONPATH`
workaround. The installed CLI entrypoint also runs. A read-only `/models`
mount and writable `/data` were verified.

The original host `models/` bind could not be read by UID 10001 because
several provisioned files (including embedding manifests and ONNX artifacts)
are mode `0600`, owned by host UID 1001. Those original permissions were not
changed. For API/resolver checks, the provisioned tree was copied to a
temporary Docker volume, assigned to UID 10001, and mounted read-only. The
API reached ready with a nonfunctional local placeholder generator profile;
no generator request was made. The original host-bind permission mismatch
remains an operational deployment limitation.

Actual container API checks returned HTTP 200 for `/health`, `/health/live`,
`/health/ready`, `/v1/settings/compute`, `/v1/capabilities`, and `/` (packaged
UI HTML). The compute API reported `configured_device=auto`, active/resolved
device `cpu`, profile `cpu_onnx_fp32_v1`, representation `onnx_fp32_v1`,
backend `sentence_transformers_onnx`, provider `CPUExecutionProvider`,
`torch_cuda_build=null`, and CUDA unavailable. At that time the embedding
runtime state was `UNLOADED`; this is resolver/API evidence, not an embedding
execution result. The focused Compute UI test file passed 10/10 tests,
including active-CPU and CPU-only/GPU-unavailable guidance. Command:
`cd ui && npm test -- src/test/slice16l_compute_settings_ux.test.tsx`.
The built UI was served by the live container; no interactive browser session
was performed.

The image contains the application virtual environment, config, certificates,
and UI output. Its history shows no copied uv binary, Python builder install
layer, `/app/src`, `.env`, `.git`, or `node_modules`, and no provisioned
embedding/reranker model tree. One qualification boundary is not met
literally: the locked `rapidocr` dependency bundles about 31 MB of OCR ONNX
models, and the `onnx` dependency includes about 13 MB of ONNX test fixtures.
These are dependency contents present in the baseline dependency family; they
were not removed because doing so could break document OCR/runtime behavior.
The existing UI builder remains in use.

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

No model weights were downloaded. The live API and Compute API were exercised,
but no interactive browser session was performed. The focused Compute UI test
passed 10/10 tests, and the packaged UI returned HTTP 200. The two authorized
local model smokes are recorded below. No external inference occurred.

The temporary model-volume owner remapping allowed the container to read the
provisioned artifacts while preserving the original `models/` tree. The
original tree's mode-0600 files still cannot be read by UID 10001 through a
direct bind mount. This remains an operational deployment note.

The image was not pushed to a registry. No production source under
`src/offline_rag/` was changed. No release promotion was performed.

## REL-01D — Local CPU model smokes

Exactly one embedding and one reranker inference were run in separate
containers from the final candidate image. Docker network mode was `none`;
`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and strict-offline application
configuration were active. The existing provisioned model tree was copied
into a temporary Docker volume, assigned to UID 10001 only in that copy, and
mounted read-only. The original host `models/` tree was not modified. The
temporary volumes were removed after the smokes.

### Embedding

One synthetic query was embedded through `ApplicationRuntime` and the
production `QualifiedEmbeddingRuntime`.

| Check | Result |
| --- | --- |
| Configured device | `auto` |
| Resolved device | `cpu` |
| Profile / representation | `cpu_onnx_fp32_v1` / `onnx_fp32_v1` |
| Backend / provider | `sentence_transformers_onnx` / `CPUExecutionProvider` |
| Precision | `fp32` |
| Runtime after call | `READY` |
| Vector | 1,024 dimensions; all values finite |
| CUDA build / availability | `None` / `False` |
| External calls or downloads | None; container network disabled |

Transformers emitted a tokenizer warning that the provisioned tokenizer has an
incorrect regex pattern and may tokenize incorrectly, with a suggestion to set
`fix_mistral_regex=True`. The smoke completed with a finite 1,024-dimensional
vector and the selected CPU backend. No tokenizer or model configuration was
changed under REL-01; the warning is retained for independent review.

### Reranker

One synthetic query/passage pair was scored by the production
`CrossEncoderReranker` using the provisioned BGE model.

| Check | Result |
| --- | --- |
| Resolved device | `cpu` |
| Scores returned | 1 |
| Score | Finite raw logit (`raw-logit-v1`) |
| Local-files-only | `True` |
| External calls or downloads | None; container network disabled |

No scientific parity test, benchmark, corpus operation, retry, or additional
model execution was performed. Both authorized local operations passed. The
qualification is functional only.
