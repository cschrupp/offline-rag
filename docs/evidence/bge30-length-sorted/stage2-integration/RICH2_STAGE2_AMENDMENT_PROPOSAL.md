# Proposed Stage 2 Workload Amendment — Rich 2

**Status:** Proposal for independent review; not accepted and not execution
authority.

## Purpose

Replace the historical Rich revision-2 workload in a future Stage 2 execution
manifest with the separately bound **Rich 2** workspace, but only after the
authorized Rich 2 Stage 1 isolated assembler probe completes and its evidence
is independently accepted.

This proposal does not alter the frozen Stage 2 workload manifest or historical
Rich evidence. The existing `stage1-bindings.json`, `workloads.json`, and
`NATIVE_SETTINGS_MANIFEST.json` remain unchanged.

## Proposed binding

Use the distinct preparation binding in `rich2-stage1-binding.json`:

- workspace `ws_ee9ddd1e51354be1b7981282cc1dd240`, revision 2;
- source `src_e5f3f9cf065a468397d85e4c97f7f6f5`;
- source inventory SHA-256
  `3fef97218820b06e65baa48468923f7ac23166c286b648722f5db468c4accfad`;
- one source document
  `doc_c3084e336e87f2bbcc915a3c12b0e9bbd6128d8c34298637abbfb0ea6ac390cc`;
- snapshot `snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca`;
- no prior turns, question “Describe the naturalistic decision method”,
  `all_active` source scope;
- ten searchable child candidates and the already-bound scientific settings.

The historical Rich revision-2 binding remains available as provenance. Matching
document and snapshot identities do not merge the two workspace identities or
make the new binding historical evidence.

## Proposed change after acceptance

If the Rich 2 Stage 1 probe and its review pass, prepare a separate,
independently reviewable amendment that:

1. substitutes the Rich 2 workspace/revision/source-inventory binding for the
   Rich workload in a new Stage 2 execution manifest;
2. retains Recipes exactly as currently bound;
3. retains the question, no-history condition, `all_active` scope, application
   image, model artifacts, CPU policy, batching comparison, resource limits,
   28 load plus 8 lifecycle submissions, and zero retries;
4. records the amendment date and links the original frozen workload and Rich
   2 Stage 1 evidence without rewriting either; and
5. updates the execution driver's expected binding set only in that new
   amendment candidate.

The existing frozen manifest must not be edited in place. Any resulting
execution manifest must receive a new identity and independent review before
Stage 2 can be authorized.

## Required Stage 1 acceptance evidence

Before proposing the execution-manifest change, require the one isolated
assembler call to verify physical snapshot resolution in the exclusive scratch
copy, exactly ten in-scope fused candidates, ordered candidate identities and
raw-logit associations, canonical tie-breaking, anchor and evidence-unit
identities, packed-context hash, complete existing stage timings, exact
scientific/configuration identities, and restoration of the original service
and publications.

Any missing backing, source/snapshot/config drift, candidate population or
scope mismatch, incomplete instrumentation, resource-policy violation, or
restoration failure leaves the amendment unqualified.

## Failure-safe order for the future authorized probe

The independent restore watchdog must be running **before** the original
container is stopped. First capture its exact identity and the read-only
`rich2-metadata` publication baseline while the service is healthy. Create the
unique scratch/session directory, empty `stage1` output directory, and absent
`done`/`abort` markers. Then launch
`native_host_control.py supervise` independently with the captured container
snapshot, metadata baseline, `--scratch-layout rich2-stage1`,
`--metadata-mode rich2-metadata`, the verified CPU set, and the bounded
monotonic ceiling.

Only after the supervisor is confirmed alive may the coordinator stop the
original container, copy `/srv/seneca/data`, verify exclusive Qdrant ownership,
and run isolated preflight. A shell `EXIT`/signal handler must call
`native_host_control.py signal-failure --abort "$ABORT" --done "$DONE"` on
any failure after watchdog startup, then wait for that supervisor's restoration
and verification before returning failure. This includes stop, copy and
preflight errors, even when no diagnostic container was created. On a normal
one-shot completion, the coordinator records the exit status in `done`, waits
for the supervisor, and treats any nonzero diagnostic or supervisor status as
qualification failure.

The diagnostic container name and ownership label must come from
`native_host_control.py rich2-identity "$SESSION"`. The required pair is
`seneca-stage2-$SESSION` and
`io.seneca.stage2.session=$SESSION`; verify the created container with the
existing `docker_adapter.owned_container()` check before starting it. The
watchdog then terminates only that exact session-owned container. Successful
completion requires the watchdog's post-restore checks: original container
identity/image/mounts/restart policy, both health endpoints, unchanged
read-only publication metadata, and unowned scratch Qdrant storage.

## Explicit boundary

This proposal authorizes no VM startup, host maintenance, production
interruption, data transfer/copy, model loading, live query, one-shot probe,
Stage 2 submission, deployment, merge, or batching activation. Rich 2 is not
yet part of the executable Stage 2 workload.
