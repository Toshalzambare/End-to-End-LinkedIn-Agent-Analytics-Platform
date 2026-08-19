"""
KPI Metrics Calculator — Core business metrics for the LinkedIn Analytics Platform.
Feeds Power BI dashboards (Part 6) with pre-computed aggregations.
"""

import structlog

logger = structlog.get_logger()


def compute_core_kpis(conn, date_from: str | None = None, date_to: str | None = None) -> dict:
    """
    Compute core KPIs across all accounts for a date range.

    Returns:
        Dict with all core KPI values.
    """
    where_clause = ""
    params = []
    if date_from:
        where_clause += " AND d.full_date >= ?"
        params.append(date_from)
    if date_to:
        where_clause += " AND d.full_date <= ?"
        params.append(date_to)

    row = conn.execute(
        f"""
        SELECT
            COUNT(CASE WHEN f.activity_type = 'invite_sent' THEN 1 END) AS total_invites_sent,
            COUNT(CASE WHEN f.activity_type = 'invite_accepted' THEN 1 END) AS total_invites_accepted,
            COUNT(CASE WHEN f.activity_type = 'message_sent' THEN 1 END) AS total_messages_sent,
            COUNT(CASE WHEN f.activity_type = 'reply_received' THEN 1 END) AS total_replies_received,
            COUNT(CASE WHEN f.activity_type = 'follow_up_sent' THEN 1 END) AS total_follow_ups,
            SUM(f.is_converted) AS total_conversions,
            AVG(f.response_time_hours) AS avg_response_time_hours
        FROM fact_outreach_activity f
        JOIN dim_date d ON f.date_key = d.date_key
        WHERE 1=1 {where_clause}
        """,
        params,
    ).fetchone()

    invites = row["total_invites_sent"] or 0
    accepted = row["total_invites_accepted"] or 0
    messages = row["total_messages_sent"] or 0
    replies = row["total_replies_received"] or 0
    conversions = row["total_conversions"] or 0

    kpis = {
        "total_invites_sent": invites,
        "total_invites_accepted": accepted,
        "total_messages_sent": messages,
        "total_replies_received": replies,
        "total_follow_ups": row["total_follow_ups"] or 0,
        "total_conversions": conversions,
        "acceptance_rate": round(accepted / invites, 4) if invites > 0 else 0.0,
        "reply_rate": round(replies / messages, 4) if messages > 0 else 0.0,
        "conversion_rate": round(conversions / (invites + messages), 4) if (invites + messages) > 0 else 0.0,
        "avg_response_time_hours": round(row["avg_response_time_hours"] or 0, 2),
    }

    logger.info("core_kpis_computed", **kpis)
    return kpis


def compute_account_health(conn) -> list[dict]:
    """
    Compute per-account health metrics.

    Returns:
        List of account health dicts.
    """
    rows = conn.execute(
        """
        SELECT
            a.account_id,
            a.account_name,
            a.agent_status,
            a.account_age_tier,
            a.daily_invite_limit,
            a.daily_message_limit,
            COUNT(s.snapshot_key) AS days_active,
            COALESCE(AVG(s.invite_utilization), 0) AS avg_invite_utilization,
            COALESCE(AVG(s.message_utilization), 0) AS avg_message_utilization,
            COALESCE(AVG(s.acceptance_rate), 0) AS avg_acceptance_rate,
            COALESCE(AVG(s.reply_rate), 0) AS avg_reply_rate,
            COALESCE(MAX(s.anomaly_score), 0) AS max_anomaly_score,
            COALESCE(AVG(s.anomaly_score), 0) AS avg_anomaly_score
        FROM dim_linkedin_account a
        LEFT JOIN fact_daily_account_snapshot s ON a.account_key = s.account_key
        WHERE a.is_current = 1
        GROUP BY a.account_key
        """
    ).fetchall()

    return [dict(row) for row in rows]


def compute_campaign_roi(conn) -> list[dict]:
    """
    Compute per-campaign performance and ROI metrics.

    Returns:
        List of campaign performance dicts.
    """
    rows = conn.execute(
        """
        SELECT
            c.campaign_id,
            c.campaign_name,
            c.target_segment,
            c.status,
            COUNT(CASE WHEN f.activity_type = 'invite_sent' THEN 1 END) AS invites_sent,
            COUNT(CASE WHEN f.activity_type = 'invite_accepted' THEN 1 END) AS invites_accepted,
            COUNT(CASE WHEN f.activity_type = 'message_sent' THEN 1 END) AS messages_sent,
            COUNT(CASE WHEN f.activity_type = 'reply_received' THEN 1 END) AS replies_received,
            SUM(f.is_converted) AS conversions,
            AVG(f.response_time_hours) AS avg_response_time
        FROM dim_campaign c
        LEFT JOIN fact_outreach_activity f ON c.campaign_key = f.campaign_key
        GROUP BY c.campaign_key
        ORDER BY conversions DESC
        """
    ).fetchall()

    results = []
    for row in rows:
        r = dict(row)
        inv = r["invites_sent"] or 0
        acc = r["invites_accepted"] or 0
        msg = r["messages_sent"] or 0
        rep = r["replies_received"] or 0

        r["acceptance_rate"] = round(acc / inv, 4) if inv > 0 else 0.0
        r["reply_rate"] = round(rep / msg, 4) if msg > 0 else 0.0
        r["avg_response_time"] = round(r["avg_response_time"] or 0, 2)
        results.append(r)

    return results
