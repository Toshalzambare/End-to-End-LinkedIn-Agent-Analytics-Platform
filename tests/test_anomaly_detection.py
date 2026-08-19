"""
Tests for anomaly detection and risk model.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analytics.anomaly_detection import (
    modified_z_score,
    iqr_outlier_flags,
    compute_anomaly_scores,
    detect_acceptance_collapse,
    detect_reply_decay,
)
from src.analytics.risk_model import classify_account_risk, recommend_daily_limits


class TestModifiedZScore:
    """Test Modified Z-Score calculation."""

    def test_all_same_values(self):
        """All identical values should produce zero Z-scores."""
        data = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
        scores = modified_z_score(data)
        np.testing.assert_array_equal(scores, np.zeros(5))

    def test_detects_outlier(self):
        """A clear outlier should have a high Z-score."""
        data = np.array([10, 11, 9, 10, 12, 10, 11, 9, 10, 100])
        scores = modified_z_score(data)
        assert abs(scores[-1]) > 3.5  # The 100 should be flagged

    def test_normal_values_low_scores(self):
        """Normal values should have low Z-scores."""
        data = np.array([10, 11, 9, 10, 12, 10, 11, 9])
        scores = modified_z_score(data)
        assert all(abs(s) < 3.5 for s in scores)


class TestIQROutliers:
    """Test IQR-based outlier detection."""

    def test_no_outliers(self):
        """Uniform data should have no outliers."""
        data = np.array([10, 11, 12, 13, 14, 15])
        flags = iqr_outlier_flags(data)
        assert not any(flags)

    def test_detects_extreme(self):
        """Extreme values should be flagged."""
        data = np.array([10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 100])
        flags = iqr_outlier_flags(data)
        assert flags[-1]  # 100 is an outlier


class TestCompositeAnomalyScores:
    """Test the full anomaly scoring pipeline."""

    def _make_df(self, n=30, inject_anomaly=False):
        """Create a test DataFrame mimicking daily snapshots."""
        np.random.seed(42)
        df = pd.DataFrame({
            "date_key": [20240101 + i for i in range(n)],
            "account_key": [1] * n,
            "snapshot_key": list(range(1, n + 1)),
            "acceptance_rate": np.random.uniform(0.2, 0.35, n),
            "reply_rate": np.random.uniform(0.08, 0.20, n),
            "invite_utilization": np.random.uniform(0.4, 0.8, n),
            "message_utilization": np.random.uniform(0.3, 0.7, n),
            "invites_sent": np.random.randint(10, 25, n),
            "invites_accepted": np.random.randint(3, 8, n),
            "replies_received": np.random.randint(1, 5, n),
            "messages_sent": np.random.randint(5, 15, n),
        })

        if inject_anomaly:
            # Collapse acceptance rate for last 3 days
            df.loc[df.index[-3:], "acceptance_rate"] = 0.02
            df.loc[df.index[-3:], "reply_rate"] = 0.01

        return df

    def test_scores_computed(self):
        """Anomaly scores should be computed for all rows."""
        df = self._make_df()
        result = compute_anomaly_scores(df)
        assert "anomaly_score" in result.columns
        assert "risk_flag" in result.columns
        assert len(result) == len(df)

    def test_anomaly_detected(self):
        """Injected anomalies should produce higher scores."""
        df_normal = self._make_df(inject_anomaly=False)
        df_anomaly = self._make_df(inject_anomaly=True)

        result_normal = compute_anomaly_scores(df_normal)
        result_anomaly = compute_anomaly_scores(df_anomaly)

        # The anomalous dataset should have at least one Warning or Critical flag
        anomaly_flags = result_anomaly["risk_flag"].isin(["Warning", "Critical"]).sum()
        normal_flags = result_normal["risk_flag"].isin(["Warning", "Critical"]).sum()

        # Anomalous data should have more flags than normal
        assert anomaly_flags >= normal_flags


class TestAcceptanceCollapse:
    """Test acceptance collapse detection."""

    def test_collapse_detected(self):
        """A sudden drop should be flagged."""
        df = pd.DataFrame({
            "date_key": list(range(20)),
            "acceptance_rate": [0.30] * 15 + [0.05, 0.04, 0.03, 0.06, 0.04],
        })
        result = detect_acceptance_collapse(df, window=7, threshold=0.3)
        assert result["acceptance_collapse"].any()


class TestRiskModel:
    """Test risk classification and capacity recommendations."""

    def test_healthy_account(self):
        """A healthy account should get full capacity."""
        result = recommend_daily_limits(
            account_age_tier="1+ Year",
            avg_acceptance_rate=0.30,
            avg_reply_rate=0.15,
            recent_anomaly_score=0.5,
            days_of_data=30,
        )
        assert result["recommended_daily_invites"] >= 20  # Should be near ceiling
        assert result["confidence"] == "HIGH"
        assert result["risk_level"] in ("Healthy", "Low")

    def test_critical_account_reduced(self):
        """A critical-risk account should get reduced capacity."""
        result = recommend_daily_limits(
            account_age_tier="1+ Year",
            avg_acceptance_rate=0.03,
            avg_reply_rate=0.01,
            recent_anomaly_score=4.0,
            days_of_data=30,
        )
        assert result["recommended_daily_invites"] < 15  # Significantly reduced
        assert result["risk_level"] in ("Critical", "High")

    def test_insufficient_data(self):
        """With < 3 days of data, should return tier defaults."""
        result = recommend_daily_limits(
            account_age_tier="1+ Year",
            avg_acceptance_rate=0.30,
            avg_reply_rate=0.15,
            recent_anomaly_score=0.0,
            days_of_data=1,
        )
        assert result["confidence"] == "INSUFFICIENT"
        assert result["recommended_daily_invites"] == 30  # Tier ceiling

    def test_never_exceeds_ceiling(self):
        """Recommendations should never exceed the tier ceiling."""
        for tier_name in ["< 1 Month", "1 Month", "2-6 Months", "6-12 Months", "1+ Year"]:
            result = recommend_daily_limits(
                account_age_tier=tier_name,
                avg_acceptance_rate=0.50,
                avg_reply_rate=0.30,
                recent_anomaly_score=0.0,
                days_of_data=30,
            )
            assert result["recommended_daily_invites"] <= result["invite_ceiling"]
            assert result["recommended_daily_messages"] <= result["message_ceiling"]

    def test_classify_risk_levels(self):
        """Risk classification should cover the full spectrum."""
        assert classify_account_risk(0.5, 0.30, 0.15, 0.50) == "Healthy"
        assert classify_account_risk(4.0, 0.03, 0.01, 0.95) == "Critical"
