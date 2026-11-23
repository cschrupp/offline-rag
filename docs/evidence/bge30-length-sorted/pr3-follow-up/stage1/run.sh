set -euo pipefail
umask 077
cd "$1"
prefix=$PWD
deadline=$2
name=seneca-pr3-stage1
container=seneca-review
image=sha256:3bc83208a7526a49abed1b9bd9586b5ae4fd041771732e03030c3ac20419e692
stopping=0
monitor_pid=
signature() {
    docker inspect --format '{{.Id}} {{.Image}} {{json .HostConfig.RestartPolicy}} {{.Config.User}} {{range .Mounts}}{{println .Source .Destination .RW}}{{end}}' "$container"
}
healthy() {
    for path in live ready; do
        [[ $(curl -sS --max-time 4 -o /dev/null -w "%{http_code}" "http://REDACTED_REVIEW_HOST/health/$path") == 200 ]] || return 1
    done
}
inspect() {
    timeout 180 docker exec -i "$container" python -B - inspect < probe.py
}
remaining() {
    (( deadline - $(date +%s) >= $1 ))
}
cleanup() {
    rc=$?
    trap - EXIT
    trap '' HUP TERM INT
    set +e
    if [[ -n $monitor_pid ]]; then kill "$monitor_pid" 2>/dev/null; wait "$monitor_pid" 2>/dev/null; fi
    if (( stopping )); then
        docker container inspect "$name" >/dev/null 2>&1 && {
            docker kill "$name" >/dev/null 2>&1
            docker container rm "$name" >/dev/null || { echo "Diagnostic removal failed"; exit 1; }
        }
        docker start "$container" >/dev/null || { echo "RESTORATION START FAILED"; exit 1; }
        end=$(( $(date +%s) + 580 ))
        until healthy; do
            (( $(date +%s) < end )) || { echo "RESTORATION HEALTH FAILED"; exit 1; }
            sleep 5
        done
        if [[ $(signature) == "$before_signature" ]] &&
           [[ $(docker inspect -f '{{.State.Running}}' "$container") == true ]] &&
           ! docker container inspect "$name" >/dev/null 2>&1 &&
           inspect > after.json && cmp -s before.json after.json; then
            echo "RESTORATION PASS: original container running, live=200 ready=200, original image/mounts/restart policy, both workspace revisions/snapshots/source inventories/publication pointers unchanged; diagnostic removed"
            sudo -n python3 -c 'import shutil; shutil.rmtree("data")'
            [[ $? == 0 ]] || { echo "Isolated data cleanup failed"; exit 1; }
        else
            echo "RESTORATION NOT VERIFIED; isolated evidence retained"; exit 1
        fi
    fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
remaining 3600
[[ $(nproc) == 4 ]]
healthy
[[ $(docker ps --format '{{.Names}}') == "$container" ]]
! docker container inspect "$name" >/dev/null 2>&1
before_signature=$(signature)
[[ $(docker inspect -f '{{.Image}} {{.Config.Image}} {{.Config.User}} {{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}' "$container") == "$image seneca-review:9c92e706c4b9 10001:10001 0 0" ]]
[[ $(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}} {{index .Config.Labels "io.seneca.dependency-profile"}}' "$image") == "9c92e706c4b9e9d9ac0816a655bdf131cc63fca1 cpu-release" ]]
[[ $(docker inspect --format '{{json .Mounts}}' "$container" | jq -c 'map([.Type,.Source,.Destination,.RW]) | sort') == '[["bind","/srv/seneca/data","/data",true],["bind","/srv/seneca/models","/models",false]]' ]]
sudo -n true
sha256sum --check --status files.sha256
data_kib=$(sudo -n du -sk /srv/seneca/data | awk '{print $1}')
free_kib=$(df -Pk "$prefix" | awk 'NR==2 {print $4}')
mem_kib=$(awk '$1=="MemAvailable:" {print $2}' /proc/meminfo)
(( free_kib > 2*data_kib+2097152 && mem_kib >= 8388608 ))
printf 'PREFLIGHT resource safety: CPUs=4 data_KiB=%s disk_free_KiB=%s host_available_KiB=%s STOP_epoch=%s\n' "$data_kib" "$free_kib" "$mem_kib" "$deadline"
inspect > before.json
chmod 644 before.json probe.py
pid=$(docker inspect -f '{{.State.Pid}}' "$container")
for i in 1 2 3; do
    [[ -z $(sudo -n nsenter -t "$pid" -n ss -Htn state established '( sport = :8080 )') ]]
    cpu=$(docker stats --no-stream --format '{{.CPUPerc}}' "$container")
    awk -v p="${cpu%%%}" 'BEGIN {exit !(p+0 < 5)}'
    sleep 2
done
healthy
remaining 3600
printf 'PREFLIGHT PASS live=200 ready=200 idle deadline_remaining_s=%s\n' "$((deadline-$(date +%s)))"
stopping=1
docker stop -t 45 "$container" >/dev/null
[[ $(docker inspect --format '{{.State.ExitCode}} {{.State.Running}}' "$container") =~ ^(0|143)\ false$ ]]
mkdir data
sudo -n cp -a --reflink=auto /srv/seneca/data/. data/
remaining 3300
mounts=()
while IFS= read -r path; do
    mounts+=(--mount "type=bind,src=$prefix/$path,dst=/app/.venv/lib/python3.14/site-packages/${path#src/},readonly")
done < files.txt
# Retain the original effective environment but never print it or export it off-host.
# Network isolation prevents any provider or model-download traffic.
python3 - <<'PY'
import json, subprocess
from pathlib import Path
env = json.loads(subprocess.check_output(["docker","inspect","seneca-review"]))[0]["Config"]["Env"]
if any("\r" in line or "\n" in line for line in env):
    raise SystemExit("Unsupported multiline environment")
Path("runtime.env").write_text("\n".join(env)+"\n")
PY
docker run --detach --name "$name" --network none --memory 6g --memory-swap 6g \
    --env-file runtime.env -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
    --mount "type=bind,src=$prefix/data,dst=/data" \
    --mount type=bind,src=/srv/seneca/models,dst=/models,readonly \
    --mount "type=bind,src=$prefix/probe.py,dst=/diagnostic/probe.py,readonly" \
    --mount "type=bind,src=$prefix/before.json,dst=/diagnostic/before.json,readonly" \
    "${mounts[@]}" --entrypoint timeout "$image" --signal=KILL 2400 python -B /diagnostic/probe.py measure >/dev/null
unlink runtime.env
(
    while [[ $(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null) == true ]]; do
        available=$(awk '$1=="MemAvailable:" {print $2}' /proc/meminfo)
        printf '%s %s ' "$(date +%s)" "$available"
        awk '/^cpu / {print $0}' /proc/stat
        if (( available < 2097152 )); then
            echo "HOST MEMORY FLOOR BREACHED"
            docker kill "$name" >/dev/null 2>&1
            exit 1
        fi
        sleep 1
    done
) > samples.log &
monitor_pid=$!
exit_code=$(docker wait "$name")
docker logs "$name" > measurements.jsonl 2> diagnostic.stderr
printf 'Diagnostic exit code=%s\n' "$exit_code"
[[ $exit_code == 0 ]]
