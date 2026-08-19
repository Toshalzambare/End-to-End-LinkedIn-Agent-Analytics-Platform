# Risk Model Documentation — LinkedIn Agent Analytics Platform

## Part 5: Advanced Analytics & Risk Modeling

---

## 1. Statistical Basis

### Method: Modified Z-Score + IQR Hybrid Anomaly Detection

We use a **two-method ensemble** to identify anomalous agent behavior:

#### 1.1 Modified Z-Score (Primary)

**Formula:** `M_i = 0.6745 × (x_i - median) / MAD`

Where:
- `x_i` = observed value
- `median` = median of the dataset
- `MAD` = Median Absolute Deviation

**Why Modified Z-Score (not standard Z-Score)?**
- LinkedIn outreach data is **right-skewed** — most days are normal, a few are extreme.
- The standard Z-score uses the mean, which is **pulled toward outliers**, reducing sensitivity.
- The Modified Z-score uses the **median**, which is robust to the very outliers we're detecting.
- This is the recommended approach per Iglewicz & Hoaglin (1993).

**Threshold:** |M_i| > 3.5 → anomalous (industry standard for Modified Z-Score).

#### 1.2 IQR (Tukey Fences) (Confirmatory)

**Formula:**
- Lower fence: `Q1 - 1.5 × IQR`
- Upper fence: `Q3 + 1.5 × IQR`

Where `IQR = Q3 - Q1`.

**Why IQR in addition to Z-Score?**
- Provides a **distribution-free** boundary that works regardless of data normality.
- Acts as a confirmatory signal — points flagged by both methods have higher confidence.

### 1.3 Composite Anomaly Score

The composite score is a **weighted average** of per-metric Modified Z-scores:

| Signal | Weight | Direction | Rationale |
|--------|--------|-----------|-----------|
| Acceptance Rate | 30% | Low = bad | Acceptance collapse is the top LinkedIn shadow-ban indicator |
| Reply Rate | 25% | Low = bad | Reply decay signals audience disengagement or content issues |
| Invite Utilization | 20% | High = bad | Over-utilization risks triggering platform rate-limiting |
| Message Utilization | 15% | High = bad | Similar to invite utilization |
| Ghost Rate | 10% | High = bad | High acceptance but zero replies = ghosting pattern |

**Classification:**
- **Normal:** Composite score < 2.0
- **Warning:** 2.0 ≤ score ≤ 3.5
- **Critical:** score > 3.5

---

## 2. Risk Signals Detected

### 2.1 Acceptance-Rate Collapse
- **Definition:** Current acceptance rate drops > 30% below the 7-day rolling average.
- **Significance:** The strongest leading indicator of LinkedIn shadow-banning or algorithmic suppression.
- **Detection:** Rolling window comparison with configurable threshold.

### 2.2 Reply Decay
- **Definition:** A sustained negative trend in reply rate over a 7-day window.
- **Significance:** Indicates audience fatigue, poor targeting, or template degradation.
- **Detection:** Linear regression over rolling window; flagged if slope < 0 and R² > 0.5.

### 2.3 Ghosting Patterns
- **Definition:** `Ghost Rate = 1 - (replies / accepts)` — leads who accept but never reply.
- **Significance:** High ghosting suggests the account is being "soft-blocked" or leads are accepting out of curiosity but finding no value.
- **Detection:** Included in the composite anomaly score with 10% weight.

### 2.4 Utilization Spikes
- **Definition:** Sending invites or messages at or above 95% of the daily limit.
- **Significance:** Operating at limit ceiling increases the risk of triggering platform-level throttling.
- **Detection:** `invite_utilization = invites_sent / daily_invite_limit`.

---

## 3. Capacity Recommendations

### Algorithm

1. **Start from the tier ceiling** (hard maximum from Part 1).
2. **Apply a safety factor** (0.0 to 1.0) based on risk signals.
3. **Never exceed the tier ceiling.**
4. **Minimum recommendation:** 1 invite/message per day.

### Safety Factor Penalties

| Signal | Condition | Penalty |
|--------|-----------|---------|
| Anomaly Score | > 3.5 (Critical) | × 0.40 |
| Anomaly Score | 2.0–3.5 (Warning) | × 0.65 |
| Anomaly Score | 1.0–2.0 (Mild) | × 0.85 |
| Acceptance Rate | < 5% | × 0.50 |
| Acceptance Rate | 5–10% | × 0.70 |
| Acceptance Rate | 10–20% | × 0.85 |
| Reply Rate | < 2% | × 0.75 |
| Reply Rate | 2–5% | × 0.90 |
| Confidence | LOW (3–6 days) | × 0.80 |
| Confidence | MEDIUM (7–13 days) | × 0.90 |

Safety factors are multiplicative — multiple penalties compound.

### Confidence Levels

| Level | Days of Data | Meaning |
|-------|-------------|---------|
| **HIGH** | 14+ days | Strong statistical basis |
| **MEDIUM** | 7–13 days | Moderate confidence |
| **LOW** | 3–6 days | Limited data, extra conservative |
| **INSUFFICIENT** | < 3 days | Use tier defaults only |

---

## 4. Assumptions

1. **Data stationarity:** We assume outreach patterns are roughly stationary within the analysis window (no seasonal or structural breaks beyond anomalies).
2. **Independence:** Daily observations are assumed independent. In reality, consecutive days may have serial correlation (e.g., weekday patterns).
3. **Tier limits are correct:** We trust the account age tier selection from Part 1 as the true hard ceiling.
4. **API data completeness:** We assume the Polluxa API returns all events without silent data loss.

## 5. Known Limitations

1. **Small sample sizes:** With < 14 days of data, statistical power is limited and Z-scores may be unreliable.
2. **No causal inference:** Anomaly detection is purely observational — it identifies correlations, not root causes.
3. **LinkedIn black box:** We cannot observe LinkedIn's internal algorithms. Shadow-banning may occur without visible metrics changes.
4. **Weekend effects:** Reduced weekend activity may inflate utilization spikes on Mondays if not accounted for.
5. **Template variable:** Message content quality (not modeled) may significantly affect acceptance/reply rates independently of volume.
