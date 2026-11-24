#!/usr/bin/env bash
# Read-only metadata inspection or backing validation of an existing scratch copy.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
dir=$PWD/docs/evidence/bge30-length-sorted/stage2-driver
inputs=$PWD/docs/evidence/bge30-length-sorted/stage2-integration
mode=${1:?metadata, isolated, native, native-smoke, rich2-metadata or rich2-stage1}
data=$(realpath -e "${2:?data path}")
models=$(realpath -e "${3:?models path}")
cpuset=${4:?four-CPU set}
IFS=, read -r -a cpu_ids <<< "$cpuset"
[[ ${#cpu_ids[@]} -eq 4 ]]
[[ $(printf '%s\n' "${cpu_ids[@]}" | sort -u | wc -l) -eq 4 ]]
[[ $models == /srv/seneca/models ]]
extra_mounts=()
extra_args=()
if [[ $mode == isolated || $mode == native || $mode == native-smoke || $mode == rich2-stage1 ]]; then
    stop_epoch=${5:?verified automatic STOP epoch}
    [[ $stop_epoch =~ ^[0-9]+$ ]]
    case $mode in
        native)
            minimum_stop_remaining=$(PYTHONPATH="$dir" python3 -c 'from stage2_timing import MINIMUM_POST_PREPARATION_WINDOW_SECONDS; print(MINIMUM_POST_PREPARATION_WINDOW_SECONDS)')
            ;;
        native-smoke)
            minimum_stop_remaining=900
            ;;
        *)
            minimum_stop_remaining=4800
            ;;
    esac
    (( stop_epoch - $(date +%s) >= minimum_stop_remaining ))
    if [[ $mode == native || $mode == native-smoke ]]; then
        output=$(realpath -e "${6:?native binding output directory}")
        [[ -d $output && -z $(find "$output" -mindepth 1 -maxdepth 1 -print -quit) ]]
        [[ $(stat -c '%a' "$output") == 777 ]]
        [[ $data == /var/tmp/seneca-stage2-native-*/A/data || $data == /var/tmp/seneca-stage2-native-*/B/data ]]
        python3 "$dir/native_host_control.py" check-qdrant "$data/qdrant"
        extra_mounts=(--mount "type=bind,src=$output,dst=/review/output")
        extra_args=(/review/output/native-bindings.json)
    fi
elif [[ $mode != metadata && $mode != rich2-metadata && $mode != native-metadata ]]; then
    printf 'mode must be metadata, isolated, native, native-smoke, rich2-metadata or rich2-stage1\n' >&2
    exit 2
fi
if [[ $mode == native-metadata && $# -ge 5 ]]; then
    stop_epoch=$5
    [[ $stop_epoch =~ ^[0-9]+$ ]]
    minimum_stop_remaining=$(PYTHONPATH="$dir" python3 -c 'from stage2_timing import MINIMUM_MAINTENANCE_ENTRY_WINDOW_SECONDS; print(MINIMUM_MAINTENANCE_ENTRY_WINDOW_SECONDS)')
    (( stop_epoch - $(date +%s) >= minimum_stop_remaining ))
fi
awk '/^MemAvailable:/ {found=1; if ($2 < 2097152) exit 1} END {if (!found) exit 1}' /proc/meminfo
[[ -d "$data" && -d "$models" && "$data" != "$models" ]]
image=seneca-rich2-local:1f79eca0
digest=sha256:59252d0655267001c4c9ac42e5a2045131b4086bb1ab84e10dbfd98f2e831dee
docker image inspect "$image" | python3 -c '
import json,sys
assert json.load(sys.stdin)[0]["Descriptor"]["digest"] == sys.argv[1]
' "$digest"
case "$mode" in
  metadata|rich2-metadata|native-metadata)
    [[ $data == /srv/seneca/data ]]
    data_mount="type=bind,src=$data,dst=/data,readonly"
    ;;
  isolated|native|native-smoke)
    if [[ $mode == isolated ]]; then
      [[ $data == /var/tmp/seneca-stage2-copy.*/data ]]
    fi
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
  rich2-stage1)
    [[ $data == /var/tmp/seneca-rich2-stage1-*/data ]]
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
    python3 "$dir/native_host_control.py" check-qdrant "$data/qdrant"
    data_mount="type=bind,src=$data,dst=/data"
    ;;
  *) exit 2 ;;
esac
# The caller must provide an exclusively owned scratch copy for isolated mode.
# No container start, stop, restart or image swap for the live service occurs.
preflight_mode=$mode
workloads="$inputs/workloads.json"
if [[ $mode == native || $mode == native-smoke || $mode == native-metadata ]]; then
  workloads="$inputs/workloads-rich2.json"
fi
timeout -k 5 180 docker run --rm --name "seneca-stage2-preflight-$$" \
  --network none --cpuset-cpus "$cpuset" --memory 6g --memory-swap 6g \
  --mount "$data_mount" \
  --mount "type=bind,src=$models,dst=/models,readonly" \
  --mount "type=bind,src=$dir,dst=/review/driver,readonly" \
  --mount "type=bind,src=$inputs,dst=/review/inputs,readonly" \
  "${extra_mounts[@]}" \
  -e SENECA_ISOLATED_COPY=verified -e OFFLINE_RAG_CONFIG=/app/config/base.yaml \
  -e OFFLINE_RAG_DATA_DIR=/data -e OFFLINE_RAG_MODELS_DIR=/models \
  -e OFFLINE_RAG_STRICT_OFFLINE=true -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  --entrypoint timeout "$digest" -k 2 170 python -B /review/driver/preflight.py "$preflight_mode" \
  "/review/inputs/$(basename "$workloads")" /review/inputs/stage1-bindings.json \
  "${extra_args[@]}"
