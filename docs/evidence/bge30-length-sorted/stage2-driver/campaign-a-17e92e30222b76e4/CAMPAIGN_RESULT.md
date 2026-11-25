# Stage 2 Campaign A — Performance and Parity

**Disposition:** Campaign A complete. Fixed-depth parity passed for both
workloads. Campaign B lifecycle qualification remains pending.

## Execution identity

- Session: `17e92e30222b76e4`
- Driver candidate: `f2261fa82f460af60b91456a3eec1b004a2d1c96`
- Integrated application source: `1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e`
- Diagnostic image: `seneca-rich2-local:1f79eca0`, image ID and digest
  `sha256:59252d0655267001c4c9ac42e5a2045131b4086bb1ab84e10dbfd98f2e831dee`
- Original service image ID: `sha256:3bc83208a7526a49abed1b9bd9586b5ae4fd041771732e03030c3ac20419e692`
- Models, checkpoints, settings, workload bindings, 4-CPU allocation, ORT
  8/1, Torch 2/2, FP32, 180-second query deadline, 30-second shutdown grace,
  network isolation, 6-GiB container limit, and zero container swap remained
  as frozen.
- Recipes snapshot:
  `snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196`
- Rich 2 snapshot:
  `snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca`

## Execution and parity

The session submitted exactly 28 load requests: seven per workload/strategy
cell, retaining the 1/2/4 concurrency waves. All 28 attempts settled, with
zero retries. Twelve requests were accepted and completed with HTTP 200; the
other 16 were explicit capacity rejections. Each workload/strategy cell had
three completed requests. No lifecycle case ran in Campaign A.

The parity validator returned `NATIVE_FIXED_DEPTH_PARITY_PASS`:

- Recipes: 30 candidates, three completed requests per strategy, parity PASS.
- Rich 2: 10 candidates, three completed requests per strategy, parity PASS.
- Raw FP32 logits met the frozen per-pair tolerance
  `abs(delta) <= 1e-4 + 1e-5 * abs(baseline)`.
- Candidate-score associations, original candidate order, complete ranking
  and tie-break, anchors, evidence units, packed-context identity, and
  citation identity/counts matched within each workload.

The sanitized `driver-events.jsonl` preserves the 28 attempts and settlements,
server timings, batch shapes, score observations, and scientific identity
hashes. Opaque operation and trace identifiers were replaced with SHA-256
digests. `native-parity.json` is the machine-generated parity result, and
`driver-completion.json` records the successful driver exit.

Artifact checksums:

- Original VM `driver-events.jsonl` SHA-256:
  `30a8f8009ff1c8888999e78227de2b70ad67c563b6316040bbe80b084cda59e0`
- Committed sanitized `driver-events.jsonl` SHA-256:
  `55b3d8ad4651b4b9cd55027ec52d36bac086e514b235c36034f0068e694e1daf`
- `native-parity.json` SHA-256:
  `e978afacb85ce2b1150d7b86762c4bbb5b0e4e1f5718e6f70055582027ca6a79`
- `driver-completion.json` SHA-256:
  `7e29369e7a54e3b08d7e0d1328d526ea935ca727645c9e5da26ba682a85009a3`

Capacity rejections by cell:

| Workload | Strategy | Completed | Preflight capacity rejects | Query capacity rejects |
| --- | --- | ---: | ---: | ---: |
| Recipes | consecutive | 3 | 3 | 1 |
| Recipes | length-sorted-eight | 3 | 3 | 1 |
| Rich 2 | consecutive | 3 | 1 | 3 |
| Rich 2 | length-sorted-eight | 3 | 0 | 4 |

## Latency and CPU observations

The first accepted request for each strategy is reported separately as the
first-use observation. Warm medians use the remaining accepted observations
(two per Recipes cell and three per Rich 2 cell). The arms ran consecutively
(consecutive first, then length-sorted-eight); these are workload-specific
descriptive comparisons, not counterbalanced paired estimates.

| Workload | Measure | Consecutive warm median | Length-sorted-eight warm median | Change (sorted vs consecutive) |
| --- | --- | ---: | ---: | ---: |
| Recipes | Assembler wall | 61.380 s | 35.831 s | −41.6% |
| Recipes | BGE scorer wall | 59.096 s | 33.512 s | −43.3% |
| Recipes | BGE scorer CPU | 118.249 s | 63.896 s | −46.0% |
| Recipes | Worker process CPU | 123.097 s | 68.512 s | −44.3% |
| Rich 2 | Assembler wall | 27.098 s | 27.570 s | +1.7% |
| Rich 2 | BGE scorer wall | 26.589 s | 27.065 s | +1.8% |
| Rich 2 | BGE scorer CPU | 53.394 s | 52.843 s | −1.0% |
| Rich 2 | Worker process CPU | 55.463 s | 55.051 s | −0.7% |

First-use observations:

| Workload / strategy | Assembler wall | Dense stage | BGE scorer wall | BGE forward wall |
| --- | ---: | ---: | ---: | ---: |
| Recipes / consecutive | 122.324 s | 59.817 s | 61.800 s | 59.840 s |
| Recipes / length-sorted-eight | 91.091 s | 27.021 s | 63.340 s | 61.820 s |

The first-use values include first-use runtime and operating-system cache
effects; they are not a controlled estimate of model initialization cost.
Within the sorted-eight Recipes arm, dense latency fell from 27.021 seconds
on the first accepted request to 1.430 and 1.308 seconds on subsequent
accepted requests. The BGE forward workload remained the dominant warm stage.

The observed batch shapes were:

| Workload | Strategy | Batches (pairs × padded sequence width) |
| --- | --- | --- |
| Recipes, 30 candidates | consecutive | `16×368`, `14×406` |
| Recipes, 30 candidates | length-sorted-eight | `8×86`, `8×166`, `8×241`, `6×406` |
| Rich 2, 10 candidates | consecutive | `10×509` |
| Rich 2, 10 candidates | length-sorted-eight | `8×502`, `2×509` |

Sampled container memory was approximately 3.97–4.05 GiB under the 6-GiB
limit. Per-request peak process RSS observations were approximately
4.00–4.34 GiB. Spot CPU samples ranged from about 98% to 215%; these are
samples, not continuous utilization maxima. The host had 15.84 GiB available
RAM before maintenance, well above the 2-GiB floor.

## Interpretation and limits

For this Recipes workload, warm sorted-eight requests were materially faster
and used fewer scorer/worker CPU-seconds. For the naturally smaller, mostly
homogeneous Rich 2 pool, sorted-eight was about 1.7% slower in assembler wall
time. Results must therefore remain workload-specific; do not average the
Rich 2 result away or claim a universal benefit. The first arm ran before the
second, so page-cache and session-order effects limit cold-start comparisons.
Capacity-rejected requests provide no timing observations. Six completed
requests per workload are the basis for the reported medians.

This is an isolated four-vCPU qualification, not production p95, concurrency,
or SLO evidence. It does not establish user-facing activation eligibility.
Campaign B must separately pass the eight lifecycle submissions before any
production activation decision. At Campaign A restoration, 5,483 seconds
remained before automatic VM STOP, below the required 6,000-second
maintenance-entry gate; Campaign B was therefore deferred to a fresh VM
window.

## Restoration

The native driver exited zero, the independent watchdog exited zero, and the
separate `native_host_control.py verify` command exited zero. Verification
confirmed the original container ID, image, mounts, restart policy, both
health endpoints (HTTP 200), unchanged publication metadata, no diagnostic
container, and no process owning either scratch Qdrant directory. The original
container is `seneca-review` (`seneca-review:9c92e706c4b9`), with
`/srv/seneca/data:/data` read-write and `/srv/seneca/models:/models`
read-only, restart policy `unless-stopped`.

`RESTORATION_VERIFICATION.json` records the identities and verification
outcome. Original session scratch and its independent data copies remain on
the VM for evidence custody; they were not reused for Campaign B.
