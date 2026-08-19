"""
Anomaly Detection — Statistical anomaly scoring for LinkedIn agent behavior.
Part 5: Advanced Analytics & Risk Modeling.

Statistical Basis:
- Modified Z-Score (uses median & MAD for robustness against outliers)
- IQR-based outlier detection (Tukey fences)
- Composite anomaly score combining multiple signals

Why these methods:
- LinkedIn outreach data is typically right-skewed (most days are normal, a few are extreme).
- Modified Z-Score is robust to the very outliers we're trying to detect (unlike mean-based Z-Score).
- IQR provides a distribution-free boundary that works on non-normal data.
- Combining both methods reduces false positives from any single technique.

Signals monitored:
1. Acceptance-rate collapse — sudden drop in invite acceptance rate
2. Reply decay — declining reply rate over time
3. Ghosting patterns — leads that accept but never reply
4. Utilization spikes — sending at/above daily limits
"""

import numpy as np
import pandas as pd
from scipy import stats
import structlog

logger = structlog.get_logger()


def modified_z_score(data: np.ndarray) -> np.ndarray:
    """
    Compute Modified Z-Scores using median and MAD (Median Absolute Deviation).

    The modified Z-score is more robust than the standard Z-score because
    it uses the median instead of the mean, making it resistant to the
    very outliers it aims to detect.

    Formula: M_i = 0.6745 * (x_i - median) / MAD
    Threshold: |M_i| > 3.5 is typically considered an outlier (Iglewicz & Hoaglin, 1993).

    Args:
        data: Array of numeric values.

    Returns:
        Array of modified Z-scores.
    """
    median = np.median(data)
    mad = np.median(np.abs(data - median))

    if mad == 0:
        # All values are identical — no anomalies
        return np.zeros_like(data, dtype=float)

    return 0.6745 * (data - median) / mad


def iqr_outlier_flags(data: np.ndarray, k: float = 1.5) -> np.ndarray:
    """
    Flag outliers using Tukey's IQR fences.

    Lower fence: Q1 - k * IQR
    Upper fence: Q3 + k * IQR

    Args:
        data: Array of numeric values.
        k: Fence multiplier (1.5 = outlier, 3.0 = extreme outlier).

    Returns:
        Boolean array where True = outlier.
    """
    q1 = np.percentile(data, 25)
    q3 = np.percentile(data, 75)
    iqr = q3 - q1

    lower = q1 - k * iqr
    upper = q3 + k * iqr

    return (data < lower) | (data > upper)


def compute_anomaly_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute composite anomaly scores for daily account snapshots.

    Input DataFrame must contain:
    - date_key, account_key
    - acceptance_rate, reply_rate
    - invite_utilization, message_utilization
    - invites_sent, messages_sent

    Algorithm:
    1. For each metric, compute modified Z-score
    2. Flag IQR outliers
    3. Combine into a composite score (weighted average of absolute Z-scores)
    4. Classify: Normal (< 2.0), Warning (2.0–3.5), Critical (> 3.5)

    Returns:
        DataFrame with added columns: anomaly_score, risk_flag, and per-metric Z-scores.
    """
    if df.empty:
        logger.warning("anomaly_detection_empty_input")
        return df

    result = df.copy()

    # Metrics to analyze (column, weight, direction)
    # direction: 'low_bad' means low values are anomalous (rate collapse)
    #            'high_bad' means high values are anomalous (over-utilization)
    metrics = [
        ("acceptance_rate", 0.30, "low_bad"),    # Acceptance collapse is the top risk
        ("reply_rate", 0.25, "low_bad"),          # Reply decay
        ("invite_utilization", 0.20, "high_bad"), # Over-utilization
        ("message_utilization", 0.15, "high_bad"),
        ("ghost_rate", 0.10, "high_bad"),         # Ghosting
    ]

    # Compute ghost_rate if not present (accepted but never replied)
    if "ghost_rate" not in result.columns:
        accepted = result["invites_accepted"].fillna(0)
        replied = result["replies_received"].fillna(0)
        result["ghost_rate"] = np.where(
            accepted > 0,
            1.0 - (replied / accepted),
            0.0
        )

    # Compute Z-scores and IQR flags for each metric
    weighted_scores = np.zeros(len(result))
    total_weight = 0.0

    for col, weight, direction in metrics:
        if col not in result.columns:
            logger.debug("anomaly_metric_missing", metric=col)
            continue

        values = result[col].fillna(0).values.astype(float)

        if len(values) < 5:
            # Not enough data points for meaningful statistics
            logger.debug("anomaly_insufficient_data", metric=col, n=len(values))
            result[f"z_{col}"] = 0.0
            continue

        z_scores = modified_z_score(values)

        # For 'low_bad' metrics, negate so that low values produce positive anomaly scores
        if direction == "low_bad":
            z_scores = -z_scores

        # Clamp negative Z-scores to 0 (we only care about the anomalous direction)
        z_scores = np.clip(z_scores, 0, None)

        result[f"z_{col}"] = np.round(z_scores, 4)

        # IQR flag (additional confirmation)
        iqr_flags = iqr_outlier_flags(values)
        result[f"iqr_outlier_{col}"] = iqr_flags.astype(int)

        # Accumulate weighted score
        weighted_scores += z_scores * weight
        total_weight += weight

    # Normalize composite score
    if total_weight > 0:
        result["anomaly_score"] = np.round(weighted_scores / total_weight, 4)
    else:
        result["anomaly_score"] = 0.0

    # Risk classification
    result["risk_flag"] = pd.cut(
        result["anomaly_score"],
        bins=[-np.inf, 2.0, 3.5, np.inf],
        labels=["Normal", "Warning", "Critical"],
    )

    logger.info(
        "anomaly_detection_complete",
        total_records=len(result),
        warnings=int((result["risk_flag"] == "Warning").sum()),
        critical=int((result["risk_flag"] == "Critical").sum()),
    )

    return result


def detect_acceptance_collapse(df: pd.DataFrame, window: int = 7, threshold: float = 0.3) -> pd.DataFrame:
    """
    Detect acceptance-rate collapse: a sudden drop in acceptance rate
    relative to the rolling average.

    Args:
        df: DataFrame with 'acceptance_rate' and 'date_key' columns, sorted by date.
        window: Rolling window size (days).
        threshold: Fractional drop to flag (0.3 = 30% drop from rolling avg).

    Returns:
        DataFrame with 'acceptance_collapse' boolean column added.
    """
    if df.empty or "acceptance_rate" not in df.columns:
        return df

    result = df.copy().sort_values("date_key")
    rolling_avg = result["acceptance_rate"].rolling(window=window, min_periods=3).mean()

    # Flag where current rate is more than `threshold` fraction below rolling average
    result["acceptance_collapse"] = (
        (rolling_avg - result["acceptance_rate"]) / rolling_avg.clip(lower=0.01)
    ) > threshold

    return result


def detect_reply_decay(df: pd.DataFrame, window: int = 7) -> pd.DataFrame:
    """
    Detect reply decay: a sustained downward trend in reply rate.

    Uses linear regression over a rolling window. A negative slope
    with R² > 0.5 indicates a meaningful decay.

    Returns:
        DataFrame with 'reply_decay' boolean and 'reply_trend_slope' columns.
    """
    if df.empty or "reply_rate" not in df.columns:
        return df

    result = df.copy().sort_values("date_key")
    slopes = []
    decay_flags = []

    values = result["reply_rate"].fillna(0).values

    for i in range(len(values)):
        if i < window - 1:
            slopes.append(0.0)
            decay_flags.append(False)
            continue

        window_data = values[i - window + 1 : i + 1]
        x = np.arange(len(window_data))

        if np.std(window_data) == 0:
            slopes.append(0.0)
            decay_flags.append(False)
            continue

        slope, _, r_value, _, _ = stats.linregress(x, window_data)
        r_squared = r_value ** 2

        slopes.append(round(slope, 6))
        decay_flags.append(slope < 0 and r_squared > 0.5)

    result["reply_trend_slope"] = slopes
    result["reply_decay"] = decay_flags

    return result
