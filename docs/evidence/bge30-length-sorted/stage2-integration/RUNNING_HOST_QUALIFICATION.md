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
