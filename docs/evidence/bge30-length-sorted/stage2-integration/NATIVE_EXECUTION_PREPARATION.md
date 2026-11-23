# Native Stage 2 execution preparation

**State:** locally prepared; host-dependent preflight unavailable; native campaign not authorized.

This runbook is a preparation artifact. It does not authorize VM startup, maintenance, workspace queries, deployment, merge, or batching activation. The synthetic rehearsal at the accepted evidence commit is not repeated.

## Frozen identities

| Item | Required identity |
| --- | --- |
| GCP project / VM / zone | `seneca-515016` / `seneca-review` / `us-central1-a` |
| Original service | container `seneca-review`, image ref `seneca-review:9c92e706c4b9` |
| Original data / models | `/srv/seneca/data` / `/srv/seneca/models` |
| Integrated application source | `1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e` |
| Diagnostic image | `sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04` |
| BGE | `BAAI/bge-reranker-v2-m3`, revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, FP32, raw logits, `input_k=30`, `output_k=10` |
| Embedding | Qwen3 revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, `cpu_onnx_fp32_v1`, `onnx_fp32_v1`, ORT 8/1 |
| Request lifecycle | 180-second query deadline, 30-second application shutdown grace |
| Workloads | Recipes revision 4 / frozen 603-passage snapshot / selected source; Rich revision 2 / frozen 10-candidate snapshot / all active |
| Calls | 28 load + 8 lifecycle = exactly 36; zero retries |

The complete hashes and immutable bindings are in [`NATIVE_SETTINGS_MANIFEST.json`](NATIVE_SETTINGS_MANIFEST.json), `workloads.json`, and `stage1-bindings.json`.

## Step 1 — Read-only cloud identity check

Run from the authorized operator environment. This command does not start the VM:

```bash
gcloud compute instances describe seneca-review \
  --project=seneca-515016 \
  --zone=us-central1-a \
  --format='value(name,status,zone)'
```

If status is not `RUNNING`, stop. Do not start it under this preparation. If it is running after a separately authorized startup, verify the host without printing environment variables or credentials:

```bash
gcloud compute ssh user@seneca-review \
  --project=seneca-515016 \
  --zone=us-central1-a \
  --command='set -eu
 test "$(hostname)" = seneca-review
 printf "epoch="; date +%s
 printf "cpus="; python3 -c "import os; print(len(os.sched_getaffinity(0)), sorted(os.sched_getaffinity(0)))"
 free -b
 df -B1 /srv/seneca/data /srv/seneca/models /var/tmp
 docker ps --format "{{.Names}} {{.Image}} {{.Status}}"
 docker inspect seneca-review --format "{{.Id}} {{.Config.Image}} {{.Image}} {{.State.Running}} {{json .HostConfig.RestartPolicy}}"
 docker inspect seneca-review --format "{{range .Mounts}}{{println .Source .Destination .RW}}{{end}}"
 docker exec seneca-review python -B -c "import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080/health/live\",timeout=3).status); print(urllib.request.urlopen(\"http://127.0.0.1:8080/health/ready\",timeout=3).status)"'
```

If `gcloud` proposes creating/registering an SSH key or changing access, cancel; do not alter credentials. Verify the automatic STOP epoch from the existing VM lifecycle controller. Do not infer it from the VM start time. Require at least 4,800 seconds remaining; otherwise stop.

## Step 2 — Verify exact preparation checkout

After this preparation revision has been pushed, use the recorded code candidate SHA in the commands below. The worktree must be clean, and its contents must include this native preparation revision and the accepted integrated source/image identities.

```bash
REPO=/path/to/offline-rag
CODE=/var/tmp/seneca-stage2-native-code
CANDIDATE_SHA=<native-preparation-code-commit>
git -C "$REPO" fetch origin prep/stage2-docker-transport
git -C "$REPO" worktree add --detach "$CODE" "$CANDIDATE_SHA"
test -z "$(git -C "$CODE" status --porcelain)"
test "$(git -C "$CODE" rev-parse HEAD)" = "$CANDIDATE_SHA"
test "$(git -C "$CODE" show 1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e:config/base.yaml | sha256sum | cut -d' ' -f1)" = dc45247f1c807237cf09e8570d26b2600e685f637f967b7f162ed84cf9db77f0
```

Do not use a stale installed driver or rebuild/retag the diagnostic image.

## Step 3 — Pre-maintenance evidence (requires native-campaign authority)

Only after a separate authority permits the native campaign, create a fresh session scratch root and capture the original container and published-state metadata. This does not alter the application container:

```bash
set -euo pipefail
SESSION=$(python3 -c 'import secrets; print(secrets.token_hex(8))')
ROOT="/var/tmp/seneca-stage2-native-$SESSION"
install -d -m 0700 "$ROOT"
CODE=/var/tmp/seneca-stage2-native-code
DRIVER="$CODE/docs/evidence/bge30-length-sorted/stage2-driver"
STOP_EPOCH=<verified-unix-epoch-from-existing-lifecycle-controller>
CPUSET=$(python3 -c 'import os; print(",".join(map(str, sorted(os.sched_getaffinity(0))[:4])))')
test "$(python3 -c 'import os; print(len(os.sched_getaffinity(0)))')" -ge 4
test "$((STOP_EPOCH - $(date +%s)))" -ge 4800
python3 "$DRIVER/native_host_control.py" capture "$ROOT/original-container.json"
bash "$DRIVER/preflight_host.sh" metadata /srv/seneca/data /srv/seneca/models "$CPUSET" > "$ROOT/baseline-publications.json"
chmod 0600 "$ROOT/baseline-publications.json"
```

The metadata output binds both workspace revisions, snapshots, source inventories, snapshot-manifest hashes, publication pointers, and retrieval settings. Stop if either health check, container/image/mount identity, metadata preflight, available-memory check, disk check, idle-operation check, or STOP window fails.

## Step 4 — Isolated data and binding preflight (requires native-campaign authority)

Stop the original container gracefully before copying. Never open the original Qdrant directory from a second process. The copy and UID-writability check below are confined to scratch copies; the original `/srv/seneca/data` and models are not changed.

```bash
set -euo pipefail
DATA_BYTES=$(du -sb /srv/seneca/data | cut -f1)
AVAILABLE_BYTES=$(df -B1 --output=avail /var/tmp | tail -n1 | tr -d ' ')
REQUIRED_BYTES=$((2 * DATA_BYTES + 2147483648))
test "$AVAILABLE_BYTES" -ge "$REQUIRED_BYTES"
docker stop --time 30 seneca-review
test "$(docker inspect --format '{{.State.Running}}' seneca-review)" = false
for ARM in A B; do
  install -d -m 0700 -o 10001 -g 10001 "$ROOT/$ARM/data"
  sudo cp -a /srv/seneca/data/. "$ROOT/$ARM/data/"
  docker run --rm --network none --user 10001:10001 \
    --mount "type=bind,src=$ROOT/$ARM/data,dst=/data" \
    --entrypoint python \
    sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04 \
    -B -c 'from pathlib import Path; p=Path("/data/.stage2-write-check"); p.write_text("ok"); p.unlink()'
  install -d -m 0777 -o 10001 -g 10001 "$ROOT/$ARM/preflight"
  python3 "$DRIVER/native_host_control.py" check-qdrant "$ROOT/$ARM/data/qdrant"
  bash "$DRIVER/preflight_host.sh" native \
    "$ROOT/$ARM/data" /srv/seneca/models "$CPUSET" "$STOP_EPOCH" \
    "$ROOT/$ARM/preflight"
done
cmp "$ROOT/A/preflight/native-bindings.json" "$ROOT/B/preflight/native-bindings.json"
```

The preflight container is network-disabled, uses the exact image, reads models read-only, verifies model artifact hashes, current snapshot backing, selected source resolution, strict-offline configuration, four effective CPUs, and Torch/ORT settings. Any mismatch is a stop condition; do not repair or rewrite the source workspace to make it pass.

## Step 5 — Independent watchdog, exact campaign, restoration

This step is included to make the restoration handoff executable; it still requires separate native-campaign authority. Start the independent watchdog before the runner. Keep it alive independently of the SSH shell:

```bash
cd "$CODE"
SUPERVISOR_CEILING=$(python3 -c 'import time; print(time.monotonic() + 2400)')
nohup python3 "$DRIVER/native_host_control.py" supervise \
  --session "$SESSION" \
  --container "seneca-stage2-$SESSION" \
  --scratch "$ROOT" \
  --snapshot "$ROOT/original-container.json" \
  --done driver_done.json \
  --abort supervisor.abort \
  --ceiling-epoch "$SUPERVISOR_CEILING" \
  --metadata-baseline "$ROOT/baseline-publications.json" \
  --cpuset "$CPUSET" \
  > "$ROOT/supervisor.log" 2>&1 < /dev/null &
echo $! > "$ROOT/supervisor.pid"
sleep 1
kill -0 "$(cat "$ROOT/supervisor.pid")"
python3 "$DRIVER/native_stage2.py" \
  --session "$SESSION" \
  --root "$ROOT" \
  --models /srv/seneca/models \
  --bindings "$ROOT/A/preflight/native-bindings.json" \
  --baseline-snapshot "$ROOT/original-container.json" \
  --stop-epoch "$STOP_EPOCH" \
  --minimum-free-bytes 2147483648
```

The runner enforces the 2,400-second ceiling, 900-second restoration reserve, 2-GiB host-available-memory floor, 2-GiB remaining-disk floor, and 36 sends. Each arm uses an independent writable copy, the model tree is mounted read-only, the app container has no network, four CPUs, and a 6-GiB memory limit with no swap. Native teardown uses the accepted 30-second app shutdown grace; synthetic mode retains its previously qualified accelerated settings.

The watchdog stops/removes only its session-labeled container, restarts the same original container, checks its exact identity/image/mounts/restart policy and both health endpoints, confirms scratch Qdrant has no owner, and reruns metadata preflight. It treats any publication/workspace metadata drift as restoration failure. Preserve all scratch evidence until those checks pass; then archive authorized sanitized evidence before removing the scratch tree.

## Current host disposition

A read-only GCP instance lookup on 2026-11-23 reported:

```text
seneca-review  TERMINATED  us-central1-a
```

No SSH, host preflight, container start, maintenance, data copy, model load, or Stage 2 submission was performed. Host-dependent checks remain unavailable until the intended host is running under separate authority. A terminated VM is not evidence of a failed application or a passed native preflight.
