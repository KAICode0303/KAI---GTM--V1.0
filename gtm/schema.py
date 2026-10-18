"""Schema, vocabularies and business rules for the V2 GTM workspace.

Four linked levels:  Accounts -> Prospects -> Outreach Activities (with Follow-ups)  and  Accounts -> Opportunities.
Three status ideas are kept in separate columns on purpose:
    lead_temperature   (prospect)     how warm the lead is           Cold / Warm / Hot
    response_status    (prospect)     what the prospect said back    No response / Replied / ... / Opt-out
    stage              (opportunity)  where the deal is              Prospecting ... Won / Lost
Customer segment (who the client is) and modality (how we deliver) are also separate fields.
"""
SCHEMA_VERSION = 1

SDRS = ["Mini", "Sue", "Harry", "Dips", "Emma"]
REGIONS = ["US", "Europe", "LATAM", "APAC"]
SEGMENTS = ["AI Labs", "Autonomous Vehicle Companies", "Enterprises", "Fintech Companies",
            "Product and Technology Companies", "Robotics and Physical AI Companies"]
CAPABILITIES = ["AI Consulting", "AI Training Data Collection", "Annotation and Labeling", "Managed AI Programs",
                "Model Evaluation and Benchmarking", "Multimodal Data Services", "RLHF and Human-in-the-Loop",
                "Robotics and Egocentric Data"]
MODALITIES = ["Fixed-scope project", "Managed service", "Time-and-materials team"]
ACCOUNT_STATUSES = ["Not Started", "Researching", "Contacted", "Engaged", "Meeting Booked", "Opportunity", "Customer", "Nurture"]
COMPANY_SIZES = ["51-200", "201-1,000", "1,001-5,000", "5,001-10,000", "10,000+"]

TEMPERATURES = ["Cold", "Warm", "Hot"]
RESPONSE_STATUSES = ["No response", "Replied", "Interested", "Meeting booked", "Not interested", "Opt-out"]
QUALIFICATIONS = ["Unqualified", "Qualified", "Disqualified"]
LEAD_SOURCES = ["Outbound SDR", "LinkedIn Outreach", "Inbound Website", "Referral", "Conference", "Partner", "CSV import"]
SEQUENCE_ACTIVE, SEQUENCE_STOPPED = "Active", "Stopped"
STOP_OPT_OUT, STOP_REJECTION, STOP_CLOSURE = "Opt-out", "Rejection", "Closure"
STOP_REASONS = [STOP_OPT_OUT, STOP_REJECTION, STOP_CLOSURE]
RESPONSE_STOPS = {"Opt-out": STOP_OPT_OUT, "Not interested": STOP_REJECTION}   # response statuses that end a sequence

STAGES = ["Prospecting", "Qualified", "Discovery", "Proposal", "Negotiation", "Won", "Lost"]
OPEN_STAGES = STAGES[:5]
STAGE_PROBABILITY = {"Prospecting": .10, "Qualified": .25, "Discovery": .40, "Proposal": .60, "Negotiation": .80, "Won": 1.0, "Lost": 0.0}

CHANNELS = ["Email", "LinkedIn", "Call"]
CHANNEL_COLUMN = {"Email": "email_sent_at", "LinkedIn": "linkedin_sent_at", "Call": "call_made_at"}
STANDARD_FOLLOWUPS = [(3, "Email"), (7, "LinkedIn"), (14, "Call"), (21, "Email")]     # (days after first touch, channel)
FOLLOWUP_STATUSES = ["Pending", "Done", "Skipped", "Cancelled"]
FOLLOWUP_OUTCOMES = ["Pending", "No answer", "Left voicemail", "Replied - positive", "Replied - neutral",
                      "Replied - not interested", "Opt-out request", "Meeting booked", "Other"]
ACTIVITY_KINDS = ["first_touch", "follow_up", "manual"]
# What a completed follow-up's outcome does to the prospect: (response_status, temperature floor, stop reason)
OUTCOME_EFFECTS = {
    "Replied - positive": ("Interested", "Warm", None),
    "Replied - neutral": ("Replied", None, None),
    "Replied - not interested": ("Not interested", None, STOP_REJECTION),
    "Opt-out request": ("Opt-out", None, STOP_OPT_OUT),
    "Meeting booked": ("Meeting booked", "Hot", None),
}

DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY, account_name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE,
    industry TEXT, customer_segment TEXT, hq_region TEXT, company_size TEXT, icp_score INTEGER,
    decision_maker_persona TEXT, owner TEXT, status TEXT, notes TEXT, source TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, orig_json TEXT);

CREATE TABLE IF NOT EXISTS prospects (
    prospect_id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(account_id),
    full_name TEXT NOT NULL, title TEXT, email TEXT, email_key TEXT UNIQUE, linkedin_url TEXT, linkedin_key TEXT UNIQUE, phone TEXT,
    owner TEXT, lead_source TEXT, lead_temperature TEXT NOT NULL DEFAULT 'Cold', response_status TEXT NOT NULL DEFAULT 'No response',
    qualification_status TEXT NOT NULL DEFAULT 'Unqualified',
    sequence_status TEXT NOT NULL DEFAULT 'Active', stop_reason TEXT, stopped_at TEXT,
    email_sent_at TEXT, linkedin_sent_at TEXT, call_made_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, orig_json TEXT);

CREATE TABLE IF NOT EXISTS follow_ups (
    followup_id TEXT PRIMARY KEY, prospect_id TEXT NOT NULL REFERENCES prospects(prospect_id), seq_no INTEGER NOT NULL,
    is_standard INTEGER NOT NULL DEFAULT 0, due_date TEXT NOT NULL, channel TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending',
    outcome TEXT NOT NULL DEFAULT 'Pending', notes TEXT, owner TEXT, completed_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE (prospect_id, seq_no));

CREATE TABLE IF NOT EXISTS outreach_activities (
    activity_id TEXT PRIMARY KEY, prospect_id TEXT NOT NULL REFERENCES prospects(prospect_id), account_id TEXT NOT NULL,
    owner TEXT, channel TEXT NOT NULL, kind TEXT NOT NULL, followup_id TEXT, performed_at TEXT NOT NULL,
    outcome TEXT, notes TEXT, created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(account_id), prospect_id TEXT,
    name TEXT NOT NULL, name_key TEXT NOT NULL, owner TEXT, stage TEXT NOT NULL, deal_value REAL NOT NULL,
    close_probability REAL NOT NULL, expected_revenue REAL NOT NULL, expected_delivery_cost REAL NOT NULL, expected_gross_profit REAL NOT NULL,
    service_capability TEXT, modality TEXT, customer_segment TEXT, hq_region TEXT,
    expected_close_date TEXT, closed_date TEXT, last_activity_date TEXT, next_action TEXT, outcome_reason TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, orig_json TEXT, UNIQUE (account_id, name_key));

CREATE TABLE IF NOT EXISTS kyc_profiles (
    account_id TEXT PRIMARY KEY REFERENCES accounts(account_id), data_json TEXT NOT NULL, completeness REAL NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS targets (owner TEXT NOT NULL, month TEXT NOT NULL, target REAL NOT NULL, gp_target REAL NOT NULL, PRIMARY KEY (owner, month));

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, table_name TEXT NOT NULL, row_id TEXT NOT NULL, action TEXT NOT NULL,
    changes_json TEXT, actor TEXT NOT NULL);

CREATE INDEX IF NOT EXISTS ix_prospects_account ON prospects(account_id);
CREATE INDEX IF NOT EXISTS ix_followups_prospect ON follow_ups(prospect_id, status);
CREATE INDEX IF NOT EXISTS ix_activities_prospect ON outreach_activities(prospect_id);
CREATE INDEX IF NOT EXISTS ix_opps_account ON opportunities(account_id);
"""
