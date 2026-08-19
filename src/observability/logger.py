"""
Structured Logger — JSON-formatted, machine-parseable logging with correlation IDs.
Part 7: DevOps, CI/CD, & Observability.

Wraps structlog for consistent log output across the entire pipeline.
"""

import structlog
from config.logging_config import setup_logging


def get_logger(correlation_id: str | None = None, **bindings) -> structlog.BoundLogger:
    """
    Get a configured structured logger with optional bindings.

    Args:
        correlation_id: Pipeline run correlation ID.
        **bindings: Additional key-value pairs to bind to every log entry.

    Returns:
        Configured structlog BoundLogger.
    """
    logger = setup_logging(correlation_id)
    if bindings:
        logger = logger.bind(**bindings)
    return logger
