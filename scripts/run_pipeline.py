"""
Pipeline Orchestrator — Main entry point for running the full data pipeline.
Coordinates: API ingestion → DQ checks → Analytics → Snapshot updates.
"""

import sys
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.logging_config import setup_logging
from src.database.db_manager import get_db_session, initialize_database
from src.pipeline.api_client import PolluxaAPIClient
from src.pipeline.ingestion import IncrementalIngestionEngine
from src.pipeline.run_metadata import RunMetadataTracker
from src.quality.dq_scorer import run_and_score
from src.analytics.anomaly_detection import compute_anomaly_scores
from src.analytics.risk_model import generate_risk_report
from src.observability.alerting import check_and_alert
import pandas as pd


def run_pipeline(run_type: str = "incremental", db_path: str | None = None) -> dict:
    """
    Execute the full data pipeline end-to-end.

    Steps:
    1. Initialize logging with correlation ID
    2. Initialize database (idempotent)
    3. Run incremental ingestion from API
    4. Run data quality checks
    5. Compute anomaly scores and update snapshots
    6. Generate risk report
    7. Persist run metadata
    8. Check alert conditions

    Args:
        run_type: 'full' or 'incremental'
        db_path: Optional database path override

    Returns:
        Summary dict with run results.
    """
    # 1. Setup
    correlation_id = str(uuid.uuid4())
    logger = setup_logging(correlation_id)
    logger.info("pipeline_start", run_type=run_type)

    # 2. Initialize database
    initialize_database(db_path)
    logger.info("database_initialized")

    run_tracker = RunMetadataTracker(
        correlation_id=correlation_id,
        run_type=run_type,
    )

    try:
        with get_db_session(db_path) as conn:
            # 3. Ingestion
            logger.info("phase_start", phase="ingestion")
            engine = IncrementalIngestionEngine(db_path=db_path)

            campaigns_loaded = engine.ingest_campaigns(conn, run_tracker)
            leads_loaded = engine.ingest_leads(conn, run_tracker)
            activities_loaded = engine.ingest_activities(conn, run_tracker)

            logger.info(
                "ingestion_complete",
                campaigns=campaigns_loaded,
                leads=leads_loaded,
                activities=activities_loaded,
            )

            # 4. Data Quality
            logger.info("phase_start", phase="data_quality")
            dq_result = run_and_score(conn, run_id=run_tracker.run_id)
            logger.info(
                "dq_complete",
                composite_score=dq_result["composite_dq_score"],
                pass_fail=dq_result["pass_fail"],
            )

            # 5. Analytics — Anomaly Detection
            logger.info("phase_start", phase="analytics")
            snapshots_df = pd.read_sql(
                "SELECT * FROM fact_daily_account_snapshot",
                conn,
            )

            if not snapshots_df.empty:
                scored_df = compute_anomaly_scores(snapshots_df)

                # Update anomaly scores in the snapshot table
                for _, row in scored_df.iterrows():
                    conn.execute(
                        """
                        UPDATE fact_daily_account_snapshot
                        SET anomaly_score = ?, risk_flag = ?
                        WHERE snapshot_key = ?
                        """,
                        (
                            float(row["anomaly_score"]),
                            str(row["risk_flag"]),
                            int(row["snapshot_key"]),
                        )
                    )

                logger.info("anomaly_scores_updated", records=len(scored_df))

            # 6. Risk Report
            risk_report = generate_risk_report(conn)
            logger.info("risk_report_generated", accounts=len(risk_report))

            # 7. Mark success and persist metadata
            run_tracker.mark_success()
            run_tracker.persist(conn)

            # 8. Alerting
            check_and_alert(
                dq_result=dq_result,
                run_tracker=run_tracker,
                risk_report=risk_report,
            )

    except Exception as e:
        logger.exception("pipeline_failed", error=str(e))
        run_tracker.mark_failed(str(e))

        try:
            with get_db_session(db_path) as conn:
                run_tracker.persist(conn)
        except Exception:
            logger.exception("failed_to_persist_error_metadata")

        raise

    summary = {
        "run_id": run_tracker.run_id,
        "correlation_id": correlation_id,
        "status": run_tracker.status,
        "rows_extracted": run_tracker.rows_extracted,
        "rows_loaded": run_tracker.rows_loaded,
        "rows_rejected": run_tracker.rows_rejected,
        "dq_score": dq_result["composite_dq_score"],
        "dq_pass_fail": dq_result["pass_fail"],
        "risk_accounts": len(risk_report),
    }

    logger.info("pipeline_complete", **summary)
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the LinkedIn Analytics data pipeline")
    parser.add_argument("--run-type", choices=["full", "incremental"], default="incremental",
                        help="Type of pipeline run")
    parser.add_argument("--db-path", type=str, default=None,
                        help="Override database file path")
    args = parser.parse_args()

    result = run_pipeline(run_type=args.run_type, db_path=args.db_path)
    print(f"\n✅ Pipeline completed: {result['status']}")
    print(f"   Rows loaded: {result['rows_loaded']}")
    print(f"   DQ Score: {result['dq_score']} ({result['dq_pass_fail']})")
