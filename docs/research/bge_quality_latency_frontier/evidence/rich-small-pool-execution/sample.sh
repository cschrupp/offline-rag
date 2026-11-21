#!/usr/bin/env bash
# Passive host sampler, run only during the isolated diagnostic.
set -euo pipefail
echo "ticks=$(getconf CLK_TCK)"
seen=0
for ((i=0;i<480;i++)); do
  name=$(docker ps --format '{{.Names}}' | awk '/^seneca-measure-/ {print; exit}')
  if [[ -n "$name" ]]; then
    pid=$(docker inspect -f '{{.State.Pid}}' "$name" 2>/dev/null) || break
    [[ -r /proc/$pid/stat ]] || break
    seen=1
    row=$(awk '{printf "user_jiffies=%s system_jiffies=%s", $14,$15}' "/proc/$pid/stat") || break
    rss=$(awk '/^VmRSS:/ {print $2}' "/proc/$pid/status") || break
    [[ -n "$rss" ]] || break
    printf '%s %s rss_kib=%s ' "$(date -u +%FT%T.%NZ)" "$row" "$rss"
    awk '/^cpu / {printf "host_jiffies="; for(i=2;i<=9;i++) printf "%s%s",$i,(i==9?" ":",")}' /proc/stat
    awk '/^MemAvailable:/ {a=$2} /^SwapFree:/ {s=$2} END {printf "MemAvailable_kib=%s SwapFree_kib=%s\n",a,s}' /proc/meminfo
  elif (( seen )); then
    break
  fi
  sleep 4
done
