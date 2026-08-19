# Star Schema ERD — LinkedIn Agent Analytics Platform

## Entity-Relationship Diagram

```mermaid
erDiagram
    dim_date {
        int date_key PK "YYYYMMDD"
        text full_date UK "ISO date"
        int day_of_week
        text day_name
        int day_of_month
        int week_of_year
        int month_number
        text month_name
        int quarter
        int year
        int is_weekend
    }

    dim_linkedin_account {
        int account_key PK "Surrogate (auto)"
        text account_id NK "Natural key"
        text account_email
        text account_name
        text account_age_tier "Tier from Part 1"
        text risk_classification
        int daily_invite_limit
        int daily_message_limit
        text agent_status "Active/Paused/Ghost"
        text effective_from "SCD2"
        text effective_to "SCD2"
        int is_current "SCD2"
    }

    dim_campaign {
        int campaign_key PK "Surrogate (auto)"
        text campaign_id NK "Natural key"
        text campaign_name
        text target_segment
        text status
    }

    dim_lead {
        int lead_key PK "Surrogate (auto)"
        text lead_id NK "Natural key"
        text full_name
        text job_title
        text company
        text location
        text industry
    }

    dim_message_template {
        int template_key PK "Surrogate (auto)"
        text template_id NK "Natural key"
        text template_name
        text template_type
    }

    fact_outreach_activity {
        int activity_key PK "Surrogate (auto)"
        text activity_id NK "Idempotency anchor"
        int date_key FK
        int account_key FK
        int campaign_key FK
        int lead_key FK
        int template_key FK
        text activity_type "Degenerate dim"
        text activity_timestamp
        int is_accepted
        int is_replied
        int is_converted
        real response_time_hours
    }

    fact_daily_account_snapshot {
        int snapshot_key PK "Surrogate (auto)"
        int date_key FK
        int account_key FK
        int invites_sent
        int invites_accepted
        int messages_sent
        int replies_received
        real acceptance_rate
        real reply_rate
        real invite_utilization
        real message_utilization
        real anomaly_score "From Part 5"
        text risk_flag "Normal/Warning/Critical"
    }

    dim_date ||--o{ fact_outreach_activity : "date_key"
    dim_date ||--o{ fact_daily_account_snapshot : "date_key"
    dim_linkedin_account ||--o{ fact_outreach_activity : "account_key"
    dim_linkedin_account ||--o{ fact_daily_account_snapshot : "account_key"
    dim_campaign ||--o{ fact_outreach_activity : "campaign_key"
    dim_lead ||--o{ fact_outreach_activity : "lead_key"
    dim_message_template ||--o{ fact_outreach_activity : "template_key"
```

## Schema Summary

| Table Type | Table Name | Grain | SCD Strategy | Key Count |
|-----------|-----------|-------|-------------|-----------|
| **Dimension** | dim_date | 1 row per calendar date | Static (regenerated) | ~1,461 rows (4 years) |
| **Dimension** | dim_linkedin_account | 1 row per account version | **SCD Type 2** | ~3+ rows |
| **Dimension** | dim_campaign | 1 row per campaign | SCD Type 1 | ~5+ rows |
| **Dimension** | dim_lead | 1 row per lead | SCD Type 1 | ~150+ rows |
| **Dimension** | dim_message_template | 1 row per template | SCD Type 1 | ~4+ rows |
| **Fact** | fact_outreach_activity | 1 row per outreach action | N/A (append) | ~2,400+ rows |
| **Fact** | fact_daily_account_snapshot | 1 row per account per day | N/A (upsert) | ~111+ rows |
