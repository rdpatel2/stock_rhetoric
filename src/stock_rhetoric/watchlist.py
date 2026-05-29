"""Watchlist storage + per-ticker quote fetching for digests.

Storage is a single JSON file keyed by `user_key`:
- Telegram users → `str(user.id)`
- CLI → the literal `"cli"`

Validation hits yfinance with a lightweight `fast_info` probe (much cheaper than
`financials.fetch`). The quote helper used for digests fetches just enough data
for one digest line: price, 1d change, 1w change, next earnings date.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf


log = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_DEFAULT_PATH = Path.home() / ".cache" / "stock_rhetoric" / "watchlists.json"


def _path() -> Path:
    return Path(os.environ.get("STOCK_RHETORIC_WATCHLIST_PATH", str(_DEFAULT_PATH)))


def normalize(ticker: str) -> Optional[str]:
    t = (ticker or "").strip().upper()
    return t if _TICKER_RE.match(t) else None


def load() -> dict[str, list[str]]:
    p = _path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict):
            return {}
        return {str(k): sorted(set(str(t).upper() for t in v)) for k, v in data.items()}
    except (json.JSONDecodeError, OSError):
        log.warning("watchlist file corrupt or unreadable: %s", p)
        return {}


def save(data: dict[str, list[str]]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=p.parent, prefix=".watchlists.", suffix=".tmp", delete=False
    ) as f:
        json.dump(data, f, indent=2, sort_keys=True)
        tmp_name = f.name
    os.replace(tmp_name, p)


def get(user_key: str) -> list[str]:
    return load().get(str(user_key), [])


def validate_ticker(ticker: str) -> bool:
    """Quick yfinance probe — does `ticker` resolve to a tradeable symbol?"""
    try:
        info = yf.Ticker(ticker).fast_info
        last = getattr(info, "last_price", None)
        if last is None and isinstance(info, dict):
            last = info.get("last_price") or info.get("lastPrice")
        return last is not None
    except Exception:
        return False


def add(user_key: str, ticker: str) -> tuple[str, str]:
    """Returns (status, normalized_ticker). status ∈ {'added','duplicate','invalid'}."""
    norm = normalize(ticker)
    if norm is None:
        return ("invalid", (ticker or "").upper())
    data = load()
    current = set(data.get(str(user_key), []))
    if norm in current:
        return ("duplicate", norm)
    if not validate_ticker(norm):
        return ("invalid", norm)
    current.add(norm)
    data[str(user_key)] = sorted(current)
    save(data)
    return ("added", norm)


def remove(user_key: str, ticker: str) -> tuple[str, str]:
    """Returns (status, normalized_ticker). status ∈ {'removed','not_in_list','invalid'}."""
    norm = normalize(ticker)
    if norm is None:
        return ("invalid", (ticker or "").upper())
    data = load()
    current = set(data.get(str(user_key), []))
    if norm not in current:
        return ("not_in_list", norm)
    current.remove(norm)
    if current:
        data[str(user_key)] = sorted(current)
    else:
        data.pop(str(user_key), None)
    save(data)
    return ("removed", norm)


def all_user_keys() -> list[str]:
    return sorted(load().keys())


# -------------------------------------------------------------------------------------
# Per-ticker quotes for digests
# -------------------------------------------------------------------------------------


@dataclass
class WatchQuote:
    ticker: str
    price: Optional[float] = None
    change_1d: Optional[float] = None   # decimal fraction (0.012 = +1.2%)
    change_1w: Optional[float] = None
    next_earnings: Optional[date] = None
    error: Optional[str] = None


def _calendar_earnings(t: yf.Ticker) -> Optional[date]:
    """Pull next earnings date from yfinance's calendar — same logic as financials.py."""
    try:
        cal = t.calendar
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            cal = {str(k): v for k, v in cal.iloc[:, 0].items()}
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if isinstance(ed, (list, tuple)) and ed:
                return pd.Timestamp(ed[0]).date()
            if ed is not None:
                return pd.Timestamp(ed).date()
    except Exception:
        return None
    return None


def fetch_quote(ticker: str) -> WatchQuote:
    """Single yfinance call → one digest line's worth of data."""
    q = WatchQuote(ticker=ticker)
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="10d", auto_adjust=True)
        if hist is None or hist.empty:
            q.error = "no data"
            return q
        closes = hist["Close"].dropna()
        if closes.empty:
            q.error = "no closes"
            return q
        last = float(closes.iloc[-1])
        q.price = last
        if len(closes) >= 2:
            prev = float(closes.iloc[-2])
            if prev:
                q.change_1d = last / prev - 1
        # 1-week change: 5 trading sessions back.
        if len(closes) >= 6:
            week_ago = float(closes.iloc[-6])
            if week_ago:
                q.change_1w = last / week_ago - 1
        q.next_earnings = _calendar_earnings(t)
    except Exception as e:
        q.error = f"{type(e).__name__}: {e}"
    return q


async def build_digest(tickers: list[str]) -> list[WatchQuote]:
    """Fetch quotes for all tickers in parallel (bounded concurrency)."""
    sem = asyncio.Semaphore(5)

    async def _one(t: str) -> WatchQuote:
        async with sem:
            return await asyncio.to_thread(fetch_quote, t)

    return await asyncio.gather(*[_one(t) for t in tickers])
