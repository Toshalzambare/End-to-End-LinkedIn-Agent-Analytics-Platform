# Power BI Data Model — LinkedIn Agent Analytics Platform

## Connecting to the Database

### Option A: ODBC Driver (Recommended)
1. Download and install the [SQLite ODBC Driver](http://www.ch-werner.de/sqliteodbc/)
2. In Power BI Desktop: Get Data > ODBC
3. Connection string: `Driver={SQLite3 ODBC Driver};Database=C:\path\to\data\linkedin_analytics.db;`

### Option B: Export as CSV
1. Run the export script:
```bash
$env:PYTHONPATH='.'; python -c "
import sqlite3, csv, os
conn = sqlite3.connect('data/linkedin_analytics.db')
os.makedirs('data/csv_export', exist_ok=True)
for table in ['dim_date','dim_linkedin_account','dim_campaign','dim_lead','dim_message_template','fact_outreach_activity','fact_daily_account_snapshot','dq_results_history']:
    df = conn.execute(f'SELECT * FROM {table}').fetchall()
    cols = [d[0] for d in conn.execute(f'SELECT * FROM {table}').description]
    with open(f'data/csv_export/{table}.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(df)
print('Exported all tables to data/csv_export/')
"
```
2. In Power BI: Get Data > Text/CSV > Import each file

---

## Table Relationships

Configure these relationships in Power BI's Model View:

| From (Many) | Column | To (One) | Column | Cardinality |
|-------------|--------|----------|--------|-------------|
| fact_outreach_activity | date_key | dim_date | date_key | Many-to-One |
| fact_outreach_activity | account_key | dim_linkedin_account | account_key | Many-to-One |
| fact_outreach_activity | campaign_key | dim_campaign | campaign_key | Many-to-One |
| fact_outreach_activity | lead_key | dim_lead | lead_key | Many-to-One |
| fact_outreach_activity | template_key | dim_message_template | template_key | Many-to-One |
| fact_daily_account_snapshot | date_key | dim_date | date_key | Many-to-One |
| fact_daily_account_snapshot | account_key | dim_linkedin_account | account_key | Many-to-One |

**Important:** For `dim_linkedin_account`, filter the relationship on `is_current = 1` to only show active dimension rows.

---

## Dashboard Pages

### Page 1: Core KPIs
**Purpose:** Executive overview of outreach performance.

**Recommended Visuals:**
- **KPI Cards (top row):** Total Invites Sent, Acceptance Rate, Reply Rate, Conversion Rate, Avg Response Time
- **Line Chart:** Daily invites sent and acceptance rate over time (dual axis)
- **Bar Chart:** Activity type breakdown (invite_sent, message_sent, reply_received, etc.)
- **Gauge:** Throughput vs. daily limits (% of ceiling used)
- **Table:** Last 7 days KPI summary

### Page 2: Account Health
**Purpose:** Per-agent status monitoring.

**Recommended Visuals:**
- **Matrix:** Accounts x Metrics (utilization, acceptance rate, status)
- **Stacked Bar:** Agent status breakdown (Active / Paused / Ghost / Disconnected)
- **Line Chart:** Per-account utilization trend over time
- **Card:** Active agent count, Paused count, Ghost count
- **Conditional formatting:** Red for utilization > 90%, Yellow for > 70%

### Page 3: Risk Intelligence
**Purpose:** Anomaly detection and risk monitoring.

**Recommended Visuals:**
- **Scatter Plot:** Anomaly Score vs. Acceptance Rate (sized by volume, colored by risk_flag)
- **Heat Map:** Account x Date grid, colored by anomaly_score
- **KPI Cards:** Accounts at Warning, Accounts at Critical
- **Line Chart:** Anomaly score trend per account
- **Table:** Risk report with recommended limits vs. tier ceiling

### Page 4: Campaign ROI
**Purpose:** Campaign performance comparison.

**Recommended Visuals:**
- **Bar Chart:** Campaigns ranked by conversion rate
- **Funnel:** Invites Sent > Accepted > Messages > Replies > Conversions
- **Table:** Per-campaign metrics (acceptance rate, reply rate, conversions, avg response time)
- **Slicer:** Filter by target segment, campaign status, date range
- **Donut Chart:** Activity distribution by campaign

---

## Formatting Guidelines

- Use a **dark theme** for professional appearance
- Color palette: Blue (#4A90D9), Green (#2ECC71), Yellow (#F1C40F), Red (#E74C3C)
- Card backgrounds: Semi-transparent with rounded corners
- All numbers should be formatted (e.g., 23.5% not 0.235, 1,234 not 1234)
- Include the company/assessment title in the header of each page
