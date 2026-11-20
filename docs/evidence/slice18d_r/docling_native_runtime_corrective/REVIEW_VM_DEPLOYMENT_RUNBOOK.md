# Review VM cutover

Run these commands as the VM operator after independent review. The original
review runbook used direct Docker on port 80, with /srv/seneca/data and
/srv/seneca/models bind-mounted. Inspect the running container for current
settings before using that layout. Use public-safe test material.

## Inventory and protected rollback record

```bash
umask 077
snapshot=$(mktemp -d "$HOME/seneca-review-rollback.XXXXXXXX")
docker inspect seneca-review > "$snapshot/container.json"
docker inspect --format 'Image={{.Image}} Ref={{.Config.Image}} User={{.Config.User}} Restart={{json .HostConfig.RestartPolicy}} Network={{.HostConfig.NetworkMode}} Ports={{json .HostConfig.PortBindings}} ExtraHosts={{json .HostConfig.ExtraHosts}}' seneca-review
docker inspect --format '{{range .Mounts}}{{println .Type .Name .Source .Destination .RW}}{{end}}' seneca-review
docker image inspect "$(docker inspect --format '{{.Image}}' seneca-review)" --format 'Revision={{index .Config.Labels "org.opencontainers.image.revision"}} Profile={{index .Config.Labels "io.seneca.dependency-profile"}}'
systemctl is-enabled docker
```

Prefer the existing secured deployment env file after confirming it matches
the running container. Otherwise run the following to save the effective
container environment locally and report presence only. Never share, cat, or
commit either protected file. Disable shell tracing before operator work.

```bash
set +x
python3 - "$snapshot" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
config = json.loads((root / "container.json").read_text())[0]["Config"]
entries = config["Env"]
if any("\n" in entry or "\r" in entry for entry in entries):
    raise SystemExit("Multiline environment value. Use the original deployment configuration.")
env = dict(entry.split("=", 1) for entry in entries)
for name, value in sorted(env.items()):
    if name.startswith("OFFLINE_RAG_") and any(
        word in name for word in ("PROFILE", "API_KEY", "MODEL")
    ):
        print(name, "present" if value else "empty")
(root / "runtime.env").write_text("\n".join(entries) + "\n")
PY
```

Privately compare the effective provider and selected model with the running
Settings UI. Preserve the original mounts, restart policy, port bindings,
network mode, extra hosts, user and any additional live overrides. The
commands below assume the inventoried direct Docker topology matches the
original review runbook. If it differs, reproduce the observed options before
cutover, including any additional volumes or alternate network. Keep the old
container and image, including its manually patched writable layer.

## Build and qualify before stopping the service

Run from the VM's Seneca checkout. Use the technical commit accepted in review.

```bash
set -e
git fetch origin corrective/18d-r-docling-native-runtime
sha=c5a973955f20ea29abe473ffe9ae816946eb26ad
git merge-base --is-ancestor "$sha" FETCH_HEAD
git switch --detach "$sha"
tag="seneca-review:${sha:0:12}"
docker build -f deploy/Dockerfile --build-arg SENECA_DEPENDENCY_PROFILE=cpu-release --build-arg SENECA_SOURCE_SHA="$sha" -t "$tag" .
python3 scripts/verify_docling_runtime.py "$tag" "$sha" \
  --models /srv/seneca/models \
  --pdf tests/fixtures/ingestion/pdf/born_digital_reference.pdf
```

Proceed only after image contract, linkage, imports and real conversion pass.

## Cutover and rollback

Pause reviewer traffic. Check the UI operation tray and operator logs for
active ingestion or query requests. Wait for all work to finish. Record the
existing workspace and source counts privately. Use the same persistent
storage. Do not start the two application containers against it together.

```bash
set -e
test -s "$snapshot/runtime.env"
test "$(docker inspect --format '{{.Id}}' seneca-review)" = "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[0]["Id"])' "$snapshot/container.json")"
if docker container inspect seneca-review-rollback >/dev/null 2>&1; then
  echo "Rollback container name already exists. Resolve before cutover." >&2
  exit 1
fi
docker stop --time 60 seneca-review
docker rename seneca-review seneca-review-rollback
docker create --name seneca-review --restart unless-stopped \
  --add-host=host.docker.internal:host-gateway -p 80:8080 \
  --mount type=bind,src=/srv/seneca/data,dst=/data \
  --mount type=bind,src=/srv/seneca/models,dst=/models,readonly \
  --env-file "$snapshot/runtime.env" "$tag"
docker start seneca-review
curl --fail http://127.0.0.1/health/live
curl --fail --retry 12 --retry-delay 5 http://127.0.0.1/health/ready
curl --fail --output /dev/null http://127.0.0.1/workspaces
docker inspect --format 'Restart={{.HostConfig.RestartPolicy.Name}} {{range .Mounts}}{{println .Destination .RW}}{{end}}' seneca-review
systemctl is-enabled docker
```

Compare workspace and source visibility with the pre-cutover inventory.
Confirm the live Settings UI shows the expected provider and approved model
and indicates credentials are configured. Upload a public-safe PDF, wait for
ingestion to succeed, then ask a grounded question and inspect its supporting
source. Use the Feijoada recipe if available and appropriate. The enabled
Docker daemon and the inspected restart policy establish boot configuration.
An actual daemon restart or VM reboot requires separate operator scheduling.

If rollback is needed after the new container was created, stop it if
running and retain it under a diagnostic name. If creation failed and the
name is free, skip those two commands.

```bash
docker stop --time 60 seneca-review
docker rename seneca-review seneca-review-failed
docker rename seneca-review-rollback seneca-review
docker start seneca-review
curl --fail --retry 12 --retry-delay 5 http://127.0.0.1/health/ready
```

Recheck the workspace/source inventory. Keep the protected snapshot under
operator control for the rollback window.
