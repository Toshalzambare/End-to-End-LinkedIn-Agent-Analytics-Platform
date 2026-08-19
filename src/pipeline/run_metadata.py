"""
Run Metadata Tracker — Persists execution metadata for every pipeline run.
Part 2 requirement: start, end, rows in/out, status.
"""

import uuid
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


class RunMetadataTracker:
    """
    Tracks and persists metadata for a single pipeline execution.

    Recorded fields:
    - run_id (UUID)
    - correlation_id (matches structured log entries)
    - run_type ('full' or 'incremental')
    - status ('running', 'success', 'failed', 'partial')
    - started_at / ended_at
    - rows_extracted / rows_loaded / rows_rejected
    - error_message (if failed)
    - watermark_value (for incremental runs)
    """

    def __init__(self, correlation_id: str, run_type: str = "incremental"):
        self.run_id = str(uuid.uuid4())
        self.correlation_id = correlation_id
        self.run_type = run_type
        self.status = "running"
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.ended_at = None
        self.rows_extracted = 0
        self.rows_loaded = 0
        self.rows_rejected = 0
        self.error_message = None
        self.watermark_value = None

    def increment_extracted(self, count: int = 1) -> None:
        self.rows_extracted += count

    def increment_loaded(self, count: int = 1) -> None:
        self.rows_loaded += count

    def increment_rejected(self, count: int = 1) -> None:
        self.rows_rejected += count

    def mark_success(self, watermark: str | None = None) -> None:
        self.status = "success"
        self.ended_at = datetime.now(timezone.utc).isoformat()
        self.watermark_value = watermark

    def mark_failed(self, error: str) -> None:
        self.status = "failed"
        self.ended_at = datetime.now(timezone.utc).isoformat()
        self.error_message = error

    def mark_partial(self, error: str | None = None) -> None:
        self.status = "partial"
        self.ended_at = datetime.now(timezone.utc).isoformat()
        self.error_message = error

    def persist(self, conn) -> None:
        """
        Write run metadata to the pipeline_run_log table.
        Idempotent: uses INSERT OR REPLACE keyed on run_id.
        """
        conn.execute(
            """
            INSERT OR REPLACE INTO pipeline_run_log
            (run_id, correlation_id, run_type, status, started_at, ended_at,
             rows_extracted, rows_loaded, rows_rejected, error_message, watermark_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                self.correlation_id,
                self.run_type,
                self.status,
                self.started_at,
                self.ended_at,
                self.rows_extracted,
                self.rows_loaded,
                self.rows_rejected,
                self.error_message,
                self.watermark_value,
            )
        )

        logger.info(
            "run_metadata_persisted",
            run_id=self.run_id,
            status=self.status,
            rows_extracted=self.rows_extracted,
            rows_loaded=self.rows_loaded,
            rows_rejected=self.rows_rejected,
        )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "run_type": self.run_type,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "rows_extracted": self.rows_extracted,
            "rows_loaded": self.rows_loaded,
            "rows_rejected": self.rows_rejected,
            "error_message": self.error_message,
            "watermark_value": self.watermark_value,
        }
