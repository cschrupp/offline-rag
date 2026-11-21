# Execution and provenance

- Accepted research parent: `9452907113a857cee8c3de3328fad810ec366ab7`.
- Executed harness and preregistration: `b930e513d9a5353447843babc3c92f305e0e38e0`.
- Deployed source: `9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`.
- Deployed image: `sha256:3bc83208a7526a49abed1b9bd9586b5ae4fd041771732e03030c3ac20419e692`.
- Container ID: `e006597fd6e4e40939e49c1dd73da7c6d85f33d87d44929c15dc5f0f38bb7cac`.
- Incident snapshot: `snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196`.
- Deployed science settings SHA-256: `5dce337dc1875b2aa615d62ee771a0ae384559c2da14be384e067ded035f5417`.
- BGE revision: `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`.
- Intel Xeon 2.20 GHz, two cores with two hardware threads each, affinity
  and effective cpuset four CPUs, no tighter diagnostic cgroup CPU quota.
  Preflight: 15,500,176 KiB available RAM, 21,129,344 KiB disk free, 98,268
  KiB live data. Torch threads 2/2, frozen embedding ORT threads 8/1.
- Prior startup had less than 30 minutes before automatic STOP. No
  maintenance or inference ran on that window. After the operator restart,
  the first preflight found normal startup in progress. It ran no inference.
  Readiness was then polled without workload submissions and full preflight
  reran after both health endpoints answered. Verified STOP deadline was
  20:41:11 UTC with the existing 7,200-second policy.
- The verified scorer file was mounted into the isolated container alone.
  The regular deployment image and code remained in place. The harness
  copied data only after a graceful stop, opened only the isolated Qdrant
  store, disabled network access, and mounted provisioned models read-only.
- Each record ties 30 candidate IDs to a complete score permutation. Active
  input IDs, masks and positions were fingerprinted per candidate. Padding
  is right-sided and differs intentionally by arm. Evidence-unit and
  packed-context comparisons used exact hashes. The log includes per-pair
  signed deltas in original fused order and opaque identity fields.
- Scope checks, checkpoint file hashes, and the published-workspace digest
  are verified by the probe. Harness Python compilation and shell syntax
  checks passed. The existing research, ranking, and retrieval evaluation
  suite passed 42 tests.

## Restoration

The isolated process exited zero after eight assembler calls and four
passing parity comparisons. The original container was restarted and both
health endpoints returned HTTP 200. Its image, mounts and restart policy
matched preflight. The post-restart probe matched the full preflight
publication state, workspace revision, snapshot and source inventory.
The isolated copy and diagnostic staging files were removed after
verification. The automatic STOP policy remained in force.
