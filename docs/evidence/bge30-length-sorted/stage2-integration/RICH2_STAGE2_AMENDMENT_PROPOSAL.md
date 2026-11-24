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
`rich2-metadata` publication baseline while the service is healthy. Set
`DRIVER` and `INPUTS` to those directories in the reviewed checkout, and set
`SESSION` to a 16-character lowercase hex identity. Derive the container name,
ownership label, and scratch root from the helper so the scratch root matches
the `rich2-stage1` path assertion in `preflight_host.sh`:

```bash
set -euo pipefail
: "${DRIVER:?set to the reviewed stage2-driver checkout}"
: "${INPUTS:?set to its stage2-integration directory}"
: "${CPUSET:?set to the verified four-CPU set}"
: "${STOP_EPOCH:?set to the freshly verified host STOP epoch}"
: "${WATCHDOG_MONOTONIC_DEADLINE:?set to the accepted bounded monotonic deadline}"
SESSION=$(python3 -c 'import secrets; print(secrets.token_hex(8))')
IDENTITY=$(python "$DRIVER/native_host_control.py" rich2-identity "$SESSION")
CONTAINER_NAME=$(python -c 'import json,sys; print(json.load(sys.stdin)["name"])' <<<"$IDENTITY")
CONTAINER_LABEL=$(python -c 'import json,sys; print(json.load(sys.stdin)["label"])' <<<"$IDENTITY")
SCRATCH=$(python -c 'import json,sys; print(json.load(sys.stdin)["scratch_root"])' <<<"$IDENTITY")
DONE="$SCRATCH/done"
ABORT="$SCRATCH/abort"
test ! -e "$SCRATCH"
mkdir -m 0700 "$SCRATCH"
sudo install -d -m 0777 -o 10001 -g 10001 "$SCRATCH/stage1"
test ! -e "$DONE" && test ! -e "$ABORT"
SNAPSHOT="$SCRATCH/container.json"
METADATA="$SCRATCH/rich2-metadata.json"
python "$DRIVER/native_host_control.py" capture "$SNAPSHOT"
bash "$DRIVER/preflight_host.sh" rich2-metadata \
  /srv/seneca/data /srv/seneca/models "$CPUSET" > "$METADATA"
nohup python "$DRIVER/native_host_control.py" supervise \
  --session "$SESSION" --container "$CONTAINER_NAME" \
  --scratch "$SCRATCH" --snapshot "$SNAPSHOT" \
  --done "$DONE" --abort "$ABORT" \
  --ceiling-epoch "$WATCHDOG_MONOTONIC_DEADLINE" \
  --metadata-baseline "$METADATA" --metadata-mode rich2-metadata \
  --cpuset "$CPUSET" --scratch-layout rich2-stage1 \
  > "$SCRATCH/watchdog.log" 2>&1 < /dev/null &
WATCHDOG_PID=$!
restore_on_exit() {
  status=$?
  trap - EXIT INT TERM
  if [[ ! -e $DONE ]]; then
    python "$DRIVER/native_host_control.py" signal-failure \
      --abort "$ABORT" --done "$DONE" || status=1
  fi
  wait "$WATCHDOG_PID" || watchdog_status=$?
  if [[ ${watchdog_status:-0} -ne 0 && $status -eq 0 ]]; then
    status=$watchdog_status
  fi
  exit "$status"
}
trap restore_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
sleep 0.2
kill -0 "$WATCHDOG_PID"
WATCHDOG_STATE=$(ps -o stat= -p "$WATCHDOG_PID")
test -n "$WATCHDOG_STATE" && [[ $WATCHDOG_STATE != Z* ]]
```

This produces scratch `/var/tmp/seneca-rich2-stage1-$SESSION`, while the
separately required diagnostic container remains `seneca-stage2-$SESSION`
with label `io.seneca.stage2.session=$SESSION`. Capture the baseline into a
session-owned file inside `$SCRATCH`. The watchdog command above must return a
live PID; the monotonic deadline, CPU set, and host checks come from the
separately accepted execution limits. Confirm the supervisor remains alive
before proceeding.

Only after the supervisor is confirmed alive may the coordinator stop the
original container and copy its data into the session-owned scratch tree. Use
the previously accepted copy procedure and ensure the copied data is writable
by the diagnostic UID; never open original Qdrant storage from another process:

```bash
docker stop --time 30 seneca-review
test "$(docker inspect --format '{{.State.Running}}' seneca-review)" = false
sudo install -d -m 0700 -o 10001 -g 10001 "$SCRATCH/data"
sudo cp -a /srv/seneca/data/. "$SCRATCH/data/"
```

Then verify exclusive Qdrant ownership and run isolated preflight with the same
session-root convention:

```bash
bash "$DRIVER/preflight_host.sh" rich2-stage1 \
  "$SCRATCH/data" /srv/seneca/models "$CPUSET" "$STOP_EPOCH"
```

A shell `EXIT`/signal handler must call
`native_host_control.py signal-failure --abort "$ABORT" --done "$DONE"` on
any failure after watchdog startup, then wait for that supervisor's restoration
and verification before returning failure. This includes stop, copy and
preflight errors, even when no diagnostic container was created. On a normal
one-shot completion, the coordinator first waits for the diagnostic container
to exit and records its status. Only when that status is zero and the mounted
`$SCRATCH/stage1/rich2-stage1.json` is present does it emit the watchdog's
session-bound completion record using the diagnostic exit status and mounted
result path, as shown in the launch sequence below.

The command validates the one-shot observation schema and writes an atomic
`seneca-rich2-stage1-completion-v1` record containing the session, zero exit
status, and completion timestamp. The supervisor validates that record after
restoration. On any nonzero diagnostic status or earlier coordinator failure,
use `signal-failure` instead; an incomplete/empty scratch data tree is allowed
only on that aborted path. The original service, both health endpoints and
publication metadata are verified before scratch ownership checks. If the
Qdrant directory exists, ownership is always checked; successful probe paths
also require that directory to exist and be unowned. Wait for the supervisor,
and treat any nonzero diagnostic or supervisor status as qualification failure.

The isolated preflight and diagnostic container use the same read-only source
mounts: the driver checkout at `/review/driver` and frozen inputs at
`/review/inputs`. The one-shot script resolves those exact container paths;
local tests continue to resolve inputs from the repository checkout. The
diagnostic container is created with the session-derived name and label, no
network, the frozen CPU/memory limits, writable isolated `/data`, read-only
`/models`, driver and inputs, and the result directory at `/stage1`:

```bash
docker create --name "$CONTAINER_NAME" --label "$CONTAINER_LABEL" \
  --network none --cpuset-cpus "$CPUSET" --memory 6g --memory-swap 6g \
  --mount "type=bind,src=$SCRATCH/data,dst=/data" \
  --mount "type=bind,src=/srv/seneca/models,dst=/models,readonly" \
  --mount "type=bind,src=$DRIVER,dst=/review/driver,readonly" \
  --mount "type=bind,src=$INPUTS,dst=/review/inputs,readonly" \
  --mount "type=bind,src=$SCRATCH/stage1,dst=/stage1" \
  -e SENECA_ISOLATED_COPY=verified \
  -e SENECA_RICH2_STAGE1_EXECUTION_AUTHORIZED=one-call \
  -e OFFLINE_RAG_CONFIG=/app/config/base.yaml \
  -e OFFLINE_RAG_DATA_DIR=/data -e OFFLINE_RAG_MODELS_DIR=/models \
  -e OFFLINE_RAG_STRICT_OFFLINE=true -e HF_HUB_OFFLINE=1 \
  -e TRANSFORMERS_OFFLINE=1 \
  --entrypoint timeout \
  sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04 \
  -k 2 180 \
  python -B /review/driver/rich2_stage1.py --execute-one-call
```

Before `docker start`, verify the created container with
`docker_adapter.owned_container(CONTAINER_NAME, SESSION)`. Start and wait for
that exact container; use its exit status and the mounted result path in the
completion command above. The watchdog accepts only the same session-bound
name and terminates only that owned container. Successful completion requires
the watchdog's post-restore checks: original container
identity/image/mounts/restart policy, both health endpoints, unchanged
read-only publication metadata, and unowned scratch Qdrant storage.

The ownership check and start/wait sequence is:

```bash
python - "$DRIVER" "$CONTAINER_NAME" "$SESSION" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from docker_adapter import owned_container
assert owned_container(sys.argv[2], sys.argv[3]) is not None
PY
docker start "$CONTAINER_NAME" >/dev/null
DIAGNOSTIC_STATUS=$(docker wait "$CONTAINER_NAME")
if [[ $DIAGNOSTIC_STATUS -ne 0 ]]; then
  exit 1
fi
sudo chown "$(id -u):$(id -g)" "$SCRATCH/stage1/rich2-stage1.json"
python "$DRIVER/native_host_control.py" complete \
  --done "$DONE" --session "$SESSION" --exit-code "$DIAGNOSTIC_STATUS" \
  --diagnostic-result "$SCRATCH/stage1/rich2-stage1.json"
```

If `DIAGNOSTIC_STATUS` is nonzero, signal failure and wait for watchdog
restoration; only status zero proceeds to the observation-backed `complete`
command. The diagnostic's `/review/inputs` bind is read-only and contains the
same `rich2-stage1-binding.json`, `stage1-bindings.json`, workload and native
settings files that local tests resolve from `stage2-integration/`.

## Explicit boundary

This proposal authorizes no VM startup, host maintenance, production
interruption, data transfer/copy, model loading, live query, one-shot probe,
Stage 2 submission, deployment, merge, or batching activation. Rich 2 is not
yet part of the executable Stage 2 workload.
