"""
Incremental Ingestion Engine — Watermark-based incremental loading with idempotent writes.
Part 2: API Engineering & Data Pipeline.

Handles:
- Watermark retrieval and update for incremental loads
- Batch processing with configurable batch size
- Idempotent writes (no duplicates on re-run)
- Dead-letter routing for failed records
- Run metadata tracking
"""

import json
from datetime import datetime, timezone

import structlog

from config.settings import PIPELINE_BATCH_SIZE
from src.database.db_manager import (
    get_db_session,
    upsert_dimension,
    upsert_fact,
)
from src.pipeline.api_client import PolluxaAPIClient
from src.pipeline.run_metadata import RunMetadataTracker
from src.pipeline.dead_letter import DeadLetterQueue

logger = structlog.get_logger()


class IncrementalIngestionEngine:
    """
    Orchestrates incremental data ingestion from Polluxa API into the Star Schema.

    Flow:
    1. Read watermark (last successfully processed timestamp)
    2. Fetch new records from API since watermark
    3. Transform and load into dimension/fact tables (idempotent)
    4. Route failures to dead-letter queue
    5. Update watermark on success
    6. Log run metadata
    """

    def __init__(self, api_client: PolluxaAPIClient | None = None, db_path: str | None = None):
        self.api = api_client or PolluxaAPIClient()
        self.db_path = db_path
        self.dlq = DeadLetterQueue(db_path=db_path)

    def get_watermark(self, conn, entity_name: str) -> str | None:
        """Retrieve the last watermark for an entity."""
        cursor = conn.execute(
            "SELECT last_watermark FROM ingestion_watermark WHERE entity_name = ?",
            (entity_name,)
        )
        row = cursor.fetchone()
        return row["last_watermark"] if row else None

    def update_watermark(self, conn, entity_name: str, watermark_value: str) -> None:
        """Update the watermark after successful ingestion."""
        conn.execute(
            """
            INSERT INTO ingestion_watermark (entity_name, last_watermark, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(entity_name) DO UPDATE SET
                last_watermark = excluded.last_watermark,
                updated_at = datetime('now')
            """,
            (entity_name, watermark_value)
        )

    def ingest_campaigns(self, conn, run_tracker: RunMetadataTracker) -> int:
        """
        Ingest campaigns into dim_campaign. SCD Type 1 (overwrite).

        Returns:
            Number of records processed.
        """
        log = logger.bind(entity="campaigns")
        log.info("ingestion_start")

        try:
            campaigns = self.api.get_campaigns()
        except Exception as e:
            log.error("api_fetch_failed", error=str(e))
            return 0

        count = 0
        for record in campaigns:
            try:
                upsert_dimension(
                    conn,
                    table="dim_campaign",
                    natural_key_col="campaign_id",
                    natural_key_val=record["id"],
                    data={
                        "campaign_name": record.get("name", "Unknown"),
                        "target_segment": record.get("target_segment"),
                        "description": record.get("description"),
                        "status": record.get("status", "Active"),
                        "created_date": record.get("created_at"),
                    }
                )
                count += 1
            except Exception as e:
                self.dlq.send(
                    conn=conn,
                    run_id=run_tracker.run_id,
                    record=record,
                    error_type="transformation",
                    error_message=str(e),
                )
                run_tracker.increment_rejected()

        run_tracker.increment_loaded(count)
        log.info("ingestion_complete", records_processed=count)
        return count

    def ingest_leads(self, conn, run_tracker: RunMetadataTracker) -> int:
        """
        Ingest leads into dim_lead. SCD Type 1.

        Returns:
            Number of records processed.
        """
        log = logger.bind(entity="leads")
        log.info("ingestion_start")

        watermark = self.get_watermark(conn, "leads")
        log.info("watermark_read", watermark=watermark)

        try:
            leads = self.api.get_leads(since=watermark)
        except Exception as e:
            log.error("api_fetch_failed", error=str(e))
            return 0

        count = 0
        max_timestamp = watermark

        for record in leads:
            try:
                upsert_dimension(
                    conn,
                    table="dim_lead",
                    natural_key_col="lead_id",
                    natural_key_val=record["id"],
                    data={
                        "linkedin_url": record.get("linkedin_url"),
                        "full_name": record.get("full_name"),
                        "job_title": record.get("job_title"),
                        "company": record.get("company"),
                        "location": record.get("location"),
                        "industry": record.get("industry"),
                    }
                )
                count += 1

                # Track max timestamp for watermark update
                ts = record.get("updated_at") or record.get("created_at")
                if ts and (max_timestamp is None or ts > max_timestamp):
                    max_timestamp = ts

            except Exception as e:
                self.dlq.send(
                    conn=conn,
                    run_id=run_tracker.run_id,
                    record=record,
                    error_type="transformation",
                    error_message=str(e),
                )
                run_tracker.increment_rejected()

        # Update watermark
        if max_timestamp and max_timestamp != watermark:
            self.update_watermark(conn, "leads", max_timestamp)
            log.info("watermark_updated", new_watermark=max_timestamp)

        run_tracker.increment_loaded(count)
        log.info("ingestion_complete", records_processed=count)
        return count

    def ingest_activities(self, conn, run_tracker: RunMetadataTracker) -> int:
        """
        Ingest outreach activities into fact_outreach_activity.
        Uses watermark-based incremental loading with idempotent writes.

        Returns:
            Number of records processed.
        """
        log = logger.bind(entity="activities")
        log.info("ingestion_start")

        watermark = self.get_watermark(conn, "outreach_activity")
        log.info("watermark_read", watermark=watermark)

        total_loaded = 0
        offset = 0
        max_timestamp = watermark

        while True:
            # Paginated fetch
            try:
                batch = self.api.get_activities(
                    since=watermark,
                    limit=PIPELINE_BATCH_SIZE,
                    offset=offset,
                )
            except Exception as e:
                log.error("api_fetch_failed", error=str(e), offset=offset)
                break

            if not batch:
                break  # No more records

            run_tracker.increment_extracted(len(batch))

            for record in batch:
                try:
                    # Parse the activity timestamp to derive date_key
                    ts = record.get("timestamp") or record.get("created_at", "")
                    date_key = int(ts[:10].replace("-", "")) if ts else None

                    if not date_key:
                        raise ValueError(f"Missing timestamp in record {record.get('id')}")

                    # Look up dimension keys
                    account_key = self._resolve_account_key(conn, record.get("agent_id"))
                    campaign_key = self._resolve_campaign_key(conn, record.get("campaign_id"))
                    lead_key = self._resolve_lead_key(conn, record.get("lead_id"))

                    upsert_fact(
                        conn,
                        table="fact_outreach_activity",
                        natural_key_col="activity_id",
                        natural_key_val=record["id"],
                        data={
                            "date_key": date_key,
                            "account_key": account_key or 0,
                            "campaign_key": campaign_key,
                            "lead_key": lead_key,
                            "activity_type": record.get("type", "unknown"),
                            "activity_timestamp": ts,
                            "is_accepted": 1 if record.get("accepted") else 0,
                            "is_replied": 1 if record.get("replied") else 0,
                            "is_converted": 1 if record.get("converted") else 0,
                            "response_time_hours": record.get("response_time_hours"),
                            "source_system": "polluxa_api",
                        }
                    )
                    total_loaded += 1

                    # Track max timestamp
                    if ts and (max_timestamp is None or ts > max_timestamp):
                        max_timestamp = ts

                except Exception as e:
                    self.dlq.send(
                        conn=conn,
                        run_id=run_tracker.run_id,
                        record=record,
                        error_type="load",
                        error_message=str(e),
                    )
                    run_tracker.increment_rejected()

            offset += PIPELINE_BATCH_SIZE

            # Safety: if batch was smaller than page size, we've reached the end
            if len(batch) < PIPELINE_BATCH_SIZE:
                break

        # Update watermark
        if max_timestamp and max_timestamp != watermark:
            self.update_watermark(conn, "outreach_activity", max_timestamp)
            log.info("watermark_updated", new_watermark=max_timestamp)

        run_tracker.increment_loaded(total_loaded)
        log.info("ingestion_complete", records_loaded=total_loaded)
        return total_loaded

    def _resolve_account_key(self, conn, account_id: str | None) -> int | None:
        """Look up surrogate key for an account by its natural key."""
        if not account_id:
            return None
        cursor = conn.execute(
            "SELECT account_key FROM dim_linkedin_account WHERE account_id = ? AND is_current = 1",
            (account_id,)
        )
        row = cursor.fetchone()
        return row["account_key"] if row else None

    def _resolve_campaign_key(self, conn, campaign_id: str | None) -> int | None:
        """Look up surrogate key for a campaign."""
        if not campaign_id:
            return None
        cursor = conn.execute(
            "SELECT campaign_key FROM dim_campaign WHERE campaign_id = ?",
            (campaign_id,)
        )
        row = cursor.fetchone()
        return row["campaign_key"] if row else None

    def _resolve_lead_key(self, conn, lead_id: str | None) -> int | None:
        """Look up surrogate key for a lead."""
        if not lead_id:
            return None
        cursor = conn.execute(
            "SELECT lead_key FROM dim_lead WHERE lead_id = ?",
            (lead_id,)
        )
        row = cursor.fetchone()
        return row["lead_key"] if row else None
