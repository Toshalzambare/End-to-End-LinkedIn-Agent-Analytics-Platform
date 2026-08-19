"""
Alerting Module — Triggers alerts on pipeline failure, DQ threshold breach,
and anomalous conditions. Part 7 requirement.

In production, this would integrate with email (SMTP), Slack webhooks,
or PagerDuty. For this assessment, alerts are logged to the structured
log output and written to an alerts file.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import structlog

from config.settings import (
    ALERT_ON_PIPELINE_FAILURE,
    ALERT_ON_DQ_BREACH,
    ALERT_ON_ANOMALOUS_DURATION,
    DQ_PASS_THRESHOLD,
)

logger = structlog.get_logger()

ALERTS_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "alerts.json"


def _emit_alert(alert_type: str, severity: str, message: str, details: dict | None = None) -> None:
    """
    Emit an alert — log it and append to the alerts file.

    Args:
        alert_type: 'pipeline_failure', 'dq_breach', 'anomalous_duration', 'risk_critical'
        severity: 'INFO', 'WARNING', 'CRITICAL'
        message: Human-readable alert message.
        details: Additional context.
    """
    alert = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "details": details or {},
    }

    # Log the alert
    logger.warning(
        "ALERT",
        alert_type=alert_type,
        severity=severity,
        message=message,
    )

    # Append to alerts file
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(alert) + "\n")


def check_and_alert(
    dq_result: dict | None = None,
    run_tracker=None,
    risk_report: list[dict] | None = None,
) -> list[dict]:
    """
    Check all alert conditions and emit alerts as needed.

    Args:
        dq_result: Output from DQ scorer.
        run_tracker: RunMetadataTracker instance.
        risk_report: Output from risk model.

    Returns:
        List of emitted alert dicts.
    """
    alerts_emitted = []

    # 1. Pipeline failure alert
    if ALERT_ON_PIPELINE_FAILURE and run_tracker and run_tracker.status == "failed":
        _emit_alert(
            alert_type="pipeline_failure",
            severity="CRITICAL",
            message=f"Pipeline run {run_tracker.run_id} FAILED: {run_tracker.error_message}",
            details=run_tracker.to_dict(),
        )
        alerts_emitted.append({"type": "pipeline_failure", "severity": "CRITICAL"})

    # 2. DQ threshold breach alert
    if ALERT_ON_DQ_BREACH and dq_result:
        if dq_result["pass_fail"] == "FAIL":
            _emit_alert(
                alert_type="dq_breach",
                severity="WARNING",
                message=(
                    f"Data Quality score {dq_result['composite_dq_score']:.4f} "
                    f"is BELOW threshold {DQ_PASS_THRESHOLD}."
                ),
                details={
                    "composite_score": dq_result["composite_dq_score"],
                    "threshold": DQ_PASS_THRESHOLD,
                    "dimension_scores": dq_result["dimension_scores"],
                },
            )
            alerts_emitted.append({"type": "dq_breach", "severity": "WARNING"})

    # 3. Anomalous run duration
    if ALERT_ON_ANOMALOUS_DURATION and run_tracker:
        if run_tracker.started_at and run_tracker.ended_at:
            try:
                start = datetime.fromisoformat(run_tracker.started_at)
                end = datetime.fromisoformat(run_tracker.ended_at)
                duration_seconds = (end - start).total_seconds()

                # Alert if run takes longer than 10 minutes (configurable)
                if duration_seconds > 600:
                    _emit_alert(
                        alert_type="anomalous_duration",
                        severity="WARNING",
                        message=f"Pipeline run took {duration_seconds:.0f}s (>{600}s threshold).",
                        details={"duration_seconds": duration_seconds},
                    )
                    alerts_emitted.append({"type": "anomalous_duration", "severity": "WARNING"})
            except (ValueError, TypeError):
                pass

    # 4. Critical risk accounts
    if risk_report:
        critical_accounts = [r for r in risk_report if r.get("risk_level") == "Critical"]
        if critical_accounts:
            _emit_alert(
                alert_type="risk_critical",
                severity="CRITICAL",
                message=f"{len(critical_accounts)} account(s) at CRITICAL risk level.",
                details={
                    "accounts": [
                        {"id": a["account_id"], "name": a.get("account_name")}
                        for a in critical_accounts
                    ]
                },
            )
            alerts_emitted.append({"type": "risk_critical", "severity": "CRITICAL"})

    if not alerts_emitted:
        logger.info("alerting_check_passed", message="No alert conditions triggered.")

    return alerts_emitted
