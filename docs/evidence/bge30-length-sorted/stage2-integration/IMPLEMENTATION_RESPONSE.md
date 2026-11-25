# Stage 2 integration preparation

**Integrated diagnostic candidate for review. Stage 2 execution pending.**

Source commit `1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e` on
`integration/bge30-cpu-stage2` contains the approved initializer base
`f2dd2bda1890fb86ddb055ef101c2e5e098eba43`, then merge commits for PR #5
`239ecd1ef30a200e023d87284d807bb3c444abba`, PR #3
`6900aeb33f063492ab6709a73707ed1e65e6ab8d` and PR #4
`fee6515102ac2f8d9944e83d8b3d705dba9e1625`. All merges were conflict-free.
All 38 changed paths match the attributed branch's exact Git blob.
[Parent provenance](LINEAGE.txt) · [Path/blob attribution](ATTRIBUTION.tsv) ·
[Full integration diff](https://github.com/cschrupp/offline-rag/compare/f2dd2bda1890fb86ddb055ef101c2e5e098eba43...1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e)

[Draft integration PR #6](https://github.com/cschrupp/offline-rag/pull/6)
tracks combined CI. PRs #3, #4 and #5 remain separately draft.

## Qualification evidence

The combined source passed the hosted backend and frontend jobs on
[run 45079805995](https://github.com/cschrupp/offline-rag/actions/runs/45079805995)
at the exact integration commit. Local frontend lint, typecheck, 478 tests
in 52 files, and production build passed. The build reported its existing
chunk-size advisory.

The following local backend command gave 163 passes and eight failures.
The eight are the same exact-parent 15F failures recorded by PR #5.
The fixtures expect older query method signatures. They remain red.
No tests or gates were waived and no legacy fixture was edited.
A separate fixture correction would still need independent approval.

```bash
PYTHONPATH=src python -m pytest -q --tb=short \
  tests/unit/test_{cross_encoder_batching,cross_encoder_initialization,hybrid_rerank,context_expansion}.py \
  tests/unit/app/test_{workspace_turn_ownership,slice16d_b3_conversation,query_failure_observability,slice15c_snapshots_leases_documents,slice15f_admission_deadlines_shutdown}.py
```

The combined loopback uses the real workspace and managed query routes,
application ownership, and the actual cross-encoder batching code with
a deterministic FP32 forward/tokenizer fixture. Both strategies passed
the held-worker checks. An independent contender and managed query got
the shared capacity rejection, the abandoned worker retained its slot,
the cooperative deadline returned 504 after held work returned, and
resources survived transport grace. The ownership tests check preflight
precedence, trace uniqueness and terminalization. The batching tests
check active token and score association, lock behavior, exact ranks
and packed evidence, and snapshot fingerprint compatibility. This does
not establish native HTTP throughput, native concurrent-model performance
or production quality. [Loopback output](LOOPBACK.txt)

## Diagnostic image

The canonical CPU image attempt used the exact commit archive and
`deploy/Dockerfile` with `SENECA_DEPENDENCY_PROFILE=cpu-release` and
`SENECA_SOURCE_SHA=1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e`.
It timed out fetching the locked `charset-normalizer==3.5.1` wheel.
No dependency pin changed.

The built diagnostic image is the **single local experimental derivative**
at `sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04`.
It reuses the verified CPU runtime and existing UI from the pinned local
9c92e706 image. The integrated frontend change is assertion-only and
does not change served UI. The derivative copies the entire tracked
integrated Python tree and fixture, and imports them through the
diagnostic-only source path. The original installed package and runtime
layers remain intact. It contains no workspace data or model weights.
[Build script](build_diagnostic.sh) · [Image and version attestation](IMAGE_RUNTIME.json)

With that exact local base loaded, run:

```bash
bash docs/evidence/bge30-length-sorted/stage2-integration/build_diagnostic.sh
```

Rebuilding reproduces the source/runtime composition. Build metadata can
change the digest. Preserve and distribute the existing exact image by
approved offline image export/import, verifying the digest after import
before using either arm. No artifact was sent to the VM or a registry.

The network-disabled image smoke loaded the application and fixture
from the diagnostic paths. It verified all 402 packaged source files
against Git, checked the fixture hash and first-handle response, and
confirmed CPU-only Torch, identical reranker scientific hash in both
strategies, default consecutive/opt-in sorted-eight, depth 30,
query capacity one, 180 s deadline and 30 s application grace.
Python, Torch, Transformers, tokenizers, tiktoken and ONNX Runtime
versions are in the attestation.

## Execution authorization checkpoint

[Workload and artifact manifest](workloads.json) ·
[36-submission protocol and abort/restoration procedure](PROTOCOL.md) ·
[Full authorization](AUTHORIZATION.md)

Before separate execution authority, accept this exact lineage and
diagnostic image, review and validate a bounded lifecycle driver,
approve the fixture and explicit client watchdog, and verify manifest
artifacts and exact workspace/source bindings on the isolated host.
Resolve the local 15F debt disposition without counting those failures
as passes. Require the same artifact and workload order in both arms,
with batching as the only treatment difference. Verify the maintenance
window, resource watchdog, isolation and restoration reserve before
stopping production. Stage 1 evidence remains historical and unchanged.
No PR merge, deployment, VM maintenance or Stage 2 submissions occurred.

The combined-source local scorer also ran the pinned native FP32 BGE
checkpoint with the existing offline synthetic benchmark. Both workloads
passed the preregistered logit tolerance and exact ranks. Maximum
absolute delta was 1.9073486e-06. This was a development Python process,
separate from the diagnostic image and HTTP fixture. The timings are
exploratory and were collected while other local checks ran.
[Native scorer observations](NATIVE_LOCAL.jsonl)
