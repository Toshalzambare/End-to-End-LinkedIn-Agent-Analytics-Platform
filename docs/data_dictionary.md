# Data Dictionary — LinkedIn Agent Analytics Platform

## Part 3: Data Architecture & Modeling

Every column, type, and business definition for all tables in the Star Schema.

---

## Dimension Tables

### dim_date

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| date_key | INTEGER (PK) | No | Surrogate key in YYYYMMDD format (e.g., 20240115) |
| full_date | TEXT | No | ISO date string 'YYYY-MM-DD' |
| day_of_week | INTEGER | No | 0=Monday through 6=Sunday |
| day_name | TEXT | No | Full day name (e.g., 'Monday') |
| day_of_month | INTEGER | No | Day number within the month (1–31) |
| week_of_year | INTEGER | No | ISO week number (1–53) |
| month_number | INTEGER | No | Month number (1–12) |
| month_name | TEXT | No | Full month name (e.g., 'January') |
| quarter | INTEGER | No | Calendar quarter (1–4) |
| year | INTEGER | No | Four-digit year |
| is_weekend | INTEGER | No | 1 if Saturday or Sunday, else 0 |

---

### dim_linkedin_account

**SCD Type 2** — Historical changes tracked via effective_from/effective_to/is_current.

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| account_key | INTEGER (PK, auto) | No | Surrogate key (auto-incremented) |
| account_id | TEXT | No | Natural key — unique agent ID from Polluxa platform |
| account_email | TEXT | Yes | Email address linked to the LinkedIn account |
| account_name | TEXT | Yes | Display name of the account owner |
| account_age_tier | TEXT | No | Age classification: '< 1 Month', '1 Month', '2-6 Months', '6-12 Months', '1+ Year' |
| risk_classification | TEXT | No | Risk level derived from account age: 'Very High Risk' to 'Minimal Risk' |
| daily_invite_limit | INTEGER | No | Maximum daily invites allowed by the tier |
| daily_message_limit | INTEGER | No | Maximum daily messages allowed by the tier |
| agent_status | TEXT | No | Current agent state: 'Active', 'Paused', 'Ghost', 'Disconnected' |
| effective_from | TEXT | No | SCD2: Start datetime of this version |
| effective_to | TEXT | Yes | SCD2: End datetime of this version ('9999-12-31' if current) |
| is_current | INTEGER | No | SCD2: 1 = active version, 0 = historical |
| created_at | TEXT | No | Record creation timestamp |
| updated_at | TEXT | No | Last modification timestamp |

---

### dim_campaign

**SCD Type 1** — Overwrite on change (campaigns are mutable labels).

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| campaign_key | INTEGER (PK, auto) | No | Surrogate key |
| campaign_id | TEXT | No | Natural key — unique campaign ID from Polluxa |
| campaign_name | TEXT | No | Human-readable campaign name |
| target_segment | TEXT | Yes | Target audience segment (e.g., 'Recruiters', 'Founders') |
| description | TEXT | Yes | Campaign description or objective |
| status | TEXT | No | Campaign status: 'Active', 'Paused', 'Completed' |
| created_date | TEXT | Yes | Date the campaign was created |
| created_at | TEXT | No | Record creation timestamp |
| updated_at | TEXT | No | Last modification timestamp |

---

### dim_lead

**SCD Type 1** — Overwrite on change.

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| lead_key | INTEGER (PK, auto) | No | Surrogate key |
| lead_id | TEXT | No | Natural key — unique lead ID from Polluxa |
| linkedin_url | TEXT | Yes | Full LinkedIn profile URL |
| full_name | TEXT | Yes | Lead's full name |
| job_title | TEXT | Yes | Current job title |
| company | TEXT | Yes | Current employer |
| location | TEXT | Yes | Geographic location |
| industry | TEXT | Yes | Industry classification |
| created_at | TEXT | No | Record creation timestamp |
| updated_at | TEXT | No | Last modification timestamp |

---

### dim_message_template

**SCD Type 1** — Overwrite on change.

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| template_key | INTEGER (PK, auto) | No | Surrogate key |
| template_id | TEXT | No | Natural key — unique template ID |
| template_name | TEXT | Yes | Template display name |
| template_body | TEXT | Yes | Full template text with placeholders |
| template_type | TEXT | No | Template category: 'Connection', 'Follow-Up', 'InMail' |
| created_at | TEXT | No | Record creation timestamp |
| updated_at | TEXT | No | Last modification timestamp |

---

## Fact Tables

### fact_outreach_activity

**Grain:** One row per individual outreach action (invite sent, message sent, etc.)

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| activity_key | INTEGER (PK, auto) | No | Surrogate key |
| activity_id | TEXT | No | Natural key — unique event ID from Polluxa (idempotency anchor) |
| date_key | INTEGER (FK → dim_date) | No | Date when the activity occurred |
| account_key | INTEGER (FK → dim_linkedin_account) | No | The LinkedIn agent that performed the action |
| campaign_key | INTEGER (FK → dim_campaign) | Yes | Campaign this activity belongs to (NULL if unassigned) |
| lead_key | INTEGER (FK → dim_lead) | Yes | Target lead (NULL if not applicable) |
| template_key | INTEGER (FK → dim_message_template) | Yes | Message template used (NULL if none) |
| activity_type | TEXT | No | Event type: 'invite_sent', 'invite_accepted', 'message_sent', 'reply_received', 'follow_up_sent' |
| activity_timestamp | TEXT | No | Exact ISO datetime when the event occurred |
| is_accepted | INTEGER | Yes | 1 if the invite was accepted, 0 otherwise |
| is_replied | INTEGER | Yes | 1 if the message received a reply |
| is_converted | INTEGER | Yes | 1 if the lead converted (meeting booked, goal achieved) |
| response_time_hours | REAL | Yes | Hours between outreach send and response (NULL if no response) |
| loaded_at | TEXT | No | Timestamp when this record was loaded into the database |
| source_system | TEXT | No | Origin system: 'polluxa_api' |

---

### fact_daily_account_snapshot

**Grain:** One row per account per day (periodic snapshot)

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| snapshot_key | INTEGER (PK, auto) | No | Surrogate key |
| date_key | INTEGER (FK → dim_date) | No | The snapshot date |
| account_key | INTEGER (FK → dim_linkedin_account) | No | The LinkedIn agent account |
| invites_sent | INTEGER | No | Number of invites sent on this day |
| invites_accepted | INTEGER | No | Number of invites accepted on this day |
| messages_sent | INTEGER | No | Number of messages sent on this day |
| replies_received | INTEGER | No | Number of replies received on this day |
| follow_ups_sent | INTEGER | No | Number of follow-up messages sent |
| conversions | INTEGER | No | Number of conversions achieved |
| acceptance_rate | REAL | Yes | invites_accepted / invites_sent (pre-computed) |
| reply_rate | REAL | Yes | replies_received / messages_sent (pre-computed) |
| conversion_rate | REAL | Yes | conversions / total_interactions (pre-computed) |
| invite_utilization | REAL | Yes | invites_sent / daily_invite_limit (0.0 to 1.0+) |
| message_utilization | REAL | Yes | messages_sent / daily_message_limit (0.0 to 1.0+) |
| anomaly_score | REAL | Yes | Composite anomaly score from Part 5 analytics |
| risk_flag | TEXT | Yes | Risk classification: 'Normal', 'Warning', 'Critical' |
| loaded_at | TEXT | No | Record load timestamp |

---

## Operational Tables

### pipeline_run_log

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| run_id | TEXT (PK) | No | UUID identifying this pipeline execution |
| correlation_id | TEXT | No | Matches structured log entries for end-to-end tracing |
| run_type | TEXT | No | 'full' or 'incremental' |
| status | TEXT | No | 'running', 'success', 'failed', 'partial' |
| started_at | TEXT | No | ISO datetime when the run started |
| ended_at | TEXT | Yes | ISO datetime when the run ended |
| rows_extracted | INTEGER | Yes | Total rows extracted from the API |
| rows_loaded | INTEGER | Yes | Total rows successfully loaded |
| rows_rejected | INTEGER | Yes | Total rows sent to dead-letter queue |
| error_message | TEXT | Yes | Error description if the run failed |
| watermark_value | TEXT | Yes | Last processed timestamp for incremental loads |

### dead_letter_queue

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| dlq_id | INTEGER (PK, auto) | No | Surrogate key |
| run_id | TEXT (FK → pipeline_run_log) | No | Pipeline run that produced this failure |
| record_payload | TEXT | No | JSON of the failed record |
| error_type | TEXT | No | 'validation', 'transformation', 'load', 'api' |
| error_message | TEXT | No | Human-readable error description |
| failed_at | TEXT | No | Timestamp of the failure |
| retried | INTEGER | No | 1 if successfully retried, 0 otherwise |
| retried_at | TEXT | Yes | Timestamp of successful retry |

### ingestion_watermark

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| entity_name | TEXT (PK) | No | Entity being tracked: 'outreach_activity', 'leads' |
| last_watermark | TEXT | No | ISO datetime of the last successfully processed record |
| updated_at | TEXT | No | Last watermark update timestamp |

### dq_results_history

| Column | Type | Nullable | Business Definition |
|--------|------|----------|---------------------|
| dq_run_id | INTEGER (PK, auto) | No | Surrogate key |
| run_id | TEXT (FK → pipeline_run_log) | Yes | Linked pipeline run |
| check_timestamp | TEXT | No | When the DQ check was executed |
| completeness_score | REAL | No | Score for the completeness dimension (0.0–1.0) |
| uniqueness_score | REAL | No | Score for the uniqueness dimension |
| validity_score | REAL | No | Score for the validity dimension |
| timeliness_score | REAL | No | Score for the timeliness dimension |
| referential_integrity_score | REAL | No | Score for the referential integrity dimension |
| composite_dq_score | REAL | No | Weighted composite score |
| pass_fail | TEXT | No | 'PASS' or 'FAIL' |
| threshold_used | REAL | No | The threshold value used for pass/fail |
| details_json | TEXT | Yes | JSON with per-check breakdown details |
