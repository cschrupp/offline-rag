set -euo pipefail
umask 077
container=seneca-review
revision=9c92e706c4b9e9d9ac0816a655bdf131cc63fca1
deadline=$1
staging=$2
check_time() {
    local current
    current=$(date +%s)
    (( deadline - current > 1800 )) || { echo "STOP deadline has insufficient margin"; return 1; }
}
check_time
prefix=$(mktemp -d /var/tmp/seneca-one-shot.XXXXXXXX)
testname="seneca-measure-${prefix##*.}"
stopping=0
verified=0
signature() {
    docker inspect --format '{{.Id}} {{.Image}} {{.HostConfig.RestartPolicy.Name}} {{.Config.User}} {{range .Mounts}}{{println .Source .Destination .RW}}{{end}}' "$container"
}
healthy() {
    for p in live ready; do
        [[ $(curl -sS --max-time 4 -o /dev/null -w "%{http_code}" "http://127.0.0.1/health/$p" 2>/dev/null) == 200 ]] || return 1
    done
}
probe() {
    timeout 180 docker exec -i "$container" python -B - inspect < "$prefix/probe.py"
}
cleanup() {
    rc=$?
    trap - EXIT
    trap '' HUP INT TERM
    set +e
    if (( stopping )); then
        if docker container inspect "$testname" >/dev/null 2>&1; then
            docker rm -f "$testname" >/dev/null || { echo "RESTORATION BLOCKED: isolated container still present"; exit 1; }
        fi
        docker start "$container" >/dev/null || { echo "RESTORATION FAILED: original start"; exit 1; }
        for ((i=0;i<120;i++)); do
            if healthy; then break; fi
            sleep 5
        done
        if healthy && [[ $(signature) == "$before_signature" ]] &&
           probe > "$prefix/after.json" && cmp -s "$prefix/before.json" "$prefix/after.json"; then
            verified=1
            echo "RESTORATION PASS: live=200 ready=200 original image/mounts/restart policy, workspace revision, snapshot and inventory match"
        else
            echo "RESTORATION NOT VERIFIED; temporary evidence retained at $prefix"
            exit 1
        fi
    fi
    if (( !stopping || verified )); then
        sudo -n rm -rf -- "$prefix"
    fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
cp "$staging/probe.py" "$prefix/probe.py"
chmod 644 "$prefix/probe.py"
cp "$staging/cross_encoder.py" "$prefix/cross_encoder.py"
chmod 644 "$prefix/cross_encoder.py"
[[ $(nproc) == 4 ]]
healthy || { echo "PREFLIGHT FAIL: not healthy"; exit 1; }
before_signature=$(signature)
image=$(docker inspect --format '{{.Image}}' "$container")
[[ $(docker inspect --format '{{.Id}}' "$container") == e006597fd6e4e40939e49c1dd73da7c6d85f33d87d44929c15dc5f0f38bb7cac ]]
[[ $image == sha256:3bc83208a7526a49abed1b9bd9586b5ae4fd041771732e03030c3ac20419e692 ]]
[[ $(docker inspect --format '{{.Config.Image}}' "$container") == seneca-review:9c92e706c4b9 ]]
[[ $(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}} {{index .Config.Labels "io.seneca.dependency-profile"}}' "$image") == "$revision cpu-release" ]]
[[ $(docker inspect --format '{{json .Mounts}}' "$container" | jq -c 'map([.Type,.Source,.Destination,.RW]) | sort') == '[["bind","/srv/seneca/data","/data",true],["bind","/srv/seneca/models","/models",false]]' ]]
[[ $(docker ps -q --filter ancestor="$image" | wc -l) == 1 ]]
[[ $(docker inspect --format '{{.Config.User}} {{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}' "$container") == '10001:10001 0 0' ]]
sudo -n true
data_kib=$(sudo -n du -sk /srv/seneca/data | awk '{print $1}')
disk_kib=$(df -Pk "$prefix" | awk 'NR==2 {print $4}')
ram_kib=$(awk '$1=="MemAvailable:" {print $2}' /proc/meminfo)
total_kib=$(awk '$1=="MemTotal:" {print $2}' /proc/meminfo)
(( disk_kib > 3*data_kib+2*1024*1024 && ram_kib > 8*1024*1024 && total_kib > 15*1024*1024 ))
printf 'Host preflight: data KiB=%s free disk KiB=%s available RAM KiB=%s\n' "$data_kib" "$disk_kib" "$ram_kib"
python3 - "$prefix/runtime.env" <<'PY'
import json, subprocess, sys
from pathlib import Path
c=json.loads(subprocess.check_output(["docker","inspect","seneca-review"]))[0]
env=c["Config"]["Env"]
if any("\r" in line or "\n" in line for line in env):
    raise SystemExit("Unsupported multiline container environment")
Path(sys.argv[1]).write_text("\n".join(env)+"\n")
PY
probe > "$prefix/before.json" || { cat "$prefix/before.json"; exit 1; }
chmod 644 "$prefix/before.json"
cat "$prefix/before.json"
pid=$(docker inspect -f '{{.State.Pid}}' "$container")
for i in 1 2 3; do
    [[ -z $(sudo -n nsenter -t "$pid" -n ss -Htn state established '( sport = :8080 )') ]] ||
        { echo "PREFLIGHT FAIL: active application connection"; exit 1; }
    cpu=$(docker stats --no-stream --format '{{.CPUPerc}}' "$container")
    awk -v v="${cpu%%%}" 'BEGIN {exit !(v+0 < 5)}' || { echo "PREFLIGHT FAIL: application CPU not idle ($cpu)"; exit 1; }
    sleep 2
done
check_time
stopping=1
docker stop -t 45 "$container" >/dev/null
[[ $(docker inspect --format '{{.State.ExitCode}} {{.State.Running}}' "$container") =~ ^(0|143)\ false$ ]] ||
    { echo "Original container did not exit gracefully"; exit 1; }
mkdir "$prefix/data"
sudo -n cp -a --reflink=auto /srv/seneca/data/. "$prefix/data/"
check_time
printf 'Isolated exact-incident batching comparison starting\n'
started=$(date +%s)
set +e
timeout --kill-after=15s 1200 docker run --rm --name "$testname" --network none \
    --env-file "$prefix/runtime.env" \
    --mount "type=bind,src=$prefix/data,dst=/data" \
    --mount type=bind,src=/srv/seneca/models,dst=/models,readonly \
    --mount "type=bind,src=$prefix/probe.py,dst=/diagnostic/probe.py,readonly" \
    --mount "type=bind,src=$prefix/before.json,dst=/diagnostic/before.json,readonly" \
    --mount "type=bind,src=$prefix/cross_encoder.py,dst=/app/.venv/lib/python3.14/site-packages/offline_rag/rerank/cross_encoder.py,readonly" \
    --entrypoint python "$image" -B /diagnostic/probe.py measure \
    2> "$prefix/diagnostic.stderr"
rc=$?
set -e
printf 'Diagnostic container elapsed seconds=%s exit=%s\n' "$(( $(date +%s)-started ))" "$rc"
(( rc == 0 )) || exit "$rc"
if docker container inspect "$testname" >/dev/null 2>&1; then
    echo "Previous isolated container still exists"
    exit 1
fi
exit 0
