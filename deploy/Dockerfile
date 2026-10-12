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

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
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

# Explicit inputs only — local data/, models/, .git, .env must stay out of context.
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY config /app/config
COPY --from=ui-builder /ui/dist /app/ui

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Optional build_ca secret assists pip TLS only for this RUN. Bundle is written
# under /tmp and removed before the layer commits; system trust store is untouched.
RUN --mount=type=secret,id=build_ca,required=false \
    set -eu; \
    if [ -f /run/secrets/build_ca ]; then \
      cat /etc/ssl/certs/ca-certificates.crt /run/secrets/build_ca \
        > /tmp/offlinerag-build-ca-bundle.pem; \
      export SSL_CERT_FILE=/tmp/offlinerag-build-ca-bundle.pem; \
      export REQUESTS_CA_BUNDLE=/tmp/offlinerag-build-ca-bundle.pem; \
      export CURL_CA_BUNDLE=/tmp/offlinerag-build-ca-bundle.pem; \
      export PIP_CERT=/tmp/offlinerag-build-ca-bundle.pem; \
    fi; \
    pip install --no-cache-dir --upgrade pip; \
    pip install --no-cache-dir .; \
    rm -f /tmp/offlinerag-build-ca-bundle.pem; \
    # Prove no custom CA files were installed into the runtime trust store path.
    ! ls /usr/local/share/ca-certificates/*.crt >/dev/null 2>&1; \
    chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 8080

# Exec form so SIGTERM reaches the ASGI process (D19).
CMD ["python", "-m", "offline_rag.api.server"]
