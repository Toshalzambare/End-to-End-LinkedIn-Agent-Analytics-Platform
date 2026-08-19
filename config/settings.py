"""
Configuration module — Externalized settings loaded from environment variables.
All secrets are read from .env (never hardcoded). Defaults are safe for local dev.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


# ==============================================================================
# Polluxa API
# ==============================================================================
POLLUXA_API_BASE_URL = os.getenv("POLLUXA_API_BASE_URL", "https://sales.polluxa.com/api")
POLLUXA_API_KEY = os.getenv("POLLUXA_API_KEY", "")
POLLUXA_API_SECRET = os.getenv("POLLUXA_API_SECRET", "")

# ==============================================================================
# LinkedIn Agent — Account Age Tier & Limits
# ==============================================================================
LINKEDIN_ACCOUNT_AGE_TIER = os.getenv("LINKEDIN_ACCOUNT_AGE_TIER", "1+ Year")
DAILY_INVITE_LIMIT = int(os.getenv("DAILY_INVITE_LIMIT", "30"))
DAILY_MESSAGE_LIMIT = int(os.getenv("DAILY_MESSAGE_LIMIT", "60"))

# Account Age → Daily Limit Matrix (from assessment spec)
ACCOUNT_AGE_LIMITS = {
    "< 1 Month":   {"risk": "Very High Risk", "invites": 5,  "messages": 10},
    "1 Month":     {"risk": "High Risk",      "invites": 10, "messages": 15},
    "2-6 Months":  {"risk": "Moderate Risk",   "invites": 15, "messages": 25},
    "6-12 Months": {"risk": "Low Risk",        "invites": 25, "messages": 40},
    "1+ Year":     {"risk": "Minimal Risk",    "invites": 30, "messages": 60},
}

# ==============================================================================
# Database
# ==============================================================================
DATABASE_PATH = os.getenv("DATABASE_PATH", str(_PROJECT_ROOT / "data" / "linkedin_analytics.db"))

# ==============================================================================
# Pipeline
# ==============================================================================
PIPELINE_BATCH_SIZE = int(os.getenv("PIPELINE_BATCH_SIZE", "100"))
PIPELINE_MAX_RETRIES = int(os.getenv("PIPELINE_MAX_RETRIES", "3"))
PIPELINE_RETRY_BACKOFF_BASE = int(os.getenv("PIPELINE_RETRY_BACKOFF_BASE", "2"))
PIPELINE_RATE_LIMIT_RPM = int(os.getenv("PIPELINE_RATE_LIMIT_REQUESTS_PER_MINUTE", "30"))

# ==============================================================================
# Data Quality
# ==============================================================================
DQ_PASS_THRESHOLD = float(os.getenv("DQ_PASS_THRESHOLD", "0.85"))
DQ_ALERT_ON_FAIL = os.getenv("DQ_ALERT_ON_FAIL", "true").lower() == "true"

# ==============================================================================
# Logging
# ==============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")
LOG_FILE = os.getenv("LOG_FILE", str(_PROJECT_ROOT / "logs" / "pipeline.log"))

# ==============================================================================
# Alerting
# ==============================================================================
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")
ALERT_ON_PIPELINE_FAILURE = os.getenv("ALERT_ON_PIPELINE_FAILURE", "true").lower() == "true"
ALERT_ON_DQ_BREACH = os.getenv("ALERT_ON_DQ_BREACH", "true").lower() == "true"
ALERT_ON_ANOMALOUS_DURATION = os.getenv("ALERT_ON_ANOMALOUS_DURATION", "true").lower() == "true"
