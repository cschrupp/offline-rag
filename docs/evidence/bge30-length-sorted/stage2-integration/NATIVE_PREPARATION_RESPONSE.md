# Codex Response — Native Stage 2 Preparation

**Preparation code candidate:** `69c46fb0796eea4287b8aec6111077f08c4ec38f`  
**Accepted preparation base:** `819aad83cfc6621d5208ac5de51b2077ec416e24`  
**Branch:** `prep/stage2-docker-transport`

## Completed

Native execution mode is wired into the already-qualified Stage 2 driver. The default synthetic rehearsal path remains synthetic; no accepted rehearsal was repeated.

The native path uses the accepted integrated application source `1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e`, the pinned diagnostic image, production CPU embedding and BGE reranking resources, the deterministic provider fixture, resolved Recipes/Rich workspace bindings, and the existing workspace conversation route. It preserves the frozen `cpu_onnx_fp32_v1` embedding profile, BGE-30 FP32 scoring, the consecutive versus `length_sorted_8` comparison, the 36-submission driver budget, 180-second request deadline, and 30-second application shutdown grace.

The native preflight binds the exact config, manifest, workload and Stage 1 binding hashes; model artifacts; published snapshot/workspace/source identities; local strict-offline settings; and host/container storage conditions. It checks publication scientific-setting hashes against the manifest before producing native bindings. The parity validator fails closed on incomplete arms, non-finite or out-of-tolerance logits, changed candidate-score associations, ranking/tie-break changes, anchor/evidence changes, packed-context changes, or citation changes.

The host-control path captures the original container identity and mounts, restores that same container, checks health and publication metadata, confirms scratch Qdrant is unowned, and retains the existing independent watchdog. Native diagnostic containers use network isolation, a read-only model mount, bounded CPU/memory, and the original 30-second shutdown grace. Synthetic-mode lifecycle acceleration remains unchanged.

## Validation performed

- Focused native contract, parity, native driver, and Docker adapter suites: **26 passed**.
- Ruff lint: **passed**.
- Ruff formatting check on changed Python files: **passed**.
- Python compilation of changed/new execution modules: **passed**.
- `bash -n` on `preflight_host.sh`: **passed**.
- `git diff --check`: **passed**.
- Pinned diagnostic image identity is present in the local Docker image store: **verified by image ID/digest**.
- Native model load, real inference, host preflight, maintenance, and campaign: **not run**.

## Host availability and boundary

A read-only GCP lookup on 2026-11-23 returned `seneca-review TERMINATED` in `us-central1-a`. No SSH, VM startup, container operation, data copy, model load, or Stage 2 submission was performed. Thus the host-specific identity, storage ownership, STOP-window, memory/disk, publication, and restoration checks remain unavailable.

The exact host command sequence is in [`NATIVE_EXECUTION_PREPARATION.md`](NATIVE_EXECUTION_PREPARATION.md). It begins with read-only instance-state verification, requires a running host and at least 4,800 seconds before automatic STOP, then performs identity and metadata checks before maintenance. Its later steps are explicitly marked as requiring separate native-campaign authority.

## Remaining authority boundary

This is native-mode preparation only. It does not authorize starting the VM, maintenance, copying production data, native Stage 2 submissions, deployment, merge, production activation, batching-default changes, or promotion. The next boundary is verification of the intended running host and a separate authorization for the native campaign.
