"""Generate the linked, entirely FICTIONAL datasets for the Sales & GTM Command Center.

Run:  python generate_gtm_data.py

It keeps your original 50 deals (data/opportunities.csv, same numbers) and builds everything else around them:

  accounts.csv         64 companies (the 50 deal clients + 14 extra prospects)
  contacts.csv         fictional people at those accounts (example.com emails only)
  leads.csv            ~300 leads; 50 of them became the 50 opportunities
  sdr_activity.csv     daily activity per rep (qualified leads / meetings are derived from leads.csv)
  activity_targets.csv weekly activity targets
  account_research.csv / market_research.csv / tool_research.csv
  collateral.csv       decks, case studies, proposals ...
  targets.csv          monthly revenue AND gross-profit targets per rep

IDs link the tables:  opportunity -> lead -> contact -> account  (and collateral -> account / opportunity).
Fixed random seed = same data every run.
"""
import random
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

random.seed(11)
AS_OF = date(2026, 10, 8)
D = Path("data")
REPS = ["Jon", "Sara", "Alex", "Emma", "Ryan"]


def wd(d):
    """Move a weekend date back to Friday (SDR work happens on weekdays)."""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def iso(d):
    return d.isoformat() if d else ""


def slug(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ------------------------------------------------------------------ opportunities (v1 file, extended)
EXTRA_OPP_COLS = ["account_id", "lead_id", "created_date", "next_follow_up_date", "outcome_reason"]
opps = pd.read_csv(D / "opportunities.csv")
opps = opps.drop(columns=[c for c in EXTRA_OPP_COLS if c in opps.columns])  # makes re-runs safe
for c in ["expected_close_date", "last_activity_date"]:
    opps[c] = pd.to_datetime(opps[c]).dt.date

SEG_INDUSTRY = {"AI Labs": ["AI Research"], "Product and Technology Companies": ["Software & Internet"],
                "Robotics and Physical AI Companies": ["Robotics & Automation"],
                "Autonomous Vehicle Companies": ["Autonomous Mobility"], "Fintech Companies": ["Financial Technology"],
                "Enterprises": ["Logistics", "Healthcare", "Insurance", "Retail", "Manufacturing", "Energy"]}
SEG_PERSONA = {"AI Labs": ["Head of Data / Research Ops", "VP of AI Research"],
               "Product and Technology Companies": ["VP of Engineering", "Head of ML Platform"],
               "Robotics and Physical AI Companies": ["Head of Robotics Data", "VP of Autonomy"],
               "Autonomous Vehicle Companies": ["Head of Perception Data", "Director of Simulation"],
               "Enterprises": ["Chief Data Officer", "VP of AI Transformation"],
               "Fintech Companies": ["Head of Risk Models", "Chief AI Officer"]}
SEG_TECH = {"AI Labs": "LLM training, RLHF pipelines, evaluation harnesses",
            "Product and Technology Companies": "Recommendation models, copilots, MLOps stack",
            "Robotics and Physical AI Companies": "Egocentric video, teleoperation, manipulation models",
            "Autonomous Vehicle Companies": "LiDAR/camera perception, simulation, edge-case mining",
            "Enterprises": "Document AI, forecasting models, internal copilots",
            "Fintech Companies": "Fraud and credit models, KYC automation, LLM assistants"}
SEG_SERVICES = {"AI Labs": "RLHF and Human-in-the-Loop", "Product and Technology Companies": "Model Evaluation and Benchmarking",
                "Robotics and Physical AI Companies": "Robotics and Egocentric Data",
                "Autonomous Vehicle Companies": "Multimodal Data Services", "Enterprises": "Managed AI Programs",
                "Fintech Companies": "AI Consulting"}
SIGNALS = ["Hiring data/ML annotators", "Recent funding round", "New AI product announcement", "Job posts for AI program managers",
           "Published benchmark results", "Leadership change in AI team", "Expanded to a new region", "Open RFP for data services",
           "Conference talk on data quality", "Partnership with a cloud provider"]
SOURCE_TOOLS = ["Apollo", "ZoomInfo", "LinkedIn", "Company Website", "Industry Report"]

PROSPECTS = [("Helixmind Labs", "AI Labs"), ("Aurora Cognition", "AI Labs"),
             ("Brightloop Apps", "Product and Technology Companies"), ("Nexora Platforms", "Product and Technology Companies"),
             ("Softwave Studio", "Product and Technology Companies"), ("Pivotal Arms Robotics", "Robotics and Physical AI Companies"),
             ("Walkabout Machines", "Robotics and Physical AI Companies"), ("Crestline Autonomy", "Autonomous Vehicle Companies"),
             ("Roadsprout AV", "Autonomous Vehicle Companies"), ("Blue Harbor Energy", "Enterprises"),
             ("Alderwood Retail", "Enterprises"), ("Penny Orbit", "Fintech Companies"), ("Safeledger Pay", "Fintech Companies"),
             ("Clearpath Lending", "Fintech Companies")]

# ------------------------------------------------------------------ accounts
accounts = []
opp_account = {}
for i, o in opps.iterrows():
    aid = f"ACC-{101 + i}"
    opp_account[o.opportunity_id] = aid
    status = {"Won": "Customer", "Lost": "Nurture"}.get(o.stage, "Opportunity")
    accounts.append(dict(account_id=aid, account_name=o.client_name, customer_segment=o.customer_segment, region=o.region,
                         owner=o.sales_owner, prospecting_status=status, last_contact_date=o.last_activity_date,
                         next_action=o.next_action, base_service=o.service_offering,
                         icp=random.randint(78, 97) if o.stage == "Won" else random.randint(58, 95)))
for j, (name, seg) in enumerate(PROSPECTS):
    status = random.choice(["Not Started", "Researching", "Contacted", "Engaged", "Meeting Booked", "Contacted", "Researching"])
    last = None if status in ("Not Started", "Researching") else AS_OF - timedelta(days=random.randint(2, 40))
    nxt = {"Not Started": "Run account research", "Researching": "Finish research brief", "Contacted": "Send follow-up email",
           "Engaged": "Book discovery call", "Meeting Booked": "Prepare meeting agenda"}[status]
    accounts.append(dict(account_id=f"ACC-{101 + len(opps) + j}", account_name=name, customer_segment=seg,
                         region=random.choices(["US", "Europe", "LATAM", "APAC"], [.42, .26, .12, .2])[0],
                         owner=random.choice(REPS), prospecting_status=status, last_contact_date=last, next_action=nxt,
                         base_service=SEG_SERVICES[seg], icp=random.randint(48, 92)))
acc = pd.DataFrame(accounts)
acc["industry"] = acc.customer_segment.map(lambda s: random.choice(SEG_INDUSTRY[s]))
acc["company_size"] = [random.choices(["51-200", "201-1,000", "1,001-5,000", "5,001-10,000", "10,000+"],
                                      [.2, .3, .25, .15, .1])[0] for _ in range(len(acc))]
acc["decision_maker_persona"] = acc.customer_segment.map(lambda s: random.choice(SEG_PERSONA[s]))
acc["research_rationale"] = [f"{SEG_TECH[r.customer_segment].split(',')[0]} programs signal demand for {r.base_service}."
                             for r in acc.itertuples()]
acc["source_tool"] = [random.choice(SOURCE_TOOLS) for _ in range(len(acc))]
acc = acc.rename(columns={"icp": "icp_score"})
acc["last_contact_date"] = acc["last_contact_date"].map(lambda d: iso(d) if d else "")
accounts_out = acc[["account_id", "account_name", "industry", "customer_segment", "region", "company_size", "icp_score",
                    "decision_maker_persona", "owner", "prospecting_status", "research_rationale", "source_tool",
                    "last_contact_date", "next_action"]]
accounts_out.to_csv(D / "accounts.csv", index=False)

# ------------------------------------------------------------------ contacts
FIRST = ["Maya", "Liam", "Priya", "Noah", "Elena", "Kenji", "Amara", "Lucas", "Sofia", "Omar", "Chloe", "Diego", "Hana", "Ethan",
         "Zara", "Mateo", "Ingrid", "Arjun", "Leila", "Felix", "Nina", "Tomas", "Aiko", "Callum", "Rania", "Gabriel"]
LAST = ["Alder", "Brooks", "Castillo", "Dhillon", "Ekström", "Fischer", "Gomez", "Hayashi", "Ibrahim", "Jensen", "Kowalski",
        "Lindqvist", "Moreau", "Nakamura", "Okafor", "Petrov", "Quinn", "Rossi", "Sato", "Tanaka", "Underhill", "Vargas",
        "Whitfield", "Xu", "Yilmaz", "Zielinski"]
contacts, used = [], set()
cid = 3001
for r in acc.itertuples():
    for k in range(random.choice([1, 2, 2])):
        while True:
            f, l = random.choice(FIRST), random.choice(LAST)
            if (f, l) not in used:
                used.add((f, l))
                break
        persona = r.decision_maker_persona if k == 0 else random.choice(SEG_PERSONA[r.customer_segment])
        contacts.append(dict(contact_id=f"CON-{cid}", account_id=r.account_id, contact_name=f"{f} {l}", title=persona,
                             email=f"{slug(f)}.{slug(l)}@{slug(r.account_name)}.example.com", is_primary=(k == 0),
                             contact_status=random.choice(["Not contacted", "Contacted", "Replied", "Meeting held"])))
        cid += 1
con = pd.DataFrame(contacts)
con.to_csv(D / "contacts.csv", index=False)
primary = con[con.is_primary].set_index("account_id")["contact_id"].to_dict()

# ------------------------------------------------------------------ leads (50 become opportunities)
SOURCES = ["Outbound SDR", "LinkedIn Outreach", "Inbound Website", "Referral", "Conference", "Partner"]
SRC_W = [.34, .21, .15, .13, .11, .06]
SDR_SOURCES = {"Outbound SDR", "LinkedIn Outreach"}
FIRST_LEAD = date(2026, 1, 5)
leads, opp_created, opp_lead = [], {}, {}
lid = 2001
for i, o in opps.iterrows():
    if o.stage in ("Won", "Lost"):
        created = max(date(2026, 3, 2), o.expected_close_date - timedelta(days=random.randint(45, 150)))
    else:
        created = AS_OF - timedelta(days=random.randint(14, 200))
    created = min(created, o.last_activity_date - timedelta(days=3))
    held = max(FIRST_LEAD, wd(created - timedelta(days=random.randint(1, 5))))
    booked = max(FIRST_LEAD, wd(held - timedelta(days=random.randint(2, 9))))
    qual = max(FIRST_LEAD, wd(booked - timedelta(days=random.randint(1, 7))))
    lead_created = max(FIRST_LEAD, wd(qual - timedelta(days=random.randint(2, 12))))
    leads.append(dict(lead_id=f"LEAD-{lid}", account_id=opp_account[o.opportunity_id], contact_id=primary[opp_account[o.opportunity_id]],
                      lead_source=random.choices(SOURCES, SRC_W)[0], created_date=lead_created, owner=o.sales_owner,
                      qualification_status="Qualified", qualified_date=qual, meeting_booked_date=booked, meeting_held_date=held,
                      opportunity_id=o.opportunity_id, disqualification_reason=""))
    opp_created[o.opportunity_id], opp_lead[o.opportunity_id] = created, f"LEAD-{lid}"
    lid += 1

owner_of = acc.set_index("account_id")["owner"].to_dict()
for _ in range(250):
    a = random.choice(acc.account_id.tolist())
    created = wd(AS_OF - timedelta(days=random.randint(3, 270)))
    age = (AS_OF - created).days
    probs = [.5, .4, .1, 0] if age < 14 else [.05, .25, .40, .30]
    status = random.choices(["New", "Contacted", "Qualified", "Disqualified"], probs)[0]
    qual = booked = held = None
    reason = ""
    if status == "Qualified":
        qual = wd(created + timedelta(days=random.randint(2, 12)))
        if qual > AS_OF:
            status, qual = "Contacted", None
    if status == "Qualified" and random.random() < .6:
        booked = wd(qual + timedelta(days=random.randint(1, 7)))
        if booked > AS_OF:
            booked = None
        else:
            h = wd(booked + timedelta(days=random.randint(2, 9)))
            held = h if (h <= AS_OF and random.random() < .75) else None
    if status == "Disqualified":
        reason = random.choice(["No budget", "Not ICP fit", "No near-term AI data need", "Unresponsive"])
    leads.append(dict(lead_id=f"LEAD-{lid}", account_id=a, contact_id=primary[a], lead_source=random.choices(SOURCES, SRC_W)[0],
                      created_date=created, owner=owner_of[a], qualification_status=status, qualified_date=qual,
                      meeting_booked_date=booked, meeting_held_date=held, opportunity_id="", disqualification_reason=reason))
    lid += 1
lead_df = pd.DataFrame(leads)
for c in ["created_date", "qualified_date", "meeting_booked_date", "meeting_held_date"]:
    lead_df[c] = lead_df[c].map(lambda d: iso(d) if isinstance(d, date) else "")
lead_df.to_csv(D / "leads.csv", index=False)

# ------------------------------------------------------------------ finish opportunities
WON_REASONS = ["Strong technical fit", "Successful pilot", "Best value for quality", "Existing relationship", "Fast delivery plan"]
LOST_REASONS = ["Budget cut", "Chose in-house team", "Lost on price", "No decision / timing", "Competitor with deeper domain expertise"]
opps["account_id"] = opps.opportunity_id.map(opp_account)
opps["lead_id"] = opps.opportunity_id.map(opp_lead)
opps["created_date"] = opps.opportunity_id.map(opp_created)
nf = []
for o in opps.itertuples():
    if o.stage in ("Won", "Lost"):
        nf.append(None)
    elif (AS_OF - o.last_activity_date).days > 30:
        nf.append(o.last_activity_date + timedelta(days=14))
    else:
        nf.append(o.last_activity_date + timedelta(days=random.randint(10, 28)))
opps["next_follow_up_date"] = nf
opps["outcome_reason"] = [random.choice(WON_REASONS) if s == "Won" else random.choice(LOST_REASONS) if s == "Lost" else ""
                          for s in opps.stage]
for c in ["expected_close_date", "last_activity_date", "created_date", "next_follow_up_date"]:
    opps[c] = opps[c].map(lambda d: iso(d) if isinstance(d, date) else "")
opps.to_csv(D / "opportunities.csv", index=False)

# ------------------------------------------------------------------ SDR activity (qualified / meetings come from leads)
REP_FACTOR = {"Jon": 1.10, "Sara": 1.00, "Alex": 0.90, "Emma": 1.05, "Ryan": 0.85}
REP_RESP = {"Jon": .045, "Sara": .05, "Alex": .035, "Emma": .04, "Ryan": .03}
ld = lead_df[lead_df.lead_source.isin(SDR_SOURCES)]


def counts(col, rep):
    s = ld[(ld.owner == rep) & (ld[col] != "")][col]
    return s.value_counts().to_dict()


qual_c = {r: counts("qualified_date", r) for r in REPS}
book_c = {r: counts("meeting_booked_date", r) for r in REPS}
held_c = {r: counts("meeting_held_date", r) for r in REPS}
rows, day = [], FIRST_LEAD
while day <= AS_OF:
    if day.weekday() < 5:
        progress = (day - FIRST_LEAD).days / 280
        for rep in REPS:
            k = day.isoformat()
            q, b, h = qual_c[rep].get(k, 0), book_c[rep].get(k, 0), held_c[rep].get(k, 0)
            if random.random() < .03 and not (q or b or h):    # a day off (never on a day with logged lead outcomes)
                continue
            f = REP_FACTOR[rep] * (1 + .15 * progress)

            def g(mean):
                return max(0, round(random.gauss(mean * f, mean * .2)))
            calls, emails, li, fu, res = g(18), g(30), g(14), g(12), g(6)
            pos = max(round((calls + emails + li) * REP_RESP[rep] * random.uniform(.7, 1.3)), q)
            rows.append(dict(date=k, rep=rep, cold_calls=calls, emails_sent=emails, linkedin_outreach=li, follow_ups=fu,
                             accounts_researched=res, positive_responses=pos, qualified_leads=q, meetings_booked=b,
                             meetings_held=h))
    day += timedelta(days=1)
pd.DataFrame(rows).to_csv(D / "sdr_activity.csv", index=False)
pd.DataFrame([("cold_calls", 100), ("emails_sent", 170), ("linkedin_outreach", 75), ("follow_ups", 60), ("accounts_researched", 30),
              ("positive_responses", 10), ("qualified_leads", 1), ("meetings_booked", 1), ("meetings_held", 1)],
             columns=["metric", "weekly_target"]).to_csv(D / "activity_targets.csv", index=False)

# ------------------------------------------------------------------ research
tools = [
    ("Apollo", "Contact & account data", "Can we build accurate prospect lists for AI Labs and Product companies quickly?", "Broad contact coverage will cut list-building time by half."),
    ("ZoomInfo", "Contact & account data", "Does a premium database improve contact accuracy for Enterprises?", "Higher accuracy offsets higher cost for large-enterprise targeting."),
    ("LinkedIn Sales Navigator", "Social selling", "Is it the best way to reach AI/ML leaders directly?", "Warm LinkedIn outreach beats cold email for technical buyers."),
    ("Clay", "Data enrichment", "Can enrichment workflows combine several sources into one research brief?", "Automated enrichment saves ~30 min per account."),
    ("Cognism", "Contact & account data", "Is European contact data more compliant and complete?", "Better fit for Europe outreach."),
    ("Crunchbase", "Account intelligence", "Do funding signals predict data-services demand?", "Recent funding is a strong buying signal for AI Labs."),
    ("Company Websites", "Manual research", "What can careers pages and blogs tell us about AI data needs?", "Job posts reveal annotation and evaluation needs."),
    ("Industry Reports", "Market research", "Which segments are growing fastest?", "Physical AI and evaluation services are accelerating."),
    ("Lusha", "Contact & account data", "Is a lightweight tool enough for early-stage prospecting?", "Good for quick lookups, weaker for lists."),
    ("Intent Data Platform (demo)", "Intent data", "Can intent signals prioritise accounts showing active research?", "Intent adds value only for accounts with high ICP fit."),
]
st_cycle = ["Completed", "Adopted", "In Progress", "Completed", "Planned", "In Progress", "Adopted", "Completed", "Rejected", "Planned"]
tr = []
for n, (name, cat, obj, hyp) in enumerate(tools):
    status = st_cycle[n]
    cov, acc_, ease, val = (random.randint(2, 5) for _ in range(4))
    tr.append(dict(tool_id=f"TOOL-{n + 1:02d}", tool_name=name, category=cat, research_objective=obj, hypothesis=hyp,
                   data_coverage=cov, data_accuracy=acc_, ease_of_use=ease, value_for_money=val,
                   status=status, owner=random.choice(REPS), start_date=iso(AS_OF - timedelta(days=random.randint(20, 120))),
                   findings="Demo evaluation (fictional): " + ("tested on a 30-account sample; results logged." if status != "Planned" else "not started yet."),
                   recommendation={"Adopted": "Keep in stack", "Rejected": "Do not adopt", "Completed": "Use selectively"}.get(status, "TBD"),
                   next_action={"Planned": "Schedule trial", "In Progress": "Finish sample test", "Completed": "Share summary with team",
                                "Adopted": "Document workflow", "Rejected": "Archive notes"}[status]))
pd.DataFrame(tr).to_csv(D / "tool_research.csv", index=False)

markets = [
    ("Physical AI & egocentric data demand", "Robotics and Physical AI Companies", "APAC", "Size demand for first-person video data.", "Robotics labs will outsource egocentric collection as they scale."),
    ("RLHF vendor landscape", "AI Labs", "US", "Map how labs buy human-feedback services.", "Labs prefer managed programs with strong QA over raw labour."),
    ("AV perception data buyers", "Autonomous Vehicle Companies", "US", "Identify edge-case labelling buyers.", "AV teams pay premiums for rare-scenario annotation."),
    ("Fintech model-evaluation requirements", "Fintech Companies", "Europe", "Understand evaluation needs under new AI rules.", "Regulation drives demand for independent model evaluation."),
    ("Enterprise managed AI programs", "Enterprises", "US", "Learn typical buying cycle length.", "Enterprises buy slower but renew longer."),
    ("Multimodal data pricing benchmarks", "Product and Technology Companies", "Europe", "Benchmark pricing for image+text+audio programs.", "Bundled multimodal pricing can win vs single-modality vendors."),
    ("LATAM AI adoption", "Enterprises", "LATAM", "Find early adopters in LATAM.", "Banks and retailers lead LATAM AI spend."),
    ("APAC robotics hubs", "Robotics and Physical AI Companies", "APAC", "List top robotics clusters.", "Japan and Korea clusters are most ready to buy."),
    ("Model evaluation & benchmarking trend", "AI Labs", "US", "Track demand for third-party evals.", "Independent benchmarks become a standard procurement step."),
    ("Synthetic vs human data debate", "Product and Technology Companies", "US", "Assess threat of synthetic data.", "Synthetic data complements, not replaces, expert human data."),
    ("Annotation tooling market", "Autonomous Vehicle Companies", "Europe", "Compare annotation platforms.", "Platform + managed service beats tooling alone."),
    ("AI Labs vendor consolidation", "AI Labs", "US", "See if labs are reducing vendors.", "Labs consolidate to fewer, higher-quality partners."),
]
mr = []
for n, (topic, seg, reg, obj, hyp) in enumerate(markets):
    status = random.choice(["Completed", "In Progress", "In Progress", "Planned", "Completed"])
    mr.append(dict(research_id=f"MKT-{n + 1:02d}", topic=topic, customer_segment=seg, region=reg, research_objective=obj,
                   business_hypothesis=hyp, source_tool=random.choice(["Industry Report", "LinkedIn", "Company Website", "Apollo"]),
                   owner=random.choice(REPS), status=status, priority=random.choice(["High", "High", "Medium", "Low"]),
                   start_date=iso(AS_OF - timedelta(days=random.randint(10, 150))),
                   findings="Initial findings (fictional): " + ("hypothesis supported by 3 of 4 sources." if status == "Completed" else "work in progress."),
                   implication_for_kai="Prioritise outreach in this segment." if status == "Completed" else "Pending",
                   next_action={"Completed": "Brief the sales team", "In Progress": "Collect 2 more sources", "Planned": "Define sources"}[status]))
pd.DataFrame(mr).to_csv(D / "market_research.csv", index=False)

ar = []
for n, a in enumerate(acc.itertuples()):
    if n % 4 == 3:        # ~75% of accounts have a research brief
        continue
    status = "Completed" if a.prospecting_status in ("Customer", "Opportunity", "Nurture", "Meeting Booked") else random.choice(["In Progress", "Planned", "Completed"])
    ar.append(dict(research_id=f"ACR-{len(ar) + 1:03d}", account_id=a.account_id, owner=a.owner,
                   research_objective=f"Decide whether {a.account_name} fits our {a.base_service} offer.",
                   business_hypothesis=f"{a.customer_segment} teams like this need external expertise to scale AI data work.",
                   why_selected=f"ICP score {a.icp_score}; {SEG_TECH[a.customer_segment].split(',')[0].lower()} focus.",
                   icp_fit="Strong" if a.icp_score >= 80 else "Good" if a.icp_score >= 65 else "Weak",
                   account_priority="High" if a.icp_score >= 80 else "Medium" if a.icp_score >= 65 else "Low",
                   buying_signals="; ".join(random.sample(SIGNALS, 2)), relevant_technologies=SEG_TECH[a.customer_segment],
                   source_tool=a.source_tool, status=status,
                   research_date=iso(AS_OF - timedelta(days=random.randint(3, 160))),
                   findings="Fictional brief: key stakeholders and use cases identified." if status == "Completed" else "In progress.",
                   next_action="Share brief with account owner" if status == "Completed" else "Finish research"))
pd.DataFrame(ar).to_csv(D / "account_research.csv", index=False)

# ------------------------------------------------------------------ collateral
COL_TYPES = ["Capability Deck", "Case Study", "Proposal", "Pitch Deck", "One-Pager", "Email Campaign", "LinkedIn Content", "RFP Response"]
items = []   # (title, type, account_id, opp_id, segment, priority)
segs = list(SEG_PERSONA)
for s in segs:
    items.append((f"Capability Deck - {s}", "Capability Deck", "", "", s, "Medium"))
for svc in ["Egocentric data program", "RLHF quality uplift", "Model evaluation suite", "Multimodal data pipeline", "Managed annotation team",
            "AV edge-case labeling", "Fintech model audit", "Enterprise AI roadmap"]:
    items.append((f"Case Study - {svc}", "Case Study", "", "", random.choice(segs), "Medium"))
for svc in ["AI Training Data Collection", "Annotation and Labeling", "Model Evaluation and Benchmarking", "RLHF and Human-in-the-Loop",
            "Robotics and Egocentric Data", "Managed AI Programs"]:
    items.append((f"One-Pager - {svc}", "One-Pager", "", "", random.choice(segs), "Low"))
oi = opps.set_index("opportunity_id")
for o in opps.itertuples():
    if o.stage in ("Proposal", "Negotiation"):
        items.append((f"Proposal - {o.client_name}", "Proposal", o.account_id, o.opportunity_id, o.customer_segment,
                      "High" if o.stage == "Negotiation" or o.deal_value > 600000 else "Medium"))
    if o.stage in ("Discovery", "Proposal") and random.random() < .5:
        items.append((f"Pitch Deck - {o.client_name}", "Pitch Deck", o.account_id, o.opportunity_id, o.customer_segment, "Medium"))
for a in random.sample(acc.account_id.tolist(), 3):
    r = acc[acc.account_id == a].iloc[0]
    items.append((f"RFP Response - {r.account_name}", "RFP Response", a, "", r.customer_segment, "High"))
for s in random.sample(segs, 5):
    items.append((f"Email Campaign - {s} Q4 outreach", "Email Campaign", "", "", s, "Medium"))
for t in ["Physical AI data quality", "Why human experts matter", "Evaluation beyond benchmarks", "Behind the scenes: managed programs",
          "Customer story spotlight", "Hiring and expert network"]:
    items.append((f"LinkedIn Post Series - {t}", "LinkedIn Content", "", "", random.choice(segs), "Low"))

col = []
for n, (title, typ, a, o, seg, pri) in enumerate(items):
    due = AS_OF + timedelta(days=random.randint(-45, 60))
    owner = oi.loc[o, "sales_owner"] if o else random.choice(REPS)
    if due < AS_OF - timedelta(days=10):
        status = random.choices(["Delivered", "Approved", "In Review", "Drafting"], [.5, .2, .15, .15])[0]
    elif due < AS_OF + timedelta(days=14):
        status = random.choices(["Approved", "In Review", "Drafting", "Not Started"], [.15, .3, .4, .15])[0]
    else:
        status = random.choices(["In Review", "Drafting", "Not Started"], [.15, .4, .45])[0]
    approval = {"Not Started": "Draft", "Drafting": "Draft", "In Review": random.choice(["Manager Review", "Legal Review"]),
                "Approved": "Approved", "Delivered": "Approved"}[status]
    done = iso(min(AS_OF, due + timedelta(days=random.randint(-6, 3)))) if status in ("Approved", "Delivered") else ""
    col.append(dict(item_id=f"COL-{n + 1:03d}", title=title, content_type=typ, owner=owner, account_id=a, opportunity_id=o,
                    customer_segment=seg, status=status, approval_stage=approval, priority=pri, due_date=iso(due),
                    completed_date=done, effort_hours=random.choice([2, 4, 6, 8, 12, 16, 24]),
                    next_action={"Not Started": "Kick off draft", "Drafting": "Complete first draft", "In Review": "Address review comments",
                                 "Approved": "Send to client", "Delivered": "Collect feedback"}[status]))
pd.DataFrame(col).to_csv(D / "collateral.csv", index=False)

# ------------------------------------------------------------------ targets: revenue + gross profit, with a Q4 ramp
BASE = {"Jon": 110_000, "Sara": 100_000, "Alex": 90_000, "Emma": 105_000, "Ryan": 85_000}   # same as generate_data.py
RAMP = [0.8, 0.8, 0.9, 0.9, 1.0, 1.0, 1.1, 1.2, 1.3, 1.8, 2.2, 2.4]                          # plan grows into Q4
trows = []
for r in REPS:
    for mth, f in enumerate(RAMP, 1):
        rev = round(BASE[r] * f, -3)
        trows.append({"sales_owner": r, "month": f"2026-{mth:02d}", "target": rev, "gp_target": round(rev * 0.40, -2)})
pd.DataFrame(trows).to_csv(D / "targets.csv", index=False)

print("accounts", len(acc), "| contacts", len(con), "| leads", len(lead_df), "| sdr rows", len(rows),
      "| collateral", len(col), "| account research", len(ar))
