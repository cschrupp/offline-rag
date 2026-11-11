#!/usr/bin/env bash
set -euo pipefail

readonly UV_VERSION="0.11.18"
readonly UV_ARCHIVE_SHA256="588f3e360f69ce02b6982aa99f2240e803933a6b7e176ac01617830adf955add"

usage() {
  cat <<'EOF'
Usage: scripts/workstation/install.sh --ollama-model MODEL [--data-dir PATH] [--models-dir PATH]

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

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
HOST_TOOL="$SOURCE_ROOT/scripts/workstation/host.py"
CONFIG_TOOL="$SOURCE_ROOT/scripts/workstation/configure.py"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
DATA_HOME="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().absolute())' "$DATA_HOME")"
CONFIG_HOME="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().absolute())' "$CONFIG_HOME")"
BIN_HOME="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().absolute())' "$BIN_HOME")"
SENECA_ROOT="$DATA_HOME/seneca"
APP_DIR="$SENECA_ROOT/app"
DATA_DIR="${CUSTOM_DATA_DIR:-$SENECA_ROOT/data}"
MODELS_DIR="${CUSTOM_MODELS_DIR:-$SENECA_ROOT/models}"
DATA_DIR="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().absolute())' "$DATA_DIR")"
MODELS_DIR="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().absolute())' "$MODELS_DIR")"
CONFIG_DIR="$CONFIG_HOME/seneca"
ENV_FILE="$CONFIG_DIR/workstation.env"
SERVICE_DIR="$CONFIG_HOME/systemd/user"
SERVICE_FILE="$SERVICE_DIR/seneca.service"
METADATA_FILE="$CONFIG_DIR/installation.json"

python3 "$HOST_TOOL" preflight \
  --app-dir "$APP_DIR" --data-dir "$DATA_DIR" --models-dir "$MODELS_DIR" \
  --ollama-model "$OLLAMA_MODEL" || {
    printf '\nPreflight failed. No Seneca application, data, or model root was changed.\n' >&2
    exit 1
  }

[[ -f "$SOURCE_ROOT/pyproject.toml" && -f "$SOURCE_ROOT/uv.lock" ]] || {
  printf 'Run this installer from a complete Seneca source checkout.\n' >&2
  exit 1
}
if ! git -C "$SOURCE_ROOT" rev-parse --verify HEAD >/dev/null 2>&1 || \
  [[ -n "$(git -C "$SOURCE_ROOT" status --porcelain)" ]]; then
  printf 'Install from a clean, committed Git checkout so the recorded source SHA is accurate.\n' >&2
  exit 1
fi

if [[ ! -d "$SOURCE_ROOT/ui/dist" || ! -f "$SOURCE_ROOT/ui/dist/index.html" ]]; then
  command -v node >/dev/null 2>&1 || {
    printf 'Node.js 22 is required because this checkout has no compiled ui/dist.\n' >&2
    exit 1
  }
  command -v npm >/dev/null 2>&1 || { printf 'npm is required to build the UI.\n' >&2; exit 1; }
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
  [[ "$NODE_MAJOR" == "22" ]] || {
    printf 'UI build requires Node.js 22; found %s.\n' "$(node --version)" >&2
    exit 1
  }
fi

TARGET="$(python3 -c 'import platform; r=platform.release().lower(); print("wsl2" if "microsoft" in r else "linux")')"
case "$(uname -m)" in
  x86_64|amd64) ;;
  *) printf 'Unsupported architecture: %s\n' "$(uname -m)" >&2; exit 1 ;;
esac

mkdir -p "$SENECA_ROOT" "$DATA_DIR" "$MODELS_DIR" "$CONFIG_DIR" "$SERVICE_DIR" "$BIN_HOME"
chmod 700 "$CONFIG_DIR"

UV_BIN=""
if command -v uv >/dev/null 2>&1 && [[ "$(uv --version)" == "uv $UV_VERSION" ]]; then
  UV_BIN="$(command -v uv)"
else
  UV_DIR="$SENECA_ROOT/tools/uv/$UV_VERSION"
  UV_BIN="$UV_DIR/bin/uv"
  if [[ ! -x "$UV_BIN" ]]; then
    UV_STAGE="$(mktemp -d "$SENECA_ROOT/.uv-install.XXXXXX")"
    trap 'rm -rf -- "${UV_STAGE:-}" "${STAGE:-}"' EXIT
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
STAGE="$SENECA_ROOT/.app-staging.$STAMP.$$"
BACKUP="$SENECA_ROOT/app.previous.$STAMP.$$"
mkdir -m 0700 "$STAGE"
trap 'rm -rf -- "${STAGE:-}"' EXIT

cp "$SOURCE_ROOT/pyproject.toml" "$SOURCE_ROOT/uv.lock" "$SOURCE_ROOT/README.md" "$STAGE/"
cp -a "$SOURCE_ROOT/src" "$SOURCE_ROOT/config" "$STAGE/"
mkdir -p "$STAGE/scripts"
cp "$SOURCE_ROOT/scripts/provision_docling.py" "$SOURCE_ROOT/scripts/provision_tiktoken.py" "$STAGE/scripts/"
cp -a "$SOURCE_ROOT/scripts/workstation" "$STAGE/scripts/"

if [[ -d "$SOURCE_ROOT/ui/dist" && -f "$SOURCE_ROOT/ui/dist/index.html" ]]; then
  mkdir -p "$STAGE/ui"
  cp -a "$SOURCE_ROOT/ui/dist/." "$STAGE/ui/"
else
  command -v node >/dev/null 2>&1 || { printf 'Node.js 22 is required to build the UI.\n' >&2; exit 1; }
  command -v npm >/dev/null 2>&1 || { printf 'npm is required to build the UI.\n' >&2; exit 1; }
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
  [[ "$NODE_MAJOR" == "22" ]] || { printf 'UI build requires Node.js 22; found %s.\n' "$(node --version)" >&2; exit 1; }
  cp -a "$SOURCE_ROOT/ui" "$STAGE/ui"
  rm -rf "$STAGE/ui/node_modules" "$STAGE/ui/dist"
  (cd "$STAGE/ui" && npm ci && npm run build)
fi
[[ -f "$STAGE/ui/index.html" ]] || { printf 'Compiled UI is missing index.html.\n' >&2; exit 1; }

"$UV_BIN" python install 3.14
"$UV_BIN" sync --project "$STAGE" --locked --no-dev --extra cpu-release --no-editable --python 3.14
rm -rf -- "$STAGE/src"

STAGED_PYTHON="$STAGE/.venv/bin/python"
STAGED_CLI="$STAGE/.venv/bin/offline-rag"
[[ -x "$STAGED_PYTHON" && -x "$STAGED_CLI" ]] || { printf 'Staged Python environment or CLI is missing.\n' >&2; exit 1; }
"$STAGED_PYTHON" - <<'PY'
import offline_rag
from pathlib import Path

module_path = Path(offline_rag.__file__).resolve()
if "/src/" in str(module_path):
    raise SystemExit(f"application unexpectedly imports from source checkout: {module_path}")
print(f"Installed package import: {module_path}")
PY
"$STAGED_CLI" --help >/dev/null
[[ ! -e "$STAGE/src" ]] || {
  printf 'The staged runtime must not retain the application source tree.\n' >&2
  exit 1
}

if [[ -e "$APP_DIR" ]]; then
  mv -- "$APP_DIR" "$BACKUP"
fi
if ! mv -- "$STAGE" "$APP_DIR"; then
  [[ ! -e "$BACKUP" ]] || mv -- "$BACKUP" "$APP_DIR"
  printf 'Could not promote validated staged app; previous install restored.\n' >&2
  exit 1
fi
STAGE=""

rollback_app() {
  if [[ -e "$BACKUP" ]]; then
    rm -rf -- "$APP_DIR"
    mv -- "$BACKUP" "$APP_DIR"
  fi
}
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
metadata_args=(write-metadata --path "$METADATA_FILE" --source-root "$SOURCE_ROOT" \
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

install -m 0755 "$SOURCE_ROOT/scripts/workstation/seneca" "$BIN_HOME/seneca"
systemctl --user daemon-reload
systemctl --user enable seneca.service
printf 'Seneca workstation package installed. Start it with: %s/seneca start\n' "$BIN_HOME"
printf 'The app, data, and models are at %s, %s, and %s. Data and models were preserved.\n' \
  "$APP_DIR" "$DATA_DIR" "$MODELS_DIR"
if [[ -e "$BACKUP" ]]; then
  printf 'Previous application retained at %s\n' "$BACKUP"
fi
