# OfflineRAG application image (Slice 15G).
# Generative LLM/runtime weights are intentionally NOT installed in this image.

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

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 8080

# Exec form so SIGTERM reaches the ASGI process (D19).
CMD ["python", "-m", "offline_rag.api.server"]
