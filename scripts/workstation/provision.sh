#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/workstation/provision.sh --onnx-source DIRECTORY

Explicitly provisions Seneca's local Docling, tokenizer, CPU embedding, and
reranker artifacts. The ONNX source must be the already-qualified local bundle;
this script does not build or convert model representations.
EOF
}

ONNX_SOURCE=""
while (($#)); do
  case "$1" in
    --onnx-source)
      (($# >= 2)) || { usage >&2; exit 2; }
      ONNX_SOURCE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ -n "$ONNX_SOURCE" && -d "$ONNX_SOURCE" && -r "$ONNX_SOURCE" ]] || {
  printf 'Provide a readable directory containing the already-qualified ONNX bundle.\n' >&2
  exit 2
}

APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/seneca/app"
ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/seneca/workstation.env"
[[ -x "$APP_DIR/.venv/bin/offline-rag" && -r "$ENV_FILE" ]] || {
  printf 'Install Seneca first with scripts/workstation/install.sh.\n' >&2
  exit 1
}
CONFIG_TOOL="$APP_DIR/scripts/workstation/configure.py"
MODELS_DIR="$("$APP_DIR/.venv/bin/python" "$CONFIG_TOOL" read-root --path "$ENV_FILE" --name models)"

run_provision() {
  local label="$1"
  shift
  printf '\n== %s ==\n' "$label"
  "$APP_DIR/.venv/bin/python" "$CONFIG_TOOL" \
    exec-env --path "$ENV_FILE" --set HF_HUB_OFFLINE=0 \
    --set TRANSFORMERS_OFFLINE=0 -- "$@"
}

run_provision "Docling parser artifacts" \
  "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/provision_docling.py" \
  --output "$MODELS_DIR/docling"
run_provision "tiktoken cl100k_base cache" \
  "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/provision_tiktoken.py" \
  --output "$MODELS_DIR/tokenizers/tiktoken"
run_provision "qualified CPU ONNX embedding representation" \
  "$APP_DIR/.venv/bin/offline-rag" provision embedding \
  --config "$APP_DIR/config/base.yaml" \
  --representation onnx_fp32_v1 --onnx-source "$ONNX_SOURCE"
run_provision "pinned BGE reranker" \
  "$APP_DIR/.venv/bin/offline-rag" provision reranker \
  --config "$APP_DIR/config/base.yaml"

printf '\nProvisioned artifacts passed their existing provisioning checks.\n'
printf 'Start Seneca once with `seneca start` so ApplicationRuntime creates durable data paths.\n'
printf 'After startup, run `seneca doctor` for read-only installation diagnostics.\n'
printf 'Runtime remains strict-offline.\n'
