# Managed workspace query worker — analysis only

Deployed source: 9c92e706c4b9e9d9ac0816a655bdf131cc63fca1.

The synchronous workspace conversation route (api/workspaces.py:675–690)
calls run_conversation_turn without an operation handle. The conversation
core already accepts one. /v1/query uses the existing admission gate and
run_owned_worker with disconnect watching (api/query.py:47–90,
api/workers.py:25–67). The effective managed-query budget is one concurrent
query and a 180-second cooperative deadline. Neither gates the current
workspace route.

A separate corrective could preserve the workspace validator and canonical
grounded executor while routing work through that existing gate and worker.
Preserve A2-D05b's request validation before readiness/admission so malformed
turns retain their established errors. Acquire a shared token before resolver
or inference. Overload should return the existing typed error rather than
begin a second inference. Keep capacity held until the worker actually
exits, including on client disconnect or expiry. The disconnect watcher
signals cancellation, and the operation checks it at existing checkpoints.
An in-flight Torch forward call cannot be preempted by that mechanism.
A detected disconnect during assembly can prevent subsequent generation
once the next checkpoint is reached. The managed deadline is a behavior
change on this route and needs explicit review of scope and error mapping.
It does not guarantee a wall-clock limit for noninterruptible inference.

Keep the revision, snapshot and document IDs captured at admission, including
while the UI's workspace changes. Preserve conversation/query trace IDs,
terminal projections and normal cited rendering. Define how to record a
cancellation before grounded execution allocates a trace. Avoid fabricating
an HTTP response code for a disconnected client.

Validation should cover malformed requests under readiness/drain, admission
overload without model calls, disconnect during assembly with no generation
after the next checkpoint, token retention until worker return, deadline
mapping, trace persistence, concurrent publication without rebinding, and
unchanged successful cited rendering. Use deterministic HTTP test fixtures
before a separately authorized live smoke. Roll back by selecting the
previous deployment image with its same mounts and settings, then verify
health and immutable publication identity.

The owned worker could address abandoned work or load amplification. It
does not make one isolated prompt faster. For that problem, the smallest
follow-up is a bounded projection of existing context metadata: count plus
dense, lexical, fusion, BGE and context packing times, and an explicit
cold/warm observation. No new performance framework or science change.
