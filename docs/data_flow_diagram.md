# Data Flow Diagram — LinkedIn Agent Analytics Platform

## End-to-End Data Flow

```mermaid
flowchart LR
    subgraph Source
        API["Polluxa API<br/>(sales.polluxa.com)"]
    end

    subgraph "Staging Layer"
        WM["Watermark Check<br/>(last_processed_timestamp)"]
        EXT["API Extract<br/>(paginated, rate-limited)"]
        VAL["Validation<br/>(schema + business rules)"]
        DLQ["Dead Letter Queue<br/>(failed records)"]
    end

    subgraph "Presentation Layer (Star Schema)"
        DD["dim_date"]
        DA["dim_linkedin_account<br/>(SCD Type 2)"]
        DC["dim_campaign<br/>(SCD Type 1)"]
        DL["dim_lead<br/>(SCD Type 1)"]
        DT["dim_message_template"]
        FA["fact_outreach_activity<br/>(grain: 1 row per action)"]
        FS["fact_daily_account_snapshot<br/>(grain: 1 row per account per day)"]
    end

    subgraph "Analytics Layer"
        DQ["DQ Checks<br/>(5 dimensions)"]
        AN["Anomaly Detection<br/>(Modified Z-Score + IQR)"]
        RM["Risk Model<br/>(capacity recommendations)"]
    end

    subgraph "Visualization"
        PBI["Power BI<br/>(4 dashboard pages)"]
    end

    API --> WM --> EXT --> VAL
    VAL -->|valid| DA & DC & DL & DT & FA
    VAL -->|invalid| DLQ
    FA --> FS
    DD --> FA & FS
    DA --> FA & FS
    DC --> FA
    DL --> FA
    FA & FS --> DQ
    FS --> AN --> RM
    AN -->|anomaly_score| FS
    FA & FS & DA & DC & DL --> PBI
```

## Pipeline Execution Flow

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as API Client
    participant I as Ingestion Engine
    participant DB as SQLite (Star Schema)
    participant DQ as DQ Checks
    participant AN as Anomaly Detection
    participant AL as Alerting

    O->>O: Generate correlation_id
    O->>DB: Initialize schema (idempotent)
    
    O->>I: Start ingestion
    I->>DB: Read watermark
    I->>A: Fetch data (since watermark)
    A-->>I: Paginated response
    I->>I: Validate & transform
    I->>DB: Upsert dimensions (SCD1/SCD2)
    I->>DB: Upsert facts (idempotent)
    I->>DB: Update watermark
    I->>DB: Log run metadata
    
    O->>DQ: Run quality checks
    DQ->>DB: Query all tables
    DQ->>DB: Persist DQ history
    DQ-->>O: Composite score + pass/fail
    
    O->>AN: Compute anomaly scores
    AN->>DB: Read daily snapshots
    AN->>DB: Update anomaly_score & risk_flag
    AN-->>O: Risk report
    
    O->>AL: Check alert conditions
    AL-->>O: Alerts emitted (if any)
    
    O->>DB: Final run metadata update
```

## Data Refresh Schedule

| Entity | Refresh Type | Trigger | Watermark Column |
|--------|-------------|---------|-----------------|
| Campaigns | Full | Every run | N/A |
| Leads | Incremental | Every run | `updated_at` |
| Activities | Incremental | Every run | `activity_timestamp` |
| Daily Snapshots | Computed | After activity load | N/A (aggregated) |
| DQ Checks | Full | After every load | N/A |
| Anomaly Scores | Full | After DQ checks | N/A |
