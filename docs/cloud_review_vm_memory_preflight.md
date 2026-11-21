# Google Cloud review VM memory preflight

On 2026-11-20 at 23:48:16 UTC, the global Linux OOM killer terminated the
Seneca Python server (UID 10001, approximately 7.3 GiB anonymous RSS) on
`seneca-review` in `us-central1-a`. The `e2-standard-2` host had 2 vCPUs,
8 GiB RAM, and no swap. Ingestion stopped at `building_indexes`. Recovery
reported `recovered_A` and preserved the previous published snapshot.
This establishes host memory exhaustion. The cause of the workload's
memory demand was not independently diagnosed.

An 8 GiB `/swapfile-seneca` was activated and its fstab entry verified.
Post-reboot persistence remains unverified. A later small PDF ingestion
succeeded. Larger workloads remain unqualified on the 8 GiB host.
The proposed `e2-standard-4` resize (4 vCPUs, 16 GiB RAM) is planned.
Verify the actual machine type rather than inferring completion.

## Read-only preflight

From a shell with Google Cloud access, select the intended project and inspect
the configured cost control and disks:

```bash
gcloud compute instances describe seneca-review --zone=us-central1-a \
  --format='yaml(name,zone,machineType,scheduling,resourcePolicies,disks)'
```

Verify the effective automatic runtime limit is two hours and its action is
**STOP**, with the instance and persistent disks retained. If a separate
policy enforces it, verify that policy as well. A nightly stop schedule alone
does not enforce a two-hour session limit. Before a planned stop or resize,
pause new work, inspect the operation tray and server activity, and wait
for active ingestion and queries to finish. Do not begin ingestion when it
cannot reasonably finish within the remaining review window.

On the VM, enter a workload-specific minimum for **remaining** free disk
space in GiB. For routine startup and ingestion, budget for source bytes,
staging, index growth, and operating headroom. For an image rebuild, also
budget for BuildKit intermediates, the new image, and retained rollback
images on Docker's filesystem. Run the preflight again with the rebuild
budget before building. The review VM was reported to have about 16 GiB
free after swap was allocated. Check current space with `df`; a RAM resize
does not itself expand the boot disk. For a first deployment, pass `host-only` after the disk minimum
and run the full check once the container exists. Separately review `MemAvailable` against the specific workload and
other host processes. The physical RAM floor allows for kernel reservations
on the nominal 16 GiB machine.

```bash
read -r -p 'Minimum remaining disk headroom for this operation (GiB): ' seneca_disk_gib &&
bash -s -- "$seneca_disk_gib" <<'BASH'
set -euo pipefail
fail() { printf 'PREFLIGHT FAIL: %s\n' "$*" >&2; exit 1; }
[[ ${1:-} =~ ^[1-9][0-9]*$ ]] || fail "Pass remaining disk headroom in GiB"
gib=$((1024 * 1024))
swapfile=/swapfile-seneca
metadata() {
  curl -fsS --max-time 5 -H 'Metadata-Flavor: Google' \
    "http://metadata.google.internal/computeMetadata/v1/instance/$1"
}
name=$(metadata name) || fail "Cannot read GCE instance name"
zone=$(metadata zone) || fail "Cannot read GCE zone"
machine=$(metadata machine-type) || fail "Cannot read GCE machine type"
[[ $name == seneca-review && ${zone##*/} == us-central1-a ]] ||
  fail "Unexpected instance or zone"
[[ ${machine##*/} == e2-standard-4 ]] || fail "Expected e2-standard-4"
ram=$(awk '$1 == "MemTotal:" {print $2}' /proc/meminfo)
(( ram >= 15 * gib )) || fail "Expected nominal 16 GiB physical RAM"
free -h

active=$(awk -v file="$swapfile" '$1 == file {print $3}' /proc/swaps)
# An 8 GiB swap file reserves a header page, so usable capacity is slightly less.
page_kib=$(( $(getconf PAGESIZE) / 1024 ))
[[ $active =~ ^[0-9]+$ ]] && (( active >= 8 * gib - page_kib )) ||
  fail "$swapfile is missing, inactive, or below the 8 GiB swap-file requirement"
[[ $(sudo stat -c '%u:%a' "$swapfile") == 0:600 ]] ||
  fail "Swap file must be owned by root and mode 0600"
sudo awk -v file="$swapfile" '
  $1 == file { count++; if ($2 == "none" && $3 == "swap" && $4 == "sw" &&
    $5 == "0" && $6 == "0") valid++ }
  END { exit !(count == 1 && valid == 1) }
' /etc/fstab || fail "Expected exactly one persistent swap entry"

docker_root=$(docker info --format '{{.DockerRootDir}}') ||
  fail "Cannot read Docker storage root"
for path in / "$docker_root" /srv/seneca/data /srv/seneca/models; do
  [[ -d $path ]] || fail "Missing directory $path"
  available=$(df -Pk -- "$path" | awk 'NR == 2 { print $4 }')
  (( available >= $1 * gib )) || fail "Insufficient free disk for $path"
done
df -h / "$docker_root" /srv/seneca/data /srv/seneca/models
systemctl is-enabled --quiet docker || fail "Docker is not enabled at boot"
if docker container inspect seneca-review >/dev/null 2>&1; then
  [[ $(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' seneca-review) == unless-stopped ]] ||
    fail "Expected container restart policy unless-stopped"
  mounts=$(docker inspect -f '{{range .Mounts}}{{println .Source .Destination .RW}}{{end}}' seneca-review)
  printf '%s\n' "$mounts"
  grep -Fxq "/srv/seneca/data /data true" <<< "$mounts" &&
    grep -Fxq "/srv/seneca/models /models false" <<< "$mounts" ||
    fail "Expected persistent read-write data and read-only models mounts"
elif [[ ${2:-} != host-only ]]; then
  fail "Cannot inspect seneca-review. Before its first deployment, set the documented mounts and restart policy, then repeat this check before ingestion."
else
  printf "Container checks pending until after first deployment.\n"
fi
printf 'Host checks passed. Review live memory headroom, workload disk needs, and the GCE STOP policy before ingestion.\n'
BASH
```

Repeat after a controlled reboot and after any machine-type change. A correct
fstab entry is configuration evidence. An active swap entry after reboot
establishes persistence. Keep both persistent mounts in place across
container replacement, restart, or resize.

## Provision swap on a new review VM

Plan a maintenance window. Review existing mechanisms with `swapon --show`,
`lsblk -f`, and the swap entries in `/etc/fstab`. If another mechanism is
configured or active, investigate it before adding another. Use these
commands on a compatible **ext4** root filesystem with sufficient space.
Other filesystems may need a different swap procedure. Enter the minimum disk space your workload needs after swap allocation.
Provisioning checks for that headroom plus 8 GiB for the swap file. The script preserves an existing
active target and refuses to overwrite an inactive file.

```bash
read -r -p 'Minimum remaining disk headroom after swap (GiB): ' seneca_disk_gib &&
sudo bash -s -- "$seneca_disk_gib" <<'BASH'
set -euo pipefail
fail() { printf 'SWAP SETUP FAIL: %s\n' "$*" >&2; exit 1; }
[[ ${1:-} =~ ^[1-9][0-9]*$ ]] || fail "Pass remaining disk headroom in GiB"
file=/swapfile-seneca
entry="$file none swap sw 0 0"
gib=$((1024 * 1024))
count=$(awk -v file="$file" '$1 == file {n++} END {print n+0}' /etc/fstab)
if (( count > 0 )); then
  awk -v file="$file" '
    $1 == file { n++; if ($2 == "none" && $3 == "swap" && $4 == "sw" &&
      $5 == "0" && $6 == "0") good++ }
    END { exit !(n == 1 && good == 1) }
  ' /etc/fstab || fail "Existing target entry is duplicated or unexpected"
fi
awk -v file="$file" '
  $1 !~ /^#/ && $3 == "swap" && $1 != file { other=1 }
  END { exit other }
' /etc/fstab || fail "Another swap mechanism is configured"
awk -v file="$file" 'NR > 1 && $1 != file { other=1 } END { exit other }' /proc/swaps ||
  fail "Another swap mechanism is active"
active=$(awk -v file="$file" '$1 == file {print $3}' /proc/swaps)
if [[ -z $active ]]; then
  [[ ! -e $file && ! -L $file ]] || fail "Existing inactive target requires inspection"
  [[ $(findmnt -n -o FSTYPE --target /) == ext4 ]] || fail "Expected ext4"
  available=$(df -Pk / | awk 'NR == 2 { print $4 }')
  (( available >= (8 + $1) * gib )) || fail "Insufficient free root filesystem space"
  umask 077
  temp=$(mktemp /swapfile-seneca.new.XXXXXXXX)
  trap 'rm -f -- "$temp"' EXIT
  dd if=/dev/zero of="$temp" bs=1M count=8192 status=progress conv=fsync
  chmod 0600 "$temp"
  mkswap "$temp"
  mv -nT -- "$temp" "$file"
  [[ ! -e $temp ]] || fail "Target appeared during provisioning"
  swapon "$file"
fi
[[ $(stat -c '%u:%a' "$file") == 0:600 ]] || fail "Expected root-owned mode 0600"
active=$(awk -v file="$file" '$1 == file {print $3}' /proc/swaps)
[[ $active =~ ^[0-9]+$ ]] &&
  (( active >= 8 * gib - $(getconf PAGESIZE) / 1024 )) ||
  fail "Active swap capacity is below the 8 GiB swap-file requirement"
if (( count == 0 )); then
  backup=$(mktemp /etc/fstab.seneca.XXXXXXXX)
  cp -p -- /etc/fstab "$backup"
  printf '\n%s\n' "$entry" >> /etc/fstab
  printf 'fstab backup: %s\n' "$backup"
fi
findmnt --verify
swapon --show
free -h
BASH
```

Run one provisioning session at a time. If activation fails and leaves an
inactive file, inspect it before retrying. After the next approved reboot,
run the preflight and confirm active swap before substantial ingestion.
