"""
Dead Letter Queue — Captures failed records for investigation and retry.
Part 2 requirement: dead-letter capture for failed records.
"""

import json
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


class DeadLetterQueue:
    """
    Routes failed records to the dead_letter_queue table for later investigation.

    Each failed record captures:
    - The full record payload (as JSON)
    - Error type classification (validation, transformation, load, api)
    - Error message
    - Timestamp
    - Link back to the pipeline run
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def send(
        self,
        conn,
        run_id: str,
        record: dict,
        error_type: str,
        error_message: str,
    ) -> None:
        """
        Send a failed record to the dead-letter queue.

        Args:
            conn: Active database connection.
            run_id: The pipeline run ID that produced this failure.
            record: The original record that failed processing.
            error_type: Classification of the error:
                        'validation', 'transformation', 'load', 'api'
            error_message: Human-readable error description.
        """
        try:
            payload = json.dumps(record, default=str)
        except (TypeError, ValueError):
            payload = str(record)

        conn.execute(
            """
            INSERT INTO dead_letter_queue
            (run_id, record_payload, error_type, error_message, failed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                payload,
                error_type,
                error_message,
                datetime.now(timezone.utc).isoformat(),
            )
        )

        logger.warning(
            "dead_letter_queued",
            run_id=run_id,
            error_type=error_type,
            error_message=error_message[:200],
        )

    @staticmethod
    def get_unretried(conn, limit: int = 100) -> list[dict]:
        """
        Fetch unretried dead-letter records for investigation or retry.

        Returns:
            List of dead-letter records as dicts.
        """
        cursor = conn.execute(
            """
            SELECT dlq_id, run_id, record_payload, error_type, error_message, failed_at
            FROM dead_letter_queue
            WHERE retried = 0
            ORDER BY failed_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def mark_retried(conn, dlq_id: int) -> None:
        """Mark a dead-letter record as successfully retried."""
        conn.execute(
            """
            UPDATE dead_letter_queue
            SET retried = 1, retried_at = datetime('now')
            WHERE dlq_id = ?
            """,
            (dlq_id,)
        )

    @staticmethod
    def get_count_by_run(conn, run_id: str) -> int:
        """Get the count of dead-letter records for a specific run."""
        cursor = conn.execute(
            "SELECT COUNT(*) FROM dead_letter_queue WHERE run_id = ?",
            (run_id,)
        )
        return cursor.fetchone()[0]
