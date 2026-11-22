# CPU Stage 2 preflight and Stage 1 closeout

**Stage 2 blocked before maintenance. Zero campaign submissions.** The
accepted Stage 1 measurements and outcomes are preserved.

## Stage 1 credential closeout

The historical runner created `runtime.env` before invoking Docker and
unlinked it only on the normal path. An exit or interrupt between those
operations could leave the file. The maintained runner now streams the
validated environment through an anonymous pipe to Docker's
`--env-file /dev/stdin`; it creates no credential file. Docker retains
container configuration until normal diagnostic teardown removes the
container, as before. The file-level change does not alter effective
settings or the measurement code.

SSH inspection searched Seneca diagnostic directories under `/tmp` and
`/var/tmp` for environment files by name, without reading their contents.
No matching files were found, so no credential files were removed. There
was no diagnostic container left. For all three Stage 1 directories the
before and after workspace records matched byte for byte and the copied
data directory was absent. The two failed setups stopped before any
assembler calls. One was a read-permission error on staged Python files
and the other a missing retriever import in the probe. The accepted run
and its measurement files are untouched.

`bash -n` and `git diff --check` passed. A network-disabled Docker
smoke with a dummy variable verified `--env-file /dev/stdin` using the
same image. An initial smoke command had a Python quoting error;
the subsequent check passed. Neither smoke started the application or
loaded a model.

## Blocking route contract

The intended synchronous workspace conversation endpoint in
`src/offline_rag/api/workspaces.py` calls `run_conversation_turn`
without an operation handle. The checkpoints in
`src/offline_rag/app/conversation/turn.py` require that handle.
The endpoint neither admits through the managed query gate nor starts
the disconnect watcher. A client-side timeout does not supply the
missing server-side deadline checkpoint. The failure to wire this
control exists on both batching arms. Actual disconnect, drain,
resource contention and terminal behavior remain unmeasured.

`/v1/query` in `src/offline_rag/api/query.py` does obtain an operation
handle, watches for disconnect through `api/workers.py`, and releases
the handle after the worker terminates. That endpoint does not provide
the workspace conversation route or its selected-source request
contract. Substituting it or injecting an operation handle into the
workspace endpoint would change the behavior under qualification.
Managed query lifecycle is also unqualified by this campaign.

The VM was running with its original container and returned HTTP 200
for both health probes. Automatic STOP was scheduled for 12:40 La Paz.
No complete, bounded execution plan could be frozen for the intended
route's required lifecycle cases under the unchanged contract. The
isolated workload phase was not run as a partial substitute for the
complete campaign. No maintenance, application request, provider call
or production change occurred.

## Readiness

Recipes retains the Stage 1 parity and performance pass for the exact
isolated workload only. Rich retains its parity pass, missed performance
gate and 45.731 s outlier. Neither has qualified actual HTTP contention,
citation delivery or lifecycle behavior. There is no qualified CPU
opt-in scope yet and no workload selector was designed.

The next review should resolve the workspace lifecycle contract and
approve a route-specific local fixture and bounded campaign for a fresh
window. Keep the consecutive default and PR #3 draft. Any later pilot
rollback would restore consecutive on an image retaining the initializer
and verify health, snapshot binding, admission, latency, error and
abandoned-work behavior.
