# syntax=docker/dockerfile:1.7
# OfflineRAG application image (Slice 15G + 16C frontend).
# Generative LLM/runtime weights are intentionally NOT installed in this image.
#
# Optional TLS-intercepted build hosts may pass a BuildKit secret:
#   docker build --secret id=build_ca,src=/path/to/extra-ca.pem ...
# The secret is mount-only for dependency fetch RUNs. It MUST NOT be COPY'd
# into the image and MUST NOT persist in the final runtime trust store.

FROM node:22-bookworm-slim AS ui-builder

WORKDIR /ui

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY ui/package.json ui/package-lock.json ./
# Optional build_ca secret extends Node trust for this RUN only.
RUN --mount=type=secret,id=build_ca,required=false \
    if [ -f /run/secrets/build_ca ]; then \
      export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; \
    fi \
    && npm ci

COPY ui/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.18 AS uv-bin

FROM python:3.14-slim AS python-base

FROM python-base AS python-builder

ARG SENECA_DEPENDENCY_PROFILE=cpu-release
ARG SENECA_SOURCE_SHA=unknown

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src
COPY config /app/config

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Optional build_ca secret assists uv package fetches for this RUN only.
RUN --mount=type=secret,id=build_ca,required=false \
    --mount=from=uv-bin,source=/uv,target=/usr/local/bin/uv,ro \
    set -eu; \
    case "$SENECA_DEPENDENCY_PROFILE" in cpu-release|cuda-dev) ;; *) \
      echo "unsupported dependency profile" >&2; exit 2 ;; esac; \
    if [ -f /run/secrets/build_ca ]; then \
      cat /etc/ssl/certs/ca-certificates.crt /run/secrets/build_ca \
        > /tmp/offlinerag-build-ca-bundle.pem; \
      export SSL_CERT_FILE=/tmp/offlinerag-build-ca-bundle.pem; \
      export REQUESTS_CA_BUNDLE=/tmp/offlinerag-build-ca-bundle.pem; \
      export CURL_CA_BUNDLE=/tmp/offlinerag-build-ca-bundle.pem; \
    fi; \
    uv sync --locked --no-dev --extra "$SENECA_DEPENDENCY_PROFILE" --no-editable --no-cache; \
    rm -f /tmp/offlinerag-build-ca-bundle.pem; \
    ! ls /usr/local/share/ca-certificates/*.crt >/dev/null 2>&1

FROM python-base AS runtime

ARG SENECA_DEPENDENCY_PROFILE=cpu-release
ARG SENECA_SOURCE_SHA=unknown

LABEL org.opencontainers.image.revision="$SENECA_SOURCE_SHA" \
      io.seneca.dependency-profile="$SENECA_DEPENDENCY_PROFILE"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    OFFLINE_RAG_CONFIG=/app/config/base.yaml \
    OFFLINE_RAG_DATA_DIR=/data \
    OFFLINE_RAG_MODELS_DIR=/models \
    OFFLINE_RAG_STRICT_OFFLINE=true \
    OFFLINE_RAG_HTTP_HOST=0.0.0.0 \
    OFFLINE_RAG_HTTP_PORT=8080 \
    OFFLINE_RAG_ALLOW_NON_LOOPBACK=true \
    OFFLINE_RAG_SHUTDOWN_GRACE_SECONDS=30 \
    OFFLINE_RAG_UI_DIR=/app/ui \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

RUN groupadd --gid 10001 offlinerag \
    && useradd --uid 10001 --gid 10001 --create-home \
        --home-dir /home/offlinerag --shell /usr/sbin/nologin offlinerag \
    && mkdir -p /data /models \
    && chown 10001:10001 /data /models

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=python-builder --chown=10001:10001 /app/.venv /app/.venv
COPY --from=python-builder --chown=10001:10001 /app/config /app/config
COPY --from=ui-builder --chown=10001:10001 /ui/dist /app/ui

USER 10001:10001

EXPOSE 8080

# Exec form so SIGTERM reaches the ASGI process (D19).
CMD ["python", "-m", "offline_rag.api.server"]
