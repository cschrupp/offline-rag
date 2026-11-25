"""Lightweight local logging helpers.

Uses the standard library only. Supports human-readable console output and
structured JSON records. No cloud telemetry.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "message": record.getMessage(),
        }
        for key in ("trace_id", "experiment_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        metrics = getattr(record, "metrics", None)
        if isinstance(metrics, dict):
            payload["metrics"] = metrics
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", None)
        prefix = f"{record.levelname} {record.name}"
        metrics = getattr(record, "metrics", None)
        metric_suffix = (
            f" metrics={json.dumps(metrics, sort_keys=True, default=str)}"
            if isinstance(metrics, dict)
            else ""
        )
        if event:
            return f"{prefix} event={event} {record.getMessage()}{metric_suffix}"
        return f"{prefix} {record.getMessage()}{metric_suffix}"


def configure_logging(
    *,
    level: str = "INFO",
    structured: bool = True,
    logger_name: str = "offline_rag",
) -> logging.Logger:
    """Configure and return the package logger.

    Safe to call multiple times; existing handlers on the named logger are replaced.
    """
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(StructuredFormatter() if structured else HumanFormatter())
    logger.addHandler(handler)
    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    event: str,
    trace_id: str | None = None,
    experiment_id: str | None = None,
    **extra: Any,
) -> None:
    """Emit a log record with standard OfflineRAG context fields."""
    payload = {"event": event}
    if trace_id is not None:
        payload["trace_id"] = trace_id
    if experiment_id is not None:
        payload["experiment_id"] = experiment_id
    payload.update(extra)
    logger.log(level, message, extra=payload)
