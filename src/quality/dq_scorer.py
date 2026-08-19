"""
Composite Data Quality Scorer — Weighted aggregation with pass/fail threshold.
Part 4: Data Quality & Automation.

Weighting rationale:
- Completeness (25%): Missing data fundamentally undermines analytics.
- Uniqueness (25%): Duplicate records inflate KPIs and distort trends.
- Validity (20%): Invalid values produce misleading results.
- Timeliness (15%): Stale data reduces decision-making value.
- Referential Integrity (15%): Broken FK links cause join failures.

Total: 100%
"""

import json
from datetime import datetime, timezone

import structlog

from config.settings import DQ_PASS_THRESHOLD
from src.quality.dq_checks import CheckResult, run_all_checks

logger = structlog.get_logger()

# Dimension weights — documented rationale above
DIMENSION_WEIGHTS = {
    "completeness": 0.25,
    "uniqueness": 0.25,
    "validity": 0.20,
    "timeliness": 0.15,
    "referential_integrity": 0.15,
}


def compute_composite_score(check_results: list[CheckResult]) -> dict:
    """
    Compute the composite DQ score from individual check results.

    Algorithm:
    1. Group checks by dimension.
    2. Average the scores within each dimension.
    3. Apply dimension weights to compute the final composite score.
    4. Apply pass/fail threshold.

    Args:
        check_results: List of CheckResult from run_all_checks().

    Returns:
        Dict with dimension scores, composite score, pass/fail status, and details.
    """
    # Group scores by dimension
    dimension_scores: dict[str, list[float]] = {}
    for result in check_results:
        dim = result.dimension
        if dim not in dimension_scores:
            dimension_scores[dim] = []
        dimension_scores[dim].append(result.score)

    # Average each dimension
    dimension_averages = {}
    for dim, scores in dimension_scores.items():
        dimension_averages[dim] = sum(scores) / len(scores) if scores else 1.0

    # Compute weighted composite
    composite = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        avg = dimension_averages.get(dim, 1.0)  # Default to 1.0 if no checks for this dimension
        composite += avg * weight

    # Round for readability
    composite = round(composite, 4)
    pass_fail = "PASS" if composite >= DQ_PASS_THRESHOLD else "FAIL"

    result = {
        "composite_dq_score": composite,
        "pass_fail": pass_fail,
        "threshold": DQ_PASS_THRESHOLD,
        "dimension_scores": {
            dim: round(dimension_averages.get(dim, 1.0), 4)
            for dim in DIMENSION_WEIGHTS
        },
        "dimension_weights": DIMENSION_WEIGHTS,
        "total_checks": len(check_results),
        "check_details": [
            {
                "check_name": r.check_name,
                "dimension": r.dimension,
                "table": r.table_name,
                "score": round(r.score, 4),
                "total": r.total_records,
                "passed": r.passed_records,
                "failed": r.failed_records,
                "details": r.details,
            }
            for r in check_results
        ],
    }

    logger.info(
        "dq_composite_score",
        composite_score=composite,
        pass_fail=pass_fail,
        threshold=DQ_PASS_THRESHOLD,
        dimension_scores=result["dimension_scores"],
    )

    return result


def run_and_score(conn, run_id: str | None = None) -> dict:
    """
    Execute all DQ checks, compute composite score, and persist to history.

    Args:
        conn: Active database connection.
        run_id: Optional pipeline run ID to link this DQ run to.

    Returns:
        Composite score result dict.
    """
    # Run checks
    check_results = run_all_checks(conn)

    # Compute composite score
    score_result = compute_composite_score(check_results)

    # Persist to history table
    conn.execute(
        """
        INSERT INTO dq_results_history
        (run_id, check_timestamp, completeness_score, uniqueness_score,
         validity_score, timeliness_score, referential_integrity_score,
         composite_dq_score, pass_fail, threshold_used, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            datetime.now(timezone.utc).isoformat(),
            score_result["dimension_scores"]["completeness"],
            score_result["dimension_scores"]["uniqueness"],
            score_result["dimension_scores"]["validity"],
            score_result["dimension_scores"]["timeliness"],
            score_result["dimension_scores"]["referential_integrity"],
            score_result["composite_dq_score"],
            score_result["pass_fail"],
            score_result["threshold"],
            json.dumps(score_result["check_details"]),
        )
    )

    logger.info("dq_results_persisted", composite_score=score_result["composite_dq_score"])
    return score_result
