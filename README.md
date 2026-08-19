# End-to-End LinkedIn Agent Analytics Platform

A production-ready analytics platform that ingests, models, analyzes, and visualizes automated LinkedIn outreach data from the Polluxa platform.

## Architecture Overview

```
Polluxa API  -->  Data Pipeline  -->  Star Schema (SQLite)  -->  Analytics  -->  Power BI
                  (Python)             (5 dims + 2 facts)       (Anomaly +     (4 dashboard
                                                                 Risk Model)    pages)
```

See [docs/architecture.md](docs/architecture.md) for the full system architecture diagram.

## Quick Start

### Prerequisites

- Python 3.11+
- Power BI Desktop (for dashboards)
- Docker (optional, for containerized deployment)

### Setup

```bash
# Clone the repository
git clone https://github.com/Toshalzambare/End-to-End-LinkedIn-Agent-Analytics-Platform.git
cd End-to-End-LinkedIn-Agent-Analytics-Platform

# Create and activate virtual environment
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Polluxa API credentials
```

### Generate Sample Data

```bash
# Set environment variables (Windows PowerShell)
$env:PYTHONPATH='.'; $env:PYTHONIOENCODING='utf-8'

# Generate realistic synthetic data (3 accounts, 5 campaigns, 150 leads, 45 days)
python scripts/generate_sample_data.py
```

### Run the Pipeline

```bash
# Incremental run (default)
python scripts/run_pipeline.py

# Full reload
python scripts/run_pipeline.py --run-type full
```

### Run Data Quality Checks

```bash
python scripts/run_dq_checks.py
```

### Run Tests

```bash
pytest tests/ -v --tb=short
```

### Docker

```bash
# Build and run
docker build -t linkedin-analytics .
docker-compose up

# Run DQ checks in Docker
docker-compose --profile tools run dq-checker
```

## Project Structure

```
.
+-- .github/workflows/ci-cd.yml    # GitHub Actions CI/CD pipeline
+-- config/                         # Configuration & logging
+-- src/
|   +-- pipeline/                   # API client, ingestion, dead-letter queue
|   +-- database/                   # Star Schema DDL & DB manager
|   +-- quality/                    # DQ checks & composite scorer
|   +-- analytics/                  # Anomaly detection & risk model
|   +-- observability/              # Structured logging & alerting
+-- tests/                          # Pytest test suite (27 tests)
+-- scripts/                        # Pipeline runner, DQ runner, data generator
+-- powerbi/                        # DAX measures & data model docs
+-- docs/                           # Full documentation suite
+-- Dockerfile                      # Containerized deployment
+-- docker-compose.yml              # Multi-service orchestration
```

## Key Features

### Part 2: API Engineering & Data Pipeline
- Secure token-based API authentication (no secrets in source control)
- Idempotent writes -- re-running any load does not duplicate or corrupt records
- Incremental loading via watermarks (only fetches new data since last run)
- Exponential backoff retry with rate-limit awareness (HTTP 429 handling)
- Dead-letter queue for failed records
- Run metadata persisted for every execution

### Part 3: Data Architecture & Modeling
- Star Schema with 5 dimension tables and 2 fact tables
- SCD Type 2 on `dim_linkedin_account` (tracks tier/status changes over time)
- Surrogate keys on all dimensions
- Conformed grain documented per table
- Full data dictionary: [docs/data_dictionary.md](docs/data_dictionary.md)
- ERD diagram: [docs/star_schema_erd.md](docs/star_schema_erd.md)

### Part 4: Data Quality & Automation
- 5-dimension automated checks: completeness, uniqueness, validity, timeliness, referential integrity
- Weighted composite DQ score (pass/fail threshold: 0.85)
- DQ results history table for trending quality over time
- Standalone DQ runner script

### Part 5: Advanced Analytics & Risk Modeling
- Modified Z-Score + IQR hybrid anomaly detection
- Detects: acceptance-rate collapse, reply decay, ghosting patterns, utilization spikes
- Per-account capacity recommendations with documented safety factors
- Full statistical documentation: [docs/risk_model_documentation.md](docs/risk_model_documentation.md)

### Part 6: Power BI Engineering
- 25+ explicit DAX measures (no implicit aggregations)
- 4 dashboard pages: Core KPIs, Account Health, Risk Intelligence, Campaign ROI
- Time intelligence measures (7-day rolling, WoW change)
- DAX reference: [powerbi/DAX_measures.md](powerbi/DAX_measures.md)

### Part 7: DevOps, CI/CD, & Observability
- Dockerfile with pinned dependencies, non-root user, health check
- GitHub Actions CI/CD: test --> build --> DQ gate
- Structured JSON logging with correlation IDs (via `structlog`)
- Alerting on pipeline failure, DQ threshold breach, and critical risk accounts

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System architecture with Mermaid diagram |
| [Data Flow](docs/data_flow_diagram.md) | End-to-end data flow from API to dashboard |
| [Star Schema ERD](docs/star_schema_erd.md) | Entity-relationship diagram |
| [Data Dictionary](docs/data_dictionary.md) | Every column, type, and business definition |
| [Risk Model](docs/risk_model_documentation.md) | Statistical basis, assumptions, limitations |
| [DAX Measures](powerbi/DAX_measures.md) | All Power BI DAX measure definitions |
| [Part 1 Guide](docs/part1_evidence/README.md) | Screenshot evidence guide |

## Account Age Tier Matrix

| Account Age | Risk Level | Daily Invites | Daily Messages |
|-------------|------------|---------------|----------------|
| < 1 Month | Very High Risk | 5 | 10 |
| 1 Month | High Risk | 10 | 15 |
| 2-6 Months | Moderate Risk | 15 | 25 |
| 6-12 Months | Low Risk | 25 | 40 |
| 1+ Year | Minimal Risk | 30 | 60 |

## License

This project is an assessment submission and is not licensed for public distribution.
