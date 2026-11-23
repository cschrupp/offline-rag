# Historical Stage 2 partial-driver response

> **Historical snapshot:** this response predates completion of the Docker
> adapter and full local rehearsal. Its pending items were implemented and
> tested later. The current qualification is recorded in
> [DOCKER_QUALIFICATION.md](DOCKER_QUALIFICATION.md) and the full completion
> handoff in [STAGE2_FINAL_RESPONSE.md](STAGE2_FINAL_RESPONSE.md).

# Stage 2 driver qualification checkpoint

**Partial local qualification. Execution gate remains closed.**
The Stage 2 integration source and image were preserved. No production
application code, model behavior, settings, VM or workspace was changed.
The authorization is retained in [AUTHORIZATION.md](AUTHORIZATION.md).

## Implemented and verified locally

- [Scheduler](driver.py) has the exact 28 load and eight lifecycle call
  schedule, synchronized 1/2/4 client waves, unique ordinals, budgeted
  attempts and no retry path. It rejects incomplete or mismatched
  settlement. The full 36-case synthetic adapter rehearsal passed.
- The settlement envelope records one ordinal, strategy/workload from
  the attempt, admission class, HTTP status if delivered, operation
  identity, terminal category, and worker-return acknowledgement.
  Synthetic tests distinguish the two 503 reasons, reject client EOF
  as worker completion, and stop future attempts after watchdog abort.
  The scheduler records an attempt before calling transport. A real
  adapter still needs to record the actual send boundary and correlate
  operation and trace IDs.
- The [independent process watchdog](host_watchdog.py) passed local
  resource and deadline abort tests. It kills only its child process
  group. Docker container cleanup must be independently targeted by a
  future adapter. Killing a Docker CLI client alone does not remove a
  detached container or free its Qdrant lock.
- [Forward observation hooks](forward_observer.py) provide bounded
  barriers and record forward shape and wall time without altering
  model inputs or outputs. A deterministic Torch fixture confirmed
  unchanged output and hook removal. The hooks have not been connected
  to the production checkpoint under HTTP or to a per-request
  operation ID in the complete driver.
- Both strategies passed the existing bounded real-loopback ownership
  check again with deterministic resources, including shared admission,
  abandoned worker retention, next-checkpoint deadline and shutdown
  after transport grace. This is separate from the scheduler rehearsal.
  It does not qualify the full Docker campaign.
- Ten scheduler and helper tests passed. Ruff lint and format, Python
  compilation, shell parsing and Git whitespace checks passed.
  [Scheduler results](SCHEDULER_RESULTS.txt) · [Loopback output](LOOPBACK.txt)

## Immutable artifact and transfer

The locally retained image was verified without rebuilding. Docker
reported its exposed image ID and OCI index digest as the same value on
this engine. The AMD64 platform manifest and its image configuration
are different digests. The verifier checks the descriptor and artifact
structure explicitly. All 402 source-file digests matched the integrated
commit. The fixture, dependency versions, CPU-only Torch, depth 30,
default/opt-in behavior and shared reranker fingerprint matched the
accepted image attestation. An initial Docker template lookup failed
on the descriptor field casing. Parsing the inspect JSON corrected it.
[Image verification](IMAGE_VERIFICATION.txt) · [Archive identities](ARCHIVE_VERIFICATION.txt)

A Docker save archive was verified locally. It is retained outside Git at
`/tmp/seneca-stage2-qualified-image.tar`. An authorized offline transfer
must use these exact bytes. Before and after transfer run:

```bash
driver=docs/evidence/bge30-length-sorted/stage2-driver
python "$driver/verify_archive.py" /path/to/seneca-stage2-qualified-image.tar
```

After separate authority to stage the artifact on the intended host, use
`docker image load -i /path/to/seneca-stage2-qualified-image.tar`, then
`bash "$driver/verify_image.sh"`. Fail closed if the loaded OCI descriptor
or runtime differs. Rebuilt derivatives and Docker exports that change
the archived identity require separate review. No archive was imported
on or transferred to the intended host.

## Read-only preflight and remaining gate

The accepted [workloads](../stage2-integration/workloads.json) and
[Stage 1 bindings](../stage2-integration/stage1-bindings.json) remain
unchanged. The [host script](preflight_host.sh) selects the exact image,
loopback-only network namespace, CPU set, read-only model mount and 6 GiB
container memory cap. Metadata mode mounts data read-only and never opens
Qdrant. It resolves the Recipes logical source against the original
trace scope and checks Rich's single-document scope, publication
identities, manifests, workspace inventory, science hash and model
files. Isolated mode requires an existing dedicated scratch copy, checks
for overlapping mounts on running containers and opens only that copy
to validate backing completeness. This gate still requires host-level
exclusive ownership against non-Docker processes. It performs no service
maintenance. Missing publication and insufficient STOP window were
rejected locally. Positive binding and real backing validation on the
intended host remain unexecuted.

Both arm preflights must match the frozen settings and bindings, with the
batching strategy as the only treatment difference. The wrapper currently
uses image/default settings. A sanitized, credential-free injection of the
actual scientific settings, and a capture of both effective settings
manifests, still require verification. Do not run against an incorrect
configuration or infer success from the image attestation alone.

## Operational state machine and execution decision

The frozen proposal requires at least 4,800 s until automatic STOP,
at most 2,400 s diagnostic execution, at least 900 s restoration
reserve, a 6 GiB RSS ceiling, 2 GiB host-available memory floor and
unchanged 180 s cooperative query deadline. The 195 s client watchdog
is a transport bound. On expiry stop new submissions and record the
disconnect. It cannot be used as evidence of worker return or as
permission to release capacity. A deadline fixture releases held work
after 180 s and before transport expiry. If that interval cannot safely
be met, mark the case incomplete. Hard host expiry must target the
isolated container and confirm its termination before storage cleanup.
The runtime still owns its slot during cooperative shutdown, including
when transport grace expires.

The final host state sequence must be: verified artifacts and safe
copy → verified idle original → arm independent restoration → stop
original → start first isolated arm → settle all requests or abort →
terminate isolated container and confirm storage release → next arm
only if healthy and within budget → restore original → verify both
health endpoints, image, mounts, policy and publication identities →
discard only the isolated copy. Any failure closes the submit gate
and invokes restoration. Neither a missing terminal event nor a
watchdog-aborted session can pass.

**Do not issue VM execution authority yet.** The remaining deliverable is
a bounded real Docker/HTTP adapter with operation-to-request correlation,
client socket watchdog, held lifecycle barriers wired to the canonical
route, Docker termination and independently rehearsed restoration.
Rehearse the complete adapter with synthetic backing first. The local
primitives do not yet demonstrate these pieces as one end-to-end driver.
The host still needs read-only image/data/model verification and reserved
restoration time. No scientific behavior change has been identified as
necessary. A test requiring such a change should return for review.

Proposed final authority, conditional on closing those gates: permit
one isolated maintenance window on the verified host using the exact
diagnostic archive and frozen bindings. Permit only 28 load and eight
lifecycle submissions, maximum 36 and zero retries, across the two
unchanged arms. Apply the ceilings above and the reviewed independent
watchdogs. Require restoration verification and preserve all submitted
outcomes. Exclude production queries, external provider calls,
migration, default changes, deployment and merge.
