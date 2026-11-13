#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/workstation/build_container.sh {cpu|cuda}

Builds one immutable local container variant from the exact clean Git HEAD.
This helper never pushes to a registry.
EOF
}

[[ $# -eq 1 ]] || { usage >&2; exit 2; }
case "$1" in
  cpu)
    PROFILE="cpu-release"
    SUFFIX="cpu"
    ;;
  cuda)
    PROFILE="cuda-dev"
    SUFFIX="cuda"
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *) usage >&2; exit 2 ;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
[[ -z "$(git status --porcelain)" ]] || {
  printf 'Build container variants only from a clean committed checkout.\n' >&2
  exit 1
}
SOURCE_SHA="$(git rev-parse HEAD)"
VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
IMAGE="seneca:${VERSION}-${SUFFIX}"

docker build \
  --file deploy/Dockerfile \
  --build-arg "SENECA_DEPENDENCY_PROFILE=$PROFILE" \
  --build-arg "SENECA_SOURCE_SHA=$SOURCE_SHA" \
  --tag "$IMAGE" \
  .

printf 'Built local image: %s\n' "$IMAGE"
printf 'Source SHA: %s\n' "$SOURCE_SHA"
printf 'Dependency profile: %s\n' "$PROFILE"
