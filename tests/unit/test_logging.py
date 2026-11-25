"""Local structured logging tests."""

from __future__ import annotations

import json
import logging
from io import StringIO

from offline_rag.observability.logging import (
    HumanFormatter,
    StructuredFormatter,
    configure_logging,
    log_event,
)


def test_structured_log_record_emitted_locally() -> None:
    stream = StringIO()
    logger = logging.getLogger("offline_rag.test_logging")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)

    log_event(
        logger,
        logging.INFO,
        "hello",
        event="test.event",
        trace_id="trace_1",
        experiment_id="cfg_1",
        metrics={"candidate_count": 10, "latency_ms": 12},
    )

    payload = json.loads(stream.getvalue().strip())
    assert payload["event"] == "test.event"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "offline_rag.test_logging"
    assert payload["trace_id"] == "trace_1"
    assert payload["experiment_id"] == "cfg_1"
    assert payload["metrics"] == {"candidate_count": 10, "latency_ms": 12}
    assert "timestamp" in payload


def test_configure_logging_returns_named_logger() -> None:
    logger = configure_logging(
        level="WARNING", structured=False, logger_name="offline_rag.test_cfg"
    )
    assert logger.name == "offline_rag.test_cfg"
    assert logger.level == logging.WARNING


def test_human_log_formatter_includes_metrics() -> None:
    stream = StringIO()
    logger = logging.getLogger("offline_rag.test_human_metrics")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(stream)
    handler.setFormatter(HumanFormatter())
    logger.addHandler(handler)
    log_event(
        logger,
        logging.INFO,
        "reranking complete",
        event="reranker_completed",
        metrics={"candidate_count": 10},
    )
    assert 'metrics={"candidate_count": 10}' in stream.getvalue()
