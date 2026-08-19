"""
Structured logging configuration — JSON-formatted, machine-parseable logs
with correlation IDs for end-to-end pipeline tracing (Part 7 requirement).
"""

import sys
import logging
import uuid
from pathlib import Path

import structlog

from config.settings import LOG_LEVEL, LOG_FORMAT, LOG_FILE


def setup_logging(correlation_id: str | None = None) -> structlog.BoundLogger:
    """
    Configure structured logging for the pipeline.

    Args:
        correlation_id: Optional correlation ID for tracing a pipeline run.
                        If not provided, a new UUID is generated.

    Returns:
        A configured structlog BoundLogger instance.
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    # Ensure log directory exists
    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure standard library logging (structlog wraps this)
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
        force=True,
    )

    # Choose renderer based on LOG_FORMAT
    if LOG_FORMAT == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, LOG_LEVEL.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bind the correlation ID to all subsequent log entries
    logger = structlog.get_logger()
    logger = logger.bind(correlation_id=correlation_id)

    return logger
