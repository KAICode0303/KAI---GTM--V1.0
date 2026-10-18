"""The demo clock. Demo data is anchored at a fixed 'today' so every figure is reproducible (V1 uses the same date).

Set GTM_CLOCK=real to use the machine's real date instead.
"""
import os
from datetime import date, datetime

import metrics

DEMO_TODAY = metrics.AS_OF.date()          # 2026-10-08, shared with the V1 Command Center


def today():
    return date.today() if os.environ.get("GTM_CLOCK", "").lower() == "real" else DEMO_TODAY


def now():
    """Timestamp for user actions: the demo date with the real time of day (or the real now)."""
    if os.environ.get("GTM_CLOCK", "").lower() == "real":
        return datetime.now().replace(microsecond=0)
    return datetime.combine(DEMO_TODAY, datetime.now().time()).replace(microsecond=0)


def label():
    return f"{today():%b %d, %Y}" + (" (real clock)" if os.environ.get("GTM_CLOCK", "").lower() == "real" else " (demo clock)")
