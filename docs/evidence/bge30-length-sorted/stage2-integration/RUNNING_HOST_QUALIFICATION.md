# Running-Host Qualification — Read-Only Attempt

**Observed:** 2026-11-23 18:10 UTC

**Disposition:** `NO-GO — host qualification incomplete; native Stage 2 not authorized`

**Repository:** `prep/stage2-docker-transport` at `65fc2cf2f4e04ed16790f4637a26d0c4257c142b`

This record covers read-only qualification only. No application container was
stopped, started, or replaced; no live data was copied; no model was loaded;
and no query or Stage 2 submission was executed.

## Results

| Check | Result | Evidence |
|---|---|---|
| Repository identity | PASS | Worktree clean; local and remote preparation branch were both `65fc2cf2`. The native implementation (`69c46fb`), accepted preparation evidence (`00a05817`), and integrated application (`1f79eca0`) are ancestors. |
| VM identity/status | PASS | GCP API returned instance ID `1808070158197176999`, `RUNNING`, `e2-standard-4`, zone `us-central1-a`. |
| Automatic STOP controller | PASS, current window only | Instance scheduling specifies `maxRunDuration=7200` seconds and termination action `STOP`. From `lastStartTimestamp=2026-11-23T09:54:26.441-08:00`, the configured deadline was epoch `1795463666`; 6,262 seconds remained at observation. This is not an authorization to run the campaign. |
| Boot-disk provision | PARTIAL | GCP API reports one 50 GB boot disk. Guest filesystem capacity and free space were unavailable. |
| Existing SSH identity | BLOCKED | The local public key matches an unexpired project-metadata key and the GCE host-key alias is already known. No matching identity is loaded in an SSH agent; the private key was not usable noninteractively. SSH returned `Permission denied (publickey)`. No key was generated, registered, or changed. |
| External application health | UNAVAILABLE | Read-only GETs to `/health/live` and `/health/ready` on port 8080 timed out. This does not establish that the application is unhealthy; it only means this execution environment could not reach those endpoints. |
| Container identity, health, mounts and restart policy | UNAVAILABLE | Requires the blocked SSH host access. |
| Guest CPU affinity, memory, swap, free disk, competing containers and current operations | UNAVAILABLE | Requires the blocked SSH host access. |
| Live publication metadata and Qdrant ownership | UNAVAILABLE | No live data inspection or alternate Qdrant access was attempted. |
| Model hashes and compatibility | UNAVAILABLE on VM | Host model files could not be read. Locally, the retained model archive SHA-256 matches the custody manifest. |
| Pinned diagnostic image on VM | UNAVAILABLE | No Docker host access. Locally, the retained archive SHA-256 matches `48084b824acd41126f54eb264d6ad63f4414be3239a23ed905edf864c50c3380`. |
| Metadata-only preflight | NOT RUN | Source review confirms `preflight.py metadata` does not enter the Qdrant backend-opening branch; it validates file-backed metadata and hashes. It was not run because the SSH connection failed and copying code to the host is outside this read-only attempt. |

## Access boundary and restoration of an unintended change

The first SSH attempt used the existing key and made no key or IAM changes. A
subsequent `gcloud compute ssh --troubleshoot` unexpectedly initiated enabling
the Network Management API, outside the read-only authority. I disabled that
service immediately and verified it no longer appears in the project's
enabled-service list. The troubleshooting command did not complete a network
diagnostic. No other cloud configuration was changed.

## Artifacts and frozen experiment

Locally retained image and model archive identities match the custody
manifest. The experiment remains frozen at 28 load submissions plus 8
lifecycle submissions, 36 total, with zero retries. No submissions were
spent. The accepted BGE, Qwen3, candidate depth, batching strategies,
workspaces, and snapshots were not changed.

## Disposition and remaining prerequisites

**Overall: NO-GO for separately authorizing native Stage 2 based on this
attempt.** The GCP control plane confirms the intended instance is running
and the configured STOP reserve currently exceeds 4,800 seconds, but the
application, guest resources, actual publications, model artifacts, Docker
image availability, and Qdrant ownership could not be qualified.

The concrete blocker is an SSH identity usable by this session. The existing
public key is already registered, so the next access path should unlock/load
its matching private key or use another already-authorized SSH identity. Do
not register a new key, change IAM, or enable another GCP service to work
around this blocker. Once read-only host access is available, repeat the
remaining host checks and the metadata-only preflight. A separate native
campaign authorization is still required even if those checks pass.

## Read-only running-host follow-up — 2026-11-23

**Authority:** User authorized read-only qualification after starting the VM;
the existing SSH private key could be unlocked with the passphrase supplied
directly by the user. The passphrase is not recorded here. No key, IAM, VM,
container, configuration, publication, or workspace changes were made.

**Current disposition:** `NO-GO — Rich frozen publication binding has drifted;
the pinned diagnostic image and its exact host checkout are also unavailable.
Native Stage 2 remains unauthorized.`

The earlier access failure and Network Management API enable/disable event
above remain historical facts. This follow-up does not rewrite that record.

### Host and service checks

| Check | Result | Evidence |
|---|---|---|
| SSH access | PASS | `gcloud compute ssh` connected using the existing registered key in a temporary SSH agent. The agent was removed on command exit. No credential was created or registered. |
| GCP identity and lifecycle | PASS for read-only qualification | Instance `1808070158197176999`, `RUNNING`, `e2-standard-4`, zone `us-central1-a`. GCE scheduling reports `maxRunDuration=7200s`, termination action `STOP`, and `lastStartTimestamp=2026-11-23T09:54:26.441-08:00`. This configured deadline is 2026-11-23 19:54:26 UTC (epoch `1795463666`); 5,029 seconds remained at 18:30:37 UTC. This exceeds the later campaign's 4,800-second preflight threshold at this observation only; it does not authorize that campaign. Cloud Scheduler inventory was unavailable because its API is disabled; it was not enabled. |
| Guest resources | PASS for current host preflight | Four logical CPUs and affinity `0-3`; 16.78 GB RAM total, 15.85 GB available; 8.59 GB swap with 12 KB used. Root/`/var/tmp` filesystem has 52.59 GB total and 21.63 GB available. `/srv/seneca/data` is 101,269,855 bytes; the runbook's `2 × data + 2 GiB` scratch estimate is about 2.35 GB, below available space. |
| Active containers and load | PASS at sampling | Only `seneca-review` was running; `seneca-review-preranker-rollback` was exited. `seneca-review` reported 0.18% CPU, 362.9 MiB memory, 7 PIDs. No established TCP connections to port 8080 were present at sampling. |
| Container identity | PASS | Container ID `e006597fd6e4e40939e49c1dd73da7c6d85f33d87d44929c15dc5f0f38bb7cac`; image reference `seneca-review:9c92e706c4b9`; image ID `sha256:3bc83208a7526a49abed1b9bd9586b5ae4fd041771732e03030c3ac20419e692`; running; restart count 0; OOM false; restart policy `unless-stopped`. |
| Mounts and health | PASS | `/srv/seneca/data` → `/data` read/write; `/srv/seneca/models` → `/models` read-only. `/health/live` and `/health/ready` both returned 200. The original container was not stopped or restarted. |
| Qdrant ownership / active work | PASS for non-interference check | The live application was the sole running container with the data mount; no second Qdrant backend was opened. Existing managed-operation records were all terminal: 8 succeeded, 2 failed, 1 interrupted; zero nonterminal records. The check did not inspect private operation payloads. |

### Configuration, model and publication checks

The active container's `/app/config/base.yaml` SHA-256 is
`dc45247f1c807237cf09e8570d26b2600e685f637f967b7f162ed84cf9db77f0`, matching
the frozen native settings manifest. The deployment's computed scientific
settings hash is
`5dce337dc1875b2aa615d62ee771a0ae384559c2da14be384e067ded035f5417`, also
matching. The safe configuration projection reported query capacity 1,
180-second query deadline, 30-second shutdown grace, BGE revision
`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, input/output depths 30/10,
batch size 16, max length 1024, and Qwen revision
`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`. No environment variables or
credentials were displayed. The current runtime capability projection selects
`cpu_onnx_fp32_v1` / `onnx_fp32_v1`, CPUExecutionProvider and FP32; its state
was `UNLOADED`. No model was loaded or inference executed. The deployed
configuration reports `strict_offline=false`; the authorized future
diagnostic is separately designed to set strict offline and disable network.

Read-only SHA-256 checks through the existing container matched all expected
listed model files: BGE 6/6 and Qwen ONNX 16/16. These checks read the
read-only model mount and did not load either model.

| Workload | Result | Verified metadata |
|---|---|---|
| Recipes | PASS | Workspace `ws_198edc9159d04d4fa9527bef1c7dc513`, active revision 4; current snapshot and publication pointer both `snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196`; selected scope resolves to the frozen document; source inventory hash `378173053c42ef2afcb0985d9d24b9a6f2a320e299ded06a815e7a9e6ee4b101`; snapshot manifest hash matches; dense index has 603 expected/indexed passages; snapshot ID recomputes and its file-backed manifests and Qdrant collection directory exist. |
| Rich | **FAIL — frozen binding changed** | Workspace `ws_73a29d6defb545e8958746d78ac80775` is active at revision 3, not required revision 2. Current snapshot and publication pointer are both `snap_8047d545f63c35453fb0ea8584dddba5d014958d746b2c0e7d229cf5c9c81f4f`, not frozen snapshot `snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca`. Current source inventory hash is `3e389c40ec6b0dd94f8d51618978bdc97d73bb5d74f9f82511bd8c17975cfde1`, not the frozen hash. The frozen document remains active, but all-active scope now resolves to two documents; the frozen binding expected one. The current snapshot manifest recomputes correctly and reports 10 dense passages, but that does not restore the frozen identity. No workspace or publication was modified. |

### Preflight availability and scope

The exact pinned diagnostic image
`sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04`
is **not present on the VM**; no Stage 2 diagnostic image tag was found. The
expected checkout `/var/tmp/seneca-stage2-native-code` is absent, and no
existing `preflight_host.sh` was found under the inspected `/home/user`,
`/srv` (excluding model assets), or `/opt` trees. The retained local OCI
archive remains the transfer prerequisite recorded in the custody manifest;
it was not transferred. Therefore the canonical metadata-only preflight was
not run.

To independently inspect file-backed metadata despite that blocker, a
read-only Python projection was executed inside the already-running deployed
container. It used workspace/publication/snapshot metadata and manifest-file
loaders only; it did not instantiate a Qdrant client, resolve a query, load a
model, or call a provider. The first assertion-based pass stopped when it
detected the Rich revision mismatch; a subsequent non-asserting pass captured
the remaining metadata and model hashes. An intermediate local diagnostic
command had a quoting/syntax error and made no host change. The final
read-only checks completed successfully, except for the explicitly recorded
Rich binding mismatch.

The prior Network Management API event was restored to disabled as recorded
above. A later read-only Cloud Scheduler listing returned `SERVICE_DISABLED`;
it was not enabled and caused no cloud change. The GCE instance-level
max-runtime/STOP policy was available directly from Compute API.

### Decision and remaining prerequisites

**Overall: NO-GO for native Stage 2.** The host and service are healthy, the
frozen Recipes binding matches, the effective settings hash and model file
hashes match, and the STOP reserve exceeded the threshold at observation.
However:

1. Rich is no longer the authorized revision-2 / one-document snapshot. The
frozen Rich binding must be restored or separately re-authorized and
requalified; this read-only task does not authorize either action.
2. The exact pinned diagnostic image and native-preparation checkout must be
made available on the host under a separate, explicit transfer/staging
authorization, then the canonical metadata preflight must pass.
3. Before any later execution authority, recheck the STOP window, idle state,
   resources, exact images/mounts, both workloads, and all frozen bindings.

No Stage 2 submissions were made. The 36-call budget remains untouched. No
maintenance, data copy, query, model load, deployment, configuration change,
or publication modification occurred. Independent acceptance of this
read-only report and a separate native-campaign authorization are still
required.
