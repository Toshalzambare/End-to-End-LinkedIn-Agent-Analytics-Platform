"""
Sample Data Generator — Creates realistic synthetic LinkedIn outreach data.
Generates all dimension and fact table records for testing and demonstration.

This script produces data that mimics real LinkedIn agent outreach patterns:
- Daily invite/message volumes that respect tier limits
- Realistic acceptance rates (15-35%) and reply rates (8-20%)
- Occasional anomalies for risk model testing
- Multiple campaigns with different target segments
- Ghost/paused agent scenarios for account health testing
"""

import random
import uuid
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.db_manager import get_db_session, initialize_database, populate_date_dimension

# Seed for reproducibility
random.seed(42)

# ============================================================
# Configuration
# ============================================================

NUM_ACCOUNTS = 3
NUM_CAMPAIGNS = 5
NUM_LEADS = 150
DAYS_OF_DATA = 45  # ~6.5 weeks of history
START_DATE = datetime.now(timezone.utc) - timedelta(days=DAYS_OF_DATA)

ACCOUNT_PROFILES = [
    {
        "account_id": "acct_001",
        "account_email": "toshal.zambare@example.com",
        "account_name": "Toshal Zambare",
        "account_age_tier": "1+ Year",
        "risk_classification": "Minimal Risk",
        "daily_invite_limit": 30,
        "daily_message_limit": 60,
        "agent_status": "Active",
        "base_acceptance_rate": 0.28,
        "base_reply_rate": 0.15,
    },
    {
        "account_id": "acct_002",
        "account_email": "assistant.one@example.com",
        "account_name": "Assistant Account 1",
        "account_age_tier": "6-12 Months",
        "risk_classification": "Low Risk",
        "daily_invite_limit": 25,
        "daily_message_limit": 40,
        "agent_status": "Active",
        "base_acceptance_rate": 0.22,
        "base_reply_rate": 0.12,
    },
    {
        "account_id": "acct_003",
        "account_email": "assistant.two@example.com",
        "account_name": "Assistant Account 2",
        "account_age_tier": "2-6 Months",
        "risk_classification": "Moderate Risk",
        "daily_invite_limit": 15,
        "daily_message_limit": 25,
        "agent_status": "Paused",  # For ghost/paused testing
        "base_acceptance_rate": 0.18,
        "base_reply_rate": 0.08,
    },
]

CAMPAIGNS = [
    {"id": "camp_001", "name": "Recruiter Outreach Q3", "segment": "Recruiters", "status": "Active"},
    {"id": "camp_002", "name": "Founder Network Build", "segment": "Founders", "status": "Active"},
    {"id": "camp_003", "name": "Engineering Talent Pipeline", "segment": "Engineers", "status": "Active"},
    {"id": "camp_004", "name": "Sales Leader Connect", "segment": "Sales Leaders", "status": "Paused"},
    {"id": "camp_005", "name": "Product Manager Outreach", "segment": "Product Managers", "status": "Completed"},
]

FIRST_NAMES = [
    "Aarav", "Priya", "Rahul", "Sneha", "Vikram", "Ananya", "Rohan", "Ishita",
    "Arjun", "Kavya", "Aditya", "Neha", "Karan", "Divya", "Manish", "Pooja",
    "James", "Sarah", "Michael", "Emily", "David", "Jessica", "Chris", "Amanda",
    "Alex", "Maria", "Daniel", "Lisa", "Ryan", "Nicole", "Kevin", "Laura",
]

LAST_NAMES = [
    "Sharma", "Patel", "Singh", "Kumar", "Gupta", "Reddy", "Joshi", "Mehta",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Anderson", "Wilson", "Taylor", "Thomas", "Moore", "Jackson", "Martin", "Lee",
]

JOB_TITLES = [
    "Software Engineer", "Senior Developer", "Tech Lead", "Engineering Manager",
    "Product Manager", "Data Scientist", "HR Manager", "Recruiter",
    "VP Engineering", "CTO", "Founder", "CEO", "Sales Director",
    "Marketing Manager", "Growth Lead", "DevOps Engineer",
]

COMPANIES = [
    "Google", "Microsoft", "Amazon", "Meta", "Apple", "Netflix", "Uber",
    "Spotify", "Stripe", "Shopify", "Salesforce", "Adobe", "Oracle",
    "Infosys", "TCS", "Wipro", "HCL", "Accenture", "Deloitte", "McKinsey",
]

INDUSTRIES = ["Technology", "Finance", "Healthcare", "E-commerce", "Consulting", "SaaS", "Education"]

LOCATIONS = [
    "San Francisco, CA", "New York, NY", "Bangalore, India", "London, UK",
    "Toronto, Canada", "Berlin, Germany", "Singapore", "Mumbai, India",
    "Seattle, WA", "Austin, TX", "Hyderabad, India", "Pune, India",
]

MESSAGE_TEMPLATES = [
    {"id": "tmpl_001", "name": "Cold Connect", "type": "Connection",
     "body": "Hi {name}, I came across your profile and would love to connect. I'm working in {industry} and think we could share valuable insights."},
    {"id": "tmpl_002", "name": "Mutual Interest", "type": "Connection",
     "body": "Hi {name}, I noticed we share an interest in {topic}. Would love to connect and exchange ideas!"},
    {"id": "tmpl_003", "name": "Follow-Up Day 3", "type": "Follow-Up",
     "body": "Hi {name}, thanks for connecting! I wanted to follow up and see if you'd be open to a quick chat about {topic}."},
    {"id": "tmpl_004", "name": "Value Offer", "type": "Follow-Up",
     "body": "Hi {name}, I recently published some insights on {topic} that might be relevant to your work at {company}. Happy to share!"},
]


def generate_leads() -> list[dict]:
    """Generate synthetic lead records."""
    leads = []
    for i in range(NUM_LEADS):
        leads.append({
            "lead_id": f"lead_{i+1:04d}",
            "linkedin_url": f"https://linkedin.com/in/{random.choice(FIRST_NAMES).lower()}-{random.choice(LAST_NAMES).lower()}-{random.randint(1000,9999)}",
            "full_name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            "job_title": random.choice(JOB_TITLES),
            "company": random.choice(COMPANIES),
            "location": random.choice(LOCATIONS),
            "industry": random.choice(INDUSTRIES),
        })
    return leads


def generate_activities(leads: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Generate synthetic outreach activities and daily snapshots.

    Includes:
    - Normal daily patterns
    - A simulated anomaly period (days 30-33: acceptance rate collapses for acct_001)
    - Weekend reduced activity
    - Paused account with no activity after day 20
    """
    activities = []
    daily_snapshots = []

    for day_offset in range(DAYS_OF_DATA):
        current_date = START_DATE + timedelta(days=day_offset)
        date_key = int(current_date.strftime("%Y%m%d"))
        is_weekend = current_date.weekday() >= 5

        for acct in ACCOUNT_PROFILES:
            acct_id = acct["account_id"]

            # Paused account stops after day 20
            if acct["agent_status"] == "Paused" and day_offset > 20:
                continue

            # Reduce volume on weekends
            weekend_factor = 0.3 if is_weekend else 1.0

            # Daily invite volume (with some randomness)
            max_inv = acct["daily_invite_limit"]
            base_invites = int(max_inv * random.uniform(0.5, 0.95) * weekend_factor)
            invites_sent = max(0, base_invites)

            # ---- ANOMALY INJECTION ----
            # Days 30-33: acceptance rate collapses for account 1
            if acct_id == "acct_001" and 30 <= day_offset <= 33:
                accept_rate = random.uniform(0.02, 0.06)  # Dramatic drop
            else:
                accept_rate = acct["base_acceptance_rate"] * random.uniform(0.7, 1.3)
                accept_rate = min(accept_rate, 1.0)

            invites_accepted = int(invites_sent * accept_rate)

            # Messages sent (to accepted leads + follow-ups)
            max_msg = acct["daily_message_limit"]
            messages_sent = min(
                max_msg,
                int(invites_accepted * random.uniform(1.5, 2.5) * weekend_factor)
            )

            # Reply rate
            if acct_id == "acct_001" and 32 <= day_offset <= 38:
                reply_rate = random.uniform(0.01, 0.04)  # Reply decay
            else:
                reply_rate = acct["base_reply_rate"] * random.uniform(0.6, 1.4)
                reply_rate = min(reply_rate, 1.0)

            replies_received = int(messages_sent * reply_rate)
            follow_ups = int(messages_sent * random.uniform(0.1, 0.3))
            conversions = int(replies_received * random.uniform(0.05, 0.15))

            # Generate individual activity records
            campaign = random.choice(CAMPAIGNS)
            available_leads = random.sample(leads, min(invites_sent + messages_sent, len(leads)))
            lead_idx = 0

            # Invite activities
            for i in range(invites_sent):
                hour = random.randint(8, 18)
                minute = random.randint(0, 59)
                ts = current_date.replace(hour=hour, minute=minute)
                lead = available_leads[lead_idx % len(available_leads)]
                lead_idx += 1

                accepted = i < invites_accepted
                activities.append({
                    "activity_id": str(uuid.uuid4()),
                    "date_key": date_key,
                    "account_id": acct_id,
                    "campaign_id": campaign["id"],
                    "lead_id": lead["lead_id"],
                    "template_id": random.choice(MESSAGE_TEMPLATES)["id"],
                    "activity_type": "invite_sent",
                    "activity_timestamp": ts.isoformat(),
                    "is_accepted": 1 if accepted else 0,
                    "is_replied": 0,
                    "is_converted": 0,
                    "response_time_hours": round(random.uniform(1, 72), 2) if accepted else None,
                })

                # Also create an 'invite_accepted' event for accepted ones
                if accepted:
                    resp_time = random.uniform(1, 48)
                    accept_ts = ts + timedelta(hours=resp_time)
                    activities.append({
                        "activity_id": str(uuid.uuid4()),
                        "date_key": int(accept_ts.strftime("%Y%m%d")),
                        "account_id": acct_id,
                        "campaign_id": campaign["id"],
                        "lead_id": lead["lead_id"],
                        "template_id": None,
                        "activity_type": "invite_accepted",
                        "activity_timestamp": accept_ts.isoformat(),
                        "is_accepted": 1,
                        "is_replied": 0,
                        "is_converted": 0,
                        "response_time_hours": round(resp_time, 2),
                    })

            # Message activities
            for i in range(messages_sent):
                hour = random.randint(9, 17)
                minute = random.randint(0, 59)
                ts = current_date.replace(hour=hour, minute=minute)
                lead = available_leads[lead_idx % len(available_leads)]
                lead_idx += 1

                replied = i < replies_received
                converted = i < conversions

                activities.append({
                    "activity_id": str(uuid.uuid4()),
                    "date_key": date_key,
                    "account_id": acct_id,
                    "campaign_id": campaign["id"],
                    "lead_id": lead["lead_id"],
                    "template_id": random.choice(MESSAGE_TEMPLATES)["id"],
                    "activity_type": "message_sent",
                    "activity_timestamp": ts.isoformat(),
                    "is_accepted": 0,
                    "is_replied": 1 if replied else 0,
                    "is_converted": 1 if converted else 0,
                    "response_time_hours": round(random.uniform(0.5, 24), 2) if replied else None,
                })

            # Daily snapshot
            inv_util = invites_sent / max_inv if max_inv > 0 else 0
            msg_util = messages_sent / max_msg if max_msg > 0 else 0
            acc_rate = invites_accepted / invites_sent if invites_sent > 0 else 0
            rpl_rate = replies_received / messages_sent if messages_sent > 0 else 0
            conv_rate = conversions / (invites_sent + messages_sent) if (invites_sent + messages_sent) > 0 else 0

            daily_snapshots.append({
                "date_key": date_key,
                "account_id": acct_id,
                "invites_sent": invites_sent,
                "invites_accepted": invites_accepted,
                "messages_sent": messages_sent,
                "replies_received": replies_received,
                "follow_ups_sent": follow_ups,
                "conversions": conversions,
                "acceptance_rate": round(acc_rate, 4),
                "reply_rate": round(rpl_rate, 4),
                "conversion_rate": round(conv_rate, 4),
                "invite_utilization": round(inv_util, 4),
                "message_utilization": round(msg_util, 4),
            })

    return activities, daily_snapshots


def load_data(db_path: str | None = None) -> dict:
    """
    Generate and load all synthetic data into the database.

    Returns:
        Summary dict with counts of loaded records.
    """
    print("=" * 60)
    print("LinkedIn Agent Analytics — Sample Data Generator")
    print("=" * 60)

    with get_db_session(db_path) as conn:
        # 1. Initialize schema
        print("\n[1/7] Initializing database schema...")
        initialize_database(db_path)

        # 2. Populate date dimension
        print("[2/7] Populating date dimension...")
        populate_date_dimension(conn)
        conn.commit()

        # 3. Load accounts (dimension)
        print("[3/7] Loading LinkedIn accounts...")
        account_key_map = {}
        for acct in ACCOUNT_PROFILES:
            conn.execute(
                """
                INSERT OR IGNORE INTO dim_linkedin_account
                (account_id, account_email, account_name, account_age_tier,
                 risk_classification, daily_invite_limit, daily_message_limit,
                 agent_status, effective_from, is_current)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 1)
                """,
                (acct["account_id"], acct["account_email"], acct["account_name"],
                 acct["account_age_tier"], acct["risk_classification"],
                 acct["daily_invite_limit"], acct["daily_message_limit"],
                 acct["agent_status"])
            )
            cursor = conn.execute(
                "SELECT account_key FROM dim_linkedin_account WHERE account_id = ? AND is_current = 1",
                (acct["account_id"],)
            )
            row = cursor.fetchone()
            account_key_map[acct["account_id"]] = row["account_key"]
        conn.commit()
        print(f"   → {len(ACCOUNT_PROFILES)} accounts loaded")

        # 4. Load campaigns (dimension)
        print("[4/7] Loading campaigns...")
        campaign_key_map = {}
        for camp in CAMPAIGNS:
            conn.execute(
                """
                INSERT OR IGNORE INTO dim_campaign
                (campaign_id, campaign_name, target_segment, status, created_date)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (camp["id"], camp["name"], camp["segment"], camp["status"])
            )
            cursor = conn.execute(
                "SELECT campaign_key FROM dim_campaign WHERE campaign_id = ?",
                (camp["id"],)
            )
            row = cursor.fetchone()
            campaign_key_map[camp["id"]] = row["campaign_key"]
        conn.commit()
        print(f"   → {len(CAMPAIGNS)} campaigns loaded")

        # 5. Load leads (dimension)
        print("[5/7] Loading leads...")
        leads = generate_leads()
        lead_key_map = {}
        for lead in leads:
            conn.execute(
                """
                INSERT OR IGNORE INTO dim_lead
                (lead_id, linkedin_url, full_name, job_title, company, location, industry)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (lead["lead_id"], lead["linkedin_url"], lead["full_name"],
                 lead["job_title"], lead["company"], lead["location"], lead["industry"])
            )
            cursor = conn.execute(
                "SELECT lead_key FROM dim_lead WHERE lead_id = ?",
                (lead["lead_id"],)
            )
            row = cursor.fetchone()
            lead_key_map[lead["lead_id"]] = row["lead_key"]
        conn.commit()
        print(f"   → {len(leads)} leads loaded")

        # 6. Load activities (fact)
        print("[6/7] Generating and loading outreach activities...")
        activities, daily_snapshots = generate_activities(leads)

        for act in activities:
            acct_key = account_key_map.get(act["account_id"], 0)
            camp_key = campaign_key_map.get(act["campaign_id"])
            lead_key = lead_key_map.get(act["lead_id"])
            tmpl_key = None  # Simplified — could map templates too

            conn.execute(
                """
                INSERT OR IGNORE INTO fact_outreach_activity
                (activity_id, date_key, account_key, campaign_key, lead_key,
                 template_key, activity_type, activity_timestamp,
                 is_accepted, is_replied, is_converted, response_time_hours)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (act["activity_id"], act["date_key"], acct_key, camp_key, lead_key,
                 tmpl_key, act["activity_type"], act["activity_timestamp"],
                 act["is_accepted"], act["is_replied"], act["is_converted"],
                 act["response_time_hours"])
            )
        conn.commit()
        print(f"   → {len(activities)} activity records loaded")

        # 7. Load daily snapshots (fact)
        print("[7/7] Loading daily account snapshots...")
        for snap in daily_snapshots:
            acct_key = account_key_map.get(snap["account_id"], 0)
            conn.execute(
                """
                INSERT OR IGNORE INTO fact_daily_account_snapshot
                (date_key, account_key, invites_sent, invites_accepted,
                 messages_sent, replies_received, follow_ups_sent, conversions,
                 acceptance_rate, reply_rate, conversion_rate,
                 invite_utilization, message_utilization)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (snap["date_key"], acct_key, snap["invites_sent"], snap["invites_accepted"],
                 snap["messages_sent"], snap["replies_received"], snap["follow_ups_sent"],
                 snap["conversions"], snap["acceptance_rate"], snap["reply_rate"],
                 snap["conversion_rate"], snap["invite_utilization"], snap["message_utilization"])
            )
        conn.commit()
        print(f"   → {len(daily_snapshots)} daily snapshot records loaded")

        # 8. Load message templates
        for tmpl in MESSAGE_TEMPLATES:
            conn.execute(
                """
                INSERT OR IGNORE INTO dim_message_template
                (template_id, template_name, template_body, template_type)
                VALUES (?, ?, ?, ?)
                """,
                (tmpl["id"], tmpl["name"], tmpl["body"], tmpl["type"])
            )
        conn.commit()

    summary = {
        "accounts": len(ACCOUNT_PROFILES),
        "campaigns": len(CAMPAIGNS),
        "leads": len(leads),
        "activities": len(activities),
        "daily_snapshots": len(daily_snapshots),
        "templates": len(MESSAGE_TEMPLATES),
        "days_of_data": DAYS_OF_DATA,
    }

    print("\n" + "=" * 60)
    print("✅ Sample data generation complete!")
    print(f"   Accounts:     {summary['accounts']}")
    print(f"   Campaigns:    {summary['campaigns']}")
    print(f"   Leads:        {summary['leads']}")
    print(f"   Activities:   {summary['activities']}")
    print(f"   Snapshots:    {summary['daily_snapshots']}")
    print(f"   Templates:    {summary['templates']}")
    print(f"   Date range:   {DAYS_OF_DATA} days")
    print("=" * 60)

    return summary


if __name__ == "__main__":
    load_data()
