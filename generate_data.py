"""Generate the fictional sample dataset for Kai's Company.

Run once:  python generate_data.py
Creates:   data/opportunities.csv  (50 fictional deals)
           data/targets.csv        (monthly sales target per rep)

Everything is invented. A fixed random seed means you get the same file every time.
"""
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

AS_OF = date(2026, 10, 8)  # the "today" of our fictional world
random.seed(7)

REPS = ["Jon", "Sara", "Alex", "Emma", "Ryan"]
MONTHLY_TARGET = {"Jon": 110_000, "Sara": 100_000, "Alex": 90_000, "Emma": 105_000, "Ryan": 85_000}

# Which services make sense for which customer segment
SEGMENT_SERVICES = {
    "AI Labs": ["AI Training Data Collection", "Annotation and Labeling", "Model Evaluation and Benchmarking", "RLHF and Human-in-the-Loop", "Multimodal Data Services"],
    "Product and Technology Companies": ["Annotation and Labeling", "Model Evaluation and Benchmarking", "Multimodal Data Services", "AI Consulting", "Managed AI Programs"],
    "Robotics and Physical AI Companies": ["Robotics and Egocentric Data", "Robotics and Egocentric Data", "AI Training Data Collection", "Multimodal Data Services"],
    "Autonomous Vehicle Companies": ["Annotation and Labeling", "Multimodal Data Services", "Model Evaluation and Benchmarking", "Managed AI Programs"],
    "Enterprises": ["AI Consulting", "Managed AI Programs", "Model Evaluation and Benchmarking", "RLHF and Human-in-the-Loop"],
    "Fintech Companies": ["AI Consulting", "Model Evaluation and Benchmarking", "Managed AI Programs", "Annotation and Labeling"],
}

# (min, max) deal value in USD and (min, max) gross-profit margin per service
SERVICE_ECONOMICS = {
    "AI Training Data Collection": ((150_000, 700_000), (0.32, 0.45)),
    "Annotation and Labeling": ((100_000, 500_000), (0.30, 0.42)),
    "Model Evaluation and Benchmarking": ((120_000, 450_000), (0.42, 0.55)),
    "RLHF and Human-in-the-Loop": ((200_000, 800_000), (0.35, 0.48)),
    "Robotics and Egocentric Data": ((250_000, 900_000), (0.34, 0.46)),
    "Multimodal Data Services": ((180_000, 650_000), (0.36, 0.48)),
    "AI Consulting": ((80_000, 350_000), (0.55, 0.68)),
    "Managed AI Programs": ((300_000, 1_100_000), (0.38, 0.50)),
}

STAGE_PROB = {"Prospecting": 0.10, "Qualified": 0.25, "Discovery": 0.40,
              "Proposal": 0.60, "Negotiation": 0.80, "Won": 1.0, "Lost": 0.0}

# How many of the 50 deals sit in each stage
STAGE_COUNTS = {"Prospecting": 6, "Qualified": 6, "Discovery": 7, "Proposal": 8,
                "Negotiation": 6, "Won": 11, "Lost": 6}

NEXT_ACTIONS = {
    "Prospecting": ["Send intro email", "Book discovery call", "Research buying team", "Share capability deck"],
    "Qualified": ["Confirm budget and timeline", "Map decision makers", "Schedule technical deep-dive", "Share relevant case study"],
    "Discovery": ["Run requirements workshop", "Scope pilot project", "Draft solution outline", "Meet data/ML team"],
    "Proposal": ["Send proposal", "Review pricing with finance", "Walk through proposal", "Prepare pilot SOW"],
    "Negotiation": ["Finalize contract terms", "Get legal review", "Align on delivery SLAs", "Secure executive sign-off"],
    "Won": ["Kick off delivery", "Schedule onboarding call", "Plan first QBR", "Explore expansion"],
    "Lost": ["Log loss reason", "Revisit in 6 months", "Send thank-you note", "Share feedback with team"],
}

# 50 invented company names (each tagged with the segment it fits)
COMPANIES = {
    "AI Labs": ["Quantara Labs", "Neurovane AI", "Synthwave Research", "Cortexa Labs", "Lumenmind AI", "Axiom Cognition", "Parallax Intelligence", "Novaform Labs", "Deepcurrent Labs"],
    "Product and Technology Companies": ["Brightpath Software", "Cloudweave Technologies", "Pixelforge Systems", "Stackhaven", "Orbitly Platforms", "Fernhollow Apps", "Fluxnote Technologies", "Gridline Digital", "Tessera Cloud", "Nimbus Forge"],
    "Robotics and Physical AI Companies": ["Mechanova Robotics", "Atlas Dynamo", "Kinetiq Robotics", "Handsfree Automation", "Roverly Systems", "Gearbloom Robotics", "Stridewell Machines", "Tinkerlift Robotics"],
    "Autonomous Vehicle Companies": ["Autopath Mobility", "Driveon Autonomy", "Lanewise AV", "Tarnwick Motors", "Skyroad Mobility", "Pilotline Vehicles", "Trackwise Autonomy"],
    "Enterprises": ["Harborview Holdings", "Summit Ridge Group", "Meridian Logistics", "Cobalt Retail Group", "Evergreen Health Network", "Ironbridge Industries", "Pinecrest Insurance", "Redwood Manufacturing"],
    "Fintech Companies": ["Ledgerly", "Payvista", "Coinhaven Finance", "Trustleaf Capital", "Moneyloom", "Vaultwise", "Quickpay Nova", "Bankly Orbit"],
}
assert sum(len(v) for v in COMPANIES.values()) == 50

REGION_WEIGHTS = {"US": 0.42, "Europe": 0.26, "LATAM": 0.12, "APAC": 0.20}


def pick_region():
    return random.choices(list(REGION_WEIGHTS), weights=REGION_WEIGHTS.values())[0]


def build_stage_list():
    stages = [s for s, n in STAGE_COUNTS.items() for _ in range(n)]
    random.shuffle(stages)
    return stages


def make_dates(stage):
    """Return (expected_close_date, last_activity_date) that make sense for the stage."""
    if stage == "Won":
        close = date(2026, 1, 12) + timedelta(days=random.randint(0, 270))  # Jan - early Oct
        close = min(close, AS_OF - timedelta(days=3))
        return close, close + timedelta(days=random.randint(0, 2))
    if stage == "Lost":
        close = AS_OF - timedelta(days=random.randint(10, 150))
        return close, close
    # Open deals: close in the future, later stages close sooner
    horizon = {"Prospecting": (90, 190), "Qualified": (70, 160), "Discovery": (45, 120),
               "Proposal": (20, 80), "Negotiation": (7, 45)}[stage]
    close = AS_OF + timedelta(days=random.randint(*horizon))
    # last activity: most deals are fresh, a few are stalled (35+ days)
    stalled = random.random() < 0.30
    days_ago = random.randint(35, 75) if stalled else random.randint(1, 28)
    return close, AS_OF - timedelta(days=days_ago)


def main():
    stages = build_stage_list()
    rows = []
    segments = [seg for seg, names in COMPANIES.items() for _ in names]
    names = [n for ns in COMPANIES.values() for n in ns]
    order = list(range(50))
    random.shuffle(order)

    for i, idx in enumerate(order):
        segment, client, stage = segments[idx], names[idx], stages[i]
        service = random.choice(SEGMENT_SERVICES[segment])
        (vmin, vmax), (gmin, gmax) = SERVICE_ECONOMICS[service]
        deal_value = round(random.randint(vmin, vmax), -3)

        margin = random.uniform(gmin, gmax)
        revenue = deal_value                      # expected revenue = deal value (kept simple)
        cost = round(revenue * (1 - margin), -2)  # delivery cost
        gross_profit = revenue - cost             # GP = revenue - delivery cost

        prob = STAGE_PROB[stage]
        if stage not in ("Won", "Lost"):
            prob = round(min(0.95, max(0.05, prob + random.choice([-0.05, 0, 0, 0.05]))), 2)
        close, last = make_dates(stage)

        rows.append({
            "opportunity_id": f"OPP-{1001 + i}",
            "client_name": client,
            "customer_segment": segment,
            "service_offering": service,
            "region": pick_region(),
            "sales_owner": REPS[i % 5] if i < 50 else random.choice(REPS),
            "stage": stage,
            "deal_value": deal_value,
            "expected_revenue": revenue,
            "expected_delivery_cost": cost,
            "expected_gross_profit": gross_profit,
            "gp_margin_pct": round(gross_profit / revenue * 100, 1),
            "close_probability": prob,
            "expected_close_date": close.isoformat(),
            "last_activity_date": last.isoformat(),
            "next_action": random.choice(NEXT_ACTIONS[stage]),
            "monthly_sales_target": MONTHLY_TARGET[REPS[i % 5]],
        })

    df = pd.DataFrame(rows)
    # Shuffle owners so reps aren't tied to ID order, but keep an even spread (10 deals each)
    owners = df["sales_owner"].tolist()
    random.shuffle(owners)
    df["sales_owner"] = owners
    df["monthly_sales_target"] = df["sales_owner"].map(MONTHLY_TARGET)

    Path("data").mkdir(exist_ok=True)
    df.to_csv("data/opportunities.csv", index=False)

    # Targets file: one row per rep per month, Jan - Dec 2026
    trows = [{"sales_owner": r, "month": f"2026-{m:02d}", "target": MONTHLY_TARGET[r]}
             for r in REPS for m in range(1, 13)]
    pd.DataFrame(trows).to_csv("data/targets.csv", index=False)
    print(f"Wrote {len(df)} opportunities and {len(trows)} target rows.")
    print(df["stage"].value_counts().to_string())


if __name__ == "__main__":
    main()
