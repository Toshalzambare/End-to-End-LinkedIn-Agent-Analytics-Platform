"""
Tests for database schema initialization and idempotent operations.
"""

import sys
import sqlite3
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.db_manager import (
    initialize_database,
    get_db_session,
    upsert_dimension,
    upsert_fact,
    populate_date_dimension,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database for testing."""
    path = str(tmp_path / "test.db")
    initialize_database(path)
    return path


class TestSchemaInitialization:
    """Test that schema initializes correctly."""

    def test_tables_created(self, db_path):
        """All expected tables should exist after initialization."""
        with get_db_session(db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row["name"] for row in cursor.fetchall()}

        expected = {
            "dim_date", "dim_linkedin_account", "dim_campaign",
            "dim_lead", "dim_message_template",
            "fact_outreach_activity", "fact_daily_account_snapshot",
            "pipeline_run_log", "dead_letter_queue",
            "ingestion_watermark", "dq_results_history",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_idempotent_initialization(self, db_path):
        """Calling initialize_database twice should not error."""
        initialize_database(db_path)  # Second call
        initialize_database(db_path)  # Third call
        # Should not raise


class TestIdempotentUpserts:
    """Test that upserts are idempotent — no duplicates on re-run."""

    def test_dimension_upsert_insert(self, db_path):
        """First upsert should insert a new record."""
        with get_db_session(db_path) as conn:
            key = upsert_dimension(
                conn, "dim_campaign", "campaign_id", "camp_test_1",
                {"campaign_name": "Test Campaign", "status": "Active"}
            )
            assert key is not None
            assert key > 0

    def test_dimension_upsert_update(self, db_path):
        """Second upsert with same natural key should update, not duplicate."""
        with get_db_session(db_path) as conn:
            key1 = upsert_dimension(
                conn, "dim_campaign", "campaign_id", "camp_test_2",
                {"campaign_name": "Original Name", "status": "Active"}
            )
            key2 = upsert_dimension(
                conn, "dim_campaign", "campaign_id", "camp_test_2",
                {"campaign_name": "Updated Name", "status": "Paused"}
            )
            assert key1 == key2  # Same surrogate key

            # Verify the update
            cursor = conn.execute(
                "SELECT campaign_name, status FROM dim_campaign WHERE campaign_id = 'camp_test_2'"
            )
            row = cursor.fetchone()
            assert row["campaign_name"] == "Updated Name"
            assert row["status"] == "Paused"

    def test_fact_upsert_no_duplicate(self, db_path):
        """Re-inserting a fact with the same activity_id should not create duplicates."""
        with get_db_session(db_path) as conn:
            # Disable FK checks for this test — we're testing idempotency, not FK integrity
            conn.execute("PRAGMA foreign_keys=OFF;")
            # Need a date first
            populate_date_dimension(conn, 2024, 2024)
            conn.commit()

            data = {
                "date_key": 20240101,
                "account_key": 0,
                "activity_type": "invite_sent",
                "activity_timestamp": "2024-01-01T10:00:00",
                "is_accepted": 0,
                "is_replied": 0,
                "is_converted": 0,
                "source_system": "test",
            }

            key1 = upsert_fact(conn, "fact_outreach_activity", "activity_id", "act_001", data)
            key2 = upsert_fact(conn, "fact_outreach_activity", "activity_id", "act_001", data)

            assert key1 == key2

            cursor = conn.execute(
                "SELECT COUNT(*) FROM fact_outreach_activity WHERE activity_id = 'act_001'"
            )
            assert cursor.fetchone()[0] == 1


class TestDateDimension:
    """Test date dimension population."""

    def test_date_dimension_populated(self, db_path):
        """Date dimension should contain all dates in the range."""
        with get_db_session(db_path) as conn:
            populate_date_dimension(conn, 2024, 2024)
            conn.commit()

            cursor = conn.execute("SELECT COUNT(*) FROM dim_date WHERE year = 2024")
            count = cursor.fetchone()[0]
            assert count == 366  # 2024 is a leap year

    def test_date_dimension_idempotent(self, db_path):
        """Running populate twice should not create duplicates."""
        with get_db_session(db_path) as conn:
            populate_date_dimension(conn, 2024, 2024)
            conn.commit()
            populate_date_dimension(conn, 2024, 2024)
            conn.commit()

            cursor = conn.execute("SELECT COUNT(*) FROM dim_date WHERE year = 2024")
            count = cursor.fetchone()[0]
            assert count == 366
