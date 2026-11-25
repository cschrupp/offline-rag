#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
evidence=docs/evidence/bge30-length-sorted/stage2-integration
source_sha=1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e
base=seneca-review:9c92e706c4b9
expected=sha256:8d45e633fac9b82a833a59117064c074759e317563a0bdb0cca87179986ee9a1
[[ $(docker image inspect --format '{{.Id}}' "$base") == "$expected" ]]
scratch=$(mktemp -d)
trap 'python3 -c "import shutil, sys; shutil.rmtree(sys.argv[1])" "$scratch"' EXIT
git archive "$source_sha" src/offline_rag | tar -xf - -C "$scratch"
cp "$evidence/provider_fixture.py" "$scratch/provider_fixture.py"
cp "$evidence/Dockerfile.diagnostic" "$scratch/Dockerfile"
docker build --network none --pull=false \
    --build-arg BASE_IMAGE="$base" --build-arg INTEGRATED_SHA="$source_sha" \
    --tag seneca-stage2-diagnostic:1f79eca0e30e "$scratch"
docker image inspect --format '{{.Id}} {{json .RepoDigests}}' seneca-stage2-diagnostic:1f79eca0e30e
