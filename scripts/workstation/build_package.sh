#!/usr/bin/env bash
set -euo pipefail

readonly UV_VERSION="0.11.18"
readonly REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

[[ -z "$(git status --porcelain)" ]] || {
  printf 'Build packages only from a clean committed checkout.\n' >&2
  exit 1
}
SOURCE_SHA="$(git rev-parse HEAD)"
VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$NODE_MAJOR" == "22" ]] || { printf 'Node.js 22 is required.\n' >&2; exit 1; }
for command in npm tar sha256sum; do
  command -v "$command" >/dev/null || { printf 'Missing required builder command: %s\n' "$command" >&2; exit 1; }
done

SHORT_SHA="${SOURCE_SHA:0:12}"
NAME="seneca-workstation-${VERSION}-linux-x86_64-${SHORT_SHA}"
OUTPUT="$REPO_ROOT/dist/workstation"
BUILD="$(mktemp -d)"
trap 'rm -rf -- "$BUILD"' EXIT
ROOT="$BUILD/$NAME"
mkdir -p "$ROOT/payload" "$OUTPUT"
mkdir -p "$BUILD/source"

git archive "$SOURCE_SHA" | tar -x -C "$BUILD/source"
SOURCE="$BUILD/source"
(cd "$SOURCE/ui" && npm ci && npm run build)
cp "$SOURCE/pyproject.toml" "$SOURCE/uv.lock" "$SOURCE/README.md" "$ROOT/payload/"
cp -a "$SOURCE/src" "$SOURCE/config" "$ROOT/payload/"
mkdir -p "$ROOT/payload/ui" "$ROOT/payload/scripts/workstation"
cp -a "$SOURCE/ui/dist/." "$ROOT/payload/ui/"
cp "$SOURCE/scripts/provision_docling.py" "$SOURCE/scripts/provision_tiktoken.py" "$ROOT/payload/scripts/"
cp "$SOURCE/scripts/workstation/configure.py" "$SOURCE/scripts/workstation/host.py" \
  "$SOURCE/scripts/workstation/provision.sh" "$SOURCE/scripts/workstation/runtime.py" \
  "$SOURCE/scripts/workstation/seneca" \
  "$ROOT/payload/scripts/workstation/"
cp "$SOURCE/scripts/workstation/install.sh" "$ROOT/install.sh"
chmod 0755 "$ROOT/install.sh" "$ROOT/payload/scripts/workstation/"*.sh "$ROOT/payload/scripts/workstation/seneca"

python3 - "$ROOT/RELEASE.json" "$VERSION" "$SOURCE_SHA" <<'PY'
import json
import sys
from pathlib import Path

path, version, source_sha = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
path.write_text(json.dumps({
    "schema_version": 1,
    "product": "Seneca",
    "project": "offline-rag",
    "project_version": version,
    "source_sha": source_sha,
    "target": "linux-x86_64",
    "python": "3.14",
    "uv_version": "0.11.18",
    "dependency_profile": "cpu-release",
    "ui_source_sha": source_sha,
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
(cd "$ROOT" && find install.sh RELEASE.json payload -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
ARCHIVE="$OUTPUT/$NAME.tar.gz"
tar -czf "$ARCHIVE" -C "$BUILD" "$NAME"
(cd "$OUTPUT" && sha256sum "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256")
printf 'Package: %s\n' "$ARCHIVE"
printf 'SHA-256: %s\n' "$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
