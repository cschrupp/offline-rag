#!/usr/bin/env bash
# Read-only metadata inspection or backing validation of an existing scratch copy.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
dir=$PWD/docs/evidence/bge30-length-sorted/stage2-driver
inputs=$PWD/docs/evidence/bge30-length-sorted/stage2-integration
mode=${1:?metadata or isolated}
data=$(realpath -e "${2:?data path}")
models=$(realpath -e "${3:?models path}")
cpuset=${4:?four-CPU set}
stop_epoch=${5:?verified automatic STOP epoch}
[[ $stop_epoch =~ ^[0-9]+$ ]]
(( stop_epoch - $(date +%s) >= 4800 ))
awk '/^MemAvailable:/ {found=1; if ($2 < 2097152) exit 1} END {if (!found) exit 1}' /proc/meminfo
[[ -d "$data" && -d "$models" && "$data" != "$models" ]]
image=seneca-stage2-diagnostic:1f79eca0e30e
digest=sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04
docker image inspect "$image" | python3 -c '
import json,sys
assert json.load(sys.stdin)[0]["Descriptor"]["digest"] == sys.argv[1]
' "$digest"
case "$mode" in
  metadata)
    data_mount="type=bind,src=$data,dst=/data,readonly"
    ;;
  isolated)
    [[ $data == /var/tmp/seneca-stage2-copy.*/data ]]
    active=$(docker ps -q)
    if [[ -n $active ]]; then
        mapfile -t ids <<< "$active"
        docker inspect "${ids[@]}" | python3 -c '
import json, pathlib, sys
target = pathlib.Path(sys.argv[1])
for container in json.load(sys.stdin):
    for mount in container.get("Mounts", []):
        source = pathlib.Path(mount["Source"]).resolve()
        assert not (target.is_relative_to(source) or source.is_relative_to(target))
' "$data"
    fi
    data_mount="type=bind,src=$data,dst=/data"
    ;;
  *) exit 2 ;;
esac
# The caller must provide an exclusively owned scratch copy for isolated mode.
# No container start, stop, restart or image swap for the live service occurs.
timeout -k 5 180 docker run --rm --name "seneca-stage2-preflight-$$" \
  --network none --cpuset-cpus "$cpuset" --memory 6g --memory-swap 6g \
  --mount "$data_mount" \
  --mount "type=bind,src=$models,dst=/models,readonly" \
  --mount "type=bind,src=$dir,dst=/review/driver,readonly" \
  --mount "type=bind,src=$inputs,dst=/review/inputs,readonly" \
  -e SENECA_ISOLATED_COPY=verified -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  --entrypoint timeout "$digest" -k 2 170 python -B /review/driver/preflight.py "$mode" \
  /review/inputs/workloads.json /review/inputs/stage1-bindings.json
