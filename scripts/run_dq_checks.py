"""
Standalone DQ Check Runner — Execute data quality checks independently.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.logging_config import setup_logging
from src.database.db_manager import get_db_session
from src.quality.dq_scorer import run_and_score


def main():
    logger = setup_logging()
    logger.info("dq_runner_start")

    with get_db_session() as conn:
        result = run_and_score(conn)

    print("\n" + "=" * 60)
    print("DATA QUALITY REPORT")
    print("=" * 60)
    print(f"\n  Composite Score: {result['composite_dq_score']:.4f}")
    print(f"  Threshold:      {result['threshold']}")
    print(f"  Result:         {result['pass_fail']}")
    print(f"\n  Dimension Scores:")
    for dim, score in result["dimension_scores"].items():
        weight = result["dimension_weights"][dim]
        print(f"    {dim:30s} {score:.4f}  (weight: {weight:.0%})")

    print(f"\n  Individual Checks ({result['total_checks']} total):")
    for check in result["check_details"]:
        status = "✅" if check["score"] >= 0.85 else "⚠️" if check["score"] >= 0.5 else "❌"
        print(f"    {status} {check['check_name']:40s} {check['score']:.4f}  ({check['details'][:60]})")

    print("\n" + "=" * 60)

    if result["pass_fail"] == "FAIL":
        logger.warning("dq_check_failed", composite_score=result["composite_dq_score"])
        sys.exit(1)
    else:
        logger.info("dq_check_passed", composite_score=result["composite_dq_score"])


if __name__ == "__main__":
    main()
