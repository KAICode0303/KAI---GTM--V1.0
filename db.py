"""Tiny local database layer (SQLite - built into Python, no server, no cost).

The CSV files in data/ are the *seed data*. On first launch they are copied into data/kai_gtm.db.
The app reads from the database, so your edits (e.g. changing a deal's stage) are saved there.
Click "Reset demo data" in the About page (or delete data/kai_gtm.db) to start fresh from the CSVs.
"""
import sqlite3
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "kai_gtm.db"
TABLES = ["opportunities", "accounts", "contacts", "leads", "sdr_activity", "activity_targets", "tool_research",
          "market_research", "account_research", "collateral", "targets"]


def _connect():
    return sqlite3.connect(DB_PATH)


def seed():
    """(Re)create every table from its CSV file."""
    with _connect() as con:
        for t in TABLES:
            pd.read_csv(DATA_DIR / f"{t}.csv").to_sql(t, con, if_exists="replace", index=False)


def init():
    """Create the database on first run (or if a table is missing)."""
    if not DB_PATH.exists():
        seed()
        return
    with _connect() as con:
        have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(TABLES) <= have:
        seed()


def read(table):
    assert table in TABLES, f"unknown table {table}"
    with _connect() as con:
        return pd.read_sql(f"SELECT * FROM {table}", con)


def write(table, df):
    """Replace a whole table with `df` (dates must already be plain text/ISO strings)."""
    assert table in TABLES, f"unknown table {table}"
    with _connect() as con:
        df.to_sql(table, con, if_exists="replace", index=False)
