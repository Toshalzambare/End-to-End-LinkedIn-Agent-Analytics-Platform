# Power BI DAX Measures — LinkedIn Agent Analytics Platform

## Part 6: Power BI Engineering

All measures below are **explicit DAX** — no implicit aggregations.
Copy each measure into Power BI Desktop's modeling pane.

---

## 1. Core KPI Measures

### Total Invites Sent
```dax
Total Invites Sent = 
CALCULATE(
    COUNTROWS(fact_outreach_activity),
    fact_outreach_activity[activity_type] = "invite_sent"
)
```

### Total Invites Accepted
```dax
Total Invites Accepted = 
CALCULATE(
    COUNTROWS(fact_outreach_activity),
    fact_outreach_activity[activity_type] = "invite_accepted"
)
```

### Total Messages Sent
```dax
Total Messages Sent = 
CALCULATE(
    COUNTROWS(fact_outreach_activity),
    fact_outreach_activity[activity_type] = "message_sent"
)
```

### Total Replies Received
```dax
Total Replies Received = 
CALCULATE(
    COUNTROWS(fact_outreach_activity),
    fact_outreach_activity[activity_type] = "reply_received"
)
```

### Total Follow-Ups Sent
```dax
Total Follow-Ups = 
CALCULATE(
    COUNTROWS(fact_outreach_activity),
    fact_outreach_activity[activity_type] = "follow_up_sent"
)
```

### Total Conversions
```dax
Total Conversions = 
SUM(fact_outreach_activity[is_converted])
```

### Acceptance Rate
```dax
Acceptance Rate = 
DIVIDE(
    [Total Invites Accepted],
    [Total Invites Sent],
    0
)
```

### Reply Rate
```dax
Reply Rate = 
DIVIDE(
    [Total Replies Received],
    [Total Messages Sent],
    0
)
```

### Conversion Rate
```dax
Conversion Rate = 
DIVIDE(
    [Total Conversions],
    [Total Invites Sent] + [Total Messages Sent],
    0
)
```

### Average Response Time (Hours)
```dax
Avg Response Time = 
AVERAGE(fact_outreach_activity[response_time_hours])
```

---

## 2. Account Health Measures

### Active Agents Count
```dax
Active Agents = 
CALCULATE(
    COUNTROWS(dim_linkedin_account),
    dim_linkedin_account[agent_status] = "Active",
    dim_linkedin_account[is_current] = 1
)
```

### Paused Agents Count
```dax
Paused Agents = 
CALCULATE(
    COUNTROWS(dim_linkedin_account),
    dim_linkedin_account[agent_status] = "Paused",
    dim_linkedin_account[is_current] = 1
)
```

### Ghost Agents Count
```dax
Ghost Agents = 
CALCULATE(
    COUNTROWS(dim_linkedin_account),
    dim_linkedin_account[agent_status] = "Ghost",
    dim_linkedin_account[is_current] = 1
)
```

### Average Invite Utilization
```dax
Avg Invite Utilization = 
AVERAGE(fact_daily_account_snapshot[invite_utilization])
```

### Average Message Utilization
```dax
Avg Message Utilization = 
AVERAGE(fact_daily_account_snapshot[message_utilization])
```

### Throughput vs. Limit (Invites)
```dax
Invite Throughput % = 
DIVIDE(
    SUM(fact_daily_account_snapshot[invites_sent]),
    SUMX(
        fact_daily_account_snapshot,
        RELATED(dim_linkedin_account[daily_invite_limit])
    ),
    0
)
```

---

## 3. Risk Intelligence Measures

### Average Anomaly Score
```dax
Avg Anomaly Score = 
AVERAGE(fact_daily_account_snapshot[anomaly_score])
```

### Max Anomaly Score
```dax
Max Anomaly Score = 
MAX(fact_daily_account_snapshot[anomaly_score])
```

### Accounts at Warning
```dax
Warning Accounts = 
CALCULATE(
    DISTINCTCOUNT(fact_daily_account_snapshot[account_key]),
    fact_daily_account_snapshot[risk_flag] = "Warning"
)
```

### Accounts at Critical
```dax
Critical Accounts = 
CALCULATE(
    DISTINCTCOUNT(fact_daily_account_snapshot[account_key]),
    fact_daily_account_snapshot[risk_flag] = "Critical"
)
```

### Risk Score KPI (with conditional formatting)
```dax
Risk Score KPI = 
VAR AvgScore = [Avg Anomaly Score]
RETURN
    IF(AvgScore > 3.5, 3,      -- Critical (Red)
    IF(AvgScore > 2.0, 2,      -- Warning (Yellow)
    1))                         -- Normal (Green)
```

---

## 4. Campaign ROI Measures

### Campaign Acceptance Rate
```dax
Campaign Acceptance Rate = 
DIVIDE(
    CALCULATE(COUNTROWS(fact_outreach_activity), fact_outreach_activity[activity_type] = "invite_accepted"),
    CALCULATE(COUNTROWS(fact_outreach_activity), fact_outreach_activity[activity_type] = "invite_sent"),
    0
)
```

### Campaign Reply Rate
```dax
Campaign Reply Rate = 
DIVIDE(
    CALCULATE(COUNTROWS(fact_outreach_activity), fact_outreach_activity[activity_type] = "reply_received"),
    CALCULATE(COUNTROWS(fact_outreach_activity), fact_outreach_activity[activity_type] = "message_sent"),
    0
)
```

### Campaign Conversion Rate
```dax
Campaign Conversion Rate = 
DIVIDE(
    SUM(fact_outreach_activity[is_converted]),
    COUNTROWS(fact_outreach_activity),
    0
)
```

### Best Performing Campaign
```dax
Best Campaign = 
TOPN(1, VALUES(dim_campaign[campaign_name]), [Campaign Conversion Rate], DESC)
```

---

## 5. Time Intelligence Measures

### Invites Sent (Rolling 7 Days)
```dax
Invites 7D Rolling = 
CALCULATE(
    [Total Invites Sent],
    DATESINPERIOD(dim_date[full_date], MAX(dim_date[full_date]), -7, DAY)
)
```

### Acceptance Rate Trend (Rolling 7 Days)
```dax
Accept Rate 7D Rolling = 
CALCULATE(
    [Acceptance Rate],
    DATESINPERIOD(dim_date[full_date], MAX(dim_date[full_date]), -7, DAY)
)
```

### Week over Week Change
```dax
WoW Invites Change = 
VAR CurrentWeek = [Total Invites Sent]
VAR PriorWeek = 
    CALCULATE(
        [Total Invites Sent],
        DATEADD(dim_date[full_date], -7, DAY)
    )
RETURN
    DIVIDE(CurrentWeek - PriorWeek, PriorWeek, 0)
```

---

## 6. Data Quality Measures

### Latest DQ Score
```dax
Latest DQ Score = 
CALCULATE(
    MAX(dq_results_history[composite_dq_score]),
    LASTDATE(dq_results_history[check_timestamp])
)
```

### DQ Pass/Fail Status
```dax
DQ Status = 
VAR LatestScore = [Latest DQ Score]
RETURN
    IF(LatestScore >= 0.85, "PASS", "FAIL")
```

---

## How to Use in Power BI

1. Open Power BI Desktop
2. Connect to the SQLite database file (`data/linkedin_analytics.db`)
   - Use ODBC driver for SQLite, or export tables as CSV files first
3. Import all tables (dim_date, dim_linkedin_account, dim_campaign, dim_lead, fact_outreach_activity, fact_daily_account_snapshot, dq_results_history)
4. Create relationships as documented in `data_model.md`
5. Go to **Modeling → New Measure** and paste each DAX formula above
6. Build visuals using these measures on 4 dashboard pages:
   - **Page 1: Core KPIs** (cards, line charts, gauges)
   - **Page 2: Account Health** (matrix, bar charts, status indicators)
   - **Page 3: Risk Intelligence** (scatter plot, heat map, KPI cards)
   - **Page 4: Campaign ROI** (bar charts, funnel, comparison tables)
