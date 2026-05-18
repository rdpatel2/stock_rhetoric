"""NYSE open/closed check."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

_NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketStatus:
    is_open: bool
    as_of: date
    reason: str  # "open", "weekend", "holiday: <name>", "after-hours" (currently unused)


def _today() -> date:
    """Today in America/New_York, honoring STOCK_RHETORIC_TODAY override for tests."""
    override = os.environ.get("STOCK_RHETORIC_TODAY")
    if override:
        return datetime.strptime(override, "%Y-%m-%d").date()
    return datetime.now(_NY).date()


def check_nyse(today: date | None = None) -> MarketStatus:
    """Return whether NYSE has a trading session on the given date (default: today ET)."""
    d = today or _today()
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=d, end_date=d)
    if not schedule.empty:
        return MarketStatus(is_open=True, as_of=d, reason="open")

    if d.weekday() >= 5:
        return MarketStatus(is_open=False, as_of=d, reason="weekend")

    # Weekday but no session → exchange holiday. pandas_market_calendars exposes
    # holidays() (US Federal-style) but the canonical NYSE holiday list lives on the
    # underlying calendar object.
    try:
        holidays = nyse.holidays().holidays
        if d in holidays:
            return MarketStatus(is_open=False, as_of=d, reason="holiday")
    except Exception:
        pass
    return MarketStatus(is_open=False, as_of=d, reason="closed")
