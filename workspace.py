"""Loads every table, prepares the columns, and applies the global filters (owner, region, period).

The result is a `Workspace`: one object holding filtered copies of every dataset, so each page
and Hoomi all see exactly the same numbers.
"""
from dataclasses import dataclass

import pandas as pd

import db
import metrics as m

DATE_COLS = {
    "leads": ["created_date", "qualified_date", "meeting_booked_date", "meeting_held_date"],
    "sdr": ["date"],
    "collateral": ["due_date", "completed_date"],
    "accounts": ["last_contact_date"],
    "tool_research": ["start_date"],
    "market_research": ["start_date"],
    "account_research": ["research_date"],
}


@dataclass
class Workspace:
    opps: pd.DataFrame
    accounts: pd.DataFrame
    contacts: pd.DataFrame
    leads: pd.DataFrame
    sdr: pd.DataFrame
    act_targets: pd.DataFrame
    tools: pd.DataFrame
    market: pd.DataFrame
    acct_research: pd.DataFrame
    collateral: pd.DataFrame
    targets: pd.DataFrame
    owners: list
    regions: list
    start: pd.Timestamp
    end: pd.Timestamp


def _dates(df, cols):
    df = df.copy()
    for c in cols:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def load_raw():
    """Read all tables from the database into prepared DataFrames."""
    db.init()
    raw = {
        "opps": m.prepare_opps(db.read("opportunities")),
        "accounts": _dates(db.read("accounts"), DATE_COLS["accounts"]),
        "contacts": db.read("contacts"),
        "leads": _dates(db.read("leads"), DATE_COLS["leads"]),
        "sdr": _dates(db.read("sdr_activity").rename(columns={"rep": "owner"}), DATE_COLS["sdr"]),
        "act_targets": db.read("activity_targets"),
        "tools": _dates(db.read("tool_research"), DATE_COLS["tool_research"]),
        "market": _dates(db.read("market_research"), DATE_COLS["market_research"]),
        "acct_research": _dates(db.read("account_research"), DATE_COLS["account_research"]),
        "collateral": _dates(db.read("collateral"), DATE_COLS["collateral"]),
        "targets": db.read("targets"),
    }
    from analytics import prepare_collateral
    raw["collateral"] = prepare_collateral(raw["collateral"])
    return raw


def build(raw, owners, regions, start, end, segments=None, services=None, stages=None):
    """Apply the global filters to every dataset and return a Workspace."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    acct_region = raw["accounts"].set_index("account_id")["region"]

    seg_ok = lambda s: s.isin(segments) if segments else s.notna() | s.isna()     # None = no filter
    opps = raw["opps"]
    opps = opps[opps["sales_owner"].isin(owners) & opps["region"].isin(regions) & seg_ok(opps["customer_segment"])]
    if services:
        opps = opps[opps["service_offering"].isin(services)]
    if stages:
        opps = opps[opps["stage"].isin(stages)]
    # Period rule: open deals are a live snapshot (always shown); Won/Lost are shown if they closed in the period.
    opps = opps[opps["is_open"] | opps["expected_close_date"].between(start, end)]

    acc = raw["accounts"]
    accounts = acc[acc["owner"].isin(owners) & acc["region"].isin(regions) & seg_ok(acc["customer_segment"])]
    acct_seg = acc.set_index("account_id")["customer_segment"]
    leads = raw["leads"][raw["leads"]["owner"].isin(owners) & raw["leads"]["account_id"].map(acct_region).isin(regions)
                         & seg_ok(raw["leads"]["account_id"].map(acct_seg))]
    leads = leads[leads["created_date"].between(start, end)]
    sdr = raw["sdr"][raw["sdr"]["owner"].isin(owners) & raw["sdr"]["date"].between(start, end)]

    col = raw["collateral"]
    col_region = col["account_id"].map(acct_region)
    col = col[col["owner"].isin(owners) & (col_region.isin(regions) | col_region.isna()) & seg_ok(col["customer_segment"])]
    col = col[col["due_date"].between(start, end) | ~col["is_done"]]

    ar = raw["acct_research"]
    ar = ar[ar["owner"].isin(owners) & ar["account_id"].map(acct_region).isin(regions) & seg_ok(ar["account_id"].map(acct_seg))]
    market = raw["market"]
    market = market[market["owner"].isin(owners) & market["region"].isin(regions) & seg_ok(market["customer_segment"])]

    return Workspace(opps=opps, accounts=accounts, contacts=raw["contacts"], leads=leads, sdr=sdr,
                     act_targets=raw["act_targets"], tools=raw["tools"], market=market, acct_research=ar,
                     collateral=col, targets=raw["targets"], owners=list(owners), regions=list(regions),
                     start=start, end=end)
