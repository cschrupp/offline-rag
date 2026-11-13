"""Static contracts for the shared CPU/CUDA container build path."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_uses_one_runtime_path_with_locked_profile_argument() -> None:
    dockerfile = (ROOT / "deploy/Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.count("FROM python-base AS python-builder") == 1
    assert dockerfile.count("FROM python-base AS runtime") == 1
    assert "ARG SENECA_DEPENDENCY_PROFILE=cpu-release" in dockerfile
    assert 'case "$SENECA_DEPENDENCY_PROFILE" in cpu-release|cuda-dev' in dockerfile
    assert (
        'uv sync --locked --no-dev --extra "$SENECA_DEPENDENCY_PROFILE"' in dockerfile
    )
    assert 'org.opencontainers.image.revision="$SENECA_SOURCE_SHA"' in dockerfile
    assert 'io.seneca.dependency-profile="$SENECA_DEPENDENCY_PROFILE"' in dockerfile
    assert 'if [ "$SENECA_DEPENDENCY_PROFILE" = cuda-dev ]; then' in dockerfile
    assert "apt-get install -y --no-install-recommends gcc" in dockerfile
    assert dockerfile.count("COPY --from=ui-builder") == 1
    assert 'CMD ["python", "-m", "offline_rag.api.server"]' in dockerfile


def test_local_container_builder_selects_only_dependency_profile_and_never_pushes() -> (
    None
):
    builder = (ROOT / "scripts/workstation/build_container.sh").read_text(
        encoding="utf-8"
    )
    assert 'PROFILE="cpu-release"' in builder
    assert 'PROFILE="cuda-dev"' in builder
    assert 'IMAGE="seneca:${VERSION}-${SUFFIX}"' in builder
    assert "SENECA_SOURCE_SHA=$SOURCE_SHA" in builder
    assert "docker push" not in builder
    assert "git status --porcelain" in builder
