# Architecture — LinkedIn Agent Analytics Platform

## System Architecture

```mermaid
graph TB
    subgraph External
        A[Polluxa Platform<br/>sales.polluxa.com] -->|REST API| B
    end

    subgraph "Data Pipeline (Python)"
        B[API Client<br/>Rate-Limited + Retry] --> C[Incremental Ingestion<br/>Watermark-Based]
        C --> D{Validation}
        D -->|Valid| E[Idempotent Loader]
        D -->|Invalid| F[Dead Letter Queue]
        E --> G[(SQLite Database<br/>Star Schema)]
        F --> G
    end

    subgraph "Quality & Analytics"
        G --> H[DQ Checks<br/>5 Dimensions]
        H --> I[Composite DQ Score]
        G --> J[Anomaly Detection<br/>Modified Z-Score + IQR]
        J --> K[Risk Model<br/>Capacity Recommendations]
    end

    subgraph "Presentation"
        G --> L[Power BI Desktop<br/>DAX Measures]
        L --> M[Dashboard Pages<br/>KPIs · Health · Risk · ROI]
    end

    subgraph "Operations"
        N[Structured Logging<br/>JSON + Correlation IDs] -.-> B
        N -.-> C
        N -.-> H
        O[Alerting<br/>Failure · DQ · Risk] -.-> I
        O -.-> K
        P[GitHub Actions<br/>CI/CD Pipeline] -.->|Tests + Build| G
        Q[Docker<br/>Containerized] -.-> B
    end
```

## Component Overview

| Component | Purpose | Technology |
|-----------|---------|------------|
| **API Client** | Secure, rate-limited API communication | Python `requests` + `tenacity` |
| **Ingestion Engine** | Incremental data loading with watermarks | Custom Python, SQLite |
| **Star Schema** | Dimensional data model | SQLite DDL |
| **DQ Framework** | Automated quality validation | Custom Python (5 dimensions) |
| **Anomaly Detection** | Statistical outlier identification | `scipy`, `numpy`, Modified Z-Score |
| **Risk Model** | Account classification + capacity limits | Custom Python, `pandas` |
| **Power BI** | Dashboard visualization | Power BI Desktop + DAX |
| **CI/CD** | Automated testing and deployment | GitHub Actions |
| **Container** | Reproducible deployment | Docker |
| **Observability** | Logging and alerting | `structlog` (JSON) |

## Security Architecture

- **Secrets**: All credentials stored in `.env`, never in source control
- **`.env.example`**: Template with placeholder values committed to repo
- **API Auth**: Bearer token + API secret in request headers
- **Database**: Local SQLite file with WAL mode for safe concurrent access
- **Container**: Runs as non-root user with minimal attack surface
