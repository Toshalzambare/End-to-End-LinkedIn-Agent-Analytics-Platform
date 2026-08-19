-- ==============================================================================
-- Star Schema DDL — LinkedIn Agent Analytics Platform
-- Part 3: Data Architecture & Modeling
-- ==============================================================================
-- Database: SQLite
-- Grain, keys, relationships, and SCD strategy documented inline.
-- ==============================================================================

-- ============================================================
-- DIMENSION TABLES
-- ============================================================

-- DIM_DATE: Standard date dimension for time-based analysis.
-- SCD Type: N/A (static, fully regenerated).
-- Grain: One row per calendar date.
CREATE TABLE IF NOT EXISTS dim_date (
    date_key        INTEGER PRIMARY KEY,    -- Surrogate key (YYYYMMDD format)
    full_date       TEXT    NOT NULL UNIQUE, -- ISO date string 'YYYY-MM-DD'
    day_of_week     INTEGER NOT NULL,       -- 0=Monday … 6=Sunday
    day_name        TEXT    NOT NULL,        -- 'Monday', 'Tuesday', etc.
    day_of_month    INTEGER NOT NULL,
    week_of_year    INTEGER NOT NULL,
    month_number    INTEGER NOT NULL,
    month_name      TEXT    NOT NULL,
    quarter         INTEGER NOT NULL,
    year            INTEGER NOT NULL,
    is_weekend      INTEGER NOT NULL DEFAULT 0  -- 1 if Saturday/Sunday
);

-- DIM_LINKEDIN_ACCOUNT: The LinkedIn accounts connected to the platform.
-- SCD Type 2: Track changes in account age tier and risk classification.
-- Grain: One row per account per version (SCD2 versioning).
CREATE TABLE IF NOT EXISTS dim_linkedin_account (
    account_key         INTEGER PRIMARY KEY AUTOINCREMENT,  -- Surrogate key
    account_id          TEXT    NOT NULL,        -- Natural key from Polluxa
    account_email       TEXT,
    account_name        TEXT,
    account_age_tier    TEXT    NOT NULL,        -- '< 1 Month', '1 Month', '2-6 Months', '6-12 Months', '1+ Year'
    risk_classification TEXT    NOT NULL,        -- 'Very High Risk' … 'Minimal Risk'
    daily_invite_limit  INTEGER NOT NULL,
    daily_message_limit INTEGER NOT NULL,
    agent_status        TEXT    NOT NULL DEFAULT 'Active',  -- 'Active', 'Paused', 'Ghost', 'Disconnected'
    -- SCD Type 2 columns
    effective_from      TEXT    NOT NULL,        -- ISO datetime
    effective_to        TEXT    DEFAULT '9999-12-31T23:59:59',
    is_current          INTEGER NOT NULL DEFAULT 1,  -- 1 = current version
    -- Audit
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_dim_account_natural ON dim_linkedin_account(account_id, is_current);

-- DIM_CAMPAIGN: Outreach campaigns / target segments.
-- SCD Type 1: Overwrite on change (campaigns are mutable labels).
-- Grain: One row per campaign.
CREATE TABLE IF NOT EXISTS dim_campaign (
    campaign_key    INTEGER PRIMARY KEY AUTOINCREMENT,  -- Surrogate key
    campaign_id     TEXT    NOT NULL UNIQUE,     -- Natural key from Polluxa
    campaign_name   TEXT    NOT NULL,
    target_segment  TEXT,                        -- e.g. 'Recruiters', 'Founders', 'Engineers'
    description     TEXT,
    status          TEXT    NOT NULL DEFAULT 'Active',  -- 'Active', 'Paused', 'Completed'
    created_date    TEXT,
    -- Audit
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- DIM_LEAD: Individual leads targeted by outreach.
-- SCD Type 1: Overwrite on change.
-- Grain: One row per lead.
CREATE TABLE IF NOT EXISTS dim_lead (
    lead_key        INTEGER PRIMARY KEY AUTOINCREMENT,  -- Surrogate key
    lead_id         TEXT    NOT NULL UNIQUE,     -- Natural key from Polluxa
    linkedin_url    TEXT,
    full_name       TEXT,
    job_title       TEXT,
    company         TEXT,
    location        TEXT,
    industry        TEXT,
    -- Audit
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- DIM_MESSAGE_TEMPLATE: Message templates used for outreach.
-- SCD Type 1: Overwrite on change.
-- Grain: One row per template.
CREATE TABLE IF NOT EXISTS dim_message_template (
    template_key    INTEGER PRIMARY KEY AUTOINCREMENT,  -- Surrogate key
    template_id     TEXT    NOT NULL UNIQUE,     -- Natural key
    template_name   TEXT,
    template_body   TEXT,
    template_type   TEXT    NOT NULL DEFAULT 'Connection',  -- 'Connection', 'Follow-Up', 'InMail'
    -- Audit
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ============================================================
-- FACT TABLES
-- ============================================================

-- FACT_OUTREACH_ACTIVITY: Core transactional fact table.
-- Grain: One row per outreach action (invite sent, message sent, etc.).
-- This is the primary fact table driving all KPIs.
CREATE TABLE IF NOT EXISTS fact_outreach_activity (
    activity_key        INTEGER PRIMARY KEY AUTOINCREMENT,  -- Surrogate key
    activity_id         TEXT    NOT NULL UNIQUE,     -- Natural key (idempotency anchor)
    -- Foreign keys to dimensions
    date_key            INTEGER NOT NULL,
    account_key         INTEGER NOT NULL,
    campaign_key        INTEGER,
    lead_key            INTEGER,
    template_key        INTEGER,
    -- Degenerate dimensions
    activity_type       TEXT    NOT NULL,    -- 'invite_sent', 'invite_accepted', 'message_sent', 'reply_received', 'follow_up_sent'
    activity_timestamp  TEXT    NOT NULL,    -- ISO datetime of the event
    -- Measures
    is_accepted         INTEGER DEFAULT 0,  -- 1 if invite was accepted
    is_replied          INTEGER DEFAULT 0,  -- 1 if message got a reply
    is_converted        INTEGER DEFAULT 0,  -- 1 if lead converted (meeting/goal achieved)
    response_time_hours REAL,               -- Hours between send and response (NULL if no response)
    -- Audit
    loaded_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    source_system       TEXT    NOT NULL DEFAULT 'polluxa_api',

    FOREIGN KEY (date_key)     REFERENCES dim_date(date_key),
    FOREIGN KEY (account_key)  REFERENCES dim_linkedin_account(account_key),
    FOREIGN KEY (campaign_key) REFERENCES dim_campaign(campaign_key),
    FOREIGN KEY (lead_key)     REFERENCES dim_lead(lead_key),
    FOREIGN KEY (template_key) REFERENCES dim_message_template(template_key)
);

CREATE INDEX IF NOT EXISTS idx_fact_activity_date    ON fact_outreach_activity(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_activity_account ON fact_outreach_activity(account_key);
CREATE INDEX IF NOT EXISTS idx_fact_activity_type    ON fact_outreach_activity(activity_type);

-- FACT_DAILY_ACCOUNT_SNAPSHOT: Periodic (daily) snapshot fact table.
-- Grain: One row per account per day.
-- Captures daily utilization, throughput, and cumulative metrics.
CREATE TABLE IF NOT EXISTS fact_daily_account_snapshot (
    snapshot_key            INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key                INTEGER NOT NULL,
    account_key             INTEGER NOT NULL,
    -- Measures: daily counts
    invites_sent            INTEGER NOT NULL DEFAULT 0,
    invites_accepted        INTEGER NOT NULL DEFAULT 0,
    messages_sent           INTEGER NOT NULL DEFAULT 0,
    replies_received        INTEGER NOT NULL DEFAULT 0,
    follow_ups_sent         INTEGER NOT NULL DEFAULT 0,
    conversions             INTEGER NOT NULL DEFAULT 0,
    -- Measures: rates (precomputed for Power BI performance)
    acceptance_rate         REAL,   -- invites_accepted / invites_sent
    reply_rate              REAL,   -- replies_received / messages_sent
    conversion_rate         REAL,   -- conversions / total interactions
    -- Measures: utilization against limits
    invite_utilization      REAL,   -- invites_sent / daily_invite_limit
    message_utilization     REAL,   -- messages_sent / daily_message_limit
    -- Measures: risk signals
    anomaly_score           REAL,   -- Computed by Part 5 analytics
    risk_flag               TEXT    DEFAULT 'Normal',  -- 'Normal', 'Warning', 'Critical'
    -- Audit
    loaded_at               TEXT    NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (date_key)    REFERENCES dim_date(date_key),
    FOREIGN KEY (account_key) REFERENCES dim_linkedin_account(account_key),
    UNIQUE(date_key, account_key)  -- Enforce grain: one row per account per day
);

CREATE INDEX IF NOT EXISTS idx_snapshot_date    ON fact_daily_account_snapshot(date_key);
CREATE INDEX IF NOT EXISTS idx_snapshot_account ON fact_daily_account_snapshot(account_key);


-- ============================================================
-- OPERATIONAL TABLES (Pipeline Support)
-- ============================================================

-- Pipeline run metadata — Part 2 requirement.
CREATE TABLE IF NOT EXISTS pipeline_run_log (
    run_id          TEXT    PRIMARY KEY,         -- UUID
    correlation_id  TEXT    NOT NULL,            -- Matches structured log correlation ID
    run_type        TEXT    NOT NULL,            -- 'full', 'incremental'
    status          TEXT    NOT NULL DEFAULT 'running',  -- 'running', 'success', 'failed', 'partial'
    started_at      TEXT    NOT NULL,
    ended_at        TEXT,
    rows_extracted  INTEGER DEFAULT 0,
    rows_loaded     INTEGER DEFAULT 0,
    rows_rejected   INTEGER DEFAULT 0,
    error_message   TEXT,
    watermark_value TEXT                         -- Last processed timestamp for incremental loads
);

-- Dead-letter queue — Part 2 requirement.
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    dlq_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    NOT NULL,
    record_payload  TEXT    NOT NULL,            -- JSON of the failed record
    error_type      TEXT    NOT NULL,            -- 'validation', 'transformation', 'load', 'api'
    error_message   TEXT    NOT NULL,
    failed_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    retried         INTEGER NOT NULL DEFAULT 0,  -- 1 if retried successfully
    retried_at      TEXT,

    FOREIGN KEY (run_id) REFERENCES pipeline_run_log(run_id)
);

-- Watermark table for incremental loading — Part 2 requirement.
CREATE TABLE IF NOT EXISTS ingestion_watermark (
    entity_name     TEXT    PRIMARY KEY,         -- e.g. 'outreach_activity', 'leads'
    last_watermark  TEXT    NOT NULL,            -- ISO datetime of last successfully loaded record
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Data Quality results history — Part 4 requirement.
CREATE TABLE IF NOT EXISTS dq_results_history (
    dq_run_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT,                    -- Links to pipeline_run_log
    check_timestamp     TEXT    NOT NULL DEFAULT (datetime('now')),
    -- Individual dimension scores (0.0 to 1.0)
    completeness_score  REAL    NOT NULL,
    uniqueness_score    REAL    NOT NULL,
    validity_score      REAL    NOT NULL,
    timeliness_score    REAL    NOT NULL,
    referential_integrity_score REAL NOT NULL,
    -- Composite
    composite_dq_score  REAL    NOT NULL,
    pass_fail           TEXT    NOT NULL,        -- 'PASS' or 'FAIL'
    threshold_used      REAL    NOT NULL,
    -- Details
    details_json        TEXT,                    -- JSON with per-check breakdown

    FOREIGN KEY (run_id) REFERENCES pipeline_run_log(run_id)
);
