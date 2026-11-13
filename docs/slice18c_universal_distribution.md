# Slice 18C — Universal Workstation Distribution

**Authority:** `S18C-UNIVERSAL-DISTRIBUTION-IMPL-001`  
**Canonical base:** `e98fc147fe754936152024aa6630a17c43aa15da`  
**Implementation branch:** `feature/slice18c-universal-distribution`  
**Current state:** AUTHORIZED / IMPLEMENTATION IN PROGRESS

Slice 18C is bounded release engineering. It delivers one CPU-first universal
workstation package with explicit, transactional CUDA enablement, and two
immutable container dependency variants from the same Seneca source. It does
not change the qualified CPU/CUDA execution profiles, scientific behavior,
retrieval, generation, model/index identities, or user data.

## Preserved runtime contract

`embedding.device = auto | cpu | cuda` and the existing profile resolver remain
authoritative:

```text
usable CUDA + AUTO  → cuda_fp16_v1 → torch_st_v1 → PyTorch / CUDA FP16
unavailable + AUTO  → cpu_onnx_fp32_v1 → onnx_fp32_v1 → ONNX Runtime CPU
```

The workstation archive remains a single CPU-first package. Its initial
environment uses the locked `cpu-release` extra. Only an explicit user action
may construct a separate `cuda-dev` candidate environment. The active release
is never modified in place; activation happens after validation through the
existing atomic release-link pattern, with CPU rollback on failure.

The container build uses one Dockerfile and one runtime layout. The default
profile is `cpu-release`; an explicit build argument selects `cuda-dev`. No
drivers, system CUDA toolkit, or post-resolution package mutation are added.

## 18C-A — Locked dependency feasibility

Both checks used fresh disposable Python 3.14 environments under `/tmp`, with
the accepted `uv.lock` and project metadata unchanged. No second lockfile or
package-version change was introduced.

| Profile | Installed environment bytes | Torch | CUDA build / availability | NVIDIA distributions |
| --- | ---: | --- | --- | ---: |
| `cpu-release` | 1,604,272,235 | `2.14.0+cpu` | `None` / `False` | 0 |
| `cuda-dev` | 6,380,938,425 | `2.14.0+cu130` | `13.0` / `True` | 15 |

The CPU environment therefore remains CPU-only. The CUDA environment installs
the existing locked CUDA-capable graph. Sizes are descriptive measurements,
not threshold-based pass criteria. Full package names and host limitations are
recorded in [`docs/evidence/slice18c_universal_distribution/FEASIBILITY.md`](evidence/slice18c_universal_distribution/FEASIBILITY.md).

On this execution host, `nvidia-smi` returned a probe failure, while CUDA
PyTorch in the isolated `cuda-dev` environment reported CUDA available. These
are recorded as distinct observations: the host offer probe does not select a
profile, and the actual candidate environment must still pass Seneca's existing
PyTorch profile resolver. No embedding, reranking, corpus, or benchmark call
has been made as part of the dependency feasibility check.

## Implementation and qualification plan

1. Preserve the verified archive as a source-bound reconstruction seed without
   `/data`, `/models`, credentials, or user content.
2. Keep workstation installation CPU-first and offer CUDA only in an
   interactive install when a host capability probe observes NVIDIA support.
3. Implement `seneca enable-cuda` and `seneca disable-cuda` with explicit
   consent, immutable releases, existing model provisioning, runtime
   validation, atomic activation, service/readiness checks, and rollback.
4. Build the same source as `seneca:<version>-cpu` and
   `seneca:<version>-cuda`; compare dependency inventories and runtime
   invariants without publishing either image.
5. Run focused workstation, package, profile, provisioning, and container
   checks. Use synthetic inputs only for any local inference smoke.
6. Report unavailable host/service/image cells as unavailable; do not infer GPU
   qualification from package installation.

## Environment qualification limits

- The host `nvidia-smi` capability probe currently fails; no automatic CUDA
  offer is justified from that probe result.
- Docker CLI exists, but this environment cannot access `/var/run/docker.sock`.
  Local CPU/CUDA image builds and image runtime checks are currently
  unavailable; no registry or cloud action is authorized.
- Linux GPU PyTorch capability is observed in the isolated `cuda-dev` venv, but
  the workstation CUDA transition and actual embedding/reranker execution have
  not yet been qualified.

These are execution-environment limits, not changes to the distribution
contract. The final evidence must preserve each cell's actual disposition.

## Explicit exclusions

Slice 18C does not authorize `main` promotion, registry pushes, GitHub Release
publication, Google Cloud deployment, native Windows packaging, M7 closeout,
or implementation of Slices 18D–18F. It does not modify the accepted REL-01
performance evidence or reopen the deferred 18B real-host lifecycle checks.
