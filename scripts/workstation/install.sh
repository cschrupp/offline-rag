#!/usr/bin/env bash
set -euo pipefail

readonly UV_VERSION="0.11.18"
readonly UV_ARCHIVE_SHA256="588f3e360f69ce02b6982aa99f2240e803933a6b7e176ac01617830adf955add"

usage() {
  cat <<'EOF'
Usage: ./install.sh --ollama-model MODEL [--data-dir PATH] [--models-dir PATH]

Installs the locked CPU workstation application on Linux x86-64 or WSL2.
The selected model must already be present in the local Ollama instance.
EOF
}

OLLAMA_MODEL=""
CUSTOM_DATA_DIR=""
CUSTOM_MODELS_DIR=""
while (($#)); do
  case "$1" in
    --ollama-model)
      (($# >= 2)) || { usage >&2; exit 2; }
      OLLAMA_MODEL="$2"
      shift 2
      ;;
    --data-dir)
      (($# >= 2)) || { usage >&2; exit 2; }
      CUSTOM_DATA_DIR="$2"
      shift 2
      ;;
    --models-dir)
      (($# >= 2)) || { usage >&2; exit 2; }
      CUSTOM_MODELS_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done
[[ -n "$OLLAMA_MODEL" ]] || { usage >&2; exit 2; }

PACKAGE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PAYLOAD="$PACKAGE_ROOT/payload"
RELEASE_JSON="$PACKAGE_ROOT/RELEASE.json"
HOST_TOOL="$PAYLOAD/scripts/workstation/host.py"
CONFIG_TOOL="$PAYLOAD/scripts/workstation/configure.py"

[[ -f "$RELEASE_JSON" && -f "$PACKAGE_ROOT/SHA256SUMS" ]] || {
  printf 'This installer must run from a complete workstation package.\n' >&2
  exit 1
}
if ! python3 - "$PACKAGE_ROOT" <<'PY'
import os
import re
import sys
from pathlib import Path, PurePosixPath

root = Path(sys.argv[1])
manifest = root / "SHA256SUMS"
install_script = root / "install.sh"
release_json = root / "RELEASE.json"
payload = root / "payload"
expected_root_entries = {"install.sh", "RELEASE.json", "SHA256SUMS", "payload"}


def invalid_package() -> None:
    raise SystemExit("package file set does not match SHA256SUMS")


if manifest.is_symlink() or not manifest.is_file():
    invalid_package()
if {entry.name for entry in root.iterdir()} != expected_root_entries:
    invalid_package()
if install_script.is_symlink() or not install_script.is_file():
    invalid_package()
if release_json.is_symlink() or not release_json.is_file():
    invalid_package()
if payload.is_symlink() or not payload.is_dir():
    invalid_package()

# The manifest must close the extracted tree, not just hash the entries it lists.
expected: set[str] = set()
line_pattern = re.compile(r"^[0-9a-f]{64}  (.+)$")
try:
    lines = manifest.read_text(encoding="utf-8").splitlines()
except (OSError, UnicodeError):
    invalid_package()

for line in lines:
    match = line_pattern.fullmatch(line)
    if match is None:
        invalid_package()
    relative_name = match.group(1)
    relative_path = PurePosixPath(relative_name)
    if (
        "\\" in relative_name
        or relative_path.is_absolute()
        or ".." in relative_path.parts
        or relative_path.as_posix() != relative_name
        or not (
            relative_name in {"install.sh", "RELEASE.json"}
            or relative_name.startswith("payload/")
        )
        or relative_name in expected
    ):
        invalid_package()
    expected.add(relative_name)

if not {"install.sh", "RELEASE.json"}.issubset(expected):
    invalid_package()
if not any(name.startswith("payload/") for name in expected):
    invalid_package()

actual = {"install.sh", "RELEASE.json"}
expected_directories = {"payload"}
for name in expected:
    parts = PurePosixPath(name).parts
    for index in range(1, len(parts)):
        directory = "/".join(parts[:index])
        if directory == "payload" or directory.startswith("payload/"):
            expected_directories.add(directory)

actual_directories = {"payload"}
for current, directories, files in os.walk(payload, followlinks=False):
    current_path = Path(current)
    for name in directories:
        path = current_path / name
        if path.is_symlink() or not path.is_dir():
            invalid_package()
        actual_directories.add(path.relative_to(root).as_posix())
    for name in files:
        path = current_path / name
        if path.is_symlink() or not path.is_file():
            invalid_package()
        actual.add(path.relative_to(root).as_posix())

if actual != expected or actual_directories != expected_directories:
    invalid_package()
PY
then
  printf 'Package integrity verification failed; no installation state was changed.\n' >&2
  exit 1
fi
(cd "$PACKAGE_ROOT" && sha256sum --check --status SHA256SUMS) || {
  printf 'Package integrity verification failed; no installation state was changed.\n' >&2
  exit 1
}
python3 - "$RELEASE_JSON" <<'PY'
import json
import re
import sys
from pathlib import Path

release = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
required = {
    "schema_version": 1,
    "product": "Seneca",
    "project": "offline-rag",
    "target": "linux-x86_64",
    "python": "3.14",
    "uv_version": "0.11.18",
    "dependency_profile": "cpu-release",
}
if any(release.get(key) != value for key, value in required.items()):
    raise SystemExit("Unsupported or invalid workstation release metadata")
if not re.fullmatch(r"[0-9a-f]{40}", str(release.get("source_sha", ""))):
    raise SystemExit("Invalid package source SHA")
if release.get("ui_source_sha") != release.get("source_sha"):
    raise SystemExit("UI and package source identities differ")
if not isinstance(release.get("project_version"), str) or not release["project_version"]:
    raise SystemExit("Missing project version")
PY

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
DATA_HOME="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().absolute())' "$DATA_HOME")"
CONFIG_HOME="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().absolute())' "$CONFIG_HOME")"
BIN_HOME="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().absolute())' "$BIN_HOME")"
SENECA_ROOT="$DATA_HOME/seneca"
APP_DIR="$SENECA_ROOT/app"
RELEASES_DIR="$SENECA_ROOT/releases"
DATA_DIR="${CUSTOM_DATA_DIR:-$SENECA_ROOT/data}"
MODELS_DIR="${CUSTOM_MODELS_DIR:-$SENECA_ROOT/models}"
DATA_DIR="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().absolute())' "$DATA_DIR")"
MODELS_DIR="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().absolute())' "$MODELS_DIR")"
CONFIG_DIR="$CONFIG_HOME/seneca"
ENV_FILE="$CONFIG_DIR/workstation.env"
SERVICE_DIR="$CONFIG_HOME/systemd/user"
SERVICE_FILE="$SERVICE_DIR/seneca.service"
METADATA_FILE="$CONFIG_DIR/installation.json"
UV_STAGE=""
RELEASE_DIR=""
PROMOTED=0

cleanup() {
  [[ -z "$UV_STAGE" ]] || rm -rf -- "$UV_STAGE"
  if [[ -n "$RELEASE_DIR" && "$PROMOTED" == 0 ]]; then
    rm -rf -- "$RELEASE_DIR"
  fi
}
trap cleanup EXIT

python3 "$HOST_TOOL" preflight \
  --app-dir "$APP_DIR" --data-dir "$DATA_DIR" --models-dir "$MODELS_DIR" \
  --ollama-model "$OLLAMA_MODEL" || {
    printf '\nPreflight failed. No Seneca application, data, or model root was changed.\n' >&2
    exit 1
  }

[[ -f "$PAYLOAD/pyproject.toml" && -f "$PAYLOAD/uv.lock" && -d "$PAYLOAD/ui" ]] || {
  printf 'Release package is missing required application inputs.\n' >&2
  exit 1
}
SOURCE_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_sha"])' "$RELEASE_JSON")"

TARGET="$(python3 -c 'import platform; r=platform.release().lower(); print("wsl2" if "microsoft" in r else "linux")')"
case "$(uname -m)" in
  x86_64|amd64) ;;
  *) printf 'Unsupported architecture: %s\n' "$(uname -m)" >&2; exit 1 ;;
esac

mkdir -p "$SENECA_ROOT" "$RELEASES_DIR" "$DATA_DIR" "$MODELS_DIR" "$CONFIG_DIR" "$SERVICE_DIR" "$BIN_HOME"
chmod 700 "$CONFIG_DIR"

if [[ -L "$APP_DIR" && ! -e "$APP_DIR" ]]; then
  printf 'The installed app link is broken; repair it before reinstalling.\n' >&2
  exit 1
fi
if [[ -e "$APP_DIR" && ! -L "$APP_DIR" && ! -d "$APP_DIR" ]]; then
  printf 'The installed app path is not a directory or release link.\n' >&2
  exit 1
fi

UV_BIN=""
if command -v uv >/dev/null 2>&1 && [[ "$(uv --version)" == "uv $UV_VERSION" ]]; then
  UV_BIN="$(command -v uv)"
else
  UV_DIR="$SENECA_ROOT/tools/uv/$UV_VERSION"
  UV_BIN="$UV_DIR/bin/uv"
  if [[ ! -x "$UV_BIN" ]]; then
    UV_STAGE="$(mktemp -d "$SENECA_ROOT/.uv-install.XXXXXX")"
    curl --fail --location --silent --show-error \
      "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz" \
      --output "$UV_STAGE/uv.tar.gz"
    printf '%s  %s\n' "$UV_ARCHIVE_SHA256" "$UV_STAGE/uv.tar.gz" | sha256sum --check --status || {
      printf 'Downloaded uv archive failed its pinned SHA-256 check.\n' >&2
      exit 1
    }
    tar -xzf "$UV_STAGE/uv.tar.gz" -C "$UV_STAGE"
    install -D -m 0755 "$UV_STAGE/uv-x86_64-unknown-linux-gnu/uv" "$UV_BIN"
    rm -rf -- "$UV_STAGE"
    UV_STAGE=""
  fi
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE_DIR="$(mktemp -d "$RELEASES_DIR/$SOURCE_SHA-$STAMP-$$.XXXXXX")"
LEGACY_BACKUP="$SENECA_ROOT/app.legacy.$STAMP.$$"

cp "$PAYLOAD/pyproject.toml" "$PAYLOAD/uv.lock" "$PAYLOAD/README.md" "$RELEASE_DIR/"
cp -a "$PAYLOAD/src" "$PAYLOAD/config" "$PAYLOAD/ui" "$RELEASE_DIR/"
cp -a "$PAYLOAD/scripts" "$RELEASE_DIR/"

"$UV_BIN" python install 3.14
UV_PROJECT_ENVIRONMENT="$RELEASE_DIR/.venv" "$UV_BIN" sync --project "$RELEASE_DIR" \
  --locked --no-dev --extra cpu-release --no-editable --python 3.14
rm -rf -- "$RELEASE_DIR/src"

RELEASE_PYTHON="$RELEASE_DIR/.venv/bin/python"
RELEASE_CLI="$RELEASE_DIR/.venv/bin/offline-rag"
[[ -x "$RELEASE_PYTHON" && -x "$RELEASE_CLI" ]] || { printf 'Release Python environment or CLI is missing.\n' >&2; exit 1; }
"$RELEASE_PYTHON" - <<'PY'
import offline_rag
from pathlib import Path

module_path = Path(offline_rag.__file__).resolve()
if "/src/" in str(module_path):
    raise SystemExit(f"application unexpectedly imports from source checkout: {module_path}")
print(f"Installed package import: {module_path}")
PY
"$RELEASE_CLI" --help >/dev/null
[[ ! -e "$RELEASE_DIR/src" ]] || {
  printf 'The staged runtime must not retain the application source tree.\n' >&2
  exit 1
}

PREVIOUS_APP_KIND="none"
PREVIOUS_RELEASE=""
if [[ -L "$APP_DIR" ]]; then
  PREVIOUS_APP_KIND="release-link"
  PREVIOUS_RELEASE="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve(strict=True))' "$APP_DIR")"
  python3 - "$PREVIOUS_RELEASE" "$RELEASES_DIR" <<'PY'
from pathlib import Path
import sys

release = Path(sys.argv[1]).resolve(strict=True)
releases_root = Path(sys.argv[2]).resolve(strict=True)
if releases_root not in release.parents:
    raise SystemExit("the current app link is not backed by a managed release")
PY
elif [[ -d "$APP_DIR" ]]; then
  PREVIOUS_APP_KIND="legacy-directory"
  mv -- "$APP_DIR" "$LEGACY_BACKUP"
fi

if ! python3 "$CONFIG_TOOL" activate-release --app-link "$APP_DIR" --release-dir "$RELEASE_DIR"; then
  if [[ "$PREVIOUS_APP_KIND" == "legacy-directory" ]]; then
    mv -- "$LEGACY_BACKUP" "$APP_DIR"
  fi
  printf 'Could not atomically activate the validated app release.\n' >&2
  exit 1
fi
PROMOTED=1

rollback_app() {
  case "$PREVIOUS_APP_KIND" in
    release-link)
      if ! python3 "$CONFIG_TOOL" activate-release --app-link "$APP_DIR" \
        --release-dir "$PREVIOUS_RELEASE"; then
        printf 'Could not restore the previous app release; retaining both releases.\n' >&2
        return 1
      fi
      ;;
    legacy-directory)
      if ! rm -f -- "$APP_DIR" || ! mv -- "$LEGACY_BACKUP" "$APP_DIR"; then
        printf 'Could not restore the previous app directory; retaining the new release.\n' >&2
        return 1
      fi
      ;;
    none)
      if ! rm -f -- "$APP_DIR"; then
        printf 'Could not remove the failed app link; retaining the new release.\n' >&2
        return 1
      fi
      ;;
  esac
  PROMOTED=0
}

# Exercise the exact final-path entrypoint after the symlink is active. The
# venv was created in its immutable release directory and was never moved.
if ! "$APP_DIR/.venv/bin/offline-rag" --help >/dev/null || \
  ! "$APP_DIR/.venv/bin/python" -c 'import offline_rag; print(offline_rag.__file__)'; then
  rollback_app
  printf 'Post-activation package/CLI smoke failed; previous app restored.\n' >&2
  exit 1
fi

if ! python3 "$CONFIG_TOOL" write-env --path "$ENV_FILE" --app-dir "$APP_DIR" \
  --data-dir "$DATA_DIR" --models-dir "$MODELS_DIR" --model "$OLLAMA_MODEL"; then
  rollback_app
  exit 1
fi
if ! python3 "$CONFIG_TOOL" write-service --path "$SERVICE_FILE" \
  --app-dir "$APP_DIR" --env-file "$ENV_FILE"; then
  rollback_app
  exit 1
fi

MEM_TOTAL=""
MEM_AVAILABLE=""
if [[ "$TARGET" == wsl2 ]]; then
  read -r MEM_TOTAL MEM_AVAILABLE < <(python3 - <<'PY'
from pathlib import Path
values = {}
for line in Path('/proc/meminfo').read_text().splitlines():
    key, _, rest = line.partition(':')
    if key in {'MemTotal', 'MemAvailable'}:
        values[key] = int(rest.split()[0]) * 1024
print(values.get('MemTotal', ''), values.get('MemAvailable', ''))
PY
  )
  if [[ -z "$MEM_TOTAL" || -z "$MEM_AVAILABLE" ]]; then
    rollback_app
    printf 'Could not record WSL-visible memory.\n' >&2
    exit 1
  fi
fi
metadata_args=(write-metadata --path "$METADATA_FILE" --source-sha "$SOURCE_SHA" \
  --project-version "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["project_version"])' "$RELEASE_JSON")" \
  --package-identity "$(basename "$PACKAGE_ROOT")" --release-json "$RELEASE_JSON" \
  --target "$TARGET" --app-dir "$APP_DIR" --data-dir "$DATA_DIR" \
  --models-dir "$MODELS_DIR" --ui-dir "$APP_DIR/ui" --uv-path "$UV_BIN" \
  --model "$OLLAMA_MODEL")
if [[ "$TARGET" == wsl2 ]]; then
  metadata_args+=(--mem-total "$MEM_TOTAL" --mem-available "$MEM_AVAILABLE")
fi
if ! python3 "$CONFIG_TOOL" "${metadata_args[@]}"; then
  rollback_app
  exit 1
fi

if ! install -m 0755 "$PAYLOAD/scripts/workstation/seneca" "$BIN_HOME/seneca"; then
  rollback_app
  printf 'Could not install the Seneca command wrapper; previous app restored.\n' >&2
  exit 1
fi
if ! systemctl --user daemon-reload || ! systemctl --user enable seneca.service; then
  rollback_app
  printf 'Could not enable the user service; previous app restored.\n' >&2
  exit 1
fi
printf 'Seneca workstation package installed. Start it with: %s/seneca start\n' "$BIN_HOME"
printf 'The app, data, and models are at %s, %s, and %s. Data and models were preserved.\n' \
  "$APP_DIR" "$DATA_DIR" "$MODELS_DIR"
if [[ "$PREVIOUS_APP_KIND" == "legacy-directory" ]]; then
  printf 'Previous directory-format app retained at %s\n' "$LEGACY_BACKUP"
elif [[ "$PREVIOUS_APP_KIND" == "release-link" ]]; then
  printf 'Previous release retained at %s\n' "$PREVIOUS_RELEASE"
fi
