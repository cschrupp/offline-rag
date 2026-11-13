# Slice 18C-A — Dependency Feasibility Record

**Authority:** `S18C-UNIVERSAL-DISTRIBUTION-IMPL-001`  
**Base/source under test:** `e98fc147fe754936152024aa6630a17c43aa15da`  
**Platform:** Linux x86-64 / Python 3.14.5  
**Lock:** repository `uv.lock`, unchanged

Two fresh virtual environments were resolved and installed using the locked
project metadata:

```text
uv sync --locked --no-dev --extra cpu-release --no-editable
uv sync --locked --no-dev --extra cuda-dev --no-editable
```

| Measurement | `cpu-release` | `cuda-dev` |
| --- | ---: | ---: |
| Environment size (`du -sb`) | 1,604,272,235 bytes | 6,380,938,425 bytes |
| Installed Torch | `2.14.0+cpu` | `2.14.0+cu130` |
| `torch.version.cuda` | `None` | `13.0` |
| `torch.cuda.is_available()` | `False` | `True` |
| Installed `nvidia-*` distributions | 0 | 15 |

The 15 CUDA-profile distributions were:

```text
nvidia-curand
nvidia-cudnn-cu13
nvidia-nvshmem-cu13
nvidia-cublas
nvidia-cuda-nvrtc
nvidia-cuda-cupti
nvidia-cusparse
nvidia-nccl-cu13
nvidia-nvjitlink
nvidia-cusolver
nvidia-cufile
nvidia-cufft
nvidia-nvtx
nvidia-cuda-runtime
nvidia-cusparselt-cu13
```

Both commands resolved 157 packages. The CPU environment installed 128
packages; the CUDA environment installed 147. No lockfile, dependency version,
or project dependency declaration was changed for this check.

The host `nvidia-smi` probe returned `probe_failed`, whereas the isolated CUDA
PyTorch runtime reported availability. The former is only the non-mutating
workstation offer signal; it is not the Seneca backend selector. The existing
`probe_torch_cuda()` and qualified resolver remain the runtime authority.

This is dependency feasibility evidence only. It is not a CUDA embedding,
reranker, workstation transition, container build, throughput, or scientific
qualification result. Environment sizes are descriptive and have no arbitrary
acceptance threshold.
