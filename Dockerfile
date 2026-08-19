# ==============================================================================
# Dockerfile — LinkedIn Agent Analytics Platform
# Part 7: DevOps, CI/CD, & Observability
# ==============================================================================
# Multi-stage build with pinned dependencies and externalised configuration.
# ==============================================================================

FROM python:3.11-slim AS base

# Metadata
LABEL maintainer="Toshal Zambare"
LABEL description="LinkedIn Agent Analytics Platform — Data Pipeline"
LABEL version="1.0.0"

# Security: run as non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        sqlite3 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies (pinned versions)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config/ ./config/
COPY src/ ./src/
COPY scripts/ ./scripts/

# Create directories for data, logs, and dead letters
RUN mkdir -p /app/data /app/logs /app/dead_letter && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Externalised configuration via environment variables
ENV DATABASE_PATH=/app/data/linkedin_analytics.db
ENV LOG_FILE=/app/logs/pipeline.log
ENV LOG_LEVEL=INFO
ENV LOG_FORMAT=json
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sqlite3; sqlite3.connect('/app/data/linkedin_analytics.db').execute('SELECT 1')" || exit 1

# Default command: run the pipeline
CMD ["python", "scripts/run_pipeline.py", "--run-type", "incremental"]
