"""
Risk Model — Account risk classification and daily capacity recommendations.
Part 5: Advanced Analytics & Risk Modeling.

Uses anomaly scores, historical performance, and account tier ceilings
to recommend optimal daily capacity limits per account.

Assumptions:
- Account tier limits (from Part 1) are hard ceilings — never exceed.
- Recommended limits should be conservative when risk signals are present.
- A minimum 3-day history is needed for meaningful recommendations.

Confidence Levels:
- HIGH: 14+ days of data, stable metrics
- MEDIUM: 7–13 days of data
- LOW: 3–6 days of data
- INSUFFICIENT: < 3 days — use tier defaults

Limitations:
- Cannot detect LinkedIn's internal shadow-ban signals (black box).
- Anomaly detection is backward-looking; cannot predict future changes.
- Small data volumes reduce statistical power.
"""

import numpy as np
import pandas as pd
import structlog

from config.settings import ACCOUNT_AGE_LIMITS

logger = structlog.get_logger()


def classify_account_risk(
    anomaly_score: float,
    acceptance_rate: float,
    reply_rate: float,
    utilization: float,
) -> str:
    """
    Classify overall account risk level based on multiple signals.

    Returns:
        Risk level: 'Critical', 'High', 'Moderate', 'Low', 'Healthy'
    """
    score = 0

    # Anomaly score contribution
    if anomaly_score > 3.5:
        score += 4
    elif anomaly_score > 2.0:
        score += 2
    elif anomaly_score > 1.0:
        score += 1

    # Acceptance rate contribution
    if acceptance_rate < 0.05:
        score += 3  # Near-zero acceptance is critical
    elif acceptance_rate < 0.10:
        score += 2
    elif acceptance_rate < 0.20:
        score += 1

    # Reply rate contribution
    if reply_rate < 0.02:
        score += 2
    elif reply_rate < 0.05:
        score += 1

    # Over-utilization
    if utilization > 0.95:
        score += 2
    elif utilization > 0.80:
        score += 1

    # Map score to risk level
    if score >= 7:
        return "Critical"
    elif score >= 5:
        return "High"
    elif score >= 3:
        return "Moderate"
    elif score >= 1:
        return "Low"
    else:
        return "Healthy"


def recommend_daily_limits(
    account_age_tier: str,
    avg_acceptance_rate: float,
    avg_reply_rate: float,
    recent_anomaly_score: float,
    days_of_data: int,
) -> dict:
    """
    Recommend daily invite and message limits for an account.

    Strategy:
    1. Start from the tier ceiling (hard max from Part 1).
    2. Apply a safety factor based on risk signals.
    3. Never recommend above the tier ceiling.
    4. Gradually increase limits as the account proves healthy.

    Args:
        account_age_tier: The account's tier from Part 1 (e.g., '1+ Year').
        avg_acceptance_rate: Average acceptance rate over available history.
        avg_reply_rate: Average reply rate.
        recent_anomaly_score: Most recent anomaly score.
        days_of_data: Number of days of historical data available.

    Returns:
        Dict with recommended limits, confidence level, and reasoning.
    """
    tier = ACCOUNT_AGE_LIMITS.get(account_age_tier)
    if not tier:
        logger.warning("unknown_account_tier", tier=account_age_tier)
        tier = ACCOUNT_AGE_LIMITS["1+ Year"]

    max_invites = tier["invites"]
    max_messages = tier["messages"]

    # Determine confidence level
    if days_of_data >= 14:
        confidence = "HIGH"
    elif days_of_data >= 7:
        confidence = "MEDIUM"
    elif days_of_data >= 3:
        confidence = "LOW"
    else:
        confidence = "INSUFFICIENT"
        return {
            "recommended_daily_invites": max_invites,
            "recommended_daily_messages": max_messages,
            "invite_ceiling": max_invites,
            "message_ceiling": max_messages,
            "safety_factor": 1.0,
            "confidence": confidence,
            "risk_level": "Unknown",
            "reasoning": (
                f"Only {days_of_data} day(s) of data available. "
                f"Using tier defaults ({max_invites} invites, {max_messages} messages). "
                f"Minimum 3 days needed for recommendations."
            ),
        }

    # Compute safety factor (0.0 to 1.0, where 1.0 = full capacity)
    # Start at 1.0 and reduce based on risk signals
    safety_factor = 1.0

    # Anomaly score penalty
    if recent_anomaly_score > 3.5:
        safety_factor *= 0.40  # Critical: drop to 40%
    elif recent_anomaly_score > 2.0:
        safety_factor *= 0.65  # Warning: drop to 65%
    elif recent_anomaly_score > 1.0:
        safety_factor *= 0.85  # Mild: drop to 85%

    # Acceptance rate penalty
    if avg_acceptance_rate < 0.05:
        safety_factor *= 0.50
    elif avg_acceptance_rate < 0.10:
        safety_factor *= 0.70
    elif avg_acceptance_rate < 0.20:
        safety_factor *= 0.85

    # Reply rate penalty
    if avg_reply_rate < 0.02:
        safety_factor *= 0.75
    elif avg_reply_rate < 0.05:
        safety_factor *= 0.90

    # Confidence discount (less data = more conservative)
    if confidence == "LOW":
        safety_factor *= 0.80
    elif confidence == "MEDIUM":
        safety_factor *= 0.90

    # Compute recommended limits (never exceed ceiling, minimum of 1)
    rec_invites = max(1, min(max_invites, int(max_invites * safety_factor)))
    rec_messages = max(1, min(max_messages, int(max_messages * safety_factor)))

    risk_level = classify_account_risk(
        recent_anomaly_score,
        avg_acceptance_rate,
        avg_reply_rate,
        rec_invites / max_invites if max_invites > 0 else 0,
    )

    reasoning_parts = [
        f"Tier: {account_age_tier} ({tier['risk']}) — ceiling: {max_invites} invites, {max_messages} messages.",
        f"Safety factor: {safety_factor:.2f} (based on anomaly={recent_anomaly_score:.2f}, "
        f"accept_rate={avg_acceptance_rate:.2%}, reply_rate={avg_reply_rate:.2%}).",
        f"Confidence: {confidence} ({days_of_data} days of data).",
        f"Risk level: {risk_level}.",
    ]

    result = {
        "recommended_daily_invites": rec_invites,
        "recommended_daily_messages": rec_messages,
        "invite_ceiling": max_invites,
        "message_ceiling": max_messages,
        "safety_factor": round(safety_factor, 4),
        "confidence": confidence,
        "risk_level": risk_level,
        "reasoning": " ".join(reasoning_parts),
    }

    logger.info(
        "capacity_recommendation",
        account_tier=account_age_tier,
        recommended_invites=rec_invites,
        recommended_messages=rec_messages,
        safety_factor=round(safety_factor, 4),
        risk_level=risk_level,
    )

    return result


def generate_risk_report(conn) -> list[dict]:
    """
    Generate a full risk report for all active accounts.

    Queries the daily snapshot fact table, computes anomaly scores,
    and produces per-account capacity recommendations.

    Returns:
        List of per-account risk assessment dicts.
    """
    # Fetch all active accounts
    accounts = conn.execute(
        """
        SELECT a.account_key, a.account_id, a.account_name, a.account_age_tier,
               a.risk_classification, a.daily_invite_limit, a.daily_message_limit
        FROM dim_linkedin_account a
        WHERE a.is_current = 1 AND a.agent_status = 'Active'
        """
    ).fetchall()

    reports = []

    for account in accounts:
        acct_key = account["account_key"]
        acct_tier = account["account_age_tier"]

        # Fetch snapshot history for this account
        snapshots = conn.execute(
            """
            SELECT date_key, invites_sent, invites_accepted, messages_sent,
                   replies_received, acceptance_rate, reply_rate,
                   invite_utilization, message_utilization, anomaly_score
            FROM fact_daily_account_snapshot
            WHERE account_key = ?
            ORDER BY date_key
            """,
            (acct_key,)
        ).fetchall()

        days_of_data = len(snapshots)

        if days_of_data == 0:
            reports.append({
                "account_id": account["account_id"],
                "account_name": account["account_name"],
                "account_tier": acct_tier,
                "days_of_data": 0,
                **recommend_daily_limits(acct_tier, 0.0, 0.0, 0.0, 0),
            })
            continue

        # Compute averages
        accept_rates = [s["acceptance_rate"] for s in snapshots if s["acceptance_rate"] is not None]
        reply_rates = [s["reply_rate"] for s in snapshots if s["reply_rate"] is not None]
        anomaly_scores = [s["anomaly_score"] for s in snapshots if s["anomaly_score"] is not None]

        avg_accept = np.mean(accept_rates) if accept_rates else 0.0
        avg_reply = np.mean(reply_rates) if reply_rates else 0.0
        recent_anomaly = anomaly_scores[-1] if anomaly_scores else 0.0

        recommendation = recommend_daily_limits(
            acct_tier, avg_accept, avg_reply, recent_anomaly, days_of_data
        )

        reports.append({
            "account_id": account["account_id"],
            "account_name": account["account_name"],
            "account_tier": acct_tier,
            "days_of_data": days_of_data,
            "avg_acceptance_rate": round(avg_accept, 4),
            "avg_reply_rate": round(avg_reply, 4),
            "recent_anomaly_score": round(recent_anomaly, 4),
            **recommendation,
        })

    logger.info("risk_report_generated", total_accounts=len(reports))
    return reports
