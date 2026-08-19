"""
Data Quality Checks — Automated validation across 5 dimensions.
Part 4: Data Quality & Automation.

Dimensions checked:
1. Completeness — Are required fields populated?
2. Uniqueness — Are natural keys unique?
3. Validity — Do values conform to expected formats/ranges?
4. Timeliness — Is data recent enough?
5. Referential Integrity — Do foreign keys resolve?
"""

from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import structlog

logger = structlog.get_logger()


class CheckResult(NamedTuple):
    """Result of a single DQ check."""
    check_name: str
    dimension: str        # 'completeness', 'uniqueness', 'validity', 'timeliness', 'referential_integrity'
    table_name: str
    total_records: int
    passed_records: int
    failed_records: int
    score: float          # 0.0 to 1.0
    details: str          # Human-readable explanation


def run_all_checks(conn) -> list[CheckResult]:
    """
    Execute all data quality checks and return results.

    Args:
        conn: Active database connection.

    Returns:
        List of CheckResult for each check performed.
    """
    results = []

    # ================================================================
    # 1. COMPLETENESS — Required fields must not be NULL/empty
    # ================================================================

    completeness_checks = [
        ("fact_outreach_activity", ["activity_id", "date_key", "account_key", "activity_type", "activity_timestamp"]),
        ("dim_linkedin_account", ["account_id", "account_age_tier", "risk_classification"]),
        ("dim_campaign", ["campaign_id", "campaign_name"]),
        ("dim_lead", ["lead_id"]),
        ("fact_daily_account_snapshot", ["date_key", "account_key"]),
    ]

    for table, required_cols in completeness_checks:
        total = _count_rows(conn, table)
        if total == 0:
            results.append(CheckResult(
                check_name=f"completeness_{table}",
                dimension="completeness",
                table_name=table,
                total_records=0,
                passed_records=0,
                failed_records=0,
                score=1.0,
                details=f"Table {table} is empty — skipped.",
            ))
            continue

        # Count rows where ANY required column is NULL or empty
        null_conditions = " OR ".join(
            f"({col} IS NULL OR {col} = '')" for col in required_cols
        )
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {null_conditions}"
        )
        failed = cursor.fetchone()[0]
        passed = total - failed
        score = passed / total if total > 0 else 1.0

        results.append(CheckResult(
            check_name=f"completeness_{table}",
            dimension="completeness",
            table_name=table,
            total_records=total,
            passed_records=passed,
            failed_records=failed,
            score=score,
            details=f"Checked columns: {required_cols}. {failed}/{total} rows have missing required fields.",
        ))

    # ================================================================
    # 2. UNIQUENESS — Natural keys must be unique
    # ================================================================

    uniqueness_checks = [
        ("fact_outreach_activity", "activity_id"),
        ("dim_campaign", "campaign_id"),
        ("dim_lead", "lead_id"),
        ("dim_date", "full_date"),
    ]

    for table, key_col in uniqueness_checks:
        total = _count_rows(conn, table)
        if total == 0:
            results.append(CheckResult(
                check_name=f"uniqueness_{table}_{key_col}",
                dimension="uniqueness",
                table_name=table,
                total_records=0, passed_records=0, failed_records=0,
                score=1.0,
                details=f"Table {table} is empty — skipped.",
            ))
            continue

        cursor = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT {key_col} FROM {table} GROUP BY {key_col} HAVING COUNT(*) > 1)"
        )
        duplicate_groups = cursor.fetchone()[0]

        cursor = conn.execute(
            f"SELECT COUNT(*) - COUNT(DISTINCT {key_col}) FROM {table}"
        )
        duplicate_rows = cursor.fetchone()[0]

        passed = total - duplicate_rows
        score = passed / total if total > 0 else 1.0

        results.append(CheckResult(
            check_name=f"uniqueness_{table}_{key_col}",
            dimension="uniqueness",
            table_name=table,
            total_records=total,
            passed_records=passed,
            failed_records=duplicate_rows,
            score=score,
            details=f"Key: {key_col}. Found {duplicate_groups} duplicate groups ({duplicate_rows} extra rows).",
        ))

    # ================================================================
    # 3. VALIDITY — Values must be in expected ranges/formats
    # ================================================================

    # Check activity_type is from known set
    valid_activity_types = ("invite_sent", "invite_accepted", "message_sent", "reply_received", "follow_up_sent")
    total = _count_rows(conn, "fact_outreach_activity")
    if total > 0:
        placeholders = ", ".join("?" for _ in valid_activity_types)
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM fact_outreach_activity WHERE activity_type NOT IN ({placeholders})",
            valid_activity_types,
        )
        invalid = cursor.fetchone()[0]
        results.append(CheckResult(
            check_name="validity_activity_type",
            dimension="validity",
            table_name="fact_outreach_activity",
            total_records=total,
            passed_records=total - invalid,
            failed_records=invalid,
            score=(total - invalid) / total,
            details=f"Valid types: {valid_activity_types}. {invalid} records have invalid activity_type.",
        ))

    # Check rates are between 0 and 1
    for rate_col in ["acceptance_rate", "reply_rate", "conversion_rate"]:
        total_snap = _count_rows(conn, "fact_daily_account_snapshot")
        if total_snap > 0:
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM fact_daily_account_snapshot "
                f"WHERE {rate_col} IS NOT NULL AND ({rate_col} < 0 OR {rate_col} > 1)"
            )
            invalid = cursor.fetchone()[0]
            results.append(CheckResult(
                check_name=f"validity_{rate_col}",
                dimension="validity",
                table_name="fact_daily_account_snapshot",
                total_records=total_snap,
                passed_records=total_snap - invalid,
                failed_records=invalid,
                score=(total_snap - invalid) / total_snap,
                details=f"{rate_col} must be between 0 and 1. {invalid} records out of range.",
            ))

    # Check risk_classification is valid
    valid_risks = ("Very High Risk", "High Risk", "Moderate Risk", "Low Risk", "Minimal Risk")
    total_acct = _count_rows(conn, "dim_linkedin_account")
    if total_acct > 0:
        placeholders = ", ".join("?" for _ in valid_risks)
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM dim_linkedin_account WHERE risk_classification NOT IN ({placeholders})",
            valid_risks,
        )
        invalid = cursor.fetchone()[0]
        results.append(CheckResult(
            check_name="validity_risk_classification",
            dimension="validity",
            table_name="dim_linkedin_account",
            total_records=total_acct,
            passed_records=total_acct - invalid,
            failed_records=invalid,
            score=(total_acct - invalid) / total_acct,
            details=f"Valid risks: {valid_risks}. {invalid} records have invalid classification.",
        ))

    # ================================================================
    # 4. TIMELINESS — Data should be recent
    # ================================================================

    # Check that the most recent activity is within the last 7 days
    cursor = conn.execute(
        "SELECT MAX(activity_timestamp) FROM fact_outreach_activity"
    )
    row = cursor.fetchone()
    max_ts = row[0] if row else None

    if max_ts:
        try:
            latest = datetime.fromisoformat(max_ts.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - latest).total_seconds() / 3600
            # Score: 1.0 if < 24h, degrades linearly, 0.0 if > 168h (7 days)
            timeliness = max(0.0, min(1.0, 1.0 - (age_hours - 24) / (168 - 24)))
        except (ValueError, TypeError):
            timeliness = 0.0
            age_hours = -1
    else:
        timeliness = 0.0
        age_hours = -1

    results.append(CheckResult(
        check_name="timeliness_latest_activity",
        dimension="timeliness",
        table_name="fact_outreach_activity",
        total_records=1,
        passed_records=1 if timeliness >= 0.5 else 0,
        failed_records=0 if timeliness >= 0.5 else 1,
        score=timeliness,
        details=f"Latest activity: {max_ts}. Age: {age_hours:.1f} hours. Score degrades linearly from 24h to 168h.",
    ))

    # ================================================================
    # 5. REFERENTIAL INTEGRITY — FK references must resolve
    # ================================================================

    fk_checks = [
        ("fact_outreach_activity", "date_key", "dim_date", "date_key"),
        ("fact_outreach_activity", "account_key", "dim_linkedin_account", "account_key"),
        ("fact_daily_account_snapshot", "date_key", "dim_date", "date_key"),
        ("fact_daily_account_snapshot", "account_key", "dim_linkedin_account", "account_key"),
    ]

    for child_table, child_col, parent_table, parent_col in fk_checks:
        total = _count_rows(conn, child_table)
        if total == 0:
            results.append(CheckResult(
                check_name=f"ri_{child_table}_{child_col}",
                dimension="referential_integrity",
                table_name=child_table,
                total_records=0, passed_records=0, failed_records=0,
                score=1.0,
                details=f"Table {child_table} is empty — skipped.",
            ))
            continue

        cursor = conn.execute(
            f"""
            SELECT COUNT(*) FROM {child_table} c
            WHERE c.{child_col} IS NOT NULL
              AND c.{child_col} NOT IN (SELECT {parent_col} FROM {parent_table})
            """
        )
        orphans = cursor.fetchone()[0]
        passed = total - orphans
        score = passed / total if total > 0 else 1.0

        results.append(CheckResult(
            check_name=f"ri_{child_table}_{child_col}",
            dimension="referential_integrity",
            table_name=child_table,
            total_records=total,
            passed_records=passed,
            failed_records=orphans,
            score=score,
            details=f"FK: {child_table}.{child_col} → {parent_table}.{parent_col}. {orphans} orphan records.",
        ))

    return results


def _count_rows(conn, table: str) -> int:
    """Helper to count total rows in a table."""
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
    return cursor.fetchone()[0]
