"""
Tests for Data Quality checks and composite scoring.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.db_manager import initialize_database, get_db_session, populate_date_dimension
from src.quality.dq_checks import run_all_checks
from src.quality.dq_scorer import compute_composite_score, run_and_score


@pytest.fixture
def populated_db(tmp_path):
    """Create a DB with sample data for DQ testing."""
    path = str(tmp_path / "dq_test.db")
    initialize_database(path)

    with get_db_session(path) as conn:
        populate_date_dimension(conn, 2024, 2024)

        # Insert a test account
        conn.execute(
            """
            INSERT INTO dim_linkedin_account
            (account_id, account_age_tier, risk_classification,
             daily_invite_limit, daily_message_limit, effective_from, is_current)
            VALUES ('acct_test', '1+ Year', 'Minimal Risk', 30, 60, datetime('now'), 1)
            """
        )

        # Insert a test campaign
        conn.execute(
            """
            INSERT INTO dim_campaign (campaign_id, campaign_name, status)
            VALUES ('camp_test', 'Test Campaign', 'Active')
            """
        )

        # Insert valid activity records
        for i in range(10):
            conn.execute(
                """
                INSERT INTO fact_outreach_activity
                (activity_id, date_key, account_key, campaign_key,
                 activity_type, activity_timestamp, is_accepted, is_replied,
                 is_converted, source_system)
                VALUES (?, 20240115, 1, 1, 'invite_sent', '2024-01-15T10:00:00',
                        0, 0, 0, 'test')
                """,
                (f"act_dq_{i}",)
            )

        conn.commit()

    return path


class TestDQChecks:
    """Test individual DQ check execution."""

    def test_checks_return_results(self, populated_db):
        """DQ checks should return a non-empty list of results."""
        with get_db_session(populated_db) as conn:
            results = run_all_checks(conn)
        assert len(results) > 0

    def test_all_dimensions_covered(self, populated_db):
        """All 5 DQ dimensions should be checked."""
        with get_db_session(populated_db) as conn:
            results = run_all_checks(conn)
        dimensions = {r.dimension for r in results}
        expected = {"completeness", "uniqueness", "validity", "timeliness", "referential_integrity"}
        assert expected.issubset(dimensions), f"Missing dimensions: {expected - dimensions}"

    def test_scores_in_range(self, populated_db):
        """All check scores should be between 0.0 and 1.0."""
        with get_db_session(populated_db) as conn:
            results = run_all_checks(conn)
        for r in results:
            assert 0.0 <= r.score <= 1.0, f"Score out of range for {r.check_name}: {r.score}"


class TestCompositeScoring:
    """Test composite DQ score calculation."""

    def test_composite_score_in_range(self, populated_db):
        """Composite score should be between 0.0 and 1.0."""
        with get_db_session(populated_db) as conn:
            results = run_all_checks(conn)
        score_result = compute_composite_score(results)
        assert 0.0 <= score_result["composite_dq_score"] <= 1.0

    def test_pass_fail_correct(self, populated_db):
        """Pass/fail should match threshold comparison."""
        with get_db_session(populated_db) as conn:
            results = run_all_checks(conn)
        score_result = compute_composite_score(results)

        if score_result["composite_dq_score"] >= score_result["threshold"]:
            assert score_result["pass_fail"] == "PASS"
        else:
            assert score_result["pass_fail"] == "FAIL"

    def test_weights_sum_to_one(self):
        """Dimension weights should sum to 1.0."""
        from src.quality.dq_scorer import DIMENSION_WEIGHTS
        assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 0.001

    def test_run_and_score_persists(self, populated_db):
        """run_and_score should persist results to dq_results_history."""
        with get_db_session(populated_db) as conn:
            run_and_score(conn, run_id=None)
            conn.commit()

            cursor = conn.execute("SELECT COUNT(*) FROM dq_results_history")
            assert cursor.fetchone()[0] >= 1
